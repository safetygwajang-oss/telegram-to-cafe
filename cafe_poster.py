"""
네이버 카페 게시글 작성 - 최종본
- 자동 요약 (규칙 기반)
- 채널 통합 발행 (도배 방지)
- 자가진단 + 자동복구
"""
import re
import time
import urllib.parse
import requests

from config import (
    CAFE_ID, MENU_ID,
    MAX_TOTAL_BODY, MAX_PER_ITEM, MAX_SUBJECT_LEN,
    HTTP_TIMEOUT, RETRY_COUNT, RETRY_DELAY_SEC,
    get_env,
)
from utils import info, ok, fail, warn, remove_emojis, mask_forbidden, truncate


# ==========================================================
# 1. 토큰
# ==========================================================
def get_access_token() -> str:
    res = requests.get(
        "https://nid.naver.com/oauth2.0/token",
        params={
            "grant_type":    "refresh_token",
            "client_id":     get_env("NAVER_CLIENT_ID"),
            "client_secret": get_env("NAVER_CLIENT_SECRET"),
            "refresh_token": get_env("NAVER_REFRESH_TOKEN"),
        },
        timeout=HTTP_TIMEOUT,
    )
    data = res.json()
    if "access_token" not in data:
        raise RuntimeError(f"토큰 재발급 실패: {data}")
    ok("Access Token 발급 완료")
    return data["access_token"]


# ==========================================================
# 2. 문자 정제
# ==========================================================
def _sanitize(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[\ud800-\udfff]', '', text)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    text = re.sub(r'[\u200B-\u200D\uFE00-\uFE0F\uFFFD]', '', text)
    text = re.sub(r'[\u2500-\u257F\u2580-\u259F\u2600-\u26FF]', '', text)
    return text.encode('utf-8', errors='ignore').decode('utf-8')


# ==========================================================
# 3. 🆕 규칙 기반 자동 요약
# ==========================================================
def _summarize_body(body: str, max_len: int) -> str:
    """
    긴 텔레그램 원문을 규칙 기반으로 요약
    - 짧으면 그대로
    - 길면 핵심 문장만 추출 (첫 문단 + 숫자/퍼센트 포함 문장)
    """
    body = body.strip()
    if len(body) <= max_len:
        return body

    # 문장 단위 분할
    sentences = re.split(r'(?<=[.!?。])\s+|\n+', body)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return body[:max_len] + "..."

    # 우선순위 스코어링
    scored = []
    for i, sent in enumerate(sentences):
        score = 0
        # 앞 문장일수록 가점 (첫 3문장 필수)
        if i < 3:
            score += 100 - i * 10
        # 숫자/퍼센트 포함 (중요 정보)
        if re.search(r'\d+[.,]?\d*%|\d{2,}', sent):
            score += 20
        # 키워드 가점
        for kw in ['상승', '하락', '급등', '급락', '전망', '예상', '발표', '실적', 
                   '금리', 'CPI', 'PPI', 'GDP', '연준', 'Fed', '엔비디아', '삼성', 'AI',
                   '반도체', '2차전지', '배터리']:
            if kw in sent:
                score += 5
        # 너무 짧으면 감점
        if len(sent) < 10:
            score -= 50
        scored.append((score, i, sent))

    # 점수 높은 순 정렬 후 원래 순서로 재배열
    scored.sort(key=lambda x: -x[0])
    
    selected = []
    total_len = 0
    picked_idx = set()
    for score, idx, sent in scored:
        if total_len + len(sent) > max_len - 20:
            continue
        picked_idx.add(idx)
        total_len += len(sent) + 2
        if total_len >= max_len - 50:
            break

    # 원본 순서 복원
    result_sents = [sentences[i] for i in sorted(picked_idx)]
    summary = " ".join(result_sents)

    if len(summary) > max_len:
        summary = summary[:max_len - 5] + "..."

    return summary + "\n(요약)"


# ==========================================================
# 4. 제목 / 본문 빌더
# ==========================================================
def _build_subject(digest_list: list, date_str: str) -> str:
    """통합 제목"""
    total = sum(d["count"] for d in digest_list)
    return f"[{date_str}] 시황 브리핑 (총 {total}건)"


def _build_unified_content(digest_list: list) -> str:
    """
    🆕 모든 채널을 하나의 본문으로 통합
    - 채널별 섹션 구분
    - 각 메시지는 자동 요약
    """
    lines = []
    lines.append("=" * 40)
    lines.append(f"[일일 시황 브리핑]")
    lines.append(f"날짜: {digest_list[0]['date']}")
    lines.append(f"채널: {len(digest_list)}개")
    lines.append("=" * 40)
    lines.append("")

    # 채널 목록
    for d in digest_list:
        lines.append(f"  - {d['chat_name']}: {d['count']}건")
    lines.append("")

    current_size = len("\n".join(lines))
    per_item_limit = 400  # 🆕 항목당 400자로 축소

    for digest in digest_list:
        # 채널 헤더
        lines.append("")
        lines.append("#" * 40)
        lines.append(f"[ {digest['chat_name']} ]")
        lines.append("#" * 40)
        lines.append("")

        for i, item in enumerate(digest["items"], 1):
            time_str = item.get("date_kst", "")[11:16]
            raw_body = mask_forbidden(item.get("body", ""))
            
            # 🆕 자동 요약
            summarized = _summarize_body(raw_body, per_item_limit)

            block_lines = [
                f"[{i}. {time_str}]",
                summarized,
                "",
                "-" * 40,
                "",
            ]
            block_size = sum(len(l) + 1 for l in block_lines)

            # 전체 크기 체크
            if current_size + block_size > MAX_TOTAL_BODY - 300:
                lines.append("")
                lines.append(">> 길이 제한으로 이하 생략")
                current_size = MAX_TOTAL_BODY  # 더 이상 추가 안 함
                break

            lines.extend(block_lines)
            current_size += block_size

        if current_size >= MAX_TOTAL_BODY:
            break

    lines.append("")
    lines.append("=" * 40)
    lines.append("※ 본 정보는 참고용입니다.")
    lines.append("※ 투자 판단과 책임은 본인에게 있습니다.")
    lines.append("=" * 40)

    return "\n".join(lines)


# ==========================================================
# 5. HTTP 요청
# ==========================================================
def _post_once(subject: str, content: str, token: str) -> tuple[bool, int, str]:
    url = f"https://openapi.naver.com/v1/cafe/{CAFE_ID}/menu/{MENU_ID}/articles"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/x-www-form-urlencoded; charset=utf-8",
    }
    body = "&".join([
        f"subject={urllib.parse.quote(subject, safe='')}",
        f"content={urllib.parse.quote(content, safe='')}",
        "openyn=true",
    ])
    try:
        res = requests.post(url, headers=headers, data=body.encode("utf-8"), timeout=HTTP_TIMEOUT)
    except Exception as e:
        return False, 0, f"네트워크: {e}"

    try:
        result = res.json()
    except Exception:
        return False, res.status_code, f"파싱실패: {res.text[:200]}"

    status = result.get("message", {}).get("status")
    if status != "200":
        return False, res.status_code, f"status={status}, body={res.text[:250]}"

    return True, res.status_code, result["message"]["result"]["articleUrl"]


# ==========================================================
# 6. 🆕 통합 발행 (도배 방지)
# ==========================================================
def post_all_unified(digest_list: list, token: str) -> str | None:
    """
    모든 채널 → 1개 글로 통합 발행
    Rate Limit 회피용
    """
    if not digest_list:
        warn("발행할 내용 없음")
        return None

    date_str = digest_list[0]["date"]
    subject = _sanitize(remove_emojis(_build_subject(digest_list, date_str)))
    content = _sanitize(remove_emojis(_build_unified_content(digest_list)))

    info("=" * 60)
    info(f"📢 통합 발행 시작")
    info(f"  제목: {subject}")
    info(f"  본문: {len(content)}자")
    info(f"  채널: {len(digest_list)}개")
    info("=" * 60)

    # 3회 재시도 (간격 크게)
    delays = [0, 30, 90]  # 즉시 → 30초 → 90초
    for attempt, delay in enumerate(delays, 1):
        if delay > 0:
            info(f"  ⏳ {delay}초 대기 후 재시도... (Rate Limit 회피)")
            time.sleep(delay)

        info(f"\n  [시도 {attempt}/{len(delays)}]")
        success, code, result = _post_once(subject, content, token)

        if success:
            ok(f"  ✅ 성공: {result}")
            return result

        warn(f"  실패 [HTTP {code}]: {result[:200]}")

        # 500 에러이고 body에 특정 문구 있으면 → Rate Limit
        if "500" in result or code == 403:
            warn(f"  → Rate Limit 의심. 대기 시간 늘려서 재시도")

    # 최종 실패 - 진단
    fail("\n  ❌ 3회 모두 실패")
    fail("  가능한 원인:")
    fail(f"  1. 일일 API 발행 한도 초과 (하루 뒤 재시도)")
    fail(f"  2. 카페 도배 방지 (몇 시간 뒤 재시도)")
    fail(f"  3. API 권한 만료 (Refresh Token 재발급 필요)")
    fail(f"  4. CAFE_ID({CAFE_ID}) or MENU_ID({MENU_ID}) 오류")

    return None


# ==========================================================
# 7. 하위 호환 (기존 main.py가 호출하는 함수)
# ==========================================================
def post_to_cafe(digest: dict, token: str) -> str | None:
    """
    ⚠️ 기존 방식(채널별 개별 발행)은 Rate Limit에 걸림
    → post_all_unified() 사용 권장
    호환성을 위해 남겨두지만 실제로는 단일 채널을 리스트로 감싸서 처리
    """
    return post_all_unified([digest], token)
