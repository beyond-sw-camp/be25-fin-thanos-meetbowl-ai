# Meetbowl AI Server AGENTS

## 목적

본 문서는 `meetbowl-ai`에서 작업하는 모든 개발자와 AI Agent가 반드시 따라야 하는 규칙을 정의한다.

---

## 필수 문서

작업 전 반드시 아래 문서를 읽는다.

```text
../AGENTS.md
../docs/architecture.md
../docs/conventions.md
../docs/event-contract.md
../docs/communication-decision.md
docs/architecture.md
docs/conventions.md
docs/api-spec.md
```

---

## 역할

`meetbowl-ai`는 AI 처리 전용 서버이다.

담당 기능:

- 회의록 초안 생성
- 회의 요약
- 결정사항/후속 조치 추출
- 실시간 피드백
- 이전 결정사항 리마인드
- 중복 논의 감지
- 피드백 근거 회의록 연결
- 챗봇
- RAG
- 임베딩
- Qdrant 검색

---

## 데이터 소유권

`meetbowl-ai`만 Qdrant에 접근할 수 있다.

금지:

```text
MariaDB 직접 접근
LiveKit 직접 접근
업무 상태 직접 변경
내부 메일 직접 발송
```

AI 처리 결과 저장은 `meetbowl-be`에 이벤트 또는 내부 API로 요청한다.

---

## LLM 규칙

LLM Provider 추상화를 사용한다.

허용 Provider:

```text
Gemini
Claude
OpenAI
```

UseCase 또는 Workflow에서 Provider SDK를 직접 호출하지 않는다.

---

## Prompt 규칙

프롬프트를 UseCase 또는 Workflow 코드에 직접 작성하지 않는다.

반드시 `prompts` 모듈에서 관리한다.

모든 주요 Prompt는 버전을 가진다.

예시:

```text
minutes-v1
chat-v1
feedback-v1
```

---

## RAG 규칙

Qdrant 접근은 `rag` 모듈만 수행한다.

Workflow에서 직접 Qdrant를 호출하지 않는다.

권한 필터 없는 RAG 검색은 금지한다.

챗봇과 실시간 피드백은 사용자가 열람 권한을 가진 자료만 기반으로 답변하거나 피드백을 생성한다.

---

## 이벤트 규칙

이벤트 이름과 payload는 루트 `docs/event-contract.md`를 따른다.

구독:

```text
meeting.ended
minutes.generation.requested
document.index.requested
meeting.feedback.requested
```

발행:

```text
minutes.generated
meeting.feedback.generated
```

임의 이벤트 추가 금지.

---

## 금지 사항

- 사용자 인증 구현
- 회의 CRUD 구현
- 메일 CRUD 구현
- MariaDB 접근
- 비즈니스 데이터 직접 저장
- 권한 필터 없는 RAG 검색
- LLM 응답을 검증 없이 저장 요청
- 출처 없는 챗봇 답변을 확정적으로 제공

---

## 구현 원칙

- 모든 AI 기능은 Workflow 단위로 구현한다.
- 모든 LLM 응답은 Schema Validation을 수행한다.
- AI 회의록은 검토자 승인 전까지 초안 상태임을 전제로 생성한다.
- 챗봇 답변은 가능한 한 출처를 포함한다.
- 자료에서 확인되지 않는 내용을 단정하지 않는다.
