from datetime import datetime
from urllib.parse import parse_qs
import json
import os

from flask import Flask, abort, jsonify, render_template, request
from google.cloud import tasks_v2
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    FollowEvent,
    MessageEvent,
    PostbackEvent,
    TextMessage,
    TextSendMessage,
)

from availability_notifier import check_and_send_availability
from config import get_settings
from driver_license_notifier import (
    check_and_send_driver_license_availability,
    decode_driver_last_available_date_texts,
)
from line_templates import (
    build_modify_confirmation_message,
    build_modify_date_message,
    build_set_notification_date_message,
    build_start_confirmation_message,
    build_stop_notification_message,
)
from repositories import (
    DRIVER_LICENSE_USER_TYPE,
    exception_date_repository,
    notification_setting_repository,
    user_info_repository,
)
from utils import decode_compact_datetimes, log_exception_details

settings = get_settings()
line_bot_api = LineBotApi(settings.line_channel_access_token)
handler = WebhookHandler(settings.line_channel_secret)

app = Flask(__name__)

NORMALIZED_APP_BASE_URL = settings.app_base_url.rstrip("/")
IMMEDIATE_CHECK_TASK_URL = f"{NORMALIZED_APP_BASE_URL}/tasks/immediate-check"


@app.route("/")
def index():
    return "LINE Bot is running on Cloud Run!"


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@app.route("/liff/exclude-add")
def liff_exclude_add():
    return render_template(
        "liff_exclude_add.html",
        liff_id=settings.liff_exclude_add_id,
        page_title="除外日を追加",
    )


@app.route("/liff/exclude-remove")
def liff_exclude_remove():
    return render_template(
        "liff_exclude_remove.html",
        liff_id=settings.liff_exclude_remove_id,
        page_title="除外日を解除",
    )


@app.route("/liff/registration-summary")
def liff_registration_summary():
    return render_template(
        "liff_registration_summary.html",
        liff_id=settings.liff_registration_id,
        page_title="登録情報を確認",
    )


@app.route("/api/exceptions", methods=["GET"])
def api_get_exceptions():
    user_id = require_user_id_from_request()
    try:
        dates = [dt.isoformat() for dt in exception_date_repository.list_dates(user_id)]
        return jsonify({"dates": dates})
    except Exception as exc:
        log_exception_details(f"api/exceptions:get user_id={user_id}", exc)
        return jsonify({"error": "除外日一覧の取得に失敗しました。"}), 500


@app.route("/api/exceptions", methods=["POST"])
def api_add_exceptions():
    user_id = require_user_id_from_request()
    payload = request.get_json(silent=True) or {}
    dates = payload.get("dates", [])
    try:
        saved_count = exception_date_repository.save_dates(user_id, decode_iso_dates(dates))
        return jsonify({"saved_count": saved_count})
    except Exception as exc:
        log_exception_details(f"api/exceptions:add user_id={user_id} dates={dates}", exc)
        return jsonify({"error": "除外日の追加に失敗しました。"}), 500


@app.route("/api/exceptions/remove", methods=["POST"])
def api_remove_exceptions():
    user_id = require_user_id_from_request()
    payload = request.get_json(silent=True) or {}
    dates = payload.get("dates", [])
    try:
        removed_count = exception_date_repository.remove_dates(user_id, decode_iso_dates(dates))
        return jsonify({"removed_count": removed_count})
    except Exception as exc:
        log_exception_details(f"api/exceptions:remove user_id={user_id} dates={dates}", exc)
        return jsonify({"error": "除外日の解除に失敗しました。"}), 500


@app.route("/api/registration-summary", methods=["GET"])
def api_registration_summary():
    user_id = require_user_id_from_request()
    try:
        return jsonify(build_registration_summary_payload(user_id))
    except Exception as exc:
        log_exception_details(f"api/registration-summary user_id={user_id}", exc)
        return jsonify({"error": "登録情報の取得に失敗しました。"}), 500


@app.route("/tasks/immediate-check", methods=["POST"])
def task_immediate_check():
    expected_secret = settings.immediate_check_task_secret.strip()
    if expected_secret and request.headers.get("X-Task-Secret", "").strip() != expected_secret:
        abort(401)

    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    line_user_id = payload.get("line_user_id")
    if not user_id or not line_user_id:
        abort(400)

    request_date = notification_setting_repository.get_last_date(user_id)
    if not request_date:
        return ("", 204)

    try:
        user_type = user_info_repository.get_user_type_by_id(user_id)
        if user_type == DRIVER_LICENSE_USER_TYPE:
            check_and_send_driver_license_availability(
                request_date,
                line_user_id,
                user_id,
                compare_with_last=False,
            )
        else:
            # 即時確認は通常の送信経路を使うが、差分がない場合の通知抑止は行わない。
            check_and_send_availability(
                request_date,
                line_user_id,
                user_id,
                set(exception_date_repository.list_dates(user_id)),
                compare_with_last=False,
            )
    except Exception as exc:
        line_bot_api.push_message(
            line_user_id,
            TextSendMessage(text="即時確認に失敗しました。時間をおいてもう一度お試しください。"),
        )

    return ("", 204)


@handler.add(FollowEvent)
def handle_follow(event):
    line_user_id = event.source.user_id
    user_info_repository.get_or_create_user(
        line_user_id,
        get_line_profile_name_or_none(line_user_id),
    )

def get_line_profile_name_or_none(line_user_id):
    try:
        return line_bot_api.get_profile(line_user_id).display_name
    except Exception:
        return None


def build_notification_not_enabled_message():
    return TextSendMessage(text="通知が有効になっていません。まずは通知を開始してください。")


def handle_notification_setting_message(event, user_id):
    if notification_setting_repository.is_enabled(user_id):
        reply_msg = build_stop_notification_message()
    else:
        reply_msg = build_set_notification_date_message()
    line_bot_api.reply_message(event.reply_token, reply_msg)


def handle_modify_date_message_command(event, user_id):
    if not notification_setting_repository.is_enabled(user_id):
        line_bot_api.reply_message(event.reply_token, build_notification_not_enabled_message())
        return

    reply_msg = build_modify_date_message(notification_setting_repository.get_last_date(user_id))
    line_bot_api.reply_message(event.reply_token, reply_msg)


def handle_immediate_check_message(event, user_id):
    if not notification_setting_repository.is_enabled(user_id):
        line_bot_api.reply_message(event.reply_token, build_notification_not_enabled_message())
        return

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="現在の空き状況を確認しています。"),
    )
    try:
        enqueue_immediate_check(user_id, event.source.user_id)
    except Exception as exc:
        log_exception_details(
            f"message:immediate-check user_id={user_id} line_user_id={event.source.user_id}",
            exc,
        )
        line_bot_api.push_message(
            event.source.user_id,
            TextSendMessage(text="即時確認の受付に失敗しました。時間をおいてもう一度お試しください。"),
        )


def handle_account_registration_message(event):
    line_user_id = event.source.user_id
    user_name = get_line_profile_name_or_none(line_user_id)
    existing_user_id = user_info_repository.get_user_id(line_user_id)

    try:
        user_info_repository.get_or_create_user(line_user_id, user_name)
    except Exception:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="アカウント登録に失敗しました。時間をおいて再度お試しください。"),
        )
        return

    message_text = "アカウント登録は完了済みです。" if existing_user_id else "アカウント登録が完了しました。"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=message_text),
    )


def handle_driver_license_mode_message(event, user_id):
    try:
        user_info_repository.update_user_type(user_id, DRIVER_LICENSE_USER_TYPE)
        notification_setting_repository.clear_state(user_id)
    except Exception as exc:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="運転免許通知への切り替えに失敗しました。時間をおいて再度お試しください。"),
        )
        return

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="運転免許通知モードに切り替えました。通知設定から期限日を設定してください。"),
    )


MESSAGE_HANDLERS = {
    "通知設定": handle_notification_setting_message,
    "日付変更": handle_modify_date_message_command,
    "即時確認": handle_immediate_check_message,
    "運転免許": handle_driver_license_mode_message,
}


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    if event.message.text == "アカウント登録":
        handle_account_registration_message(event)
        return

    message_handler = MESSAGE_HANDLERS.get(event.message.text)
    if not message_handler:
        return

    user_id = require_user_id_from_line_user_id(
        event.source.user_id,
        source=f"message:{event.message.text}",
    )
    message_handler(event, user_id)


@handler.add(PostbackEvent)
def handle_postback(event):
    action = event.postback.data
    selected_date = None

    if event.postback.params:
        selected_date = event.postback.params.get("date")

    # datetimepicker の値は params に入り、confirm 系の操作は data 文字列側に入る。
    data_dict = parse_qs(event.postback.data)
    if "date" in data_dict:
        selected_date = data_dict["date"][0]
    if "action" in data_dict:
        action = data_dict["action"][0]

    user_id = require_user_id_from_line_user_id(
        event.source.user_id,
        source=f"postback:{action}",
    )

    if action == "start":
        reply_msg = build_start_confirmation_message(selected_date)
    elif action == "modify":
        reply_msg = build_modify_confirmation_message(selected_date)
    elif action == "stop":
        notification_setting_repository.clear_state(user_id)
        exception_date_repository.clear_dates(user_id)
        reply_msg = TextSendMessage(text="通知を停止しました。")
    elif action == "confirm_start":
        notification_setting_repository.update_last_date(user_id, selected_date)
        notification_setting_repository.set_enabled(user_id, True)
        reply_msg = TextSendMessage(text=f"{selected_date} までの空き情報の通知を開始しました。")
    elif action == "confirm_modify":
        notification_setting_repository.update_last_date(user_id, selected_date)
        reply_msg = TextSendMessage(text=f"通知対象日を {selected_date} に変更しました。")
    else:
        reply_msg = TextSendMessage(text="操作を処理できませんでした。")

    line_bot_api.reply_message(event.reply_token, reply_msg)



def require_user_id_from_request():
    # LIFF / API では転送されたヘッダーから対象の LINE ユーザーを特定し、存在しなければここで失敗させる。
    line_user_id = request.headers.get("X-Line-User-Id", "").strip()
    if not line_user_id:
        abort(401)
    return require_user_id_from_line_user_id(line_user_id, source=f"request:{request.path}")



def require_user_id_from_line_user_id(line_user_id, source="unknown"):
    # 404 への変換をここに寄せて、各 handler 側では業務分岐だけを見る。
    user_id = user_info_repository.get_user_id(line_user_id)
    if not user_id:
        print(f"[user:not_registered] line_user_id={line_user_id} source={source}")
        abort(404)
    return user_id



def enqueue_immediate_check(user_id, line_user_id):
    if not settings.cloud_tasks_project_id:
        raise RuntimeError("Cloud Tasks configuration is incomplete")

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(
        settings.cloud_tasks_project_id,
        settings.cloud_tasks_location,
        settings.cloud_tasks_queue,
    )

    # ユーザー起点の即時確認も Cloud Tasks 経由に寄せて、同じバックエンド経路で実行する。
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
    if settings.immediate_check_task_secret:
        task["http_request"]["headers"]["X-Task-Secret"] = settings.immediate_check_task_secret

    client.create_task(parent=parent, task=task)



def build_registration_summary_payload(user_id):
    notification_row = notification_setting_repository.get_settings(user_id)
    user_type = user_info_repository.get_user_type_by_id(user_id)

    if user_type == DRIVER_LICENSE_USER_TYPE:
        latest_available_dates = decode_driver_last_available_date_texts(
            notification_row.get("driver_last_available_dates") or []
        )
    else:
        latest_available_dates = decode_compact_datetimes(
            notification_row.get("last_available_dates") or []
        )

    return {
        "notification_enabled": bool(notification_row.get("get_notification")),
        "notification_type": user_type,
        "last_date": notification_row.get("last_date"),
        "exception_dates": [dt.isoformat() for dt in exception_date_repository.list_dates(user_id)],
        "latest_available_dates": latest_available_dates,
    }



def decode_iso_dates(date_values):
    decoded_dates = []
    for value in date_values:
        if value:
            decoded_dates.append(datetime.fromisoformat(value))
    return decoded_dates


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
