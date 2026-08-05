import json
import os
from pathlib import Path
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
