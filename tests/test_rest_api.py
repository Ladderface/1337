import unittest
import requests
import tempfile
import os
import time
import yaml
from pathlib import Path
from subprocess import Popen
from datetime import datetime

class TestRestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).parent.parent.resolve()
        cls.server_dir = cls.project_root / 'central_server'
        cls.data_dir = cls.server_dir / 'data'
        cls.db_path = cls.server_dir / 'db.sqlite3'
        # Создаём временный config.yaml
        cls.tmp_cfg = tempfile.NamedTemporaryFile('w+', suffix='.yaml', delete=False)
        cfg = {
            'modules': {'webhook': False, 'google_sheets': False, 'telegram': False},
            'api_keys': ['testkey'],
            'users': [
                {'username': 'admin', 'api_key': 'testkey', 'role': 'admin'},
                {'username': 'user1', 'api_key': 'userkey', 'role': 'user'},
                {'username': 'guest', 'api_key': 'guestkey', 'role': 'readonly'}
            ]
        }
        yaml.safe_dump(cfg, cls.tmp_cfg)
        cls.tmp_cfg.flush()
        cls.config_path = cls.tmp_cfg.name
        cls.tmp_cfg.close()
        cls.env = os.environ.copy()
        cls.env['CONFIG_YAML'] = cls.config_path
        # Запускаем сервер
        cls.proc = Popen([
            'uvicorn', 'central_server.server:app', '--host', '127.0.0.1', '--port', '8000', '--log-level', 'info'
        ], cwd=str(cls.project_root), env=cls.env)
        cls.wait_server_ready('http://127.0.0.1:8000/')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait()
        try:
            os.unlink(cls.config_path)
        except Exception:
            pass
        # Чистим тестовые данные
        if cls.data_dir.exists():
            import shutil
            shutil.rmtree(cls.data_dir)
        import time
        if cls.db_path.exists():
            for _ in range(5):
                try:
                    os.remove(cls.db_path)
                    break
                except PermissionError:
                    time.sleep(0.5)

    @classmethod
    def wait_server_ready(cls, url, timeout=15):
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = requests.get(url, timeout=1)
                if r.status_code == 200:
                    return True
            except Exception:
                time.sleep(0.3)
        raise RuntimeError(f"Server not ready at {url}")

    def auth(self):
        return {'Authorization': 'Bearer testkey'}

    def test_01_upload_screenshot(self):
        url = 'http://127.0.0.1:8000/upload_screenshot'
        files = {'image': ('test.png', b'\x89PNG\r\n\x1a\n' + b'0'*2000, 'image/png')}
        data = {
            'server_id': 'test-server',
            'window': 'main',
            'device_id': 'test_device',
            'meta': '{}'
        }
        r = requests.post(url, files=files, data=data, headers=self.auth(), timeout=10)
        self.assertTrue(r.ok)

    def test_02_send_log(self):
        url = 'http://127.0.0.1:8000/api/send_message'
        payload = {
            'server_id': 'test-server',
            'device_id': 'test_device',
            'type': 'info',
            'message': 'Test log'
        }
        r = requests.post(url, json=payload, headers=self.auth(), timeout=10)
        self.assertTrue(r.ok)

    def test_03_export_screenshots_csv(self):
        url = 'http://127.0.0.1:8000/export/screenshots?format=csv'
        r = requests.get(url, headers=self.auth(), timeout=10)
        self.assertTrue(r.ok)
        self.assertIn('server_id', r.text)
        self.assertIn('test-server', r.text)

    def test_04_export_screenshots_zip(self):
        url = 'http://127.0.0.1:8000/export/screenshots?format=zip'
        r = requests.get(url, headers=self.auth(), timeout=10)
        self.assertTrue(r.ok)
        self.assertEqual(r.headers['content-type'], 'application/zip')

    def test_05_export_logs_csv(self):
        url = 'http://127.0.0.1:8000/export/logs?format=csv'
        r = requests.get(url, headers=self.auth(), timeout=10)
        self.assertTrue(r.ok)
        self.assertIn('server_id', r.text)
        self.assertIn('Test log', r.text)

    def test_06_command_lifecycle(self):
        # Отправка команды
        url = 'http://127.0.0.1:8000/commands'
        data = {
            'server_id': 'test-server',
            'device_id': 'test_device',
            'command': 'echo',
            'params': '{"msg": "hello"}'
        }
        r = requests.post(url, data=data, headers=self.auth(), timeout=10, allow_redirects=False)
        self.assertIn(r.status_code, (303, 200))
        # Получение команд через API
        url = 'http://127.0.0.1:8000/api/get_commands?server_id=test-server&device_id=test_device'
        r = requests.get(url, headers=self.auth(), timeout=10)
        self.assertTrue(r.ok)
        cmds = r.json()['commands']
        self.assertTrue(any(cmd['command'] == 'echo' for cmd in cmds))
        # Подтверждение выполнения команды
        cmd_id = cmds[0]['id']
        url = 'http://127.0.0.1:8000/api/command_result'
        payload = {'command_id': cmd_id, 'status': 'done', 'result': 'ok'}
        r = requests.post(url, json=payload, headers=self.auth(), timeout=10)
        self.assertTrue(r.ok)

    def test_07_export_command_history_csv(self):
        url = 'http://127.0.0.1:8000/api/command_history?format=csv'
        r = requests.get(url, headers=self.auth(), timeout=10)
        self.assertTrue(r.ok)
        self.assertIn('command', r.text)
        self.assertIn('echo', r.text)

    def test_08_export_command_history_xlsx(self):
        url = 'http://127.0.0.1:8000/api/command_history?format=xlsx'
        r = requests.get(url, headers=self.auth(), timeout=10)
        self.assertTrue(r.ok)
        self.assertEqual(r.headers['content-type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_09_analytics_summary(self):
        url = 'http://127.0.0.1:8000/api/analytics/summary'
        r = requests.get(url, timeout=10)
        self.assertTrue(r.ok)
        data = r.json()
        self.assertIn('screens_logs', data)
        self.assertIn('commands_status', data)

    def test_10_analytics_device_activity(self):
        url = 'http://127.0.0.1:8000/api/analytics/device_activity'
        r = requests.get(url, timeout=10)
        self.assertTrue(r.ok)
        data = r.json()
        self.assertIn('device_activity', data)

    def test_11_analytics_errors(self):
        url = 'http://127.0.0.1:8000/api/analytics/errors'
        r = requests.get(url, timeout=10)
        self.assertTrue(r.ok)
        data = r.json()
        self.assertIn('errors', data)

    def test_12_analytics_commands_history(self):
        url = 'http://127.0.0.1:8000/api/analytics/commands_history'
        r = requests.get(url, timeout=10)
        self.assertTrue(r.ok)
        data = r.json()
        self.assertIn('commands_history', data)

    def test_13_role_admin_can_export(self):
        url = 'http://127.0.0.1:8000/export/screenshots?format=csv'
        r = requests.get(url, headers=self.auth(), timeout=10)
        self.assertTrue(r.ok)

    def test_14_role_user_cannot_export(self):
        url = 'http://127.0.0.1:8000/export/screenshots?format=csv'
        r = requests.get(url, headers={'Authorization': 'Bearer userkey'}, timeout=10)
        self.assertEqual(r.status_code, 403)

    def test_15_role_guest_cannot_send_log(self):
        url = 'http://127.0.0.1:8000/api/send_message'
        payload = {
            'server_id': 'test-server',
            'device_id': 'test_device',
            'type': 'info',
            'message': 'Test log guest'
        }
        r = requests.post(url, json=payload, headers={'Authorization': 'Bearer guestkey'}, timeout=10)
        self.assertEqual(r.status_code, 403)

    def test_16_role_user_can_send_log(self):
        url = 'http://127.0.0.1:8000/api/send_message'
        payload = {
            'server_id': 'test-server',
            'device_id': 'test_device',
            'type': 'info',
            'message': 'Test log user'
        }
        r = requests.post(url, json=payload, headers={'Authorization': 'Bearer userkey'}, timeout=10)
        self.assertTrue(r.ok)

    def test_17_role_guest_cannot_send_command(self):
        url = 'http://127.0.0.1:8000/commands'
        data = {
            'server_id': 'test-server',
            'device_id': 'test_device',
            'command': 'echo',
            'params': '{}'
        }
        r = requests.post(url, data=data, headers={'Authorization': 'Bearer guestkey'}, timeout=10, allow_redirects=False)
        self.assertEqual(r.status_code, 403)

    def test_18_role_user_can_send_command(self):
        url = 'http://127.0.0.1:8000/commands'
        data = {
            'server_id': 'test-server',
            'device_id': 'test_device',
            'command': 'echo',
            'params': '{}'
        }
        r = requests.post(url, data=data, headers={'Authorization': 'Bearer userkey'}, timeout=10, allow_redirects=False)
        self.assertIn(r.status_code, (303, 200))

if __name__ == '__main__':
    unittest.main() 