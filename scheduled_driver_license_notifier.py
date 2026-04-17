from datetime import datetime, timedelta, timezone

from driver_license_notifier import check_and_send_driver_license_availability
from repositories import DRIVER_LICENSE_USER_TYPE, notification_setting_repository
from utils import log_exception_details



def current_jst_date():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()



def is_request_date_expired(request_date):
    return datetime.strptime(request_date, "%Y-%m-%d").date() < current_jst_date()



def run_scheduled_checks():
    for target in notification_setting_repository.list_enabled_targets(DRIVER_LICENSE_USER_TYPE):
        request_date = target["last_date"]
        if not request_date:
            continue

        if is_request_date_expired(request_date):
            notification_setting_repository.clear_state(target["user_id"])
            continue

        line_user_id = target["line_user_id"]
        user_db_id = target["user_id"]
        check_and_send_driver_license_availability(
            request_date,
            line_user_id,
            user_db_id,
        )

if __name__ == "__main__":
    run_scheduled_checks()
