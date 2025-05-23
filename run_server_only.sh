#!/bin/bash
set -e

if ! command -v pip &>/dev/null; then
  echo "[ERR] pip не найден. Установите Python и pip!"; exit 1
fi
pip install -r requirements.txt
cd central_server
nohup uvicorn server:app --host 0.0.0.0 --port 8000 --reload > ../server.log 2>&1 &
SERVER_PID=$!
cd ..
sleep 2
echo "[OK] Сервер (PID $SERVER_PID) запущен. Web: http://localhost:8000"
echo "Остановить: kill $SERVER_PID" 