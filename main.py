from datetime import datetime
from urllib.parse import parse_qs
import json
from pathlib import Path
import os
import traceback

from flask import Flask, abort, jsonify, render_template, request
from google.cloud import tasks_v2
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
from utils import clear_notification_state, decode_compact_datetimes, format_grouped_datetimes_for_display
from scraper import send_line_message

load_dotenv()
load_dotenv(dotenv_path=Path.home() / ".env", override=False)

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LIFF_EXCLUDE_ADD_ID = os.environ.get("LIFF_EXCLUDE_ADD_ID")
LIFF_EXCLUDE_REMOVE_ID = os.environ.get("LIFF_EXCLUDE_REMOVE_ID")
LIFF_REGISTRATION_ID = os.environ.get("LIFF_REGISTRATION_ID")
APP_BASE_URL = os.environ.get("APP_BASE_URL").rstrip("/")
CLOUD_TASKS_PROJECT_ID = os.environ.get("CLOUD_TASKS_PROJECT_ID")
CLOUD_TASKS_LOCATION = os.environ.get("CLOUD_TASKS_LOCATION")
CLOUD_TASKS_QUEUE = os.environ.get("CLOUD_TASKS_QUEUE")
IMMEDIATE_CHECK_TASK_URL = os.environ.get("IMMEDIATE_CHECK_TASK_URL", f"{APP_BASE_URL}/tasks/immediate-check")
IMMEDIATE_CHECK_TASK_SECRET = os.environ.get("IMMEDIATE_CHECK_TASK_SECRET")

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


@app.route("/liff/registration-summary")
def liff_registration_summary():
    return render_template(
        "liff_registration_summary.html",
        liff_id=LIFF_REGISTRATION_ID,
        page_title="登録情報を確認",
        remove_url=build_liff_remove_url(),
    )


@app.route("/api/exceptions", methods=["GET"])
def api_get_exceptions():
    user_id = get_user_id_from_request()
    try:
        response = (
            supabase.table("exceptions_date")
            .select("date")
            .eq("user_id", user_id)
            .order("date")
            .execute()
        )
        dates = [row["date"] for row in (response.data or []) if row.get("date")]
        return jsonify({"dates": dates})
    except Exception as exc:
        print(f"[api/exceptions:get] user_id={user_id} failed: {exc}")
        return jsonify({"error": "除外日一覧の取得に失敗しました。"}), 500


@app.route("/api/exceptions", methods=["POST"])
def api_add_exceptions():
    user_id = get_user_id_from_request()
    payload = request.get_json(silent=True) or {}
    dates = payload.get("dates", [])
    try:
        saved_count = save_exception_dates(user_id, decode_iso_dates(dates))
        return jsonify({"saved_count": saved_count})
    except Exception as exc:
        print(f"[api/exceptions:add] user_id={user_id} dates={dates} failed: {exc}")
        return jsonify({"error": "除外日の追加に失敗しました。"}), 500


@app.route("/api/exceptions/remove", methods=["POST"])
def api_remove_exceptions():
    user_id = get_user_id_from_request()
    payload = request.get_json(silent=True) or {}
    dates = payload.get("dates", [])
    try:
        removed_count = remove_exception_dates(user_id, decode_iso_dates(dates))
        return jsonify({"removed_count": removed_count})
    except Exception as exc:
        print(f"[api/exceptions:remove] user_id={user_id} dates={dates} failed: {exc}")
        return jsonify({"error": "除外日の解除に失敗しました。"}), 500

@app.route("/api/registration-summary", methods=["GET"])
def api_registration_summary():
    user_id = get_user_id_from_request()
    try:
        return jsonify(get_registration_summary_payload(user_id))
    except Exception as exc:
        print(f"[api/registration-summary] user_id={user_id} failed: {exc}")
        return jsonify({"error": "登録情報の取得に失敗しました。"}), 500


@app.route("/tasks/immediate-check", methods=["POST"])
def task_immediate_check():
    expected_secret = IMMEDIATE_CHECK_TASK_SECRET.strip()
    if expected_secret and request.headers.get("X-Task-Secret", "").strip() != expected_secret:
        abort(401)

    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    line_user_id = payload.get("line_user_id")
    if not user_id or not line_user_id:
        abort(400)

    try:
        send_line_message(
            get_notification_target_date(user_id),
            line_user_id,
            user_id,
            set(get_exception_dates(user_id)),
            compare_with_last=False,
        )
    except Exception as exc:
        traceback.print_exception(type(exc), exc, exc.__traceback__)
        line_bot_api.push_message(
            line_user_id,
            TextSendMessage(text="即時確認に失敗しました。時間をおいてもう一度お試しください。"),
        )

    return ("", 204)



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
            try:
                enqueue_immediate_check(user_id, event.source.user_id)
            except Exception as exc:
                traceback.print_exception(type(exc), exc, exc.__traceback__)
                line_bot_api.push_message(
                    event.source.user_id,
                    TextSendMessage(text="即時確認の受付に失敗しました。時間をおいてもう一度お試しください。"),
                )
            return
    elif received_text == "登録情報確認":
        registration_url = build_liff_registration_url()
        if not registration_url:
            reply_msg = TextSendMessage(text=get_registration_summary(user_id))
        else:
            reply_msg = TemplateSendMessage(
                alt_text="登録情報の確認画面を開きます。",
                template={
                    "type": "buttons",
                    "title": "登録情報を確認",
                    "text": "通知状態、除外日時、最新の空き状況を確認できます。",
                    "actions": [
                        {
                            "type": "uri",
                            "label": "画面を開く",
                            "uri": registration_url,
                        }
                    ],
                },
            )
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
        clear_notification_state(user_id)
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
        .select("last_date,get_notification,last_available_dates")
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



def enqueue_immediate_check(user_id, line_user_id):
    if not CLOUD_TASKS_PROJECT_ID or not IMMEDIATE_CHECK_TASK_URL:
        raise RuntimeError("Cloud Tasks configuration is incomplete")

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(CLOUD_TASKS_PROJECT_ID, CLOUD_TASKS_LOCATION, CLOUD_TASKS_QUEUE)

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": IMMEDIATE_CHECK_TASK_URL,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "user_id": user_id,
                    "line_user_id": line_user_id,
                }
            ).encode(),
        }
    }
    if IMMEDIATE_CHECK_TASK_SECRET:
        task["http_request"]["headers"]["X-Task-Secret"] = IMMEDIATE_CHECK_TASK_SECRET

    client.create_task(parent=parent, task=task)


def get_registration_summary_payload(user_id):
    notification_row = get_notification_settings(user_id)
    return {
        "notification_enabled": bool(notification_row.get("get_notification")),
        "last_date": notification_row.get("last_date"),
        "exception_dates": [dt.isoformat() for dt in get_exception_dates(user_id)],
        "latest_available_dates": decode_compact_datetimes(notification_row.get("last_available_dates") or []),
    }


def get_registration_summary(user_id):
    payload = get_registration_summary_payload(user_id)

    lines = [f"通知状態: {'ON' if payload['notification_enabled'] else 'OFF'}"]
    if payload["notification_enabled"]:
        lines.append(f"通知期限日: {payload['last_date'] or '未設定'}")

    if payload["exception_dates"]:
        lines.append("除外日時:")
        lines.extend(format_grouped_datetimes_for_display(payload["exception_dates"], include_bullet=True))
    else:
        lines.append("除外日時: なし")

    if payload["latest_available_dates"]:
        lines.append("最新の空き状況:")
        lines.extend(format_grouped_datetimes_for_display(payload["latest_available_dates"], include_bullet=True))
    else:
        lines.append("最新の空き状況: なし")

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


def build_liff_registration_url():
    if not APP_BASE_URL:
        return None
    return f"{APP_BASE_URL}/liff/registration-summary"




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
