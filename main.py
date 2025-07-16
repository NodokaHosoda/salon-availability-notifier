from urllib.parse import urlparse, parse_qs
import time, os, asyncio, re
from datetime import datetime
from playwright.async_api import async_playwright


LINE_TOKEN = os.environ.get("LINE_TOKEN")
URL = "https://beauty.hotpepper.jp/slnH000440848/"

"""
TODO: LINE通知の実装
def send_line_notify(message):
    if not LINE_TOKEN:
        print("LINE_TOKEN is missing")
        return
    requests.post(
        "https://notify-api.line.me/api/notify",
        headers={"Authorization": f"Bearer {LINE_TOKEN}"},
        data={"message": message}
    )
"""

async def check_availability():
    date = "20250814"
    request_date = datetime.strptime(date, "%Y%m%d")
    availability_elements = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
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
        if count > 0:
            data = await create_avaliable_date_list(availability_elements, request_date)
            print(data)
        else:
            print("No available dates found.")

        await browser.close()

async def create_avaliable_date_list(elements, request_date: datetime):
    text = ""
    for ele in elements:
        url = await ele.get_attribute("href")
        parsed_url = urlparse(url)
        params = parse_qs(parsed_url.query)
        date = params.get("rsvRequestDate1", [""])[0]

        if datetime.strptime(date, "%Y%m%d") <= request_date:
            time = params.get("rsvRequestTime1", [""])[0]
            date = format_date(date)
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
    asyncio.run(check_availability())