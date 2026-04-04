from datetime import datetime

from clients import get_supabase_client



def ensure_notification_setting(user_id):
    response = (
        get_supabase_client()
        .table("notification_setting")
        .select("user_id")
        .eq("user_id", user_id)
        .execute()
    )
    if response.data:
        return

    (
        get_supabase_client()
        .table("notification_setting")
        .insert({"user_id": user_id, "last_date": None, "get_notification": False})
        .execute()
    )



def get_or_create_user(line_user_id):
    # follow イベントや復旧経路から同じ helper を呼べるよう、ユーザー作成は冪等にしている。
    user_id = get_user_id_from_line_user_id(line_user_id)
    if user_id:
        ensure_notification_setting(user_id)
        return user_id

    try:
        response = (
            get_supabase_client()
            .table("user_info")
            .insert({"line_user_id": line_user_id, "line_user_name": None})
            .execute()
        )
        user_id = response.data[0]["id"]
    except Exception:
        # 同時実行で先に他方が作成した場合は、作成済みの行を取り直して続行する。
        user_id = get_user_id_from_line_user_id(line_user_id)
        if not user_id:
            raise

    ensure_notification_setting(user_id)
    return user_id



def get_user_id_from_line_user_id(line_user_id):
    response = (
        get_supabase_client()
        .table("user_info")
        .select("id")
        .eq("line_user_id", line_user_id)
        .single()
        .execute()
    )
    if not response.data:
        return None
    return response.data["id"]



def get_notification_settings(user_id):
    response = (
        get_supabase_client()
        .table("notification_setting")
        .select("last_date,get_notification,last_available_dates")
        .eq("user_id", user_id)
        .execute()
    )
    return response.data[0] if response.data else {}



def is_notification_enabled(user_id):
    notification_row = get_notification_settings(user_id)
    return bool(notification_row.get("get_notification"))



def update_last_date(user_id, new_date):
    (
        get_supabase_client()
        .table("notification_setting")
        .update({"last_date": new_date})
        .eq("user_id", user_id)
        .execute()
    )



def set_notification_enabled(user_id, enabled):
    (
        get_supabase_client()
        .table("notification_setting")
        .update({"get_notification": enabled})
        .eq("user_id", user_id)
        .execute()
    )



def get_notification_target_date(user_id):
    notification_row = get_notification_settings(user_id)
    return notification_row.get("last_date")



def get_last_available_dates(user_id):
    notification_row = get_notification_settings(user_id)
    return notification_row.get("last_available_dates")



def update_last_available_dates(user_id, compact_datetimes):
    (
        get_supabase_client()
        .table("notification_setting")
        .update({"last_available_dates": compact_datetimes})
        .eq("user_id", user_id)
        .execute()
    )



def get_exception_dates(user_id):
    response = (
        get_supabase_client()
        .table("exceptions_date")
        .select("date")
        .eq("user_id", user_id)
        .order("date")
        .execute()
    )
    return [
        datetime.fromisoformat(row["date"])
        for row in (response.data or [])
        if row.get("date")
    ]



def save_exception_dates(user_id, dates):
    unique_dates = sorted(set(dates))
    if not unique_dates:
        return 0

    # add API は再実行に耐えられるよう、既に保存済みの日時は追加しない。
    existing_response = (
        get_supabase_client()
        .table("exceptions_date")
        .select("date")
        .eq("user_id", user_id)
        .execute()
    )
    existing_dates = {
        datetime.fromisoformat(row["date"])
        for row in (existing_response.data or [])
        if row.get("date")
    }
    payload = [
        {"user_id": user_id, "date": dt.isoformat()}
        for dt in unique_dates
        if dt not in existing_dates
    ]
    if not payload:
        return 0

    get_supabase_client().table("exceptions_date").insert(payload).execute()
    return len(payload)



def remove_exception_dates(user_id, dates):
    unique_dates = sorted(set(dates))
    removed_count = 0
    for dt in unique_dates:
        response = (
            get_supabase_client()
            .table("exceptions_date")
            .delete()
            .eq("user_id", user_id)
            .eq("date", dt.isoformat())
            .execute()
        )
        removed_count += len(response.data or [])
    return removed_count



def clear_notification_state(user_id):
    # 通知停止では通知フラグだけでなく、その設定に紐づく除外日もまとめてクリアする。
    (
        get_supabase_client()
        .table("notification_setting")
        .update({"get_notification": False, "last_date": None, "last_available_dates": None})
        .eq("user_id", user_id)
        .execute()
    )
    get_supabase_client().table("exceptions_date").delete().eq("user_id", user_id).execute()



def list_enabled_notification_targets():
    # 定期実行の対象は、通知が有効なユーザーだけでよい。
    response = (
        get_supabase_client()
        .table("notification_setting")
        .select(
            """
            user_id,
            last_date,
            user_info (
                line_user_id
            )
            """
        )
        .eq("get_notification", True)
        .execute()
    )

    targets = []
    for row in response.data or []:
        user_info = row.get("user_info") or {}
        line_user_id = user_info.get("line_user_id")
        if not line_user_id:
            continue
        targets.append(
            {
                "user_id": row["user_id"],
                "last_date": row.get("last_date"),
                "line_user_id": line_user_id,
            }
        )
    return targets
