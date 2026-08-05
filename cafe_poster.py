# 안전한 본문 크기 (HTML 엔티티 변환 후 URL 인코딩 고려)
# 원문 기준 약 5000자가 안전선
MAX_TOTAL_BODY = 5000
MAX_PER_ITEM = 1500   # 메시지 1건당 최대 길이


def build_content(digest_info):
    """본문 - 헤드라인 박스 + 시간순 메시지 목록 (크기 제한 적용)"""
    lines = []
    items = digest_info["items"]

    # 헤드라인 박스
    lines.extend(build_headline_box(digest_info))
    lines.append("")
    lines.append("")

    # 시간순 메시지 목록
    current_size = len("\n".join(lines))
    truncated_count = 0
    included_count = 0

    for i, item in enumerate(items, 1):
        time_str = item["date_kst"][11:16]
        body = clean_forbidden_words(item["body"])

        # 개별 메시지 길이 제한
        if len(body) > MAX_PER_ITEM:
            body = body[:MAX_PER_ITEM] + "\n... (이하 생략)"

        # 이 메시지 블록 예상 크기
        block = "[ " + str(i) + ". " + time_str + " ]\n" + body + "\n\n----------------------------------------\n\n"

        # 전체 본문 크기 초과 예상되면 중단
        if current_size + len(block) > MAX_TOTAL_BODY:
            truncated_count = len(items) - included_count
            break

        lines.append("[ " + str(i) + ". " + time_str + " ]")
        lines.append(body)
        lines.append("")
        lines.append("----------------------------------------")
        lines.append("")

        current_size += len(block)
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
