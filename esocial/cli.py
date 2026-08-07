#!/usr/bin/env python3
"""
LIBeSocial CLI - Command Line Interface for eSocial operations
Premium Enterprise Tool for validation, submission and monitoring
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, List
import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich import box

from esocial.async_client import AsyncESocialClient as ESocialAsyncClient
from esocial.models import BatchConfig, ESocialConfig, EventType
from esocial.secrets import SecretsManager
from esocial.audit import AuditLogger, AuditEventType as EventType
from esocial.returns import ReturnParser as ReturnsParser

console = Console()

@click.group()
@click.version_option(version='2.0.0-premium', prog_name='esocial-cli')
@click.option('--env', default='production', help='Environment: production, homologation')
@click.option('--config', '-c', type=click.Path(exists=True), help='Path to config file')
@click.pass_context
def cli(ctx, env: str, config: Optional[str]):
    """
    🏛️  LIBeSocial CLI - Premium Enterprise Tool
    
    Manage eSocial events with enterprise-grade features:
    - Validation, submission, monitoring
    - Security, audit logging, compliance
    - Async operations, batch processing
    """
    ctx.ensure_object(dict)
    ctx.obj['ENV'] = env
    ctx.obj['CONFIG'] = config
    
    # Load configuration
    if config:
        ctx.obj['CONFIG_DATA'] = json.loads(Path(config).read_text())
    else:
        ctx.obj['CONFIG_DATA'] = {}


@cli.command()
@click.argument('xml_file', type=click.Path(exists=True))
@click.option('--event-type', '-t', required=True, help='Event type (e.g., S-1000, S-2200)')
@click.option('--strict/--no-strict', default=True, help='Strict validation mode')
@click.pass_context
def validate(ctx, xml_file: str, event_type: str, strict: bool):
    """
    Validate XML event against eSocial XSD schemas
    
    Example:
        esocial-cli validate evento.xml -t S-2200
    """
    xml_path = Path(xml_file)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Validating [bold cyan]{xml_path.name}[/]", total=None)
        
        try:
            from esocial.xml import XMLValidate
            validator = XMLValidate(event_type=event_type, strict=strict)
            is_valid, errors = validator.validate_file(str(xml_path))
            
            progress.update(task, completed=True)
            
            if is_valid:
                console.print(Panel(
                    f"[green]✓ Valid XML[/]\n\nFile: {xml_path}\nEvent: {event_type}\nSchema: eSocial {event_type}",
                    title="✅ Validation Successful",
                    box=box.DOUBLE_EDGE,
                    border_style="green"
                ))
                sys.exit(0)
            else:
                error_list = "\n".join([f"  • {err}" for err in errors[:5]])
                if len(errors) > 5:
                    error_list += f"\n  ... and {len(errors) - 5} more errors"
                
                console.print(Panel(
                    f"[red]✗ Invalid XML[/]\n\n{error_list}",
                    title="❌ Validation Failed",
                    box=box.DOUBLE_EDGE,
                    border_style="red"
                ))
                sys.exit(1)
                
        except Exception as e:
            progress.update(task, completed=True)
            console.print(f"[red]Error:[/red] {str(e)}")
            sys.exit(1)


@cli.command()
@click.argument('xml_files', nargs=-1, type=click.Path(exists=True))
@click.option('--batch-file', '-b', type=click.Path(exists=True), help='JSON file with batch config')
@click.option('--event-type', '-t', help='Event type for all files')
@click.option('--dry-run', is_flag=True, help='Validate only, don\'t submit')
@click.option('--async-mode', is_flag=True, help='Use async submission')
@click.pass_context
def submit(ctx, xml_files: tuple, batch_file: Optional[str], event_type: Optional[str], dry_run: bool, async_mode: bool):
    """
    Submit events to eSocial
    
    Examples:
        esocial-cli submit evento1.xml evento2.xml -t S-2200
        esocial-cli submit --batch-file batch.json --dry-run
    """
    config_data = ctx.obj['CONFIG_DATA']
    env = ctx.obj['ENV']
    
    # Prepare batch
    events = []
    if batch_file:
        batch_data = json.loads(Path(batch_file).read_text())
        events = batch_data.get('events', [])
    elif xml_files:
        events = [
            {"file": str(f), "type": event_type or "S-1000"}
            for f in xml_files
        ]
    else:
        console.print("[red]Error:[/red] No XML files or batch file provided")
        sys.exit(1)
    
    async def run_submission():
        config = ESocialConfig.from_env() if not config_data else ESocialConfig(**config_data)
        
        async with ESocialAsyncClient(config=config) as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Submitting events...", total=len(events))
                
                if dry_run:
                    progress.update(task, description="Dry run - validating only...")
                    for event in events:
                        console.print(f"  ✓ Would submit: {event['file']}")
                        progress.advance(task)
                    return
                
                # Submit events
                results = []
                for event in events:
                    try:
                        result = await client.send_event(
                            event_type=event['type'],
                            xml_path=event['file']
                        )
                        results.append(result)
                        console.print(f"  ✓ Submitted: {event['file']} → {result.get('receipt_number', 'N/A')}")
                    except Exception as e:
                        console.print(f"  ✗ Failed: {event['file']} → {str(e)}")
                        results.append({"error": str(e)})
                    finally:
                        progress.advance(task)
                
                # Summary
                success_count = sum(1 for r in results if 'receipt_number' in r)
                console.print(Panel(
                    f"[bold]Results:[/bold]\n"
                    f"✓ Success: {success_count}\n"
                    f"✗ Failed: {len(results) - success_count}",
                    title="📊 Submission Summary",
                    box=box.ROUNDED
                ))
    
    asyncio.run(run_submission())


@cli.command()
@click.option('--protocol', '-p', required=True, help='Protocol number to check')
@click.option('--wait', '-w', is_flag=True, help='Wait until processing completes')
@click.option('--timeout', default=300, help='Timeout in seconds when using --wait')
@click.pass_context
def status(ctx, protocol: str, wait: bool, timeout: int):
    """
    Check processing status of a submitted batch
    
    Examples:
        esocial-cli status -p 1.2.3.4.5.6.7.8.9
        esocial-cli status -p 1.2.3.4.5.6.7.8.9 --wait
    """
    config_data = ctx.obj['CONFIG_DATA']
    config = ESocialConfig.from_env() if not config_data else ESocialConfig(**config_data)
    
    async def check_status():
        async with ESocialAsyncClient(config=config) as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(f"Checking protocol {protocol}...", total=None)
                
                if wait:
                    progress.update(task, description=f"Waiting for protocol {protocol}...")
                    result = await client.wait_processing(protocol, timeout=timeout)
                else:
                    result = await client.check_status(protocol)
                
                progress.update(task, completed=True)
                
                # Display results
                table = Table(title=f"Status - Protocol {protocol}", box=box.ROUNDED)
                table.add_column("Field", style="cyan")
                table.add_column("Value", style="green")
                
                table.add_row("Status", result.get('status', 'UNKNOWN'))
                table.add_row("Receipt Number", result.get('receipt_number', 'N/A'))
                table.add_row("Processing Date", result.get('processing_date', 'N/A'))
                
                if 'events' in result:
                    for idx, event in enumerate(result['events']):
                        table.add_row(
                            f"Event {idx+1}",
                            f"{event.get('type')} - {event.get('status', 'Pending')}"
                        )
                
                console.print(table)
                
                # Show errors if any
                if result.get('errors'):
                    error_table = Table(title="⚠️ Errors", box=box.ROUNDED, border_style="red")
                    error_table.add_column("Event", style="yellow")
                    error_table.add_column("Error", style="red")
                    for error in result['errors']:
                        error_table.add_row(error.get('event_id', 'N/A'), error.get('message', 'Unknown error'))
                    console.print(error_table)
    
    asyncio.run(check_status())


@cli.command()
@click.option('--from-date', '-f', help='Start date (YYYY-MM-DD)')
@click.option('--to-date', '-t', help='End date (YYYY-MM-DD)')
@click.option('--event-type', '-e', help='Filter by event type')
@click.option('--format', 'fmt', type=click.Choice(['table', 'json']), default='table')
@click.pass_context
def returns(ctx, from_date: Optional[str], to_date: Optional[str], event_type: Optional[str], fmt: str):
    """
    Query and download event returns (S-500X series)
    
    Examples:
        esocial-cli returns -f 2024-01-01 -t 2024-01-31
        esocial-cli returns -e S-5001 --format json
    """
    config_data = ctx.obj['CONFIG_DATA']
    config = ESocialConfig.from_env() if not config_data else ESocialConfig(**config_data)
    
    async def fetch_returns():
        async with ESocialAsyncClient(config=config) as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Fetching returns...", total=None)
                
                returns = await client.download_returns(
                    from_date=from_date,
                    to_date=to_date,
                    event_type=event_type
                )
                
                progress.update(task, completed=True)
                
                if fmt == 'json':
                    console.print(json.dumps(returns, indent=2, default=str))
                else:
                    table = Table(title=f"Returns ({len(returns)} found)", box=box.ROUNDED)
                    table.add_column("ID", style="cyan")
                    table.add_column("Type", style="yellow")
                    table.add_column("Date", style="green")
                    table.add_column("Status", style="blue")
                    
                    for ret in returns[:20]:  # Limit display
                        table.add_row(
                            str(ret.get('id', 'N/A')),
                            ret.get('event_type', 'Unknown'),
                            ret.get('date', 'N/A'),
                            ret.get('status', 'Unknown')
                        )
                    
                    console.print(table)
                    
                    if len(returns) > 20:
                        console.print(f"\n[yellow]... and {len(returns) - 20} more returns[/]")
    
    asyncio.run(fetch_returns())


@cli.command()
@click.option('--days', '-d', default=30, help='Audit logs from last N days')
@click.option('--event-type', '-e', type=click.Choice([e.value for e in EventType]), help='Filter by event type')
@click.option('--severity', '-s', type=click.Choice(['INFO', 'WARNING', 'ERROR', 'CRITICAL']), help='Filter by severity')
@click.option('--format', 'fmt', type=click.Choice(['table', 'json']), default='table')
@click.pass_context
def audit(ctx, days: int, event_type: Optional[str], severity: Optional[str], fmt: str):
    """
    Query audit logs for compliance and security review
    
    Examples:
        esocial-cli audit -d 7
        esocial-cli audit -e SUBMISSION -s ERROR
    """
    from datetime import datetime, timedelta, timezone
    
    logger = AuditLogger(service_name='esocial-cli')
    
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    logs = logger.query_logs(
        start_date=start_date,
        event_type=event_type,
        severity=severity
    )
    
    if fmt == 'json':
        output = [log.to_dict() for log in logs]
        console.print(json.dumps(output, indent=2, default=str))
    else:
        table = Table(title=f"Audit Logs (Last {days} days, {len(logs)} entries)", box=box.ROUNDED)
        table.add_column("Timestamp", style="cyan")
        table.add_column("Event", style="yellow")
        table.add_column("Severity", style="red")
        table.add_column("User", style="green")
        table.add_column("Details", style="white")
        
        for log in logs[:50]:  # Limit display
            severity_style = {
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'orange3',
                'CRITICAL': 'red bold'
            }.get(log.severity, 'white')
            
            table.add_row(
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.event_type.value,
                f"[{severity_style}]{log.severity}[/{severity_style}]",
                log.user_id or 'system',
                log.details[:50] + '...' if len(log.details) > 50 else log.details
            )
        
        console.print(table)
        
        if len(logs) > 50:
            console.print(f"\n[yellow]... and {len(logs) - 50} more log entries[/]")


@cli.command()
@click.pass_context
def health(ctx):
    """
    Check system health and connectivity
    """
    config_data = ctx.obj['CONFIG_DATA']
    
    async def check_health():
        try:
            config = ESocialConfig() if not config_data else ESocialConfig(**config_data)
        except Exception as e:
            console.print(f"[red]Configuration error:[/red] {str(e)}")
            sys.exit(1)
        
        async with ESocialAsyncClient(config=config) as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Running health checks...", total=4)
                
                # Check 1: Configuration
                progress.update(task, description="Checking configuration...")
                config_ok = config.is_valid()
                progress.advance(task)
                
                # Check 2: Secrets
                progress.update(task, description="Checking secrets...")
                secrets_mgr = SecretsManager()
                secrets_ok = await secrets_mgr.health_check()
                progress.advance(task)
                
                # Check 3: Connectivity
                progress.update(task, description="Checking eSocial connectivity...")
                try:
                    conn_ok = await client.health_check()
                except:
                    conn_ok = False
                progress.advance(task)
                
                # Check 4: Audit Logger
                progress.update(task, description="Checking audit logger...")
                logger = AuditLogger(service_name='health-check')
                logger.log(
                    event_type=EventType.SYSTEM_HEALTH,
                    actor='cli',
                    action='health_check',
                    resource='system',
                    resource_type='component'
                )
                audit_ok = True
                progress.advance(task)
                
                # Results
                table = Table(title="🏥 System Health Check", box=box.DOUBLE_EDGE)
                table.add_column("Component", style="cyan")
                table.add_column("Status", style="green")
                
                status_icon = lambda ok: "[green]✓ OK[/]" if ok else "[red]✗ FAILED[/]"
                
                table.add_row("Configuration", status_icon(config_ok))
                table.add_row("Secrets Manager", status_icon(secrets_ok))
                table.add_row("eSocial Connectivity", status_icon(conn_ok))
                table.add_row("Audit Logger", status_icon(audit_ok))
                
                console.print(table)
                
                all_ok = all([config_ok, secrets_ok, conn_ok, audit_ok])
                if all_ok:
                    console.print(Panel("[green]✓ All systems operational[/]", title="Health Status", border_style="green"))
                    sys.exit(0)
                else:
                    console.print(Panel("[red]✗ Some components failed[/]", title="Health Status", border_style="red"))
                    sys.exit(1)
    
    asyncio.run(check_health())


@cli.command()
@click.option('--output', '-o', type=click.Path(), help='Output file for sample config')
@click.pass_context
def init_config(ctx, output: Optional[str]):
    """
    Generate sample configuration file
    """
    sample_config = {
        "environment": "homologation",
        "cnpj": "00000000000000",
        "cert_path": "/path/to/cert.pem",
        "cert_password": "${CERT_PASSWORD}",
        "api_url": "https://prepro.receita.economia.gov.br",
        "timeout": 30,
        "max_retries": 3,
        "retry_delay": 2.0,
        "enable_circuit_breaker": True,
        "circuit_breaker_threshold": 5,
        "circuit_breaker_timeout": 60,
        "enable_rate_limit": True,
        "rate_limit_per_minute": 60,
        "enable_caching": True,
        "cache_ttl": 300,
        "secrets_provider": "environment",
        "audit_enabled": True,
        "audit_level": "INFO"
    }
    
    config_json = json.dumps(sample_config, indent=2)
    
    if output:
        Path(output).write_text(config_json)
        console.print(f"[green]✓ Configuration written to {output}[/]")
    else:
        console.print(Panel(
            config_json,
            title="📋 Sample Configuration (esocial-config.json)",
            subtitle="Save this file and use with: esocial-cli -c esocial-config.json",
            box=box.ROUNDED
        ))


def main():
    """Main entry point"""
    cli(obj={})


if __name__ == '__main__':
    main()
