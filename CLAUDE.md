# CLAUDE.md — Teramot Dashboard Deploy

## Qué hace este proyecto

Este repo es el sistema de deploy de dashboards de Teramot.

El flujo completo es:
1. En claude.ai (con MCP Teramot), el usuario construye una gold table en Athena
2. Claude genera un dashboard en HTML con los datos de esa tabla
3. El usuario dice "deployalo" — Claude llama al MCP local de deploy
4. El MCP sube el HTML y la configuración a este repo
5. GitHub Actions regenera el dashboard diariamente con datos frescos de Athena
6. GitHub Pages sirve el HTML en una URL pública

## Estructura del repo

```
teramot-dashboards/
├── CLAUDE.md                          ← este archivo
├── dashboards/
│   └── [nombre-dashboard]/
│       ├── index.html                 ← HTML generado por Claude (template)
│       ├── refresh.py                 ← script que regenera el HTML desde Athena
│       └── config.json                ← metadata del dashboard
├── scripts/
│   ├── deploy_mcp.py                  ← servidor MCP local
│   └── run_all_refreshes.py           ← script que GitHub Actions ejecuta
└── .github/
    └── workflows/
        └── daily-refresh.yml          ← cron job diario
```

## Formato de config.json

Cada dashboard tiene un config.json:

```json
{
  "nombre": "farmacia-ventas",
  "cliente": "Farmacia Demo",
  "gold_table": "gold_ventas_region_farmacia",
  "athena_database": "teramot_gold",
  "athena_output": "s3://teramot-athena-results/dashboards/",
  "refresh_hour_utc": 10,
  "creado": "2026-04-08"
}
```

## Formato de refresh.py

Cada dashboard tiene su propio refresh.py. Este script:
1. Consulta Athena usando config.json
2. Toma el index.html como template
3. Reemplaza el bloque de datos hardcodeados con datos frescos
4. Guarda el index.html actualizado

El bloque de datos en el HTML siempre está delimitado así:

```html
<!-- TERAMOT_DATA_START -->
<script>
const DASHBOARD_DATA = { /* datos hardcodeados */ };
</script>
<!-- TERAMOT_DATA_END -->
```

refresh.py reemplaza todo lo que está entre esos comentarios.

## El MCP local (scripts/deploy_mcp.py)

Servidor MCP que corre en la máquina del usuario y expone dos tools:

### Tool: deploy_dashboard

Parámetros:
- `html` (string): el HTML completo generado por Claude
- `gold_table` (string): nombre de la tabla gold en Athena
- `nombre` (string): identificador del dashboard (slug, sin espacios)
- `cliente` (string): nombre legible del cliente
- `athena_database` (string): nombre de la base en Athena (default: "teramot_gold")

Qué hace:
1. Valida que el HTML tenga los delimitadores TERAMOT_DATA_START/END
2. Genera el refresh.py para esa gold table
3. Genera el config.json
4. Escribe los archivos al repo local
5. Hace git add, commit, push
6. Devuelve la URL pública del dashboard

### Tool: list_dashboards

Devuelve la lista de dashboards deployados con sus URLs y última actualización.

## Convenciones importantes

### El HTML que genera Claude DEBE tener los delimitadores de datos

Siempre pedirle a Claude que envuelva el bloque de datos JavaScript así:

```html
<!-- TERAMOT_DATA_START -->
<script>
const DASHBOARD_DATA = {
  ventas: [...],
  fechaActualizacion: "2026-04-08"
};
</script>
<!-- TERAMOT_DATA_END -->
```

Sin esos delimitadores, el refresh.py no puede actualizar los datos.

### Nombres de dashboards
- Usar slugs en minúsculas con guiones: `farmacia-ventas`, `cocacola-distribuidores`
- Sin espacios, sin caracteres especiales
- Deben ser únicos en el repo

### Gold tables
- Las gold tables viven en Athena, generadas por Teramot
- Nomenclatura: `gold_[métrica]_[cliente]` (ej: `gold_ventas_region_farmacia`)
- El refresh.py hace `SELECT * FROM [gold_table]` por defecto
- Si necesitás una query más específica, editá el refresh.py manualmente

## Cómo agregar un nuevo dashboard (flujo completo)

1. En claude.ai con MCP Teramot:
   - Construir la gold table
   - Generar el HTML del dashboard
   - Verificar que tenga los delimitadores TERAMOT_DATA_START/END
   - Decir: "deployalo como [nombre]"

2. El MCP local hace el deploy automáticamente

3. Verificar en: `https://saltateramot.github.io/teramot-dashboards/dashboards/[nombre]/`

## GitHub Actions — daily-refresh.yml

El workflow:
- Se ejecuta todos los días a las 10am UTC (7am Argentina)
- También se puede disparar manualmente desde GitHub Actions
- Corre `scripts/run_all_refreshes.py` que itera sobre todos los dashboards
- Si un refresh falla, continúa con los demás y reporta errores al final
- Hace commit y push solo si hubo cambios en algún HTML

## Variables de entorno requeridas

En GitHub Secrets:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION`

En el MCP local (archivo .env en la raíz del repo):
- `GITHUB_REPO_PATH`: ruta local al repo clonado
- `GITHUB_PAGES_URL`: https://saltateramot.github.io/teramot-dashboards
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION`
- `ATHENA_OUTPUT_BUCKET`: bucket S3 para resultados de Athena

## Qué construir (instrucciones para Claude Code)

Construir los siguientes archivos desde cero:

### 1. scripts/deploy_mcp.py
Servidor MCP local usando la librería `mcp` de Python.
- Instalar con: `pip install mcp`
- Exponer los tools `deploy_dashboard` y `list_dashboards`
- Leer variables de entorno desde `.env` usando `python-dotenv`
- Usar `subprocess` para git add, commit, push
- Devolver la URL pública armada con `GITHUB_PAGES_URL`

### 2. scripts/run_all_refreshes.py
Script que GitHub Actions ejecuta diariamente.
- Iterar sobre todas las carpetas en `dashboards/`
- Por cada una, leer `config.json` y ejecutar `refresh.py`
- Capturar errores por dashboard sin detener el proceso
- Imprimir resumen al final: cuántos OK, cuántos fallaron

### 3. .github/workflows/daily-refresh.yml
GitHub Actions workflow:
- Trigger: schedule cron `0 10 * * *` + workflow_dispatch (manual)
- Steps: checkout, setup Python, install boto3, run run_all_refreshes.py, git commit y push si hay cambios
- Usar secrets: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION

### 4. dashboards/ejemplo/
Crear un dashboard de ejemplo con datos hardcodeados para verificar que el sistema funciona:
- `index.html`: dashboard HTML simple con Chart.js y los delimitadores TERAMOT_DATA_START/END
- `config.json`: config de ejemplo
- `refresh.py`: script de refresh que consulta Athena y regenera el HTML

### 5. .env.example
Archivo de ejemplo con todas las variables de entorno necesarias (sin valores reales).

## Troubleshooting

**El refresh falló en GitHub Actions**
→ Ver logs en Actions → buscar el run del día → identificar qué dashboard falló
→ Causa más común: la gold table no se actualizó en Athena ese día

**El HTML no se actualiza después del push**
→ GitHub Pages puede tardar 1-2 minutos en reflejar cambios
→ Hacer hard refresh en el browser (Ctrl+Shift+R)

**El MCP local no responde**
→ Verificar que deploy_mcp.py esté corriendo en background
→ Verificar que esté registrado correctamente en claude.ai Settings → MCP Servers

**Los datos del dashboard no coinciden con Athena**
→ Verificar que el nombre de la gold table en config.json sea correcto
→ Correr refresh.py manualmente: `python dashboards/[nombre]/refresh.py`
