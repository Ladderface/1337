import os
import sys
import time
import yaml
import requests
import logging
import schedule
from pathlib import Path
from datetime import datetime
import threading
import json
import hashlib
from device_session import DeviceSession
from scenario_runner import ScenarioRunner
import integrations

CONFIG_PATH = Path(__file__).parent / 'config_agent.yaml'

# --- Загрузка конфига ---
def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

# --- Логирование ---
def setup_logging(level):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

# --- Watchdog ---
def watchdog_loop():
    while True:
        try:
            out = os.popen('adb devices').read()
            if 'device' not in out:
                logging.warning('ADB не видит ни одного устройства! Перезапуск...')
                os.system('adb kill-server')
                time.sleep(2)
                os.system('adb start-server')
        except Exception as e:
            logging.error(f'Watchdog error: {e}')
        time.sleep(30)

def start_watchdog():
    t = threading.Thread(target=watchdog_loop, daemon=True)
    t.start()

# --- Автосканирование ADB-устройств ---
def scan_adb_devices():
    out = os.popen('adb devices').read().splitlines()
    devices = []
    for line in out:
        if '\tdevice' in line:
            dev_id = line.split('\t')[0].strip()
            devices.append(dev_id)
    return devices

# --- last.png и отправка только новых скринов ---
def get_file_hash(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

last_hashes = {}

def device_job(cfg, device, section='default'):
    if not device.get('enabled', True):
        return
    session = DeviceSession(device, cfg)
    meta = session.get_metadata()
    # 1. Снять скриншот
    screenshot_path = session.take_screenshot()
    if screenshot_path:
        # 2. last.png + отправка только новых скринов
        hash_now = get_file_hash(screenshot_path)
        key = f"{device['id']}:{section}"
        if last_hashes.get(key) == hash_now:
            logging.info(f"[{device['id']}] Скриншот не изменился, не отправляю.")
            os.remove(screenshot_path)
            return
        last_hashes[key] = hash_now
        # last.png (перезапись)
        last_dir = Path(cfg.get('screenshot_dir', 'screenshots')) / device['id'].replace(':', '_') / section
        last_dir.mkdir(parents=True, exist_ok=True)
        last_path = last_dir / 'last.png'
        os.replace(screenshot_path, last_path)
        # 3. Отправить скриншот с метаданными и секцией
        upload_screenshot(cfg, device, last_path, meta, section)
        send_message(cfg, device['id'], 'log', f'Скриншот отправлен: {last_path}')
    else:
        send_message(cfg, device['id'], 'error', 'Ошибка снятия скриншота')
    # 4. Получить и выполнить команды
    commands = get_commands(cfg, device)
    for cmd in commands:
        status = 'done'
        result = ''
        try:
            if cmd['command'] == 'screencap':
                device_job(cfg, device, section=cmd.get('section', 'default'))
                result = 'Скриншот обновлён'
            elif cmd['command'] == 'echo':
                result = f'echo: {cmd["params"]}'
            elif cmd['command'] == 'update_agent':
                result = update_agent()
            elif cmd['command'] == 'custom':
                # TODO: кастомные бинды/действия
                result = f'custom: {cmd["params"]}'
            else:
                status = 'error'
                result = f'Неизвестная команда: {cmd["command"]}'
        except Exception as e:
            status = 'error'
            result = str(e)
        confirm_command(cfg, cmd['id'], status, result)

def upload_screenshot(cfg, device, screenshot_path, meta=None, section='default'):
    url = cfg['server_url'].rstrip('/') + '/upload_screenshot'
    headers = {'Authorization': f'Bearer {cfg["api_key"]}'}
    data = {
        'server_id': cfg['server_id'],
        'window': device.get('window', 'main'),
        'device_id': device['id'],
        'device_name': device.get('name', device['id']),
        'ip': device.get('ip', ''),
        'port': device.get('port', ''),
        'section': section,
        'meta': json.dumps(meta or {})
    }
    files = {'image': open(screenshot_path, 'rb')}
    resp = requests.post(url, headers=headers, data=data, files=files, timeout=30)
    if resp.ok:
        logging.info(f'[{device["id"]}] Скриншот отправлен: {resp.json().get("path")}')
    else:
        logging.error(f'[{device["id"]}] Ошибка отправки скриншота: {resp.text}')
    files['image'].close()

def send_message(cfg, device_id, msg_type, message):
    url = cfg['server_url'].rstrip('/') + '/api/send_message'
    headers = {'Authorization': f'Bearer {cfg["api_key"]}'}
    data = {
        'server_id': cfg['server_id'],
        'device_id': device_id,
        'type': msg_type,
        'message': message
    }
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=15)
        if resp.ok:
            logging.info(f'[{device_id}] Сообщение отправлено: {msg_type}')
        else:
            logging.error(f'[{device_id}] Ошибка отправки сообщения: {resp.text}')
    except Exception as e:
        logging.error(f'[{device_id}] Ошибка HTTP: {e}')

def get_commands(cfg, device):
    url = cfg['server_url'].rstrip('/') + '/api/get_commands'
    headers = {'Authorization': f'Bearer {cfg["api_key"]}'}
    params = {'server_id': cfg['server_id'], 'device_id': device['id']}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.ok:
            return resp.json().get('commands', [])
        else:
            logging.error(f'[{device["id"]}] Ошибка получения команд: {resp.text}')
    except Exception as e:
        logging.error(f'[{device["id"]}] Ошибка HTTP: {e}')
    return []

def confirm_command(cfg, command_id, status, result=None):
    url = cfg['server_url'].rstrip('/') + '/api/command_result'
    headers = {'Authorization': f'Bearer {cfg["api_key"]}'}
    data = {'command_id': command_id, 'status': status}
    if result:
        data['result'] = result
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        if resp.ok:
            logging.info(f'[cmd:{command_id}] Подтверждение отправлено: {status}')
        else:
            logging.error(f'[cmd:{command_id}] Ошибка подтверждения: {resp.text}')
    except Exception as e:
        logging.error(f'[cmd:{command_id}] Ошибка HTTP: {e}')

def schedule_jobs(cfg):
    def job_for_dynamic():
        # Автосканирование устройств
        found = scan_adb_devices()
        for dev_id in found:
            # Поиск в конфиге, если нет — добавить с дефолтными параметрами
            device = next((d for d in cfg['devices'] if d['id'] == dev_id), None)
            if not device:
                device = {'id': dev_id, 'enabled': True, 'window': 'main', 'interval': 60}
            threading.Thread(target=device_job, args=(cfg, device, 'default'), daemon=True).start()
    schedule.every(30).seconds.do(job_for_dynamic)
    # Также планировщик по конфигу (для кастомных секций/биндов)
    for device in cfg['devices']:
        interval = device.get('interval', 60)
        def job(dev=device):
            threading.Thread(target=device_job, args=(cfg, dev, 'default'), daemon=True).start()
        schedule.every(interval).seconds.do(job)

def update_agent():
    try:
        url = 'https://example.com/agent.py'  # TODO: указать реальный URL
        r = requests.get(url, timeout=10)
        if r.ok:
            with open(__file__, 'wb') as f:
                f.write(r.content)
            os.execv(sys.executable, ['python'] + sys.argv)
            return 'Агент обновлён и перезапущен'
        else:
            return f'Ошибка загрузки: {r.status_code}'
    except Exception as e:
        return f'Ошибка обновления: {e}'

def main():
    cfg = load_config()
    setup_logging(cfg.get('log_level', 'INFO'))
    logging.info('Агент запущен')
    start_watchdog()
    if len(sys.argv) > 1:
        if sys.argv[1] == 'status':
            for device in cfg['devices']:
                session = DeviceSession(device, cfg)
                meta = session.get_metadata()
                print(f"{device['id']}: {meta}")
            sys.exit(0)
        if sys.argv[1] == 'test':
            for device in cfg['devices']:
                device_job(cfg, device, 'default')
            sys.exit(0)
    schedule_jobs(cfg)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    main() 