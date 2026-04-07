from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qs, urlparse
import re

from playwright.async_api import async_playwright

from config import get_settings
from utils import format_grouped_datetimes_for_display

MENU_ENTRY_TEXT = "空席確認・予約する"
COURSE_TEXT = "12月1日から2200円。カットのみ"
AVAILABILITY_MESSAGE_PREFIX = "空きがあります！\n"
NO_AVAILABILITY_MESSAGE_SUFFIX = " までの空きはありません。"


@dataclass(frozen=True)
class AvailabilityCheckResult:
    message: str
    visible_dates: list[datetime]


async def check_availability(request_date, exception_dates=None):
    request_deadline = datetime.strptime(request_date, "%Y-%m-%d")
    availability_elements = []
    exception_set = exception_dates or set()
    task_url = get_settings().task_url

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(task_url, wait_until="domcontentloaded")

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
            # 指定期限まで週送りしながら、その間に見つかる空き枠をすべて集める。
            while True:
                calendar = page.locator("table.innerTable")
                last_date_tr = calendar.locator("tr.dayCellContainer")
                last_date_obj = await last_date_tr.locator("th:last-of-type").text_content()
                last_date = parse_hotpepper_date(last_date_obj)
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

            visible_dates = []
            if availability_elements:
                visible_dates = await collect_available_dates(
                    availability_elements,
                    request_deadline,
                    exception_set,
                )
                if visible_dates:
                    dates_text = format_grouped_datetimes_for_display(visible_dates, as_text=True)
                    print(f"Available dates found: {dates_text}")
                    return AvailabilityCheckResult(
                        message=f"{AVAILABILITY_MESSAGE_PREFIX}{dates_text}",
                        visible_dates=visible_dates,
                    )

            print("No available dates found")
            return AvailabilityCheckResult(
                message=f"{request_date}{NO_AVAILABILITY_MESSAGE_SUFFIX}",
                visible_dates=[],
            )
        finally:
            await browser.close()


async def collect_available_dates(elements, request_deadline, exception_set):
    available_dates = []
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
        # Hot Pepper 側で同じ枠が重複して見えることがあるため、日時単位で正規化する。
        if dt_obj in seen_datetimes:
            continue

        seen_datetimes.add(dt_obj)
        if dt_obj in exception_set:
            continue

        available_dates.append(dt_obj)

    return available_dates



def parse_hotpepper_date(date_str):
    cleaned = re.sub(r"[（(].*?[）)]", "", date_str or "")
    return datetime.strptime(cleaned.strip(), "%a %b %d %H:%M:%S JST %Y")
