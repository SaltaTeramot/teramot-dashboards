#!/usr/bin/env python3
"""
MCP local para deploy de dashboards Teramot.
Expone: deploy_dashboard, list_dashboards
"""

import json
import os
import subprocess
import textwrap
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

load_dotenv(Path(__file__).parent.parent / ".env")

REPO_PATH = Path(os.environ["GITHUB_REPO_PATH"])
PAGES_URL = os.environ["GITHUB_PAGES_URL"].rstrip("/")
DASHBOARDS_DIR = REPO_PATH / "dashboards"

app = Server("teramot-deploy")


def _generate_refresh_py(gold_table: str, athena_database: str, athena_output: str) -> str:
    return textwrap.dedent(f'''\
        #!/usr/bin/env python3
        """
        Regenera index.html con datos frescos desde Athena.
        Generado automáticamente por deploy_mcp.py
        """

        import json
        import os
        import re
        import time
        from pathlib import Path

        import boto3

        CONFIG_PATH = Path(__file__).parent / "config.json"
        HTML_PATH = Path(__file__).parent / "index.html"

        DATA_START = "<!-- TERAMOT_DATA_START -->"
        DATA_END = "<!-- TERAMOT_DATA_END -->"


        def run_query(client, query, database, output):
            response = client.start_query_execution(
                QueryString=query,
                QueryExecutionContext={{"Database": database}},
                ResultConfiguration={{"OutputLocation": output}},
            )
            execution_id = response["QueryExecutionId"]
            while True:
                status = client.get_query_execution(QueryExecutionId=execution_id)
                state = status["QueryExecution"]["Status"]["State"]
                if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                    break
                time.sleep(2)
            if state != "SUCCEEDED":
                raise RuntimeError(f"Query {{state}}: {{execution_id}}")
            return execution_id


        def fetch_results(client, execution_id):
            paginator = client.get_paginator("get_query_results")
            rows = []
            columns = None
            for page in paginator.paginate(QueryExecutionId=execution_id):
                result_rows = page["ResultSet"]["Rows"]
                if columns is None:
                    columns = [c["VarCharValue"] for c in result_rows[0]["Data"]]
                    result_rows = result_rows[1:]
                for row in result_rows:
                    values = [c.get("VarCharValue", "") for c in row["Data"]]
                    rows.append(dict(zip(columns, values)))
            return rows


        def main():
            with open(CONFIG_PATH) as f:
                config = json.load(f)

            client = boto3.client("athena", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

            query = f"SELECT * FROM {{config[\'gold_table\']}}"
            execution_id = run_query(
                client, query, config["athena_database"], config["athena_output"]
            )
            rows = fetch_results(client, execution_id)

            today = date.today().isoformat() if False else __import__("datetime").date.today().isoformat()
            data_block = (
                DATA_START + "\\n"
                "<script>\\n"
                "const DASHBOARD_DATA = " + json.dumps({{"rows": rows, "fechaActualizacion": today}}, ensure_ascii=False, indent=2) + ";\\n"
                "</script>\\n"
                + DATA_END
            )

            html = HTML_PATH.read_text(encoding="utf-8")
            pattern = re.compile(
                re.escape(DATA_START) + r".*?" + re.escape(DATA_END),
                re.DOTALL,
            )
            if not pattern.search(html):
                raise ValueError("No se encontraron los delimitadores TERAMOT_DATA_START/END en index.html")

            new_html = pattern.sub(data_block, html)
            HTML_PATH.write_text(new_html, encoding="utf-8")
            print(f"OK: {{len(rows)}} filas actualizadas en index.html")


        if __name__ == "__main__":
            main()
    ''')


def _generate_config_json(nombre: str, cliente: str, gold_table: str,
                           athena_database: str) -> dict:
    return {
        "nombre": nombre,
        "cliente": cliente,
        "gold_table": gold_table,
        "athena_database": athena_database,
        "athena_output": f"s3://{os.environ.get('ATHENA_OUTPUT_BUCKET', 'teramot-athena-results')}/dashboards/",
        "refresh_hour_utc": 10,
        "creado": date.today().isoformat(),
    }


def _git_push(message: str):
    def run(cmd):
        result = subprocess.run(cmd, cwd=REPO_PATH, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"git error: {result.stderr.strip()}")
        return result.stdout.strip()

    run(["git", "add", "-A"])
    run(["git", "commit", "-m", message])
    run(["git", "push"])


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="deploy_dashboard",
            description="Sube un dashboard HTML al repo y hace push para publicarlo en GitHub Pages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "html": {"type": "string", "description": "HTML completo del dashboard"},
                    "gold_table": {"type": "string", "description": "Nombre de la tabla gold en Athena"},
                    "nombre": {"type": "string", "description": "Slug del dashboard (minúsculas, guiones)"},
                    "cliente": {"type": "string", "description": "Nombre legible del cliente"},
                    "athena_database": {
                        "type": "string",
                        "description": "Base de datos en Athena",
                        "default": "teramot_gold",
                    },
                },
                "required": ["html", "gold_table", "nombre", "cliente"],
            },
        ),
        Tool(
            name="list_dashboards",
            description="Lista los dashboards deployados con sus URLs y última actualización.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "deploy_dashboard":
        html: str = arguments["html"]
        gold_table: str = arguments["gold_table"]
        nombre: str = arguments["nombre"]
        cliente: str = arguments["cliente"]
        athena_database: str = arguments.get("athena_database", "teramot_gold")

        if "<!-- TERAMOT_DATA_START -->" not in html or "<!-- TERAMOT_DATA_END -->" not in html:
            return [TextContent(type="text", text="ERROR: El HTML no contiene los delimitadores TERAMOT_DATA_START/END.")]

        dash_dir = DASHBOARDS_DIR / nombre
        dash_dir.mkdir(parents=True, exist_ok=True)

        (dash_dir / "index.html").write_text(html, encoding="utf-8")

        config = _generate_config_json(nombre, cliente, gold_table, athena_database)
        (dash_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

        athena_output = config["athena_output"]
        (dash_dir / "refresh.py").write_text(
            _generate_refresh_py(gold_table, athena_database, athena_output), encoding="utf-8"
        )

        try:
            _git_push(f"deploy: {nombre} ({cliente})")
        except RuntimeError as e:
            return [TextContent(type="text", text=f"ERROR en git push: {e}")]

        url = f"{PAGES_URL}/dashboards/{nombre}/"
        return [TextContent(type="text", text=f"Dashboard deployado exitosamente.\nURL: {url}")]

    elif name == "list_dashboards":
        if not DASHBOARDS_DIR.exists():
            return [TextContent(type="text", text="No hay dashboards deployados todavía.")]

        lines = []
        for dash_dir in sorted(DASHBOARDS_DIR.iterdir()):
            config_path = dash_dir / "config.json"
            if not config_path.exists():
                continue
            with open(config_path) as f:
                config = json.load(f)
            url = f"{PAGES_URL}/dashboards/{dash_dir.name}/"
            lines.append(f"- **{config['nombre']}** ({config['cliente']})\n  URL: {url}\n  Creado: {config['creado']}")

        if not lines:
            return [TextContent(type="text", text="No hay dashboards deployados todavía.")]

        return [TextContent(type="text", text="\n\n".join(lines))]

    return [TextContent(type="text", text=f"Tool desconocida: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
