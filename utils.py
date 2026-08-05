"""
공통 유틸리티
- 로깅
- 텍스트 정제
- 해시
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
