"""챗 라우팅 규칙: 인사·사용법은 no_search, 내용은 single_pass, 목록·건수는 agentic."""

from app.rag.chat_router import is_architecture_question, route_chat_mode


def test_greetings_and_chat_help_do_not_search() -> None:
    assert route_chat_mode("안녕하세요") == "no_search"
    assert route_chat_mode("Hi!") == "no_search"
    assert route_chat_mode("이 챗봇 사용법 알려줘") == "no_search"
    assert route_chat_mode("챗봇이 뭘 할 수 있어?") == "no_search"


def test_greetings_with_typos_and_symbols_do_not_search() -> None:
    # 인사말 뒤 기호·오타 자모가 붙어도 single_pass로 새지 않아야 한다(엉뚱한 출처 부착 방지).
    assert route_chat_mode("안녕₩") == "no_search"
    assert route_chat_mode("안녕하세여ㅛ") == "no_search"
    assert route_chat_mode("하이ㅋㅋ") == "no_search"
    assert route_chat_mode("반가워요^^") == "no_search"
    # 인사 뒤에 실제 업무 질문이 이어지면 인사로 오인하지 않는다.
    assert route_chat_mode("안녕하세요 6월 회의록 알려줘") == "single_pass"
    assert route_chat_mode("안녕 메모 몇 개야") == "agentic"


def test_identity_and_capability_questions_do_not_search() -> None:
    # "챗봇" 단어 없이 2인칭으로 정체성·기능을 물어도 근거-기반 거절로 빠지지 않아야 한다.
    assert route_chat_mode("너의 기능은 뭐니?") == "no_search"
    assert route_chat_mode("넌 뭐야?") == "no_search"
    assert route_chat_mode("너 누구야") == "no_search"
    # 자료의 '기능 명세'를 묻는 업무 질의는 그대로 검색 경로를 탄다.
    assert route_chat_mode("결제 모듈의 기능 명세 알려줘") == "single_pass"


def test_content_and_multihop_go_single_pass() -> None:
    assert route_chat_mode("S등급을 받은 직원의 AI 인프라 업무를 요약해줘") == "single_pass"
    # 날짜를 포함하지만 내용 질의 → single_pass로 오분류되지 않아야 한다.
    assert route_chat_mode("6월 중순까지 완료해야 하는 업무가 뭐야?") == "single_pass"
    assert route_chat_mode("프로젝트 오로라 마일스톤 알려줘") == "single_pass"
    # "저널리스트" 안의 "리스트"를 목록 질의로 오인하지 않는다.
    assert (
        route_chat_mode(
            "RTL Deutschland의 저널리스트들이 활용하는 솔루션은 무엇이며, "
            "EU 데이터 상주 정책의 Existing Projects 제한 사항은 무엇인지 설명해줘."
        )
        == "single_pass"
    )


def test_count_queries_go_agentic() -> None:
    assert route_chat_mode("내 메모 몇 개야?") == "agentic"
    assert route_chat_mode("이번 회의록 몇 건이야") == "agentic"
    assert route_chat_mode("자료 개수 알려줘") == "agentic"


def test_enumeration_queries_go_agentic() -> None:
    assert route_chat_mode("오늘 만든 메모 전체 알려줘") == "agentic"
    assert route_chat_mode("내 자료 목록 보여줘") == "agentic"


def test_recency_with_creation_intent_goes_agentic() -> None:
    assert route_chat_mode("이번 주에 작성한 회의록 보여줘") == "agentic"
    assert route_chat_mode("최근에 올린 자료 알려줘") == "agentic"


def test_architecture_questions_use_structured_answer_contract() -> None:
    assert is_architecture_question("내 프로젝트에 어떤 구조로 적용할까?")
    assert is_architecture_question("안전성 분류 아키텍처를 설계해줘")
    assert not is_architecture_question("마감일이 언제야?")
