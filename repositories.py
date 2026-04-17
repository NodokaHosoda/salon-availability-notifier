from datetime import datetime
from functools import lru_cache

from supabase import create_client

from config import get_settings
from utils import log_exception_details

SALON_USER_TYPE = "salon"
DRIVER_LICENSE_USER_TYPE = "driverlicense"


@lru_cache
def get_supabase_client():
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_key)


class BaseRepository:
    @property
    def client(self):
        return get_supabase_client()


class NotificationSettingRepository(BaseRepository):
    def _setting_exists(self, user_id):
        response = (
            self.client
            .table("notification_setting")
            .select("user_id")
            .eq("user_id", user_id)
            .execute()
        )
        return bool(response.data)

    def initial_settings(self, user_id):
        if self._setting_exists(user_id):
            return

        try:
            (
                self.client
                .table("notification_setting")
                .insert(
                    {
                        "user_id": user_id,
                        "last_date": None,
                        "get_notification": False,
                    }
                )
                .execute()
            )
            print(f"[notification_setting:created] user_id={user_id}")
        except Exception as exc:
            recovery_response = (
                self.client
                .table("notification_setting")
                .select("user_id")
                .eq("user_id", user_id)
                .execute()
            )
            if recovery_response.data:
                return
            log_exception_details(f"notification_setting:create user_id={user_id}", exc)
            raise

    def get_settings(self, user_id):
        response = (
            self.client
            .table("notification_setting")
            .select(
                "last_date,get_notification,last_available_dates,driver_last_available_dates"
            )
            .eq("user_id", user_id)
            .execute()
        )
        return response.data[0] if response.data else {}

    def is_enabled(self, user_id):
        return bool(self.get_settings(user_id).get("get_notification"))

    def set_enabled(self, user_id, enabled):
        (
            self.client
            .table("notification_setting")
            .update({"get_notification": enabled})
            .eq("user_id", user_id)
            .execute()
        )

    def list_enabled_targets(self, user_type=None):
        response = (
            self.client
            .table("notification_setting")
            .select(
                """
                user_id,
                last_date,
                user_info (
                    line_user_id,
                    type
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
            effective_type = user_info.get("type") or SALON_USER_TYPE
            if not line_user_id:
                continue
            if user_type and effective_type != user_type:
                continue
            targets.append(
                {
                    "user_id": row["user_id"],
                    "last_date": row.get("last_date"),
                    "line_user_id": line_user_id,
                    "user_type": effective_type,
                }
            )
        return targets

    def get_last_date(self, user_id):
        return self.get_settings(user_id).get("last_date")

    def update_last_date(self, user_id, new_date):
        (
            self.client
            .table("notification_setting")
            .update({"last_date": new_date})
            .eq("user_id", user_id)
            .execute()
        )

    def get_last_available_dates(self, user_id):
        return self.get_settings(user_id).get("last_available_dates")

    def update_last_available_dates(self, user_id, compact_datetimes):
        (
            self.client
            .table("notification_setting")
            .update({"last_available_dates": compact_datetimes})
            .eq("user_id", user_id)
            .execute()
        )

    def get_driver_last_available_dates(self, user_id):
        return self.get_settings(user_id).get("driver_last_available_dates")

    def update_driver_last_available_dates(self, user_id, driver_slots):
        (
            self.client
            .table("notification_setting")
            .update({"driver_last_available_dates": driver_slots})
            .eq("user_id", user_id)
            .execute()
        )

    def clear_state(self, user_id):
        (
            self.client
            .table("notification_setting")
            .update(
                {
                    "get_notification": False,
                    "last_date": None,
                    "last_available_dates": None,
                    "driver_last_available_dates": None,
                }
            )
            .eq("user_id", user_id)
            .execute()
        )


class ExceptionDateRepository(BaseRepository):
    def list_dates(self, user_id):
        response = (
            self.client
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

    def save_dates(self, user_id, dates):
        unique_dates = sorted(set(dates))
        if not unique_dates:
            return 0

        existing_response = (
            self.client
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

        self.client.table("exceptions_date").insert(payload).execute()
        return len(payload)

    def remove_dates(self, user_id, dates):
        unique_dates = sorted(set(dates))
        removed_count = 0
        for dt in unique_dates:
            response = (
                self.client
                .table("exceptions_date")
                .delete()
                .eq("user_id", user_id)
                .eq("date", dt.isoformat())
                .execute()
            )
            removed_count += len(response.data or [])
        return removed_count

    def clear_dates(self, user_id):
        self.client.table("exceptions_date").delete().eq("user_id", user_id).execute()


class UserInfoRepository(BaseRepository):
    def __init__(self, notification_setting_repository):
        self.notification_setting_repository = notification_setting_repository

    def get_or_create_user(self, line_user_id, user_name=None):
        user_id = self.get_user_id(line_user_id)
        if user_id:
            self.notification_setting_repository.initial_settings(user_id)
            return user_id

        try:
            response = (
                self.client
                .table("user_info")
                .insert({"line_user_id": line_user_id, "user_name": user_name})
                .execute()
            )
            user_id = response.data[0]["id"]
        except Exception as exc:
            user_id = self.get_user_id(line_user_id)
            if not user_id:
                log_exception_details(
                    f"user_info:create line_user_id={line_user_id} user_name={user_name}",
                    exc,
                )
                raise

        self.notification_setting_repository.initial_settings(user_id)
        return user_id

    def get_user_id(self, line_user_id):
        response = (
            self.client
            .table("user_info")
            .select("id")
            .eq("line_user_id", line_user_id)
            .execute()
        )
        if not response.data:
            return None
        return response.data[0]["id"]

    def get_user_type(self, line_user_id):
        response = (
            self.client
            .table("user_info")
            .select("type")
            .eq("line_user_id", line_user_id)
            .execute()
        )
        if not response.data:
            return SALON_USER_TYPE
        return response.data[0].get("type") or SALON_USER_TYPE

    def get_user_type_by_id(self, user_id):
        response = (
            self.client
            .table("user_info")
            .select("type")
            .eq("id", user_id)
            .execute()
        )
        if not response.data:
            return SALON_USER_TYPE
        return response.data[0].get("type") or SALON_USER_TYPE

    def update_user_type(self, user_id, user_type):
        (
            self.client
            .table("user_info")
            .update({"type": user_type})
            .eq("id", user_id)
            .execute()
        )


notification_setting_repository = NotificationSettingRepository()
exception_date_repository = ExceptionDateRepository()
user_info_repository = UserInfoRepository(notification_setting_repository)
