#!/usr/bin/env python3
"""
Itera sobre todos los dashboards y ejecuta su refresh.py.
Usado por GitHub Actions en el cron diario.
"""

import json
import subprocess
import sys
from pathlib import Path

DASHBOARDS_DIR = Path(__file__).parent.parent / "dashboards"


def main():
    if not DASHBOARDS_DIR.exists():
        print("No hay dashboards todavía.")
        sys.exit(0)

    dashboards = sorted(
        d for d in DASHBOARDS_DIR.iterdir()
        if d.is_dir() and (d / "refresh.py").exists() and (d / "config.json").exists()
    )

    if not dashboards:
        print("No hay dashboards con refresh.py.")
        sys.exit(0)

    ok = []
    failed = []

    for dash_dir in dashboards:
        with open(dash_dir / "config.json") as f:
            config = json.load(f)
        nombre = config.get("nombre", dash_dir.name)
        print(f"\n[{nombre}] Ejecutando refresh...")

        result = subprocess.run(
            [sys.executable, str(dash_dir / "refresh.py")],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print(f"[{nombre}] OK")
            if result.stdout:
                print(result.stdout.strip())
            ok.append(nombre)
        else:
            print(f"[{nombre}] FALLO")
            if result.stdout:
                print(result.stdout.strip())
            if result.stderr:
                print(result.stderr.strip())
            failed.append(nombre)

    print("\n" + "=" * 50)
    print(f"Resultado: {len(ok)} OK, {len(failed)} fallaron")
    if ok:
        print(f"  OK: {', '.join(ok)}")
    if failed:
        print(f"  Fallaron: {', '.join(failed)}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
