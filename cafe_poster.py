import os
import requests

CAFE_ID = "31767633"
MENU_ID = "16"

# ==========================================================
# 🎯 본문 크기 제한
# ==========================================================
MAX_TOTAL_BODY = 5000
MAX_PER_ITEM = 1500
MAX_SUBJECT_LEN = 90


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


def remove_emojis(text):
    """네이버 API 500 에러를 유발하는 4바이트 이모지만 깔끔하게 제거"""
    if not text:
        return ""
    return "".join(c for c in text if ord(c) <= 0xFFFF)


def clean_forbidden_words(text):
    """출처 노출 방지"""
    if not text:
        return text
    forbidden = ["iSAFETY", "isafety", "ISAFETY", "iSafety", "아이세이프티", "아이세이프"]
    for word in forbidden:
        text = text.replace(word, "")
    return text.strip()


def extract_subject_from_first_msg(items, date_str):
    """첫 메시지의 첫 줄을 카페 게시글 제목으로 사용"""
    if not items:
        return "[" + date_str + "] 시황 브리핑"

    first_body = items[0].get("body", "").strip()
    first_line = first_body.split("\n")[0].strip()

    if len(first_line) < 5:
        return "[" + date_str + "] 시황 브리핑"

    if len(first_line) > MAX_SUBJECT_LEN:
        first_line = first_line[:MAX_SUBJECT_LEN - 3] + "..."

    return first_line


def build_headline_box(digest_info):
    """본문 최상단 헤드라인 박스"""
    lines = []
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(digest_info["chat_name"])
    lines.append("📅 " + digest_info["date"] + "  |  📊 총 " + str(digest_info["count"]) + "건")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    return lines


def build_content(digest_info):
    """본문 - 헤드라인 박스 + 시간순 메시지 목록"""
    lines = []
    items = digest_info["items"]

    lines.extend(build_headline_box(digest_info))
    lines.append("")
    lines.append("")

    current_size = len("\n".join(lines))
    truncated_count = 0
    included_count = 0

    for i, item in enumerate(items, 1):
        time_str = item.get("date_kst", "")[11:16] if item.get("date_kst") else ""
        body = clean_forbidden_words(item.get("body", ""))

        if len(body) > MAX_PER_ITEM:
            body = body[:MAX_PER_ITEM] + "\n... (이하 생략)"

        header = "[ " + str(i) + ". " + time_str + " ]"
        block_text = header + "\n" + body + "\n\n----------------------------------------\n\n"

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

    if truncated_count > 0:
        lines.append("")
        lines.append(">> 본문 길이 제한으로 " + str(truncated_count) + "건은 생략되었습니다.")
        lines.append("")

    lines.append("※ 본 정보는 참고용이며, 투자 판단의 근거로 사용하지 마세요.")
    lines.append("※ 투자에 대한 모든 책임은 본인에게 있습니다.")

    return "\n".join(lines)


def post_to_cafe(digest_info, access_token):
    # 1. 제목과 본문 생성
    raw_subject = extract_subject_from_first_msg(digest_info["items"], digest_info["date"])
    raw_content = build_content(digest_info)

    # 2. 이모지 제거 (네이버 500 에러 방지)
    subject = remove_emojis(raw_subject)
    content = remove_emojis(raw_content)

    print("  📝 제목:", subject)
    print("  📏 본문 길이:", len(content), "자")

    url = "https://openapi.naver.com/v1/cafe/" + CAFE_ID + "/menu/" + MENU_ID + "/articles"

    # 3. 깔끔한 기본 헤더 사용 (ms949 삭제)
    headers = {
        "Authorization": "Bearer " + access_token,
    }

    # 4. requests 라이브러리가 알아서 안전하게 변환하도록 딕셔너리 그대로 전달
    data = {
        "subject": subject,
        "content": content,
        "openyn": "true",
    }

    res = requests.post(
        url,
        headers=headers,
        data=data,
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
