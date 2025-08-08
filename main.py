from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage,
    TemplateSendMessage, ButtonsTemplate,
    DatePickerAction, MessageAction
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
    interact_message = create_interact_message()
    line_bot_api.reply_message(
        event.reply_token,
        interact_message
    )

def create_interact_message():
    buttons_template = ButtonsTemplate(
        title="Menu",
        text="空き情報の通知設定",
        actions=[
            DatePickerAction(
                label="date",
                data="action=date",
                mode="date"
            ),
            MessageAction(
                label="start",
                text="上記の日付以前の空き情報の通知を受け取る"
            ),
            MessageAction(
                label="stop",
                text="通知を止める"
            )
        ]
    )
    return TemplateSendMessage(
        alt_text="This is a buttons template",
        template=buttons_template
    )

@app.route("/")
def index():
    return "LINE Bot is running on Cloud Run!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)