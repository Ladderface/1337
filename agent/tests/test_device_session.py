import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys
import os
from subprocess import Popen
PROJECT_ROOT = str(Path(__file__).parent.parent.parent.resolve())
AGENT_DIR = str(Path(__file__).parent.parent.resolve())
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)
from device_session import DeviceSession
import tempfile
import shutil
import requests
import threading
import time
import http.server
import socketserver
import queue
import socket
import yaml
from datetime import datetime

class TestDeviceSession(unittest.TestCase):
    def setUp(self):
        self.device = {'id': 'test_device'}
        self.cfg = {'screenshot_dir': 'test_screenshots'}
        Path('test_screenshots').mkdir(exist_ok=True)
        self.session = DeviceSession(self.device, self.cfg)

    @patch('device_session.subprocess.run')
    def test_take_screenshot_success(self, mock_run):
        # Эмулируем успешное создание файла
        test_file = Path('test_screenshots/test_device_2020-01-01_00-00-00.png')
        test_file.write_bytes(b'\x89PNG\r\n\x1a\n' + b'0' * 2000)
        with patch('device_session.datetime') as mock_dt:
            mock_dt.now.return_value.strftime.return_value = '2020-01-01_00-00-00'
            result = self.session.take_screenshot()
        self.assertTrue(result.endswith('.png'))
        test_file.unlink()

    @patch('device_session.subprocess.run', side_effect=Exception('ADB error'))
    def test_take_screenshot_fail(self, mock_run):
        result = self.session.take_screenshot()
        self.assertIsNone(result)

    def wait_server_ready(self, url, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = requests.get(url, timeout=1)
                if r.status_code == 200:
                    return True
            except Exception as e:
                time.sleep(0.3)
        raise RuntimeError(f"Server not ready at {url}")

    def test_last_png_upload_and_api(self):
        project_root = Path(__file__).parent.parent.parent.resolve()
        server_dir = project_root / 'central_server'
        proc = Popen([
            'uvicorn', 'central_server.server:app', '--host', '127.0.0.1', '--port', '8000', '--log-level', 'info'
        ], cwd=str(project_root))
        try:
            self.wait_server_ready('http://127.0.0.1:8000/')
            # Эмулируем загрузку скриншота
            url = 'http://127.0.0.1:8000/upload_screenshot'
            files = {'image': ('test.png', b'\x89PNG\r\n\x1a\n' + b'0'*2000, 'image/png')}
            data = {
                'server_id': 'test-server',
                'window': 'main',
                'device_id': 'test_device',
                'meta': '{}'
            }
            headers = {'Authorization': 'Bearer testkey'}
            r = requests.post(url, files=files, data=data, headers=headers, timeout=10)
            self.assertTrue(r.ok)
            # Проверяем, что last.png доступен
            url_last = 'http://127.0.0.1:8000/download_last/test-server/main/test_device'
            r2 = requests.get(url_last, timeout=10)
            self.assertEqual(r2.status_code, 200)
            self.assertTrue(r2.content.startswith(b'\x89PNG'))
        finally:
            proc.terminate()
            proc.wait()

    class WebhookHandler(http.server.BaseHTTPRequestHandler):
        received = queue.Queue()
        def do_POST(self):
            length = int(self.headers.get('content-length', 0))
            body = self.rfile.read(length)
            try:
                import json
                payload = json.loads(body)
            except Exception as e:
                payload = None
            TestDeviceSession.WebhookHandler.received.put(payload)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
        def log_message(self, format, *args):
            pass

    @staticmethod
    def start_webhook_server():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        class ReusableTCPServer(socketserver.TCPServer):
            allow_reuse_address = True
        httpd = ReusableTCPServer(('127.0.0.1', port), TestDeviceSession.WebhookHandler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        return httpd, port

    @patch('central_server.integrations.google_sheets.append_to_sheet', return_value=True)
    @patch('central_server.server.send_telegram_alert', return_value=None)
    def test_integration_hooks(self, mock_tg, mock_sheets):
        import tempfile
        import time
        import yaml
        import os
        project_root = Path(__file__).parent.parent.parent.resolve()
        server_dir = project_root / 'central_server'
        with tempfile.NamedTemporaryFile('w+', suffix='.yaml', delete=False) as tmp_cfg:
            try:
                webhook_server, port = TestDeviceSession.start_webhook_server()
                print(f"[TEST] Webhook test server started on port: {port}")
                # Запись валидного config.yaml во временный файл
                webhook_url = f'http://127.0.0.1:{port}/webhook'
                cfg = {
                    'modules': {'webhook': True, 'google_sheets': True, 'telegram': True},
                    'webhook': {'url': webhook_url, 'secret': 'test'},
                    'google_sheets': {'credentials': 'fake.json', 'sheet_id': 'fakeid', 'worksheet': 'Лист1'},
                    'telegram': {'bot_token': 'fake', 'chat_id': 'fake'},
                    'api_keys': ['testkey']
                }
                yaml.safe_dump(cfg, tmp_cfg)
                tmp_cfg.flush()
                config_path = tmp_cfg.name
            finally:
                tmp_cfg.close()
            print(f"[TEST] Using config.yaml: {config_path}")
            print(f"[TEST] Webhook URL in config: {webhook_url}")
            env = os.environ.copy()
            env['CONFIG_YAML'] = config_path
            proc = Popen([
                'uvicorn', 'central_server.server:app', '--host', '127.0.0.1', '--port', '8000', '--log-level', 'info'
            ], cwd=str(project_root), env=env)
            try:
                print(f"[TEST] Waiting for server ready...")
                self.wait_server_ready('http://127.0.0.1:8000/')
                print(f"[TEST] Server ready, sending screenshot and alert...")
                # Эмулируем загрузку скриншота
                url = 'http://127.0.0.1:8000/upload_screenshot'
                files = {'image': ('test.png', b'\x89PNG\r\n\x1a\n' + b'0'*2000, 'image/png')}
                data = {
                    'server_id': 'test-server',
                    'window': 'main',
                    'device_id': 'test_device',
                    'meta': '{}'
                }
                headers = {'Authorization': 'Bearer testkey'}
                r = requests.post(url, files=files, data=data, headers=headers, timeout=10)
                print(f"[TEST] Screenshot upload status: {r.status_code}")
                self.assertTrue(r.ok)
                # Эмулируем отправку лога (alert)
                url_log = 'http://127.0.0.1:8000/api/send_message'
                payload = {
                    'server_id': 'test-server',
                    'device_id': 'test_device',
                    'type': 'alert',
                    'message': 'Test alert'
                }
                r2 = requests.post(url_log, json=payload, headers=headers, timeout=10)
                print(f"[TEST] Alert send status: {r2.status_code}")
                self.assertTrue(r2.ok)
                import time
                print("[TEST] Sleep 3s to allow integration threads to complete...")
                time.sleep(3)
                # Проверяем, что интеграции были вызваны
                got_webhook = False
                bodies = []
                start = time.time()
                print(f"[TEST] Waiting for webhook POST (timeout 30s)...")
                while time.time() - start < 30:
                    try:
                        payload = self.WebhookHandler.received.get(timeout=1)
                        print(f"[TEST] Webhook received payload: {payload}")
                        bodies.append(payload)
                        if payload and payload.get('event') in ('screenshot_uploaded', 'alert'):
                            got_webhook = True
                            break
                    except queue.Empty:
                        pass
                print(f"[TEST] Webhook bodies: {bodies}")
                if not got_webhook:
                    print(f"[TEST] FAIL: Webhook did not receive expected event. All payloads: {bodies}")
                print(f"[TEST] mock_sheets.call_args_list: {mock_sheets.call_args_list}")
                self.assertTrue(got_webhook)
            finally:
                print("[TEST] Terminating server and webhook...")
                proc.terminate()
                proc.wait()
                webhook_server.shutdown()
                print(f"[TEST] Removing config.yaml: {config_path}")
                try:
                    os.unlink(config_path)
                except Exception as e:
                    print(f"[TEST] Could not remove config.yaml: {e}")

    def test_google_sheets_e2e(self):
        """
        E2E тест Google Sheets: если заданы GSHEET_CREDENTIALS и GSHEET_SHEET_ID и файл существует — реально пишет строку в Google Sheets и проверяет результат.
        Иначе — тест пропускается (или мокается).
        """
        creds = os.environ.get('GSHEET_CREDENTIALS')
        sheet_id = os.environ.get('GSHEET_SHEET_ID')
        worksheet = os.environ.get('GSHEET_WORKSHEET', 'Лист1')
        if not creds or not sheet_id or not os.path.exists(creds):
            print('[TEST] Google Sheets e2e: credentials or sheet_id not set, skipping real test.')
            return
        import tempfile
        import yaml
        import gspread
        from datetime import datetime
        project_root = Path(__file__).parent.parent.parent.resolve()
        with tempfile.NamedTemporaryFile('w+', suffix='.yaml', delete=False) as tmp_cfg:
            try:
                # Формируем config.yaml с реальными параметрами
                cfg = {
                    'modules': {'google_sheets': True},
                    'google_sheets': {
                        'credentials': creds,
                        'sheet_id': sheet_id,
                        'worksheet': worksheet
                    },
                    'api_keys': ['testkey']
                }
                yaml.safe_dump(cfg, tmp_cfg)
                tmp_cfg.flush()
                config_path = tmp_cfg.name
            finally:
                tmp_cfg.close()
            print(f"[TEST] Google Sheets e2e: Using config.yaml: {config_path}")
            env = os.environ.copy()
            env['CONFIG_YAML'] = config_path
            proc = Popen([
                'uvicorn', 'central_server.server:app', '--host', '127.0.0.1', '--port', '8000', '--log-level', 'info'
            ], cwd=str(project_root), env=env)
            try:
                self.wait_server_ready('http://127.0.0.1:8000/')
                # Отправляем событие (лог)
                url_log = 'http://127.0.0.1:8000/api/send_message'
                now = datetime.now().isoformat()
                payload = {
                    'server_id': 'test-server',
                    'device_id': 'test_device',
                    'type': 'alert',
                    'message': f'Test Google Sheets e2e {now}'
                }
                headers = {'Authorization': 'Bearer testkey'}
                r = requests.post(url_log, json=payload, headers=headers, timeout=10)
                self.assertTrue(r.ok)
                # Проверяем, что строка появилась в Google Sheets
                gc = gspread.service_account(filename=creds)
                sh = gc.open_by_key(sheet_id)
                ws = sh.worksheet(worksheet)
                rows = ws.get_all_values()
                found = any(now[:16] in row[0] and 'Test Google Sheets e2e' in row[2] for row in rows[-10:])
                print(f"[TEST] Google Sheets e2e: found row: {found}")
                self.assertTrue(found)
            finally:
                print("[TEST] Terminating server...")
                proc.terminate()
                proc.wait()
                print(f"[TEST] Removing config.yaml: {config_path}")
                try:
                    os.unlink(config_path)
                except Exception as e:
                    print(f"[TEST] Could not remove config.yaml: {e}")

    def test_telegram_e2e(self):
        """
        E2E тест Telegram: если заданы TG_BOT_TOKEN и TG_CHAT_ID — реально отправляет красивое сообщение с эмодзи, markdown, подписью.
        """
        bot_token = os.environ.get('TG_BOT_TOKEN')
        chat_id = os.environ.get('TG_CHAT_ID')
        if not bot_token or not chat_id:
            print('[TEST] Telegram e2e: TG_BOT_TOKEN or TG_CHAT_ID not set, skipping real test.')
            return
        import requests
        from datetime import datetime
        text = (
            "🚀 <b>Интеграционный тест Telegram</b>\n"
            "✅ Всё работает! Время: <code>{}</code>\n"
            "👤 <i>Автоматизация ADB Device Manager</i>\n"
            "✨ <b>Успех!</b> #test #integration"
        ).format(datetime.now().isoformat())
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
        }
        resp = requests.post(url, data=data, timeout=10)
        print(f"[TEST] Telegram e2e: status={resp.status_code}, text={resp.text}")
        self.assertTrue(resp.ok)

if __name__ == '__main__':
    unittest.main() 