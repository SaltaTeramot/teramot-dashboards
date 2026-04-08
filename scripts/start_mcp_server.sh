#!/bin/bash
# Arranca el MCP server HTTP/SSE y expone el tunnel con ngrok.
# Uso: ./scripts/start_mcp_server.sh

set -e

PYTHON=/usr/local/bin/python3.11
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Cargar .env si existe
if [ -f "$REPO_DIR/.env" ]; then
  set -a
  source "$REPO_DIR/.env"
  set +a
fi

PORT="${MCP_PORT:-8080}"

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
echo " Endpoint SSE:  http://localhost:$PORT/sse"
echo "========================================"
echo ""

# Arrancar el MCP server en background
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

# Trap para limpiar el MCP server al salir
trap "echo ''; echo 'Deteniendo MCP server...'; kill $MCP_PID 2>/dev/null; exit 0" INT TERM

# Arrancar ngrok y capturar la URL pública
echo "[2/2] Iniciando ngrok tunnel en puerto $PORT..."
ngrok http $PORT --log=stdout --log-format=json &
NGROK_PID=$!

# Esperar a que ngrok exponga la URL
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
  echo " $NGROK_URL/sse"
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
