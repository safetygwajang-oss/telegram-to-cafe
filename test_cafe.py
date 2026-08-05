import os
import requests

CAFE_ID = "31767633"
MENU_ID = "16"

def to_html_entity(text: str) -> str:
    return "".join(f"&#{ord(c)};" if ord(c) > 127 else c for c in text)

def post_cafe_article(subject: str, content: str):
    # 1. access_token 발급
    r = requests.get(
        "https://nid.naver.com/oauth2.0/token",
        params={
            "grant_type": "refresh_token",
            "client_id": os.environ["NAVER_CLIENT_ID"],
            "client_secret": os.environ["NAVER_CLIENT_SECRET"],
            "refresh_token": os.environ["NAVER_REFRESH_TOKEN"],
        }
    )
    token = r.json()["access_token"]

    # 2. 카페 글쓰기 (한글 엔티티 변환)
    url = f"https://openapi.naver.com/v1/cafe/{CAFE_ID}/menu/{MENU_ID}/articles"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
    }
    data = {
        "subject": to_html_entity(subject),
        "content": to_html_entity(content),
        "openyn": "false",
    }
    r = requests.post(url, headers=headers, data=data)
    return r.status_code, r.text

# 테스트
status, resp = post_cafe_article(
    "API 연동 테스트 (한글)",
    "안녕하세요! 한글이 잘 나오나 확인합니다."
)
print(status, resp)
