import os
import requests
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta

CAFE_ID = "31767633"
MENU_ID = "16"

KST = timezone(timedelta(hours=9))


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
    forbidden = [
        "텔레그램", "telegram", "Telegram", "TELEGRAM",
        "단톡방", "단톡", "톡방",
    ]
    for word in forbidden:
        text = text.replace(word, "")
    text = text.replace("  ", " ").strip()
    while text and text[0] in ">/<|- ":
        text = text[1:].strip()
    while text and text[-1] in ">/<|- ":
        text = text[:-1].strip()
    return text


def build_subject(digest_info):
    date_str = digest_info["date"]
    count = digest_info["count"]
    yymmdd = date_str.replace("-", "")[2:]
    return "[ECONOMY] BRIEFING #" + yymmdd + " (" + str(count) + " items)"


def build_headline_box(digest_info):
    lines = []
    date_str = digest_info["date"]
    count = digest_info["count"]

    lines.append("========================================")
    lines.append("[ " + date_str + " 경제 브리핑 ]")
    lines.append("   - 총 " + str(count) + "건 정리")
    lines.append("   - 어제 08:00 ~ 오늘 08:00 기준")
    lines.append("========================================")
    return lines


def build_content(digest_info):
    lines = []
    items = digest_info["items"]

    lines.extend(build_headline_box(digest_info))
    lines.append("")
    lines.append("")

    for i, item in enumerate(items, 1):
        time_str = item["date_kst"][11:16]
        body = clean_forbidden_words(item["body"])

        lines.append("[ " + str(i) + ". " + time_str + " ]")
        lines.append(body)
        lines.append("")
        lines.append("----------------------------------------")
        lines.append("")

    lines.append("※ 본 정보는 참고용이며, 투자 판단의 근거로 사용하지 마세요.")
    lines.append("※ 투자에 대한 모든 책임은 본인에게 있습니다.")

    return "\n".join(lines)


def post_to_cafe(digest_info, access_token):
    subject = build_subject(digest_info)
    content = build_content(digest_info)

    print("  📝 제목:", subject)
    print("  📏 본문 길이:", len(content), "자")

    encoded_subject = to_html_entity(subject)
    encoded_content = to_html_entity(content)

    url = "https://openapi.naver.com/v1/cafe/" + CAFE_ID + "/menu/" + MENU_ID + "/articles"
    headers = {
        "Authorization": "Bearer " + access_token,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    body_data = urlencode({
        "subject": encoded_subject,
        "content": encoded_content,
        "openyn": "true",
    })

    res = requests.post(url, headers=headers, data=body_data, timeout=30)

    print("  📨 상태코드:", res.status_code)
    print("  📨 응답:", res.text[:500])

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
    print("  ✅ 성공:", article_url)
    return article_url
