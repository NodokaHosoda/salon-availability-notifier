from urllib.parse import urlparse, parse_qs
import os, asyncio, re, json, requests
from datetime import datetime
from playwright.async_api import async_playwright
from supabase import create_client

LINE_TOKEN = os.environ.get("LINE_TOKEN")
URL = os.environ.get("TASK_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def send_line_message(request_date, user_id, exception_dates=None):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    message = loop.run_until_complete(check_availability(request_date, exception_dates))
    loop.close()
    if not message:
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    body = {
        "to": user_id,
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

async def check_availability(request_date, exception_dates=None):
    print(f'Checking exception_dates: {exception_dates}')
    #request_date = datetime.strptime(REQUEST_DATE, "%Y%m%d")
    availability_elements = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded")

        # メニューを選択画面へ
        await page.get_by_text("空席確認・予約する").nth(0).click()
        await page.wait_for_load_state("load")

        # メニューを選択し空席確認へ
        cut_only = page.locator(f"p.couponMenuName", has_text="カットのみ")
        count = await cut_only.count()
        # カットのみが含まれる要素が複数あるのでカットのみに完全一致する要素を探す
        for i in range(count):
            ele = cut_only.nth(i)
            text = await ele.text_content()
            if text.strip() == "カットのみ":
                cut_only = ele
                break

        tr = cut_only.locator("xpath=ancestor::tr")
        await tr.locator("text=空席確認・予約する").click()
        await page.wait_for_load_state("load")

        while True:
            calendar = page.locator("table.innerTable")
            last_date_tr = calendar.locator("tr.dayCellContainer")
            last_date_obj = await last_date_tr.locator("th:last-of-type").text_content()
            last_date = convert_to_ymd(last_date_obj)
            # カレンダーの空きを検出
            await page.screenshot(path="debug.png")
            availability_elements += await calendar.locator("a.icnOpen").all()

            if last_date < request_date:
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
        if count > 0:
            data = await create_avaliable_date_list(availability_elements)
            if data:
                print(data)
                return "空きがあります！\n"+ data
        print("No available dates found.")
        await browser.close()
        return False

async def create_avaliable_date_list(elements):
    text = ""
    for ele in elements:
        url = await ele.get_attribute("href")
        print(f'url{url}')
        parsed_url = urlparse(url)
        params = parse_qs(parsed_url.query)
        print(f'params{params}')
        date = params.get("rsvRequestDate1", [""])[0]
        print(f'date{date}')
        date_obj = datetime.strptime(date, "%Y%m%d")
        formatted_date = date_obj.strftime("%Y-%m-%d")

        if formatted_date <= request_date:
            time = params.get("rsvRequestTime1", [""])[0]
            date = format_date(formatted_date)
            time = format_time(time)
            text += f"{date} {time}\n"
    return text

def format_date(date_str: str):
    jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    date_obj = datetime.strptime(date_str, "%Y%m%d")
    weekday_jp = jp_weekdays[date_obj.weekday()]
    return date_obj.strftime(f"%Y年%m月%d日（{weekday_jp}）")

def format_time(time_str: str):
    time_obj = datetime.strptime(time_str, "%H%M")
    return time_obj.strftime("%H:%M") 

def convert_to_ymd(date_str: str) -> datetime:
    # （水）など日本語の曜日部分を削除
    cleaned = re.sub(r"[（(].*?[)）]", "", date_str)
    # 日付文字列を datetime オブジェクトに変換
    return datetime.strptime(cleaned.strip(), "%a %b %d %H:%M:%S JST %Y")

if __name__ == "__main__":
    response = supabase.table("notification_setting").select(
        """
        last_date,
        user_info (
            line_user_id,
            exceptions_date(date)
        )
        """
    ).eq("get_notification", True).execute()

    for row in response.data:
        user_id = row["user_info"]["line_user_id"]
        request_date = row["last_date"]
        exception_dates = [d["date"] for d in row.get("exceptions_date", [])]
        send_line_message(request_date, user_id, exception_dates)