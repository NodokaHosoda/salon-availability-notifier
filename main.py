from flask import Flask, request, abort
import sqlite3
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage,
    TemplateSendMessage, TextSendMessage
)
import os

app = Flask(__name__)

# 環境変数からLINEの設定を取得
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/")
def index():
    return "LINE Bot is running on Cloud Run!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

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

# メッセージ受信イベント
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    received_text = event.message.text

    if received_text == "通知開始":
        reply_msg = TemplateSendMessage(
            alt_text=set_notification_date["altText"],
            template=set_notification_date["template"]
        )
    elif received_text == "通知停止":
        reply_msg = TemplateSendMessage(
            alt_text=modify_date["altText"],
            template=modify_date["template"]
        )
    elif received_text == "日付変更":
        reply_msg = TemplateSendMessage(
            alt_text=modify_date["altText"],
            template=modify_date["template"]
        )
    elif received_text == "日付確認":
        registered_date = get_registered_date()
        reply_msg = TextSendMessage(text= registered_date)
    else:
        if received_text not in ["はい", "いいえ"]:
            reply_msg = TextSendMessage(
                text="「通知開始」「通知停止」「日付変更」のいずれかを送信してください。"
            )
    line_bot_api.reply_message(event.reply_token, reply_msg)


def get_registered_date():
  return "日付は設定されていません"

# 定型メッセージ
set_notification_date = {
  "type": "template",
  "altText": "何日まで空き情報を確認したいか、日付を選択し「送信」を押してください。",
  "template": {
    "type": "buttons",
    "text": "何日まで空き情報を確認したいか、日付を選択し「送信」を押してください。",
    "actions": [
      {
        "type": "datetimepicker",
        "label": "日付を選択",
        "data": "action=start",
        "mode": "date"
      }
    ]
  }
}

start_notification = {
  "type": "template",
  "altText": "上記の日付までの空き情報の通知を開始しますか？",
  "template": {
    "type": "confirm",
    "text": "上記の日付までの空き情報の通知を開始しますか？",
    "actions": [
      {
        "type": "message",
        "label": "はい",
        "text": "はい"
      },
      {
        "type": "message",
        "label": "いいえ",
        "text": "いいえ"
      }
    ]
  }
}

modify_date = {
  "type": "template",
  "altText": "日付を変更します。新しい日付を選択し「送信」を押してください。",
  "template": {
    "type": "buttons",
    "title": "Menu",
    "text": "日付を変更します。新しい日付を選択し「送信」を押してください。",
    "actions": [
      {
        "type": "datetimepicker",
        "label": "日付を選択",
        "data": "action=modify",
        "mode": "date"
      }
    ]
  }
}

confirm_modified_date = {
  "type": "template",
  "altText": "以上の日付に変更しますか？",
  "template": {
    "type": "confirm",
    "text": "以上の日付に変更しますか？",
    "actions": [
      {
        "type": "message",
        "label": "はい",
        "text": "はい"
      },
      {
        "type": "message",
        "label": "いいえ",
        "text": "いいえ"
      }
    ]
  }
}

stop_notification = {
  "type": "template",
  "altText": "通知を止めますか？",
  "template": {
    "type": "confirm",
    "text": "通知を止めますか？",
    "actions": [
      {
        "type": "message",
        "label": "はい",
        "text": "はい"
      },
      {
        "type": "message",
        "label": "いいえ",
        "text": "いいえ"
      }
    ]
  }
}