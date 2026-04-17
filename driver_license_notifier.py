from collections import defaultdict
from datetime import datetime, timedelta, timezone

from availability_notifier import send_line_push_message
from driver_license_scraper import fetch_driver_license_slots, serialize_driver_license_slots
from line_templates import build_availability_message_payload
from repositories import notification_setting_repository


def current_jst_date():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


def build_driver_license_sections(slots, highlighted_keys=None):
    highlighted = set(highlighted_keys or [])
    grouped = defaultdict(lambda: defaultdict(list))
    for slot in slots:
        grouped[slot.place_name][slot.date].append(slot)

    sections = []
    for place_name in sorted(grouped):
        for date_text in sorted(grouped[place_name]):
            label = datetime.strptime(date_text, "%Y%m%d").strftime("%Y年%m月%d日")
            sections.append(
                {
                    "label": f"{place_name} / {label}",
                    "items": [
                        {
                            "text": f"{slot.display_time}（残り {slot.remaining}）",
                            "highlighted": slot.compare_key in highlighted,
                        }
                        for slot in grouped[place_name][date_text]
                    ],
                }
            )
    return sections


def decode_driver_last_available_date_texts(values):
    items = []
    for value in values or []:
        try:
            place_name, date_text, display_time = value.split("|", 2)
        except ValueError:
            continue
        label = datetime.strptime(date_text, "%Y%m%d").strftime("%Y-%m-%d")
        items.append(f"{place_name} / {label} / {display_time}")
    return items


def check_and_send_driver_license_availability(
    request_date,
    line_user_id,
    user_db_id,
    compare_with_last=True,
):
    deadline_date = datetime.strptime(request_date, "%Y-%m-%d").date()
    slots = fetch_driver_license_slots(deadline_date, current_date=current_jst_date())
    visible_slots = serialize_driver_license_slots(slots)
    highlighted_slots = visible_slots

    if compare_with_last:
        previous_slots = notification_setting_repository.get_driver_last_available_dates(user_db_id) or []
        highlighted_slots = sorted(set(visible_slots) - set(previous_slots))
        if not highlighted_slots:
            print("No newly added driver license availability, skipping notification.")
            notification_setting_repository.update_driver_last_available_dates(
                user_db_id,
                visible_slots,
            )
            return

    if not slots:
        message_payload = {"type": "text", "text": f"{request_date} までの空きはありません。"}
    else:
        message_payload = build_availability_message_payload(
            "空きがあります！",
            sections=build_driver_license_sections(slots, highlighted_keys=highlighted_slots),
            total_count=len(slots),
        )

    if not send_line_push_message(line_user_id, user_db_id, message_payload):
        return

    notification_setting_repository.update_driver_last_available_dates(
        user_db_id,
        visible_slots,
    )
