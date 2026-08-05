import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message

KST = timezone(timedelta(hours=9))

# 🔑 환경변수 (GitHub Secrets)
API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION_STRING = os.environ["TELEGRAM_SESSION"]

# 🎯 수집할 텔레그램 방 목록
TARGET_CHATS = [
    -1001304649917,   # 키움증권 전략/시황 한지영
    -1001157157231,   # 사제콩이_서상영
]

# 📁 저장 폴더
OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)


def fetch_last_24h_messages():
    """어제 08:00 ~ 오늘 08:00 (KST) 사이의 메시지 수집"""
    now_kst = datetime.now(KST)
    today_8am = now_kst.replace(hour=8, minute=0, second=0, microsecond=0)
    yesterday_8am = today_8am - timedelta(days=1)

    start_utc = yesterday_8am.astimezone(timezone.utc)
    end_utc = today_8am.astimezone(timezone.utc)

    print(f"📅 수집 구간: {yesterday_8am:%Y-%m-%d %H:%M} ~ {today_8am:%Y-%m-%d %H:%M} (KST)")

    results = []
    with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        for chat in TARGET_CHATS:
            try:
                entity = client.get_entity(chat)
                chat_name = getattr(entity, 'title', str(chat))
            except Exception as e:
                print(f"  ⚠️ {chat} 접근 실패: {e}")
                continue

            count = 0
            for msg in client.iter_messages(entity, offset_date=end_utc, limit=500):
                if not isinstance(msg, Message):
                    continue
                if msg.date < start_utc:
                    break
                text = (msg.message or "").strip()
                if not text:
                    continue

                results.append({
                    "chat_id": str(chat),
                    "chat_name": chat_name,
                    "msg_id": f"{chat}_{msg.id}",
                    "date_kst": msg.date.astimezone(KST).isoformat(),
                    "text": text,
                })
                count += 1

            print(f"  📥 {chat_name}: {count}건")

    results.sort(key=lambda x: x["date_kst"])
    print(f"📊 총 수집: {len(results)}건")
    return results


def save_results(messages):
    """JSON 파일로 저장 (날짜별)"""
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    output_file = OUTPUT_DIR / f"{today_str}.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    
    print(f"💾 저장 완료: {output_file}")
    return output_file


if __name__ == "__main__":
    msgs = fetch_last_24h_messages()
    save_results(msgs)
    
    print("\n" + "=" * 60)
    print("샘플 3건:")
    print("=" * 60)
    for m in msgs[:3]:
        print(f"\n📌 [{m['date_kst'][:16]}] {m['chat_name']}")
        print(f"   {m['text'][:100]}")
