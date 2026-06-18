"""챗봇 정확도 회귀 확인용 eval 러너.

전용 eval 사용자로 픽스처 문서를 색인하고, eval/cases.json의 질문을 실제 챗 워크플로에
태운 뒤 기대값과 대조한다. 마지막에 eval 사용자 소유 색인을 모두 정리한다.

실행: GEMINI_API_KEY가 설정된 상태에서
    uv run python eval/run_eval.py

기대값(expect) 종류:
- contains: 답변에 모든 문자열이 포함돼야 함
- cites: 출처 title 중 해당 문자열을 포함하는 것이 있어야 함
- min_sources: 출처가 N개 이상이어야 함
- refuses: 출처가 없고 답변이 '근거 없음'류여야 함(무근거 차단 검증)
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx

# 스크립트로 직접 실행해도 app 패키지를 import할 수 있도록 프로젝트 루트를 경로에 추가한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.container import build_container
from app.core.config import get_settings
from app.schemas.chat import ChatCommand
from app.schemas.indexing import AccessScope, DocumentMetadata, IndexDocumentCommand

# 실제 사용자/데이터와 섞이지 않도록 eval 전용 소유자 UUID를 고정 사용한다.
_EVAL_OWNER = UUID("eeee0000-0000-4000-8000-000000000001")
_REFUSAL_HINTS = ("확인", "찾지 못", "없습니다", "근거")
# '오늘 만든 메모' 케이스가 달력에 따라 깨지지 않도록 기준 시간대를 챗봇과 동일한 KST로 둔다.
_KST = timezone(timedelta(hours=9))


def _load_cases() -> dict:
    return json.loads((Path(__file__).parent / "cases.json").read_text("utf-8"))


def _resolve_created_at(value: str) -> datetime:
    """픽스처의 생성 시각을 해석한다.

    'today'/'yesterday' 상대 표현을 지원해, 언제 돌려도 '오늘 만든 메모' 케이스가
    유효하도록 한다(고정 날짜를 박으면 날짜가 지나면서 eval이 시간 의존적으로 깨진다).
    """
    # 색인 스키마는 created_at이 UTC여야 하므로, KST로 '오늘'을 잡되 동일 시점을 UTC로 변환해 반환한다.
    now = datetime.now(_KST)
    if value == "today":
        return now.astimezone(timezone.utc)
    if value == "yesterday":
        return (now - timedelta(days=1)).astimezone(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


async def _seed(container, documents: list[dict]) -> None:
    """픽스처 문서를 eval 전용 소유자로 색인한다(질의 대상 자료를 미리 심는 단계)."""
    for doc in documents:
        command = IndexDocumentCommand(
            document_id=uuid4(),
            document_type=doc["document_type"],
            owner_user_id=_EVAL_OWNER,
            title=doc["title"],
            content=doc["content"],
            access_scope=AccessScope(user_ids=[_EVAL_OWNER]),
            metadata=DocumentMetadata(),
            created_at=_resolve_created_at(doc["created_at"]),
        )
        await container.document_indexing_workflow.execute(command)


def _evaluate(expect: dict, answer: str, source_titles: list[str]) -> tuple[bool, str]:
    """한 케이스의 기대값(contains/cites/min_sources/refuses)과 실제 응답을 대조한다."""
    if expect.get("refuses"):
        if source_titles:
            return False, f"거부 기대인데 출처가 있음: {source_titles}"
        if not any(hint in answer for hint in _REFUSAL_HINTS):
            return False, "거부 기대인데 답변이 근거없음류가 아님"
        return True, "거부 정상"
    for needle in expect.get("contains", []):
        if needle not in answer:
            return False, f"답변에 '{needle}' 없음"
    cites = expect.get("cites")
    if cites and not any(cites in title for title in source_titles):
        return False, f"출처에 '{cites}' 없음 (출처: {source_titles})"
    min_sources = expect.get("min_sources")
    if min_sources is not None and len(source_titles) < min_sources:
        return False, f"출처 {len(source_titles)}개 < 기대 {min_sources}개"
    return True, "통과"


async def _cleanup(settings) -> None:
    """eval 소유자로 색인된 모든 point를 삭제해 실데이터를 오염시키지 않는다."""
    body = {
        "filter": {
            "must": [{"key": "ownerUserId", "match": {"value": str(_EVAL_OWNER)}}]
        }
    }
    url = (
        f"{settings.qdrant_url.rstrip('/')}"
        f"/collections/{settings.qdrant_collection}/points/delete?wait=true"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(url, json=body)


async def _run_cases(
    container, cases: list[dict], *, verbose: bool = True
) -> tuple[int, int, float, float]:
    """케이스를 실행해 통과 수와 비용 지표(평균 출처 수·평균 출처 글자 수)를 함께 돌려준다.

    출처 수/글자 수는 모델에 들어가는 입력 토큰에 대략 비례하므로, top_n 스윕에서 정확도 대비
    비용을 비교하는 상대 지표로 쓴다(정확한 토큰 수는 아니다).
    """
    passed = 0
    total_sources = 0
    total_chars = 0
    for case in cases:
        command = ChatCommand(
            request_id=uuid4(),
            correlation_id=uuid4(),
            user_id=_EVAL_OWNER,
            question=case["question"],
            message_history=[],
            shared_workspace_ids=[],
        )
        result = await container.chat_workflow.execute(command)
        titles = [source.title for source in result.sources]
        total_sources += len(result.sources)
        total_chars += sum(len(source.snippet) for source in result.sources)
        ok, reason = _evaluate(case["expect"], result.answer, titles)
        passed += ok
        if verbose:
            mark = "PASS" if ok else "FAIL"
            print(f"[{mark}] {case['id']:<18} {reason}")
            if not ok:
                print(f"        Q: {case['question']}")
                print(f"        A: {result.answer[:160]}")
    count = len(cases)
    # 0건 분모 방지(케이스가 비어 있을 일은 없지만 안전하게 처리한다).
    return passed, count, total_sources / count, total_chars / count


async def main() -> int:
    """기본 설정의 top_n으로 eval을 1회 실행한다."""
    settings = get_settings()
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY가 필요합니다(eval은 실제 임베딩·생성을 사용).")
        return 2

    data = _load_cases()
    container = build_container(settings)
    try:
        await _seed(container, data["documents"])
        await asyncio.sleep(1.0)  # upsert 직후 조회 가능해지도록 잠시 대기
        print(
            f"\n=== 챗봇 eval ({len(data['cases'])} cases, "
            f"top_n={settings.rerank_top_n}) ==="
        )
        passed, total, _, _ = await _run_cases(container, data["cases"])
    finally:
        # 성공/실패와 무관하게 eval 색인을 정리해 실데이터를 오염시키지 않는다.
        await _cleanup(settings)

    print(f"\n결과: {passed}/{total} 통과 ({passed / total * 100:.0f}%)\n")
    return 0 if passed == total else 1


async def _sweep(values: list[int]) -> int:
    """top_n(리랭커가 남기는 출처 수)을 여러 값으로 바꿔가며 정확도와 비용 지표를 비교한다.

    색인은 top_n과 무관하므로 한 번만 심고, 값마다 챗 워크플로만 새로 구성해 같은 케이스를 재질의한다.
    목표: 정확도(통과율)는 유지되면서 평균 출처 수/글자 수가 가장 적은 top_n을 찾는 것.
    """
    base = get_settings()
    if not base.gemini_api_key:
        print("GEMINI_API_KEY가 필요합니다(eval은 실제 임베딩·생성을 사용).")
        return 2

    data = _load_cases()
    # 색인은 top_n과 무관하므로 기본 설정으로 한 번만 심어 재사용한다.
    seed_container = build_container(base)
    rows: list[tuple[int, int, int, float, float]] = []
    try:
        await _seed(seed_container, data["documents"])
        await asyncio.sleep(1.0)
        for top_n in values:
            # 같은 색인 데이터에 top_n만 바꾼 챗 워크플로로 동일 케이스를 재실행한다.
            swept = base.model_copy(update={"rerank_top_n": top_n})
            container = build_container(swept)
            print(f"\n--- top_n={top_n} ---")
            passed, total, avg_sources, avg_chars = await _run_cases(
                container, data["cases"]
            )
            rows.append((top_n, passed, total, avg_sources, avg_chars))
    finally:
        await _cleanup(base)

    # 요약 표: 통과는 정확도, 평균출처/평균글자는 입력 토큰(비용)의 대략적 비례 지표다.
    print("\n=== top_n 스윕 요약 ===")
    print(f"{'top_n':>6} | {'통과':>7} | {'평균출처':>8} | {'평균글자':>8}")
    print("-" * 42)
    for top_n, passed, total, avg_sources, avg_chars in rows:
        print(
            f"{top_n:>6} | {passed:>3}/{total:<3} | "
            f"{avg_sources:>8.1f} | {avg_chars:>8.0f}"
        )
    print(
        "\n정확도(통과율)가 유지되는 선에서 평균출처/평균글자가 가장 작은 top_n을 고르세요.\n"
    )
    return 0


if __name__ == "__main__":
    # 사용법:
    #   uv run python eval/run_eval.py                  → 기본 top_n으로 1회 평가
    #   uv run python eval/run_eval.py sweep 5 6 8 10   → top_n 스윕 비교(숫자 생략 시 기본 후보)
    cli_args = sys.argv[1:]
    if cli_args and cli_args[0] == "sweep":
        sweep_values = [int(value) for value in cli_args[1:]] or [5, 6, 8, 10]
        raise SystemExit(asyncio.run(_sweep(sweep_values)))
    raise SystemExit(asyncio.run(main()))
