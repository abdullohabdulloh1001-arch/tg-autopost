"""
Kanal/guruhlarga o'z akkauntingizdan xabar yuboradi. Har bir til guruhiga o'z tilidagi matn.

Kerakli muhit o'zgaruvchilari (GitHub Secrets):
    API_ID, API_HASH, SESSION

Fayllar (har bir til uchun juftlik):
    channels_uz.txt + message_uz.txt   - o'zbekcha guruhlar va o'zbekcha matn
    channels_en.txt + message_en.txt   - inglizcha guruhlar va inglizcha matn
    channels_ru.txt + message_ru.txt   - ruscha guruhlar va ruscha matn
    image_uz.jpg / image_en.jpg / image_ru.jpg  - ixtiyoriy, shu tilga rasm
    image.jpg  - ixtiyoriy, hamma tillar uchun umumiy rasm

    channels.txt + message.txt  - eski variant, til fayllari bo'lmasa ishlatiladi

channels_*.txt: har qatorda bitta kanal (@username, t.me/... link, -100... ID yoki "me").
message_*.txt: HTML (bot o'zi shunday saqlaydi): <b>qalin</b>, <i>kursiv</i>, <a href="...">link</a>
message.txt (eski variant): Markdown: **qalin**, __kursiv__, [link](https://...)
TEST_MODE=1 bo'lsa, hamma matnlar faqat o'zingizga (Saved Messages) yuboriladi.

Sinash uchun: DRY_RUN=1 python send.py  (hech narsa yubormaydi, faqat ko'rsatadi)
"""

import asyncio
import os
import random
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
LANGS = ["uz", "en", "ru"]
IMAGE_EXTS = [".jpg", ".jpeg", ".png"]

# Har bir yuborish orasidagi pauza (soniya). Spamga tushmaslik uchun kamaytirmang.
MIN_DELAY = 8
MAX_DELAY = 20

CAPTION_LIMIT = 1024  # Telegram rasm ostidagi matn chegarasi


def read_channels(path):
    channels = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()  # # dan keyingisi izoh
        if not line:
            continue
        if line.lower() in ("me", "self"):
            channels.append("me")  # Saved Messages (Избранное) - test uchun
            continue
        line = line.replace("https://", "").replace("http://", "")
        if line.startswith("t.me/"):
            line = line[len("t.me/"):]
            if line.startswith("+") or line.startswith("joinchat"):
                print(f"[!] Yopiq taklif linki ishlamaydi, raqamli ID ishlating: {line}")
                continue
            parts = line.split("/")
            if parts[0] == "c" and len(parts) > 1 and parts[1].isdigit():
                line = "-100" + parts[1]  # t.me/c/123... yopiq kanal xabar linki
            else:
                line = "@" + parts[0]
        if line.lstrip("-").isdigit():
            channels.append(int(line))
        else:
            channels.append(line if line.startswith("@") else "@" + line)
    return channels


def find_image(stem):
    for ext in IMAGE_EXTS:
        p = BASE / f"{stem}{ext}"
        if p.exists():
            return p
    return None


def load_jobs():
    """[(nom, kanallar, matn, rasm, parse_mode), ...] ro'yxatini qaytaradi."""
    jobs = []
    common_image = find_image("image")
    for lang in LANGS:
        cf, mf = BASE / f"channels_{lang}.txt", BASE / f"message_{lang}.txt"
        if not (cf.exists() and mf.exists()):
            continue
        channels = read_channels(cf)
        text = mf.read_text(encoding="utf-8").strip()
        if not channels or not text:
            print(f"[{lang}] kanal yoki matn bo'sh, o'tkazib yuborildi")
            continue
        jobs.append((lang, channels, text, find_image(f"image_{lang}") or common_image, "html"))

    if not jobs:  # eski variant: channels.txt + message.txt
        cf, mf = BASE / "channels.txt", BASE / "message.txt"
        if cf.exists() and mf.exists():
            channels = read_channels(cf)
            text = mf.read_text(encoding="utf-8").strip()
            if channels and text:
                jobs.append(("asosiy", channels, text, common_image, "md"))

    if not jobs:
        print("Yuboriladigan narsa yo'q: botda matn va kanallarni kiriting.")
        sys.exit(0)
    if os.environ.get("TEST_MODE", "").strip() == "1":
        print("TEST REJIMI: hammasi faqat Saved Messages'ga yuboriladi")
        jobs = [(name, ["me"], text, image, pm) for name, _, text, image, pm in jobs]
    return jobs


async def send_all(jobs):
    from telethon import TelegramClient
    from telethon.errors import (
        ChatWriteForbiddenError,
        ChannelPrivateError,
        FloodWaitError,
        SlowModeWaitError,
        UserBannedInChannelError,
    )
    from telethon.sessions import StringSession

    api_id = os.environ.get("API_ID", "").strip()
    api_hash = os.environ.get("API_HASH", "").strip()
    session = os.environ.get("SESSION", "").strip()
    if not (api_id and api_hash and session):
        sys.exit("API_ID, API_HASH yoki SESSION topilmadi. GitHub Secrets'ni tekshiring.")

    total = sum(len(j[1]) for j in jobs)
    ok, failed = [], []
    stop = False
    async with TelegramClient(StringSession(session), int(api_id), api_hash) as client:
        me = await client.get_me()
        print(f"Akkaunt: {me.first_name} (@{me.username})")

        uploads = {}
        first = True
        for name, channels, text, image, pm in jobs:
            print(f"\n=== {name.upper()}: {len(channels)} ta ===")
            if image and image not in uploads:
                uploads[image] = await client.upload_file(image)
            uploaded = uploads.get(image)

            for i, ch in enumerate(channels):
                if stop:
                    failed.append(ch)
                    continue
                if not first:
                    await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
                first = False
                try:
                    if uploaded and len(text) <= CAPTION_LIMIT:
                        await client.send_file(ch, uploaded, caption=text, parse_mode=pm)
                    elif uploaded:
                        await client.send_file(ch, uploaded)
                        await client.send_message(ch, text, parse_mode=pm, link_preview=False)
                    else:
                        await client.send_message(ch, text, parse_mode=pm, link_preview=False)
                    print(f"[OK]   {ch}")
                    ok.append(ch)
                except FloodWaitError as e:
                    print(f"[STOP] Telegram {e.seconds} soniya kutishni so'radi. Qolganlari keyingi safar.")
                    failed.append(ch)
                    stop = True
                except SlowModeWaitError as e:
                    print(f"[SKIP] {ch}: slow mode, {e.seconds} soniyadan keyin mumkin")
                    failed.append(ch)
                except (ChatWriteForbiddenError, UserBannedInChannelError):
                    print(f"[SKIP] {ch}: bu yerga yozishga ruxsat yo'q")
                    failed.append(ch)
                except ChannelPrivateError:
                    print(f"[SKIP] {ch}: kanal yopiq yoki siz a'zo emassiz")
                    failed.append(ch)
                except Exception as e:  # noqa: BLE001
                    print(f"[ERR]  {ch}: {type(e).__name__}: {e}")
                    failed.append(ch)

    print(f"\nYuborildi: {len(ok)}/{total}")
    if failed:
        print("Yuborilmadi: " + ", ".join(map(str, failed)))
    if not ok:
        sys.exit(1)  # hammasi xato bo'lsa, GitHub qizil belgi ko'rsatadi


def main():
    jobs = load_jobs()

    if os.environ.get("DRY_RUN", "").strip() == "1":
        print("DRY RUN - hech narsa yuborilmaydi")
        for name, channels, text, image, pm in jobs:
            image_name = image.name if image else "yo'q"
            print(f"\n=== {name.upper()} ===")
            print(f"Kanallar ({len(channels)}): {channels}")
            print(f"Rasm: {image_name}")
            if image and len(text) > CAPTION_LIMIT:
                print(f"Matn {len(text)} belgi, {CAPTION_LIMIT} dan uzun: rasm va matn alohida ketadi")
            print(f"Matn:\n{text}")
        return

    asyncio.run(send_all(jobs))


if __name__ == "__main__":
    main()
