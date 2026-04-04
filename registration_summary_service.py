from repositories import get_exception_dates, get_notification_settings
from utils import decode_compact_datetimes



def build_registration_summary_payload(user_id):
    notification_row = get_notification_settings(user_id)
    return {
        "notification_enabled": bool(notification_row.get("get_notification")),
        "last_date": notification_row.get("last_date"),
        "exception_dates": [dt.isoformat() for dt in get_exception_dates(user_id)],
        "latest_available_dates": decode_compact_datetimes(
            notification_row.get("last_available_dates") or []
        ),
    }
