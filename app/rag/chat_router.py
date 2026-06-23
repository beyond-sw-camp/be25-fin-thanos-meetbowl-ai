import re

# 명백히 자료 검색이 필요 없는 짧은 인사와 챗봇 사용법·기능 질문.
# 업무 자료 질문을 잘못 빠른 경로로 보내지 않도록 보수적인 표현만 사용한다.
_GREETING_PATTERN = re.compile(
    r"^\s*(안녕(?:하세요)?|반가워(?:요)?|하이|헬로|hi|hello|"
    r"고마워(?:요)?|감사(?:합니다|해요)?)[!?.\s]*$",
    re.IGNORECASE,
)
_CHAT_HELP_PATTERN = re.compile(
    r"챗봇.*(?:사용법|기능|도움말|(?:뭐|무엇을|뭘)\s*할\s*수\s*있)"
    r"|(?:사용법|도움말).*(?:알려|설명|보여)"
)
# 건수 질의(count_documents 툴 필요): "메모 몇 개야?", "회의록 몇 건?"
_COUNT_PATTERN = re.compile(r"몇\s*(개|건|명|가지)|개수|건수")
# 열거 질의(list_recent_documents 툴 필요): "전체/모두/목록/나열"
_LIST_PATTERN = re.compile(r"전체|전부|모두|모든|목록|리스트|나열")
# 상대적 시점 표현. 단독으로는 분기하지 않고(예: "6월 중순 업무"는 내용 질의) 생성/열거 의도와 함께일 때만.
_RECENCY_PATTERN = re.compile(r"오늘|어제|이번\s*주|지난\s*주|이번\s*달|지난\s*달|최근")
_CREATE_OR_SHOW_PATTERN = re.compile(r"만든|작성|생성|올린|쓴|보여|알려|적은")
_ARCHITECTURE_PATTERN = re.compile(r"구조|아키텍처|설계|프로젝트.*적용|통합.*방법")


def route_chat_mode(question: str) -> str:
    """질문을 보고 no_search, single_pass, agentic 처리 경로를 고른다.

    날짜 표현만으로는 agentic으로 보내지 않는다('6월 중순까지 완료할 업무'처럼 날짜를 포함한
    내용 질의를 느린 경로로 오분류하지 않기 위함). 상대 시점은 생성/열거 의도와 함께일 때만 라우팅한다.
    """
    if _GREETING_PATTERN.search(question) or _CHAT_HELP_PATTERN.search(question):
        return "no_search"
    if _COUNT_PATTERN.search(question) or _LIST_PATTERN.search(question):
        return "agentic"
    if _RECENCY_PATTERN.search(question) and _CREATE_OR_SHOW_PATTERN.search(question):
        return "agentic"
    return "single_pass"


def is_architecture_question(question: str) -> bool:
    """필수 설계 섹션을 구조화해야 하는 질문인지 판정한다."""
    return _ARCHITECTURE_PATTERN.search(question) is not None
