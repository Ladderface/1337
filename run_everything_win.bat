@echo off
setlocal
where python >nul 2>nul || (echo [ERR] Python не найден! & exit /b 1)
where pip >nul 2>nul || (echo [ERR] pip не найден! & exit /b 1)

pip install -r requirements.txt
start "ADB Central Server" cmd /k "cd central_server && uvicorn server:app --reload"
start "ADB Agent" cmd /k "cd agent && python agent.py"
echo [OK] Сервер и агент запущены в отдельных окнах.
echo Web-интерфейс: http://localhost:8000
pause 