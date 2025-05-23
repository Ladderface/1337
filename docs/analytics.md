# Аналитика и графики

## Описание

Система поддерживает аналитику по скриншотам, логам, командам с визуализацией на графиках (Chart.js) и API.

## Вкладки аналитики

- Общая статистика (скриншоты, логи по дням)
- Активность устройств
- Ошибки/алерты по дням
- История команд

## Примеры API

- `/api/analytics/summary?server_id=server-01&date_from=2024-05-01&date_to=2024-05-31`
- `/api/analytics/device_activity?device_id=127.0.0.1:5555`
- `/api/analytics/errors?type=error`
- `/api/analytics/commands_history?status=done`

## Параметры

- server_id, device_id, date_from, date_to, type, status

## UI

- Вкладки, фильтры, адаптивная верстка, динамическая подгрузка графиков

## Best practices

- Для анализа используйте фильтры по дате, устройству, серверу.
- Для экспорта данных используйте API.
