from pathlib import Path
import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
load_dotenv(dotenv_path=Path.home() / ".env", override=False)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def clear_notification_state(user_id):
    (
        supabase.table("notification_setting")
        .update({"get_notification": False, "last_date": None, "last_available_dates": None})
        .eq("user_id", user_id)
        .execute()
    )
    supabase.table("exceptions_date").delete().eq("user_id", user_id).execute()
