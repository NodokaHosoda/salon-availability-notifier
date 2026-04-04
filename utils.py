from datetime import datetime

WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]



def ensure_datetime(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)



def serialize_compact_datetimes(values):
    unique_dates = sorted(set(ensure_datetime(value) for value in values))
    return [dt.strftime("%Y%m%d%H%M") for dt in unique_dates]



def encode_compact_datetimes(values):
    return ",".join(serialize_compact_datetimes(values))



def decode_compact_datetimes(values):
    decoded = []
    for value in values:
        if not value:
            continue
        decoded.append(datetime.strptime(value, "%Y%m%d%H%M").isoformat())
    return decoded



def format_date_only_for_display(value):
    dt_obj = ensure_datetime(value)
    weekday = WEEKDAYS[dt_obj.weekday()]
    return dt_obj.strftime(f"%Y年%m月%d日（{weekday}）")



def format_time_for_display(value):
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if "T" in value:
        return ensure_datetime(value).strftime("%H:%M")
    return datetime.strptime(value, "%H%M").strftime("%H:%M")



def format_iso_for_display(value):
    dt_obj = ensure_datetime(value)
    return f"{format_date_only_for_display(dt_obj)}{dt_obj.strftime('%H:%M')}"



def format_grouped_datetimes_for_display(values, include_bullet=False, as_text=False):
    grouped = {}
    for value in sorted(ensure_datetime(item) for item in values):
        date_label = format_date_only_for_display(value)
        grouped.setdefault(date_label, []).append(value.strftime("%H:%M"))

    lines = []
    for date_label, times in grouped.items():
        prefix = "- " if include_bullet else ""
        lines.append(f"{prefix}{date_label}")
        lines.append(f"  {', '.join(times)}")

    if as_text:
        return "\n".join(lines)
    return lines
