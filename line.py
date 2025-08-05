
#テスト用　絶対コミットしないこと
LINE_TOKEN = "test"
USER_ID = "REMOVED"

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