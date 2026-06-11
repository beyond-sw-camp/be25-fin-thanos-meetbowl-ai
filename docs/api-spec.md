# Meetbowl ai-server API 명세서

## 1. 역할

`meetbowl-ai`는 Meetbowl의 AI 처리 서버다.

담당 범위:

- STT 원문 기반 AI 회의록 초안 생성
- 회의록 재생성/요약
- 회의 중 실시간 피드백 생성
- 이전 결정사항 리마인드
- 중복 논의 감지
- 피드백 근거 회의록 연결
- AI 챗봇 답변 생성
- 권한 기반 RAG 검색
- Qdrant 기반 벡터 검색
- LLM Provider 호출

`meetbowl-ai`는 프론트엔드가 직접 호출하지 않는다.

---

## 2. 공통 규칙

### Base URL

```text
/api/v1
```

### 인증

내부 서버 간 인증을 사용한다.

```http
X-Internal-Token: {internalToken}
```

### 공통 성공 응답

```json
{
  "success": true,
  "data": {},
  "message": null
}
```

### 공통 실패 응답

```json
{
  "success": false,
  "error": {
    "code": "AI_ERROR_CODE",
    "message": "오류 메시지",
    "details": []
  }
}
```

---

## 3. Error Code

| Code | HTTP | 설명 |
|---|---:|---|
| `AI_PROVIDER_UNAVAILABLE` | 503 | LLM/Embedding Provider 장애 |
| `AI_RESPONSE_PARSE_FAILED` | 502 | LLM 응답 파싱 실패 |
| `AI_RESPONSE_VALIDATION_FAILED` | 502 | LLM 응답 스키마 검증 실패 |
| `AI_RAG_ACCESS_DENIED` | 403 | 권한 없는 RAG 접근 |
| `AI_CONTEXT_NOT_FOUND` | 404 | 답변/피드백 생성 컨텍스트 없음 |
| `AI_DOCUMENT_INDEX_FAILED` | 500 | 문서 색인 실패 |
| `AI_FEEDBACK_GENERATION_FAILED` | 500 | 피드백 생성 실패 |

---

## 4. Health API

| Method | Endpoint | 설명 | 호출 주체 |
|---|---|---|---|
| GET | `/health` | 서버 상태 확인 | Infra/API Server |
| GET | `/health/llm` | LLM Provider 연결 상태 확인 | Infra/API Server |
| GET | `/health/vector-store` | Qdrant 연결 상태 확인 | Infra/API Server |

---

## 5. Meeting Minutes Generation API

관련 요구사항:

```text
FR-041
FR-142~146
```

회의 종료 후 자동 회의록 생성과 수동 재생성의 운영 기본 경로는 RabbitMQ Consumer다.

REST API는 테스트, 관리성 수동 호출, 장애 대응용 재처리 경로로 사용한다.

현재 개발 단계의 회의록 생성 파이프라인은 Gemini API의 structured output을 사용한다.
생성 workflow의 원문 입력 계약은 하나의 긴 `rawTranscript` 문자열이다. RabbitMQ 이벤트
경로의 회의 정보와 원문은 아직 `FakeMinutesContextLoader`의
결정적인 개발용 fixture로 구성하며, 운영 적용 전 `meetbowl-be` 내부 context API를
호출하는 adapter로 교체해야 한다. 향후 원문이 발화 목록으로 확정되면 context adapter에서
시간순 정렬 및 긴 문자열 결합을 수행한 뒤 기존 workflow에 전달한다. REST
`/minutes/generate` 입력의 참여자와 `rawTranscript`는 동일한 workflow에서 직접 사용한다.
외부 API 없는 테스트에는 `LLM_PROVIDER=fake`를 사용할 수 있다.

| Method | Endpoint | 설명 | 호출 주체 |
|---|---|---|---|
| POST | `/minutes/generate` | 회의록 초안 생성 | meetbowl-be/RabbitMQ Consumer |
| POST | `/minutes/regenerate` | 회의록 초안 재생성 | meetbowl-be |
| POST | `/minutes/summarize` | 회의 원문 요약 | meetbowl-be |
| POST | `/minutes/extract-actions` | 결정사항/후속 조치 추출 | meetbowl-be |

### POST `/minutes/generate`

#### Request

```json
{
  "meetingId": "uuid",
  "organizationId": "uuid",
  "hostUserId": "uuid",
  "reviewerUserId": "uuid",
  "title": "회의 제목",
  "startedAt": "2026-06-02T00:00:00Z",
  "endedAt": "2026-06-02T01:00:00Z",
  "participants": [
    {
      "userId": "uuid",
      "name": "홍길동",
      "department": "기획팀"
    }
  ],
  "rawTranscript": "오늘 회의 안건은 배포 일정입니다.\n금요일 배포를 결정했습니다."
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "meetingId": "uuid",
    "status": "DRAFT",
    "minutesDraft": {
      "summary": "회의 요약",
      "agendaItems": [
        {
          "title": "안건명",
          "discussion": "논의 내용",
          "decision": "결정 사항"
        }
      ],
      "decisions": ["결정사항 1"],
      "actionItems": [
        {
          "content": "후속 조치",
          "assigneeName": "홍길동",
          "dueDate": null
        }
      ]
    },
    "editorContent": {
      "type": "doc",
      "content": [
        {
          "type": "heading",
          "attrs": {
            "level": 1
          },
          "content": [
            {
              "type": "text",
              "text": "회의록"
            }
          ]
        }
      ]
    },
    "model": "llm-model-name",
    "promptVersion": "minutes-v1",
    "generatedAt": "2026-06-02T01:05:00Z"
  },
  "message": null
}
```

`editorContent`는 검증된 `minutesDraft`를 AI 서버가 결정적으로 변환한 Tiptap
StarterKit 호환 JSON이다. 회의 요약은 기본으로 포함하며, 안건별 논의, 결정사항,
후속 조치는 실제 내용이 존재할 때만 섹션을 생성한다. Gemini가 editor node를 직접
생성하지 않는다. 현재 루트
이벤트 계약의 `minutes.generated` payload에는 `editorContent`가 정의되어 있지 않으므로
RabbitMQ 발행 payload에는 포함하지 않는다.

---

## 6. Real-time Meeting Feedback API

실시간 피드백은 REST보다 Redis Stream 소비 방식이 기본이다.

REST API는 테스트/수동 호출/폴백 용도로 둔다.

| Method | Endpoint | 설명 | 호출 주체 |
|---|---|---|---|
| POST | `/meeting-feedback/analyze` | 현재 발화 기반 실시간 피드백 생성 | meetbowl-stt/meetbowl-be |
| POST | `/meeting-feedback/remind-decisions` | 이전 결정사항 리마인드 생성 | meetbowl-stt/meetbowl-be |
| POST | `/meeting-feedback/detect-duplicate` | 중복 논의 감지 | meetbowl-stt/meetbowl-be |

### Response

```json
{
  "success": true,
  "data": {
    "feedbackType": "DECISION_REMINDER",
    "message": "이 안건은 지난 회의에서 이미 A안으로 결정된 이력이 있습니다.",
    "sources": [
      {
        "minutesId": "uuid",
        "meetingId": "uuid",
        "title": "지난 회의 제목",
        "meetingDate": "2026-05-20",
        "snippet": "A안으로 진행하기로 결정"
      }
    ],
    "model": "llm-model-name",
    "generatedAt": "2026-06-02T01:10:00Z"
  },
  "message": null
}
```

---

## 7. Chatbot API

`meetbowl-be`가 사용자 인증과 자료 접근 권한을 검증한 뒤 호출한다.

| Method | Endpoint | 설명 | 호출 주체 |
|---|---|---|---|
| POST | `/chat` | AI 챗봇 질의 | meetbowl-be |
| POST | `/chat/search-context` | 답변 전 권한 기반 컨텍스트 검색 | meetbowl-be |

### POST `/chat`

#### Request

```json
{
  "requestId": "uuid",
  "correlationId": "uuid",
  "userId": "uuid",
  "organizationId": "uuid",
  "question": "지난 회의에서 결정된 배포 일정 알려줘",
  "messageHistory": [
    {
      "role": "user",
      "content": "배포 관련 자료를 찾아줘"
    },
    {
      "role": "assistant",
      "content": "관련 자료를 찾았습니다. 어떤 내용을 확인할까요?"
    }
  ],
  "sharedWorkspaceIds": ["uuid"]
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "answer": "지난 회의에서는 6월 10일까지 1차 배포를 진행하기로 결정했습니다.",
    "sources": [
      {
        "type": "MEETING_MINUTES",
        "resourceId": "uuid",
        "title": "배포 일정 회의록",
        "snippet": "6월 10일까지 1차 배포"
      }
    ],
    "model": "llm-model-name"
  },
  "message": null
}
```

Qdrant 검색은 `organizationId`가 일치하면서 `ownerUserId == userId` 또는
`workspaceId/sharedWorkspaceIds`가 요청의 `sharedWorkspaceIds`에 포함되는 자료로 제한한다.
권한이 없는 자료는 검색 결과와 답변에 포함하지 않는다. `X-Internal-Token`이 없거나 다르면 403을 반환한다.

자료에서 확인되지 않는 내용을 단정하지 않는다.

---

## 8. Embedding / Indexing API

Qdrant 색인은 `meetbowl-ai`가 담당한다. 단, 원본 업무 데이터의 소유권은 `meetbowl-be`에 있다.

문서 색인의 운영 기본 경로는 RabbitMQ `document.index.requested` 이벤트 소비다.

REST API는 테스트, 관리성 수동 호출, 장애 대응용 재처리 경로로 사용한다.

| Method | Endpoint | 설명 | 호출 주체 |
|---|---|---|---|
| POST | `/indexes/documents` | 문서 임베딩 및 색인 | meetbowl-be/Event Consumer |
| DELETE | `/indexes/documents/{documentId}` | 문서 색인 삭제 | meetbowl-be/Event Consumer |
| POST | `/indexes/search` | 벡터 검색 | meetbowl-be/Internal |

### POST `/indexes/documents`

```json
{
  "documentId": "uuid",
  "documentType": "MEETING_MINUTES",
  "organizationId": "uuid",
  "ownerUserId": "uuid",
  "accessScope": {
    "userIds": ["uuid"],
    "departmentIds": ["uuid"],
    "sharedWorkspaceIds": []
  },
  "title": "회의록 제목",
  "content": "색인할 본문",
  "metadata": {
    "meetingId": "uuid",
    "workspaceId": "uuid",
    "fileVersionId": "uuid",
    "createdAt": "2026-06-02T01:00:00Z"
  }
}
```

---

## 9. Queue / Stream Consumer

`meetbowl-ai`는 아래 메시지를 소비할 수 있다.

| Source | Event | 설명 |
|---|---|---|
| RabbitMQ `ai.minutes.generate` | `meeting.ended` | 회의 종료 후 회의록 생성 |
| RabbitMQ `ai.minutes.regenerate` | `minutes.generation.requested` | 회의록 생성/재생성 |
| RabbitMQ `ai.index.document` | `document.index.requested` | 자료 색인 |
| Redis Stream | `meeting.feedback.requested` | Final Transcript 기반 실시간 피드백 분석 |

발행:

| Target | Event | 설명 |
|---|---|---|
| RabbitMQ | `minutes.generated` | AI 회의록 초안 생성 완료 |
| Redis Stream | `meeting.feedback.generated` | STT 서버로 실시간 회의 피드백 결과 전달 |

---

## 10. 저장 원칙

- `meetbowl-ai`는 MariaDB에 직접 쓰지 않는다.
- 회의록 초안 저장 요청의 운영 기본 경로는 RabbitMQ `minutes.generated` 이벤트 발행이다.
- `meetbowl-be` 내부 API 호출은 장애 대응, 수동 재처리, 테스트 용도로만 사용한다.
- Qdrant에는 검색용 벡터와 권한 필터용 metadata만 저장한다.
- AI 답변은 가능한 한 참조 출처를 포함한다.
- 권한이 없는 자료는 검색 결과와 답변에 포함하지 않는다.
