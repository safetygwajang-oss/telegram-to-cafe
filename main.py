import json
import os
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from message_parser import parse
from cafe_poster import get_access_token, post_to_cafe

KST = timezone(timedelta(hours=9))
STATE_FILE = "posted_messages.json"
DATA_DIR = Path("data")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"posted_hashes": [], "last_run": None}


def save_state(state):
    # 최근 3000개만 유지 (파일 무한증가 방지)
    state["posted_hashes"] = state["posted_hashes"][-3000:]
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_today_messages():
    """오늘 날짜 JSON 파일에서 메시지 로드"""
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    data_file = DATA_DIR / f"{today_str}.json"

    if not data_file.exists():
        print(f"⚠️ 데이터 파일이 없습니다: {data_file}")
        return []

    with open(data_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    print(f"🚀 시작: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}")

    state = load_state()
    posted_hashes = set(state["posted_hashes"])
    print(f"📚 기존 게시 이력: {len(posted_hashes)}건 (해시 기준)")

    # 1) JSON 파일에서 오늘자 메시지 로드
    raw_msgs = load_today_messages()
    print(f"📥 JSON에서 로드: {len(raw_msgs)}건")

    # 2) 정제·중복 제거
    items = []
    for m in raw_msgs:
        p = parse(m)
        if not p:
            continue
        if p["hash"] in posted_hashes:
            continue
        items.append(p)
        posted_hashes.add(p["hash"])

    print(f"🆕 신규 유효 메시지: {len(items)}건")

    if not items:
        print("📭 새 메시지가 없습니다. 종료.")
        state["last_run"] = datetime.now(KST).isoformat()
        save_state(state)
        return

    # 3) ⭐ 톡방(채널)별로 그룹화
    grouped = defaultdict(list)
    for item in items:
        grouped[item["chat_name"]].append(item)

    print(f"📊 채널 수: {len(grouped)}개")
    for ch, msgs in grouped.items():
        print(f"   - {ch}: {len(msgs)}건")

    # 4) 토큰 발급 (1회)
    token = get_access_token()

    # 5) ⭐ 톡방별로 개별 게시글 발행
    today = datetime.now(KST).strftime("%Y-%m-%d")
    success_count = 0
    fail_count = 0

    for idx, (chat_name, msgs) in enumerate(grouped.items(), 1):
        # 시간순 정렬 (오래된 것부터)
        msgs.sort(key=lambda x: x["date_kst"])

        digest_info = {
            "date": today,
            "chat_name": chat_name,
            "count": len(msgs),
            "items": msgs,
        }

        print(f"\n[{idx}/{len(grouped)}] 📢 {chat_name} 발행 중...")
        try:
            url = post_to_cafe(digest_info, token)
            if url:
                success_count += 1
                print(f"  🎉 완료: {url}")
            else:
                fail_count += 1
                print(f"  ❌ 실패")
        except Exception as e:
            fail_count += 1
            print(f"  ❌ 오류: {e}")

        # ⚠️ 스팸 필터 회피: 톡방 간 5초 대기
        if idx < len(grouped):
            print("  ⏳ 5초 대기...")
            time.sleep(5)

    print(f"\n🎉 전체 완료: 성공 {success_count}건 / 실패 {fail_count}건")

    # 6) 상태 저장
    state["posted_hashes"] = list(posted_hashes)
    state["last_run"] = datetime.now(KST).isoformat()
    save_state(state)


if __name__ == "__main__":
    main()
