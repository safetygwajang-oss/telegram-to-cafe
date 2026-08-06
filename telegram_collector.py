"""
텔레그램에서 지정 기간의 메시지 수집 → data/YYYY-MM-DD.json 저장
- 시간 범위 필터
- 스팸/광고 자동 제외
- 최소 길이 필터
- 중복 제거 (해시 기반)
- 채널별 그룹핑
"""
import json
from datetime import datetime, timezone, timedelta
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message

from config import (
    KST, DATA_DIR, TARGET_CHATS,
    COLLECT_START_HOUR, COLLECT_LIMIT_PER_CHAT,
    MIN_MSG_LEN,
    get_env,
)
from utils import (
    info, ok, warn,
    is_spam, content_hash, mask_forbidden,
)


# ==========================================================
# 1. 수집 구간
# ==========================================================
def _get_time_range():
    """어제 08:00 ~ 오늘 08:00 (KST)"""
    now = datetime.now(KST)
    today_start = now.replace(
        hour=COLLECT_START_HOUR, minute=0, second=0, microsecond=0
    )
    yesterday_start = today_start - timedelta(days=1)
    return yesterday_start, today_start


# ==========================================================
# 2. 메시지 유효성 검사
# ==========================================================
def _is_valid_message(text: str) -> tuple[bool, str]:
    """
    메시지가 발행 가치가 있는지 판단
    반환: (통과여부, 사유)
    """
    if not text or not text.strip():
        return False, "빈 메시지"

    if len(text) < MIN_MSG_LEN:
        return False, f"너무 짧음({len(text)}자)"

    if is_spam(text):
        return False, "스팸패턴 매칭"

    return True, "OK"


# ==========================================================
# 3. 텔레그램 수집
# ==========================================================
def fetch_messages():
    api_id   = int(get_env("TELEGRAM_API_ID"))
    api_hash = get_env("TELEGRAM_API_HASH")
    session  = get_env("TELEGRAM_SESSION")

    start_kst, end_kst = _get_time_range()
    start_utc = start_kst.astimezone(timezone.utc)
    end_utc   = end_kst.astimezone(timezone.utc)

    info(f"수집 구간: {start_kst:%m-%d %H:%M} ~ {end_kst:%m-%d %H:%M} (KST)")

    if not TARGET_CHATS:
        warn("TARGET_CHATS 가 비어있음")
        return []

    results = []
    seen_hashes = set()  # 채널 간 중복 제거용

    with TelegramClient(StringSession(session), api_id, api_hash) as client:
        for chat_id in TARGET_CHATS:
            try:
                entity = client.get_entity(chat_id)
                chat_name = getattr(entity, "title", str(chat_id))
            except Exception as e:
                warn(f"{chat_id} 접근 실패: {e}")
                continue

            raw_count      = 0
            filtered_count = 0
            dup_count      = 0
            passed_count   = 0

            try:
                for msg in client.iter_messages(
                    entity,
                    offset_date=end_utc,
                    limit=COLLECT_LIMIT_PER_CHAT,
                ):
                    if not isinstance(msg, Message):
                        continue
                    if msg.date < start_utc:
                        break

                    raw_count += 1
                    text = (msg.message or "").strip()

                    # 1) 유효성 검사
                    is_valid, reason = _is_valid_message(text)
                    if not is_valid:
                        filtered_count += 1
                        continue

                    # 2) 중복 검사 (같은 내용이 여러 채널에서 올라올 수 있음)
                    h = content_hash(text)
                    if h in seen_hashes:
                        dup_count += 1
                        continue
                    seen_hashes.add(h)

                    # 3) 금칙어 마스킹 (원본 저장 전에 이미 처리)
                    cleaned_text = mask_forbidden(text)

                    results.append({
                        "chat_id":   str(chat_id),
                        "chat_name": chat_name,
                        "msg_id":    f"{chat_id}_{msg.id}",
                        "date_kst":  msg.date.astimezone(KST).isoformat(),
                        "text":      cleaned_text,
                        "hash":      h,
                    })
                    passed_count += 1

            except Exception as e:
                warn(f"{chat_name} 수집 중 에러: {e}")
                continue

            info(
                f"  📥 {chat_name}: "
                f"원본 {raw_count} → 필터 {filtered_count} / 중복 {dup_count} "
                f"→ 통과 {passed_count}건"
            )

    # 시간순 정렬 (오래된 순)
    results.sort(key=lambda x: x["date_kst"])
    ok(f"총 수집: {len(results)}건")
    return results


# ==========================================================
# 4. JSON 저장
# ==========================================================
def save_results(messages):
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    output_file = DATA_DIR / f"{today_str}.json"

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        ok(f"저장 완료: {output_file} ({len(messages)}건)")
    except Exception as e:
        warn(f"저장 실패: {e}")

    return output_file


# ==========================================================
# 5. 🆕 채널별 그룹핑 (cafe_poster 용)
# ==========================================================
def build_digest_list(messages: list) -> list:
    """
    수집한 메시지들을 채널별로 그룹핑
    cafe_poster.post_all_unified() 에서 쓰는 형태로 변환

    반환 예시:
    [
      {
        "date": "2026-08-06",
        "chat_name": "키움증권 전략/시황 한지영",
        "count": 5,
        "items": [
          {"date_kst": "...", "body": "..."},
          ...
        ]
      },
      ...
    ]
    """
    today_str = datetime.now(KST).strftime("%Y-%m-%d")

    # 채널별 그룹핑
    grouped = {}
    for m in messages:
        chat_name = m["chat_name"]
        if chat_name not in grouped:
            grouped[chat_name] = []
        grouped[chat_name].append({
            "date_kst": m["date_kst"],
            "body":     m["text"],
        })

    digest_list = []
    for chat_name, items in grouped.items():
        # 시간순 정렬 (오래된 → 최신)
        items.sort(key=lambda x: x["date_kst"])
        digest_list.append({
            "date":      today_str,
            "chat_name": chat_name,
            "count":     len(items),
            "items":     items,
        })

    # 채널 순서: 메시지 많은 순
    digest_list.sort(key=lambda x: -x["count"])

    return digest_list


# ==========================================================
# 6. 단독 실행 (테스트용)
# ==========================================================
if __name__ == "__main__":
    msgs = fetch_messages()
    save_results(msgs)

    print("\n" + "=" * 60)
    print("샘플 3건")
    print("=" * 60)
    for m in msgs[:3]:
        print(f"\n📌 [{m['date_kst'][:16]}] {m['chat_name']}")
        print(f"   {m['text'][:100]}")

    print("\n" + "=" * 60)
    print("채널별 그룹핑 결과")
    print("=" * 60)
    digest = build_digest_list(msgs)
    for d in digest:
        print(f"  - {d['chat_name']}: {d['count']}건")
