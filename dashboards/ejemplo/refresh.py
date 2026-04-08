#!/usr/bin/env python3
"""
Regenera index.html con datos frescos desde Athena.
Dashboard: ejemplo
"""

import json
import os
import re
import time
from datetime import date
from pathlib import Path

import boto3

CONFIG_PATH = Path(__file__).parent / "config.json"
HTML_PATH = Path(__file__).parent / "index.html"

DATA_START = "<!-- TERAMOT_DATA_START -->"
DATA_END = "<!-- TERAMOT_DATA_END -->"


def run_query(client, query, database, output):
    response = client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": output},
    )
    execution_id = response["QueryExecutionId"]
    while True:
        status = client.get_query_execution(QueryExecutionId=execution_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
    if state != "SUCCEEDED":
        raise RuntimeError(f"Query {state}: {execution_id}")
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

    query = f"SELECT * FROM {config['gold_table']}"
    execution_id = run_query(client, query, config["athena_database"], config["athena_output"])
    rows = fetch_results(client, execution_id)

    today = date.today().isoformat()
    data_block = (
        DATA_START + "\n"
        "<script>\n"
        "const DASHBOARD_DATA = "
        + json.dumps({"rows": rows, "fechaActualizacion": today}, ensure_ascii=False, indent=2)
        + ";\n"
        "</script>\n"
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
    print(f"OK: {len(rows)} filas actualizadas en index.html")


if __name__ == "__main__":
    main()
