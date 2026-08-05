import os
import requests

CAFE_ID = "31767633"
MENU_ID = "16"

# ==========================================================
# 🎯 본문 크기 제한
# 네이버 카페 API는 본문 크기에 제한이 있음.
# HTML 엔티티 변환 + URL 인코딩 시 3~4배로 부풀기 때문에
# 원문 기준 5000자 이내가 안전.
# ==========================================================
MAX_TOTAL_BODY = 5000   # 본문 전체 최대 길이 (원문 기준)
MAX_PER_ITEM = 1500     # 개별 메시지 최대 길이
MAX_SUBJECT_LEN = 90    # 네이버 카페 제목 최대 길이


def get_access_token():
    CLIENT_ID = os.environ["NAVER_CLIENT_ID"]
    CLIENT_SECRET = os.environ["NAVER_CLIENT_SECRET"]
    REFRESH_TOKEN = os.environ["NAVER_REFRESH_TOKEN"]

    res = requests.get(
        "https://nid.naver.com/oauth2.0/token",
        params={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": REFRESH_TOKEN,
        },
        timeout=10
    )
    data = res.json()
    if "access_token" not in data:
        raise RuntimeError("토큰 재발급 실패: " + str(data))
    print("✅ Access Token 발급")
    return data["access_token"]


def to_html_entity(text):
    """비-ASCII 문자를 HTML 엔티티로 변환"""
    result = ""
    for ch in text:
        if ord(ch) < 128:
            result += ch
        else:
            result += "&#" + str(ord(ch)) + ";"
    return result


def clean_forbidden_words(text):
    """출처 노출 방지"""
    if not text:
        return text
    forbidden = ["iSAFETY", "isafety", "ISAFETY", "iSafety", "아이세이프티", "아이세이프"]
    for word in forbidden:
        text = text.replace(word, "")
    return text.strip()


def extract_subject_from_first_msg(items, date_str):
    """
    ⭐ 첫 메시지의 첫 줄을 카페 게시글 제목으로 사용
    예: "[8/5, 장 시작 전 생각: 갈아타기 vs 추가하기, 키움 한지영]"
    """
    if not items:
        return "[" + date_str + "] 시황 브리핑"

    first_body = items[0].get("body", "").strip()
    first_line = first_body.split("\n")[0].strip()

    # 첫 줄이 너무 짧거나 비어있으면 fallback
    if len(first_line) < 5:
        return "[" + date_str + "] 시황 브리핑"

    # 길이 제한 (90자 초과 시 자르기)
    if len(first_line) > MAX_SUBJECT_LEN:
        first_line = first_line[:MAX_SUBJECT_LEN - 3] + "..."

    return first_line


def build_headline_box(digest_info):
    """본문 최상단 헤드라인 박스 - 채널명 + 날짜 + 건수"""
    lines = []
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📢 " + digest_info["chat_name"])
    lines.append("📅 " + digest_info["date"] + "  |  📊 총 " + str(digest_info["count"]) + "건")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    return lines


def build_content(digest_info):
    """본문 - 헤드라인 박스 + 시간순 메시지 목록 (크기 제한 적용)"""
    lines = []
    items = digest_info["items"]

    # ========== 헤드라인 박스 ==========
    lines.extend(build_headline_box(digest_info))
    lines.append("")
    lines.append("")

    # ========== 시간순 메시지 목록 (크기 제한) ==========
    current_size = len("\n".join(lines))
    truncated_count = 0
    included_count = 0

    for i, item in enumerate(items, 1):
        # 시간 (HH:MM)
        time_str = item.get("date_kst", "")[11:16] if item.get("date_kst") else ""
        body = clean_forbidden_words(item.get("body", ""))

        # 개별 메시지 길이 제한
        if len(body) > MAX_PER_ITEM:
            body = body[:MAX_PER_ITEM] + "\n... (이하 생략)"

        # 이 블록의 예상 크기 계산
        header = "[ " + str(i) + ". " + time_str + " ]"
        block_text = header + "\n" + body + "\n\n----------------------------------------\n\n"

        # 전체 본문 크기 초과 예상되면 중단
        if current_size + len(block_text) > MAX_TOTAL_BODY:
            truncated_count = len(items) - included_count
            break

        lines.append(header)
        lines.append(body)
        lines.append("")
        lines.append("----------------------------------------")
        lines.append("")

        current_size += len(block_text)
        included_count += 1

    # 잘린 경우 안내
    if truncated_count > 0:
        lines.append("")
        lines.append(">> 본문 길이 제한으로 " + str(truncated_count) + "건은 생략되었습니다.")
        lines.append("")

    # 푸터
    lines.append("※ 본 정보는 참고용이며, 투자 판단의 근거로 사용하지 마세요.")
    lines.append("※ 투자에 대한 모든 책임은 본인에게 있습니다.")

    return "\n".join(lines)


def post_to_cafe(digest_info, access_token):
    # ⭐ 제목: 첫 메시지 첫 줄에서 자동 추출
    subject = extract_subject_from_first_msg(
        digest_info["items"],
        digest_info["date"]
    )
    content = build_content(digest_info)

    print("  📝 제목:", subject)
    print("  📏 본문 길이:", len(content), "자")

    encoded_subject = to_html_entity(subject)
    encoded_content = to_html_entity(content)

    url = "https://openapi.naver.com/v1/cafe/" + CAFE_ID + "/menu/" + MENU_ID + "/articles"
    headers = {
        "Authorization": "Bearer " + access_token,
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
    }

    res = requests.post(
        url,
        headers=headers,
        data={
            "subject": encoded_subject,
            "content": encoded_content,
            "openyn": "true",
        },
        timeout=15
    )

    print("  📨 상태코드:", res.status_code)
    print("  📨 응답:", res.text[:300])

    try:
        result = res.json()
    except Exception:
        print("  ❌ JSON 파싱 실패")
        return None

    status = result.get("message", {}).get("status")
    if status != "200":
        print("  ❌ 실패 - 상태:", status)
        return None

    article_url = result["message"]["result"]["articleUrl"]
    return article_url
