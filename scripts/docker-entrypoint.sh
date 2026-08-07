#!/bin/bash
# LIBeSocial Premium - Docker Entrypoint Script
# ==============================================
# Funções: Setup inicial, health checks, execução de comandos

set -e

echo "🚀 LIBeSocial Premium v2.0.0 - Starting..."

# Verificar variáveis de ambiente críticas
if [ "$ESOCIAL_ENV" = "production" ] && [ -z "$ESOCIAL_CNPJ" ]; then
    echo "⚠️  Warning: ESOCIAL_CNPJ not set in production mode"
fi

# Aguardar Redis estar disponível (se configurado)
if [ -n "$ESOCIAL_REDIS_URL" ]; then
    echo "⏳ Waiting for Redis..."
    REDIS_HOST=$(echo $ESOCIAL_REDIS_URL | sed -E 's|redis://([^:]+):.*|\1|')
    REDIS_PORT=$(echo $ESOCIAL_REDIS_URL | sed -E 's|redis://[^:]+:([0-9]+).*|\1|')
    
    max_attempts=30
    attempt=1
    while ! nc -z $REDIS_HOST $REDIS_PORT 2>/dev/null; do
        if [ $attempt -ge $max_attempts ]; then
            echo "❌ Redis not available after $max_attempts attempts"
            exit 1
        fi
        echo "   Attempt $attempt/$max_attempts - Redis not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done
    echo "✅ Redis is available"
fi

# Verificar certificados (se caminho configurado)
if [ -n "$ESOCIAL_CERT_PATH" ] && [ -d "$ESOCIAL_CERT_PATH" ]; then
    cert_count=$(find "$ESOCIAL_CERT_PATH" -name "*.pem" -o -name "*.pfx" -o -name "*.p12" 2>/dev/null | wc -l)
    if [ $cert_count -gt 0 ]; then
        echo "✅ Found $cert_count certificate(s) in $ESOCIAL_CERT_PATH"
    else
        echo "⚠️  No certificates found in $ESOCIAL_CERT_PATH"
    fi
fi

# Executar comando principal
echo "📋 Executing: $@"
exec "$@"
