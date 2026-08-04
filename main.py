import json
import os
from datetime import datetime, timezone, timedelta

from telegram_collector import fetch_last_24h_messages
from message_parser import parse
from cafe_poster import get_access_token, post_to_cafe

KST = timezone(timedelta(hours=9))
STATE_FILE = "posted_messages.json"


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


def main():
    print(f"🚀 시작: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}")

    state = load_state()
    posted_hashes = set(state["posted_hashes"])
    print(f"📚 기존 게시 이력: {len(posted_hashes)}건 (해시 기준)")

    # 1) 지난 24시간 텔레그램 메시지 수집
    raw_msgs = fetch_last_24h_messages()

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

    # 3) 하루치를 하나의 브리핑으로 묶기
    digest_info = {
        "date": datetime.now(KST).strftime("%Y-%m-%d"),
        "count": len(items),
        "items": items,
    }

    # 4) 카페 게시
    token = get_access_token()
    print(f"✅ Access Token 발급")

    try:
        url = post_to_cafe(digest_info, token)
        if url:
            print(f"\n🎉 완료: {url}")
        else:
            print(f"\n❌ 게시 실패")
            return
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        return

    # 5) 상태 저장
    state["posted_hashes"] = list(posted_hashes)
    state["last_run"] = datetime.now(KST).isoformat()
    save_state(state)


if __name__ == "__main__":
    main()
