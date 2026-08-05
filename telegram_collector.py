"""
텔레그램에서 지정 기간의 메시지 수집 → data/YYYY-MM-DD.json 저장
"""
import json
from datetime import datetime, timezone, timedelta
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message

from config import (
    KST, DATA_DIR, TARGET_CHATS,
    COLLECT_START_HOUR, COLLECT_LIMIT_PER_CHAT,
    get_env,
)
from utils import info, ok, warn


def _get_time_range():
    """어제 08:00 ~ 오늘 08:00 (KST)"""
    now = datetime.now(KST)
    today_start = now.replace(hour=COLLECT_START_HOUR, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    return yesterday_start, today_start


def fetch_messages():
    api_id     = int(get_env("TELEGRAM_API_ID"))
    api_hash   = get_env("TELEGRAM_API_HASH")
    session    = get_env("TELEGRAM_SESSION")

    start_kst, end_kst = _get_time_range()
    start_utc = start_kst.astimezone(timezone.utc)
    end_utc   = end_kst.astimezone(timezone.utc)

    info(f"수집 구간: {start_kst:%m-%d %H:%M} ~ {end_kst:%m-%d %H:%M} (KST)")

    results = []
    with TelegramClient(StringSession(session), api_id, api_hash) as client:
        for chat_id in TARGET_CHATS:
            try:
                entity = client.get_entity(chat_id)
                chat_name = getattr(entity, "title", str(chat_id))
            except Exception as e:
                warn(f"{chat_id} 접근 실패: {e}")
                continue

            count = 0
            for msg in client.iter_messages(
                entity, offset_date=end_utc, limit=COLLECT_LIMIT_PER_CHAT
            ):
                if not isinstance(msg, Message):
                    continue
                if msg.date < start_utc:
                    break
                text = (msg.message or "").strip()
                if not text:
                    continue

                results.append({
                    "chat_id":   str(chat_id),
                    "chat_name": chat_name,
                    "msg_id":    f"{chat_id}_{msg.id}",
                    "date_kst":  msg.date.astimezone(KST).isoformat(),
                    "text":      text,
                })
                count += 1

            info(f"  📥 {chat_name}: {count}건")

    results.sort(key=lambda x: x["date_kst"])
    ok(f"총 수집: {len(results)}건")
    return results


def save_results(messages):
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    output_file = DATA_DIR / f"{today_str}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

    ok(f"저장 완료: {output_file}")
    return output_file


if __name__ == "__main__":
    msgs = fetch_messages()
    save_results(msgs)

    print("\n" + "=" * 60)
    print("샘플 3건")
    print("=" * 60)
    for m in msgs[:3]:
        print(f"\n📌 [{m['date_kst'][:16]}] {m['chat_name']}")
        print(f"   {m['text'][:100]}")
