import os
from datetime import datetime, timezone, timedelta
from telethon.sync import TelegramClient
from telethon.tl.types import Message

KST = timezone(timedelta(hours=9))

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]

# 🎯 수집할 텔레그램 방 목록
# - 공개 채널: "@channel_username"
# - 비공개 방: 방 이름 문자열 또는 채널 ID(정수)
TARGET_CHATS = [
    "@economy_daily_room",   # ← 실제 값으로 교체
]

SESSION_NAME = "tg_session"


def fetch_last_24h_messages():
    """
    어제 08:00 ~ 오늘 08:00 (KST) 사이의 메시지 수집
    매일 08:00에 실행되므로 '지난 24시간'과 동일
    """
    now_kst = datetime.now(KST)
    today_8am = now_kst.replace(hour=8, minute=0, second=0, microsecond=0)
    yesterday_8am = today_8am - timedelta(days=1)

    # Telethon 비교용 UTC 변환
    start_utc = yesterday_8am.astimezone(timezone.utc)
    end_utc = today_8am.astimezone(timezone.utc)

    print(f"📅 수집 구간: {yesterday_8am:%Y-%m-%d %H:%M} ~ {today_8am:%Y-%m-%d %H:%M} (KST)")

    results = []
    with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        for chat in TARGET_CHATS:
            try:
                entity = client.get_entity(chat)
            except Exception as e:
                print(f"  ⚠️ {chat} 접근 실패: {e}")
                continue

            count = 0
            for msg in client.iter_messages(entity, offset_date=end_utc, limit=500):
                if not isinstance(msg, Message):
                    continue
                if msg.date < start_utc:
                    break  # 24시간보다 오래된 건 중단
                text = (msg.message or "").strip()
                if not text:
                    continue

                results.append({
                    "chat": str(chat),
                    "msg_id": f"{chat}_{msg.id}",
                    "date_kst": msg.date.astimezone(KST).isoformat(),
                    "text": text,
                })
                count += 1

            print(f"  📥 {chat}: {count}건")

    # 오래된 것부터 정렬
    results.sort(key=lambda x: x["date_kst"])
    print(f"📊 총 수집: {len(results)}건")
    return results


if __name__ == "__main__":
    msgs = fetch_last_24h_messages()
    print("\n" + "=" * 60)
    print("샘플 3건:")
    print("=" * 60)
    for m in msgs[:3]:
        print(f"\n📌 [{m['date_kst'][:16]}]")
        print(f"   {m['text'][:100]}")
