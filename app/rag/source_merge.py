from app.schemas.chat import ChatSource

_MAX_SNIPPET_CHARS = 2_000
_MAX_SECTIONS = 6
_SECTION_SEPARATOR = "\n\n--- related chunk ---\n\n"


def merge_chat_sources(primary: ChatSource, additional: ChatSource) -> ChatSource:
    """같은 문서에서 검색된 여러 청크를 하나의 인용 소스로 합친다.

    문서 인용은 resource_id 하나로 유지하면서 서로 다른 근거 조각을 모두
    생성 모델에 제공한다. ChatSource 스키마 상한에 맞춰 최대 2,000자로 제한한다.
    """
    if primary.resource_id != additional.resource_id:
        raise ValueError("cannot merge different resources")
    sections: list[str] = []
    for snippet in (primary.snippet, additional.snippet):
        for section in snippet.split(_SECTION_SEPARATOR):
            normalized = section.strip()
            if normalized and normalized not in sections:
                sections.append(normalized)
    sections = sections[:_MAX_SECTIONS]
    # 첫 청크가 2,000자를 독점해 뒤의 근거가 잘리지 않도록 청크별 공간을 균등 배분한다.
    separator_chars = len(_SECTION_SEPARATOR) * max(0, len(sections) - 1)
    section_limit = max(
        1, (_MAX_SNIPPET_CHARS - separator_chars) // max(1, len(sections))
    )
    snippet = _SECTION_SEPARATOR.join(
        section[:section_limit] for section in sections
    )
    return primary.model_copy(
        update={
            "snippet": snippet[:_MAX_SNIPPET_CHARS],
            "score": max(primary.score, additional.score),
        }
    )
