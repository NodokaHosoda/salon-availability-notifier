from linebot.models import TemplateSendMessage


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
