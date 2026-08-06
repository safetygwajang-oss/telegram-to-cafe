"""
공통 유틸리티
- 로깅
- 텍스트 정제
- 해시
- 스팸 필터
"""
import re
import hashlib
from datetime import datetime
from config import KST, FORBIDDEN_WORDS


def log(tag: str, msg: str):
    """일관된 로그 포맷"""
    ts = datetime.now(KST).strftime("%H:%M:%S")
    print(f"[{ts}] {tag} {msg}")


def info(msg: str):  log("[INFO]", msg)
def ok(msg: str):    log("[ OK ]", msg)
def warn(msg: str):  log("[WARN]", msg)
def fail(msg: str):  log("[FAIL]", msg)


def remove_emojis(text: str) -> str:
    """
    4바이트(BMP 밖) 이모지 제거.
    네이버 API가 종종 이모지에서 500 에러를 반환하기 때문.
    """
    if not text:
        return ""
    return "".join(c for c in text if ord(c) <= 0xFFFF)


def mask_forbidden(text: str) -> str:
    """출처 노출 방지 - 금칙어 제거"""
    if not text:
        return text
    for word in FORBIDDEN_WORDS:
        text = text.replace(word, "")
    # 텔레그램 초대 링크 제거
    text = re.sub(r"https?://t\.me/\S+", "", text)
    # 과도한 공백 정리
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def content_hash(text: str) -> str:
    """중복 판별용 해시 (공백 제거 후 앞 200자 기준)"""
    normalized = re.sub(r"\s+", "", text)[:200]
    return hashlib.md5(normalized.encode()).hexdigest()


def truncate(text: str, limit: int, suffix: str = "...") -> str:
    """길이 초과 시 잘라내기"""
    if len(text) <= limit:
        return text
    return text[:limit - len(suffix)] + suffix


# ==========================================================
# 🆕 스팸 필터
# ==========================================================
def is_spam(text: str) -> bool:
    """
    스팸/광고성 메시지 판별
    - 리딩방/무료체험 등 광고 키워드
    - URL 도배
    - 너무 짧은 메시지
    - 특수문자 도배
    
    Returns:
        True  → 스팸 (제외 대상)
        False → 정상 메시지
    """
    if not text:
        return True  # 빈 메시지도 제외

    text_lower = text.lower()

    # 1. 광고성 키워드 (한 개라도 걸리면 스팸)
    spam_keywords = [
        "무료체험", "무료 체험",
        "리딩방", "리딩 방",
        "무료입장", "무료 입장",
        "종목추천 무료", "무료 종목추천",
        "카톡문의", "카톡 문의",
        "텔레문의", "텔레 문의",
        "1:1 상담", "1대1 상담",
        "수익인증", "수익 인증",
        "단톡방 초대", "오픈채팅 초대",
        "vip방", "vip 방",
        "프리미엄방", "프리미엄 방",
    ]
    for kw in spam_keywords:
        if kw in text_lower:
            return True

    # 2. URL 3개 이상 → 링크 도배 스팸
    url_count = len(re.findall(r'https?://\S+', text))
    if url_count >= 3:
        return True

    # 3. 너무 짧은 메시지 (5자 미만)
    stripped = re.sub(r'\s+', '', text)
    if len(stripped) < 5:
        return True

    # 4. 특수문자/이모지 비율이 70% 초과 → 스팸
    if len(stripped) > 0:
        special_count = len(re.findall(r'[^\w가-힣\s]', stripped))
        if special_count / len(stripped) > 0.7:
            return True

    # 5. 같은 문자 10회 이상 반복 (ㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋ, !!!!!!!!!!)
    if re.search(r'(.)\1{9,}', text):
        return True

    return False
