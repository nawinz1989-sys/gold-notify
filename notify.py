import json
import os
import urllib.request
import datetime


def get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


# ดึงราคาทอง + อัตราแลกเปลี่ยน
gold = get("https://api.gold-api.com/price/XAU")["price"]
thb = get("https://api.exchangerate-api.com/v4/latest/USD")["rates"]["THB"]
gold_thb = gold * thb

# เวลาไทย (UTC+7)
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
dt = now.strftime("%d %b %Y %H:%M")

msg = (
    "\n🥇 ราคาทองแท่ง\n"
    f"💰 XAU/USD: ${gold:,.2f} /oz\n"
    f"💱 USD/THB: {thb:.2f} บาท\n"
    f"🏆 ทอง/oz (THB): {gold_thb:,.0f} บาท\n"
    f"⏰ {dt} ICT"
)

# ส่งผ่าน LINE Messaging API (push)
token = os.environ["LINE_TOKEN"]
user = os.environ["LINE_USER_ID"]
payload = json.dumps({
    "to": user,
    "messages": [{"type": "text", "text": msg}],
}).encode("utf-8")

req = urllib.request.Request(
    "https://api.line.me/v2/bot/message/push",
    data=payload,
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
)
with urllib.request.urlopen(req) as r:
    print("LINE status:", r.status)
    print(msg)
