import os
import sys
import subprocess
import time
import shutil

REQUIRED_PY = (3, 8)
REQUIRED_PKGS = [
    'uvicorn', 'fastapi', 'pydantic', 'requests', 'gspread', 'openpyxl', 'pyyaml', 'jinja2', 'sqlite3'
]

print('[CHECK] Python version:', sys.version)
if sys.version_info < REQUIRED_PY:
    print(f'[ERR] Требуется Python {REQUIRED_PY[0]}.{REQUIRED_PY[1]}+')
    sys.exit(1)

if shutil.which('pip') is None:
    print('[ERR] pip не найден!')
    sys.exit(1)

print('[CHECK] pip found')

print('[CHECK] pip install -r requirements.txt')
subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])

for pkg in REQUIRED_PKGS:
    try:
        __import__(pkg)
    except ImportError:
        print(f'[SETUP] pip install {pkg}')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg])

print('[OK] Все зависимости установлены.')

# Запуск сервера и агента в отдельных окнах/процессах
if os.name == 'nt':
    # Windows: start в новых окнах
    subprocess.Popen(['start', 'cmd', '/k', 'cd central_server && uvicorn server:app --reload'], shell=True)
    subprocess.Popen(['start', 'cmd', '/k', 'cd agent && python agent.py'], shell=True)
else:
    # Unix: nohup &
    subprocess.Popen('cd central_server && nohup uvicorn server:app --host 0.0.0.0 --port 8000 --reload > ../server.log 2>&1 &', shell=True)
    subprocess.Popen('nohup python agent/agent.py > agent.log 2>&1 &', shell=True)

print('[OK] Сервер и агент запущены.')
print('Web-интерфейс: http://localhost:8000')
print('Для остановки используйте kill или закройте окна.') 