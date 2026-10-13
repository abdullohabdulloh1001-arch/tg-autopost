"""
Kanallar/guruhlarga bir xil xabarni o'z akkauntingizdan yuboradi.

Kerakli muhit o'zgaruvchilari (GitHub Secrets):
    API_ID, API_HASH, SESSION

Fayllar:
    channels.txt  - har qatorda bitta kanal (@username, t.me/... link yoki -100... ID)
    message.txt   - yuboriladigan matn (Markdown: **qalin**, __kursiv__, [link](https://...))
    image.jpg / image.png  - ixtiyoriy rasm, bo'lsa xabar rasm bilan ketadi

Sinash uchun: DRY_RUN=1 python send.py  (hech narsa yubormaydi, faqat ko'rsatadi)
"""

import asyncio
import os
import random
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
CHANNELS_FILE = BASE / "channels.txt"
MESSAGE_FILE = BASE / "message.txt"
IMAGE_NAMES = ["image.jpg", "image.jpeg", "image.png"]

# Har bir yuborish orasidagi pauza (soniya). Spamga tushmaslik uchun kamaytirmang.
MIN_DELAY = 8
MAX_DELAY = 20

CAPTION_LIMIT = 1024  # Telegram rasm ostidagi matn chegarasi


def read_channels():
    if not CHANNELS_FILE.exists():
        sys.exit("channels.txt topilmadi")
    channels = []
    for line in CHANNELS_FILE.read_text(encoding="utf-8").splitlines():
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
    if not channels:
        sys.exit("channels.txt bo'sh")
    return channels


def read_message():
    if not MESSAGE_FILE.exists():
        sys.exit("message.txt topilmadi")
    text = MESSAGE_FILE.read_text(encoding="utf-8").strip()
    if not text:
        sys.exit("message.txt bo'sh")
    return text


def find_image():
    for name in IMAGE_NAMES:
        p = BASE / name
        if p.exists():
            return p
    return None


async def send_all(channels, text, image):
    from telethon import TelegramClient
    from telethon.errors import (
        ChatWriteForbiddenError,
        ChannelPrivateError,
        FloodWaitError,
        SlowModeWaitError,
        UserBannedInChannelError,
    )
    from telethon.sessions import StringSession

    api_id = os.environ.get("API_ID")
    api_hash = os.environ.get("API_HASH")
    session = os.environ.get("SESSION")
    if not (api_id and api_hash and session):
        sys.exit("API_ID, API_HASH yoki SESSION topilmadi. GitHub Secrets'ni tekshiring.")

    ok, failed = [], []
    async with TelegramClient(StringSession(session), int(api_id), api_hash) as client:
        me = await client.get_me()
        print(f"Akkaunt: {me.first_name} (@{me.username})")

        # Matn juda uzun bo'lsa, rasm alohida, matn alohida ketadi
        uploaded = await client.upload_file(image) if image else None

        for i, ch in enumerate(channels):
            try:
                if uploaded and len(text) <= CAPTION_LIMIT:
                    await client.send_file(ch, uploaded, caption=text, parse_mode="md")
                elif uploaded:
                    await client.send_file(ch, uploaded)
                    await client.send_message(ch, text, parse_mode="md", link_preview=False)
                else:
                    await client.send_message(ch, text, parse_mode="md", link_preview=False)
                print(f"[OK]   {ch}")
                ok.append(ch)
            except FloodWaitError as e:
                print(f"[STOP] Telegram {e.seconds} soniya kutishni so'radi. Qolganlari keyingi safar.")
                failed.extend(channels[i:])
                break
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

            if i < len(channels) - 1:
                await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    print(f"\nYuborildi: {len(ok)}/{len(channels)}")
    if failed:
        print("Yuborilmadi: " + ", ".join(map(str, failed)))
    if not ok:
        sys.exit(1)  # hammasi xato bo'lsa, GitHub qizil belgi ko'rsatadi


def main():
    channels = read_channels()
    text = read_message()
    image = find_image()

    if os.environ.get("DRY_RUN", "").strip() == "1":
        print("DRY RUN - hech narsa yuborilmaydi\n")
        print(f"Kanallar ({len(channels)}): {channels}")
        image_name = image.name if image else "yo'q"
        print(f"Rasm: {image_name}")
        if image and len(text) > CAPTION_LIMIT:
            print(f"Matn {len(text)} belgi, {CAPTION_LIMIT} dan uzun: rasm va matn alohida ketadi")
        print(f"\nMatn:\n{text}")
        return

    asyncio.run(send_all(channels, text, image))


if __name__ == "__main__":
    main()
