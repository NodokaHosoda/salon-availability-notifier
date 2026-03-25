from urllib.parse import parse_qs
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage,FollowEvent,
    TemplateSendMessage, TextSendMessage, PostbackEvent
)
import os
from supabase import create_client

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 環境変数からLINEの設定を取得
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/")
def index():
    return "LINE Bot is running on Cloud Run!"

# Webhook受信用
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    print("Request body:", body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# 新規ユーザ登録
@handler.add(FollowEvent)
def handle_follow(event):
    line_user_id = event.source.user_id  # LINEのユーザーID
    # すでに登録済みか確認
    response = supabase.table("user_info") \
        .select("id") \
        .eq("line_user_id", line_user_id) \
        .execute()

    if not response.data:  
      # 新規登録
      response = supabase.table("user_info").insert({
          "line_user_id": line_user_id,
          "line_user_name": None  # 取得できればセット
      }).execute()
      supabase.table("notification_setting").insert({
          "user_id": response.data[0]["id"],
          "last_date": None,
          "get_notification": False
      }).execute()
      print("新規ユーザーを登録しました")


# メッセージ受信イベント
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    received_text = event.message.text
    user_id = get_user_id(event)

    if received_text == "通知開始":
        if is_notification_enabled(user_id):
            reply_msg = TextSendMessage(text="通知は既に有効になっています。新しい通知を開始するには、まず現在の通知を停止してください。")
            line_bot_api.reply_message(event.reply_token, reply_msg)
            return
        reply_msg = TemplateSendMessage(
            alt_text=set_notification_date["altText"],
            template=set_notification_date["template"]
        )
        
    elif received_text == "通知停止":
        if not is_notification_enabled(user_id):
            reply_msg = TextSendMessage(text="通知は既に停止されています。")
            line_bot_api.reply_message(event.reply_token, reply_msg)
            return
        reply_msg = TemplateSendMessage(
            alt_text=stop_notification["altText"],
            template=stop_notification["template"]
        )
    elif received_text == "日付変更":
        if not is_notification_enabled(user_id):
            reply_msg = TextSendMessage(text="通知が有効になっていません。まずは通知を開始してください。")
            line_bot_api.reply_message(event.reply_token, reply_msg)
            return
        reply_msg = TemplateSendMessage(
            alt_text=modify_date["altText"],
            template=modify_date["template"]
        )
    elif received_text == "日付確認":
        if not is_notification_enabled(user_id):
            reply_msg = TextSendMessage(text="通知が有効になっていません。")
            line_bot_api.reply_message(event.reply_token, reply_msg)
            return
        user_id = get_user_id(event)
        registered_date = get_registered_date(user_id)
        reply_msg = TextSendMessage(text= registered_date)
    else:
        return
    line_bot_api.reply_message(event.reply_token, reply_msg)


@handler.add(PostbackEvent)
def handle_postback(event):
    action = event.postback.data
    selected_date = None

    # datetimepickerのときだけparamsに含まれる
    if event.postback.params:
        selected_date = event.postback.params.get("date")

    # confirm_xxx の場合は data 内に入っているのでパースする
    data_dict = parse_qs(event.postback.data)
    if "date" in data_dict:
        selected_date = data_dict["date"][0]
    if "action" in data_dict:
        action = data_dict["action"][0]
        
    user_id = get_user_id(event)

    if action == "start":
        data = create_start_msg(selected_date)
        reply_msg = TemplateSendMessage(
            alt_text=data["altText"],
            template=data["template"]
        )
    elif action == "modify":
        data = create_modify_msg(selected_date)
        reply_msg = TemplateSendMessage(
            alt_text=data["altText"],
            template=data["template"]
        )
    elif action == "stop":
        supabase.table("notification_setting") \
            .update({"get_notification": False, "last_date": None}) \
            .eq("user_id", user_id) \
            .execute()
        # 除外日時を削除
        supabase.table("exceptions_date") \
            .delete() \
            .eq("user_id", user_id) \
            .execute()
        reply_msg = TextSendMessage(text="通知を停止しました")

    elif "confirm_start" in action:
        update_last_date(user_id, selected_date)
        supabase.table("notification_setting") \
            .update({"get_notification": True}) \
            .eq("user_id", user_id) \
            .execute()
        reply_msg = TextSendMessage(text=f"{selected_date}までの空き情報の通知を開始しました")

    elif "confirm_modify" in action:
        update_last_date(user_id, selected_date)
        reply_msg = TextSendMessage(text=f"日付を{selected_date}に変更しました")

    line_bot_api.reply_message(event.reply_token, reply_msg)

def is_notification_enabled(user_id):
    """指定ユーザーの通知設定が ON かどうかを返す"""
    response = supabase.table("notification_setting") \
        .select("get_notification") \
        .eq("user_id", user_id) \
        .execute()

    if response.data and response.data[0]["get_notification"]:
        return True
    return False

def update_last_date(user_id, new_date):
    supabase.table("notification_setting") \
        .update({"last_date": new_date}) \
        .eq("user_id", user_id) \
        .execute()

def get_registered_date(user_id):
  last_date = supabase.table("notification_setting").select("last_date").eq("user_id", user_id).execute()
  if not last_date.data:
    return "日付が設定されていません。"
  exception_dates = supabase.table("exceptions_date").select("date").eq("user_id", user_id).execute()

  message = f"登録中の日付: {last_date.data[0]['last_date']}"
  if exception_dates.data:
    message += "\n通知除外日時:\n"
    for date in exception_dates.data:
      message += f"- {date['date']}\n"
  return message

def get_user_id(event):
    line_user_id = event.source.user_id
    res = supabase.table("user_info").select("id").eq("line_user_id", line_user_id).single().execute()
    return res.data['id']

# 定型メッセージ
set_notification_date = {
  "type": "template",
  "altText": "何日までの空き情報を確認したいか、日付を選択し「送信」を押してください。",
  "template": {
    "type": "buttons",
    "title": "通知開始：日付選択",
    "text": "何日まで空き情報を確認したいか、日付を選択し「送信」を押してください。",
    "actions": [
      {
        "type": "datetimepicker",
        "label": "日付を選択",
        "data": "start",
        "mode": "date"
      }
    ]
  }
}

modify_date = {
  "type": "template",
  "altText": "日付を変更します。新しい日付を選択し「送信」を押してください。",
  "template": {
    "type": "buttons",
    "title": "日付変更：日付選択",
    "text": "日付を変更します。新しい日付を選択し「送信」を押してください。",
    "actions": [
      {
        "type": "datetimepicker",
        "label": "日付を選択",
        "data": "modify",
        "mode": "date"
      }
    ]
  }
}

stop_notification = {
  "type": "template",
  "altText": "通知を止めますか？",
  "template": {
    "type": "confirm",
    "title": "通知停止",
    "text": "通知を止めますか？",
    "actions": [
      {
        "type": "postback",
        "label": "はい",
        "text": "はい",
        "data": "stop"
      },
      {
        "type": "message",
        "label": "いいえ",
        "text": "いいえ"
      }
    ]
  }
}

def create_modify_msg(selected_date):
  confirm_modified_date = {
    "type": "template",
    "altText": f"日付を{selected_date}に変更しますか？",
    "template": {
      "type": "confirm",
      "title": "日付変更：確認",
      "text": f"日付を{selected_date}に変更しますか？",
      "actions": [
        {
          "type": "postback",
          "label": "はい",
          "text": "はい",
          "data": f"action=confirm_modify&date={selected_date}"
        },
        {
          "type": "message",
          "label": "いいえ",
          "text": "いいえ"
        }
      ]
    }
  }
  return confirm_modified_date

def create_start_msg(selected_date):
  start_notification = {
    "type": "template",
    "altText": f"{selected_date}までの空き情報の通知を開始しますか？",
    "template": {
      "type": "confirm",
      "title": "通知開始：確認",
      "text": f"{selected_date}までの空き情報の通知を開始しますか？",
      "actions": [
        {
          "type": "postback",
          "label": "はい",
          "text": "はい",
          "data": f"action=confirm_start&date={selected_date}"
        },
        {
          "type": "message",
          "label": "いいえ",
          "text": "いいえ"
        }
      ]
    }
  }
  return start_notification

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
