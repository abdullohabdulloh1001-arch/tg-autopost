"""
Workflow ishga tushganda: hozir yuborish kerakmi yoki yo'qmi, shuni hal qiladi.

GitHub cron faqat UTC biladi, UK esa yozda UTC+1, qishda UTC+0.
Shuning uchun send.yml da ikkita cron bor (bot ularni o'zi yozadi).
Bu skript hozirgi faslga mos keladiganini tanlaydi, ikkinchisi o'tkazib yuboriladi.
"""

import datetime
import json
import os
import sys
from zoneinfo import ZoneInfo


def expected_cron(hhmm, lead, offset_hours):
    h, m = map(int, hhmm.split(":"))
    total = (h * 60 + m - lead - offset_hours * 60) % 1440
    return f"{total % 60} {total // 60} * * *"


def decide():
    event = os.environ.get("EVENT", "")
    schedule = os.environ.get("SCHEDULE", "").strip()
    cfg = json.loads(open("config.json", encoding="utf-8").read())

    if event == "workflow_dispatch":
        return True, "qo'lda ishga tushirildi"
    if not cfg.get("enabled", True):
        return False, "bot orqali to'xtatilgan (enabled=false)"

    tz = ZoneInfo(cfg.get("tz", "Europe/London"))
    offset = int(datetime.datetime.now(tz).utcoffset().total_seconds() // 3600)
    want = expected_cron(cfg["time"], int(cfg.get("lead_minutes", 5)), offset)
    if schedule == want:
        return True, f"vaqt keldi ({cfg['time']} {cfg.get('tz')})"
    return False, f"bu cron ({schedule}) hozirgi faslga mos emas, kutilgani: {want}"


if __name__ == "__main__":
    run, why = decide()
    print(f"Yuboriladimi: {'HA' if run else 'YOQ'} - {why}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"run={'yes' if run else 'no'}\n")
    sys.exit(0)
