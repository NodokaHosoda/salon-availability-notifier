from flask import Flask, request, abort
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

# Webhook受信用
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

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
            alt_text=start_notification["altText"],
            template=start_notification["template"]
        )
    elif received_text == "通知停止":
        reply_msg = TemplateSendMessage(
            alt_text=stop_notification["altText"],
            template=stop_notification["template"]
        )
    elif received_text == "日付変更":
        reply_msg = TemplateSendMessage(
            alt_text=modify_date["altText"],
            template=modify_date["template"]
        )
    else:
        reply_msg = TextSendMessage(
            text="「通知開始」「通知停止」「日付変更」のいずれかを送信してください。"
        )
    line_bot_api.reply_message(event.reply_token, reply_msg)


modify_date = {
  "type": "template",
  "altText": "This is a buttons template",
  "template": {
    "type": "buttons",
    "title": "Menu",
    "text": "Please select",
    "actions": [
      {
        "type": "datetimepicker",
        "label": "Select date",
        "data": "storeId=12345",
        "mode": "date"
      },
      {
        "type": "postback",
        "label": "Buy",
        "data": "action=modify_date"
      }
    ]
  }
}

stop_notification = {
  "type": "template",
  "altText": "this is a confirm template",
  "template": {
    "type": "confirm",
    "text": "通知を止めますか？",
    "actions": [
      {
        "type": "message",
        "label": "Yes",
        "text": "はい"
      },
      {
        "type": "message",
        "label": "No",
        "text": "いいえ"
      }
    ]
  }
}

start_notification = {
  "type": "template",
  "altText": "this is a confirm template",
  "template": {
    "type": "buttons",
    "text": "通知を止めますか？",
    "actions": [
      {
        "type": "datetimepicker",
        "label": "Select date",
        "data": "action=start",
        "mode": "date"
      },
      {
        "type": "message",
        "label": "Yes",
        "text": "はい"
      },
      {
        "type": "message",
        "label": "No",
        "text": "いいえ"
      }
    ]
  }
}

@app.route("/")
def index():
    return "LINE Bot is running on Cloud Run!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)