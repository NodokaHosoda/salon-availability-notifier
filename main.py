from datetime import datetime
from urllib.parse import parse_qs
import json
import os
import traceback

from flask import Flask, abort, jsonify, render_template, request
from google.cloud import tasks_v2
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    FollowEvent,
    MessageEvent,
    PostbackEvent,
    TextMessage,
    TextSendMessage,
)

from availability_notifier import check_and_send_availability
from clients import get_line_bot_api, get_webhook_handler
from config import get_settings
from line_templates import (
    build_modify_confirmation_message,
    build_modify_date_message,
    build_set_notification_date_message,
    build_start_confirmation_message,
    build_stop_notification_message,
)
from registration_summary_service import build_registration_summary_payload
from repositories import (
    clear_notification_state,
    get_exception_dates,
    get_notification_target_date,
    get_or_create_user,
    get_user_id_from_line_user_id,
    is_notification_enabled,
    remove_exception_dates,
    save_exception_dates,
    set_notification_enabled,
    update_last_date,
)

settings = get_settings()
line_bot_api = get_line_bot_api()
handler = get_webhook_handler()

app = Flask(__name__)

NORMALIZED_APP_BASE_URL = settings.app_base_url.rstrip("/")
DEFAULT_IMMEDIATE_CHECK_TASK_URL = f"{NORMALIZED_APP_BASE_URL}/tasks/immediate-check"


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
        dates = [dt.isoformat() for dt in get_exception_dates(user_id)]
        return jsonify({"dates": dates})
    except Exception as exc:
        print(f"[api/exceptions:get] user_id={user_id} failed: {exc}")
        return jsonify({"error": "除外日一覧の取得に失敗しました。"}), 500


@app.route("/api/exceptions", methods=["POST"])
def api_add_exceptions():
    user_id = require_user_id_from_request()
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
    user_id = require_user_id_from_request()
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
    user_id = require_user_id_from_request()
    try:
        return jsonify(build_registration_summary_payload(user_id))
    except Exception as exc:
        print(f"[api/registration-summary] user_id={user_id} failed: {exc}")
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

    try:
        # 即時確認は通常の送信経路を使うが、差分がない場合の通知抑止は行わない。
        check_and_send_availability(
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
    get_or_create_user(event.source.user_id)


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    received_text = event.message.text
    user_id = require_user_id_from_line_user_id(event.source.user_id)

    if received_text == "通知設定":
        if is_notification_enabled(user_id):
            reply_msg = build_stop_notification_message()
        else:
            reply_msg = build_set_notification_date_message()
    elif received_text == "日付変更":
        if not is_notification_enabled(user_id):
            reply_msg = TextSendMessage(text="通知が有効になっていません。まずは通知を開始してください。")
            line_bot_api.reply_message(event.reply_token, reply_msg)
            return
        reply_msg = build_modify_date_message(get_notification_target_date(user_id))
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
    else:
        return

    line_bot_api.reply_message(event.reply_token, reply_msg)


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

    user_id = require_user_id_from_line_user_id(event.source.user_id)

    if action == "start":
        reply_msg = build_start_confirmation_message(selected_date)
    elif action == "modify":
        reply_msg = build_modify_confirmation_message(selected_date)
    elif action == "stop":
        clear_notification_state(user_id)
        reply_msg = TextSendMessage(text="通知を停止しました。")
    elif action == "confirm_start":
        update_last_date(user_id, selected_date)
        set_notification_enabled(user_id, True)
        reply_msg = TextSendMessage(text=f"{selected_date} までの空き情報の通知を開始しました。")
    elif action == "confirm_modify":
        update_last_date(user_id, selected_date)
        reply_msg = TextSendMessage(text=f"通知対象日を {selected_date} に変更しました。")
    else:
        reply_msg = TextSendMessage(text="操作を処理できませんでした。")

    line_bot_api.reply_message(event.reply_token, reply_msg)



def require_user_id_from_request():
    # LIFF / API では転送されたヘッダーから対象の LINE ユーザーを特定し、存在しなければここで失敗させる。
    line_user_id = request.headers.get("X-Line-User-Id", "").strip()
    if not line_user_id:
        abort(401)
    return require_user_id_from_line_user_id(line_user_id)



def require_user_id_from_line_user_id(line_user_id):
    # 404 への変換をここに寄せて、各 handler 側では業務分岐だけを見る。
    user_id = get_user_id_from_line_user_id(line_user_id)
    if not user_id:
        abort(404)
    return user_id



def enqueue_immediate_check(user_id, line_user_id):
    if not settings.cloud_tasks_project_id or not (
        settings.immediate_check_task_url or DEFAULT_IMMEDIATE_CHECK_TASK_URL
    ):
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
            "url": settings.immediate_check_task_url or DEFAULT_IMMEDIATE_CHECK_TASK_URL,
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



def decode_iso_dates(date_values):
    decoded_dates = []
    for value in date_values:
        if value:
            decoded_dates.append(datetime.fromisoformat(value))
    return decoded_dates


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
