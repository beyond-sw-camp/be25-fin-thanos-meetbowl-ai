import argparse
import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
from redis.asyncio import Redis


TRANSCRIPT_SEGMENTS = (
    "지난 회의에서 결제 자동 승인 정책을 논의했었죠",
    "이번에도 백만원 이하 거래 승인 기준을 확인해 봅시다",
    "백만원 이하 결제를 자동 승인하는 방안이 맞는지 검토하겠습니다",
    "기존 결정사항과 현재 정책이 같은지 확인해 주세요",
)


async def main() -> int:
    args = parse_args()
    organization_id = uuid4()
    current_meeting_id = uuid4()
    historical_meeting_id = uuid4()
    session_id = uuid4()
    document_id = uuid4()
    participant_user_ids = [uuid4(), uuid4()]

    fixture = {
        "organizationId": str(organization_id),
        "currentMeetingId": str(current_meeting_id),
        "historicalMeetingId": str(historical_meeting_id),
        "sessionId": str(session_id),
        "documentId": str(document_id),
        "participantUserIds": [str(value) for value in participant_user_ids],
    }
    print("[fixture]")
    print(json.dumps(fixture, ensure_ascii=False, indent=2))

    await index_historical_minutes(
        ai_url=args.ai_url,
        internal_token=args.internal_token,
        organization_id=organization_id,
        meeting_id=historical_meeting_id,
        document_id=document_id,
        participant_user_ids=participant_user_ids,
    )
    print("\n[index] test minutes indexed")

    redis = Redis.from_url(args.redis_url, decode_responses=True)
    diagnostics = None
    try:
        await redis.ping()
        result = await publish_segments_and_wait(
            redis=redis,
            organization_id=organization_id,
            meeting_id=current_meeting_id,
            session_id=session_id,
            participant_user_ids=participant_user_ids,
            timeout_seconds=args.timeout,
        )
        if result is None:
            diagnostics = await inspect_feedback_streams(
                redis=redis,
                meeting_id=current_meeting_id,
            )
    finally:
        await redis.aclose()

    if result is None:
        print(
            "\n[result] no feedback event received. "
            "Check REDIS_FEEDBACK_ENABLED, embedding profiles, collection, and score threshold."
        )
        print("\n[redis diagnostics]")
        print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
        return 2

    print("\n[result]")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


async def index_historical_minutes(
    *,
    ai_url: str,
    internal_token: str,
    organization_id: UUID,
    meeting_id: UUID,
    document_id: UUID,
    participant_user_ids: list[UUID],
) -> None:
    payload = {
        "documentId": str(document_id),
        "documentType": "MEETING_MINUTES",
        "organizationId": str(organization_id),
        "ownerUserId": str(participant_user_ids[0]),
        "accessScope": {
            "userIds": [str(value) for value in participant_user_ids],
            "departmentIds": [],
            "sharedWorkspaceIds": [],
        },
        "title": "결제 자동 승인 정책 회의",
        "content": (
            "결제 자동 승인 정책과 백만원 이하 거래 기준을 검토했습니다. "
            "백만원 이하 결제는 자동 승인하기로 최종 확정했습니다."
        ),
        "metadata": {
            "meetingId": str(meeting_id),
            "approvedAt": "2026-06-18T01:00:00Z",
        },
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{ai_url.rstrip('/')}/api/v1/indexes/documents",
            headers={"X-Internal-Token": internal_token},
            json=payload,
        )
        if response.is_error:
            raise RuntimeError(
                "minutes indexing failed: "
                f"status={response.status_code}, body={response.text}"
            )


async def publish_segments_and_wait(
    *,
    redis: Redis,
    organization_id: UUID,
    meeting_id: UUID,
    session_id: UUID,
    participant_user_ids: list[UUID],
    timeout_seconds: int,
) -> dict | None:
    source_stream = f"meeting:{meeting_id}:feedback-source"
    result_stream = f"meeting:{meeting_id}:feedback-result"
    # meetingId가 실행마다 새 UUID이므로 이 stream에는 이번 실행 결과만 존재한다.
    # "$"는 XREAD 호출 이전에 AI가 빠르게 쓴 결과를 건너뛰므로 0-0부터 읽는다.
    result_cursor = "0-0"
    correlation_id = uuid4()

    for sequence, text in enumerate(TRANSCRIPT_SEGMENTS):
        envelope = {
            "eventId": str(uuid4()),
            "eventType": "meeting.feedback.segment.created",
            "occurredAt": utc_now(),
            "producer": "stt-server",
            "version": 1,
            "correlationId": str(correlation_id),
            "payload": {
                "meetingId": str(meeting_id),
                "sessionId": str(session_id),
                "organizationId": str(organization_id),
                "participantUserIds": [
                    str(value) for value in participant_user_ids
                ],
                "segmentId": str(uuid4()),
                "sequence": sequence,
                "language": "ko",
                "text": text,
                "isFinal": True,
                "startedAtMs": sequence * 6_000,
                "endedAtMs": sequence * 6_000 + 5_000,
            },
        }
        await redis.xadd(source_stream, {"event": json.dumps(envelope)})
        print(f"[source] sequence={sequence} published")

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        remaining_ms = max(
            1,
            int((deadline - asyncio.get_running_loop().time()) * 1_000),
        )
        responses = await redis.xread(
            {result_stream: result_cursor},
            count=10,
            block=min(1_000, remaining_ms),
        )
        for _, messages in responses:
            for message_id, fields in messages:
                result_cursor = message_id
                raw_event = fields.get("event")
                if not raw_event:
                    continue
                event = json.loads(raw_event)
                if (
                    event.get("eventType") == "meeting.feedback.generated"
                    and event.get("payload", {}).get("sessionId") == str(session_id)
                ):
                    return event
    return None


async def inspect_feedback_streams(
    *, redis: Redis, meeting_id: UUID
) -> dict[str, object]:
    source_stream = f"meeting:{meeting_id}:feedback-source"
    result_stream = f"meeting:{meeting_id}:feedback-result"
    try:
        groups = await redis.xinfo_groups(source_stream)
    except Exception as exc:
        groups = [{"error": str(exc)}]
    result_entries = await redis.xrevrange(result_stream, count=1)
    return {
        "sourceStream": source_stream,
        "sourceLength": await redis.xlen(source_stream),
        "sourceConsumerGroups": groups,
        "resultStream": result_stream,
        "resultLength": await redis.xlen(result_stream),
        "latestResult": result_entries[0] if result_entries else None,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Index fixture minutes, publish feedback segments, and print the result."
    )
    parser.add_argument("--ai-url", default="http://127.0.0.1:8000")
    parser.add_argument("--redis-url", default="redis://localhost:6381")
    parser.add_argument(
        "--internal-token",
        default="meetbowl-local-internal-token-32bytes",
    )
    parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
