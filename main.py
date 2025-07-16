from urllib.parse import urlparse, parse_qs
import time, os, requests, asyncio
from datetime import datetime
from playwright.async_api import async_playwright # type: ignore


LINE_TOKEN = os.environ.get("LINE_TOKEN")
URL = "https://beauty.hotpepper.jp/slnH000440848/"
def send_line_notify(message):
    if not LINE_TOKEN:
        print("LINE_TOKEN is missing")
        return
    requests.post(
        "https://notify-api.line.me/api/notify",
        headers={"Authorization": f"Bearer {LINE_TOKEN}"},
        data={"message": message}
    )

async def check_availability():
    date = "20250923"
    request_date = datetime.strptime(date, "%Y%m%d")
    availability_elements = []

    async with async_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded")

        # メニューを選択画面へ
        page.get_by_text("空席確認・予約する").click()
        page.wait_for_load_state("load")

        # メニューを選択し空席確認へ
        tr = page.locator(f"p.couponMenuName", has_text="カットのみ").locator("xpath=ancestor::tr")
        tr.locator("text=空席確認・予約する").click()
        page.wait_for_load_state("load")

        while True:
            calendar = page.locator("table.innerTable")
            curr_month = calendar.locator("th.monthCell").text_content()
            last_date_tr = calendar.locator("tr.dayCellContainer")
            text = await last_date_tr.locator("th:last-of-type").text_content()
            date = text.split("\n")[0]
            date = curr_month.replace("年", "-").replace("月", "-") + date
            last_date = datetime.strptime(date, "%Y-%m-%d")
            # カレンダーの空きを検出
            availability_elements += await calendar.locator("a.icnOpen").all()

            if(last_date < request_date):
                # 次の一週間へ
                calendar.locator("a.arrowPagingWeekR").click()
                page.wait_for_load_state("load")
            else:
                break

        count = availability_elements.count()
        if count > 0:
            data = create_avaliable_date_list(availability_elements)
            console.log(data)

        browser.close()

def create_avaliable_date_list(elements):
    for ele in range(elements):
        url = ele.get_attribute("href")
        parsed_url = urlparse(href)
        params = parse_qs(parsed_url.query)
        date = params.get("rsvRequestDate1", [""])[0]
        time = params.get("rsvRequestTime1", [""])[0]
        date = format_date(date)
        time = format_time(time)
        text += f"{date} {time}\n"
    return text

def format_date(str: date):
    jp_weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    date_obj = datetime.strptime(date, "%Y%m%d")
    weekday_jp = jp_weekdays[date_obj.weekday()]
    return date_obj.strftime(f"%Y年%m月%d日（{weekday_jp}）")

def format_time(str: time):
    time_obj = datetime.strptime(time, "%H%M")
    return time_obj.strftime("%H:%M") 

if __name__ == "__main__":
    check_availability()

