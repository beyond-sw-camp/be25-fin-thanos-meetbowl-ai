# Meetbowl ai-server 아키텍처

## 1. 목적

`meetbowl-ai`는 Meetbowl의 AI 기능을 담당하는 내부 서버다.

회의록 초안 생성, 회의 요약, 실시간 회의 피드백, AI 챗봇, 번역 보조, RAG 검색, LLM Provider 연동을 담당한다.

일반 사용자는 `meetbowl-ai`를 직접 호출하지 않는다.

프론트엔드는 `meetbowl-be`를 호출하고, `meetbowl-be`가 내부 API 또는 이벤트를 통해 `meetbowl-ai`와 통신한다.

---

## 2. 책임 범위

`meetbowl-ai`가 담당하는 책임은 다음과 같다.

- STT Final Transcript 기반 AI 회의록 초안 생성
- 회의 주요 내용, 결정사항, 후속 조치 추출
- 회의록 검토자에게 제공할 초안 구조화
- 실시간 회의 발화 기반 이전 결정사항 리마인드
- 중복 논의 가능성 탐지
- 관련 회의록 근거 연결
- AI 챗봇 답변 생성
- 사용자가 열람 가능한 자료만 대상으로 한 RAG 검색
- Qdrant 벡터 검색
- Embedding 생성
- LLM Provider 호출 및 fallback
- AI 결과의 출처 정보 구성
- AI 처리 결과 이벤트 발행

`meetbowl-ai`는 사용자 인증의 최종 판단, MariaDB 직접 저장, 내부 메일 발송, 회의실 예약 정합성 처리를 담당하지 않는다.

---

## 3. 외부 시스템 관계

```text
meetbowl-be
  ↓ internal REST / RabbitMQ
meetbowl-ai
  ↓ Qdrant
  ↓ LLM Provider
  ↓ Embedding Provider
  ↓ Redis Stream
  ↓ RabbitMQ
  ↓ Object Storage Read
```

### meetbowl-be

`meetbowl-ai`의 업무 요청 출처다.

예시:

- 회의록 생성 요청
- 챗봇 질의 요청
- 자료 인덱싱 요청
- 권한 context 전달

### Qdrant

벡터 검색 저장소다.

저장 대상:

- 회의록 chunk embedding
- 백업 메일 chunk embedding
- 공유 워크스페이스 파일 chunk embedding
- 개인 워크스페이스 자료 chunk embedding

Qdrant에는 원본 업무 데이터 전체를 저장하지 않는다.

권한 필터링에 필요한 최소 metadata만 함께 저장한다.

문서 색인은 `DocumentIndexingWorkflow`가 embedding provider와 `rag` 모듈의 Qdrant
index adapter를 조율한다. REST 입력 계약은 translator를 거쳐 내부 command로 변환되며,
검색 시 사용하는 source type과 권한 metadata를 동일한 형식으로 저장한다. 본문은
`rag.chunking`이 문단 경계와 overlap을 고려해 청크로 나누고, 청크마다 별도 point로
색인해 긴 문서에서도 질문과 맞는 부분만 검색되도록 한다.

### RabbitMQ

오래 걸리거나 반드시 처리되어야 하는 AI 작업에 사용한다.

예시:

- `meeting.ended`
- `minutes.generation.requested`
- `minutes.generated`
- `document.index.requested`

### Redis Stream

실시간성이 강한 회의 중 이벤트 흐름에 사용한다.

예시:

- STT Final Transcript 기반 피드백 요청
- 실시간 회의 피드백 요청
- 실시간 회의 피드백 결과를 STT 서버로 전달

Redis Stream 데이터는 장기 보관 데이터가 아니다.

---

## 4. 레이어 구조

`meetbowl-ai`는 다음 구조를 따른다.

```text
api / consumer
  ↓
workflow / usecase
  ↓
pipeline
  ↓
provider / adapter
```

### api / consumer

외부 요청 진입점이다.

- FastAPI Router
- RabbitMQ Consumer
- Redis Stream Consumer

여기에는 AI 로직을 직접 작성하지 않는다.

BE 챗봇 REST 계약은 API schema에서만 해석하고 translator를 거쳐 내부
`ChatCommand`로 변환한다. BE 요청/응답 필드가 변경될 때 workflow와 provider 계약을
직접 변경하지 않고 translator에서 호환성을 조정한다.

챗봇 답변은 PydanticAI Agent가 생성한다. 접근 context(`ChatCommand`)를 Agent
dependency로 주입하고, Agent는 `search_documents` Tool을 호출해 근거를 검색한 뒤
구조화된 답변(`GeneratedChatAnswer`)을 반환한다. `messageHistory`는 Agent 실행
문맥으로만 전달하고 저장하지 않는다. 검색 Tool은 질문이 특정 유형에 한정될 때
`source_types` 인자로 범위를 좁힐 수 있고, 검색 결과는 넓게 모은 뒤 reranker가 질의
관련도로 재정렬해 상위 N개만 답변 근거로 쓴다(`ports.reranker` — 운영은 Gemini,
테스트는 결정적 Fake).

챗봇 검색은 dense(의미) 벡터와 sparse(BM25) 벡터를 함께 쓰는 하이브리드 방식이다.
색인 시 `rag.sparse`가 청크마다 sparse 벡터를 만들어 dense 벡터와 같이 저장하고,
검색 시 두 경로를 Qdrant의 RRF(Reciprocal Rank Fusion)로 융합해 의미·키워드 매칭을
모두 살린다. sparse 인덱스는 `modifier: idf`라서 Qdrant가 질의 시점에 IDF를 적용한다.

챗봇 검색 권한 조건은 `rag.access_filter`의 공통 builder에서 생성한다. 모든 검색은
조직 일치 조건과 `ownerUserId == userId` 또는 BE가 요청마다 계산한 공유 워크스페이스
조건을 함께 적용하며, 권한 필터는 dense·sparse 두 검색 경로 모두에 붙는다. 실제 Qdrant
HTTP 호출과 payload-to-source 변환도 `rag` adapter가 담당하며 검색 Tool은 `rag`
adapter를 통해서만 Qdrant에 접근한다.

### workflow / usecase

AI 작업 단위를 조율한다.

예시:

- `GenerateMinutesWorkflow`
- `AnswerChatWorkflow`
- `GenerateMeetingFeedbackWorkflow`
- `IndexDocumentWorkflow`

역할:

- 입력 검증
- 권한 context 확인
- pipeline 호출
- 결과 구조화
- schema validation
- 이벤트 발행

### pipeline

AI 처리 흐름의 핵심이다.

예시:

- Transcript 정제
- chunk 구성
- RAG 검색
- prompt 구성
- LLM 호출
- JSON 파싱
- 품질 검증
- 출처 매핑

### provider / adapter

외부 AI Provider와 저장소 연동을 담당한다.

예시:

- Gemini Adapter
- OpenAI Adapter
- Claude Adapter
- Embedding Adapter
- Qdrant Adapter
- Object Storage Reader
- RabbitMQ Publisher

---

## 5. 권장 모듈 구조

```text
app
  api
  consumers
  workflows
  services
  pipelines
  providers
  rag
  prompts
  schemas
  events
  core
  utils
```

---

## 6. 데이터 접근 원칙

`meetbowl-ai`는 MariaDB에 직접 접근하지 않는다.

필요한 업무 데이터는 다음 방식으로 받는다.

1. `meetbowl-be`가 요청 payload에 포함
2. `meetbowl-be` 내부 API를 통해 조회
3. RabbitMQ 이벤트 payload로 전달
4. Object Storage에서 파일 원본을 읽고 처리

AI 결과 저장도 `meetbowl-ai`가 DB에 직접 저장하지 않는다.

```text
meetbowl-ai
  ↓ minutes.generated event
meetbowl-be
  ↓
MariaDB
```

---

## 7. RAG 설계 원칙

AI 챗봇과 실시간 회의 피드백은 권한 기반 RAG를 사용한다.

검색 대상은 사용자가 열람 가능한 자료로 제한한다.

필수 metadata 예시:

```json
{
  "sourceType": "MEETING_MINUTES",
  "sourceId": "minutes-id",
  "organizationId": "organization-id",
  "ownerUserId": "user-id",
  "allowedUserIds": ["user-id"],
  "allowedDepartmentIds": ["department-id"],
  "sharedWorkspaceIds": ["space-id"],
  "createdAt": "2026-06-02T00:00:00Z"
}
```

권한 필터 없이 전체 벡터 검색을 수행하면 안 된다.

---

## 8. 회의록 생성 흐름

```text
meetbowl-be
  ↓ meeting.ended or minutes.generation.requested
RabbitMQ
  ↓
meetbowl-ai consumer
  ↓ transcript load
  ↓ transcript cleanup
  ↓ agenda/decision/action item extraction
  ↓ minutes draft generation
  ↓ JSON schema validation
  ↓ quality check
  ↓ minutes.generated event
RabbitMQ
  ↓
meetbowl-be
```

회의록 생성 결과는 검토자 승인 전까지 `DRAFT` 상태다.

`meetbowl-ai`는 회의록을 최종본으로 확정하지 않는다.

---

## 9. AI 챗봇 흐름

```text
meetbowl-fe
  ↓
meetbowl-be
  ↓ POST /chat
meetbowl-ai
  ↓ user permission context 확인
  ↓ Qdrant metadata filter 구성
  ↓ vector search
  ↓ source rerank
  ↓ prompt 구성
  ↓ LLM answer 생성
  ↓ citation 포함 응답
meetbowl-be
  ↓
meetbowl-fe
```

챗봇은 자료에서 확인되지 않는 내용을 단정하지 않는다.

답변에는 가능한 한 출처를 포함한다.

---

## 10. 실시간 회의 피드백 흐름

```text
meetbowl-stt
  ↓ Redis Stream: meeting.feedback.requested(final transcript window)
meetbowl-ai
  ↓ 최근 발화 window 구성
  ↓ 회의 주제 추정
  ↓ 권한 기반 과거 회의록 검색
  ↓ 중복 논의/이전 결정사항 판단
  ↓ 근거 회의록 매핑
  ↓ meeting.feedback.generated 발행
Redis Stream
  ↓
meetbowl-stt
  ↓ LiveKit DataChannel
meetbowl-fe
```

실시간 피드백은 회의 흐름을 방해하지 않도록 짧고 근거 중심으로 제공한다.

피드백은 가능한 경우 관련 회의록 제목, 회의 일자, 결정사항 snippet을 포함한다.

`meetbowl-ai`는 사용자 화면에 직접 피드백을 전송하지 않는다. 피드백 결과는 Redis Stream으로 `meetbowl-stt`에 전달하고, `meetbowl-stt`가 LiveKit DataChannel로 회의 참여자에게 전달한다.

---

## 11. LLM Provider 원칙

LLM Provider는 교체 가능해야 한다.

Provider 직접 호출 코드를 Workflow에 작성하지 않는다.

반드시 Provider Adapter를 통해 호출한다.

권장 구조:

```text
LLMProvider interface
  ├─ GeminiProvider
  ├─ OpenAIProvider
  └─ ClaudeProvider
```

Provider 장애 시 fallback 정책을 적용할 수 있어야 한다.

---

## 12. JSON 출력 검증

회의록, 피드백, 구조화 요약은 반드시 schema validation을 거친다.

LLM 응답을 그대로 신뢰하지 않는다.

필수 처리:

- JSON parse
- schema validation
- 필수 필드 누락 확인
- 빈 결정사항/후속조치 처리
- 출처 매핑 확인
- 권한 범위 확인

---

## 13. 금지 사항

- MariaDB 직접 접근 금지
- 권한 필터 없는 RAG 검색 금지
- LLM 응답을 검증 없이 저장 요청 금지
- Prompt를 Workflow 내부에 하드코딩 금지
- Provider별 SDK 호출을 여러 곳에 분산 금지
- AI가 생성한 내용을 사실로 단정하는 응답 금지
- 출처 없는 챗봇 답변을 확정적으로 제공 금지
