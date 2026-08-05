"""
텔레그램 원본 메시지 → 정제된 dict
"""
import re
from config import MIN_MSG_LEN, SPAM_PATTERNS
from utils import mask_forbidden, content_hash


def _is_valid(text: str) -> bool:
    """스팸/광고/잡담 필터링"""
    if len(text) < MIN_MSG_LEN:
        return False
    for pat in SPAM_PATTERNS:
        if re.search(pat, text):
            return False
    return True


def parse(msg: dict) -> dict | None:
    """
    원본 메시지 → 파싱 결과
    반환: dict 또는 None (유효하지 않은 경우)
    """
    text = mask_forbidden(msg.get("text", ""))
    if not _is_valid(text):
        return None

    return {
        "msg_id":    msg["msg_id"],
        "chat_name": msg.get("chat_name", "Unknown"),
        "date_kst":  msg["date_kst"],
        "body":      text,
        "hash":      content_hash(text),
    }
