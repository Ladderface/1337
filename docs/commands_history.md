# История команд

## Описание

Система хранит историю всех команд, отправленных агентам, с фильтрацией, экспортом и UI.

## Параметры фильтрации

- server_id, device_id, command, status, дата, текст/параметры

## Примеры API

- `/api/command_history?server_id=server-01&status=done&format=csv`
- `/api/command_history?device_id=127.0.0.1:5555&format=xlsx`

## Примеры UI

- Страница /command_history: фильтры, экспорт, адаптивный интерфейс

## Экспорт

- CSV, Excel (xlsx) с учетом фильтров

## Best practices

- Для массового экспорта используйте фильтры.
- Для анализа используйте Excel/Google Sheets.
