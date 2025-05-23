import threading
import logging
from pathlib import Path
from datetime import datetime
import subprocess

class DeviceSession:
    def __init__(self, device, cfg):
        self.device = device
        self.cfg = cfg
        self.device_id = device['id']
        self.screenshot_dir = cfg.get('screenshot_dir', 'screenshots')
        Path(self.screenshot_dir).mkdir(exist_ok=True)
        self.lock = threading.Lock()

    def take_screenshot(self):
        ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        safe_device = self.device_id.replace(':', '_').replace('/', '_')
        filename = f'{safe_device}_{ts}.png'
        local_path = Path(self.screenshot_dir) / filename
        remote_path = f'/sdcard/{filename}'
        cmd_cap = ['adb', '-s', self.device_id, 'shell', 'screencap', '-p', remote_path]
        cmd_pull = ['adb', '-s', self.device_id, 'pull', remote_path, str(local_path)]
        cmd_rm = ['adb', '-s', self.device_id, 'shell', 'rm', remote_path]
        try:
            subprocess.run(cmd_cap, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(cmd_pull, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(cmd_rm, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if local_path.exists() and local_path.stat().st_size > 1000:
                return str(local_path)
        except Exception as e:
            logging.error(f'[{self.device_id}] Ошибка снятия скриншота: {e}')
        return None

    def get_metadata(self):
        meta = {}
        # Версия ADB
        try:
            out = subprocess.check_output(['adb', 'version'], stderr=subprocess.STDOUT, text=True)
            meta['adb_version'] = out.strip().splitlines()[0]
        except Exception as e:
            meta['adb_version'] = f'error: {e}'
        # Uptime устройства
        try:
            out = subprocess.check_output(['adb', '-s', self.device_id, 'shell', 'cat', '/proc/uptime'], stderr=subprocess.STDOUT, text=True)
            meta['uptime'] = out.strip().split()[0]
        except Exception as e:
            meta['uptime'] = f'error: {e}'
        # Свободное место
        try:
            out = subprocess.check_output(['adb', '-s', self.device_id, 'shell', 'df', '/data'], stderr=subprocess.STDOUT, text=True)
            lines = out.strip().splitlines()
            if len(lines) > 1:
                meta['free_space'] = lines[1]
            else:
                meta['free_space'] = lines[0]
        except Exception as e:
            meta['free_space'] = f'error: {e}'
        return meta

    # Метаданные, расширяемые методы, интеграции и т.д. будут добавлены далее 