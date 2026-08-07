# 🚀 LIBeSocial Premium - Guia de Release e Deploy

## Visão Geral

Este documento descreve o processo completo de release e deploy do LIBeSocial Premium Enterprise v2.0.0.

## 📋 Pré-requisitos

### Secrets Necessários (GitHub)

Configure os seguintes secrets no repositório GitHub:

1. **PYPI_API_TOKEN** - Token para publicação no PyPI
   - Acesse: https://pypi.org/manage/account/token/
   - Configure em: Settings → Secrets → Actions

2. **GITHUB_TOKEN** - Automático (já configurado pelo GitHub)

3. **Ambiente Production** (opcional)
   - Configure em: Settings → Environments → production
   - Adicione reviewers/approvals se necessário

## 🔖 Criando um Release

### Método 1: Workflow Automatizado (Recomendado)

1. Acesse: **Actions → Release Automation → Run workflow**

2. Preencha os parâmetros:
   - **version_type**: Escolha entre `patch`, `minor`, ou `major`
     - `patch`: Correções de bugs (1.0.0 → 1.0.1)
     - `minor`: Novas features backward-compatible (1.0.0 → 1.1.0)
     - `major`: Mudanças breaking (1.0.0 → 2.0.0)
   - **changelog**: Descrição opcional das mudanças

3. Execute o workflow

4. O workflow irá automaticamente:
   - ✅ Bump da versão no `pyproject.toml`
   - ✅ Commit e push da mudança
   - ✅ Criação de tag Git (`vX.Y.Z`)
   - ✅ Geração de changelog automático
   - ✅ Criação de draft release no GitHub
   - ✅ Build e push da Docker image
   - ✅ Publicação no PyPI

### Método 2: Manual (Sempre funciona)

```bash
# 1. Atualizar versão
poetry version patch  # ou minor, major

# 2. Commit das mudanças
git add pyproject.toml
git commit -m "chore: bump version to $(poetry version -s)"

# 3. Criar tag
git tag -a "v$(poetry version -s)" -m "Release v$(poetry version -s)"

# 4. Push
git push origin main
git push origin v$(poetry version -s)

# 5. Build e publish
poetry build
poetry publish

# 6. Docker build e push
docker build -t libesocial/premium:$(poetry version -s) --target production .
docker push libesocial/premium:$(poetry version -s)
```

## 🐳 Docker Images

### Tags Disponíveis

- `latest` - Última versão estável (main branch)
- `X.Y.Z` - Versão específica (ex: `2.0.0`)
- `X.Y` - Última patch da versão minor (ex: `2.0`)

### Pull da Imagem

```bash
# Produção
docker pull ghcr.io/libesocial/libesocial-python:latest

# Versão específica
docker pull ghcr.io/libesocial/libesocial-python:2.0.0
```

### Uso com Docker Compose

```bash
# Development
docker-compose --profile development up dev redis

# Testes
docker-compose --profile testing up test

# Produção
docker-compose --profile production up prod redis

# CLI commands
docker-compose --profile cli run cli validate events/meu_evento.xml
docker-compose --profile cli run cli submit events/meu_evento.xml
docker-compose --profile cli run cli status ENVIO_123
docker-compose --profile cli run cli audit --event-type S-1000
docker-compose --profile cli run cli health
```

## 📦 PyPI Package

### Instalação

```bash
pip install libesocial-premium==2.0.0
```

### Uso como Biblioteca

```python
from esocial import PremiumClient, Config

config = Config(
    cnpj="00.000.000/0001-00",
    cert_path="/path/to/cert.pem",
    env="production"
)

client = PremiumClient(config)
```

## 🎯 CI/CD Pipeline

### Jobs Executados

1. **Quality Checks**
   - flake8 (linting)
   - mypy (type checking)
   - black (formatting check)
   - isort (imports check)

2. **Tests & Coverage**
   - pytest com coverage
   - Upload para Codecov
   - Threshold mínimo: 90%

3. **Security Scan**
   - safety (vulnerabilidades em dependências)
   - bandit (security linting)

4. **Docker Build** (apenas tags)
   - Multi-platform (amd64, arm64)
   - Push para GHCR

5. **Release & Publish** (apenas tags)
   - GitHub Release
   - PyPI publish

6. **Deploy** (opcional)
   - Trigger de deployment em produção

## 📊 Monitoramento do Release

### Status Checks

Acompanhe o status dos workflows em:
- **Actions tab**: https://github.com/libesocial/libesocial-python/actions

### Artefatos Gerados

Cada workflow gera artefatos disponíveis por 90 dias:
- `test-results.xml` - Resultados dos testes JUnit
- `coverage/` - Relatório HTML de coverage
- `security-reports/` - Relatórios de segurança
- `release-notes/` - Changelog gerado

## 🔧 Troubleshooting

### Release falhou no PyPI

```bash
# Verificar token
echo $PYPI_API_TOKEN

# Testar upload manual
poetry config pypi-token.pypi YOUR_TOKEN
poetry publish --dry-run
```

### Docker build falhou

```bash
# Build local para debug
docker build -t libesocial/debug --target production .

# Testar container
docker run --rm libesocial/debug python -c "import esocial; print(esocial.__version__)"
```

### Tests falhando

```bash
# Rodar testes localmente
docker-compose --profile testing up test

# Ou com poetry
poetry run pytest tests/ -v --tb=short
```

## 📝 Versionamento Semântico

Seguimos [Semantic Versioning 2.0.0](https://semver.org/):

- **MAJOR** (X.0.0): Mudanças breaking incompatible
- **MINOR** (1.X.0): Novas features backward-compatible
- **PATCH** (1.0.X): Bug fixes backward-compatible

### Exemplos

- `1.0.0` → Primeira release estável
- `1.0.1` → Hotfix crítico
- `1.1.0` → Nova feature (ex: suporte a S-500X)
- `2.0.0` → Breaking change (ex: migração Pydantic V2)

## 🎉 Pós-Release Checklist

Após cada release, verificar:

- [ ] Release notes revisadas e publicadas
- [ ] Docker image disponível no GHCR
- [ ] Package disponível no PyPI
- [ ] Documentação atualizada
- [ ] Stakeholders notificados
- [ ] Monitoring dashboards atualizados
- [ ] Backup de certificados verificado

## 📞 Suporte

- **Issues**: https://github.com/libesocial/libesocial-python/issues
- **Discussions**: https://github.com/libesocial/libesocial-python/discussions
- **Email**: team@libesocial.com

---

**Última atualização**: Janeiro 2025  
**Versão do documento**: 2.0.0
