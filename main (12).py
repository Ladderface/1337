#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обновлённый скрипт для управления ADB-устройствами с живым прогресс‑баром.

Изменения:
1. Подробное логирование с использованием Rich и записью crash.log при необработанных исключениях.
2. Компактный, обновляемый в реальном времени прогресс‑бар (одна строка на устройство) с индикатором и описанием этапа.
3. Гибкая настройка (ENABLED_STEPS) для включения/отключения отдельных этапов.
4. Сохранён исходный функционал (работа с ADB, детекция изображений, перезапуски, планировщик и фоновые процессы).
5. **Новый функционал (детектор бана):**  
   – Раз в 60 сек. проверяются все подключённые устройства на наличие бан‑изображения (бан-файл — ban.png).  
   – При обнаружении бан‑изображения (если для данного устройства за текущую дату ещё не фиксировался бан) выводится сообщение в консоль, делается скриншот (сохраняется в папку screenshots с именем "ip_порт_YYYY-MM-DD_HH-MM-SS.png") и в лог (файл ban_report.log) добавляется CSV‑запись вида:  
     `device,ban_datetime,screenshot_path`  
   – Запись бан‑события для одного устройства производится не чаще одного раза в день (информация хранится в файле ban_record.json).
6. Если какого‑либо изображения (шаблонов) нет в каталоге, бот не падает, а выводит сообщение об ошибке и продолжает работу.

Перед запуском установите необходимые пакеты:
    pip install rich opencv-python-headless numpy schedule
"""

import os
os.environ["OPENCV_LOG_LEVEL"] = "FATAL"

import sys
from pathlib import Path
import subprocess
import cv2
import numpy as np
import time
import multiprocessing
from multiprocessing import Lock, Value, Manager
import schedule
from datetime import datetime
import logging
from threading import Thread
import json  # Для работы с бан-записями
import random
import sqlite3
from contextlib import closing

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.traceback import install as rich_install
from typing import Optional, Tuple, Dict, Any, List

rich_install(show_locals=True)

# ==============================
# Глобальная конфигурация этапов (включение/отключение)
# ==============================
ENABLED_STEPS = {
    "click_image_1": True,
    "click_image_2": True,
    "click_image_3": True,
    "input_text": True,
    "click_image_4": True,
    "click_image_5": True,
    "click_image_6": True,
    "click_image_7": True,
    "click_image_8": True,
    "always_wait": True,
    "additional_click": True
}

# ==============================
# Настройки (конфигурация)
# ==============================
DEVICES_FILE = "devices.txt"

# Пути к шаблонным изображениям
TEMPLATE_IMAGE_1 = "tpl1729712561481.png"
TEMPLATE_IMAGE_2 = "tpl1729713570074.png"
TEMPLATE_IMAGE_3 = "tpl1729759399717.png"
TEMPLATE_IMAGE_4 = "tpl1729760259340.png"
TEMPLATE_IMAGE_5 = "tpl1729760963933.png"
TEMPLATE_IMAGE_6 = "tpl1729761655306.png"
TEMPLATE_IMAGE_7 = "tpl1729762328309.png"
TEMPLATE_IMAGE_REPEAT = "tpl1730041404533.png"
TEMPLATE_IMAGE_8 = "tpl1730957533790.png"

# Для постоянного ожидания
TEMPLATE_IMAGE_ALWAYS = "1337.png"
MATCH_THRESHOLD_ALWAYS = 0.8
MAX_ATTEMPTS_ALWAYS = 800
CLICK_DELAY_ALWAYS_SECONDS = 1

# Для дополнительного клика
ADDITIONAL_TEMPLATE_IMAGE = "tpl1730957533790.png"
ADDITIONAL_CLICK_COORDS = (834, 101)
ADDITIONAL_CLICK_DURATION = 1

MATCH_THRESHOLD = 0.8

# Новый путь к изображению бана
BAN_IMAGE = "ban.png"

# Задержки (сек)
CLICK_DELAY_SECONDS = 3
CLICK_DELAY_IMAGE_6_SECONDS = 3
DELAY_SECONDS = 6
ADDITIONAL_DELAY_SECONDS = 30
DELAY_IMAGE_6_SECONDS = 3
BATCH_START_INTERVAL = 45
START_DELAY_BETWEEN_DEVICES = 15
DELAY_BEFORE_CLICK_IMAGE_2 = 45
CHECK_DURATION_SECONDS = 9

MAX_ATTEMPTS_IMAGE_1 = 40
MAX_ATTEMPTS_IMAGE_2 = 40
MAX_ATTEMPTS_IMAGE_3 = 300
MAX_ATTEMPTS_IMAGE_4 = 15
MAX_ATTEMPTS_IMAGE_5 = 10
MAX_ATTEMPTS_IMAGE_6 = 30
MAX_ATTEMPTS_IMAGE_7 = 20
MAX_ATTEMPTS_IMAGE_8 = 20

MAX_RESTARTS = 3
BATCH_SIZE = 2
TEXT_TO_ENTER = "NaftaliN1337228"

ADB_COMMANDS = [
    ["adb", "-s", "{device}", "shell", "am", "force-stop", "com.br.top"],
    ["adb", "-s", "{device}", "shell", "monkey", "-p", "com.br.top", "-c", "android.intent.category.LAUNCHER", "1"],
    ["adb", "-s", "{device}", "shell", "am", "force-stop", "com.launcher.brgame"],
    ["adb", "-s", "{device}", "shell", "monkey", "-p", "com.launcher.brgame", "-c", "android.intent.category.LAUNCHER", "1"]
]

# ==============================
# Настройка логирования и консоли
# ==============================
def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

setup_logging()
logger = logging.getLogger(__name__)
console = Console()

try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass

# ==============================
# Глобальный обработчик исключений
# ==============================
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.error("Неотловленное исключение", exc_info=(exc_type, exc_value, exc_traceback))
    crash_log = Path("crash.log")
    with crash_log.open("w", encoding="utf-8") as f:
        f.write("Неотловленное исключение:\n")
        import traceback
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    console.print(Panel.fit("[bold red]Произошла ошибка! Подробности см. файл crash.log[/bold red]",
                             title="[bold yellow]Ошибка", border_style="red"))
    input("Нажмите Enter для выхода...")
    sys.exit(1)

sys.excepthook = handle_exception

# ==============================
# Функция обновления прогресса
# ==============================
def update_progress(progress_data: Dict[str, Any], device: str, current: int, description: str, total: int) -> None:
    progress_data[device] = {"current": current, "total": total, "description": description}

# ==============================
# Прогресс‑дашборд (одна строка на устройство)
# ==============================
def progress_dashboard(progress_data: Dict[str, Any]) -> None:
    from rich.progress import Progress, BarColumn, TextColumn
    task_mapping = {}
    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=20),
        TextColumn("{task.completed:>2}/{task.total}"),
        TextColumn("{task.fields[status]}")
    )
    with progress:
        while True:
            for device, data in progress_data.items():
                current = data.get("current", 0)
                total = data.get("total", 1)
                desc = data.get("description", "")
                status = f"{desc}"
                if device not in task_mapping:
                    task_id = progress.add_task(f"{device}", total=total, completed=current, status=status)
                    task_mapping[device] = task_id
                else:
                    task_id = task_mapping[device]
                    progress.update(task_id, completed=current, total=total, status=status)
            time.sleep(0.5)

# ==============================
# Функции для работы с ADB и изображениями (остальные функции остаются без изменений)
# ==============================
def run_adb_command(command: List[str]) -> Tuple[int, str, str]:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return -1, "", str(e)

def connect_to_device(device: str, print_lock: Lock) -> bool:
    if ':' in device:
        connect_command = ["adb", "connect", device]
        code, out, err = run_adb_command(connect_command)
        if code == 0 and ("connected" in out.lower() or "already connected" in out.lower()):
            with print_lock:
                logger.info(f"Подключено к устройству: {device}")
            return True
        else:
            with print_lock:
                logger.error(f"Не удалось подключиться к устройству {device}. Ошибка: {err}")
            return False
    else:
        return True

def disconnect_device(device: str, print_lock: Lock) -> None:
    disconnect_command = ["adb", "disconnect", device]
    code, out, err = run_adb_command(disconnect_command)
    if code == 0:
        with print_lock:
            logger.info(f"Отключено устройство: {device}")
    else:
        with print_lock:
            logger.error(f"Не удалось отключить устройство {device}. Ошибка: {err}")

def get_connected_devices(print_lock: Lock) -> List[str]:
    try:
        result = subprocess.run(["adb", "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        lines = result.stdout.strip().split('\n')
        devices = []
        for line in lines[1:]:
            if line.strip():
                parts = line.split('\t')
                if len(parts) == 2 and parts[1] == "device":
                    devices.append(parts[0])
        return devices
    except subprocess.CalledProcessError as e:
        with print_lock:
            logger.error("Ошибка при выполнении 'adb devices':\n%s", e.stderr)
        return []
    except FileNotFoundError:
        with print_lock:
            logger.error("ADB не найден. Убедитесь, что ADB установлен и добавлен в PATH.")
        sys.exit(1)

DB_PATH = 'adb_manager.db'

def save_screenshot_to_db(device_id: str, path: str):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS screenshots (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, path TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        c.execute('INSERT INTO screenshots (device_id, path) VALUES (?, ?)', (device_id, path))
        conn.commit()

def take_screenshot(device: str, screenshot_path: str, print_lock: Lock, max_retries: int = 3) -> bool:
    """
    Создаёт скриншот на устройстве с уникальным именем, скачивает его, проверяет валидность PNG, удаляет только свой файл.
    Делает несколько попыток при ошибках.
    """
    for attempt in range(1, max_retries + 1):
        remote_path = f"/storage/emulated/0/screenshot_{os.getpid()}_{int(time.time()*1000)}_{random.randint(1000,9999)}.png"
        code, out, err = run_adb_command(["adb", "-s", device, "shell", "screencap", "-p", remote_path])
        if code != 0:
            with print_lock:
                logger.error(f"[{device}] Ошибка screencap (попытка {attempt}): {err} (stdout: {out})")
            time.sleep(0.5)
            continue
        time.sleep(0.3)
        code, out, err = run_adb_command(["adb", "-s", device, "shell", "ls", "-l", remote_path])
        if code != 0 or "No such file" in out or "No such file" in err:
            with print_lock:
                logger.error(f"[{device}] Скриншот не найден после screencap (попытка {attempt}): {err} (stdout: {out})")
            time.sleep(0.5)
            continue
        code, out, err = run_adb_command(["adb", "-s", device, "pull", remote_path, screenshot_path])
        if code != 0:
            with print_lock:
                logger.error(f"[{device}] Ошибка pull скриншота (попытка {attempt}): {err} (stdout: {out})")
            time.sleep(0.5)
            continue
        run_adb_command(["adb", "-s", device, "shell", "rm", remote_path])
        # Проверка размера и сигнатуры PNG
        if not os.path.exists(screenshot_path) or os.path.getsize(screenshot_path) < 1000:
            with print_lock:
                logger.error(f"[{device}] Локальный файл скриншота слишком мал или не создан (попытка {attempt})")
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
            time.sleep(0.5)
            continue
        with open(screenshot_path, "rb") as f:
            sig = f.read(8)
            if sig != b'\x89PNG\r\n\x1a\n':
                with print_lock:
                    logger.error(f"[{device}] Локальный файл скриншота не PNG (попытка {attempt})")
                os.remove(screenshot_path)
                time.sleep(0.5)
                continue
        # --- Сохраняем успешный скриншот в БД ---
        try:
            save_screenshot_to_db(device, screenshot_path)
        except Exception as e:
            with print_lock:
                logger.error(f"[{device}] Ошибка при сохранении скриншота в БД: {e}")
        return True
    with print_lock:
        logger.error(f"[{device}] Не удалось получить скриншот после {max_retries} попыток.")
    return False

def find_image_on_screen(screenshot_path: str, template_path: str, print_lock: Lock, threshold: float = MATCH_THRESHOLD) -> Optional[Tuple[int, int]]:
    # Проверка валидности PNG
    if not os.path.exists(template_path):
        with print_lock:
            logger.error(f"Шаблонное изображение {template_path} не найдено!")
        return None
    if not os.path.exists(screenshot_path) or os.path.getsize(screenshot_path) < 1000:
        with print_lock:
            logger.error(f"Скриншот {screenshot_path} невалиден или слишком мал! Размер: {os.path.getsize(screenshot_path) if os.path.exists(screenshot_path) else 0}")
        return None
    with open(screenshot_path, "rb") as f:
        sig = f.read(8)
        if sig != b'\x89PNG\r\n\x1a\n':
            with print_lock:
                logger.error(f"Скриншот {screenshot_path} не PNG! Сигнатура: {sig}")
            return None
    screenshot = cv2.imread(screenshot_path, cv2.IMREAD_COLOR)
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if screenshot is None or template is None:
        with print_lock:
            logger.error(f"Ошибка чтения скриншота или шаблона: {screenshot_path}, {template_path}")
        return None
    screenshot_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    w, h = template_gray.shape[::-1]
    res = cv2.matchTemplate(screenshot_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    loc = np.where(res >= threshold)
    for pt in zip(*loc[::-1]):
        center_x = pt[0] + w // 2
        center_y = pt[1] + h // 2
        return (center_x, center_y)
    return None

def capture_and_find_image(device: str, template_path: str, print_lock: Lock, threshold: float = MATCH_THRESHOLD, suffix: str = "capture") -> Optional[Tuple[int, int]]:
    # Уникальное имя для локального скриншота
    screenshot_path = f"screenshot_{device}_{suffix}_{os.getpid()}_{int(time.time()*1000)}_{random.randint(1000,9999)}.png"
    coords = None
    if take_screenshot(device, screenshot_path, print_lock):
        coords = find_image_on_screen(screenshot_path, template_path, print_lock, threshold)
    if os.path.exists(screenshot_path):
        os.remove(screenshot_path)
    return coords

def click_on_screen(device: str, x: int, y: int, print_lock: Lock) -> bool:
    code, out, err = run_adb_command(["adb", "-s", device, "shell", "input", "tap", str(x), str(y)])
    if code != 0:
        with print_lock:
            logger.error(f"Ошибка при отправке клика на устройстве {device}: {err}")
        return False
    return True

def click_and_hold(device: str, x: int, y: int, duration: float, print_lock: Lock) -> bool:
    duration_ms = int(duration * 1000)
    code, out, err = run_adb_command(["adb", "-s", device, "shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)])
    if code != 0:
        with print_lock:
            logger.error(f"Ошибка при выполнении длительного клика на устройстве {device}: {err}")
        return False
    return True

def input_text(device: str, text: str, print_lock: Lock) -> bool:
    formatted_text = text.replace(' ', '%s')
    code, out, err = run_adb_command(["adb", "-s", device, "shell", "input", "text", formatted_text])
    if code != 0:
        with print_lock:
            logger.error(f"Ошибка при вводе текста на устройстве {device}: {err}")
        return False
    return True

def clear_input_field(device: str, print_lock: Lock, times: int = 10) -> None:
    for _ in range(times):
        run_adb_command(["adb", "-s", device, "shell", "input", "keyevent", "67"])
    with print_lock:
        logger.info(f"[{device}] Поле ввода очищено (Backspace отправлен {times} раз).")

def press_enter_key(device: str, print_lock: Lock) -> bool:
    code, out, err = run_adb_command(["adb", "-s", device, "shell", "input", "keyevent", "66"])
    if code != 0:
        with print_lock:
            logger.error(f"Ошибка при нажатии Enter на устройстве {device}: {err}")
        return False
    return True

def wait_for_image(device: str, template_path: str, print_lock: Lock, timeout: int = 10, interval: int = 1, threshold: float = MATCH_THRESHOLD) -> Tuple[bool, Optional[Tuple[int, int]]]:
    start_time = time.time()
    while time.time() - start_time < timeout:
        coords = capture_and_find_image(device, template_path, print_lock, threshold)
        if coords:
            return True, coords
        time.sleep(interval)
    return False, None

def find_and_click(device: str, screenshot_suffix: str, template_image: str, device_info: Dict[str, Any], key: str, print_lock: Lock, max_attempts: int = 1, delay_between_attempts: int = DELAY_SECONDS, click_delay: int = CLICK_DELAY_SECONDS) -> bool:
    image_found = False
    attempts = 0
    while not image_found and attempts < max_attempts:
        coords = capture_and_find_image(device, template_image, print_lock, threshold=MATCH_THRESHOLD, suffix=f"{screenshot_suffix}_{attempts}")
        if coords:
            x, y = coords
            time.sleep(click_delay)
            if click_on_screen(device, x, y, print_lock):
                device_info[key] = f"Клик выполнен по координатам ({x}, {y})"
                image_found = True
                with print_lock:
                    logger.info(f"[{device}] {key.replace('_', ' ').capitalize()} найдено и кликнуто.")
            else:
                device_info[f"{key}_error"] = f"Не удалось выполнить клик по {key.replace('_', ' ')}"
        else:
            attempts += 1
            with print_lock:
                logger.info(f"[{device}] {key.replace('_', ' ').capitalize()} не найдено. Попытка {attempts}/{max_attempts} через {delay_between_attempts} сек.")
            if attempts < max_attempts:
                time.sleep(delay_between_attempts)
    return image_found

def find_image(device: str, screenshot_suffix: str, template_image: str, device_info: Dict[str, Any], key: str, print_lock: Lock, max_attempts: int = 1, delay_between_attempts: int = DELAY_SECONDS) -> Tuple[bool, Optional[Tuple[int, int]]]:
    image_found = False
    match_coords = None
    attempts = 0
    while not image_found and attempts < max_attempts:
        coords = capture_and_find_image(device, template_image, print_lock, threshold=MATCH_THRESHOLD, suffix=f"{screenshot_suffix}_{attempts}")
        if coords:
            match_coords = coords
            device_info[key] = f"Изображение найдено по координатам ({coords[0]}, {coords[1]})"
            image_found = True
            with print_lock:
                logger.info(f"[{device}] {key.replace('_', ' ').capitalize()} найдено.")
        else:
            attempts += 1
            with print_lock:
                logger.info(f"[{device}] {key.replace('_', ' ').capitalize()} не найдено. Попытка {attempts}/{max_attempts} через {delay_between_attempts} сек.")
            if attempts < max_attempts:
                time.sleep(delay_between_attempts)
    return image_found, match_coords

def always_wait_and_click(device: str, template_image: str, device_info: Dict[str, Any], print_lock: Lock) -> None:
    if not ENABLED_STEPS.get("always_wait", True):
        with print_lock:
            logger.info(f"[{device}] Этап always_wait отключён.")
        return
    attempts = 0
    while attempts < MAX_ATTEMPTS_ALWAYS:
        coords = capture_and_find_image(device, template_image, print_lock, threshold=MATCH_THRESHOLD_ALWAYS, suffix=f"always_{attempts}")
        if coords:
            x, y = coords
            with print_lock:
                logger.info(f"[{device}] Найдено изображение {template_image} по координатам ({x}, {y}). Нажимаю через {CLICK_DELAY_ALWAYS_SECONDS} сек.")
            time.sleep(CLICK_DELAY_ALWAYS_SECONDS)
            if click_on_screen(device, x, y, print_lock):
                device_info["click_always_image"] = f"Клик выполнен по координатам ({x}, {y})"
                with print_lock:
                    logger.info(f"[{device}] Клик по изображению {template_image} выполнен.")
                time.sleep(CHECK_DURATION_SECONDS)
                remain_coords = capture_and_find_image(device, template_image, print_lock, threshold=MATCH_THRESHOLD_ALWAYS, suffix=f"always_check_{attempts}")
                if remain_coords:
                    attempts += 1
                    with print_lock:
                        logger.info(f"[{device}] Изображение {template_image} осталось. Повтор {attempts}/{MAX_ATTEMPTS_ALWAYS}.")
                    continue
            else:
                device_info["click_always_image_error"] = f"Не удалось кликнуть по координатам ({x}, {y})"
            break
        else:
            with print_lock:
                logger.info(f"[{device}] Изображение {template_image} не найдено (попытка {attempts + 1}).")
            break
        attempts += 1

def additional_click_function(device: str, template_image: str, coords: Tuple[int, int], duration: float, device_info: Dict[str, Any], print_lock: Lock) -> None:
    if not ENABLED_STEPS.get("additional_click", True):
        with print_lock:
            logger.info(f"[{device}] Этап additional_click отключён.")
        return
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        found_coords = capture_and_find_image(device, template_image, print_lock, threshold=MATCH_THRESHOLD, suffix=f"additional_click_{attempt}")
        if found_coords:
            with print_lock:
                logger.info(f"[{device}] Найдено дополнительное изображение {template_image} (попытка {attempt}). Кликаю по координатам {coords} на {duration} сек.")
            x, y = coords
            if click_and_hold(device, x, y, duration, print_lock):
                device_info["additional_click"] = f"Длительный клик выполнен по координатам ({x}, {y}) на {duration} сек."
                with print_lock:
                    logger.info(f"[{device}] Длительный клик по координатам ({x}, {y}) выполнен.")
                return
            else:
                device_info["additional_click_error"] = f"Не удалось выполнить длительный клик (попытка {attempt})."
        else:
            with print_lock:
                logger.info(f"[{device}] Дополнительное изображение {template_image} не найдено (попытка {attempt}).")
    if "additional_click" not in device_info:
        device_info["additional_click_error"] = f"Не удалось найти/кликнуть {template_image} после {max_retries} попыток."

def check_and_restart_if_needed(device: str, text_entered: bool, restart_count: int, max_restarts: int, print_lock: Lock, reason: str = "") -> bool:
    if not text_entered:
        if restart_count < max_restarts:
            with print_lock:
                logger.info(f"[{device}] {reason}. Перезапуск операций. Счётчик: {restart_count + 1}")
            return True
        else:
            with print_lock:
                logger.error(f"[{device}] {reason}. Достигнуто максимальное число перезапусков ({max_restarts}). Операции прекращены.")
            return False
    return False

def perform_adb_operations(
    device: str,
    template_image_1: str,
    template_image_2: str,
    template_image_3: str,
    template_image_4: str,
    template_image_5: str,
    template_image_6: str,
    template_image_7: str,
    template_image_8: str,
    text_to_enter: str,
    template_image_repeat: str,
    last_click_time: Value,
    lock: Lock,
    print_lock: Lock,
    restart_count: int = 0,
    progress_data: Dict[str, Any] = None
) -> Dict[str, Any]:
    results = {"device": device, "success": False, "details": [], "device_info": {}}
    steps = [
        ("click_image_1", "Click Image 1"),
        ("click_image_2", "Click Image 2"),
        ("click_image_3", "Click Image 3"),
        ("input_text", "Input Text"),
        ("click_image_4", "Click Image 4"),
        ("click_image_5", "Click Image 5"),
        ("click_image_6", "Click Image 6"),
        ("click_image_7", "Click Image 7"),
        ("click_image_8", "Click Image 8"),
        ("always_wait", "Always Wait"),
        ("additional_click", "Additional Click")
    ]
    # Фильтруем только включённые этапы
    steps = [step for step in steps if ENABLED_STEPS.get(step[0], True)]
    total_steps = len(steps)
    if progress_data is not None:
        update_progress(progress_data, device, 0, "Начало", total_steps)

    code, model_out, model_err = run_adb_command(["adb", "-s", device, "shell", "getprop", "ro.product.model"])
    code2, sdk_out, sdk_err = run_adb_command(["adb", "-s", device, "shell", "getprop", "ro.build.version.sdk"])
    device_model = model_out.strip() if model_out else "unknown_model"
    device_sdk = sdk_out.strip() if sdk_out else "unknown_sdk"
    results["device_info"]["device_model"] = device_model
    results["device_info"]["device_sdk"] = device_sdk

    check_command = ["adb", "-s", device, "get-state"]
    code, out, err = run_adb_command(check_command)
    results["details"].append({
        "command": " ".join(check_command),
        "returncode": code,
        "stdout": out,
        "stderr": err
    })
    if code != 0 or out.lower() != "device":
        with print_lock:
            logger.error(f"[{device}] Устройство не в состоянии 'device'. Код: {code}, Вывод: {out}, Ошибка: {err}")
        results["device_info"]["connection_error"] = f"Устройство не подключено или не в состоянии 'device'. Код: {code}, Ошибка: {err}"
        return results

    for cmd in ADB_COMMANDS:
        formatted_cmd = [part.replace("{device}", device) for part in cmd]
        c_code, c_out, c_err = run_adb_command(formatted_cmd)
        results["details"].append({
            "command": " ".join(formatted_cmd),
            "returncode": c_code,
            "stdout": c_out,
            "stderr": c_err
        })
        if c_code == 0:
            if "am force-stop" in " ".join(formatted_cmd):
                app_package = formatted_cmd[-1]
                results["device_info"][f"force_stop_{app_package}"] = "Успешно выполнено"
            elif "monkey" in " ".join(formatted_cmd):
                app_package = formatted_cmd[2].split(":")[-1]
                results["device_info"][f"start_app_{app_package}"] = "Успешно выполнено"
        else:
            if "am force-stop" in " ".join(formatted_cmd):
                app_package = formatted_cmd[-1]
                results["device_info"][f"force_stop_{app_package}_error"] = c_err
            elif "monkey" in " ".join(formatted_cmd):
                app_package = formatted_cmd[2].split(":")[-1]
                results["device_info"][f"start_app_{app_package}_error"] = c_err

    all_apps_success = True
    for app in ["com.br.top", "com.launcher.brgame"]:
        if f"force_stop_{app}_error" in results["device_info"] or f"start_app_{app}_error" in results["device_info"]:
            all_apps_success = False
            break
    if all_apps_success:
        results["device_info"]["restart_app"] = "Успешно выполнено"
    else:
        results["device_info"]["restart_app_error"] = "Не удалось перезапустить одно или оба приложения"

    time.sleep(DELAY_SECONDS)
    if ENABLED_STEPS.get("click_image_1", True):
        if not find_and_click(device, "1", template_image_1, results["device_info"], "click_image_1", print_lock, max_attempts=MAX_ATTEMPTS_IMAGE_1):
            results["device_info"]["click_image_1_error"] = f"Не удалось найти/кликнуть по первому изображению после {MAX_ATTEMPTS_IMAGE_1} попыток."
        if progress_data is not None:
            update_progress(progress_data, device, 1, "Click Image 1", total_steps)

    with lock:
        current_time = time.time()
        elapsed = current_time - last_click_time.value
        if elapsed < DELAY_BEFORE_CLICK_IMAGE_2:
            wait_time = DELAY_BEFORE_CLICK_IMAGE_2 - elapsed
            with print_lock:
                logger.info(f"[{device}] Ожидание {wait_time:.2f} сек перед кликом по второму изображению.")
            time.sleep(wait_time)
        last_click_time.value = time.time()

    if ENABLED_STEPS.get("click_image_2", True):
        found_click2 = find_and_click(device, "2", template_image_2, results["device_info"], "click_image_2", print_lock, max_attempts=MAX_ATTEMPTS_IMAGE_2)
        if not found_click2:
            results["device_info"]["click_image_2_error"] = f"Не удалось найти/кликнуть по второму изображению после {MAX_ATTEMPTS_IMAGE_2} попыток."
            with print_lock:
                logger.error(f"[{device}] Не удалось найти {template_image_2}. Перезапуск.")
            if restart_count < MAX_RESTARTS:
                return perform_adb_operations(device, template_image_1, template_image_2, template_image_3, template_image_4, template_image_5, template_image_6, template_image_7, template_image_8, text_to_enter, template_image_repeat, last_click_time, lock, print_lock, restart_count=restart_count + 1, progress_data=progress_data)
            else:
                with print_lock:
                    logger.error(f"[{device}] Максимальное число перезапусков достигнуто.")
        else:
            if progress_data is not None:
                update_progress(progress_data, device, 2, "Click Image 2", total_steps)
            time.sleep(ADDITIONAL_DELAY_SECONDS)
            repeat_coords = capture_and_find_image(device, template_image_repeat, print_lock, threshold=MATCH_THRESHOLD, suffix="repeat")
            if repeat_coords:
                with print_lock:
                    logger.info(f"[{device}] Обнаружено изображение повторного запуска. Перезапуск.")
                if restart_count < MAX_RESTARTS:
                    return perform_adb_operations(device, template_image_1, template_image_2, template_image_3, template_image_4, template_image_5, template_image_6, template_image_7, template_image_8, text_to_enter, template_image_repeat, last_click_time, lock, print_lock, restart_count=restart_count + 1, progress_data=progress_data)
                else:
                    with print_lock:
                        logger.error(f"[{device}] Максимальное число повторных запусков достигнуто.")
            else:
                with print_lock:
                    logger.info(f"[{device}] Изображение повторного запуска не найдено.")

    if ENABLED_STEPS.get("click_image_3", True):
        if not find_and_click(device, "3", template_image_3, results["device_info"], "click_image_3", print_lock, max_attempts=MAX_ATTEMPTS_IMAGE_3):
            results["device_info"]["click_image_3_error"] = f"Не удалось найти/кликнуть по третьему изображению после {MAX_ATTEMPTS_IMAGE_3} попыток."
        if progress_data is not None:
            update_progress(progress_data, device, 3, "Click Image 3", total_steps)

    time.sleep(DELAY_SECONDS)

    if ENABLED_STEPS.get("input_text", True):
        text_entered = False
        attempt_input_text = 0
        MAX_TEXT_INPUT_ATTEMPTS = 5
        while not text_entered and attempt_input_text < MAX_TEXT_INPUT_ATTEMPTS:
            attempt_input_text += 1
            clear_input_field(device, print_lock, times=10)
            time.sleep(1)
            if input_text(device, text_to_enter, print_lock):
                with print_lock:
                    logger.info(f"[{device}] Текст '{text_to_enter}' отправлен команде input.")
                press_enter_key(device, print_lock)
                results["device_info"]["input_text"] = f"Текст '{text_to_enter}' успешно введён (попытка {attempt_input_text})."
                text_entered = True
                with print_lock:
                    logger.info(f"[{device}] Текст '{text_to_enter}' успешно введён (попытка {attempt_input_text}).")
            else:
                results["device_info"]["input_text_error"] = f"Не удалось ввести текст (попытка {attempt_input_text})."
                with print_lock:
                    logger.error(f"[{device}] Не удалось ввести текст. Повтор через {DELAY_SECONDS} сек.")
                time.sleep(DELAY_SECONDS)
        if check_and_restart_if_needed(device, text_entered, restart_count, MAX_RESTARTS, print_lock, reason="Текст не введён"):
            return perform_adb_operations(device, template_image_1, template_image_2, template_image_3, template_image_4, template_image_5, template_image_6, template_image_7, template_image_8, text_to_enter, template_image_repeat, last_click_time, lock, print_lock, restart_count=restart_count + 1, progress_data=progress_data)
        if progress_data is not None:
            update_progress(progress_data, device, 4, "Input Text", total_steps)

    if ENABLED_STEPS.get("click_image_4", True):
        if not find_and_click(device, "4", template_image_4, results["device_info"], "click_image_4", print_lock, max_attempts=MAX_ATTEMPTS_IMAGE_4):
            results["device_info"]["click_image_4_error"] = f"Не удалось найти/кликнуть по четвёртому изображению после {MAX_ATTEMPTS_IMAGE_4} попыток."
            press_enter_key(device, print_lock)
        if progress_data is not None:
            update_progress(progress_data, device, 5, "Click Image 4", total_steps)

    if ENABLED_STEPS.get("click_image_5", True):
        found_image_5, coords_image_5 = find_image(device, "5", template_image_5, results["device_info"], "found_image_5", print_lock, max_attempts=MAX_ATTEMPTS_IMAGE_5)
        if not found_image_5:
            results["device_info"]["found_image_5_error"] = f"Пятое изображение не найдено после {MAX_ATTEMPTS_IMAGE_5} попыток."
        else:
            x_coord = 320
            y_coord = 320
            if click_and_hold(device, x_coord, y_coord, duration=1, print_lock=print_lock):
                results["device_info"]["click_additional_action"] = f"Клик по координатам ({x_coord}, {y_coord}) с удержанием 1 сек выполнен."
                with print_lock:
                    logger.info(f"[{device}] Клик по координатам ({x_coord}, {y_coord}) с удержанием 1 сек выполнен.")
            else:
                results["device_info"]["click_additional_action_error"] = f"Не удалось выполнить клик по координатам ({x_coord}, {y_coord})."
                with print_lock:
                    logger.error(f"[{device}] Не удалось выполнить клик по координатам ({x_coord}, {y_coord}).")
            time.sleep(5)
            if coords_image_5 is not None:
                x5, y5 = coords_image_5
                time.sleep(CLICK_DELAY_SECONDS)
                if click_on_screen(device, x5, y5, print_lock):
                    results["device_info"]["click_image_5"] = f"Клик выполнен по координатам ({x5}, {y5})."
                    with print_lock:
                        logger.info(f"[{device}] Click image 5 найдено и кликнуто.")
                    screenshot_suffix_8 = "8"
                    image_found_8 = False
                    attempts_8 = 0
                    while not image_found_8 and attempts_8 < MAX_ATTEMPTS_IMAGE_8:
                        coords_8 = capture_and_find_image(device, template_image_8, print_lock, threshold=MATCH_THRESHOLD, suffix=f"{screenshot_suffix_8}_{attempts_8}")
                        if coords_8:
                            x8, y8 = coords_8
                            time.sleep(CLICK_DELAY_SECONDS)
                            if click_on_screen(device, x8, y8, print_lock):
                                results["device_info"]["click_image_8"] = f"Клик выполнен по координатам ({x8}, {y8})."
                                image_found_8 = True
                                with print_lock:
                                    logger.info(f"[{device}] Клик по дополнительному изображению 8 выполнен.")
                            else:
                                results["device_info"]["click_image_8_error"] = "Не удалось выполнить клик по дополнительному изображению 8."
                        else:
                            attempts_8 += 1
                            with print_lock:
                                logger.info(f"[{device}] Дополнительное изображение 8 не найдено. Попытка {attempts_8}/{MAX_ATTEMPTS_IMAGE_8} через 4 сек.")
                        if not image_found_8 and attempts_8 < MAX_ATTEMPTS_IMAGE_8:
                            time.sleep(4)
                    if not image_found_8:
                        results["device_info"]["click_image_8_error"] = f"Дополнительное изображение 8 не найдено после {MAX_ATTEMPTS_IMAGE_8} попыток."
                else:
                    results["device_info"]["click_image_5_error"] = "Не удалось кликнуть по пятому изображению."
                    with print_lock:
                        logger.error(f"[{device}] Не удалось кликнуть по пятому изображению.")
            else:
                results["device_info"]["click_image_5_error"] = "Координаты пятого изображения отсутствуют."
                with print_lock:
                    logger.error(f"[{device}] Координаты пятого изображения отсутствуют.")
        if progress_data is not None:
            update_progress(progress_data, device, 6, "Click Image 5", total_steps)

    if ENABLED_STEPS.get("click_image_6", True):
        find_and_click(device, "6", template_image_6, results["device_info"], "click_image_6", print_lock, max_attempts=MAX_ATTEMPTS_IMAGE_6, delay_between_attempts=DELAY_IMAGE_6_SECONDS, click_delay=CLICK_DELAY_IMAGE_6_SECONDS)
        if progress_data is not None:
            update_progress(progress_data, device, 7, "Click Image 6", total_steps)

    if ENABLED_STEPS.get("click_image_7", True):
        find_and_click(device, "7", template_image_7, results["device_info"], "click_image_7", print_lock, max_attempts=MAX_ATTEMPTS_IMAGE_7)
        if progress_data is not None:
            update_progress(progress_data, device, 8, "Click Image 7", total_steps)

    if ENABLED_STEPS.get("always_wait", True):
        try:
            always_wait_and_click(device, TEMPLATE_IMAGE_ALWAYS, results["device_info"], print_lock)
            if progress_data is not None:
                update_progress(progress_data, device, 9, "Always Wait", total_steps)
        except Exception as e:
            with print_lock:
                logger.error(f"[{device}] Ошибка в always_wait_and_click: {e}")
            results["device_info"]["always_wait_and_click_error"] = str(e)

    if ENABLED_STEPS.get("additional_click", True):
        try:
            additional_click_function(device, ADDITIONAL_TEMPLATE_IMAGE, ADDITIONAL_CLICK_COORDS, ADDITIONAL_CLICK_DURATION, results["device_info"], print_lock)
            if progress_data is not None:
                update_progress(progress_data, device, 10, "Additional Click", total_steps)
        except Exception as e:
            with print_lock:
                logger.error(f"[{device}] Ошибка в additional_click_function: {e}")
            results["device_info"]["additional_click_function_error"] = str(e)

    required_keys = [
        "click_image_1",
        "click_image_2",
        "click_image_3",
        "input_text",
        "click_image_4",
        "click_image_5",
        "click_image_6",
        "click_image_7",
        "click_image_8",
        "restart_app",
        "click_always_image",
        "additional_click"
    ]
    if all(key in results["device_info"] for key in required_keys):
        results["success"] = True

    if progress_data is not None:
        update_progress(progress_data, device, total_steps, "Завершено", total_steps)

    return results

def check_adb_installed(print_lock: Lock) -> None:
    try:
        result = subprocess.run(
            ["adb", "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        adb_version = result.stdout.strip().split('\n')[0]
        with print_lock:
            logger.info(f"Найдена версия ADB: {adb_version}\n")
    except subprocess.CalledProcessError as e:
        with print_lock:
            logger.error("Ошибка при выполнении команды ADB:\n%s", e.stderr)
        sys.exit(1)
    except FileNotFoundError:
        with print_lock:
            logger.error("ADB не найден. Убедитесь, что ADB установлен и добавлен в PATH.")
        sys.exit(1)

def process_device(device: str, template_image_paths: Dict[str, Path], text_to_enter: str, logs_dir: Path, last_click_time: Value, lock: Lock, print_lock: Lock, progress_data: Dict[str, Any]) -> None:
    try:
        result = perform_adb_operations(
            device,
            str(template_image_paths.get("1", "")),
            str(template_image_paths.get("2", "")),
            str(template_image_paths.get("3", "")),
            str(template_image_paths.get("4", "")),
            str(template_image_paths.get("5", "")),
            str(template_image_paths.get("6", "")),
            str(template_image_paths.get("7", "")),
            str(template_image_paths.get("8", "")),
            text_to_enter,
            str(template_image_paths.get("repeat", "")),
            last_click_time=last_click_time,
            lock=lock,
            print_lock=print_lock,
            restart_count=0,
            progress_data=progress_data
        )
    except Exception as e:
        with print_lock:
            logger.error(f"[{device}] Неожиданная ошибка: {e}")
        result = {
            "device": device,
            "success": False,
            "details": [],
            "device_info": {"unexpected_error": str(e)}
        }

    log_file = logs_dir / f"{device}.log"
    try:
        with open(log_file, "a", encoding="utf-8") as log:
            log.write(f"--- Запуск в {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            for detail in result.get("details", []):
                log.write(f"Команда: {detail.get('command', 'N/A')}\n")
                log.write(f"Код завершения: {detail.get('returncode', 'N/A')}\n")
                log.write(f"STDOUT:\n{detail.get('stdout', '')}\n")
                log.write(f"STDERR:\n{detail.get('stderr', '')}\n")
                log.write("-" * 40 + "\n")
            log.write("\n")
            if result.get("success", False):
                log.write(f"Устройство {device} успешно обработано.\n")
                for key, value in result.get("device_info", {}).items():
                    log.write(f"{key}: {value}\n")
            else:
                log.write(f"Обработка устройства {device} завершилась с ошибкой.\n")
                for key, value in result.get("device_info", {}).items():
                    log.write(f"{key}: {value}\n")
            log.write("=" * 80 + "\n\n")
    except Exception as e:
        with print_lock:
            logger.error(f"[{device}] Ошибка при записи в лог-файл: {e}")

    if result.get("success", False):
        with print_lock:
            logger.info(f"[SUCCESS] Устройство {device}: операции успешно выполнены.")
    else:
        with print_lock:
            logger.error(f"[FAILED] Устройство {device}: не все операции выполнены. См. лог {log_file}")

def execute_scheduled_process(template_image_paths: Dict[str, Path], text_to_enter: str, logs_dir: Path, last_click_time: Value, lock: Lock, print_lock: Lock, progress_data: Dict[str, Any]) -> None:
    devices_in_file = []
    devices_file_path = Path(DEVICES_FILE)
    if devices_file_path.is_file():
        with open(devices_file_path, "r", encoding="utf-8") as f:
            devices_in_file = [line.strip() for line in f if line.strip()]
    else:
        with print_lock:
            logger.error(f"Файл {DEVICES_FILE} не найден!")
        return

    for dev in devices_in_file:
        disconnect_device(dev, print_lock)

    connected_devices = []
    for dev in devices_in_file:
        if connect_to_device(dev, print_lock):
            connected_devices.append(dev)

    if not connected_devices:
        with print_lock:
            logger.error("Нет подключённых устройств для обработки.")
        return

    current_devices = get_connected_devices(print_lock)
    devices_to_process = [dev for dev in connected_devices if dev in current_devices]

    if not devices_to_process:
        with print_lock:
            logger.error("Нет устройств для обработки после проверки подключения.")
        return

    with print_lock:
        logger.info(f"Начало обработки устройств в {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    batches = [devices_to_process[i:i + BATCH_SIZE] for i in range(0, len(devices_to_process), BATCH_SIZE)]
    total_batches = len(batches)

    with print_lock:
        logger.info(f"Всего пакетов: {total_batches}")

    for batch_index, batch_devices in enumerate(batches):
        with print_lock:
            logger.info(f"Запуск пакета {batch_index + 1}/{total_batches}: устройств в пакете - {len(batch_devices)}")
        processes = []
        for idx, dev in enumerate(batch_devices):
            p = multiprocessing.Process(
                target=process_device,
                args=(dev, template_image_paths, text_to_enter, logs_dir, last_click_time, lock, print_lock, progress_data),
                name=f"Process-{dev}"
            )
            p.start()
            processes.append(p)
            if START_DELAY_BETWEEN_DEVICES > 0 and idx < len(batch_devices) - 1:
                time.sleep(START_DELAY_BETWEEN_DEVICES)
        if batch_index < total_batches - 1:
            time.sleep(BATCH_START_INTERVAL)

def scheduler_func(template_image_paths: Dict[str, Path], text_to_enter: str, logs_dir: Path, last_click_time: Value, lock: Lock, print_lock: Lock, progress_data: Dict[str, Any]) -> None:
    global current_run_process
    current_run_process = None

    def job():
        global current_run_process
        new_process = multiprocessing.Process(
            target=execute_scheduled_process,
            args=(template_image_paths, text_to_enter, logs_dir, last_click_time, lock, print_lock, progress_data),
            name="Scheduled-Process"
        )
        new_process.start()
        current_run_process = new_process
        with print_lock:
            logger.info(f"Запущена новая задача по расписанию в {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")

    schedule.every().hour.at(":05").do(job)
    schedule.every().hour.at(":25").do(job)
    schedule.every().hour.at(":45").do(job)

    with print_lock:
        logger.info("Планировщик запущен. Скрипт будет выполняться в 05, 25 и 45 минут каждого часа.\n")

    while True:
        schedule.run_pending()
        time.sleep(1)

def progress_dashboard(progress_data: Dict[str, Any]) -> None:
    from rich.progress import Progress, BarColumn, TextColumn
    task_mapping = {}
    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=20),
        TextColumn("{task.completed:>2}/{task.total}"),
        TextColumn("{task.fields[status]}")
    )
    with progress:
        while True:
            for device, data in progress_data.items():
                current = data.get("current", 0)
                total = data.get("total", 1)
                desc = data.get("description", "")
                status = desc
                if device not in task_mapping:
                    task_id = progress.add_task(f"{device}", total=total, completed=current, status=status)
                    task_mapping[device] = task_id
                else:
                    task_id = task_mapping[device]
                    progress.update(task_id, completed=current, total=total, status=status)
            time.sleep(0.5)

def is_admin() -> bool:
    try:
        if os.name == 'nt':
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin()
        else:
            return os.geteuid() == 0
    except Exception:
        return False

def run_as_admin() -> None:
    if os.name == 'nt':
        try:
            import ctypes
            python_exe = sys.executable
            script = os.path.abspath(sys.argv[0])
            params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
            ctypes.windll.shell32.ShellExecuteW(None, "runas", python_exe, f'"{script}" {params}', None, 1)
            sys.exit()
        except Exception as e:
            logger.error(f"Не удалось запустить скрипт с правами администратора: {e}")
            sys.exit(1)
    else:
        logger.error("Для запуска скрипта с правами администратора используйте sudo:")
        logger.error(f"sudo python3 {os.path.abspath(sys.argv[0])}")
        sys.exit(1)

def set_process_priority() -> None:
    if os.name == 'nt':
        try:
            import ctypes
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.kernel32.SetPriorityClass(handle, 0x00000080)
            logger.info("Установлен высокий приоритет процесса.")
        except Exception as e:
            logger.error(f"Не удалось установить высокий приоритет процесса: {e}")
    else:
        try:
            os.nice(-10)
            logger.info("Установлен высокий приоритет процесса (низкое значение nice).")
        except Exception as e:
            logger.error(f"Не удалось установить высокий приоритет процесса: {e}")

def background_image_clicker_8(print_lock: Lock) -> None:
    image_path = ADDITIONAL_TEMPLATE_IMAGE
    while True:
        devices = get_connected_devices(print_lock)
        for device in devices:
            coords = capture_and_find_image(device, image_path, print_lock, threshold=MATCH_THRESHOLD, suffix="bg8")
            if coords:
                x, y = coords
                with print_lock:
                    logger.info(f"[BG-8] На устройстве {device} найдено изображение {image_path} по координатам ({x}, {y}).")
                clicked = click_on_screen(device, x, y, print_lock)
                if clicked:
                    with print_lock:
                        logger.info(f"[BG-8] Клик по изображению {image_path} на устройстве {device} выполнен.")
                else:
                    with print_lock:
                        logger.error(f"[BG-8] Не удалось кликнуть по изображению {image_path} на устройстве {device}.")
        time.sleep(5)

# ==============================
# Новый фоновой процесс: детектор банов
# ==============================
def background_ban_detector(print_lock: Lock) -> None:
    """
    Раз в 60 секунд проверяет все подключённые устройства на наличие бан‑изображения (BAN_IMAGE).
    Если изображение обнаружено и для данного устройства за текущую дату ещё не зафиксирован бан,
    – выводит сообщение в консоль, делает скриншот (сохраняется в папку "screenshots") и записывает событие в лог-файл (ban_report.log) в CSV‑формате.
    Запись для одного устройства производится не чаще одного раза в день.
    """
    record_file = "ban_record.json"   # Файл для хранения последней даты фиксации бана для каждого устройства
    ban_log_file = "ban_report.log"     # Лог‑отчет (CSV: device,ban_datetime,screenshot_path)
    screenshots_dir = Path("screenshots")
    screenshots_dir.mkdir(exist_ok=True)
    try:
        with open(record_file, "r", encoding="utf-8") as f:
            ban_records = json.load(f)
    except Exception:
        ban_records = {}

    while True:
        devices = get_connected_devices(print_lock)
        current_date = datetime.now().strftime("%Y-%m-%d")
        for device in devices:
            coords = capture_and_find_image(device, BAN_IMAGE, print_lock, threshold=MATCH_THRESHOLD, suffix="ban")
            if coords:
                # Если бан уже зафиксирован сегодня для данного устройства, пропускаем запись
                if ban_records.get(device) == current_date:
                    with print_lock:
                        logger.info(f"[BAN DETECTOR] Для устройства {device} бан уже зафиксирован за {current_date}.")
                else:
                    ban_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    # Формируем имя файла скриншота: заменяем двоеточие на подчеркивание
                    screenshot_filename = f"{device.replace(':', '_')}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.png"
                    screenshot_path = screenshots_dir / screenshot_filename
                    if take_screenshot(device, str(screenshot_path), print_lock):
                        with print_lock:
                            logger.info(f"[BAN DETECTOR] Скриншот сохранён: {screenshot_path}")
                    else:
                        with print_lock:
                            logger.error(f"[BAN DETECTOR] Не удалось сохранить скриншот для {device}")
                    # Запись события в лог (CSV-формат: device,ban_datetime,screenshot_path)
                    entry = f"{device},{ban_time},{screenshot_path}\n"
                    with open(ban_log_file, "a", encoding="utf-8") as f:
                        f.write(entry)
                    # Обновляем запись для данного устройства и сохраняем в record_file (одностричный JSON)
                    ban_records[device] = current_date
                    with open(record_file, "w", encoding="utf-8") as f:
                        json.dump(ban_records, f, separators=(',', ':'))
                    with print_lock:
                        logger.warning(f"[BAN DETECTOR] BAN обнаружен на устройстве {device} в {ban_time}.")
        time.sleep(60)

def main() -> None:
    width = console.size.width
    console.print(Panel.fit(
        "[bold blue]ADB Manager[/bold blue]\n[green]Управление устройствами через ADB с красивым интерфейсом[/green]",
        title="[bold red]Добро пожаловать!",
        border_style="bright_magenta",
        width=width
    ))
    if not is_admin():
        run_as_admin()

    multiprocessing.set_start_method('spawn')

    print_lock = Lock()
    lock = Lock()
    last_click_time = Value('d', 0.0)

    manager = Manager()
    progress_data = manager.dict()

    set_process_priority()
    check_adb_installed(print_lock)

    devices_file_path = Path(DEVICES_FILE)
    if not devices_file_path.is_file():
        with print_lock:
            logger.error(f"Файл {DEVICES_FILE} не найден!")
        sys.exit(1)

    template_image_paths = {
        "1": Path(TEMPLATE_IMAGE_1),
        "2": Path(TEMPLATE_IMAGE_2),
        "3": Path(TEMPLATE_IMAGE_3),
        "4": Path(TEMPLATE_IMAGE_4),
        "5": Path(TEMPLATE_IMAGE_5),
        "6": Path(TEMPLATE_IMAGE_6),
        "7": Path(TEMPLATE_IMAGE_7),
        "8": Path(TEMPLATE_IMAGE_8),
        "repeat": Path(TEMPLATE_IMAGE_REPEAT),
        "always": Path(TEMPLATE_IMAGE_ALWAYS),
        "additional": Path(ADDITIONAL_TEMPLATE_IMAGE),
        "ban": Path(BAN_IMAGE)
    }
    # Если какого-либо шаблонного изображения нет – выводим ошибку, но не прерываем работу
    for key, path in template_image_paths.items():
        if not path.is_file():
            with print_lock:
                logger.error(f"Шаблонное изображение '{path}' (ключ: {key}) не найдено!")
            # Можно оставить запись в словаре – при попытке чтения cv2.imread вернется None, и шаг просто не выполнится

    with open(devices_file_path, "r", encoding="utf-8") as f:
        devices = [line.strip() for line in f if line.strip()]
    if not devices:
        with print_lock:
            logger.error(f"Файл {DEVICES_FILE} пуст или содержит только пустые строки.")
        sys.exit(1)
    with print_lock:
        logger.info(f"Найдено устройств в {DEVICES_FILE}: {len(devices)}")

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    dashboard_thread = Thread(target=progress_dashboard, args=(progress_data,), daemon=True)
    dashboard_thread.start()

    bg_process = multiprocessing.Process(
        target=background_image_clicker_8,
        args=(print_lock,),
        name="BG-Image-Clicker-8"
    )
    bg_process.daemon = True
    bg_process.start()
    
    # Запуск нового фонового процесса для детекции банов
    ban_detector_process = multiprocessing.Process(
        target=background_ban_detector,
        args=(print_lock,),
        name="BG-Ban-Detector"
    )
    ban_detector_process.daemon = True
    ban_detector_process.start()

    scheduler_func(template_image_paths, TEXT_TO_ENTER, logs_dir, last_click_time, lock, print_lock, progress_data)

if __name__ == "__main__":
    main()
