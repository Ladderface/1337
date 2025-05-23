#!/bin/bash
set -e

# 1. Проверка и установка зависимостей
if ! command -v pip &>/dev/null; then
  echo "[ERR] pip не найден. Установите Python и pip!"; exit 1
fi
pip install -r requirements.txt

# 2. Запуск сервера
cd central_server
nohup uvicorn server:app --host 0.0.0.0 --port 8000 --reload > ../server.log 2>&1 &
SERVER_PID=$!
cd ..

# 3. Запуск агента
nohup python agent/agent.py > agent.log 2>&1 &
AGENT_PID=$!

# 4. Статус
sleep 2
echo "[OK] Сервер (PID $SERVER_PID) и агент (PID $AGENT_PID) запущены."
echo "Web-интерфейс: http://localhost:8000"
echo "Остановить: kill $SERVER_PID $AGENT_PID" 