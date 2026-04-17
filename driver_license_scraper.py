from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_WEB_URL = "https://license-test.tokyo-madoguchi-yoyaku.com"
MONTHLY_AVAILABILITY_URL = (
    "https://license-test-tokyo-prd-police-pref-api.tokyo-madoguchi-yoyaku.com/calgetres"
)
PLACE_DATA_URL = f"{BASE_WEB_URL}/police-pref-tokyo/01/data/MKAYMA001placeData.json"
FILTER_DATA_URL = f"{BASE_WEB_URL}/police-pref-tokyo/01/data/MKAYMA001filterData.json"
REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_STATE_FILE = Path(".driver_license_scraper_state.json")
BASE_MONITOR_MONTH = 4
BASE_MONITOR_DAY = 23

DRIVING_SCHOOL_GRADUATE_TYPE = "11"
LICENSE_ONLY_CARD_TYPE = "1"
PUBLIC_USER = "pub"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
}


@dataclass(frozen=True)
class AvailabilitySlot:
    place_name: str
    date: str
    display_time: str
    remaining: int

    @property
    def slot_key(self):
        return (self.place_name, self.date, self.display_time)

    @property
    def compare_key(self):
        return f"{self.place_name}|{self.date}|{self.display_time}"


@dataclass(frozen=True)
class ScrapeState:
    month: str
    start_date: str
    slots: list[AvailabilitySlot]


@dataclass(frozen=True)
class SlotDiff:
    added: list[AvailabilitySlot]
    removed: list[AvailabilitySlot]


class DriverLicenseScraperError(RuntimeError):
    pass


def parse_args():
    parser = argparse.ArgumentParser(
        description="東京都運転免許学科試験の空き枠を一覧表示します。"
    )
    parser.add_argument(
        "--month",
        required=True,
        help="対象月を YYYY-MM 形式で指定します。例: 2026-04",
    )
    parser.add_argument(
        "--from-date",
        default="",
        help="取得開始日を YYYY-MM-DD 形式で指定します。未指定時は対象月の23日です。",
    )
    parser.add_argument(
        "--state-file",
        default=str(DEFAULT_STATE_FILE),
        help="前回結果を保存する JSON ファイルのパスです。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="前回結果と同じでも強制的に出力します。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="人向け整形ではなく JSON で出力します。",
    )
    return parser.parse_args()


def fetch_json(url, *, params=None):
    request_url = url
    if params:
        request_url = f"{url}?{urlencode(params)}"

    request = Request(request_url, headers=DEFAULT_HEADERS)
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except HTTPError as exc:
        raise DriverLicenseScraperError(
            f"HTTP error while fetching {request_url}: {exc.code}"
        ) from exc
    except URLError as exc:
        raise DriverLicenseScraperError(
            f"Network error while fetching {request_url}: {exc.reason}"
        ) from exc


def load_filter_data():
    return fetch_json(FILTER_DATA_URL)


def resolve_course_code(filter_data):
    return filter_data[DRIVING_SCHOOL_GRADUATE_TYPE]["0"][LICENSE_ONLY_CARD_TYPE]["0"][
        "typeDetail"
    ]


def resolve_places(filter_data):
    allowed_place_codes = filter_data[DRIVING_SCHOOL_GRADUATE_TYPE]["0"][
        LICENSE_ONLY_CARD_TYPE
    ]["0"]["placeCode"]
    place_data = fetch_json(PLACE_DATA_URL)
    return [
        {"code": place_code, "name": place_data[place_code]["name"]}
        for place_code in allowed_place_codes
    ]


def is_license_only_slot(slot):
    display_time = slot.get("displaytime", "")
    return "従来の免許証" in display_time and "マイナ" not in display_time


def should_include_date(slot_date, start_date, target_month):
    slot_dt = datetime.strptime(slot_date, "%Y%m%d")
    return slot_dt.strftime("%Y%m") == target_month and slot_dt.date() >= start_date.date()


def fetch_monthly_slots(target_month, start_date):
    filter_data = load_filter_data()
    course_code = resolve_course_code(filter_data)
    places = resolve_places(filter_data)
    slots = []

    for place in places:
        payload = {
            "date": target_month,
            "coursecode": course_code,
            "placecode": place["code"],
            "user": PUBLIC_USER,
        }
        response = fetch_json(MONTHLY_AVAILABILITY_URL, params=payload)
        if response.get("code") != "A0001":
            raise DriverLicenseScraperError(
                f"Unexpected API response for place={place['code']}: {response}"
            )

        for slot in response.get("body") or []:
            if not is_license_only_slot(slot):
                continue
            if not should_include_date(slot["date"], start_date, target_month):
                continue

            remaining = int(slot["capacity"]) - int(slot["reservation"])
            if remaining <= 0:
                continue

            slots.append(
                AvailabilitySlot(
                    place_name=place["name"],
                    date=slot["date"],
                    display_time=slot["displaytime"],
                    remaining=remaining,
                )
            )

    return sorted(slots, key=lambda slot: (slot.place_name, slot.date, slot.display_time))


def iter_target_months(start_date, deadline_date):
    current = start_date.replace(day=1)
    end = deadline_date.replace(day=1)
    while current <= end:
        yield current.strftime("%Y%m")
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)


def normalize_target_month(month_text):
    return datetime.strptime(month_text, "%Y-%m").strftime("%Y%m")


def resolve_start_date(month_text, from_date_text):
    target_month = normalize_target_month(month_text)
    if from_date_text:
        start_date = datetime.strptime(from_date_text, "%Y-%m-%d")
    else:
        start_date = datetime.strptime(f"{month_text}-{BASE_MONITOR_DAY}", "%Y-%m-%d")

    if start_date.strftime("%Y%m") != target_month:
        raise DriverLicenseScraperError("--from-date は --month と同じ月を指定してください。")
    return start_date


def determine_start_date(deadline_date, current_date):
    season_start = deadline_date.replace(month=BASE_MONITOR_MONTH, day=BASE_MONITOR_DAY)
    return max(current_date, season_start)


def fetch_driver_license_slots(deadline_date, current_date=None):
    effective_current_date = current_date or datetime.utcnow().date()
    start_date = determine_start_date(deadline_date, effective_current_date)
    if start_date > deadline_date:
        return []

    start_datetime = datetime.combine(start_date, time.min)
    slots = []
    for target_month in iter_target_months(start_date, deadline_date):
        slots.extend(fetch_monthly_slots(target_month, start_datetime))

    return sorted(
        [
            slot
            for slot in slots
            if datetime.strptime(slot.date, "%Y%m%d").date() <= deadline_date
        ],
        key=lambda slot: (slot.place_name, slot.date, slot.display_time),
    )


def serialize_driver_license_slots(slots):
    return [slot.compare_key for slot in slots]


def deserialize_driver_license_slots(values):
    items = []
    for value in values or []:
        try:
            place_name, date, display_time = value.split("|", 2)
        except ValueError:
            continue
        items.append(
            AvailabilitySlot(
                place_name=place_name,
                date=date,
                display_time=display_time,
                remaining=0,
            )
        )
    return items


def format_driver_license_slot_label(slot):
    date_label = datetime.strptime(slot.date, "%Y%m%d").strftime("%Y-%m-%d")
    return f"{slot.place_name} / {date_label} / {slot.display_time}"


def format_slots_as_lines(slots):
    if not slots:
        return ["空き枠はありませんでした。"]

    grouped = defaultdict(lambda: defaultdict(list))
    for slot in slots:
        grouped[slot.place_name][slot.date].append(slot)

    lines = []
    for place_name, dates in grouped.items():
        lines.append(place_name)
        for date_text in sorted(dates):
            date_label = datetime.strptime(date_text, "%Y%m%d").strftime("%Y-%m-%d")
            lines.append(f"  {date_label}")
            for slot in dates[date_text]:
                lines.append(f"    {slot.display_time} / 残り {slot.remaining}")
    return lines


def print_slots(slots):
    for line in format_slots_as_lines(slots):
        print(line)


def load_previous_state(state_file):
    if not state_file.exists():
        return None

    data = json.loads(state_file.read_text(encoding="utf-8"))
    return ScrapeState(
        month=data["month"],
        start_date=data["start_date"],
        slots=[AvailabilitySlot(**slot) for slot in data.get("slots", [])],
    )


def save_state(state_file, state):
    payload = {
        "month": state.month,
        "start_date": state.start_date,
        "slots": [asdict(slot) for slot in state.slots],
    }
    state_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def diff_slots(previous_slots, current_slots):
    previous_map = {slot.slot_key: slot for slot in previous_slots}
    current_map = {slot.slot_key: slot for slot in current_slots}
    added_keys = sorted(set(current_map) - set(previous_map))
    removed_keys = sorted(set(previous_map) - set(current_map))
    return SlotDiff(
        added=[current_map[key] for key in added_keys],
        removed=[previous_map[key] for key in removed_keys],
    )


def has_changed(previous_state, current_state):
    if previous_state is None:
        return True
    return previous_state != current_state


def print_diff_summary(diff):
    print(f"追加: {len(diff.added)}件 / 削除: {len(diff.removed)}件")
    if diff.added:
        print("追加された空き枠:")
        print_slots(diff.added)
    if diff.removed:
        print("削除された空き枠:")
        print_slots(diff.removed)


def build_json_payload(current_state, previous_state):
    diff = diff_slots(previous_state.slots if previous_state else [], current_state.slots)
    return {
        "changed": has_changed(previous_state, current_state),
        "month": current_state.month,
        "start_date": current_state.start_date,
        "slot_count": len(current_state.slots),
        "slots": [asdict(slot) for slot in current_state.slots],
        "diff": {
            "added": [asdict(slot) for slot in diff.added],
            "removed": [asdict(slot) for slot in diff.removed],
        },
    }


def main():
    args = parse_args()
    state_file = Path(args.state_file)
    target_month = normalize_target_month(args.month)
    start_date = resolve_start_date(args.month, args.from_date)
    previous_state = load_previous_state(state_file)
    current_state = ScrapeState(
        month=target_month,
        start_date=start_date.strftime("%Y-%m-%d"),
        slots=fetch_monthly_slots(target_month, start_date),
    )

    if args.json:
        print(
            json.dumps(
                build_json_payload(current_state, previous_state),
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.force or has_changed(previous_state, current_state):
            save_state(state_file, current_state)
        return

    if args.force:
        print_slots(current_state.slots)
        save_state(state_file, current_state)
        return

    if has_changed(previous_state, current_state):
        diff = diff_slots(previous_state.slots if previous_state else [], current_state.slots)
        print_diff_summary(diff)
        save_state(state_file, current_state)
        return

    print("前回結果から変化がありませんでした。")


if __name__ == "__main__":
    main()
