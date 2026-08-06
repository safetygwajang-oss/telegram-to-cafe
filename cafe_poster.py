"""
네이버 카페 게시글 자동 발행
- 채널별로 분할 발행 (본문 길이 문제 회피)
- 제목: 2026. 08. 06. THU WORLD ECONOMY NEWS (N) - 채널명
"""
import re
import time
import urllib.parse
from datetime import datetime
import requests

from config import (
    CAFE_ID, MENU_ID,
    MAX_TOTAL_BODY, MAX_PER_ITEM, MAX_SUBJECT_LEN,
    HTTP_TIMEOUT, RETRY_COUNT, RETRY_DELAY_SEC,
    get_env,
)
from utils import info, ok, fail, warn, remove_emojis, mask_forbidden


# ==========================================================
# 1. Access Token 발급
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
    """네이버 카페 API가 싫어할만한 문자 제거"""
    if not text:
        return ""
    text = re.sub(r'[\ud800-\udfff]', '', text)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    text = re.sub(r'[\u200B-\u200D\uFE00-\uFE0F\uFFFD]', '', text)
    return text.encode('utf-8', errors='ignore').decode('utf-8')


# ==========================================================
# 3. 요약
# ==========================================================
def _summarize_body(body: str, max_len: int) -> str:
    body = body.strip()
    if len(body) <= max_len:
        return body

    sentences = re.split(r'(?<=[.!?。])\s+|\n+', body)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        cut = body[:max_len]
        last_space = cut.rfind(' ')
        if last_space > max_len * 0.8:
            cut = cut[:last_space]
        return cut + "..."

    result = []
    total = 0
    for sent in sentences:
        if total + len(sent) + 1 > max_len - 5:
            break
        result.append(sent)
        total += len(sent) + 1

    if not result:
        return sentences[0][:max_len - 3] + "..."

    summary = " ".join(result)
    if len(result) < len(sentences):
        summary += " ..."
    return summary


# ==========================================================
# 4. 제목 / 본문 빌더
# ==========================================================
def _format_date_with_weekday(date_str: str) -> str:
    """
    '2026-08-06' → '2026. 08. 06. THU'
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday_map = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        wd = weekday_map[dt.weekday()]
        return f"{dt.year}. {dt.month:02d}. {dt.day:02d}. {wd}"
    except Exception:
        return date_str


def _build_subject(date_str: str, index: int, total: int, chat_name: str) -> str:
    """
    2026. 08. 06. THU WORLD ECONOMY NEWS (1/2) 키움증권 한지영
    """
    date_formatted = _format_date_with_weekday(date_str)
    # 채널명에서 특수문자 제거 (URL 인코딩 이슈 회피)
    safe_chat_name = re.sub(r'[^\w가-힣\s]', '', chat_name).strip()
    subject = f"{date_formatted} WORLD ECONOMY NEWS ({index}/{total}) {safe_chat_name}"
    return subject[:MAX_SUBJECT_LEN]


def _build_channel_content(digest: dict, date_str: str) -> str:
    """
    채널 하나의 본문 생성
    """
    lines = []
    date_formatted = _format_date_with_weekday(date_str)

    lines.append(f"[{date_formatted}]")
    lines.append(f"Channel: {digest['chat_name']}")
    lines.append(f"Messages: {digest['count']}")
    lines.append("")
    lines.append("-" * 30)
    lines.append("")

    current_size = sum(len(l) + 1 for l in lines)

    for i, item in enumerate(digest["items"], 1):
        time_str = item.get("date_kst", "")[11:16]
        raw_body = mask_forbidden(item.get("body", ""))
        summarized = _summarize_body(raw_body, MAX_PER_ITEM)

        block_lines = [
            f"{i}. {time_str}",
            summarized,
            "",
        ]
        block_size = sum(len(l) + 1 for l in block_lines)

        # 채널당 본문도 너무 길면 자름
        if current_size + block_size > MAX_TOTAL_BODY - 500:
            lines.append("")
            lines.append("... (length limit)")
            break

        lines.extend(block_lines)
        current_size += block_size

    lines.append("")
    lines.append("-" * 30)
    lines.append("※ 참고용 정보입니다. 투자 판단은 본인 책임입니다.")

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
    content_html = content.replace("\n", "<br>")

    body = "&".join([
        f"subject={urllib.parse.quote(subject, safe='')}",
        f"content={urllib.parse.quote(content_html, safe='')}",
    ])
    try:
        res = requests.post(
            url, headers=headers,
            data=body.encode("utf-8"),
            timeout=HTTP_TIMEOUT,
        )
    except Exception as e:
        return False, 0, f"네트워크: {e}"

    info(f"    [DEBUG] HTTP {res.status_code} | {res.text[:200]}")

    try:
        result = res.json()
    except Exception:
        return False, res.status_code, f"파싱실패: {res.text[:200]}"

    status = result.get("message", {}).get("status")
    if status != "200":
        return False, res.status_code, f"status={status}"

    return True, res.status_code, result["message"]["result"]["articleUrl"]


# ==========================================================
# 6. 분할 발행 (채널별)
# ==========================================================
def post_all_unified(digest_list: list, token: str) -> str | None:
    """
    채널별로 나눠서 각각 발행
    - 하나라도 성공하면 마지막 성공 URL 반환
    - 각 발행 사이 15초 대기 (도배 방지)
    """
    if not digest_list:
        warn("발행할 내용 없음")
        return None

    date_str = digest_list[0]["date"]
    total = len(digest_list)

    info("=" * 60)
    info(f"📢 분할 발행 시작: 총 {total}개 채널")
    info("=" * 60)

    success_urls = []
    failed_channels = []

    for idx, digest in enumerate(digest_list, 1):
        chat_name = digest["chat_name"]
        subject = _sanitize(remove_emojis(
            _build_subject(date_str, idx, total, chat_name)
        ))
        content = _sanitize(remove_emojis(
            _build_channel_content(digest, date_str)
        ))

        info("")
        info(f"[{idx}/{total}] {chat_name}")
        info(f"  제목: {subject}")
        info(f"  본문: {len(content)}자")

        # 각 채널당 3회 재시도
        delays = [0, 15, 45]
        posted = False

        for attempt, delay in enumerate(delays, 1):
            if delay > 0:
                info(f"  ⏳ {delay}초 대기...")
                time.sleep(delay)

            info(f"  [시도 {attempt}/{len(delays)}]")
            success, code, result = _post_once(subject, content, token)

            if success:
                ok(f"  ✅ 성공: {result}")
                success_urls.append(result)
                posted = True
                break
            else:
                warn(f"  실패 [HTTP {code}]: {result[:150]}")

        if not posted:
            fail(f"  ❌ {chat_name} 3회 모두 실패")
            failed_channels.append(chat_name)

        # 다음 채널로 넘어가기 전 도배 방지 대기
        if idx < total:
            info(f"  ⏳ 다음 채널까지 15초 대기 (도배 방지)")
            time.sleep(15)

    # 최종 결과 요약
    info("")
    info("=" * 60)
    info(f"📊 최종 결과")
    info(f"  성공: {len(success_urls)}/{total}")
    info(f"  실패: {len(failed_channels)}/{total}")
    if failed_channels:
        warn(f"  실패 채널: {', '.join(failed_channels)}")
    info("=" * 60)

    if success_urls:
        for url in success_urls:
            ok(f"  🔗 {url}")
        return success_urls[-1]

    return None
