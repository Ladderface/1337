#!/bin/bash
set -e

if ! command -v pip &>/dev/null; then
  echo "[ERR] pip не найден. Установите Python и pip!"; exit 1
fi
pip install -r requirements.txt
nohup python agent/agent.py > agent.log 2>&1 &
AGENT_PID=$!
sleep 2
echo "[OK] Агент (PID $AGENT_PID) запущен."
echo "Остановить: kill $AGENT_PID" 