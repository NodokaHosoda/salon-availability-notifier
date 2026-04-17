from linebot.models import TemplateSendMessage

from utils import format_date_only_for_display, format_time_for_display


def build_set_notification_date_message():
    return TemplateSendMessage(
        alt_text="通知したい期限日を選択してください。",
        template={
            "type": "buttons",
            "title": "通知開始",
            "text": "何日までの空き情報を確認したいか、日付を選択してください。",
            "actions": [
                {
                    "type": "datetimepicker",
                    "label": "日付を選択",
                    "data": "start",
                    "mode": "date",
                }
            ],
        },
    )


def build_modify_date_message(current_date=None):
    template = {
        "type": "buttons",
        "title": "日付変更",
        "text": "変更したい日付を選択してください。",
        "actions": [
            {
                "type": "datetimepicker",
                "label": "日付を選択",
                "data": "modify",
                "mode": "date",
            }
        ],
    }

    if current_date:
        template["text"] = (
            f"現在の登録日付は {current_date} です。変更したい日付を選択してください。"
        )
        template["actions"][0]["initial"] = current_date

    return TemplateSendMessage(
        alt_text="変更したい日付を選択してください。",
        template=template,
    )


def build_stop_notification_message():
    return TemplateSendMessage(
        alt_text="通知を停止しますか？",
        template={
            "type": "confirm",
            "title": "通知停止",
            "text": "通知を停止しますか？",
            "actions": [
                {
                    "type": "postback",
                    "label": "はい",
                    "text": "はい",
                    "data": "stop",
                },
                {
                    "type": "message",
                    "label": "いいえ",
                    "text": "いいえ",
                },
            ],
        },
    )


def build_modify_confirmation_message(selected_date):
    return TemplateSendMessage(
        alt_text=f"通知対象日を {selected_date} に変更しますか？",
        template={
            "type": "confirm",
            "title": "日付変更",
            "text": f"通知対象日を {selected_date} に変更しますか？",
            "actions": [
                {
                    "type": "postback",
                    "label": "はい",
                    "text": "はい",
                    "data": f"action=confirm_modify&date={selected_date}",
                },
                {
                    "type": "message",
                    "label": "いいえ",
                    "text": "いいえ",
                },
            ],
        },
    )


def build_start_confirmation_message(selected_date):
    return TemplateSendMessage(
        alt_text=f"{selected_date} までの空き情報の通知を開始しますか？",
        template={
            "type": "confirm",
            "title": "通知開始",
            "text": f"{selected_date} までの空き情報の通知を開始しますか？",
            "actions": [
                {
                    "type": "postback",
                    "label": "はい",
                    "text": "はい",
                    "data": f"action=confirm_start&date={selected_date}",
                },
                {
                    "type": "message",
                    "label": "いいえ",
                    "text": "いいえ",
                },
            ],
        },
    )


def build_salon_availability_sections(available_dates, highlighted_dates=None):
    highlighted = set(highlighted_dates or [])
    grouped_dates = {}
    for dt_obj in sorted(available_dates):
        date_label = format_date_only_for_display(dt_obj)
        grouped_dates.setdefault(date_label, []).append(
            {
                "key": dt_obj.strftime("%Y%m%d%H%M"),
                "text": format_time_for_display(dt_obj),
            }
        )

    sections = []
    for date_label, items in grouped_dates.items():
        sections.append(
            {
                "label": date_label,
                "items": [
                    {
                        "text": item["text"],
                        "highlighted": item["key"] in highlighted,
                    }
                    for item in items
                ],
            }
        )
    return sections


def build_availability_message_payload(message, sections=None, total_count=0, title="空きがあります"):
    if not sections:
        return {"type": "text", "text": message}

    rendered_sections = []
    for section in sections:
        item_contents = []
        items = section.get("items") or []
        for index, item in enumerate(items):
            item_contents.append(
                {
                    "type": "text",
                    "text": item["text"],
                    "size": "sm",
                    "weight": "bold" if item.get("highlighted") else "regular",
                    "color": "#A7482F" if item.get("highlighted") else "#6B655D",
                    "flex": 0,
                    "wrap": True,
                }
            )
            if index < len(items) - 1:
                item_contents.append(
                    {
                        "type": "text",
                        "text": "  ",
                        "size": "sm",
                        "color": "#6B655D",
                        "flex": 0,
                    }
                )

        rendered_sections.append(
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "margin": "lg",
                "contents": [
                    {
                        "type": "text",
                        "text": section["label"],
                        "weight": "bold",
                        "size": "sm",
                        "wrap": True,
                        "color": "#1F1F1F",
                    },
                    {
                        "type": "box",
                        "layout": "baseline",
                        "spacing": "none",
                        "contents": item_contents,
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
                        "text": title,
                        "weight": "bold",
                        "size": "xl",
                        "color": "#A7482F",
                    },
                    {
                        "type": "text",
                        "text": f"{total_count}件の候補が見つかりました。",
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
                        "contents": rendered_sections,
                    },
                ],
            },
        },
    }
