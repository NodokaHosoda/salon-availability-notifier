自分の行きつけの美容院の予約空き情報通知サービスです。

指定した期限日までの空き枠を定期的に確認し、LINE に通知します。あわせて LIFF 画面から通知対象日、除外日時、最新の登録情報を確認できるようにしています。公開サービスではなく、自分と身内用で使っているツールです。

## 課題
自分が通っている美容院は予約が埋まりやすく、普通に予約しようとすると 1 か月先くらいまで埋まっていることがあります。一方でキャンセルはわりと発生するため、空き枠が出たタイミングをすぐに知れれば、もっと近い日時で予約を取らことができます。
このプロジェクトは、予約の空き情報を監視し、空きが出たらすぐ LINE で受け取れるようにするために作りました。これによって、より近い日時で予約を取りやすくすることを狙っています。

## 主な機能
- **通知開始と停止**: LINE から通知の開始・停止を切り替えられます。
- **通知対象日の設定**: 何日までの空き情報を追いかけるかを設定、変更できます。
- **即時確認**: 定期実行を待たず、その場で最新の空き状況を確認できます。
- **定期通知**: 日中1時間ごとに空き情報に更新がないかチェックをし、新しく増えた空き枠があるときのみ通知します。
- **除外日時の管理**: 通知したくない日時を除外日時として追加・解除できます。
- **登録情報確認**: ラインの画面で通知状態、通知期限日、除外日時、最新の空き状況を確認できます。

## 主な構成
- **[main.py](./main.py)**: Flask アプリ。LINE webhook、LIFF ページ、設定用 API、即時確認タスクの入口を持つ。
- **[scheduled_notifier.py](./scheduled_notifier.py)**: 定期実行の runner。通知対象ユーザーを走査して通知処理を呼ぶ。
- **[availability_checker.py](./availability_checker.py)**: Hot Pepper 側を巡回して空き枠を取得する。
- **[availability_notifier.py](./availability_notifier.py)**: 通知本文の組み立て、差分判定、LINE push、last_available_dates 更新を担う。
- **[repositories.py](./repositories.py)**: Supabase への永続化アクセスをまとめる。
- **[line_templates.py](./line_templates.py)**: LINE の template message をまとめる。
- **[config.py](./config.py)**: env 読み込みをまとめる。
- **[templates](./templates)** / **[static](./static)**: LIFF の画面とフロントエンド資産。

## 補足
- スクレイピング部分を書き換えれば他の予約サイトの監視にも応用できる余地はありますが、現状は自分が通う美容院の予約導線や自分の運用にかなり寄せて作っており、汎用ツールとしては設計していません。

![チャット画面（通知時）](https://github.com/user-attachments/assets/6efb41c1-5c1d-459c-a90c-3d82ab6445af)

![登録情報画面](https://github.com/user-attachments/assets/fcd7f7b9-cc98-47f6-abfb-275f6c2bd138)
