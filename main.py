import yaml
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, BackgroundTasks, Path as FastAPIPath
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import subprocess
import cv2
import numpy as np
import os
import shutil
import sqlite3
from contextlib import closing
import traceback
import asyncio

# --- Автоматическое создание всех нужных папок, шаблонов и config.yaml ---
def ensure_dirs():
    for d in ['templates', 'static', 'screenshots', 'logs']:
        os.makedirs(d, exist_ok=True)
    # Авто-создание вложенных папок для скринов из config.yaml
    try:
        if os.path.exists('config.yaml'):
            import yaml
            with open('config.yaml', 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
            for sc in cfg.get('scenarios', {}).values():
                for step in sc.get('steps', []):
                    d = step.get('screenshot_dir')
                    if d:
                        os.makedirs(d, exist_ok=True)
    except Exception as e:
        print(f"[ensure_dirs] Ошибка при создании вложенных папок: {e}")
    # Создаём базовые шаблоны, если их нет
    if not os.path.exists('templates/index.html'):
        with open('templates/index.html', 'w', encoding='utf-8') as f:
            f.write('<h1>ADB Device Manager</h1>')
    if not os.path.exists('templates/adb.html'):
        with open('templates/adb.html', 'w', encoding='utf-8') as f:
            f.write('<h1>ADB Status</h1>')
    if not os.path.exists('templates/logs.html'):
        with open('templates/logs.html', 'w', encoding='utf-8') as f:
            f.write('<h1>Логи</h1>')
    if not os.path.exists('static/style.css'):
        with open('static/style.css', 'w', encoding='utf-8') as f:
            f.write('body { font-family: Arial, sans-serif; }')
    # Авто-создание config.yaml если его нет
    if not os.path.exists('config.yaml'):
        with open('config.yaml', 'w', encoding='utf-8') as f:
            f.write('devices: []\nscenarios: {}\nglobal: {}\n')

# --- Автоматическая инициализация БД ---
DB_PATH = 'adb_manager.db'
def init_db():
    if not os.path.exists(DB_PATH):
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                event_type TEXT,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS device_status (
                device_id TEXT PRIMARY KEY,
                status TEXT,
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            conn.commit()

# --- Конфиг загрузка ---
def load_config(path: str) -> Dict[str, Any]:
    """Загрузка YAML-конфига."""
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

class StepResult(BaseModel):
    success: bool
    message: str

# --- Логирование (in-memory + файл) ---
class LogManager:
    def __init__(self, log_file: str = "app.log", max_lines: int = 1000):
        self.log_file = log_file
        self.max_lines = max_lines
        self.lines = []
        self.lock = threading.Lock()
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                self.lines = f.readlines()[-max_lines:]

    def log(self, msg: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        with self.lock:
            self.lines.append(line)
            if len(self.lines) > self.max_lines:
                self.lines = self.lines[-self.max_lines:]
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(line + "\n")

    def get_lines(self, n: int = 100):
        with self.lock:
            return self.lines[-n:]

log_manager = LogManager()

def log(msg: str):
    print(msg)
    log_manager.log(msg)

# --- DeviceSession ---
class DeviceSession:
    """
    Класс для управления сессией одного устройства.
    Поддерживает старт/стоп/пауза/резюм, выполнение шагов, хранит состояние.
    Поддерживает verify_screen и расширенные скриншоты.
    """
    def __init__(self, device_id: str, scenario: List[Dict[str, Any]], global_cfg: Dict[str, Any]):
        self.device_id = device_id
        self.scenario = scenario
        self.global_cfg = global_cfg
        self.state = 'stopped'  # running, paused, stopped
        self.current_step = 0
        self.lock = threading.Lock()
        self.thread = None
        self.last_result: Optional[StepResult] = None

    def start(self):
        """Запуск сессии устройства."""
        with self.lock:
            if self.state == 'running':
                return
            self.state = 'running'
            self.thread = threading.Thread(target=self.run)
            self.thread.start()
            log(f"[Device {self.device_id}] START")

    def pause(self):
        """Пауза сессии."""
        with self.lock:
            if self.state == 'running':
                self.state = 'paused'
                log(f"[Device {self.device_id}] PAUSE")

    def resume(self):
        """Возобновление сессии."""
        with self.lock:
            if self.state == 'paused':
                self.state = 'running'
                log(f"[Device {self.device_id}] RESUME")

    def stop(self):
        """Остановка сессии."""
        with self.lock:
            self.state = 'stopped'
            log(f"[Device {self.device_id}] STOP")

    def run(self):
        while self.current_step < len(self.scenario):
            with self.lock:
                if self.state == 'stopped':
                    break
                if self.state == 'paused':
                    time.sleep(1)
                    continue
                step = self.scenario[self.current_step]
            self.last_result = self.do_step(step)
            with self.lock:
                self.current_step += 1
        with self.lock:
            self.state = 'stopped'
            log(f"[Device {self.device_id}] FINISHED")

    def do_step(self, step: Dict[str, Any]) -> StepResult:
        action = step.get('action')
        try:
            if action == 'click_image':
                return self.click_image(step)
            elif action == 'input_text':
                return self.input_text(step)
            elif action == 'wait':
                return self.wait(step)
            elif action == 'verify_screen':
                return self.verify_screen(step)
            if step.get('screenshot'):
                self.take_screenshot(step)
            if step.get('upload_to_db'):
                self.upload_screenshot_to_db(step)
            return StepResult(success=True, message=f"Step {action} выполнен")
        except Exception as e:
            log(f"[Device {self.device_id}] ERROR: {e}")
            return StepResult(success=False, message=str(e))

    def click_image(self, step: Dict[str, Any]) -> StepResult:
        template = step.get('template')
        screenshot_path = f"tmp_{self.device_id}_click.png"
        if not self.take_screenshot({'screenshot_path': screenshot_path}).success:
            return StepResult(success=False, message="Не удалось сделать скриншот")
        if not Path(template).is_file():
            return StepResult(success=False, message=f"Шаблон {template} не найден")
        img = cv2.imread(screenshot_path)
        tpl = cv2.imread(template)
        if img is None or tpl is None:
            return StepResult(success=False, message="Ошибка чтения скриншота или шаблона")
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        threshold = step.get('threshold', 0.8)
        if max_val < threshold:
            return StepResult(success=False, message=f"Совпадение ниже порога: {max_val:.2f}")
        h, w = tpl.shape[:2]
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2
        cmd = [self.global_cfg.get('adb_path', 'adb'), '-s', self.device_id, 'shell', 'input', 'tap', str(center_x), str(center_y)]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return StepResult(success=False, message=f"Ошибка ADB: {result.stderr}")
        log(f"[Device {self.device_id}] Клик по ({center_x},{center_y}) по шаблону {template}")
        return StepResult(success=True, message=f"Клик по ({center_x},{center_y})")

    def verify_screen(self, step: Dict[str, Any]) -> StepResult:
        template = step.get('template')
        screenshot_path = f"tmp_{self.device_id}_verify.png"
        if not self.take_screenshot({'screenshot_path': screenshot_path}).success:
            return StepResult(success=False, message="Не удалось сделать скриншот для верификации")
        if not Path(template).is_file():
            return StepResult(success=False, message=f"Шаблон {template} не найден")
        img = cv2.imread(screenshot_path)
        tpl = cv2.imread(template)
        if img is None or tpl is None:
            return StepResult(success=False, message="Ошибка чтения скриншота или шаблона")
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        threshold = step.get('threshold', 0.8)
        if max_val < threshold:
            return StepResult(success=False, message=f"Верификация не пройдена: совпадение {max_val:.2f}")
        screenshot_dir = step.get('screenshot_dir', self.global_cfg.get('screenshot_dir', 'screenshots'))
        section = step.get('screenshot_section', 'default')
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
        final_path = Path(screenshot_dir) / f"{self.device_id}_{section}_{int(time.time())}.png"
        cmd = [self.global_cfg.get('adb_path', 'adb'), '-s', self.device_id, 'shell', 'screencap', '-p', '/sdcard/tmp_screen.png']
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return StepResult(success=False, message=f"Ошибка screencap: {result.stderr}")
        cmd = [self.global_cfg.get('adb_path', 'adb'), '-s', self.device_id, 'pull', '/sdcard/tmp_screen.png', str(final_path)]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return StepResult(success=False, message=f"Ошибка pull: {result.stderr}")
        log(f"[Device {self.device_id}] Верификация успешна, скриншот сохранён: {final_path}")
        return StepResult(success=True, message=f"Верификация успешна, скриншот сохранён: {final_path}")

    def input_text(self, step: Dict[str, Any]) -> StepResult:
        text = step.get('text', '')
        cmd = [self.global_cfg.get('adb_path', 'adb'), '-s', self.device_id, 'shell', 'input', 'text', text.replace(' ', '%s')]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return StepResult(success=False, message=f"Ошибка ADB: {result.stderr}")
        log(f"[Device {self.device_id}] Введён текст: {text}")
        return StepResult(success=True, message=f"Введён текст: {text}")

    def wait(self, step: Dict[str, Any]) -> StepResult:
        seconds = step.get('seconds', 1)
        log(f"[Device {self.device_id}] Ожидание {seconds} сек")
        time.sleep(seconds)
        return StepResult(success=True, message=f"Ожидание {seconds} сек")

    def take_screenshot(self, step: Dict[str, Any]) -> StepResult:
        screenshot_dir = step.get('screenshot_dir', self.global_cfg.get('screenshot_dir', 'screenshots'))
        section = step.get('screenshot_section', 'default')
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
        screenshot_path = step.get('screenshot_path', str(Path(screenshot_dir) / f"{self.device_id}_{section}_{int(time.time())}.png"))
        cmd = [self.global_cfg.get('adb_path', 'adb'), '-s', self.device_id, 'shell', 'screencap', '-p', '/sdcard/tmp_screen.png']
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return StepResult(success=False, message=f"Ошибка screencap: {result.stderr}")
        cmd = [self.global_cfg.get('adb_path', 'adb'), '-s', self.device_id, 'pull', '/sdcard/tmp_screen.png', screenshot_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return StepResult(success=False, message=f"Ошибка pull: {result.stderr}")
        log(f"[Device {self.device_id}] Скриншот сохранён: {screenshot_path}")
        return StepResult(success=True, message=f"Скриншот сохранён: {screenshot_path}")

    def upload_screenshot_to_db(self, step: Dict[str, Any]) -> StepResult:
        log(f"[Device {self.device_id}] Скриншот загружен в БД (заглушка)")
        return StepResult(success=True, message="Скриншот загружен в БД (заглушка)")

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                'device_id': self.device_id,
                'state': self.state,
                'current_step': self.current_step,
                'last_result': self.last_result.dict() if self.last_result else None
            }

class DeviceManager:
    """
    Класс для управления всеми сессиями устройств.
    Поддерживает запуск "кнопок" (actions) из конфига.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sessions: Dict[str, DeviceSession] = {}
        self.global_cfg = config.get('global', {})
        self.buttons = {b['name']: b for b in config.get('buttons', [])}
        self.load_sessions()

    def load_sessions(self):
        scenarios = self.config.get('scenarios', {})
        for dev in self.config.get('devices', []):
            if not dev.get('enabled', True):
                continue
            scenario_name = dev.get('scenario', 'default')
            scenario = scenarios.get(scenario_name, {}).get('steps', [])
            self.sessions[dev['id']] = DeviceSession(dev['id'], scenario, self.global_cfg)

    def start_all(self):
        for session in self.sessions.values():
            session.start()

    def pause_all(self):
        for session in self.sessions.values():
            session.pause()

    def resume_all(self):
        for session in self.sessions.values():
            session.resume()

    def stop_all(self):
        for session in self.sessions.values():
            session.stop()

    def start_device(self, device_id: str):
        if device_id in self.sessions:
            self.sessions[device_id].start()

    def pause_device(self, device_id: str):
        if device_id in self.sessions:
            self.sessions[device_id].pause()

    def resume_device(self, device_id: str):
        if device_id in self.sessions:
            self.sessions[device_id].resume()

    def stop_device(self, device_id: str):
        if device_id in self.sessions:
            self.sessions[device_id].stop()

    def get_status_all(self) -> List[Dict[str, Any]]:
        return [s.get_status() for s in self.sessions.values()]

    def get_status_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        if device_id in self.sessions:
            return self.sessions[device_id].get_status()
        return None

    def get_buttons(self) -> List[Dict[str, Any]]:
        return list(self.buttons.values())

    def run_button(self, button_name: str, device_id: Optional[str] = None) -> str:
        if button_name not in self.buttons:
            raise ValueError(f"Кнопка {button_name} не найдена")
        scenario_name = self.buttons[button_name]['scenario']
        scenarios = self.config.get('scenarios', {})
        scenario = scenarios.get(scenario_name, {}).get('steps', [])
        if not scenario:
            raise ValueError(f"Сценарий {scenario_name} не найден")
        targets = [device_id] if device_id else list(self.sessions.keys())
        for dev_id in targets:
            if dev_id in self.sessions:
                self.sessions[dev_id].stop()
                time.sleep(0.2)
                self.sessions[dev_id] = DeviceSession(dev_id, scenario, self.global_cfg)
                self.sessions[dev_id].start()
            else:
                self.sessions[dev_id] = DeviceSession(dev_id, scenario, self.global_cfg)
                self.sessions[dev_id].start()
        log(f"Кнопка {button_name} запущена для устройств: {targets}")
        return f"Кнопка {button_name} запущена для устройств: {targets}"

# --- FastAPI REST API + Web UI ---
app = FastAPI(title="ADB Device Manager API", description="REST API + Web UI для управления сессиями устройств через ADB", version="2.0")

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

manager: Optional[DeviceManager] = None

MONITOR_SCREEN_DIR = Path('screenshots/monitor')
MONITOR_SCREEN_DIR.mkdir(parents=True, exist_ok=True)

def take_monitor_screenshot(device_id: str, adb_path: str = 'adb') -> Optional[str]:
    """Делает мониторинговый скриншот для устройства и сохраняет как <device_id>.png"""
    safe_id = device_id.replace(':', '_')
    out_path = MONITOR_SCREEN_DIR / f"{safe_id}.png"
    tmp_path = f"tmp_{safe_id}_monitor.png"
    try:
        # Снимаем скриншот через ADB
        cmd1 = [adb_path, '-s', device_id, 'shell', 'screencap', '-p', '/sdcard/tmp_monitor.png']
        res1 = subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if res1.returncode != 0:
            log(f"[MONITOR] Ошибка screencap {device_id}: {res1.stderr}")
            return None
        cmd2 = [adb_path, '-s', device_id, 'pull', '/sdcard/tmp_monitor.png', tmp_path]
        res2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if res2.returncode != 0:
            log(f"[MONITOR] Ошибка pull {device_id}: {res2.stderr}")
            return None
        # Перемещаем tmp в нужное место (перезаписываем)
        shutil.move(tmp_path, out_path)
        return str(out_path.name)
    except Exception as e:
        log(f"[MONITOR] Ошибка monitor screenshot {device_id}: {e}")
        return None
    finally:
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass

# --- Фоновая задача мониторинга ---
def monitor_background_task():
    while True:
        try:
            if manager is not None:
                for dev in manager.sessions.keys():
                    adb_path = manager.global_cfg.get('adb_path', 'adb')
                    take_monitor_screenshot(dev, adb_path)
        except Exception as e:
            log(f"[MONITOR] Ошибка фоновой задачи: {e}")
        time.sleep(30)

@app.on_event("startup")
def startup_event():
    global manager
    config = load_config('config.yaml')
    manager = DeviceManager(config)
    manager.start_all()
    # Запуск фоновой задачи мониторинга
    threading.Thread(target=monitor_background_task, daemon=True).start()
    # Запуск фоновой задачи для автоснимков
    def periodic_screenshots():
        while True:
            for dev_id, session in manager.sessions.items():
                session.take_screenshot({'screenshot_section': 'auto', 'screenshot_dir': manager.global_cfg.get('screenshot_dir', 'screenshots')})
            time.sleep(30)
    threading.Thread(target=periodic_screenshots, daemon=True).start()

@app.get("/", response_class=HTMLResponse)
def web_index(request: Request):
    try:
        if manager is None:
            return PlainTextResponse("[Ошибка] Менеджер не инициализирован! Проверь config.yaml.", status_code=500)
        # --- Только устройства из config.yaml/devices.txt (manager.sessions) ---
        devices = manager.get_status_all() if hasattr(manager, 'get_status_all') else []
        buttons = manager.get_buttons() if hasattr(manager, 'get_buttons') else []
        screenshots = get_latest_screenshots() if 'get_latest_screenshots' in globals() else []
        device_screens = {}
        for dev in devices:
            dev_id = dev['device_id']
            safe_id = dev_id.replace(':', '_')
            mon_path = MONITOR_SCREEN_DIR / f"{safe_id}.png"
            device_screens[dev_id] = mon_path.name if mon_path.exists() else None
        return templates.TemplateResponse("index.html", {
            "request": request,
            "devices": devices,
            "buttons": buttons,
            "screenshots": screenshots,
            "device_screens": device_screens,
            "now": lambda: int(time.time())
        })
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[web_index] Ошибка: {e}\n{tb}")
        return PlainTextResponse(f"[Ошибка web_index]\n{e}\n{tb}", status_code=500)

@app.get("/adb", response_class=HTMLResponse)
def adb_status(request: Request):
    try:
        adb_devices = get_adb_devices() if 'get_adb_devices' in globals() else []
        adb_log = get_adb_log() if 'get_adb_log' in globals() else []
        return templates.TemplateResponse("adb.html", {"request": request, "adb_devices": adb_devices, "adb_log": adb_log})
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[adb_status] Ошибка: {e}\n{tb}")
        return PlainTextResponse(f"[Ошибка adb_status]\n{e}\n{tb}", status_code=500)

@app.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request):
    try:
        return templates.TemplateResponse("logs.html", {"request": request})
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[logs_page] Ошибка: {e}\n{tb}")
        return PlainTextResponse(f"[Ошибка logs_page]\n{e}\n{tb}", status_code=500)

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    last_idx = 0
    try:
        while True:
            lines = log_manager.get_lines(100)
            new_lines = lines[last_idx:]
            if new_lines:
                await websocket.send_text("\n".join(new_lines))
                last_idx = len(lines)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass

@app.websocket("/ws/cli")
async def websocket_cli(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # Выполняем команду как в CLI
            result = handle_cli_command(data)
            await websocket.send_text(result)
    except WebSocketDisconnect:
        pass

@app.get("/screenshots/{filename}")
def get_screenshot(filename: str):
    try:
        screenshot_dir = manager.global_cfg.get('screenshot_dir', 'screenshots') if manager else 'screenshots'
        file_path = Path(screenshot_dir) / filename
        if not file_path.exists():
            return PlainTextResponse("Screenshot not found", status_code=404)
        return FileResponse(str(file_path))
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[get_screenshot] Ошибка: {e}\n{tb}")
        return PlainTextResponse(f"[Ошибка get_screenshot]\n{e}\n{tb}", status_code=500)

# --- API и CLI как раньше ---
@app.get("/devices", summary="Список устройств и их статусы")
def get_devices():
    return manager.get_status_all()

@app.get("/devices/{device_id}", summary="Статус устройства")
def get_device(device_id: str):
    status = manager.get_status_device(device_id)
    if not status:
        raise HTTPException(status_code=404, detail="Device not found")
    return status

@app.post("/devices/{device_id}/start", summary="Старт сессии устройства")
def start_device(device_id: str):
    manager.start_device(device_id)
    return {"result": "started"}

@app.post("/devices/{device_id}/pause", summary="Пауза сессии устройства")
def pause_device(device_id: str):
    manager.pause_device(device_id)
    return {"result": "paused"}

@app.post("/devices/{device_id}/resume", summary="Возобновить сессию устройства")
def resume_device(device_id: str):
    manager.resume_device(device_id)
    return {"result": "resumed"}

@app.post("/devices/{device_id}/stop", summary="Остановить сессию устройства")
def stop_device(device_id: str):
    manager.stop_device(device_id)
    return {"result": "stopped"}

@app.get("/status", summary="Статус всех устройств")
def status():
    return manager.get_status_all()

@app.get("/buttons", summary="Список программируемых кнопок")
def get_buttons():
    return manager.get_buttons()

@app.post("/buttons/{button_name}/run", summary="Запустить кнопку (сценарий) для всех устройств или одного")
def run_button(button_name: str, device_id: Optional[str] = None):
    try:
        log(f"[WEB] Нажата кнопка: {button_name} (device_id={device_id}) из веб-интерфейса")
        result = manager.run_button(button_name, device_id)
        # Возвращаем актуальный статус устройств
        status = manager.get_status_all()
        log(f"[WEB] Кнопка {button_name} выполнена, статус устройств: {status}")
        return {"result": result, "status": status}
    except Exception as e:
        log(f"[WEB][ERROR] Ошибка при запуске кнопки {button_name}: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# --- Вспомогательные функции для web ---
def get_latest_screenshots(n: int = 10):
    screenshot_dir = manager.global_cfg.get('screenshot_dir', 'screenshots')
    files = list(Path(screenshot_dir).glob('*.png'))
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return [f.name for f in files[:n]]

def get_adb_devices():
    try:
        result = subprocess.run([manager.global_cfg.get('adb_path', 'adb'), 'devices'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout.strip().split('\n')
    except Exception as e:
        return [f"Ошибка: {e}"]

def get_adb_log():
    try:
        result = subprocess.run([manager.global_cfg.get('adb_path', 'adb'), 'logcat', '-d', '-t', '50'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout.strip().split('\n')
    except Exception as e:
        return [f"Ошибка: {e}"]

import asyncio

def handle_cli_command(cmd: str) -> str:
    # Простейший парсер для web-CLI
    try:
        parts = cmd.strip().split()
        if not parts:
            return ''
        if parts[0] == 'pause':
            if len(parts) == 1:
                manager.pause_all()
                return 'Все устройства на паузе.'
            else:
                manager.pause_device(parts[1])
                return f'Устройство {parts[1]} на паузе.'
        elif parts[0] == 'resume':
            if len(parts) == 1:
                manager.resume_all()
                return 'Все устройства возобновлены.'
            else:
                manager.resume_device(parts[1])
                return f'Устройство {parts[1]} возобновлено.'
        elif parts[0] == 'stop':
            if len(parts) == 1:
                manager.stop_all()
                return 'Все устройства остановлены.'
            else:
                manager.stop_device(parts[1])
                return f'Устройство {parts[1]} остановлено.'
        elif parts[0] == 'start':
            if len(parts) == 1:
                manager.start_all()
                return 'Все устройства запущены.'
            else:
                manager.start_device(parts[1])
                return f'Устройство {parts[1]} запущено.'
        elif parts[0] == 'button':
            if len(parts) == 2:
                return manager.run_button(parts[1])
            elif len(parts) == 3:
                return manager.run_button(parts[1], parts[2])
            else:
                return 'Использование: button <name> [<device_id>]'
        elif parts[0] == 'devices':
            return '\n'.join([str(d) for d in manager.get_status_all()])
        elif parts[0] == 'adb':
            return '\n'.join(get_adb_devices())
        elif parts[0] == 'logs':
            return '\n'.join(log_manager.get_lines(50))
        else:
            return 'Неизвестная команда'
    except Exception as e:
        return f'Ошибка: {e}'

# --- CLI для совместимости ---
def main():
    ensure_dirs()
    init_db()
    try:
        import sys
        if len(sys.argv) > 1 and sys.argv[1] == 'api':
            uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
            return
        config = load_config('config.yaml')
        manager = DeviceManager(config)
        manager.start_all()
        print("Все устройства запущены. Введите команду (pause/resume/stop/start <id>/button <name> [<id>]/exit):")
        while True:
            cmd = input('> ').strip().split()
            if not cmd:
                continue
            if cmd[0] == 'exit':
                manager.stop_all()
                break
            elif cmd[0] == 'pause':
                if len(cmd) == 1:
                    manager.pause_all()
                else:
                    manager.pause_device(cmd[1])
            elif cmd[0] == 'resume':
                if len(cmd) == 1:
                    manager.resume_all()
                else:
                    manager.resume_device(cmd[1])
            elif cmd[0] == 'stop':
                if len(cmd) == 1:
                    manager.stop_all()
                else:
                    manager.stop_device(cmd[1])
            elif cmd[0] == 'start':
                if len(cmd) == 1:
                    manager.start_all()
                else:
                    manager.start_device(cmd[1])
            elif cmd[0] == 'button':
                if len(cmd) == 2:
                    print(manager.run_button(cmd[1]))
                elif len(cmd) == 3:
                    print(manager.run_button(cmd[1], cmd[2]))
                else:
                    print("Использование: button <name> [<device_id>]")
            else:
                print("Неизвестная команда")
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[main] Ошибка: {e}\n{tb}")
        with open('app_crash.log', 'a', encoding='utf-8') as f:
            f.write(f"[main] Ошибка: {e}\n{tb}\n")
        print("[FATAL] Программа завершена с ошибкой. См. app_crash.log")

if __name__ == "__main__":
    main()

# --- Функции для работы с БД ---
def save_screenshot(device_id: str, path: str):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO screenshots (device_id, path) VALUES (?, ?)', (device_id, path))
        conn.commit()

def get_latest_screenshots(device_id: str = None, n: int = 10):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        if device_id:
            c.execute('SELECT path, created_at FROM screenshots WHERE device_id=? ORDER BY created_at DESC LIMIT ?', (device_id, n))
        else:
            c.execute('SELECT path, created_at FROM screenshots ORDER BY created_at DESC LIMIT ?', (n,))
        return c.fetchall()

def save_event(device_id: str, event_type: str, message: str):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO events (device_id, event_type, message) VALUES (?, ?, ?)', (device_id, event_type, message))
        conn.commit()

def get_events(device_id: str = None, n: int = 100):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        if device_id:
            c.execute('SELECT event_type, message, created_at FROM events WHERE device_id=? ORDER BY created_at DESC LIMIT ?', (device_id, n))
        else:
            c.execute('SELECT device_id, event_type, message, created_at FROM events ORDER BY created_at DESC LIMIT ?', (n,))
        return c.fetchall()

def update_device_status(device_id: str, status: str):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('REPLACE INTO device_status (device_id, status, last_update) VALUES (?, ?, CURRENT_TIMESTAMP)', (device_id, status))
        conn.commit()

def get_device_status(device_id: str = None):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        if device_id:
            c.execute('SELECT status, last_update FROM device_status WHERE device_id=?', (device_id,))
            return c.fetchone()
        else:
            c.execute('SELECT device_id, status, last_update FROM device_status')
            return c.fetchall()

# --- В main() ---
def main():
    ensure_dirs()
    init_db()
    try:
        import sys
        if len(sys.argv) > 1 and sys.argv[1] == 'api':
            uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
            return
        config = load_config('config.yaml')
        manager = DeviceManager(config)
        manager.start_all()
        print("Все устройства запущены. Введите команду (pause/resume/stop/start <id>/button <name> [<id>]/exit):")
        while True:
            cmd = input('> ').strip().split()
            if not cmd:
                continue
            if cmd[0] == 'exit':
                manager.stop_all()
                break
            elif cmd[0] == 'pause':
                if len(cmd) == 1:
                    manager.pause_all()
                else:
                    manager.pause_device(cmd[1])
            elif cmd[0] == 'resume':
                if len(cmd) == 1:
                    manager.resume_all()
                else:
                    manager.resume_device(cmd[1])
            elif cmd[0] == 'stop':
                if len(cmd) == 1:
                    manager.stop_all()
                else:
                    manager.stop_device(cmd[1])
            elif cmd[0] == 'start':
                if len(cmd) == 1:
                    manager.start_all()
                else:
                    manager.start_device(cmd[1])
            elif cmd[0] == 'button':
                if len(cmd) == 2:
                    print(manager.run_button(cmd[1]))
                elif len(cmd) == 3:
                    print(manager.run_button(cmd[1], cmd[2]))
                else:
                    print("Использование: button <name> [<device_id>]")
            else:
                print("Неизвестная команда")
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[main] Ошибка: {e}\n{tb}")
        with open('app_crash.log', 'a', encoding='utf-8') as f:
            f.write(f"[main] Ошибка: {e}\n{tb}\n")
        print("[FATAL] Программа завершена с ошибкой. См. app_crash.log")

# --- В местах создания скриншота ---
# save_screenshot(device_id, screenshot_path)
# save_event(device_id, 'screenshot', 'Скриншот сохранён')
# update_device_status(device_id, 'running/paused/stopped')

# --- В web-интерфейсе ---
# Использовать get_latest_screenshots, get_events, get_device_status для отображения 

# --- ADB Port Scanner ---
PORT_RANGE = range(4000, 7000)
SEM_LIMIT = 500

async def connect_to_port(port, sem):
    async with sem:
        command = f"adb connect 127.0.0.1:{port}"
        try:
            proc = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            output = stdout.decode() + stderr.decode()
            if "connected" in output or "already connected" in output:
                return f"127.0.0.1:{port}"
        except Exception:
            pass

async def scan_adb_ports():
    sem = asyncio.Semaphore(SEM_LIMIT)
    tasks = [connect_to_port(port, sem) for port in PORT_RANGE]
    results = await asyncio.gather(*tasks)
    found = [d for d in results if d]
    # Больше не трогаем devices.txt! Только возвращаем найденные устройства
    return found

@app.post("/scan_adb", summary="Сканировать порты ADB и обновить список устройств")
def scan_adb_endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(asyncio.run, scan_adb_ports())
    return {"status": "scan started"}

# --- Web: мониторинг и история скринов ---
@app.get("/monitor", response_class=HTMLResponse)
def monitor_page(request: Request):
    try:
        # --- Только устройства из config.yaml/devices.txt (manager.sessions) ---
        devices = manager.get_status_all() if manager else []
        device_screens = {}
        for dev in devices:
            dev_id = dev['device_id']
            safe_id = dev_id.replace(':', '_')
            mon_path = MONITOR_SCREEN_DIR / f"{safe_id}.png"
            device_screens[dev_id] = mon_path.name if mon_path.exists() else None
        return templates.TemplateResponse("monitor.html", {"request": request, "devices": devices, "device_screens": device_screens, "now": lambda: int(time.time())})
    except Exception as e:
        tb = traceback.format_exc()
        return PlainTextResponse(f"[Ошибка monitor_page]\n{e}\n{tb}", status_code=500)

@app.get("/history/{device_id}", response_class=HTMLResponse)
def history_page(request: Request, device_id: str):
    try:
        # Проверяем, что device_id есть в manager.sessions
        if device_id not in manager.sessions:
            return PlainTextResponse(f"Device {device_id} not found", status_code=404)
        scrs = get_latest_screenshots(device_id, 30)
        return templates.TemplateResponse("history.html", {"request": request, "device_id": device_id, "screenshots": scrs})
    except Exception as e:
        tb = traceback.format_exc()
        return PlainTextResponse(f"[Ошибка history_page]\n{e}\n{tb}", status_code=500)

# --- JS/CSS и шаблоны будут обновлены для анимации и live-обновления --- 

@app.get("/screenshots/monitor/{filename}")
def get_monitor_screenshot(filename: str = FastAPIPath(...)):
    """Отдаёт мониторинговый скриншот из папки screenshots/monitor/"""
    file_path = MONITOR_SCREEN_DIR / filename
    if not file_path.exists():
        return PlainTextResponse("Monitor screenshot not found", status_code=404)
    return FileResponse(str(file_path), media_type="image/png") 