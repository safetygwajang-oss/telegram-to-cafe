import os
import requests
from datetime import datetime, timezone, timedelta

CAFE_ID = "31767633"
MENU_ID = "16"   

KST = timezone(timedelta(hours=9))


def get_access_token():
    """[기존 코드 그대로]"""
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
    return data["access_token"]


def to_html_entity(text):
    """[기존 코드 그대로] 비-ASCII 문자를 HTML 엔티티로 변환"""
    result = ""
    for ch in text:
        if ord(ch) < 128:
            result += ch
        else:
            result += "&#" + str(ord(ch)) + ";"
    return result


def clean_forbidden_words(text):
    """[기존 코드 응용] 출처 노출 방지 - 텔레그램 관련 단어 제거"""
    if not text:
        return text
    # 🎯 마스킹할 단어들 (필요시 추가)
    forbidden = [
        "텔레그램", "telegram", "Telegram", "TELEGRAM",
        "단톡방", "단톡", "톡방",
        # 특정 채널명/운영자명 추가
    ]
    for word in forbidden:
        text = text.replace(word, "")
    text = text.replace("  ", " ").strip()
    while text and text[0] in ">/<|- ":
        text = text[1:].strip()
    while text and text[-1] in ">/<|- ":
        text = text[:-1].strip()
    return text


# ==========================================================
# 🎯 텔레그램 버전: 하루치 메시지를 하나의 브리핑으로 묶기
# ==========================================================

def build_subject(digest_info):
    """
    제목: ASCII 문자로만 구성 (PC 리스트에서 안 깨지게)
    형식: [ECONOMY] BRIEFING #YYMMDD (N items)
    """
    date_str = digest_info["date"]           # "2026-01-15"
    count = digest_info["count"]             # 42

    # YY-MM-DD → YYMMDD (숫자만)
    yymmdd = date_str.replace("-", "")[2:]   # "260115"

    subject = "[ECONOMY] BRIEFING #" + yymmdd + " (" + str(count) + " items)"
    return subject


def build_headline_box(digest_info):
    """본문 최상단 헤드라인 박스 - '진짜 제목' 역할"""
    lines = []
    date_str = digest_info["date"]
    count = digest_info["count"]

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📊 " + date_str + " 경제 브리핑")
    lines.append("     📌 총 " + str(count) + "건 정리")
    lines.append("     🕐 어제 08:00 ~ 오늘 08:00 기준")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")

    return lines


def build_content(digest_info):
    """본문 - 헤드라인 박스 + 시간순 메시지 목록"""
    lines = []
    items = digest_info["items"]

    # ========== 🎯 헤드라인 박스 (진짜 제목) ==========
    lines.extend(build_headline_box(digest_info))
    lines.append("")
    lines.append("")

    # ========== 시간순 메시지 목록 ==========
    for i, item in enumerate(items, 1):
        time_str = item["date_kst"][11:16]   # HH:MM 추출
        body = clean_forbidden_words(item["body"])

        lines.append("【 " + str(i) + ". " + time_str + " 】")
        lines.append(body)
        lines.append("")
        lines.append("─────────────────────────")
        lines.append("")

    # ========== 푸터 ==========
    lines.append("※ 본 정보는 참고용이며, 투자 판단의 근거로 사용하지 마세요.")
    lines.append("※ 투자에 대한 모든 책임은 본인에게 있습니다.")

    return "\n".join(lines)


def post_to_cafe(digest_info, access_token):
    """[기존 로직 그대로] 카페 게시"""
    subject = build_subject(digest_info)
    content = build_content(digest_info)

    print("  📝 제목:", subject)

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
        print("  ❌ 실패")
        return None

    article_url = result["message"]["result"]["articleUrl"]
    print("  ✅ 성공:", article_url)
    return article_url
