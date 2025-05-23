# Интеграции: Telegram, Webhook, Google Sheets

## Telegram

- Включение через config.yaml:

  ```yaml
  modules:
    telegram: true
  telegram:
    bot_token: "<your_bot_token>"
    chat_id: "<your_chat_id>"
  ```

- Все алерты и ошибки отправляются в Telegram.
- Best practices: используйте отдельного бота, не публикуйте токен.

## Webhook

- Включение через config.yaml:

  ```yaml
  modules:
    webhook: true
  webhook:
    url: "https://your.webhook.url/endpoint"
    secret: "mysecretkey"
  ```

- Все события отправляются через функцию send_webhook(event, data, cfg).
- Best practices: используйте секреты, проверяйте логи.

## Google Sheets

- Включение через config.yaml:

  ```yaml
  modules:
    google_sheets: true
  google_sheets:
    credentials: "central_server/integrations/credentials.json"
    sheet_id: "1AbC...xyz"
    worksheet: "Лист1"
  ```

- Все события записываются через функцию append_to_sheet(event, data, cfg).
- Best practices: используйте отдельный лист для каждой категории событий.
