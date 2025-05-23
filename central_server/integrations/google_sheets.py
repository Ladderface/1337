import gspread
import logging
from datetime import datetime

def append_to_sheet(event: str, data: dict, cfg: dict) -> bool:
    """
    Добавляет строку в Google Sheet по событию.
    :param event: тип события (например, 'screenshot_uploaded', 'alert', 'command_executed')
    :param data: полезная нагрузка (dict)
    :param cfg: полный конфиг (dict), должен содержать google_sheets.credentials, google_sheets.sheet_id, google_sheets.worksheet
    :return: True если успешно, False если ошибка
    """
    gs_cfg = cfg.get('google_sheets', {})
    creds_path = gs_cfg.get('credentials')
    sheet_id = gs_cfg.get('sheet_id')
    worksheet_name = gs_cfg.get('worksheet', 'Лист1')
    if not (creds_path and sheet_id):
        logging.error('[sheets] Не указан credentials или sheet_id в config.yaml')
        return False
    try:
        gc = gspread.service_account(filename=creds_path)
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet(worksheet_name)
        row = [datetime.now().isoformat(), event, str(data)]
        ws.append_row(row, value_input_option='USER_ENTERED')
        logging.info(f'[sheets] Событие {event} добавлено в Google Sheet')
        return True
    except Exception as e:
        logging.error(f'[sheets] Исключение: {e}')
    return False 