from urllib.parse import urlparse, parse_qs
import os, asyncio, re, json, requests
from datetime import datetime
from playwright.async_api import async_playwright
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

LINE_TOKEN = os.environ.get("LINE_TOKEN")
URL = os.environ.get("TASK_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def send_line_message(request_date, line_user_id, user_db_id, exception_dates=None):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    exception_set = exception_dates or set()
    message, new_exceptions = loop.run_until_complete(
        check_availability(request_date, exception_set)
    )
    loop.close()
    if not message:
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    body = {
        "to": line_user_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    response = requests.post(url, headers=headers, data=json.dumps(body))
    print("Status:", response.status_code)
    print(response.json())
    save_exception_dates(user_db_id, new_exceptions)

async def check_availability(request_date, exception_dates=None):
    print(f'Checking exception_dates: {exception_dates}')
    request_deadline = datetime.strptime(request_date, "%Y-%m-%d")
    availability_elements = []
    exception_set = exception_dates or set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded")

        # メニューを選択画面へ
        await page.get_by_text("空席確認・予約する").nth(0).click()
        await page.wait_for_load_state("load")

        # メニューを選択し空席確認へ
        cut_only = page.locator(f"p.couponMenuName", has_text="12月1日から2200円。カットのみ")
        count = await cut_only.count()
        # カットのみが含まれる要素が複数あるのでカットのみに完全一致する要素を探す
        for i in range(count):
            ele = cut_only.nth(i)
            text = await ele.text_content()
            if text.strip() == "12月1日から2200円。カットのみ":
                cut_only = ele
                break

        tr = cut_only.locator("xpath=ancestor::tr")
        await tr.locator("text=空席確認・予約する").click()
        await page.wait_for_load_state("load")

        # last_dateが含まれるページまでカレンダーを進め、空き日時を取得
        try:
            while True:
                calendar = page.locator("table.innerTable")
                last_date_tr = calendar.locator("tr.dayCellContainer")
                last_date_obj = await last_date_tr.locator("th:last-of-type").text_content()
                last_date = convert_to_ymd(last_date_obj)
                # カレンダーの空きを検出
                await page.screenshot(path="debug.png")
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

            count = len(availability_elements)
            print(f'count{count}')
            print(f'list{availability_elements}')

            # 空き日時がある場合、exception_datesに含まれない日付のみを抽出してメッセージを作成
            if count > 0:
                dates, exception_list = await create_avaliable_date_list(
                    availability_elements,
                    request_deadline,
                    exception_set
                )
                if dates:
                    print(dates)
                    return "空きがあります！\n" + dates, exception_list
            print("No available dates found.")
            return None, []
        finally:
            await browser.close()

async def create_avaliable_date_list(elements, request_deadline, exception_set):
    text = ""
    exception_list = []
    seen_datetimes = set()
    for ele in elements:
        url = await ele.get_attribute("href")
        if not url:
            continue
        print(f'url{url}')
        parsed_url = urlparse(url)
        params = parse_qs(parsed_url.query)
        print(f'params{params}')
        date_str = params.get("rsvRequestDate1", [""])[0]
        if not date_str:
            continue
        print(f'date{date_str}')
        date_obj = datetime.strptime(date_str, "%Y%m%d")

        if date_obj <= request_deadline:
            #datetimeに変換し、exception_datesに含まれない場合メッセージに追加
            time_str = params.get("rsvRequestTime1", [""])[0]
            if not time_str:
                continue
            dt_obj = datetime.strptime(date_str + time_str, "%Y%m%d%H%M")
            if dt_obj in seen_datetimes:
                print(f'Skipping duplicate date: {dt_obj}')
                continue
            if dt_obj in exception_set:
                print(f'Skipping exception date: {dt_obj}')
                continue
            seen_datetimes.add(dt_obj)
            display_date = format_date_for_display(date_str)
            display_time = format_time_for_display(time_str)
            text += f"{display_date} {display_time}\n"
            exception_list.append(dt_obj)
    return text, exception_list

def save_exception_dates(user_db_id, exception_list):
    if not exception_list:
        return
    payload = [
        {
            "user_id": user_db_id,
            "date": dt.isoformat()
        }
        for dt in exception_list
    ]
    supabase.table("exceptions_date").insert(payload).execute()

def format_date_for_display(date_str: str):
    jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    date_obj = datetime.strptime(date_str, "%Y%m%d")
    weekday_jp = jp_weekdays[date_obj.weekday()]
    return date_obj.strftime(f"%Y年%m月%d日（{weekday_jp}）")

def format_time_for_display(time_str: str):
    time_obj = datetime.strptime(time_str, "%H%M")
    return time_obj.strftime("%H:%M") 

def convert_to_ymd(date_str: str) -> datetime:
    # （水）など日本語の曜日部分を削除
    cleaned = re.sub(r"[（(].*?[)）]", "", date_str)
    # 日付文字列を datetime オブジェクトに変換
    return datetime.strptime(cleaned.strip(), "%a %b %d %H:%M:%S JST %Y")

def format_date(date_str: str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return date_obj.strftime("%Y-%m-%d")

if __name__ == "__main__":
    response = supabase.table("notification_setting").select(
        """
        user_id,
        last_date,
        user_info (
            line_user_id
        )
        """
    ).eq("get_notification", True).execute()
    print(response.data)

    for row in response.data:
        request_date = row["last_date"]
        if not request_date:
            continue
        line_user_id = row["user_info"]["line_user_id"]
        user_db_id = row["user_id"]
        exception_response = supabase.table("exceptions_date").select("date").eq("user_id", user_db_id).execute()
        exception_dates = [datetime.fromisoformat(d["date"]) for d in (exception_response.data or [])]
        exception_set = set(exception_dates)
        print(f'exception_dates main: {exception_dates}')
        send_line_message(request_date, line_user_id, user_db_id, exception_set)
