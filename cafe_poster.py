"""
네이버 카페 게시글 작성 - 🔬 디버깅 모드
어디서 깨지는지 단계별로 테스트
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
# 2. 이상 문자 제거
# ==========================================================
def _sanitize(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[\ud800-\udfff]', '', text)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    text = re.sub(r'[\u200B-\u200D\uFE00-\uFE0F\uFFFD]', '', text)
    text = re.sub(r'[\u2500-\u257F\u2580-\u259F\u2600-\u26FF]', '', text)
    text = text.encode('utf-8', errors='ignore').decode('utf-8')
    return text


# ==========================================================
# 3. 제목 / 본문 빌더
# ==========================================================
def _build_subject(items: list, date_str: str) -> str:
    if not items:
        return f"[{date_str}] 시황 브리핑"
    first_line = items[0].get("body", "").strip().split("\n")[0].strip()
    if len(first_line) < 5:
        return f"[{date_str}] 시황 브리핑"
    return truncate(first_line, MAX_SUBJECT_LEN)


def _build_headline(digest: dict) -> list[str]:
    return [
        "=" * 40,
        digest["chat_name"],
        f"[날짜] {digest['date']}  |  [총] {digest['count']}건",
        "=" * 40,
        "",
        "",
    ]


def _build_content(digest: dict) -> str:
    lines = _build_headline(digest)
    current_size = len("\n".join(lines))
    included = 0
    truncated = 0
    items = digest["items"]

    for i, item in enumerate(items, 1):
        time_str = item.get("date_kst", "")[11:16]
        body = mask_forbidden(item.get("body", ""))
        body = truncate(body, MAX_PER_ITEM, suffix="\n... (이하 생략)")

        header = f"[ {i}. {time_str} ]"
        separator = "-" * 40
        block = f"{header}\n{body}\n\n{separator}\n\n"

        if current_size + len(block) > MAX_TOTAL_BODY:
            truncated = len(items) - included
            break

        lines.extend([header, body, "", separator, ""])
        current_size += len(block)
        included += 1

    if truncated > 0:
        lines.extend(["", f">> 본문 길이 제한으로 {truncated}건은 생략되었습니다.", ""])

    lines.extend([
        "※ 본 정보는 참고용이며, 투자 판단의 근거로 사용하지 마세요.",
        "※ 투자에 대한 모든 책임은 본인에게 있습니다.",
    ])

    return "\n".join(lines)


# ==========================================================
# 4. 발행
# ==========================================================
def _post_once(subject: str, content: str, token: str) -> tuple[bool, str]:
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

    res = requests.post(
        url,
        headers=headers,
        data=body.encode("utf-8"),
        timeout=HTTP_TIMEOUT,
    )

    info(f"    응답 코드: {res.status_code}")

    try:
        result = res.json()
    except Exception:
        return False, f"JSON 파싱 실패: {res.text[:200]}"

    status = result.get("message", {}).get("status")
    if status != "200":
        return False, f"status={status}, body={res.text[:300]}"

    article_url = result["message"]["result"]["articleUrl"]
    return True, article_url


# ==========================================================
# 5. 🔬 디버깅 모드 발행
# ==========================================================
def post_to_cafe(digest: dict, token: str) -> str | None:
    """
    🔬 디버깅: 어디서 깨지는지 단계별로 테스트
    """
    raw_subject = _build_subject(digest["items"], digest["date"])
    raw_content = _build_content(digest)

    subject = _sanitize(remove_emojis(raw_subject))
    content = _sanitize(remove_emojis(raw_content))

    info(f"  [원본] 제목 {len(subject)}자 / 본문 {len(content)}자")
    info("=" * 60)
    info("🔬 디버깅 모드: 단계별 테스트 시작")
    info("=" * 60)

    test_cases = [
        ("A. 초간단 ASCII",        "Test Subject",     "Hello World"),
        ("B. 한글 짧게",           "테스트 제목",       "안녕하세요 테스트입니다"),
        ("C. 실제제목+짧은본문",   subject,             "본문 테스트"),
        ("D. 짧은제목+실제본문",   "테스트 제목",       content),
        ("E. 실제제목+실제본문",   subject,             content),
    ]

    for label, test_subj, test_cont in test_cases:
        info(f"\n  🔬 {label}")
        info(f"    제목 {len(test_subj)}자 / 본문 {len(test_cont)}자")
        success, result = _post_once(test_subj, test_cont, token)

        if success:
            ok(f"    ✅ {label} 성공: {result}")
        else:
            fail(f"    ❌ {label} 실패: {result[:200]}")
            fail(f"\n  🎯🎯🎯 범인 확정: '{label}' 단계에서 실패")
            fail(f"  → 이 단계에서 새로 추가된 요소가 원인입니다")
            return None

        time.sleep(3)

    ok("\n  🎉 모든 단계 성공! (예상 못한 결과 - 재분석 필요)")
    return "디버깅 완료"
