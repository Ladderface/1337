# 📱 ADB Device Manager — Система управления и мониторинга Android-устройств

<details>
<summary>📑 Оглавление</summary>

- [Введение и архитектура](#введение-и-архитектура)
- [Быстрый старт](#быстрый-старт)
- [Структура проекта и файлов](#структура-проекта-и-файлов)
- [Конфигурация](#конфигурация)
- [Центральный сервер](#центральный-сервер)
- [Агент](#агент)
- [Масштабирование и отказоустойчивость](#масштабирование-и-отказоустойчивость)
- [Расширение: плагины, новые команды, интеграции](#расширение)
- [UI/UX: кастомизация, добавление страниц, фильтров](#uiux)
- [Безопасность и best practices](#безопасность)
- [FAQ](#faq)
- [Roadmap](#roadmap)
- [Ссылки](#ссылки)
- [Веб-интерфейс: аналитика и графики](#аналитика)
- [Автоудаление и архивация](#retention)
- [Автоматический запуск и деплой](#автоматический-запуск-и-деплой)
- [Автоматизация интеграционных тестов](#автоматизация-интеграционных-тестов)
- [CI/CD](#ci-cd)
- [Ролевая модель и права доступа](#ролевая-модель-и-права-доступа)

</details>

---

# Введение и архитектура <a name="введение-и-архитектура"></a>

**ADB Device Manager** — это масштабируемая система для автоматизации, мониторинга и управления Android-устройствами и эмуляторами через ADB. Она включает:

- Централизованный сервер (FastAPI + SQLite + Jinja2 UI)
- Множество агентов (по одному на сервер/хост с эмуляторами)
- REST API для обмена скриншотами, логами, командами
- Веб-интерфейс для мониторинга, фильтрации, истории, отправки команд
- Интеграции (Telegram, Google Sheets, Webhook, нейросети и др.)
- Гибкая конфигурация, поддержка сценариев, расширяемость

**Архитектурная схема:**

```
[ Android-эмуляторы/устройства ]
         | (ADB)
      [ Agent (Python) ]  <--- config_agent.yaml
         | (REST API)
      [ Центральный сервер (FastAPI) ]  <--- config.yaml
         | (Web UI, API, WebSocket)
      [ Пользователь / Интеграции ]
```

- Каждый агент управляет группой устройств на своём сервере, снимает скриншоты, отправляет их и метаданные на центральный сервер.
- Сервер хранит скрины и логи в структуре data/ и базе, предоставляет фильтрацию, историю, массовые команды, интеграции.
- Вся логика модульная: легко добавлять новые команды, сценарии, интеграции, UI-страницы.

---

# Быстрый старт <a name="быстрый-старт"></a>

<details>
<summary>Пошаговая инструкция</summary>

1. **Установите зависимости:**

```bash
pip install -r requirements.txt
```

2. **Настройте конфиги:**

- `config.yaml` — для сервера
- `agent/config_agent.yaml` — для агента

3. **Запустите центральный сервер:**

```bash
cd central_server
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

4. **Запустите агента на каждом сервере с эмуляторами:**

```bash
cd agent
python agent.py
```

5. **Откройте веб-интерфейс:**

- <http://localhost:8000> — мониторинг, фильтры, история
- <http://localhost:8000/logs> — логи и сообщения
- <http://localhost:8000/commands> — отправка команд

</details>

---

# Структура проекта и файлов <a name="структура-проекта-и-файлов"></a>

<details>
<summary>Дерево директорий (основные файлы)</summary>

```
1337/
├── central_server/
│   ├── server.py           # FastAPI сервер, REST API, Web UI, интеграции
│   ├── templates/          # Jinja2-шаблоны (index, logs, commands)
│   ├── static/             # CSS, JS, иконки
│   ├── data/               # Скриншоты и метаданные (по серверам/окнам)
│   └── db.sqlite3          # База данных (скрины, логи, команды)
├── agent/
│   ├── agent.py            # Агент: снимает скрины, отправляет, слушает команды
│   └── config_agent.yaml   # Конфиг агента (устройства, сервер, ключ)
├── config.yaml             # Главный конфиг сервера (устройства, сценарии, API-ключи, интеграции)
├── requirements.txt        # Зависимости Python
├── devices.txt             # (опционально) список устройств
├── screenshots/            # (опционально) локальные скрины
├── logs/                   # (опционально) логи
├── README.md               # Документация
└── ...
```

</details>

---

# Конфигурация <a name="конфигурация"></a>

## config.yaml (сервер)

```yaml
devices:
  - id: 127.0.0.1:5555
    enabled: true
    scenario: default
  - id: 127.0.0.1:5575
    enabled: true
    scenario: default
scenarios:
  default:
    steps:
      - action: click_image
        template: tpl1.png
        screenshot: true
        screenshot_section: "login"
        screenshot_dir: "screenshots/login"
        upload_to_db: false
      - action: input_text
        text: "Hello"
        screenshot: false
        upload_to_db: false
      - action: click_image
        template: tpl2.png
        screenshot: true
        screenshot_section: "main"
        screenshot_dir: "screenshots/main"
        upload_to_db: true
      - action: wait
        seconds: 10
        screenshot: false
        upload_to_db: false
api_keys:
  - testkey
telegram:
  bot_token: "<your_bot_token>"
  chat_id: "<your_chat_id>"
```

- **devices** — список устройств (id = адрес ADB)
- **scenarios** — сценарии автоматизации (шаги, действия, условия)
- **api_keys** — список ключей для авторизации агентов
- **telegram** — параметры для интеграции с Telegram

## agent/config_agent.yaml (агент)

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

- **server_url** — адрес центрального сервера
- **api_key** — ключ авторизации (должен быть в config.yaml)
- **server_id** — уникальный id сервера/агента
- **devices** — список устройств, интервал мониторинга
- **screenshot_dir** — локальная папка для скринов
- **log_level** — уровень логирования

---

(Дальнейшие разделы: сервер, агент, API, UI, интеграции, расширение, FAQ, Roadmap — будут добавлены в следующих частях)

---

## Модули и интеграции <a name="модули-и-интеграции"></a>

| Модуль         | Описание                | Включение в config.yaml | Статус   |
|----------------|------------------------|------------------------|----------|
| Telegram       | Алерты в Telegram      | `modules.telegram: true`| ✅       |
| Google Sheets  | Экспорт в таблицы      | `modules.google_sheets: true` | ⬜    |
| Webhook        | Внешние уведомления    | `modules.webhook: true`| ⬜       |

<details>
<summary>Пример секции для Telegram</summary>

```yaml
modules:
  telegram: true
telegram:
  bot_token: "<your_bot_token>"
  chat_id: "<your_chat_id>"
```

</details>

<details>
<summary>Как добавить новый модуль/интеграцию</summary>

1. Создайте файл в integrations/ (например, webhook.py)
2. Опишите параметры в config.yaml
3. В server.py добавьте вызов модуля, если он включён
4. Пример вызова:

   ```python
   if cfg['modules'].get('webhook'):
       from integrations.webhook import send_webhook
       send_webhook(...)
   ```

</details>

---

## Массовые команды <a name="массовые-команды"></a>

<details>
<summary>Примеры массовых команд</summary>

- Для всех серверов:

  ```json
  { "server_id": "*", "command": "screencap" }
  ```

- Для отдельного сервера:

  ```json
  { "server_id": "server-01", "command": "screencap" }
  ```

- Для отдельного окна/устройства:

  ```json
  { "server_id": "server-01", "device_id": "127.0.0.1:5555", "command": "screencap" }
  ```

</details>

---

## Расширение и плагины <a name="расширение-и-плагины"></a>

<details>
<summary>Как добавить новый тип команды</summary>

- Добавьте обработку команды в agent.py (device_job)
- Пример:

  ```python
  elif cmd['command'] == 'reboot':
      # выполнить перезагрузку устройства
  ```

</details>

<details>
<summary>Как добавить экспорт/фильтрацию</summary>

- Добавьте эндпоинт в server.py
- Реализуйте экспорт в нужный формат (CSV, Excel, ZIP)
- Добавьте фильтры в веб-интерфейс (templates/)

</details>

<details>
<summary>Как добавить watchdog/автовосстановление</summary>

- Реализуйте отдельный поток/процесс в agent.py
- Включайте через config_agent.yaml:

  ```yaml
  modules:
    watchdog: true
  ```

</details>

---

## Конфиги и управление функциями <a name="конфиги-и-управление-функциями"></a>

<details>
<summary>Пример секции modules в config.yaml</summary>

```yaml
modules:
  telegram: true
  google_sheets: false
  webhook: false
  mass_commands: true
  auto_cleanup: false
```

</details>

<details>
<summary>Пример секции modules в config_agent.yaml</summary>

```yaml
modules:
  telegram_alerts: true
  plugins: true
```

</details>

---

## Roadmap <a name="roadmap"></a>

| Функция/Модуль         | Статус |
|------------------------|--------|
| Telegram-интеграция    | ✅     |
| Google Sheets          | ⬜     |
| Webhook                | ⬜     |
| Расширенная фильтрация | ⬜     |
| Экспорт логов/скринов  | ⬜     |
| История команд         | ⬜     |
| Графики/аналитика      | ⬜     |
| Массовые команды       | ⬜     |
| Архивация/автоудаление | ⬜     |
| Модульная архитектура  | ✅     |

---

## FAQ <a name="faq"></a>

---

<details>
<summary>Как добавить новое устройство?</summary>

- В config.yaml (сервер) или config_agent.yaml (агент) добавьте новую секцию:

    ```yaml
    - id: "127.0.0.1:5595"
      enabled: true
      window: "main"
      interval: 60
    ```

- Перезапустите агент.

</details>

<details>
<summary>Как отправить массовую команду?</summary>

- Через веб-интерфейс /commands выберите "все устройства" или нужный диапазон.
- Через API:

    ```json
    { "server_id": "*", "command": "screencap" }
    ```

</details>

<details>
<summary>Как включить Telegram-уведомления?</summary>

- В config.yaml:

    ```yaml
    modules:
      telegram: true
    telegram:
      bot_token: "<your_bot_token>"
      chat_id: "<your_chat_id>"
    ```

- Перезапустите сервер.

</details>

<details>
<summary>Как добавить новый модуль/интеграцию?</summary>

- См. раздел [Расширение: плагины, новые команды, интеграции](#расширение)

</details>

<details>
<summary>Как сделать бэкап?</summary>

- Скопируйте central_server/db.sqlite3 и папку central_server/data/
- Для автоматизации используйте cron:

    ```bash
    tar czf backup_$(date +%F).tar.gz central_server/db.sqlite3 central_server/data/
    ```

</details>

<details>
<summary>Как обновить систему?</summary>

- Остановите сервер/агентов
- Обновите файлы (git pull или копирование)
- Проверьте requirements.txt и обновите зависимости:

    ```bash
    pip install -r requirements.txt
    ```

- Перезапустите сервисы

</details>

<details>
<summary>Как добавить новый тип команды?</summary>

- В agent.py (device_job) добавьте обработку:

    ```python
    elif cmd['command'] == 'reboot':
        subprocess.run(['adb', '-s', device_id, 'reboot'])
    ```

- На сервере отправьте команду через /commands или API

</details>

<details>
<summary>Как интегрировать с внешней системой?</summary>

- Добавьте модуль в integrations/ (сервер) или plugins/ (агент)
- Вызовите его из server.py или agent.py по событию/таймеру

</details>

---

# Roadmap <a name="roadmap"></a>

| Функция/Модуль         | Статус |
|------------------------|--------|
| Telegram-интеграция    | ✅     |
| Google Sheets          | ⬜     |
| Webhook                | ⬜     |
| Расширенная фильтрация | ⬜     |
| Экспорт логов/скринов  | ⬜     |
| История команд         | ⬜     |
| Графики/аналитика      | ⬜     |
| Массовые команды       | ⬜     |
| Архивация/автоудаление | ⬜     |
| Модульная архитектура  | ✅     |

---

# Ссылки <a name="ссылки"></a>

- [CHANGELOG.md](CHANGELOG.md)
- [Документация по FastAPI](https://fastapi.tiangolo.com/)
- [Документация по ADB](https://developer.android.com/studio/command-line/adb)
- [Документация по Telegram Bot API](https://core.telegram.org/bots/api)
- [Jinja2 Templates](https://jinja.palletsprojects.com/)
- [Chart.js (графики)](https://www.chartjs.org/)
- [Prometheus (мониторинг)](https://prometheus.io/)
- [Supervisor (автозапуск)](http://supervisord.org/)

---

> **ℹ️ Все функции, примеры и инструкции актуальны для текущей версии. Для новых модулей и интеграций — просто добавьте секцию в config.yaml и следуйте инструкции из этого README!**

# Веб-интерфейс: аналитика и графики <a name="аналитика"></a>

## /analytics — страница аналитики

- Вкладки: Общая статистика, Активность устройств, Ошибки/алерты, Команды
- Графики: Chart.js (линейные, столбчатые, круговые)
- Фильтры: сервер, устройство, дата с/по
- Данные подгружаются динамически через API

### Примеры графиков

- Скриншоты и логи по дням (line)
- Распределение статусов команд (doughnut)
- Активность устройств (bar)
- Ошибки/алерты по дням (bar)
- История команд по дням (line)

### API для аналитики

- `/api/analytics/summary` — скриншоты/логи по дням, статусы команд
- `/api/analytics/device_activity` — активность устройств
- `/api/analytics/errors` — ошибки/алерты по дням
- `/api/analytics/commands_history` — история команд по дням

**Параметры:**

- `server_id`, `device_id`, `date_from`, `date_to` (YYYY-MM-DD)

**Пример:**

```
GET /api/analytics/summary?server_id=server-01&date_from=2024-05-01&date_to=2024-05-31
```

**Формат ответа (Chart.js):**

```json
{
  "screens_logs": {
    "data": { "labels": ["2024-05-01", ...], "datasets": [{"label": "Скриншоты", "data": [12, ...]}, ...] },
    "options": { ... }
  },
  "commands_status": { ... }
}
```

**UI:**

- Вкладки, фильтры, адаптивная верстка, динамическая подгрузка графиков

## Анимация, статусы и современный UX

- last.png на главной странице автоматически обновляются каждые 30 секунд (без перезагрузки страницы).
- Карточки устройств подсвечиваются при обновлении скрина (анимация).
- Для каждого устройства отображается статус: Online (скриншот свежий, <1 мин) или Offline (нет новых скринов).
- Современный адаптивный дизайн карточек, цветовая индикация статуса.

# Центральный сервер <a name="центральный-сервер"></a>

---

## 1. Назначение и архитектура

Центральный сервер — это ядро системы. Он принимает скриншоты и логи от агентов, хранит их в файловой структуре и базе данных, предоставляет REST API и современный веб-интерфейс для мониторинга, фильтрации, истории, отправки команд и интеграций.

- **Язык:** Python 3.8+
- **Фреймворк:** FastAPI (ASGI)
- **База данных:** SQLite (по умолчанию, легко заменить на PostgreSQL/MySQL)
- **Шаблоны:** Jinja2 (HTML UI)
- **WebSocket:** для live-логов
- **Интеграции:** Telegram, Google Sheets, Webhook, плагины
- **Безопасность:** API-ключи, фильтрация, логирование

---

## 2. Основные компоненты

- `server.py` — основной серверный скрипт (FastAPI)
- `templates/` — HTML-шаблоны (index, logs, commands)
- `static/` — CSS, JS, иконки
- `data/` — скриншоты и метаданные (структурировано по серверам/окнам)
- `db.sqlite3` — база данных (скрины, логи, команды)

---

## 3. REST API: Эндпоинты и примеры

### Авторизация

Все API-запросы (кроме /screenshots и /download) требуют заголовок:

```
Authorization: Bearer <api_key>
```

API-ключи задаются в `config.yaml`:

```yaml
api_keys:
  - testkey
  - anotherkey
```

### Загрузка скриншота

**POST /upload_screenshot**

- Формы: `server_id`, `window`, `device_id`, `meta`, `image`
- Ответ: `{ "status": "ok", "path": "..." }`

**Пример на Python:**

```python
import requests
url = 'http://localhost:8000/upload_screenshot'
headers = {'Authorization': 'Bearer testkey'}
data = {'server_id': 'server-01', 'window': 'main', 'device_id': '127.0.0.1:5555', 'meta': ''}
files = {'image': open('screen.png', 'rb')}
r = requests.post(url, headers=headers, data=data, files=files)
print(r.json())
```

### Получение списка скринов

**GET /screenshots?server_id=...&window=...&device_id=...**

- Параметры фильтрации (опционально)
- Ответ: JSON-массив скринов

**Пример:**

```
GET /screenshots?server_id=server-01&window=main
```

### Скачивание скрина

**GET /download/{server_id}/{window}/{filename}**

- Прямая ссылка на PNG-файл

### Отправка сообщения/лога

**POST /api/send_message**

- JSON: `{ server_id, device_id, type, message }`
- Ответ: `{ "status": "ok" }`

### Получение сообщений

**GET /api/messages?server_id=...&device_id=...&type=...&limit=100**

- Фильтрация по серверу, устройству, типу, лимиту

### Получение команд для агента

**GET /api/get_commands?server_id=...&device_id=...**

- Ответ: `{ "commands": [ ... ] }`

### Подтверждение выполнения команды

**POST /api/command_result**

- JSON: `{ command_id, status, result }`

### История выполнения команд

Страница `/command_history` и API `/api/command_history` позволяют просматривать, фильтровать и экспортировать историю всех команд, отправленных агентам.

**Возможности:**

- Фильтрация по серверу, устройству, команде, статусу, дате, тексту/параметрам
- Экспорт отфильтрованных данных в CSV и Excel (xlsx)
- Адаптивный интерфейс для мобильных устройств
- Быстрый переход к деталям команд

**Пример использования:**

- Веб-интерфейс: [http://localhost:8000/command_history](http://localhost:8000/command_history)
- API: `/api/command_history?server_id=...&device_id=...&format=csv`

**Поля:**

- `server_id` — идентификатор сервера
- `device_id` — идентификатор устройства
- `command` — команда
- `params` — параметры (JSON)
- `status` — статус выполнения (`pending`, `done`, `error` и др.)
- `created_at` — время создания

**Экспорт:**

- CSV: кнопка "Экспорт CSV" или параметр `format=csv`
- Excel: кнопка "Экспорт Excel" или параметр `format=xlsx`

**Пример запроса:**

```
GET /api/command_history?server_id=server-01&status=done&format=xlsx
```

---

## 4. Структура базы данных (SQLite)

```sql
CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id TEXT,
    window TEXT,
    device_id TEXT,
    filename TEXT,
    meta TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id TEXT,
    device_id TEXT,
    type TEXT,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id TEXT,
    device_id TEXT,
    command TEXT,
    params TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- **screenshots** — все скрины с метаданными
- **messages** — логи, ошибки, статусы
- **commands** — команды для агентов (и их статусы)

---

## 5. Веб-интерфейс (Jinja2 + CSS)

- `/` — главная: галерея скринов, фильтры по серверу/устройству/окну
- `/logs` — логи и сообщения, live-обновление через WebSocket
- `/commands` — отправка команд агентам (выбор сервера, устройства, команды, параметры)

### Пример шаблона (index.html)

```html
<form class="filters" method="get">
    <input type="text" name="server_id" placeholder="Сервер" value="{{ server_id or '' }}">
    <input type="text" name="window" placeholder="Окно" value="{{ window or '' }}">
    <input type="text" name="device_id" placeholder="Устройство" value="{{ device_id or '' }}">
    <button type="submit">Фильтр</button>
    <a href="/" style="margin-left:12px;">Сбросить</a>
</form>
<div class="gallery">
    {% for s in screenshots %}
    <div class="gallery-item">
        <a href="/download/{{ s.server_id }}/{{ s.window }}/{{ s.filename }}" target="_blank">
            <img src="/download/{{ s.server_id }}/{{ s.window }}/{{ s.filename }}" class="gallery-img" alt="screenshot">
        </a>
        <div class="gallery-meta">
            <b>Сервер:</b> {{ s.server_id }}<br>
            <b>Окно:</b> {{ s.window }}<br>
            <b>Устройство:</b> {{ s.device_id }}<br>
            <b>Время:</b> {{ s.created_at }}
        </div>
    </div>
    {% endfor %}
</div>
```

### Пример кастомизации CSS (static/style.css)

```css
body { background: #f8f8fa; font-family: Arial, sans-serif; }
.container { max-width: 1200px; margin: 0 auto; padding: 24px; }
h1 { color: #2a2a6a; }
.filters { margin-bottom: 24px; }
.filters input, .filters select { padding: 6px 12px; border-radius: 6px; border: 1.5px solid #ccc; margin-right: 8px; }
.gallery { display: flex; flex-wrap: wrap; gap: 18px; }
.gallery-item { background: #fff; border-radius: 8px; box-shadow: 0 2px 8px #0001; padding: 10px; width: 240px; }
.gallery-img { width: 220px; max-height: 140px; border-radius: 6px; border: 1px solid #ccc; margin-bottom: 6px; }
.gallery-meta { font-size: 0.95em; color: #888; }
```

---

## 6. Интеграции и расширения

- **Telegram:** мгновенные алерты о событиях, ошибках, массовых командах
- **Google Sheets:** экспорт истории, аналитика (TODO)
- **Webhook:** внешние уведомления, интеграция с CI/CD, мониторингом
- **Плагины:** просто добавьте файл в integrations/ и подключите в server.py

**Пример интеграции Telegram:**

```python
def send_telegram_alert(text: str):
    import requests, yaml
    cfg = yaml.safe_load(open('../config.yaml', encoding='utf-8'))
    token = cfg['telegram']['bot_token']
    chat_id = cfg['telegram']['chat_id']
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    requests.post(url, data={'chat_id': chat_id, 'text': text})
```

---

## 7. Добавление новых функций и эндпоинтов

- Добавьте функцию/эндпоинт в `server.py` (FastAPI: @app.get, @app.post)
- Для UI — добавьте шаблон в `templates/` и роут в server.py
- Для интеграции — создайте файл в `integrations/`, подключите через config.yaml
- Для новых фильтров — расширьте SQL-запросы и формы в шаблонах

**Пример: добавить экспорт скринов в ZIP:**

```python
@app.get('/export_zip')
def export_zip(server_id: str):
    # Собрать файлы, упаковать в ZIP, вернуть FileResponse
    ...
```

---

## 8. Отладка, масштабирование, best practices

- **Масштабирование:**
  - FastAPI легко запускается в нескольких процессах (uvicorn --workers 4)
  - SQLite можно заменить на PostgreSQL/MySQL для больших объёмов
  - Храните скрины на отдельном диске/NAS
- **Безопасность:**
  - Используйте длинные уникальные API-ключи
  - Ограничьте доступ к серверу по IP/Firewall
  - Включите HTTPS (через nginx/traefik)
- **Отладка:**
  - Все ошибки логируются в messages
  - Используйте /logs для live-мониторинга
  - Для теста API — curl, Postman, httpie
- **Обновление:**
  - Все миграции БД — через init_db() в server.py
  - Для новых версий просто обновите файлы и перезапустите сервер

---

## 9. Примеры типовых задач

- **Добавить новый тип команды:**
  - В server.py — добавить обработку в /api/get_commands и /api/command_result
  - В agent.py — добавить обработку в device_job
- **Добавить массовую команду:**
  - В /commands (web UI) — добавить выбор "все устройства" или фильтр
- **Добавить интеграцию:**
  - В config.yaml — секция modules
  - В server.py — импорт и вызов модуля
- **Добавить экспорт/аналитику:**
  - Новый эндпоинт + шаблон + SQL-запрос

---

(Следующий раздел: Агент — будет добавлен далее)

# Агент <a name="агент"></a>

Полная документация: [docs/agent.md](docs/agent.md)

### Запуск и CLI

- `python agent.py` — запуск агента
- `python agent.py status` — статус устройств, версия ADB, uptime, свободное место
- `python agent.py test` — тестовый цикл (скриншот, отправка, команды)

### Метаданные

- С каждым скриншотом отправляются: версия ADB, uptime, свободное место

### Watchdog

- Фоновый поток, который перезапускает ADB при сбоях

### Автообновление агента

- Поддерживается команда update_agent с сервера (заглушка, требуется URL)

### Тесты

- Unit: `python -m unittest discover -s agent/tests`

### Мини-гайд по запуску агента

1. Установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```

2. Настройте config_agent.yaml
3. Запустите сервер
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
    curl -f http://localhost:8000/ || echo 'Server DOWN!' | mail -s 'ADB Server Alert' admin@example.com
    ```

---

## 5. Best practices

- Используйте уникальные server_id для каждого агента.
- Храните все логи и скрины централизованно, делайте регулярные бэкапы.
- Для production — используйте HTTPS, firewall, отдельного пользователя для сервиса.
- Для крупных инсталляций — выносите storage и БД на отдельные серверы.
- Документируйте все изменения в конфиге и структуре.

---

(Следующий раздел: Расширение — плагины, новые команды, интеграции — будет добавлен далее)

# Расширение: плагины, новые команды, интеграции <a name="расширение"></a>

---

## 1. Архитектура расширения

Система изначально проектировалась как модульная и расширяемая:

- Любой модуль (интеграция, команда, UI-страница) добавляется без изменения ядра
- Все функции включаются/выключаются через config.yaml/config_agent.yaml
- Поддерживаются плагины, внешние скрипты, кастомные команды, интеграции

---

## 2. Добавление нового модуля/интеграции (сервер)

1. **Создайте файл в `central_server/integrations/`**
    - Пример: `webhook.py`
2. **Опишите параметры в config.yaml**

    ```yaml
    modules:
      webhook: true
    webhook:
      url: "https://your.webhook.url/endpoint"
      secret: "mysecretkey"
    ```

3. **В server.py добавьте вызов модуля:**

    ```python
    if cfg['modules'].get('webhook'):
        from integrations.webhook import send_webhook
        send_webhook(...)
    ```

4. **Вызовите модуль из нужного места (например, при получении скрина/лога/команды)**

---

## 3. Добавление новой команды (сервер + агент)

### На сервере

- В таблицу `commands`

```

# Автоудаление и архивация <a name="retention"></a>

## Описание

- Фоновая задача автоматически удаляет старые скриншоты и логи по истечении retention_days.
- Перед удалением можно архивировать данные (ZIP).
- Все параметры настраиваются в config.yaml (секция global).

## Параметры
- `retention_days`: сколько дней хранить скрины и логи (0 = не удалять)
- `cleanup_interval_hours`: как часто запускать очистку (в часах)
- `archive_old`: архивировать перед удалением (true/false)
- `archive_dir`: папка для архивов

## Пример config.yaml
```yaml
global:
  retention_days: 30
  cleanup_interval_hours: 12
  archive_old: true
  archive_dir: archives
```

## Как работает

- При старте сервера запускается фоновый поток очистки.
- Все скрины и логи старше retention_days архивируются (если archive_old=true) и удаляются из файловой системы и БД.
- Архивы складываются в archive_dir (ZIP для скринов, logs.csv.zip для логов).

## Best practices

- Для production: не ставьте retention_days=0 (иначе диск может переполниться)
- Для больших архивов используйте отдельный диск/раздел для archive_dir
- Для критичных данных делайте резервные копии архивов

## Быстрый просмотр последних скриншотов (last.png)

- Для каждого устройства/окна сервер хранит last.png (последний актуальный скриншот).
- Быстрый просмотр и скачивание через web-интерфейс и API:
  - `GET /download_last/{server_id}/{window}/{device_id}` — получить last.png
- На главной странице теперь отдельная секция "Последние скриншоты (last.png)" для быстрого мониторинга.

## API

- `POST /upload_screenshot` — загрузка скриншота, теперь сохраняет и last.png
- `GET /download_last/{server_id}/{window}/{device_id}` — получить последний скриншот (last.png)
- `GET /download/{server_id}/{window}/{filename}` — скачать любой скриншот из истории

## Web-интерфейс

- Главная страница: быстрый просмотр last.png для всех устройств/окон, переход к истории, скачивание.
- История и фильтрация по устройствам, окнам, времени, метаданным.

## Секции (sections) и бинды (binds)

- Все устройства и окна теперь можно группировать по секциям (например, "login", "main", "settings").
- Секция определяется по window или по meta.section (если meta содержит поле section).
- На главной странице web-интерфейса устройства и last.png сгруппированы по секциям.
- В фильтрах и API можно указывать section для быстрой фильтрации.
- Пример API:
  - `GET /screenshots?section=main` — все скрины из секции main
  - `GET /?section=login` — web-интерфейс: только секция login

## Интеграции: webhook, Google Sheets, Telegram

- Все события (скриншот, лог, команда) автоматически отправляются во внешние системы, если модуль включён в config.yaml.
- Поддерживаются:
  - Webhook (Slack, Discord, SIEM и др.)
  - Google Sheets (запись событий в таблицу)
  - Telegram (алерты по error/alert)
- Включение/отключение через секцию modules:

```yaml
modules:
  webhook: true
  google_sheets: true
  telegram: true
```

- Пример секции webhook:

```yaml
webhook:
  url: "https://your.webhook.url/endpoint"
  secret: "mysecretkey"
```

- Пример секции google_sheets:

```yaml
google_sheets:
  credentials: "central_server/integrations/credentials.json"
  sheet_id: "1AbC...xyz"
  worksheet: "Лист1"
```

- Пример секции telegram:

```yaml
telegram:
  bot_token: "<your_bot_token>"
  chat_id: "<your_chat_id>"
```

- Все события отправляются через универсальный хук:
  - `screenshot_uploaded` — при загрузке скрина
  - `log`, `error`, `alert` — при отправке сообщения/лога
  - `command_result` — при завершении команды

## Автоматический запуск и деплой <a name="автоматический-запуск-и-деплой"></a>

Для автоматического запуска и деплоя используйте скрипты:

- Linux/macOS: `run_full_stack.sh`, `run_server_only.sh`, `run_agent_only.sh`
- Windows: `run_everything_win.bat`, `run_server_only_win.bat`, `run_agent_only_win.bat`
- Универсальный автоскрипт: `python run_check_and_setup.py`

Все скрипты автоматически установят зависимости, проверят окружение и запустят нужные сервисы. Подробнее — см. раздел "README.md" выше.

# Автоматизация интеграционных тестов <a name="автоматизация-интеграционных-тестов"></a>

Для проверки работоспособности всей системы используйте скрипт:

```bash
python run_integration_tests.py
```

Скрипт:

- Проверяет доступность сервера по адресу <http://127.0.0.1:8000/>
- Если сервер не запущен — выводит ошибку и инструкцию по запуску
- Если сервер доступен — автоматически запускает интеграционные тесты (agent/tests/test_device_session.py)
- В тесте интеграций поднимается локальный HTTP webhook endpoint (<http://127.0.0.1:9999/webhook>), и тест проверяет, что сервер реально отправляет POST-запрос на этот endpoint (реальная интеграция, а не mock).
- Показывает результат тестов

**Рекомендуется запускать после каждого изменения кода или перед деплоем!**

# Масштабирование и отказоустойчивость <a name="масштабирование-и-отказоустойчивость"></a>

Система поддерживает масштабирование на десятки серверов и сотни устройств. Используйте отдельные агенты для каждого хоста, централизованный сервер, резервное копирование и мониторинг. Подробнее:

- [8. Отладка, масштабирование, best practices](#8-отладка-масштабирование-best-practices)
- [Best practices](#best-practices)

# Безопасность и best practices <a name="безопасность"></a>

Используйте уникальные API-ключи, firewall, HTTPS, регулярные бэкапы. Для production — отдельный пользователь, ограничение доступа по IP. Подробнее:

- [Best practices](#best-practices)
- [8. Отладка, масштабирование, best practices](#8-отладка-масштабирование-best-practices)

# Веб-интерфейс: аналитика и графики <a name="аналитика"></a>

## /analytics — страница аналитики

- Вкладки: Общая статистика, Активность устройств, Ошибки/алерты, Команды
- Графики: Chart.js (линейные, столбчатые, круговые)
- Фильтры: сервер, устройство, дата с/по
- Данные подгружаются динамически через API

### Примеры графиков

- Скриншоты и логи по дням (line)
- Распределение статусов команд (doughnut)
- Активность устройств (bar)
- Ошибки/алерты по дням (bar)
- История команд по дням (line)

### API для аналитики

- `/api/analytics/summary` — скриншоты/логи по дням, статусы команд
- `/api/analytics/device_activity` — активность устройств
- `/api/analytics/errors` — ошибки/алерты по дням
- `/api/analytics/commands_history` — история команд по дням

**Параметры:**

- `server_id`, `device_id`, `date_from`, `date_to` (YYYY-MM-DD)

**Пример:**

```
GET /api/analytics/summary?server_id=server-01&date_from=2024-05-01&date_to=2024-05-31
```

**Формат ответа (Chart.js):**

```json
{
  "screens_logs": {
    "data": { "labels": ["2024-05-01", ...], "datasets": [{"label": "Скриншоты", "data": [12, ...]}, ...] },
    "options": { ... }
  },
  "commands_status": { ... }
}
```

**UI:**

- Вкладки, фильтры, адаптивная верстка, динамическая подгрузка графиков

## Анимация, статусы и современный UX

- last.png на главной странице автоматически обновляются каждые 30 секунд (без перезагрузки страницы).
- Карточки устройств подсвечиваются при обновлении скрина (анимация).
- Для каждого устройства отображается статус: Online (скриншот свежий, <1 мин) или Offline (нет новых скринов).
- Современный адаптивный дизайн карточек, цветовая индикация статуса.

# CI/CD

![CI](https://github.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPO>/actions/workflows/ci.yml/badge.svg)

Автоматический запуск интеграционных тестов при каждом коммите и pull request через GitHub Actions:

- Установка зависимостей
- Запуск `python run_integration_tests.py`
- В случае ошибки — артефакты логов доступны в Actions

**Добавление новых тестов:**

- Добавьте тесты в `agent/tests/`
- Все тесты запускаются автоматически в CI
- Для локального запуска: `python run_integration_tests.py`

## Интеграционные тесты

- Запуск: `python -m unittest agent/tests/test_device_session.py`
- Проверяется реальный вызов webhook (POST), Google Sheets и Telegram интеграции (мок).
- config.yaml для теста формируется автоматически, ничего менять не нужно.
- Все тесты проходят без реальных ключей и файлов (Google Sheets и Telegram — mock, webhook — реальный HTTP).

### Пример структуры config.yaml для интеграций

```yaml
modules:
  webhook: true
  google_sheets: true
  telegram: true
webhook:
  url: http://127.0.0.1:PORT/webhook
  secret: test
google_sheets:
  credentials: fake.json
  sheet_id: fakeid
  worksheet: Лист1
telegram:
  bot_token: fake
  chat_id: fake
```

## CI/CD

- Все тесты автоматически запускаются в GitHub Actions (см. .github/workflows/ci.yml).
- При ошибках тестов выгружаются server.log и подробный вывод.

## Быстрый старт для тестов

```sh
pip install -r requirements.txt
python -m unittest agent/tests/test_device_session.py
```

## 🧪 Изоляция config.yaml для тестов и CI

Для предотвращения конфликтов и race condition при параллельном запуске тестов теперь поддерживается переменная окружения `CONFIG_YAML`. Если она задана, сервер и все интеграции используют указанный путь к config.yaml.

**Пример запуска сервера с кастомным config.yaml:**

```bash
# Linux/Mac:
CONFIG_YAML=/tmp/test_config.yaml uvicorn central_server.server:app --host 127.0.0.1 --port 8000
```

```bat
:: Windows (cmd):
set CONFIG_YAML=C:\Users\dimas\Documents\1337\test_config.yaml
uvicorn central_server.server:app --host 127.0.0.1 --port 8000
```

```powershell
# Windows (PowerShell):
$env:CONFIG_YAML="C:\Users\dimas\Documents\1337\test_config.yaml"
uvicorn central_server.server:app --host 127.0.0.1 --port 8000
```

## 🧪 Google Sheets e2e тест

Для реального e2e теста интеграции с Google Sheets (без mock) задайте переменные окружения:

- `GSHEET_CREDENTIALS` — путь к credentials.json (Google Service Account)
- `GSHEET_SHEET_ID` — ID Google Sheet
- `GSHEET_WORKSHEET` — имя листа (опционально, по умолчанию "Лист1")

**Пример для Windows (cmd):**

```bat
set GSHEET_CREDENTIALS=C:\Users\dimas\Documents\1337\credentials.json
set GSHEET_SHEET_ID=1AbC...xyz
set GSHEET_WORKSHEET=Лист1
python -m unittest agent/tests/test_device_session.py
```

**Пример для Linux/Mac:**

```bash
export GSHEET_CREDENTIALS=/home/user/credentials.json
export GSHEET_SHEET_ID=1AbC...xyz
export GSHEET_WORKSHEET=Лист1
python -m unittest agent/tests/test_device_session.py
```

Если переменные не заданы или файл не найден — тест будет пропущен (mock).

## 🧪 Telegram e2e тест

Для реального e2e теста интеграции с Telegram (без mock) задайте переменные окружения:

- `TG_BOT_TOKEN` — токен Telegram-бота
- `TG_CHAT_ID` — chat_id для отправки сообщения

**Пример для Windows (cmd):**

```bat
set TG_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
set TG_CHAT_ID=123456789
python -m unittest agent/tests/test_device_session.py
```

**Пример для Linux/Mac:**

```bash
export TG_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
export TG_CHAT_ID=123456789
python -m unittest agent/tests/test_device_session.py
```

Если переменные не заданы — тест будет пропущен (mock).

## Тестирование и отладка

- Экспорт скринов в CSV теперь стабилен, ValueError из-за лишних полей (например, 'section') устранён (v0.2.1).
- Тесты проходят на Windows, PermissionError при удалении db.sqlite3 устранён (tearDownClass делает retry).

## Ролевая модель и права доступа

- **admin** — полный доступ (экспорт, команды, логи, просмотр)
- **user** — может отправлять команды и логи, не может экспортировать
- **readonly** — только просмотр, не может отправлять команды/логи/экспортировать

Пример секции users для config.yaml:

```yaml
users:
  - username: admin
    api_key: testkey
    role: admin
  - username: user1
    api_key: userkey
    role: user
  - username: guest
    api_key: guestkey
    role: readonly
```

**Тестирование ролей:**

- Все REST API и UI защищены по ролям
- Покрытие автотестами: права на экспорт, команды, логи, просмотр
- Для тестов используйте ключи testkey (admin), userkey (user), guestkey (readonly)
