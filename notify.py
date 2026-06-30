import json
import os
import time
import urllib.request
import datetime
from zoneinfo import ZoneInfo

RETRIES = 3            # ลองดึงซ้ำกี่ครั้งถ้าพลาด
RETRY_WAIT = 2         # หน่วงกี่วินาทีก่อนลองใหม่
MAX_ABS_CHG = 35.0     # %เปลี่ยนแปลงเกินนี้ = น่าจะข้อมูลเพี้ยน ไม่ส่ง

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


def _yahoo_once(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    d = fetch_json(url)
    meta = d["chart"]["result"][0]["meta"]
    price = meta["regularMarketPrice"]
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    chg = (price - prev) / prev * 100 if prev else 0.0
    return float(price), float(chg)


def yahoo(symbol):
    """คืนค่า (ราคาปัจจุบัน, %เปลี่ยนแปลง) — ลองซ้ำถ้าพลาด + กรองค่าเพี้ยน"""
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            price, chg = _yahoo_once(symbol)
            # กันราคาเพี้ยน: ต้อง > 0 และ %เปลี่ยนแปลงไม่สุดโต่งผิดปกติ
            if price <= 0:
                raise ValueError(f"ราคาผิดปกติ ({price})")
            if abs(chg) > MAX_ABS_CHG:
                raise ValueError(f"%เปลี่ยนแปลงเพี้ยน ({chg:+.1f}%)")
            return price, chg
        except Exception as e:
            last_err = e
            print(f"RETRY {symbol} ({attempt}/{RETRIES}):", e)
            if attempt < RETRIES:
                time.sleep(RETRY_WAIT)
    raise last_err


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

# ทอง: USD/oz (บรรทัดบน) + THB/บาททอง (บรรทัดล่าง)
if gold:
    gold_usd, gold_chg = gold
    g = f"{arrow(gold_chg)} ทอง: ${gold_usd:,.0f}/oz ({gold_chg:+.2f}%)"
    if rate:
        thb_baht = gold_usd / OZ_TO_GRAM * BAHT_GOLD_GRAM * THAI_PURITY * rate
        g += f"\n      ฿{thb_baht:,.0f}/บาท"
    lines_common.append(g)
else:
    lines_common.append(fmt("ทอง", None, 0))

# BTC: USD (บรรทัดบน) + THB (บรรทัดล่าง)
if btc:
    btc_usd, btc_chg = btc
    b = f"{arrow(btc_chg)} BTC: ${btc_usd:,.0f} ({btc_chg:+.2f}%)"
    if rate:
        b += f"\n      ฿{btc_usd * rate:,.0f}"
    lines_common.append(b)
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

# "รอบนี้" = สลอตล่าสุดที่ผ่านมาแล้ว (cron ยิงตรงเวลาหรือช้ากว่าเสมอ ไม่มีทางก่อนเวลา)
# ถ้ายังไม่ถึงรอบแรกของวัน (ก่อน 04:10) ให้ถือเป็นรอบสุดท้ายของเมื่อวาน (23:10)
passed = [s for s in SLOTS if s[0] <= mins]
slot_min, profile = max(passed or SLOTS, key=lambda s: s[0])
slot_str = f"{slot_min // 60:02d}:{slot_min % 60:02d}"

# ทดสอบ: บังคับโปรไฟล์จากปุ่ม Run workflow (A/B/C) ทับเวลาอัตโนมัติ
override = os.environ.get("PROFILE", "auto").strip().upper()
if override in ("A", "B", "C"):
    profile = override
    slot_str = f"{slot_str} (ทดสอบ {profile})"

header = f"📊 สรุปราคา | {slot_str} ICT\n{now.strftime('%d %b %Y')}\n"

# เช็ควันทำการแยกแต่ละตลาด (จันทร์-ศุกร์ ตามเวลาท้องถิ่นของตลาดนั้น)
us_open_day = datetime.datetime.now(ZoneInfo("America/New_York")).weekday() < 5
th_open_day = datetime.datetime.now(ZoneInfo("Asia/Bangkok")).weekday() < 5

extra = []
note = ""
if profile == "A":
    if us_open_day:
        extra = stock_lines(US)
    else:
        note = "\n(สุดสัปดาห์ — ตลาดสหรัฐปิด ไม่มีราคาหุ้น/ดัชนี)"
elif profile == "C":
    if th_open_day:
        extra = stock_lines(TH)
    else:
        note = "\n(สุดสัปดาห์ — ตลาดไทยปิด ไม่มีราคาหุ้น/ดัชนี)"

body = header + "\n" + "\n".join(extra + lines_common)
body += note

# รอบส่งถัดไป (เวลาไทย) — สลอตแรกที่ยังไม่ถึง ไม่งั้นวนไปรอบแรกของวันพรุ่งนี้
slot_times = sorted(s[0] for s in SLOTS)
next_min = next((m for m in slot_times if m > mins), slot_times[0])
body += f"\n\n⏭️ รอบต่อไป {next_min // 60:02d}:{next_min % 60:02d} น."

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
