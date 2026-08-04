import re
import hashlib

# 명확한 스팸/광고만 제외
SPAM_PATTERNS = [
    r"리딩방", r"무료\s*체험", r"수익률\s*보장",
    r"http[s]?://t\.me/joinchat", r"오픈채팅.*초대",
    r"입장코드", r"VIP\s*방",
]

# 🎯 출처 감추기 - 채널명/운영자명 등 (필요시 추가)
FORBIDDEN_WORDS = [
    # 예: "OOO경제방", "@admin_name",
]

MIN_LEN = 15  # 이보다 짧으면 잡담으로 판단


def is_valid(text):
    """유효한 경제정보인지 판별"""
    if len(text) < MIN_LEN:
        return False
    for pat in SPAM_PATTERNS:
        if re.search(pat, text):
            return False
    return True


def clean_text(text):
    """출처 마스킹 + 정리"""
    if not text:
        return text
    # 금칙어 제거
    for w in FORBIDDEN_WORDS:
        text = text.replace(w, "")
    # 텔레그램 초대링크 제거
    text = re.sub(r"https?://t\.me/\S+", "", text)
    # 과도한 개행 정리
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def content_hash(text):
    """중복 판별용 해시 (공백 제거 후 앞 200자)"""
    normalized = re.sub(r"\s+", "", text)[:200]
    return hashlib.md5(normalized.encode()).hexdigest()


def parse(msg):
    """
    메시지 정제 + 유효성 검사
    반환: 파싱된 dict 또는 None
    """
    text = clean_text(msg["text"])
    if not is_valid(text):
        return None
    return {
        "msg_id": msg["msg_id"],
        "date_kst": msg["date_kst"],
        "body": text,
        "hash": content_hash(text),
    }
