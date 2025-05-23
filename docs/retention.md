# Автоудаление и архивация (retention)

## Описание

Фоновая задача сервера автоматически удаляет старые скриншоты и логи по истечении retention_days. Перед удалением можно архивировать данные (ZIP). Все параметры настраиваются в config.yaml (секция global).

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
