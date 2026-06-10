# Meetbowl AI Server Conventions

## 목적

본 문서는 `meetbowl-ai`의 개발 규칙을 정의한다.

---

# 1. 구조

권장 구조:

```text
app
├─ api
├─ consumers
├─ workflows
├─ services
├─ pipelines
├─ prompts
├─ rag
├─ llm
├─ providers
├─ events
├─ schemas
└─ core
```

---

# 2. Workflow 규칙

AI 기능은 Workflow 단위로 구현한다.

예시:

```text
MinutesGenerationWorkflow
ChatWorkflow
FeedbackWorkflow
DocumentIndexWorkflow
```

Workflow는 다음을 담당한다.

- 입력 검증
- 권한 context 확인
- pipeline 호출
- 결과 구조화
- schema validation
- 이벤트 발행 요청

---

# 3. DTO / Schema 규칙

Pydantic Model을 사용한다.

구분:

| DTO | 용도 |
|---|---|
| API Request/Response Schema | 내부 REST API |
| Event Message Schema | RabbitMQ/Redis Stream 메시지 |
| Workflow Input/Output Schema | Workflow 내부 계약 |
| Provider DTO | LLM/Embedding Provider adapter |

금지:

- API Schema와 Event Message Schema 혼용
- Provider 응답을 검증 없이 Workflow 결과로 사용
- LLM 원문 응답을 그대로 저장 요청

---

# 4. LLM 규칙

LLM 호출은 반드시 Provider 추상화를 사용한다.

Provider Port는 기능(capability) 단위로 분리한다.

```text
TextGenerationPort
StreamingGenerationPort
StructuredGenerationPort
EmbeddingPort
```

구현체:

```text
GeminiProvider
ClaudeProvider
OpenAIProvider
```

Workflow는 실제 Provider 모델명이 아니라 `model_profile`을 요청한다.
Provider Adapter 또는 라우터가 profile을 실제 Provider/모델로 매핑한다.

```text
chatbot
minutes-summary
meeting-feedback
document-embedding
query-embedding
```

도메인별 `ChatbotLLMProvider`, `MinutesLLMProvider`를 만들거나 Provider Adapter에
`generate_minutes` 같은 도메인 메서드를 추가하지 않는다.

Provider Fallback 우선순위:

```text
Gemini
↓
Claude
↓
OpenAI
```

실패 시 fallback 정책을 적용할 수 있어야 한다.

---

# 5. Prompt 규칙

프롬프트는 코드에 직접 작성하지 않는다.

금지:

```python
prompt = "..."
```

허용:

```text
prompts/minutes.py
prompts/chat.py
prompts/feedback.py
```

모든 주요 Prompt는 버전을 가진다.

예시:

```text
minutes-v1
chat-v1
feedback-v1
```

---

# 6. RAG 규칙

Qdrant 접근은 `rag` 모듈만 수행한다.

금지:

```text
workflow → qdrant 직접 호출
```

RAG 검색에는 권한 필터를 필수로 적용한다.

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

권한 없는 자료는 검색 결과, 피드백, 챗봇 답변에 포함하지 않는다.

---

# 7. 응답 검증 규칙

LLM 응답은 검증 후 사용한다.

필수 처리:

- JSON parse
- Pydantic schema validation
- 필수 필드 누락 확인
- 빈 결정사항/후속조치 처리
- 출처 매핑 확인
- 권한 범위 확인

---

# 8. 에러 코드 규칙

AI 서버 에러 코드는 `AI_` prefix를 사용한다.

예시:

```text
AI_PROVIDER_UNAVAILABLE
AI_RESPONSE_PARSE_FAILED
AI_RESPONSE_VALIDATION_FAILED
AI_RAG_ACCESS_DENIED
AI_CONTEXT_NOT_FOUND
AI_DOCUMENT_INDEX_FAILED
AI_FEEDBACK_GENERATION_FAILED
```

Provider 상세 오류는 클라이언트에 그대로 노출하지 않는다.

---

# 9. 임베딩 규칙

하나의 Collection에는 하나의 Chunk Strategy만 사용한다.

Chunk 정책 변경 시 Collection을 분리한다.

Qdrant에는 원본 업무 데이터 전체를 저장하지 않는다.

검색용 벡터와 권한 필터에 필요한 최소 metadata만 저장한다.

---

# 10. 금지사항

- MariaDB 직접 접근
- 권한 필터 없는 RAG 검색
- LLM 응답을 검증 없이 저장 요청
- Prompt를 UseCase/Workflow 내부에 하드코딩
- Provider별 SDK 호출을 여러 곳에 분산
- AI가 생성한 내용을 사실로 단정하는 응답
- 출처 없는 챗봇 답변을 확정적으로 제공
