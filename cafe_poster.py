"""
네이버 카페 게시글 작성
- 이상 문자 완전 제거 후 명시적 URL 인코딩으로 전송
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
    """refresh_token으로 access_token 재발급"""
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
# 2. 이상 문자 제거 (네이버 API 403 방지)
# ==========================================================
def _sanitize(text: str) -> str:
    """
    네이버 카페 API가 거부하는 문자 완전 제거:
    - 서로게이트 잔재 (U+D800 ~ U+DFFF)
    - 제어문자 (개행/탭 제외)
    - ZWJ, variation selector 등 이모지 결합자 잔재
    - U+FFFD (replacement char)
    """
    if not text:
        return ""
    text = re.sub(r'[\ud800-\udfff]', '', text)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    text = re.sub(r'[\u200B-\u200D\uFE00-\uFE0F\uFFFD]', '', text)
    text = text.encode('utf-8', errors='ignore').decode('utf-8')
    return text


# ==========================================================
# 3. 제목 / 본문 빌더
# ==========================================================
def _build_subject(items: list, date_str: str) -> str:
    """첫 메시지의 첫 줄을 제목으로"""
    if not items:
        return f"[{date_str}] 시황 브리핑"

    first_line = items[0].get("body", "").strip().split("\n")[0].strip()

    if len(first_line) < 5:
        return f"[{date_str}] 시황 브리핑"

    return truncate(first_line, MAX_SUBJECT_LEN)


def _build_headline(digest: dict) -> list[str]:
    return [
        "━━━━━━━━━━━━━━━━━━━━━━━",
        digest["chat_name"],
        f"📅 {digest['date']}  |  📊 총 {digest['count']}건",
        "━━━━━━━━━━━━━━━━━━━━━━━",
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
        block = f"{header}\n{body}\n\n----------------------------------------\n\n"

        if current_size + len(block) > MAX_TOTAL_BODY:
            truncated = len(items) - included
            break

        lines.extend([header, body, "", "----------------------------------------", ""])
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
    """
    단일 요청.
    ⭐ 테스트 워크플로우와 동일한 방식으로 body 직접 조립.
    """
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

    info(f"  응답 코드: {res.status_code}")

    # 실패 시 디버깅용 본문 샘플
    if res.status_code != 200:
        info(f"  본문 앞 100자: {repr(content[:100])}")

    try:
        result = res.json()
    except Exception:
        return False, f"JSON 파싱 실패: {res.text[:200]}"

    status = result.get("message", {}).get("status")
    if status != "200":
        return False, f"status={status}, body={res.text[:300]}"

    article_url = result["message"]["result"]["articleUrl"]
    return True, article_url


def post_to_cafe(digest: dict, token: str) -> str | None:
    """
    카페에 게시글 작성 (재시도 포함)
    반환: 성공 시 URL, 실패 시 None
    """
    # 1. 제목/본문 생성
    raw_subject = _build_subject(digest["items"], digest["date"])
    raw_content = _build_content(digest)

    # 2. 이모지 제거 + 이상 문자 완전 제거
    subject = _sanitize(remove_emojis(raw_subject))
    content = _sanitize(remove_emojis(raw_content))

    info(f"  제목: {subject}")
    info(f"  본문: {len(content)}자")

    # 3. 재시도 루프
    last_error = ""
    for attempt in range(1, RETRY_COUNT + 2):
        success, result = _post_once(subject, content, token)
        if success:
            return result

        last_error = result
        warn(f"  시도 {attempt} 실패: {result}")
        if attempt <= RETRY_COUNT:
            time.sleep(RETRY_DELAY_SEC)

    fail(f"  최종 실패: {last_error}")
    return None
