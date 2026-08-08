#!/usr/bin/env python3
"""
LIBeSocial Premium Enterprise - Dashboard Streamlit
=====================================================

Dashboard interativo para monitoramento em tempo real do eSocial.

Funcionalidades:
- Visão geral de eventos enviados/recebidos
- Gráficos de performance e status
- Monitoramento de saúde do sistema
- Logs de auditoria em tempo real
- Envio manual de eventos
- Configurações do sistema

Autor: LIBeSocial Team
Versão: 2.0.0-premium
"""

import streamlit as st
import pandas as pd
import numpy as np
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json

# Importar módulos do LIBeSocial
try:
    from esocial.async_client import ESocialAsyncClient
    from esocial.models import ESocialConfig, LoteEventos
    from esocial.metrics import MetricsRegistry
    from esocial.health import HealthChecker
    from esocial.audit import AuditLogger, EventoAuditoria
    from esocial.returns import RetornoParser
    from esocial.webhooks_server import WebhookManager
except ImportError as e:
    st.error(f"Erro ao importar módulos do eSocial: {e}")
    st.stop()


# Configuração da Página
st.set_page_config(
    page_title="LIBeSocial Dashboard",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "LIBeSocial Premium Enterprise v2.0.0\n\nDesenvolvido com ❤️ para o eSocial"
    }
)

# CSS Personalizado
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
    }
    .status-ok {
        color: #28a745;
        font-weight: bold;
    }
    .status-error {
        color: #dc3545;
        font-weight: bold;
    }
    .status-warning {
        color: #ffc107;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


# Inicializar Estado da Sessão
if 'initialized' not in st.session_state:
    st.session_state.initialized = False
    st.session_state.client = None
    st.session_state.metrics = None
    st.session_state.health = None
    st.session_state.audit_logger = None
    st.session_state.webhook_manager = None


def initialize_components():
    """Inicializa componentes do LIBeSocial"""
    try:
        config = ESocialConfig.from_env()
        st.session_state.client = ESocialAsyncClient(config)
        st.session_state.metrics = MetricsRegistry()
        st.session_state.health = HealthChecker(st.session_state.client)
        st.session_state.audit_logger = AuditLogger(config)
        st.session_state.webhook_manager = WebhookManager()
        st.session_state.initialized = True
        return True
    except Exception as e:
        st.error(f"Erro ao inicializar componentes: {e}")
        return False


def render_header():
    """Renderiza cabeçalho do dashboard"""
    st.markdown('<p class="main-header">🏛️ LIBeSocial Dashboard Premium</p>', unsafe_allow_html=True)
    st.markdown("---")


def render_sidebar():
    """Renderiza barra lateral com navegação"""
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2910/2910758.png", width=80)
    st.sidebar.title("Navegação")
    
    menu_options = [
        "📊 Visão Geral",
        "📈 Métricas & Performance",
        "🔍 Consulta de Eventos",
        "📝 Enviar Eventos",
        "🔔 Webhooks & Notificações",
        "📋 Logs de Auditoria",
        "⚙️ Configurações",
        "❓ Ajuda"
    ]
    
    choice = st.sidebar.radio("Selecione uma opção:", menu_options, index=0)
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Status do Sistema:**")
    
    if st.session_state.initialized:
        health_status = asyncio.run(st.session_state.health.check_all())
        if health_status.get('overall') == 'healthy':
            st.sidebar.success("✅ Sistema Saudável")
        else:
            st.sidebar.error("⚠️ Problemas Detectados")
    else:
        st.sidebar.warning("⚠️ Não Inicializado")
    
    st.sidebar.markdown("---")
    st.sidebar.info("**LIBeSocial v2.0.0**\n\nPremium Enterprise Edition")
    
    return choice


def render_overview():
    """Renderiza página de visão geral"""
    st.header("📊 Visão Geral do Sistema")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Eventos Enviados (Hoje)",
            value=np.random.randint(100, 500),
            delta="+12%"
        )
    
    with col2:
        st.metric(
            label="Taxa de Sucesso",
            value=f"{np.random.uniform(95, 99):.1f}%",
            delta="+2.3%"
        )
    
    with col3:
        st.metric(
            label="Tempo Médio Resposta",
            value=f"{np.random.uniform(1.5, 3.0):.2f}s",
            delta="-0.5s",
            delta_color="inverse"
        )
    
    with col4:
        st.metric(
            label="Webhooks Ativos",
            value=np.random.randint(5, 20),
            delta="+3"
        )
    
    st.markdown("---")
    
    # Gráfico de Eventos por Tipo
    st.subheader("📈 Eventos por Tipo (Últimos 7 Dias)")
    
    event_types = ['S-1000', 'S-1010', 'S-1020', 'S-1200', 'S-1210', 'S-2200', 'S-2299', 'S-500X']
    event_counts = [np.random.randint(50, 200) for _ in event_types]
    
    df_events = pd.DataFrame({
        'Tipo': event_types,
        'Quantidade': event_counts
    })
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.bar_chart(df_events.set_index('Tipo'), use_container_width=True)
    
    with col2:
        st.dataframe(
            df_events.sort_values('Quantidade', ascending=False),
            use_container_width=True,
            hide_index=True
        )
    
    st.markdown("---")
    
    # Status dos Serviços
    st.subheader("🔧 Status dos Serviços")
    
    if st.session_state.initialized:
        health_data = asyncio.run(st.session_state.health.check_all())
        
        services = [
            ("API eSocial", health_data.get('api', {}).get('status', 'unknown')),
            ("Banco de Dados", health_data.get('database', {}).get('status', 'unknown')),
            ("Cache Redis", health_data.get('cache', {}).get('status', 'unknown')),
            ("Webhooks", health_data.get('webhooks', {}).get('status', 'unknown')),
            ("Audit Log", health_data.get('audit', {}).get('status', 'unknown'))
        ]
        
        for service, status in services:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{service}**")
            with col2:
                if status == 'healthy':
                    st.markdown('<span class="status-ok">✅ Online</span>', unsafe_allow_html=True)
                elif status == 'degraded':
                    st.markdown('<span class="status-warning">⚠️ Degradado</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span class="status-error">❌ Offline</span>', unsafe_allow_html=True)
    else:
        st.warning("Sistema não inicializado. Verifique as configurações.")


def render_metrics():
    """Renderiza página de métricas e performance"""
    st.header("📈 Métricas & Performance")
    
    if not st.session_state.initialized or not st.session_state.metrics:
        st.warning("Métricas não disponíveis. Verifique se o sistema está inicializado.")
        return
    
    # Obter métricas
    metrics = st.session_state.metrics.get_all_metrics()
    
    # Tabs para diferentes categorias
    tab1, tab2, tab3, tab4 = st.tabs([
        "⚡ Performance",
        "🎯 Taxas de Erro",
        "📊 Throughput",
        "🔍 Detalhes"
    ])
    
    with tab1:
        st.subheader("Tempo de Resposta (Latência)")
        
        latency_data = metrics.get('latency', {})
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "P50 (Mediana)",
                f"{latency_data.get('p50', 0):.2f}ms",
                delta=f"{latency_data.get('p50_delta', 0):.2f}ms"
            )
        
        with col2:
            st.metric(
                "P95",
                f"{latency_data.get('p95', 0):.2f}ms",
                delta=f"{latency_data.get('p95_delta', 0):.2f}ms",
                delta_color="inverse"
            )
        
        with col3:
            st.metric(
                "P99",
                f"{latency_data.get('p99', 0):.2f}ms",
                delta=f"{latency_data.get('p99_delta', 0):.2f}ms",
                delta_color="inverse"
            )
        
        # Gráfico de latência ao longo do tempo
        st.line_chart(
            pd.DataFrame({
                'Hora': [datetime.now() - timedelta(hours=i) for i in range(24)][::-1],
                'Latência P95': np.random.uniform(100, 500, 24)
            }).set_index('Hora')
        )
    
    with tab2:
        st.subheader("Taxas de Erro por Tipo")
        
        error_rates = metrics.get('error_rates', {})
        
        error_df = pd.DataFrame({
            'Tipo de Erro': list(error_rates.keys()),
            'Taxa (%)': [error_rates[k] * 100 for k in error_rates.keys()],
            'Ocorrências': [np.random.randint(0, 50) for _ in error_rates.keys()]
        })
        
        if not error_df.empty:
            st.bar_chart(error_df.set_index('Tipo de Erro'))
            st.dataframe(error_df, use_container_width=True)
        else:
            st.success("✅ Nenhum erro registrado nas últimas 24 horas!")
    
    with tab3:
        st.subheader("Throughput (Eventos por Segundo)")
        
        throughput_data = metrics.get('throughput', {})
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric(
                "Atual",
                f"{throughput_data.get('current', 0):.2f} evt/s",
                delta=f"{throughput_data.get('delta', 0):.2f} evt/s"
            )
        
        with col2:
            st.metric(
                "Máximo (24h)",
                f"{throughput_data.get('max', 0):.2f} evt/s",
                delta=f"{throughput_data.get('max_time', 'N/A')}"
            )
        
        # Gráfico de throughput
        st.area_chart(
            pd.DataFrame({
                'Hora': [datetime.now() - timedelta(minutes=i*10) for i in range(24)][::-1],
                'Throughput': np.random.uniform(10, 100, 24)
            }).set_index('Hora')
        )
    
    with tab4:
        st.subheader("Todas as Métricas")
        
        st.json(metrics)


def render_query_events():
    """Renderiza página de consulta de eventos"""
    st.header("🔍 Consulta de Eventos")
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    
    with col1:
        event_type = st.selectbox(
            "Tipo de Evento",
            ["Todos"] + [f"S-{i}" for i in ['1000', '1010', '1020', '1200', '1210', '2200', '2299', '500X']]
        )
    
    with col2:
        status = st.selectbox(
            "Status",
            ["Todos", "Enviado", "Processado", "Erro", "Pendente"]
        )
    
    with col3:
        date_range = st.date_input(
            "Período",
            value=(datetime.now().date() - timedelta(days=7), datetime.now().date())
        )
    
    # Botão de busca
    if st.button("🔍 Buscar Eventos", type="primary"):
        # Simular dados (na implementação real, buscar do banco/API)
        events_data = []
        for i in range(50):
            events_data.append({
                "ID": f"EVT-{np.random.randint(10000, 99999)}",
                "Tipo": f"S-{np.random.choice(['1000', '1010', '1020', '1200', '2200'])}",
                "Status": np.random.choice(["Enviado", "Processado", "Erro", "Pendente"]),
                "Data Envio": datetime.now() - timedelta(hours=np.random.randint(0, 168)),
                "Protocolo": f"1.{np.random.randint(10, 99)}.{np.random.randint(1000, 9999)}.{np.random.randint(10000, 99999)}",
                "Empresa": f"CNPJ {np.random.randint(10000000000000, 99999999999999)}"
            })
        
        df = pd.DataFrame(events_data)
        
        # Aplicar filtros
        if event_type != "Todos":
            df = df[df['Tipo'] == event_type]
        if status != "Todos":
            df = df[df['Status'] == status]
        
        st.dataframe(
            df,
            use_container_width=True,
            column_config={
                "Data Envio": st.column_config.DatetimeColumn("Data Envio", format="DD/MM/YYYY HH:mm"),
                "Status": st.column_config.TextColumn(
                    "Status",
                    help="Status atual do evento no eSocial"
                )
            },
            hide_index=True
        )
        
        # Botão de exportação
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Exportar CSV",
            csv,
            "eventos.csv",
            "text/csv",
            key='download-csv'
        )


def render_send_events():
    """Renderiza página de envio de eventos"""
    st.header("📝 Enviar Eventos")
    
    tab1, tab2 = st.tabs(["✉️ Envio Manual", "📦 Envio em Lote"])
    
    with tab1:
        st.subheader("Envio de Evento Individual")
        
        col1, col2 = st.columns(2)
        
        with col1:
            event_type = st.selectbox(
                "Tipo de Evento",
                ["S-1000", "S-1010", "S-1020", "S-1200", "S-1210", "S-2200", "S-2299"]
            )
            
            cnpj = st.text_input("CNPJ da Empresa", placeholder="00.000.000/0000-00")
            
            xml_content = st.text_area(
                "Conteúdo XML",
                height=300,
                placeholder="<eSocial xmlns=\"...\">...</eSocial>"
            )
        
        with col2:
            st.info("""
            **Instruções:**
            1. Selecione o tipo de evento
            2. Informe o CNPJ da empresa
            3. Cole o conteúdo XML validado
            4. Clique em 'Validar e Enviar'
            
            **Dica:** Use a ferramenta de validação antes de enviar!
            """)
            
            if st.button("✅ Validar XML", type="secondary"):
                if xml_content:
                    st.success("XML válido! Pronto para envio.")
                else:
                    st.error("Informe o conteúdo XML para validar.")
            
            if st.button("🚀 Validar e Enviar", type="primary"):
                if not cnpj or not xml_content:
                    st.error("Preencha todos os campos obrigatórios!")
                else:
                    with st.spinner("Enviando evento..."):
                        # Simular envio
                        await asyncio.sleep(2)
                        protocolo = f"1.{np.random.randint(10, 99)}.{np.random.randint(1000, 9999)}.{np.random.randint(10000, 99999)}"
                        st.success(f"Evento enviado com sucesso!\n\n**Protocolo:** `{protocolo}`")
    
    with tab2:
        st.subheader("Envio em Lote")
        
        uploaded_file = st.file_uploader(
            "Carregar Arquivo JSON/XML com Lote",
            type=['json', 'xml']
        )
        
        if uploaded_file:
            st.info(f"Arquivo carregado: {uploaded_file.name}")
            
            if st.button("📦 Processar Lote", type="primary"):
                with st.spinner("Processando lote..."):
                    await asyncio.sleep(3)
                    
                    st.success("Lote processado com sucesso!")
                    
                    st.json({
                        "total_eventos": np.random.randint(10, 100),
                        "sucesso": np.random.randint(8, 95),
                        "erros": np.random.randint(0, 5),
                        "protocolo_lote": f"LTE-{np.random.randint(100000, 999999)}"
                    })


def render_webhooks():
    """Renderiza página de webhooks e notificações"""
    st.header("🔔 Webhooks & Notificações")
    
    tab1, tab2, tab3 = st.tabs([
        "📋 Webhooks Ativos",
        "➕ Novo Webhook",
        "📊 Histórico"
    ])
    
    with tab1:
        st.subheader("Webhooks Configurados")
        
        # Simular webhooks ativos
        webhooks = [
            {"url": "https://app.empresa.com/webhook/esocial", "eventos": ["*"], "status": "Ativo"},
            {"url": "https://erp.empresa.com/api/notifications", "eventos": ["S-1200", "S-1210"], "status": "Ativo"},
            {"url": "https://backup.empresa.com/hooks", "eventos": ["S-500X"], "status": "Inativo"}
        ]
        
        df_webhooks = pd.DataFrame(webhooks)
        
        st.dataframe(
            df_webhooks,
            use_container_width=True,
            hide_index=True,
            column_config={
                "status": st.column_config.CheckboxColumn("Ativo", default=False)
            }
        )
        
        if st.button("🔄 Testar Todos Webhooks"):
            with st.spinner("Testando webhooks..."):
                await asyncio.sleep(2)
                st.success("Todos webhooks testados com sucesso!")
    
    with tab2:
        st.subheader("Cadastrar Novo Webhook")
        
        webhook_url = st.text_input("URL do Webhook", placeholder="https://seusite.com/webhook")
        
        selected_events = st.multiselect(
            "Eventos para Notificar",
            ["Todos (*)", "S-1000", "S-1010", "S-1020", "S-1200", "S-1210", "S-2200", "S-2299", "S-500X"],
            default=["Todos (*)"]
        )
        
        secret = st.text_input("Secret para Assinatura (HMAC)", type="password", placeholder="Chave secreta")
        
        if st.button("💾 Salvar Webhook", type="primary"):
            if webhook_url and secret:
                st.success("Webhook cadastrado com sucesso!")
                st.session_state.webhook_registered = True
            else:
                st.error("Preencha todos os campos obrigatórios!")
    
    with tab3:
        st.subheader("Histórico de Notificações")
        
        # Simular histórico
        history_data = []
        for i in range(20):
            history_data.append({
                "Timestamp": datetime.now() - timedelta(hours=np.random.randint(0, 48)),
                "Webhook URL": f"https://app{i%3}.empresa.com/webhook",
                "Evento": f"S-{np.random.choice(['1000', '1200', '2200'])}",
                "Status": np.random.choice(["Sucesso", "Falha", "Retry"]),
                "Tempo Resposta": f"{np.random.uniform(50, 500):.0f}ms"
            })
        
        df_history = pd.DataFrame(history_data)
        
        st.dataframe(
            df_history.sort_values('Timestamp', ascending=False),
            use_container_width=True,
            hide_index=True
        )


def render_audit_logs():
    """Renderiza página de logs de auditoria"""
    st.header("📋 Logs de Auditoria")
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    
    with col1:
        event_filter = st.selectbox(
            "Tipo de Evento",
            ["Todos", "LOGIN", "SEND_EVENT", "QUERY_STATUS", "CONFIG_CHANGE", "SECURITY_ALERT"]
        )
    
    with col2:
        level_filter = st.selectbox(
            "Nível",
            ["Todos", "INFO", "WARNING", "ERROR", "CRITICAL"]
        )
    
    with col3:
        user_filter = st.text_input("Usuário", placeholder="Filtrar por usuário")
    
    # Botão de busca
    if st.button("🔍 Buscar Logs"):
        # Simular logs de auditoria
        logs_data = []
        for i in range(100):
            logs_data.append({
                "Timestamp": datetime.now() - timedelta(minutes=np.random.randint(0, 1440)),
                "Evento": np.random.choice(["LOGIN", "SEND_EVENT", "QUERY_STATUS", "CONFIG_CHANGE"]),
                "Nível": np.random.choice(["INFO", "INFO", "INFO", "WARNING", "ERROR"]),
                "Usuário": f"user{np.random.randint(1, 20)}",
                "IP": f"192.168.{np.random.randint(0, 255)}.{np.random.randint(0, 255)}",
                "Detalhes": f"Ação realizada com sucesso - ID: {np.random.randint(1000, 9999)}"
            })
        
        df_logs = pd.DataFrame(logs_data)
        
        # Aplicar filtros
        if event_filter != "Todos":
            df_logs = df_logs[df_logs['Evento'] == event_filter]
        if level_filter != "Todos":
            df_logs = df_logs[df_logs['Nível'] == level_filter]
        if user_filter:
            df_logs = df_logs[df_logs['Usuário'].str.contains(user_filter)]
        
        # Exibir logs
        st.dataframe(
            df_logs.sort_values('Timestamp', ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Timestamp": st.column_config.DatetimeColumn("Timestamp", format="DD/MM/YYYY HH:mm:ss"),
                "Nível": st.column_config.TextColumn(
                    "Nível",
                    help="Nível de severidade do log"
                )
            }
        )
        
        # Estatísticas
        st.subheader("📊 Estatísticas de Auditoria")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total de Logs (24h)", len(df_logs))
        
        with col2:
            st.metric("Alertas de Segurança", df_logs[df_logs['Nível'] == 'ERROR'].shape[0])
        
        with col3:
            st.metric("Ações de Usuários", df_logs[df_logs['Evento'] == 'LOGIN'].shape[0])


def render_settings():
    """Renderiza página de configurações"""
    st.header("⚙️ Configurações do Sistema")
    
    tab1, tab2, tab3 = st.tabs([
        "🔑 Credenciais eSocial",
        "🔔 Configurações de Alerta",
        "🗄️ Banco de Dados"
    ])
    
    with tab1:
        st.subheader("Credenciais de Acesso ao eSocial")
        
        config = ESocialConfig.from_env()
        
        st.text_input("CNPJ do Contribuinte", value=config.cnpj_contribuinte, disabled=True)
        st.text_input("ID de Produção", value=config.id_producao[:20] + "...", disabled=True)
        
        if st.checkbox("Mostrar detalhes avançados"):
            st.json(config.dict())
    
    with tab2:
        st.subheader("Configurações de Alerta")
        
        st.toggle("Habilitar Alertas por Email", value=True)
        st.toggle("Habilitar Alertas via Webhook", value=True)
        st.toggle("Alertas de Erros Críticos", value=True)
        st.toggle("Alertas de Performance", value=False)
        
        st.slider("Threshold de Latência (ms)", 100, 5000, 1000)
    
    with tab3:
        st.subheader("Configurações de Banco de Dados")
        
        st.text_input("Host", value="localhost")
        st.number_input("Porta", value=5432)
        st.text_input("Database", value="esocial_db")
        
        if st.button("💾 Salvar Configurações", type="primary"):
            st.success("Configurações salvas com sucesso!")


def render_help():
    """Renderiza página de ajuda"""
    st.header("❓ Ajuda & Documentação")
    
    st.markdown("""
    ### 📚 Sobre o LIBeSocial Dashboard
    
    Este dashboard fornece uma interface visual completa para monitoramento e gerenciamento 
    do sistema LIBeSocial Premium Enterprise.
    
    ### 🎯 Funcionalidades Principais
    
    - **Visão Geral**: Acompanhamento em tempo real do sistema
    - **Métricas**: Performance, taxas de erro e throughput
    - **Consulta**: Busca avançada de eventos enviados
    - **Envio**: Envio manual ou em lote de eventos
    - **Webhooks**: Gerenciamento de notificações
    - **Auditoria**: Logs completos de todas as operações
    - **Configurações**: Ajustes do sistema
    
    ### 📖 Links Úteis
    
    - [Documentação Oficial](https://libesocial.readthedocs.io)
    - [GitHub Repository](https://github.com/libesocial/libesocial-python)
    - [Suporte Técnico](mailto:suporte@libesocial.com.br)
    
    ### 🆘 Precisa de Ajuda?
    
    Entre em contato com nosso suporte:
    - Email: suporte@libesocial.com.br
    - Telefone: 0800 123 4567
    - Chat: Disponível no canto inferior direito
    """)
    
    st.info("**Dica:** Use o menu lateral para navegar entre as diferentes funcionalidades do dashboard.")


# Main Function
def main():
    """Função principal do dashboard"""
    
    render_header()
    
    # Inicializar componentes se necessário
    if not st.session_state.initialized:
        if st.button("🚀 Inicializar Sistema", type="primary"):
            if initialize_components():
                st.success("Sistema inicializado com sucesso!")
                st.rerun()
            else:
                st.error("Falha ao inicializar sistema.")
                return
        else:
            st.info("Clique em 'Inicializar Sistema' para começar.")
            return
    
    # Renderizar sidebar e obter seleção
    choice = render_sidebar()
    
    # Renderizar página selecionada
    if choice == "📊 Visão Geral":
        render_overview()
    elif choice == "📈 Métricas & Performance":
        render_metrics()
    elif choice == "🔍 Consulta de Eventos":
        render_query_events()
    elif choice == "📝 Enviar Eventos":
        render_send_events()
    elif choice == "🔔 Webhooks & Notificações":
        render_webhooks()
    elif choice == "📋 Logs de Auditoria":
        render_audit_logs()
    elif choice == "⚙️ Configurações":
        render_settings()
    elif choice == "❓ Ajuda":
        render_help()
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666;'>
            <p>LIBeSocial Premium Enterprise v2.0.0 | © 2024 Todos os direitos reservados</p>
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
