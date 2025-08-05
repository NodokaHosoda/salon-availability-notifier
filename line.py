
#テスト用　絶対コミットしないこと
LINE_TOKEN = "ZcqqXe0w0pg75HCzCGfkJx3QYsOLebMQ5WUIWNHf1Ir0MuxUoVqYdE4RvwnuTlZVspE+pF3/aXkeBwUlIvtohGxdzslHXvnabYb+tJxd8PjizbYrNeqLpRCscxAEIQ/MSCC8sTL6VYKvbvymPeflBAdB04t89/1O/w1cDnyilFU="
USER_ID = "U69f07b1dcbe735e25996a8d9a06ac33e"

def send_line_message(message):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    body = {
        "to": USER_ID,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    response = requests.post(url, headers=headers, data=json.dumps(body))

interact_message = {
    "type": "template",
    "altText": "This is a buttons template",
    "template": {
      "type": "buttons",
      "title": "Menu",
      "text": "空き情報の通知設定",
      "actions": [
        {
          "type": "datepicker",
          "label": "date",
          "data": "action=date",
          "mode": "date",
          },
        {
          "type": "action",
          "action": {
            "type": "message",
            "label": "start",
            "text": "上記の日付以前の空き情報の通知を受け取る"
          }
        },
        {
          "type": "action",
          "action": {
            "type": "message",
            "label": "stop",
            "text": "通知を止める"
          }
        }
      ]
    }
  }