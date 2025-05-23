# -*- coding: utf-8 -*-

import asyncio
import subprocess
import time
import logging
import sys
import importlib
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, BarColumn, TimeRemainingColumn, TimeElapsedColumn, SpinnerColumn, TextColumn

# Параметры сканирования
REFRESH_INTERVAL = 10  # Обновление каждые 10 секунд (не используется в текущей версии)
PORT_RANGE = range(4000, 7000)  # Диапазон портов для подключения устройств
SEM_LIMIT = 500  # Лимит асинхронных подключений для оптимизации скорости

# Инициализация rich и logging
console = Console()
logging.basicConfig(filename="adb_monitor.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Словарь для отслеживания времени подключения устройств
device_connection_time = {}

def check_and_install_packages():
    """Проверка и установка необходимых пакетов."""
    required_packages = ['rich']
    for package in required_packages:
        try:
            importlib.import_module(package)
        except ImportError:
            console.print(f"[bold yellow]Установка пакета {package}...[/bold yellow]")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
            console.print(f"[bold green]Пакет {package} успешно установлен.[/bold green]")

def restart_adb_server():
    """Функция для перезапуска ADB сервера и инициализации подключения."""
    try:
        console.print("[bold yellow]Перезапуск ADB сервера (by NIFILIM1337) ...[/bold yellow]")
        subprocess.run(['adb', 'kill-server'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(['adb', 'start-server'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(1)  # Задержка для стабилизации ADB сервера
        logging.info("Перезапуск ADB сервера завершен.")
        console.print("[bold green]ADB сервер перезапущен.[/bold green]")
    except subprocess.CalledProcessError as e:
        logging.error(f"Ошибка при перезапуске ADB сервера: {e}")
        console.print("[bold red]Ошибка при перезапуске ADB сервера[/bold red]")

async def connect_to_port(port, sem, progress_task, progress):
    """Асинхронная функция подключения к порту и добавления успешного подключения в результат."""
    async with sem:  # Лимитируем число одновременных подключений
        command = f"adb connect 127.0.0.1:{port}"
        try:
            process = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await process.communicate()
            output = stdout.decode() + stderr.decode()
            if "connected" in output or "already connected" in output:
                return f"127.0.0.1:{port}"
        except Exception as e:
            logging.error(f"Ошибка при подключении к порту {port}: {e}")
        finally:
            # Обновление прогресса
            progress.update(progress_task, advance=1)

async def connect_to_ports():
    """Асинхронное подключение к каждому порту в указанном диапазоне и возврат списка подключённых устройств."""
    connected_devices = {}
    sem = asyncio.Semaphore(SEM_LIMIT)  # Ограничиваем количество одновременных подключений

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        "Сканировано портов: {task.completed}/{task.total}",
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        refresh_per_second=10,
    ) as progress:
        progress_task = progress.add_task("Сканирование портов", total=len(PORT_RANGE))

        # Асинхронно запускаем подключение к каждому порту
        tasks = [connect_to_port(port, sem, progress_task, progress) for port in PORT_RANGE]
        results = await asyncio.gather(*tasks)

        # Фильтруем только успешные подключения
        for device_id in results:
            if device_id:
                connected_devices[device_id] = "device"

    return connected_devices

def update_device_info_table(connected_devices):
    """Обновляет данные в таблице для отображения подключённых устройств."""
    current_time = time.time()
    table = Table(title="Мониторинг ADB-устройств", show_lines=True)
    table.add_column("Имя устройства", style="cyan", no_wrap=True)
    table.add_column("Статус", style="green")
    table.add_column("Время подключения", justify="right", style="magenta")

    # Заполнение таблицы подключёнными устройствами
    for device, status in connected_devices.items():
        if status == "device":
            if device not in device_connection_time:
                device_connection_time[device] = current_time
            connected_duration = time.time() - device_connection_time[device]
            table.add_row(device, status, f"{connected_duration:.2f} сек")
        else:
            table.add_row(device, status, "N/A")

    # Удаление старой таблицы и вывод новой
    console.clear()
    console.print(f"[bold yellow]Количество подключенных устройств: {len(connected_devices)}[/bold yellow]")
    console.print(table)

    # Запись результатов в файл scan.txt
    with open('devices.txt', 'w', encoding='utf-8') as f:
        f.write("Найденные устройства:\n")
        for device in connected_devices.keys():
            f.write(f"{device}\n")
    console.print("[green]Результаты сохранены в файл scan.txt[/green]")

async def monitor_devices():
    """Асинхронный мониторинг подключений ADB-устройств с обновлением каждые 10 секунд."""
    restart_adb_server()  # Перезапуск ADB сервера перед началом мониторинга
    connected_devices = await connect_to_ports()  # Асинхронное подключение ко всем портам

    # Обновляем таблицу после завершения сканирования всех портов
    update_device_info_table(connected_devices)

async def main():
    check_and_install_packages()  # Проверяем и устанавливаем зависимости
    try:
        while True:
            await monitor_devices()
            # Вывод команд для пользователя
            console.print("\nВыберите действие:\n[bold cyan]1.[/bold cyan] Сканировать еще раз\n[bold cyan]2.[/bold cyan] Выход")
            choice = input("Введите номер команды: ")

            if choice == "1":
                console.print("[bold green]Повторное сканирование...[/bold green]")
            elif choice == "2":
                console.print("[bold red]Выход из программы...[/bold red]")
                break
            else:
                console.print("[bold yellow]Неверная команда. Попробуйте снова.[/bold yellow]")
    except KeyboardInterrupt:
        console.print("\n[bold red]Сканирование прервано пользователем.[/bold red]")
    finally:
        # Обеспечиваем корректное завершение всех процессов
        await asyncio.sleep(0.1)
        sys.exit(0)

# Запуск асинхронного цикла
if __name__ == "__main__":
    asyncio.run(main())