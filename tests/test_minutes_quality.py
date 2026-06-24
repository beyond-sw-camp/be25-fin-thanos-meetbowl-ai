import pytest

from app.core.errors import ResponseValidationError
from app.pipelines.minutes_evidence import evidence_to_minutes_draft, finalize_minutes_evidence
from app.pipelines.minutes_quality import finalize_minutes_draft
from app.pipelines.transcript import (
    mark_suspicious_segments,
    normalize_raw_transcript,
    transcript_to_segments,
)
from app.prompts.minutes import build_minutes_evidence_prompt
from app.schemas.minutes import (
    AgendaItem,
    EvidenceActionItem,
    EvidenceAgendaItem,
    EvidenceDecision,
    MinutesDraft,
    MinutesEvidence,
    Participant,
)
from app.schemas.workflow import MinutesGenerationContext


def test_minutes_prompt_requires_korean_summary_and_noise_filtering() -> None:
    prompt = build_minutes_evidence_prompt(
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
        segments=transcript_to_segments("첫 번째 논의\n두 번째 논의"),
    )

    assert "근거(evidence)만 추출" in prompt
    assert "sourceSequences" in prompt
    assert "1. [UNKNOWN] 첫 번째 논의" in prompt
    assert "summary는 2~4문장" in prompt
    assert "[SUSPICIOUS]" in prompt


def test_normalize_raw_transcript_drops_url_and_link_copy_noise() -> None:
    normalized = normalize_raw_transcript(
        "첫 번째 논의\nhttps://meetbowl.example/invite\n공유 링크 복사\n두 번째 논의"
    )

    assert normalized == "첫 번째 논의\n두 번째 논의"


def test_transcript_to_segments_assigns_sequence_numbers() -> None:
    segments = transcript_to_segments("첫 번째 논의\n두 번째 논의")

    assert [segment.sequence for segment in segments] == [1, 2]
    assert [segment.source_text for segment in segments] == ["첫 번째 논의", "두 번째 논의"]


def test_mark_suspicious_segments_flags_isolated_non_mainstream_script() -> None:
    segments = transcript_to_segments("배포 일정 논의\n谢谢\nQA 확인은 목요일까지 진행")

    marked = mark_suspicious_segments(segments)

    assert [segment.suspicious for segment in marked] == [False, True, False]


def test_mark_suspicious_segments_flags_isolated_japanese_outlier() -> None:
    segments = transcript_to_segments("배포 일정 논의\nありがとう\nQA 확인은 목요일까지 진행")

    marked = mark_suspicious_segments(segments)

    assert [segment.suspicious for segment in marked] == [False, True, False]


def test_mark_suspicious_segments_keeps_consecutive_same_script_block() -> None:
    segments = transcript_to_segments(
        "배포 일정 논의\nありがとう\nよろしくお願いします\nQA 확인은 목요일까지 진행"
    )

    marked = mark_suspicious_segments(segments)

    assert [segment.suspicious for segment in marked] == [False, False, False, False]


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


def test_finalize_minutes_draft_keeps_agenda_and_dedupes_decisions() -> None:
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

    assert len(refined.agenda_items) == 2
    assert refined.decisions == ["금요일 배포로 진행한다."]


def test_evidence_to_minutes_draft_uses_discussion_points_and_dedupes_actions() -> None:
    evidence = MinutesEvidence(
        summary="배포 일정과 후속 조치를 정리했다.",
        agenda_items=[
            EvidenceAgendaItem(
                title="배포 일정 조율",
                discussion_points=["금요일 배포를 제안했다.", "QA 완료 후 배포하기로 정리했다."],
                source_sequences=[1, 2],
                decision="금요일 배포로 진행한다.",
            )
        ],
        decisions=[
            EvidenceDecision(content="금요일 배포로 진행한다.", source_sequences=[2]),
            EvidenceDecision(content="금요일 배포로 진행한다.", source_sequences=[2]),
        ],
        action_items=[
            EvidenceActionItem(
                content="배포 공지를 작성한다.",
                assignee_name="김영희",
                due_date=None,
                source_sequences=[3],
            ),
            EvidenceActionItem(
                content="배포 공지를 작성한다.",
                assignee_name="김영희",
                due_date=None,
                source_sequences=[3],
            ),
        ],
    )

    draft = evidence_to_minutes_draft(evidence)

    assert draft.summary == evidence.summary
    assert draft.agenda_items[0].discussion == "금요일 배포를 제안했다. QA 완료 후 배포하기로 정리했다."
    assert draft.decisions == ["금요일 배포로 진행한다."]
    assert len(draft.action_items) == 1


def test_finalize_minutes_evidence_drops_items_without_valid_source_sequences() -> None:
    segments = transcript_to_segments(
        "금요일 배포를 제안했다.\nQA 완료 후 배포하기로 정리했다.\n배포 공지는 오늘 작성한다."
    )
    evidence = MinutesEvidence(
        summary="배포 일정과 공지 준비를 정리했다.",
        agenda_items=[
            EvidenceAgendaItem(
                title="배포 일정 조율",
                discussion_points=["금요일 배포를 제안했다.", "QA 완료 후 배포하기로 정리했다."],
                source_sequences=[1, 2],
                decision="금요일 배포로 진행한다.",
            ),
            EvidenceAgendaItem(
                title="근거 없는 안건",
                discussion_points=["정리되지 않은 내용"],
                source_sequences=[99],
                decision=None,
            ),
            EvidenceAgendaItem(
                title="단일 발화 안건",
                discussion_points=["금요일 배포를 제안했다."],
                source_sequences=[1],
                decision=None,
            ),
        ],
        decisions=[
            EvidenceDecision(content="금요일 배포로 진행한다.", source_sequences=[2]),
            EvidenceDecision(content="근거 없는 결정", source_sequences=[42]),
        ],
        action_items=[
            EvidenceActionItem(
                content="배포 공지를 작성한다.",
                assignee_name="김영희",
                due_date=None,
                source_sequences=[3, 3],
            ),
            EvidenceActionItem(
                content="근거 없는 액션",
                assignee_name=None,
                due_date=None,
                source_sequences=[],
            ),
        ],
    )

    refined = finalize_minutes_evidence(evidence=evidence, segments=segments)

    assert len(refined.agenda_items) == 1
    assert refined.agenda_items[0].source_sequences == [1, 2]
    assert [decision.content for decision in refined.decisions] == ["금요일 배포로 진행한다."]
    assert refined.action_items[0].source_sequences == [3]


def test_finalize_minutes_evidence_drops_suspicious_only_decision_and_action() -> None:
    segments = mark_suspicious_segments(
        transcript_to_segments("배포 일정 논의\n谢谢\nQA 확인은 목요일까지 진행")
    )
    evidence = MinutesEvidence(
        summary="배포 일정과 QA 일정을 정리했다.",
        agenda_items=[
            EvidenceAgendaItem(
                title="배포 일정 조율",
                discussion_points=["배포 일정을 논의했다.", "QA 확인 일정을 정리했다."],
                source_sequences=[1, 3],
                decision=None,
            )
        ],
        decisions=[
            EvidenceDecision(content="감사 인사를 전달했다.", source_sequences=[2]),
            EvidenceDecision(content="QA를 목요일까지 진행한다.", source_sequences=[3]),
        ],
        action_items=[
            EvidenceActionItem(
                content="감사 인사를 다시 확인한다.",
                assignee_name=None,
                due_date=None,
                source_sequences=[2],
            ),
            EvidenceActionItem(
                content="QA 결과를 공유한다.",
                assignee_name=None,
                due_date=None,
                source_sequences=[3],
            ),
        ],
    )

    refined = finalize_minutes_evidence(evidence=evidence, segments=segments)

    assert [decision.content for decision in refined.decisions] == ["QA를 목요일까지 진행한다."]
    assert [item.content for item in refined.action_items] == ["QA 결과를 공유한다."]
