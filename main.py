"""
메인 오케스트레이터
1. 오늘자 JSON 로드
2. 파싱 + 중복 제거
3. 채널별 그룹화
4. 카페 발행
5. 상태 저장
"""
import json
import time
from collections import defaultdict
from datetime import datetime

from config import (
    KST, DATA_DIR, STATE_FILE,
    MAX_HASH_HISTORY, POST_INTERVAL_SEC,
)
from message_parser import parse
from cafe_poster import get_access_token, post_to_cafe
from utils import info, ok, warn, fail


# ==========================================================
# 상태 관리
# ==========================================================
def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"posted_hashes": [], "last_run": None}


def save_state(state: dict):
    state["posted_hashes"] = state["posted_hashes"][-MAX_HASH_HISTORY:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ==========================================================
# 데이터 로드
# ==========================================================
def load_today_messages() -> list:
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    data_file = DATA_DIR / f"{today_str}.json"

    if not data_file.exists():
        warn(f"데이터 파일 없음: {data_file}")
        return []

    with open(data_file, "r", encoding="utf-8") as f:
        return json.load(f)


# ==========================================================
# 메인
# ==========================================================
def main():
    info(f"🚀 시작: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 상태 로드
    state = load_state()
    posted_hashes = set(state["posted_hashes"])
    info(f"기존 게시 이력: {len(posted_hashes)}건")

    # 2. 오늘자 메시지 로드
    raw_msgs = load_today_messages()
    info(f"JSON 로드: {len(raw_msgs)}건")

    # 3. 파싱 + 중복 제거
    items = []
    for m in raw_msgs:
        p = parse(m)
        if not p:
            continue
        if p["hash"] in posted_hashes:
            continue
        items.append(p)

    info(f"신규 유효 메시지: {len(items)}건")

    if not items:
        info("📭 새 메시지 없음. 종료.")
        state["last_run"] = datetime.now(KST).isoformat()
        save_state(state)
        return

    # 4. 채널별 그룹화
    grouped = defaultdict(list)
    for item in items:
        grouped[item["chat_name"]].append(item)

    info(f"채널 수: {len(grouped)}개")
    for ch, msgs in grouped.items():
        info(f"  - {ch}: {len(msgs)}건")

    # 5. 토큰 발급
    token = get_access_token()

    # 6. 채널별 발행
    today = datetime.now(KST).strftime("%Y-%m-%d")
    success = 0
    failure = 0

    for idx, (chat_name, msgs) in enumerate(grouped.items(), 1):
        msgs.sort(key=lambda x: x["date_kst"])

        digest = {
            "date":      today,
            "chat_name": chat_name,
            "count":     len(msgs),
            "items":     msgs,
        }

        info(f"\n[{idx}/{len(grouped)}] 📢 {chat_name} 발행 중...")
        try:
            url = post_to_cafe(digest, token)
            if url:
                success += 1
                for msg in msgs:
                    posted_hashes.add(msg["hash"])
                ok(f"완료: {url}")
            else:
                failure += 1
                warn("실패 (hash 저장 안 함 → 다음 실행 시 재시도)")
        except Exception as e:
            failure += 1
            fail(f"오류: {e}")

        if idx < len(grouped):
            info(f"⏳ {POST_INTERVAL_SEC}초 대기...")
            time.sleep(POST_INTERVAL_SEC)

    # 7. 결과 요약
    print()
    ok(f"🎉 전체 완료: 성공 {success}건 / 실패 {failure}건")

    # 8. 상태 저장
    state["posted_hashes"] = list(posted_hashes)
    state["last_run"] = datetime.now(KST).isoformat()
    save_state(state)


if __name__ == "__main__":
    main()
