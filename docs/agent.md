# Agent (Клиент ADB Device Manager)

## Запуск агента

```bash
cd agent
python agent.py
```

## CLI-команды

- `python agent.py status` — вывести статус устройств, версию ADB, uptime, свободное место
- `python agent.py test` — выполнить тестовый цикл (скриншот, отправка, команды)

## Метаданные

С каждым скриншотом отправляются:

- Версия ADB
- Uptime устройства
- Свободное место на /data

## Watchdog

- Фоновый поток, который проверяет доступность ADB (`adb devices`)
- При сбоях перезапускает ADB (`adb kill-server`, `adb start-server`)
- Интервал проверки: 30 сек

## Автообновление агента

- Поддерживается команда `update_agent` с сервера (заглушка, требуется URL)
- После загрузки новой версии agent.py агент перезапускается автоматически

## Тесты

- Unit-тесты: `python -m unittest discover -s agent/tests`
- Покрытие: DeviceSession, ScenarioRunner, интеграция с mock ADB

## Обновление и откат

- Для обновления: используйте команду с сервера или вручную замените agent.py
- Для отката: восстановите предыдущую версию agent.py из бэкапа

## Диагностика

- Для проверки статуса: `python agent.py status`
- Для теста отправки: `python agent.py test`
- Для логов: смотрите консоль или добавьте лог-файл в setup_logging

## Пример конфига (config_agent.yaml)

```yaml
server_url: "http://localhost:8000"
api_key: "testkey"
server_id: "server-01"
devices:
  - id: "127.0.0.1:5555"
    enabled: true
    window: "main"
    interval: 60
screenshot_dir: screenshots
log_level: INFO
```

## Мини-гайд по запуску агента

1. Установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```

2. Настройте config_agent.yaml
3. Запустите сервер (см. docs/central_server.md)
4. Запустите агента:

   ```bash
   cd agent
   python agent.py
   ```

5. Для проверки статуса:

   ```bash
   python agent.py status
   ```

6. Для теста отправки:

   ```bash
   python agent.py test
   ```

7. Для обновления — используйте команду update_agent с сервера или вручную замените agent.py

## last.png и быстрый мониторинг

- Агент автоматически снимает скриншоты и отправляет только новые (по хэшу).
- Сервер сохраняет каждый скриншот в историю и как last.png (перезапись).
- Быстрый просмотр last.png для каждого устройства/окна через web-интерфейс и API.

### REST API

- `POST /upload_screenshot` — загрузка скриншота, сервер сохраняет last.png
- `GET /download_last/{server_id}/{window}/{device_id}` — получить последний скриншот (last.png)
