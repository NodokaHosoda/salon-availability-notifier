import asyncio
import json

import requests

from availability_checker import check_availability
from config import get_settings
from line_templates import build_availability_message_payload
from repositories import notification_setting_repository
from utils import serialize_compact_datetimes

REQUEST_TIMEOUT_SECONDS = 10

def send_line_push_message(line_user_id, user_db_id, message_payload):
    push_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_settings().line_channel_access_token}",
    }
    body = {
        "to": line_user_id,
        "messages": [message_payload],
    }
    try:
        response = requests.post(
            push_url,
            headers=headers,
            data=json.dumps(body),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        print(f"[line_push] user_id={user_db_id} status={response.status_code}")
        try:
            print(response.json())
        except ValueError:
            print(response.text)
        return response.ok
    except requests.RequestException as exc:
        print(f"[line_push] user_id={user_db_id} failed: {exc}")
        return False



def check_and_send_availability(request_date, line_user_id, user_db_id, exception_dates=None, compare_with_last=True):
    exception_set = exception_dates or set()
    check_result = asyncio.run(check_availability(request_date, exception_set))

    # 次回比較が実際の表示内容と一致するよう、保存するのはユーザーに見せた候補だけにする。
    visible_available_dates = serialize_compact_datetimes(check_result.visible_dates)
    new_available_dates = visible_available_dates
    if compare_with_last:
        previous_available_dates = (
            notification_setting_repository.get_last_available_dates(user_db_id) or []
        )
        new_available_dates = sorted(set(visible_available_dates) - set(previous_available_dates))
        if not new_available_dates:
            print("No newly added availability, skipping notification.")
            notification_setting_repository.update_last_available_dates(
                user_db_id, visible_available_dates
            )
            return

    message_payload = build_availability_message_payload(
        check_result.message,
        check_result.visible_dates,
        new_available_dates,
    )
    if not send_line_push_message(line_user_id, user_db_id, message_payload):
        return

    notification_setting_repository.update_last_available_dates(
        user_db_id, visible_available_dates
    )
