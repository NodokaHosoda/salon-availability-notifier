import asyncio
import json

import requests

from availability_checker import check_availability
from config import get_settings
from repositories import get_last_available_dates, update_last_available_dates
from utils import (
    format_date_only_for_display,
    format_time_for_display,
    serialize_compact_datetimes,
)

REQUEST_TIMEOUT_SECONDS = 10



def build_availability_message_payload(message, available_dates=None, new_available_dates=None):
    if not available_dates:
        return {"type": "text", "text": message}

    # 新しく増えた枠だけ強調しつつ、カード自体には現在見えている候補全体を載せる。
    highlighted_dates = set(new_available_dates or [])
    grouped_dates = {}
    for dt_obj in sorted(available_dates):
        date_label = format_date_only_for_display(dt_obj)
        grouped_dates.setdefault(date_label, []).append(
            {
                "compact": dt_obj.strftime("%Y%m%d%H%M"),
                "time": format_time_for_display(dt_obj),
            }
        )

    sections = []
    for date_label, items in grouped_dates.items():
        time_contents = []
        for index, item in enumerate(items):
            is_new = item["compact"] in highlighted_dates
            time_contents.append(
                {
                    "type": "text",
                    "text": item["time"],
                    "size": "sm",
                    "weight": "bold" if is_new else "regular",
                    "color": "#A7482F" if is_new else "#6B655D",
                    "flex": 0,
                }
            )
            if index < len(items) - 1:
                time_contents.append(
                    {
                        "type": "text",
                        "text": "  ",
                        "size": "sm",
                        "color": "#6B655D",
                        "flex": 0,
                    }
                )

        sections.append(
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "margin": "lg",
                "contents": [
                    {
                        "type": "text",
                        "text": date_label,
                        "weight": "bold",
                        "size": "sm",
                        "wrap": True,
                        "color": "#1F1F1F",
                    },
                    {
                        "type": "box",
                        "layout": "baseline",
                        "spacing": "none",
                        "contents": time_contents,
                    },
                ],
            }
        )

    return {
        "type": "flex",
        "altText": message,
        "contents": {
            "type": "bubble",
            "size": "giga",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "空きがあります",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#A7482F",
                    },
                    {
                        "type": "text",
                        "text": f"{len(available_dates)}件の候補が見つかりました。",
                        "size": "sm",
                        "wrap": True,
                        "color": "#6B655D",
                    },
                    {
                        "type": "separator",
                        "margin": "md",
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "contents": sections,
                    },
                ],
            },
        },
    }



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
        previous_available_dates = get_last_available_dates(user_db_id) or []
        new_available_dates = sorted(set(visible_available_dates) - set(previous_available_dates))
        if not new_available_dates:
            print("No newly added availability, skipping notification.")
            update_last_available_dates(user_db_id, visible_available_dates)
            return

    message_payload = build_availability_message_payload(
        check_result.message,
        check_result.visible_dates,
        new_available_dates,
    )
    if not send_line_push_message(line_user_id, user_db_id, message_payload):
        return

    update_last_available_dates(user_db_id, visible_available_dates)
