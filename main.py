from datetime import datetime
from urllib.parse import parse_qs
from pathlib import Path
import os

from flask import Flask, abort, jsonify, render_template, request
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    FollowEvent,
    MessageEvent,
    PostbackEvent,
    TemplateSendMessage,
    TextMessage,
    TextSendMessage,
)
from supabase import create_client
from scraper import send_line_message

load_dotenv()
load_dotenv(dotenv_path=Path.home() / ".env", override=False)

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LIFF_EXCLUDE_ADD_ID = os.environ.get("LIFF_EXCLUDE_ADD_ID", "")
LIFF_EXCLUDE_REMOVE_ID = os.environ.get("LIFF_EXCLUDE_REMOVE_ID", "")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


@app.route("/")
def index():
    return "LINE Bot is running on Cloud Run!"


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    print("Request body:", body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@app.route("/liff/exclude-add")
def liff_exclude_add():
    return render_template(
        "liff_exclude_add.html",
        liff_id=LIFF_EXCLUDE_ADD_ID,
        page_title="除外日を追加",
    )


@app.route("/liff/exclude-remove")
def liff_exclude_remove():
    return render_template(
        "liff_exclude_remove.html",
        liff_id=LIFF_EXCLUDE_REMOVE_ID,
        page_title="除外日を解除",
    )


@app.route("/api/exceptions", methods=["GET"])
def api_get_exceptions():
    user_id = get_user_id_from_request()
    response = (
        supabase.table("exceptions_date")
        .select("date")
        .eq("user_id", user_id)
        .order("date")
        .execute()
    )
    dates = [row["date"] for row in (response.data or []) if row.get("date")]
    return jsonify({"dates": dates})


@app.route("/api/exceptions", methods=["POST"])
def api_add_exceptions():
    user_id = get_user_id_from_request()
    payload = request.get_json(silent=True) or {}
    dates = payload.get("dates", [])
    saved_count = save_exception_dates(user_id, decode_iso_dates(dates))
    return jsonify({"saved_count": saved_count})


@app.route("/api/exceptions/remove", methods=["POST"])
def api_remove_exceptions():
    user_id = get_user_id_from_request()
    payload = request.get_json(silent=True) or {}
    dates = payload.get("dates", [])
    removed_count = remove_exception_dates(user_id, decode_iso_dates(dates))
    return jsonify({"removed_count": removed_count})


@handler.add(FollowEvent)
def handle_follow(event):
    line_user_id = event.source.user_id
    response = (
        supabase.table("user_info")
        .select("id")
        .eq("line_user_id", line_user_id)
        .execute()
    )

    if not response.data:
        response = (
            supabase.table("user_info")
            .insert({"line_user_id": line_user_id, "line_user_name": None})
            .execute()
        )
        (
            supabase.table("notification_setting")
            .insert(
                {
                    "user_id": response.data[0]["id"],
                    "last_date": None,
                    "get_notification": False,
                                    }
            )
            .execute()
        )


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    received_text = event.message.text
    user_id = get_user_id_from_line_user_id(event.source.user_id)

    if received_text == "通知設定":
        if is_notification_enabled(user_id):
            reply_msg = TemplateSendMessage(
                alt_text="通知を停止しますか？",
                template=stop_notification["template"],
            )
        else:
            reply_msg = TemplateSendMessage(
                alt_text="通知したい期限日を選択してください。",
                template=set_notification_date["template"],
            )
    elif received_text == "日付変更":
        if not is_notification_enabled(user_id):
            reply_msg = TextSendMessage(text="通知が有効になっていません。まずは通知を開始してください。")
            line_bot_api.reply_message(event.reply_token, reply_msg)
            return
        reply_msg = TemplateSendMessage(
            alt_text="変更したい日付を選択してください。",
            template=modify_date["template"],
        )
    elif received_text == "即時確認":
        if not is_notification_enabled(user_id):
            reply_msg = TextSendMessage(
                text="通知が有効になっていません。まずは通知を開始してください。"
            )
        else:
            reply_msg = TextSendMessage(
                text="現在の空き状況を確認しています。"
            )
            line_bot_api.reply_message(event.reply_token, reply_msg)
            send_line_message(
                get_notification_target_date(user_id),
                event.source.user_id,
                user_id,
                set(get_exception_dates(user_id)),
                compare_with_last=False,
            )
            return
    elif received_text == "登録情報確認":
        reply_msg = TextSendMessage(text=get_registration_summary(user_id))
    elif received_text == "除外日を解除":
        remove_url = build_liff_remove_url()
        if not remove_url:
            reply_msg = TextSendMessage(text="除外解除用の LIFF URL が設定されていません。")
        else:
            reply_msg = TemplateSendMessage(
                alt_text="除外日の解除画面を開きます。",
                template={
                    "type": "buttons",
                    "title": "除外日を解除",
                    "text": "登録済みの除外日から解除したい日時を選択してください。",
                    "actions": [
                        {
                            "type": "uri",
                            "label": "画面を開く",
                            "uri": remove_url,
                        }
                    ],
                },
            )
    else:
        return

    line_bot_api.reply_message(event.reply_token, reply_msg)


@handler.add(PostbackEvent)
def handle_postback(event):
    action = event.postback.data
    selected_date = None

    if event.postback.params:
        selected_date = event.postback.params.get("date")

    data_dict = parse_qs(event.postback.data)
    if "date" in data_dict:
        selected_date = data_dict["date"][0]
    if "action" in data_dict:
        action = data_dict["action"][0]

    user_id = get_user_id_from_line_user_id(event.source.user_id)

    if action == "start":
        data = create_start_msg(selected_date)
        reply_msg = TemplateSendMessage(
            alt_text=data["altText"],
            template=data["template"],
        )
    elif action == "modify":
        data = create_modify_msg(selected_date)
        reply_msg = TemplateSendMessage(
            alt_text=data["altText"],
            template=data["template"],
        )
    elif action == "stop":
        (
            supabase.table("notification_setting")
            .update({"get_notification": False, "last_date": None, "last_available_dates": None})
            .eq("user_id", user_id)
            .execute()
        )
        reply_msg = TextSendMessage(text="通知を停止しました。")
    elif action == "confirm_start":
        update_last_date(user_id, selected_date)
        (
            supabase.table("notification_setting")
            .update({"get_notification": True})
            .eq("user_id", user_id)
            .execute()
        )
        reply_msg = TextSendMessage(text=f"{selected_date} までの空き情報の通知を開始しました。")
    elif action == "confirm_modify":
        update_last_date(user_id, selected_date)
        reply_msg = TextSendMessage(text=f"通知対象日を {selected_date} に変更しました。")
    else:
        reply_msg = TextSendMessage(text="操作を処理できませんでした。")

    line_bot_api.reply_message(event.reply_token, reply_msg)


def get_user_id_from_request():
    line_user_id = request.headers.get("X-Line-User-Id", "").strip()
    if not line_user_id:
        abort(401)
    return get_user_id_from_line_user_id(line_user_id)


def get_user_id_from_line_user_id(line_user_id):
    response = (
        supabase.table("user_info")
        .select("id")
        .eq("line_user_id", line_user_id)
        .single()
        .execute()
    )
    if not response.data:
        abort(404)
    return response.data["id"]


def is_notification_enabled(user_id):
    notification_row = get_notification_settings(user_id)
    return bool(notification_row.get("get_notification"))


def update_last_date(user_id, new_date):
    (
        supabase.table("notification_setting")
        .update({"last_date": new_date})
        .eq("user_id", user_id)
        .execute()
    )


def get_notification_settings(user_id):
    response = (
        supabase.table("notification_setting")
        .select("last_date,get_notification")
        .eq("user_id", user_id)
        .execute()
    )
    return response.data[0] if response.data else {}


def get_notification_target_date(user_id):
    notification_row = get_notification_settings(user_id)
    return notification_row.get("last_date")


def get_exception_dates(user_id):
    response = (
        supabase.table("exceptions_date")
        .select("date")
        .eq("user_id", user_id)
        .order("date")
        .execute()
    )
    return [
        datetime.fromisoformat(row["date"])
        for row in (response.data or [])
        if row.get("date")
    ]


def get_registration_summary(user_id):
    is_enabled = is_notification_enabled(user_id)
    last_date = get_notification_target_date(user_id)

    exception_dates = get_exception_dates(user_id)

    lines = [f"通知状態: {'ON' if is_enabled else 'OFF'}"]
    if is_enabled:
        lines.append(f"通知期限日: {last_date or '未設定'}")

    if exception_dates:
        lines.append("除外日時:")
        for date in exception_dates:
            lines.append(f"- {format_iso_for_display(date.isoformat())}")
    else:
        lines.append("除外日時: なし")

    return "\n".join(lines)

def decode_iso_dates(date_values):
    decoded_dates = []
    for value in date_values:
        if value:
            decoded_dates.append(datetime.fromisoformat(value))
    return decoded_dates


def save_exception_dates(user_id, dates):
    unique_dates = sorted(set(dates))
    if not unique_dates:
        return 0

    existing_response = (
        supabase.table("exceptions_date")
        .select("date")
        .eq("user_id", user_id)
        .execute()
    )
    existing_dates = {
        datetime.fromisoformat(row["date"])
        for row in (existing_response.data or [])
        if row.get("date")
    }
    payload = [
        {"user_id": user_id, "date": dt.isoformat()}
        for dt in unique_dates
        if dt not in existing_dates
    ]
    if not payload:
        return 0

    supabase.table("exceptions_date").insert(payload).execute()
    return len(payload)


def remove_exception_dates(user_id, dates):
    unique_dates = sorted(set(dates))
    removed_count = 0
    for dt in unique_dates:
        response = (
            supabase.table("exceptions_date")
            .delete()
            .eq("user_id", user_id)
            .eq("date", dt.isoformat())
            .execute()
        )
        removed_count += len(response.data or [])
    return removed_count


def build_liff_remove_url():
    if not APP_BASE_URL:
        return None
    return f"{APP_BASE_URL}/liff/exclude-remove"


def format_iso_for_display(value):
    dt_obj = datetime.fromisoformat(value)
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    weekday = weekdays[dt_obj.weekday()]
    return dt_obj.strftime(f"%Y年%m月%d日（{weekday}）%H:%M")


set_notification_date = {
    "template": {
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
    }
}


modify_date = {
    "template": {
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
}


stop_notification = {
    "template": {
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
    }
}


def create_modify_msg(selected_date):
    return {
        "altText": f"通知対象日を {selected_date} に変更しますか？",
        "template": {
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
    }


def create_start_msg(selected_date):
    return {
        "altText": f"{selected_date} までの空き情報の通知を開始しますか？",
        "template": {
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
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
