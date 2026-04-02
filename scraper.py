from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, quote, urlparse
from pathlib import Path
import asyncio
import json
import os
import re

import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from supabase import create_client

from utils import (
    clear_notification_state,
    encode_compact_datetimes,
    format_date_only_for_display,
    format_grouped_datetimes_for_display,
    format_time_for_display,
    serialize_compact_datetimes,
)

load_dotenv()
load_dotenv(dotenv_path=Path.home() / ".env", override=False)

LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")
TASK_URL = os.environ.get("TASK_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

MENU_ENTRY_TEXT = "空席確認・予約する"
COURSE_TEXT = "12月1日から2200円。カットのみ"
AVAILABILITY_MESSAGE_PREFIX = "空きがあります！\n"
NO_AVAILABILITY_MESSAGE_SUFFIX = " までの空きはありません。"
REQUEST_TIMEOUT_SECONDS = 10

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_last_available_dates(user_db_id):
    response = (
        supabase.table("notification_setting")
        .select("last_available_dates")
        .eq("user_id", user_db_id)
        .execute()
    )
    if not response.data:
        return None
    return response.data[0].get("last_available_dates")


def update_last_available_dates(user_db_id, available_dates):
    (
        supabase.table("notification_setting")
        .update({"last_available_dates": available_dates})
        .eq("user_id", user_db_id)
        .execute()
    )


def create_line_message_payload(message, available_dates=None):
    if not available_dates:
        return {"type": "text", "text": message}

    grouped_dates = {}
    for dt_obj in sorted(available_dates):
        date_label = format_date_only_for_display(dt_obj)
        grouped_dates.setdefault(date_label, []).append(format_time_for_display(dt_obj))

    sections = []
    for date_label, times in grouped_dates.items():
        sections.append(
            {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "margin": "lg",
                "contents": [
                    {
                        "type": "text",
                        "text": date_label,
                        "weight": "bold",
                        "size": "sm",
                        "wrap": True,
                        "color": "#1F1F1F",
                    },
                    {
                        "type": "text",
                        "text": "  ".join(times),
                        "size": "sm",
                        "wrap": True,
                        "color": "#6B655D",
                    },
                ],
            }
        )

    return {
        "type": "flex",
        "altText": message,
        "contents": {
            "type": "bubble",
            "size": "giga",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "空きがあります",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#A7482F",
                    },
                    {
                        "type": "text",
                        "text": f"{len(available_dates)}件の候補が見つかりました。",
                        "size": "sm",
                        "wrap": True,
                        "color": "#6B655D",
                    },
                    {
                        "type": "separator",
                        "margin": "md",
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "contents": sections,
                    },
                ],
            },
        },
    }


def send_line_message(request_date, line_user_id, user_db_id, exception_dates=None, compare_with_last=True):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    exception_set = exception_dates or set()
    message, new_exceptions, raw_available_dates = loop.run_until_complete(
        check_availability(request_date, exception_set)
    )
    loop.close()

    available_dates = serialize_compact_datetimes(raw_available_dates)
    if compare_with_last:
        previous_available_dates = get_last_available_dates(user_db_id) or []
        if available_dates == previous_available_dates:
            print("No change in availability, skipping notification.")
            return

    push_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}",
    }
    body = {
        "to": line_user_id,
        "messages": [create_line_message_payload(message, new_exceptions)],
    }
    try:
        response = requests.post(
            push_url,
            headers=headers,
            data=json.dumps(body),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        print(f"[line_push] user_id={user_db_id} status={response.status_code}")
        try:
            print(response.json())
        except ValueError:
            print(response.text)
    except requests.RequestException as exc:
        print(f"[line_push] user_id={user_db_id} failed: {exc}")
        return

    if not response.ok:
        return

    if compare_with_last:
        update_last_available_dates(user_db_id, available_dates)
        
    if message.startswith(AVAILABILITY_MESSAGE_PREFIX) and new_exceptions:
        prompt_body = create_exclusion_prompt(line_user_id, new_exceptions)
        if prompt_body:
            try:
                prompt_response = requests.post(
                    push_url,
                    headers=headers,
                    data=json.dumps(prompt_body),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                print(f"[line_push:prompt] user_id={user_db_id} status={prompt_response.status_code}")
                try:
                    print(prompt_response.json())
                except ValueError:
                    print(prompt_response.text)
            except requests.RequestException as exc:
                print(f"[line_push:prompt] user_id={user_db_id} failed: {exc}")


async def check_availability(request_date, exception_dates=None):
    request_deadline = datetime.strptime(request_date, "%Y-%m-%d")
    availability_elements = []
    exception_set = exception_dates or set()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(TASK_URL, wait_until="domcontentloaded")

        await page.get_by_text(MENU_ENTRY_TEXT).nth(0).click()
        await page.wait_for_load_state("load")

        course_locator = page.locator("p.couponMenuName", has_text=COURSE_TEXT)
        count = await course_locator.count()
        for index in range(count):
            element = course_locator.nth(index)
            text = await element.text_content()
            if text and text.strip() == COURSE_TEXT:
                course_locator = element
                break

        row = course_locator.locator("xpath=ancestor::tr")
        await row.locator(f"text={MENU_ENTRY_TEXT}").click()
        await page.wait_for_load_state("load")

        try:
            while True:
                calendar = page.locator("table.innerTable")
                last_date_tr = calendar.locator("tr.dayCellContainer")
                last_date_obj = await last_date_tr.locator("th:last-of-type").text_content()
                last_date = convert_to_ymd(last_date_obj)
                availability_elements += await calendar.locator("a.icnOpen").all()

                if last_date < request_deadline:
                    next_btn = page.locator("a.arrowPagingWeekR")
                    if await next_btn.count() > 0 and await next_btn.is_enabled():
                        await next_btn.click()
                        await page.wait_for_load_state("load")
                    else:
                        break
                else:
                    break

            if availability_elements:
                dates, exception_list, raw_available_dates = await create_available_date_list(
                    availability_elements,
                    request_deadline,
                    exception_set,
                )
                if dates:
                    print(f"Available dates found: {dates}")
                    return f"{AVAILABILITY_MESSAGE_PREFIX}{dates}", exception_list, raw_available_dates
            print("No available dates found")
            return f"{request_date}{NO_AVAILABILITY_MESSAGE_SUFFIX}", [], raw_available_dates if availability_elements else []
        finally:
            await browser.close()


async def create_available_date_list(elements, request_deadline, exception_set):
    exception_list = []
    raw_available_dates = []
    seen_datetimes = set()
    for element in elements:
        href = await element.get_attribute("href")
        if not href:
            continue

        parsed_url = urlparse(href)
        params = parse_qs(parsed_url.query)
        date_str = params.get("rsvRequestDate1", [""])[0]
        if not date_str:
            continue

        date_obj = datetime.strptime(date_str, "%Y%m%d")
        if date_obj > request_deadline:
            continue

        time_str = params.get("rsvRequestTime1", [""])[0]
        if not time_str:
            continue

        dt_obj = datetime.strptime(date_str + time_str, "%Y%m%d%H%M")
        if dt_obj in seen_datetimes:
            continue

        seen_datetimes.add(dt_obj)
        raw_available_dates.append(dt_obj)

        if dt_obj in exception_set:
            continue

        exception_list.append(dt_obj)
    return format_grouped_datetimes_for_display(exception_list, as_text=True), exception_list, raw_available_dates


def save_exception_dates(user_db_id, exception_list):
    if not exception_list:
        return

    existing_response = (
        supabase.table("exceptions_date").select("date").eq("user_id", user_db_id).execute()
    )
    existing_dates = {
        datetime.fromisoformat(row["date"])
        for row in (existing_response.data or [])
        if row.get("date")
    }
    payload = [
        {"user_id": user_db_id, "date": dt.isoformat()}
        for dt in exception_list
        if dt not in existing_dates
    ]
    if payload:
        supabase.table("exceptions_date").insert(payload).execute()


def create_exclusion_prompt(line_user_id, exception_list):
    liff_url = build_liff_add_url(exception_list)
    if not liff_url:
        return None

    return {
        "to": line_user_id,
        "messages": [
            {
                "type": "template",
                "altText": "通知した日付を除外対象に追加できます",
                "template": {
                    "type": "buttons",
                    "title": "通知した日付の除外",
                    "text": (
                        "上記の日付を通知対象から除外する場合は画面を開いてください。"
                    ),
                    "actions": [
                        {
                            "type": "uri",
                            "label": "除外する",
                            "uri": liff_url,
                        }
                    ],
                },
            }
        ],
    }


def build_liff_add_url(exception_list):
    if not APP_BASE_URL:
        return None

    encoded_dates = encode_compact_datetimes(exception_list)
    candidate_url = f"{APP_BASE_URL}/liff/exclude-add?dates={quote(encoded_dates)}"
    if len(candidate_url) > 1800:
        return None
    return candidate_url




def convert_to_ymd(date_str):
    cleaned = re.sub(r"[（(].*?[）)]", "", date_str or "")
    return datetime.strptime(cleaned.strip(), "%a %b %d %H:%M:%S JST %Y")


if __name__ == "__main__":
    response = (
        supabase.table("notification_setting")
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

    for row in response.data or []:
        request_date = row["last_date"]
        if not request_date:
            continue

        if datetime.strptime(request_date, "%Y-%m-%d").date() < (datetime.now(timezone.utc) + timedelta(hours=9)).date():
            clear_notification_state(row["user_id"])
            continue
        line_user_id = row["user_info"]["line_user_id"]
        user_db_id = row["user_id"]
        try:
            exception_response = (
                supabase.table("exceptions_date").select("date").eq("user_id", user_db_id).execute()
            )
            exception_dates = [
                datetime.fromisoformat(item["date"])
                for item in (exception_response.data or [])
                if item.get("date")
            ]
            send_line_message(request_date, line_user_id, user_db_id, set(exception_dates))
        except Exception as exc:
            print(
                f"[scraper:user_loop] user_id={user_db_id} line_user_id={line_user_id} request_date={request_date} failed: {exc}"
            )
