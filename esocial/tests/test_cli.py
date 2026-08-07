#!/usr/bin/env python3
"""
Test suite for LIBeSocial CLI
Premium Enterprise Command Line Interface testing
"""

import pytest
import json
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import AsyncMock, patch, MagicMock

from esocial.cli import cli


class TestCLI:
    """Test CLI commands"""
    
    def setup_method(self):
        self.runner = CliRunner()
    
    def test_cli_help(self):
        """Test CLI help message"""
        result = self.runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'LIBeSocial CLI' in result.output
        assert 'validate' in result.output
        assert 'submit' in result.output
        assert 'status' in result.output
    
    def test_cli_version(self):
        """Test CLI version"""
        result = self.runner.invoke(cli, ['--version'])
        assert result.exit_code == 0
        assert '2.0.0-premium' in result.output
    
    @patch('esocial.audit.XMLValidator')
    def test_validate_success(self, mock_validator):
        """Test XML validation success"""
        mock_validator_instance = MagicMock()
        mock_validator_instance.validate_file.return_value = (True, [])
        mock_validator.return_value = mock_validator_instance
        
        # Create temp XML file
        with self.runner.isolated_filesystem():
            xml_file = Path('test.xml')
            xml_file.write_text('<xml/>')
            
            result = self.runner.invoke(cli, ['validate', str(xml_file), '-t', 'S-2200'])
            
            assert result.exit_code == 0
            assert 'Valid XML' in result.output
    
    @patch('esocial.audit.XMLValidator')
    def test_validate_failure(self, mock_validator):
        """Test XML validation failure"""
        mock_validator_instance = MagicMock()
        mock_validator_instance.validate_file.return_value = (False, ['Error 1', 'Error 2'])
        mock_validator.return_value = mock_validator_instance
        
        with self.runner.isolated_filesystem():
            xml_file = Path('test.xml')
            xml_file.write_text('<xml/>')
            
            result = self.runner.invoke(cli, ['validate', str(xml_file), '-t', 'S-2200'])
            
            assert result.exit_code == 1
            assert 'Invalid XML' in result.output
    
    @patch('esocial.cli.AsyncESocialClient')
    def test_submit_dry_run(self, mock_client_class):
        """Test submit with dry-run"""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client
        
        with self.runner.isolated_filesystem():
            xml_file = Path('test.xml')
            xml_file.write_text('<xml/>')
            
            result = self.runner.invoke(cli, ['submit', str(xml_file), '-t', 'S-2200', '--dry-run'])
            
            assert result.exit_code == 0
            assert 'Would submit' in result.output
    
    @patch('esocial.cli.AsyncESocialClient')
    def test_submit_success(self, mock_client_class):
        """Test successful submission"""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.send_event = AsyncMock(return_value={'receipt_number': '1.2.3.4.5'})
        mock_client_class.return_value = mock_client
        
        with self.runner.isolated_filesystem():
            xml_file = Path('test.xml')
            xml_file.write_text('<xml/>')
            
            result = self.runner.invoke(cli, ['submit', str(xml_file), '-t', 'S-2200'])
            
            assert result.exit_code == 0
            assert 'Submitted' in result.output
    
    @patch('esocial.cli.AsyncESocialClient')
    def test_status_check(self, mock_client_class):
        """Test status check"""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.check_status = AsyncMock(return_value={
            'status': 'SUCCESS',
            'receipt_number': '1.2.3.4.5',
            'processing_date': '2024-01-15'
        })
        mock_client_class.return_value = mock_client
        
        result = self.runner.invoke(cli, ['status', '-p', '1.2.3.4.5'])
        
        assert result.exit_code == 0
        assert 'SUCCESS' in result.output
    
    @patch('esocial.cli.AsyncESocialClient')
    def test_returns_query(self, mock_client_class):
        """Test returns query"""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.download_returns = AsyncMock(return_value=[
            {'id': 1, 'event_type': 'S-5001', 'date': '2024-01-15', 'status': 'Processed'}
        ])
        mock_client_class.return_value = mock_client
        
        result = self.runner.invoke(cli, ['returns', '-f', '2024-01-01', '-t', '2024-01-31'])
        
        assert result.exit_code == 0
        assert 'S-5001' in result.output
    
    @patch('esocial.cli.AuditLogger')
    def test_audit_query(self, mock_logger_class):
        """Test audit log query"""
        mock_logger = MagicMock()
        mock_log_entry = MagicMock()
        mock_log_entry.timestamp = MagicMock()
        mock_log_entry.timestamp.strftime.return_value = '2024-01-15 10:00:00'
        mock_log_entry.event_type.value = 'SUBMISSION'
        mock_log_entry.severity = 'INFO'
        mock_log_entry.user_id = 'user123'
        mock_log_entry.details = 'Event submitted successfully'
        mock_log_entry.to_dict.return_value = {'event': 'SUBMISSION'}
        
        mock_logger.query_logs.return_value = [mock_log_entry]
        mock_logger_class.return_value = mock_logger
        
        result = self.runner.invoke(cli, ['audit', '-d', '7'])
        
        assert result.exit_code == 0
        assert 'Audit Logs' in result.output
    
    @patch('esocial.cli.ESocialAsyncClient')
    @patch('esocial.cli.SecretsManager')
    def test_health_check_success(self, mock_secrets_class, mock_client_class):
        """Test health check - all systems operational"""
        # Mock client
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.health_check = AsyncMock(return_value=True)
        mock_client_class.return_value = mock_client
        
        # Mock secrets
        mock_secrets = AsyncMock()
        mock_secrets.health_check = AsyncMock(return_value=True)
        mock_secrets_class.return_value = mock_secrets
        
        # Mock config
        with patch('esocial.cli.ESocialConfig') as mock_config_class:
            mock_config = MagicMock()
            mock_config.is_valid.return_value = True
            mock_config_class.from_env.return_value = mock_config
            
            result = self.runner.invoke(cli, ['health'])
            
            assert result.exit_code == 0
            assert 'All systems operational' in result.output
    
    def test_init_config_output(self):
        """Test config initialization"""
        result = self.runner.invoke(cli, ['init-config'])
        
        assert result.exit_code == 0
        assert 'Sample Configuration' in result.output
        assert 'environment' in result.output
    
    def test_init_config_to_file(self):
        """Test config initialization to file"""
        with self.runner.isolated_filesystem():
            output_file = 'config.json'
            result = self.runner.invoke(cli, ['init-config', '-o', output_file])
            
            assert result.exit_code == 0
            assert Path(output_file).exists()
            
            config = json.loads(Path(output_file).read_text())
            assert 'environment' in config
            assert 'cnpj' in config


class TestCLIBatchSubmission:
    """Test batch submission scenarios"""
    
    def setup_method(self):
        self.runner = CliRunner()
    
    @patch('esocial.cli.ESocialAsyncClient')
    def test_batch_file_submission(self, mock_client_class):
        """Test submission from batch file"""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.send_event = AsyncMock(return_value={'receipt_number': '1.2.3'})
        mock_client_class.return_value = mock_client
        
        with self.runner.isolated_filesystem():
            # Create batch file
            batch_file = Path('batch.json')
            batch_file.write_text(json.dumps({
                'events': [
                    {'file': 'event1.xml', 'type': 'S-2200'},
                    {'file': 'event2.xml', 'type': 'S-2300'}
                ]
            }))
            
            # Create XML files
            Path('event1.xml').write_text('<xml/>')
            Path('event2.xml').write_text('<xml/>')
            
            result = self.runner.invoke(cli, ['submit', '--batch-file', str(batch_file)])
            
            assert result.exit_code == 0
            assert mock_client.send_event.call_count == 2
    
    @patch('esocial.cli.ESocialAsyncClient')
    def test_batch_partial_failure(self, mock_client_class):
        """Test batch with partial failures"""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        async def side_effect(*args, **kwargs):
            if kwargs.get('xml_path') == 'event1.xml':
                return {'receipt_number': '1.2.3'}
            else:
                raise Exception('Network error')
        
        mock_client.send_event = AsyncMock(side_effect=side_effect)
        mock_client_class.return_value = mock_client
        
        with self.runner.isolated_filesystem():
            batch_file = Path('batch.json')
            batch_file.write_text(json.dumps({
                'events': [
                    {'file': 'event1.xml', 'type': 'S-2200'},
                    {'file': 'event2.xml', 'type': 'S-2300'}
                ]
            }))
            
            Path('event1.xml').write_text('<xml/>')
            Path('event2.xml').write_text('<xml/>')
            
            result = self.runner.invoke(cli, ['submit', '--batch-file', str(batch_file)])
            
            assert result.exit_code == 0
            assert 'Success: 1' in result.output
            assert 'Failed: 1' in result.output


class TestCLIReturns:
    """Test returns querying functionality"""
    
    def setup_method(self):
        self.runner = CliRunner()
    
    @patch('esocial.cli.ESocialAsyncClient')
    def test_returns_json_format(self, mock_client_class):
        """Test returns in JSON format"""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.download_returns = AsyncMock(return_value=[
            {'id': 1, 'event_type': 'S-5001', 'date': '2024-01-15', 'status': 'Processed'}
        ])
        mock_client_class.return_value = mock_client
        
        result = self.runner.invoke(cli, ['returns', '--format', 'json'])
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
    
    @patch('esocial.cli.ESocialAsyncClient')
    def test_returns_filter_by_type(self, mock_client_class):
        """Test returns filtered by event type"""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.download_returns = AsyncMock(return_value=[])
        mock_client_class.return_value = mock_client
        
        result = self.runner.invoke(cli, ['returns', '-e', 'S-5001'])
        
        assert result.exit_code == 0
        mock_client.download_returns.assert_called_once_with(
            from_date=None,
            to_date=None,
            event_type='S-5001'
        )


class TestCLIAudit:
    """Test audit log functionality"""
    
    def setup_method(self):
        self.runner = CliRunner()
    
    @patch('esocial.cli.AuditLogger')
    def test_audit_filter_by_severity(self, mock_logger_class):
        """Test audit logs filtered by severity"""
        mock_logger = MagicMock()
        mock_logger.query_logs.return_value = []
        mock_logger_class.return_value = mock_logger
        
        result = self.runner.invoke(cli, ['audit', '-s', 'ERROR'])
        
        assert result.exit_code == 0
        mock_logger.query_logs.assert_called_once()
        call_kwargs = mock_logger.query_logs.call_args[1]
        assert call_kwargs['severity'] == 'ERROR'
    
    @patch('esocial.cli.AuditLogger')
    def test_audit_filter_by_event_type(self, mock_logger_class):
        """Test audit logs filtered by event type"""
        mock_logger = MagicMock()
        mock_logger.query_logs.return_value = []
        mock_logger_class.return_value = mock_logger
        
        result = self.runner.invoke(cli, ['audit', '-e', 'SUBMISSION'])
        
        assert result.exit_code == 0
        call_kwargs = mock_logger.query_logs.call_args[1]
        assert call_kwargs['event_type'] == 'SUBMISSION'
    
    @patch('esocial.cli.AuditLogger')
    def test_audit_json_export(self, mock_logger_class):
        """Test audit logs export to JSON"""
        mock_logger = MagicMock()
        mock_log = MagicMock()
        mock_log.to_dict.return_value = {'event': 'test'}
        mock_logger.query_logs.return_value = [mock_log]
        mock_logger_class.return_value = mock_logger
        
        result = self.runner.invoke(cli, ['audit', '--format', 'json'])
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
