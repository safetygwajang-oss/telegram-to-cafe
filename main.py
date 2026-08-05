"""
메인 오케스트레이터 - 통합 발행 최종본
1. 오늘자 JSON 로드
2. 파싱 + 중복 제거
3. 채널별 그룹화
4. 🆕 모든 채널을 1개 글로 통합 발행 (Rate Limit 회피)
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
from cafe_poster import get_access_token, post_all_unified
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

    # 6. 🆕 digest_list 구성 (채널별 → 하나의 리스트로)
    today = datetime.now(KST).strftime("%Y-%m-%d")
    digest_list = []

    for chat_name, msgs in grouped.items():
        msgs.sort(key=lambda x: x["date_kst"])
        digest_list.append({
            "date":      today,
            "chat_name": chat_name,
            "count":     len(msgs),
            "items":     msgs,
        })

    # 7. 🆕 통합 발행 (1개 글로 몰빵)
    info(f"\n📢 {len(digest_list)}개 채널을 1개 글로 통합 발행 시작")
    info("=" * 60)

    success_flag = False
    total_msgs = sum(d["count"] for d in digest_list)

    try:
        url = post_all_unified(digest_list, token)
        if url:
            success_flag = True
            # 성공 시 모든 메시지 hash 저장
            for digest in digest_list:
                for msg in digest["items"]:
                    posted_hashes.add(msg["hash"])
            ok(f"🎉 통합 발행 완료: {url}")
        else:
            warn("통합 발행 실패 (hash 저장 안 함 → 다음 실행 시 재시도)")
    except Exception as e:
        fail(f"발행 중 예외: {e}")
        import traceback
        fail(traceback.format_exc())

    # 8. 결과 요약
    print()
    if success_flag:
        ok(f"🎉 전체 완료: {len(digest_list)}개 채널 / 총 {total_msgs}건 발행 성공")
    else:
        fail(f"❌ 전체 실패: {len(digest_list)}개 채널 / 총 {total_msgs}건 미발행")
        info("💡 대응 방법:")
        info("   1. 네이버 카페에서 오늘 올라간 테스트 글 삭제")
        info("   2. 1~2시간 후 재실행 (Rate Limit 해제 대기)")
        info("   3. 그래도 안 되면 Refresh Token 재발급 확인")

    # 9. 상태 저장
    state["posted_hashes"] = list(posted_hashes)
    state["last_run"] = datetime.now(KST).isoformat()
    save_state(state)


if __name__ == "__main__":
    main()
