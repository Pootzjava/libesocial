#!/bin/bash
# LIBeSocial Premium Enterprise - Script de Instalação Automática
# ================================================================
# Este script instala todos os componentes do LIBeSocial Premium
# incluindo dependências Python, Docker, documentação e exemplos.

set -e  # Exit on error

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funções utilitárias
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_command() {
    if ! command -v $1 &> /dev/null; then
        log_error "$1 não está instalado. Por favor instale primeiro."
        exit 1
    fi
}

# Verificar pré-requisitos
log_info "Verificando pré-requisitos..."

check_command python3
check_command pip3

# Detectar sistema operacional
OS="$(uname -s)"
case "${OS}" in
    Linux*)     OS_NAME="Linux";;
    Darwin*)    OS_NAME="macOS";;
    *)          OS_NAME="Unknown";;
esac

log_info "Sistema operacional detectado: ${OS_NAME}"

# Criar ambiente virtual
log_info "Criando ambiente virtual Python..."
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependências Python
log_info "Instalando dependências Python..."
pip3 install --upgrade pip
pip3 install -e ".[all]"

# Verificar se Docker está disponível
if command -v docker &> /dev/null; then
    log_info "Docker detectado. Configurando containers..."
    
    # Build das imagens Docker
    log_info "Build da imagem Docker principal..."
    docker build -t libesocial:latest .
    
    # Configurar docker-compose (opcional)
    if [ -f "docker-compose.yml" ]; then
        log_info "Configurando serviços com docker-compose..."
        docker-compose config --quiet && log_success "Configuração docker-compose válida!"
    fi
else
    log_warning "Docker não detectado. Pulando configuração de containers."
fi

# Instalar dependências para documentação
log_info "Instalando ferramentas de documentação..."
pip3 install mkdocs mkdocs-material mkdocstrings pymdown-extensions

# Verificar se MkDocs foi instalado corretamente
if command -v mkdocs &> /dev/null; then
    log_success "MkDocs instalado com sucesso!"
    log_info "Para construir a documentação, execute: mkdocs build"
else
    log_warning "MkDocs não foi instalado. Documentação não estará disponível."
fi

# Instalar Streamlit para dashboard
log_info "Instalando Streamlit para dashboard..."
pip3 install streamlit plotly

# Configurar variáveis de ambiente
log_info "Criando arquivo de variáveis de ambiente de exemplo..."
if [ ! -f ".env.example" ]; then
    cat > .env.example << 'ENVEOF'
# LIBeSocial Premium Enterprise - Variáveis de Ambiente
# ======================================================

# Configurações eSocial
ESOCIAL_CNPJ_CONTRIBUINTE=00000000000000
ESOCIAL_ID_PRODUCAO=ID_DA_PRODUCAO
ESOCIAL_AMBIENTE=producao  # producao ou homologacao
ESOCIAL_TIMEOUT=30
ESOCIAL_MAX_RETRIES=3

# Configurações de Segurança
ESOCIAL_CERT_PATH=/path/to/cert.pem
ESOCIAL_KEY_PATH=/path/to/key.pem
ESOCIAL_CA_BUNDLE=/path/to/ca-bundle.crt

# Secrets Management (opcional)
SECRETS_PROVIDER=environment  # environment, aws, azure, vault
AWS_SECRET_NAME=libesocial/secrets
AZURE_KEYVAULT_NAME=my-keyvault
VAULT_URL=https://vault.example.com

# Redis Cache (opcional)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Database (opcional para auditoria)
DATABASE_URL=postgresql://user:pass@localhost:5432/esocial_db

# Webhooks
WEBHOOK_SECRET=minha_chave_secreta_hmac
WEBHOOK_RETRY_ATTEMPTS=3
WEBHOOK_TIMEOUT=10

# Monitoring
METRICS_ENABLED=true
TRACING_ENABLED=true
ALERT_EMAIL=suporte@empresa.com
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/xxx
ENVEOF
    log_success "Arquivo .env.example criado!"
fi

# Copiar para .env se não existir
if [ ! -f ".env" ]; then
    cp .env.example .env
    log_warning "Arquivo .env criado a partir do exemplo. Edite com suas configurações!"
fi

# Executar testes
log_info "Executando testes para validar instalação..."
if python3 -m pytest tests/ -v --tb=short; then
    log_success "Todos os testes passaram! Instalação validada."
else
    log_warning "Alguns testes falharam. Verifique a configuração."
fi

# Mostrar próximo passos
echo ""
log_success "=============================================="
log_success "LIBeSocial Premium Enterprise instalado!"
log_success "=============================================="
echo ""
log_info "Próximos passos:"
echo ""
echo "1. Ative o ambiente virtual:"
echo "   source .venv/bin/activate"
echo ""
echo "2. Configure suas credenciais no arquivo .env:"
echo "   nano .env"
echo ""
echo "3. Execute o CLI para testar:"
echo "   esocial-cli --help"
echo ""
echo "4. Inicie o dashboard:"
echo "   streamlit run esocial/dashboard.py"
echo ""
echo "5. Construa a documentação:"
echo "   mkdocs serve"
echo ""
echo "6. (Opcional) Inicie containers Docker:"
echo "   docker-compose up -d"
echo ""
log_info "Para mais informações, consulte a documentação em docs/"
echo ""

# Desativar ambiente virtual
deactivate

log_success "Instalação concluída com sucesso! 🎉"
