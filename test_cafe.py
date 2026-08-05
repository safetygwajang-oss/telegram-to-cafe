import os
import requests

CAFE_ID = "31767633"
MENU_ID = "16"

# 1. 토큰 발급
res = requests.get(
    "https://nid.naver.com/oauth2.0/token",
    params={
        "grant_type": "refresh_token",
        "client_id": os.environ["NAVER_CLIENT_ID"],
        "client_secret": os.environ["NAVER_CLIENT_SECRET"],
        "refresh_token": os.environ["NAVER_REFRESH_TOKEN"],
    },
    timeout=10
)
token = res.json()["access_token"]
print("✅ 토큰 발급 OK")

# 2. 카페 글쓰기 (제목/본문 모두 HTML 엔티티로)
url = "https://openapi.naver.com/v1/cafe/" + CAFE_ID + "/menu/" + MENU_ID + "/articles"

headers = {
    "Authorization": "Bearer " + token,
    "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
}

# "테스트 제목" / "안녕하세요 테스트입니다"  → HTML 엔티티
data = {
    "subject": "&#53580;&#49828;&#53944; &#51228;&#47785;",
    "content": "&#50504;&#45397;&#54616;&#49464;&#50836; &#53580;&#49828;&#53944;&#51077;&#45768;&#45796;",
    "openyn": "false",
}

res = requests.post(url, headers=headers, data=data, timeout=15)

print("상태코드:", res.status_code)
print("응답:", res.text)
