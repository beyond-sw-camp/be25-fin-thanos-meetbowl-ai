import pytest

from app.core.errors import ResponseValidationError
from app.pipelines.minutes_quality import finalize_minutes_draft
from app.pipelines.transcript import normalize_raw_transcript
from app.prompts.minutes import build_minutes_prompt
from app.schemas.minutes import AgendaItem, MinutesDraft, Participant
from app.schemas.workflow import MinutesGenerationContext


def test_minutes_prompt_requires_korean_summary_and_noise_filtering() -> None:
    prompt = build_minutes_prompt(
        prompt_version="minutes-v1",
        context=MinutesGenerationContext(
            meeting_id="00000000-0000-0000-0000-000000000001",
            organization_id="00000000-0000-0000-0000-000000000002",
            host_user_id="00000000-0000-0000-0000-000000000003",
            reviewer_user_id="00000000-0000-0000-0000-000000000004",
            title="주간 회의",
            started_at="2026-06-24T00:00:00Z",
            ended_at="2026-06-24T01:00:00Z",
            participants=[Participant(user_id="00000000-0000-0000-0000-000000000005", name="홍길동")],
            raw_transcript="논의 원문",
        ),
    )

    assert "반드시 자연스러운 한국어" in prompt
    assert "직접 인용" in prompt
    assert "운영성 잡음은 안건이나 결정사항으로 승격하지 않는다" in prompt


def test_normalize_raw_transcript_drops_url_and_link_copy_noise() -> None:
    normalized = normalize_raw_transcript(
        "첫 번째 논의\nhttps://meetbowl.example/invite\n공유 링크 복사\n두 번째 논의"
    )

    assert normalized == "첫 번째 논의\n두 번째 논의"


def test_finalize_minutes_draft_rejects_english_summary_for_korean_transcript() -> None:
    transcript = "\n".join(
        [
            "자막 발행 성공했고",
            "음성이 음성은 또 왜 안 들어가",
            "링크를 올릴게요.",
            "공유 링크 복사",
            "원인을 모르겠네.",
        ]
    )
    draft = MinutesDraft(
        summary=(
            "The meeting focused on troubleshooting technical issues, including "
            "subtitle publishing and audio input."
        ),
        agenda_items=[
            AgendaItem(
                title="Audio Input Problem",
                discussion='Discussion involved "공유 링크 복사" and "원인을 모르겠네."',
                decision=None,
            )
        ],
        decisions=[],
        action_items=[],
    )

    with pytest.raises(
        ResponseValidationError,
        match="한국어 회의 원문에 대한 요약이 한국어로 생성되지 않았습니다.",
    ):
        finalize_minutes_draft(raw_transcript=transcript, draft=draft)


def test_finalize_minutes_draft_filters_quote_based_noise_agenda() -> None:
    transcript = "배포 일정과 역할 분담을 정리했다.\n공유 링크 복사\n링크를 올릴게요."
    draft = MinutesDraft(
        summary="배포 일정과 역할 분담을 정리하고 필요한 후속 조치를 확인했다.",
        agenda_items=[
            AgendaItem(
                title="Link Sharing and Troubleshooting",
                discussion='"공유 링크 복사", "링크를 올릴게요."',
                decision=None,
            ),
            AgendaItem(
                title="배포 일정 조율",
                discussion="배포 일정을 금요일로 맞추고 QA 확인 순서를 정리했다.",
                decision="금요일 배포로 진행한다.",
            ),
        ],
        decisions=["금요일 배포로 진행한다.", "금요일 배포로 진행한다."],
        action_items=[],
    )

    refined = finalize_minutes_draft(raw_transcript=transcript, draft=draft)

    assert len(refined.agenda_items) == 1
    assert refined.agenda_items[0].title == "배포 일정 조율"
    assert refined.decisions == ["금요일 배포로 진행한다."]
