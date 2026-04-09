# teramot-dashboards

Sistema de deploy de dashboards generados por IA a partir de gold tables en AWS Athena, servidos via GitHub Pages con refresh automático diario.

## Cómo funciona

1. En claude.ai (con MCP Teramot), construís una gold table y generás un dashboard HTML
2. Decís "deployalo" → el MCP local sube los archivos a este repo
3. GitHub Actions refresca los datos todos los días a las 10am UTC
4. El dashboard queda disponible en `https://saltateramot.github.io/teramot-dashboards/dashboards/[nombre]/`

## Requisitos

- Python 3.9+
- AWS credentials con acceso a Athena y S3
- Git configurado localmente
- Cuenta en GitHub con GitHub Pages habilitado en este repo

## Instalación

```bash
git clone https://github.com/SaltaTeramot/teramot-dashboards.git
cd teramot-dashboards
pip install mcp boto3 python-dotenv
cp .env.example .env
# Editar .env con tus credenciales
```

## Variables de entorno

Ver `.env.example`. Las más importantes:

| Variable | Descripción |
|---|---|
| `AWS_ACCESS_KEY_ID` | Credencial AWS |
| `AWS_SECRET_ACCESS_KEY` | Credencial AWS |
| `ATHENA_OUTPUT_BUCKET` | Bucket S3 para resultados de Athena |
| `GITHUB_REPO_PATH` | Ruta local al repo clonado |
| `GITHUB_PAGES_URL` | URL base de GitHub Pages |

En GitHub Actions, estas variables van como **Secrets** (Settings → Secrets → Actions).

## Correr el MCP local

```bash
python scripts/deploy_mcp.py
```

Registrar en claude.ai como MCP server (Settings → MCP Servers).

## Deploy de un dashboard

Desde claude.ai con el MCP activo:

```
Deployalo como [nombre-del-dashboard]
```

El MCP hace el commit y push automáticamente. El dashboard queda disponible en ~2 minutos.

## Refresh manual

```bash
python dashboards/[nombre]/refresh.py
```

## Estructura

```
dashboards/
  [nombre]/
    index.html      ← template HTML generado por Claude
    refresh.py      ← actualiza los datos desde Athena
    config.json     ← metadata (tabla, base, horario)
scripts/
  deploy_mcp.py         ← servidor MCP local
  run_all_refreshes.py  ← corre todos los refreshes (usado por CI)
.github/workflows/
  daily-refresh.yml     ← cron job diario
```

## Troubleshooting

**Refresh falló en Actions** → Ver logs en Actions → identificar el dashboard → causa más común: la gold table no se actualizó ese día en Athena.

**HTML no se actualiza tras el push** → GitHub Pages puede tardar 1-2 minutos. Hacer hard refresh (Ctrl+Shift+R).

**MCP local no responde** → Verificar que `deploy_mcp.py` esté corriendo y registrado en claude.ai.
