from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    supabase_url: str | None
    supabase_key: str | None
    line_channel_secret: str | None
    line_channel_access_token: str | None
    liff_exclude_add_id: str | None
    liff_exclude_remove_id: str | None
    liff_registration_id: str | None
    app_base_url: str | None
    cloud_tasks_project_id: str | None
    cloud_tasks_location: str | None
    cloud_tasks_queue: str | None
    immediate_check_task_secret: str | None
    task_url: str | None


def load_environment():
    load_dotenv()
    load_dotenv(dotenv_path=Path.home() / ".env", override=False)


@lru_cache
def get_settings():
    load_environment()
    return Settings(
        supabase_url=os.environ.get("SUPABASE_URL"),
        supabase_key=os.environ.get("SUPABASE_KEY"),
        line_channel_secret=os.environ.get("LINE_CHANNEL_SECRET"),
        line_channel_access_token=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"),
        liff_exclude_add_id=os.environ.get("LIFF_EXCLUDE_ADD_ID"),
        liff_exclude_remove_id=os.environ.get("LIFF_EXCLUDE_REMOVE_ID"),
        liff_registration_id=os.environ.get("LIFF_REGISTRATION_ID"),
        app_base_url=os.environ.get("APP_BASE_URL"),
        cloud_tasks_project_id=os.environ.get("CLOUD_TASKS_PROJECT_ID"),
        cloud_tasks_location=os.environ.get("CLOUD_TASKS_LOCATION"),
        cloud_tasks_queue=os.environ.get("CLOUD_TASKS_QUEUE"),
        immediate_check_task_secret=os.environ.get("IMMEDIATE_CHECK_TASK_SECRET"),
        task_url=os.environ.get("TASK_URL"),
    )
