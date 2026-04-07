from datetime import datetime, timedelta, timezone

from availability_notifier import check_and_send_availability
from repositories import exception_date_repository, notification_setting_repository



def is_request_date_expired(request_date):
    current_jst_date = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
    return datetime.strptime(request_date, "%Y-%m-%d").date() < current_jst_date



def run_scheduled_checks():
    for target in notification_setting_repository.list_enabled_targets():
        request_date = target["last_date"]
        if not request_date:
            continue

        # JST で通知期限を過ぎたら通知対象から外し、保持していた状態もクリアする。
        if is_request_date_expired(request_date):
            notification_setting_repository.clear_state(target["user_id"])
            exception_date_repository.clear_dates(target["user_id"])
            continue

        line_user_id = target["line_user_id"]
        user_db_id = target["user_id"]
        try:
            check_and_send_availability(
                request_date,
                line_user_id,
                user_db_id,
                set(exception_date_repository.list_dates(user_db_id)),
            )
        except Exception as exc:
            print(
                f"[scheduled_notifier:user_loop] user_id={user_db_id} line_user_id={line_user_id} request_date={request_date} failed: {exc}"
            )


if __name__ == "__main__":
    run_scheduled_checks()
