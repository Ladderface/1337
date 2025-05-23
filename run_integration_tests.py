import requests
import sys
import subprocess
import time

def wait_server_ready(url, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=1)
            if r.status_code == 200:
                return True
        except Exception:
            time.sleep(0.5)
    return False

if __name__ == '__main__':
    print('[CHECK] Проверяю доступность сервера http://127.0.0.1:8000/')
    if not wait_server_ready('http://127.0.0.1:8000/'):
        print('[ERR] Сервер не запущен! Запустите сервер (run_full_stack.sh, run_everything_win.bat или python run_check_and_setup.py)')
        sys.exit(1)
    print('[OK] Сервер доступен. Запускаю интеграционные тесты...')
    code = subprocess.call([sys.executable, '-m', 'unittest', 'tests/test_device_session.py'], cwd='agent')
    if code == 0:
        print('[OK] Все интеграционные тесты пройдены.')
    else:
        print('[ERR] Некоторые тесты не прошли. См. вывод выше.')
    sys.exit(code) 