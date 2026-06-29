import json
import os
import urllib.request
import datetime

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# น้ำหนักทอง: 1 ออนซ์ = 31.1035 กรัม | ทอง 1 บาท = 15.244 กรัม | ทองแท่งไทย 96.5%
OZ_TO_GRAM = 31.1035
BAHT_GOLD_GRAM = 15.244
THAI_PURITY = 0.965


def fetch_json(url, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def yahoo(symbol):
    """คืนค่า (ราคาปัจจุบัน, %เปลี่ยนแปลง) จาก Yahoo Finance"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    d = fetch_json(url)
    meta = d["chart"]["result"][0]["meta"]
    price = meta["regularMarketPrice"]
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    chg = (price - prev) / prev * 100 if prev else 0.0
    return float(price), float(chg)


def arrow(chg):
    return "🟢▲" if chg >= 0 else "🔴▼"


def safe(fn):
    """เรียก fn() ถ้า error คืน None เพื่อไม่ให้ทั้งข้อความล่ม"""
    try:
        return fn()
    except Exception as e:
        print("WARN:", e)
        return None


def fmt(label, value_str, chg):
    if value_str is None:
        return f"⚠️ {label}: n/a"
    return f"{arrow(chg)} {label}: {value_str} ({chg:+.2f}%)"


# ---------- ดึงข้อมูลพื้นฐาน (ทุกรอบมี) ----------
usdthb = safe(lambda: yahoo("THB=X"))
gold = safe(lambda: yahoo("GC=F"))      # ทอง USD/oz
btc = safe(lambda: yahoo("BTC-USD"))    # BTC USD

rate = usdthb[0] if usdthb else None

# ---------- สร้างบรรทัด ----------
lines_common = []

# USD/THB
if usdthb:
    lines_common.append(fmt("USD/THB", f"{usdthb[0]:,.2f}", usdthb[1]))
else:
    lines_common.append(fmt("USD/THB", None, 0))

# ทอง: USD/oz + THB/บาททอง
if gold:
    gold_usd, gold_chg = gold
    g = f"${gold_usd:,.0f}/oz"
    if rate:
        thb_baht = gold_usd / OZ_TO_GRAM * BAHT_GOLD_GRAM * THAI_PURITY * rate
        g += f" | ฿{thb_baht:,.0f}/บาท"
    lines_common.append(fmt("ทอง", g, gold_chg))
else:
    lines_common.append(fmt("ทอง", None, 0))

# BTC: USD + THB
if btc:
    btc_usd, btc_chg = btc
    b = f"${btc_usd:,.0f}"
    if rate:
        b += f" | ฿{btc_usd * rate:,.0f}"
    lines_common.append(fmt("BTC", b, btc_chg))
else:
    lines_common.append(fmt("BTC", None, 0))


def stock_lines(items):
    """items = [(label, symbol, '$'|''), ...]"""
    out = []
    for label, sym, prefix in items:
        r = safe(lambda s=sym: yahoo(s))
        if r:
            out.append(fmt(label, f"{prefix}{r[0]:,.2f}", r[1]))
        else:
            out.append(fmt(label, None, 0))
    return out


US = [("S&P500", "^GSPC", ""), ("GOOGL", "GOOGL", "$"), ("AMD", "AMD", "$")]
TH = [("SET", "^SET.BK", ""), ("SCB", "SCB.BK", "฿"), ("AOT", "AOT.BK", "฿")]

# ---------- เลือกโปรไฟล์ตามเวลาไทย ----------
# slot (นาทีในวัน) -> โปรไฟล์: A=หุ้นสหรัฐ, B=พื้นฐาน, C=หุ้นไทย
SLOTS = [
    (4 * 60 + 10, "A"),   # 04.10
    (9 * 60 + 40, "B"),   # 09.40
    (12 * 60 + 40, "C"),  # 12.40
    (16 * 60 + 40, "C"),  # 16.40
    (20 * 60 + 40, "B"),  # 20.40
    (23 * 60 + 10, "A"),  # 23.10
]

now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
mins = now.hour * 60 + now.minute
slot_min, profile = min(SLOTS, key=lambda s: abs(mins - s[0]))
slot_str = f"{slot_min // 60:02d}:{slot_min % 60:02d}"

header = f"📊 สรุปราคา | {slot_str} ICT\n{now.strftime('%d %b %Y')}\n"

extra = []
if profile == "A":
    extra = stock_lines(US)
elif profile == "C":
    extra = stock_lines(TH)

body = header + "\n" + "\n".join(extra + lines_common)
body += f"\n\n🕐 ส่งจริง {now.strftime('%H:%M')}"

# ---------- ส่ง LINE ----------
token = os.environ["LINE_TOKEN"]
user = os.environ["LINE_USER_ID"]
payload = json.dumps({
    "to": user,
    "messages": [{"type": "text", "text": body}],
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
print(body)
