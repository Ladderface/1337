# Экспорт логов и скринов

## Описание

Система поддерживает экспорт скриншотов и логов по фильтрам в форматы CSV, ZIP (файлы), Excel (xlsx).

## Варианты экспорта

- Скриншоты: CSV (метаданные), ZIP (файлы)
- Логи: CSV
- История команд: CSV, Excel (xlsx)

## Примеры API

- Экспорт скринов:
  - CSV: `/export_screenshots?format=csv&server_id=...`
  - ZIP: `/export_screenshots?format=zip&server_id=...`
- Экспорт логов:
  - CSV: `/export_logs?format=csv&server_id=...`
- Экспорт истории команд:
  - CSV: `/api/command_history?format=csv&server_id=...`
  - Excel: `/api/command_history?format=xlsx&server_id=...`

## Примеры UI

- Кнопки экспорта на страницах /, /logs, /command_history учитывают все фильтры.

## Ограничения

- ZIP-архивы могут быть большими — используйте фильтры по дате/устройству.
- Для экспорта Excel требуется пакет openpyxl.

## Best practices

- Для массового экспорта используйте фильтры (дата, сервер, устройство).
- Для автоматизации используйте curl/wget и API.
