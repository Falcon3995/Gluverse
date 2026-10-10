#!/bin/sh
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$ROOT_DIR/backend/.venv" ]; then
  echo "Creating backend virtual environment..."
  (cd "$ROOT_DIR/backend" && python3 -m venv .venv)
fi

if ! "$ROOT_DIR/backend/.venv/bin/python" -c "import flask, sqlalchemy, bcrypt" >/dev/null 2>&1; then
  echo "Installing backend dependencies..."
  (cd "$ROOT_DIR/backend" && . .venv/bin/activate && python -m pip install -r requirements.txt)
fi

echo "Starting GluVerse..."
BACKEND_PORT="${BACKEND_PORT:-5000}"
while python3 -c "import socket; s=socket.socket(); raise SystemExit(0 if s.connect_ex(('127.0.0.1', int('$BACKEND_PORT'))) == 0 else 1)"; do
  BACKEND_PORT=$((BACKEND_PORT + 1))
done
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
while python3 -c "import socket; s=socket.socket(); raise SystemExit(0 if s.connect_ex(('127.0.0.1', int('$FRONTEND_PORT'))) == 0 else 1)"; do
  FRONTEND_PORT=$((FRONTEND_PORT + 1))
done

echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Frontend: http://localhost:$FRONTEND_PORT"

(
  cd "$ROOT_DIR/backend"
  . .venv/bin/activate
  PORT="$BACKEND_PORT" python app.py
) &
BACKEND_PID=$!

(
  cd "$ROOT_DIR/frontend"
  if [ ! -d node_modules ]; then
    npm install
  fi
  PORT="$FRONTEND_PORT" REACT_APP_API_BASE_URL="http://127.0.0.1:$BACKEND_PORT" npm start
) &
FRONTEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

wait "$BACKEND_PID" "$FRONTEND_PID"
