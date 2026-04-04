from functools import lru_cache

from linebot import LineBotApi, WebhookHandler
from supabase import create_client

from config import get_settings


@lru_cache
def get_supabase_client():
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_key)


@lru_cache
def get_line_bot_api():
    settings = get_settings()
    return LineBotApi(settings.line_channel_access_token)


@lru_cache
def get_webhook_handler():
    settings = get_settings()
    return WebhookHandler(settings.line_channel_secret)
