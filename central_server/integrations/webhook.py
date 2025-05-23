import requests
import logging

def send_webhook(event: str, data: dict, cfg: dict) -> bool:
    """
    Отправка события на внешний webhook (Slack, Discord, SIEM и др.)
    :param event: тип события (например, 'screenshot_uploaded', 'alert', 'command_executed')
    :param data: полезная нагрузка (dict)
    :param cfg: полный конфиг (dict), должен содержать webhook.url и webhook.secret
    :return: True если успешно, False если ошибка
    """
    url = cfg.get('webhook', {}).get('url')
    secret = cfg.get('webhook', {}).get('secret', '')
    print(f"[send_webhook] called: url={url}, event={event}, data={data}")
    if not url:
        print('[send_webhook] Не указан webhook.url в config.yaml')
        return False
    payload = {
        'event': event,
        'data': data,
        'secret': secret
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"[send_webhook] requests.post result: {resp.status_code} {resp.text}")
        if resp.ok:
            print(f'[send_webhook] Событие {event} отправлено на {url}')
            return True
        else:
            print(f'[send_webhook] Ошибка {resp.status_code}: {resp.text}')
    except Exception as e:
        print(f'[send_webhook] Исключение: {e}')
    return False 