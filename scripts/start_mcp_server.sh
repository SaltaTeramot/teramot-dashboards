#!/bin/bash
# Arranca el MCP server HTTP/SSE y expone el tunnel con ngrok.
# Uso: ./scripts/start_mcp_server.sh
#
# El .env es cargado por Python (python-dotenv), no por bash,
# para evitar problemas con espacios en las rutas.

set -e

PYTHON=/usr/local/bin/python3.11
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Leer MCP_PORT del .env usando Python (maneja espacios correctamente)
PORT=$($PYTHON - <<EOF
from pathlib import Path
try:
    from dotenv import dotenv_values
    v = dotenv_values(Path("$REPO_DIR") / ".env")
    print(v.get("MCP_PORT", "8080"))
except Exception:
    print("8080")
EOF
)

# Verificar que ngrok esté instalado
if ! command -v ngrok &>/dev/null; then
  echo "ERROR: ngrok no está instalado."
  echo "Instalalo con: brew install ngrok/ngrok/ngrok"
  echo "Luego autenticáte: ngrok config add-authtoken <tu-token>"
  exit 1
fi

# Verificar que uvicorn esté instalado
if ! $PYTHON -c "import uvicorn" &>/dev/null; then
  echo "ERROR: uvicorn no está instalado para $PYTHON."
  echo "Instalalo con: $PYTHON -m pip install uvicorn"
  exit 1
fi

echo "========================================"
echo " Teramot MCP Server"
echo "========================================"
echo " Python:        $PYTHON"
echo " Puerto local:  $PORT"
echo " Endpoint MCP:  http://localhost:$PORT/mcp"
echo "========================================"
echo ""

# Arrancar el MCP server en background
# Python carga el .env internamente con python-dotenv
echo "[1/2] Iniciando MCP server..."
$PYTHON "$SCRIPT_DIR/deploy_mcp.py" --http &
MCP_PID=$!

# Esperar a que levante
sleep 2

# Verificar que levantó correctamente
if ! kill -0 "$MCP_PID" 2>/dev/null; then
  echo "ERROR: El MCP server no pudo arrancar. Revisá los logs."
  exit 1
fi

echo "      MCP server corriendo (PID $MCP_PID)"
echo ""

# Trap para limpiar todo al salir
trap "echo ''; echo 'Deteniendo MCP server...'; kill $MCP_PID 2>/dev/null; exit 0" INT TERM

# Arrancar ngrok en background
echo "[2/2] Iniciando ngrok tunnel en puerto $PORT..."
ngrok http "$PORT" --log=stdout --log-format=json &
NGROK_PID=$!

# Esperar a que ngrok exponga la URL (consulta la API local de ngrok)
echo "      Esperando URL pública de ngrok..."
NGROK_URL=""
for i in $(seq 1 15); do
  sleep 1
  NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null \
    | $PYTHON -c "import sys,json; t=json.load(sys.stdin).get('tunnels',[]); print(next((x['public_url'] for x in t if x['proto']=='https'),''))" 2>/dev/null || true)
  if [ -n "$NGROK_URL" ]; then
    break
  fi
done

if [ -n "$NGROK_URL" ]; then
  echo ""
  echo "========================================"
  echo " URL pública lista:"
  echo " $NGROK_URL/mcp"
  echo ""
  echo " Registrá esta URL en claude.ai:"
  echo " Settings → Connectors → nuevo MCP"
  echo "========================================"
else
  echo "      (No se pudo obtener la URL automáticamente — revisá la terminal de ngrok)"
fi

echo ""
echo "Para detener todo: Ctrl+C"

# Esperar a que ngrok termine
wait $NGROK_PID

# Si ngrok termina, matar el MCP server también
kill "$MCP_PID" 2>/dev/null
