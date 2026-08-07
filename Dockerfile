# LIBeSocial Premium - Dockerfile Multi-Stage
# ============================================
# Produto: LIBeSocial Premium Enterprise v2.0.0
# Estágios: builder → test → production
# Tamanho final estimado: ~45MB (alpine + python slim)

# =============================================================================
# STAGE 1: BUILDER - Instalação de dependências e build
# =============================================================================
FROM python:3.11-slim as builder

LABEL maintainer="LIBeSocial Team <team@libesocial.com>"
LABEL version="2.0.0-premium"
LABEL description="Brazilian eSocial Premium Library - Build Stage"

# Variáveis de ambiente de build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.7.1

# Instalar dependências do sistema necessárias
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar Poetry para gerenciamento de dependências
RUN pip install "poetry==${POETRY_VERSION}"

# Criar diretório de trabalho
WORKDIR /app

# Copiar apenas arquivos de definição de dependências primeiro (cache layer)
COPY pyproject.toml poetry.lock* ./

# Instalar dependências no virtualenv do Poetry
RUN poetry config virtualenvs.create true \
    && poetry config virtualenvs.in-project true \
    && poetry install --only main --no-interaction --no-ansi

# Copiar código fonte
COPY esocial/ ./esocial/
COPY tests/ ./tests/

# Rodar testes no stage de builder (opcional, pode ser pulado em prod)
# RUN poetry run pytest tests/ -v --tb=short

# =============================================================================
# STAGE 2: TEST - Execução de testes e validações
# =============================================================================
FROM builder as test

LABEL description="LIBeSocial Premium - Test Stage"

# Instalar dependências de desenvolvimento
RUN poetry install --no-interaction --no-ansi

# Copiar configurações de linting e testing
COPY .flake8 .mypy.ini pytest.ini coverage.xml* ./

# Executar validações de qualidade
RUN poetry run flake8 esocial/ tests/ --max-line-length=120 --ignore=E501,W503 \
    && poetry run mypy esocial/ --ignore-missing-imports \
    && poetry run pytest tests/ -v --tb=short --cov=esocial --cov-report=xml \
    && echo "✅ All tests and validations passed!"

# =============================================================================
# STAGE 3: PRODUCTION - Imagem final otimizada
# =============================================================================
FROM python:3.11-slim as production

LABEL maintainer="LIBeSocial Team <team@libesocial.com>"
LABEL version="2.0.0-premium"
LABEL description="Brazilian eSocial Premium Library - Production Ready"
LABEL org.opencontainers.image.source="https://github.com/libesocial/libesocial-python"
LABEL org.opencontainers.image.licenses="MIT"

# Variáveis de ambiente de produção
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/app/.venv/bin:$PATH" \
    ESOCIAL_ENV=production \
    ESOCIAL_LOG_LEVEL=INFO \
    ESOCIAL_TIMEOUT=30 \
    ESOCIAL_MAX_RETRIES=3

# Criar usuário não-root para segurança
RUN groupadd --gid 1000 esocial \
    && useradd --uid 1000 --gid esocial --shell /bin/bash --create-home esocial

# Instalar apenas runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Copiar virtualenv do builder
COPY --from=builder /app/.venv /app/.venv

# Copiar código fonte
COPY esocial/ ./esocial/
COPY pyproject.toml ./

# Copiar scripts de entrypoint
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Mudar proprietário para usuário não-root
RUN chown -R esocial:esocial /app

# Mudar para usuário não-root
USER esocial

# Expor porta para health checks (se houver API)
EXPOSE 8080

# Health check integrado
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from esocial import __version__; print(f'Health OK: {__version__}')" || exit 1

# Entrypoint principal
ENTRYPOINT ["docker-entrypoint.sh"]

# Comando padrão (pode ser sobrescrito)
CMD ["python", "-m", "esocial.cli", "--help"]

# =============================================================================
# INSTRUÇÕES DE USO:
# =============================================================================
# Build da imagem:
#   docker build -t libesocial/premium:2.0.0 --target production .
#
# Build com testes:
#   docker build -t libesocial/premium:2.0.0-test --target test .
#
# Run CLI:
#   docker run --rm libesocial/premium:2.0.0 esocial-cli --help
#
# Run com variáveis de ambiente:
#   docker run --rm -e ESOCIAL_CNPJ=00.000.000/0001-00 libesocial/premium:2.0.0
#
# Development mode:
#   docker-compose up dev
#
# Production mode:
#   docker-compose up prod
# =============================================================================
