## 2026-06-22 실시간 피드백 query embedding 관측 로그 추가

- 목적: Redis Final segment 소비 이후 AI가 실제 query embedding을 수행했는지 운영 로그로 확인한다.
- 변경 근거: consumer ACK만으로는 rolling window gate 통과와 embedding provider 호출 완료를 구분할 수 없었다.
- 변경 파일: `app/workflows/meeting_feedback.py`
- 변경 동작: embedding 응답 이후 meeting/session ID, 모델명, 벡터 차원, window segment 수와 문자 수를 INFO로 기록한다.
- 보안: 회의 원문과 embedding vector는 로그에 남기지 않는다.
- 제외 범위: Qdrant 문서 색인 생성과 검색 기준은 변경하지 않았다.
- 로그 출력: Uvicorn 기본 설정에서 INFO가 누락되지 않도록 `uvicorn.error` 로거를 사용한다.
- 검증: 피드백 workflow 및 Redis consumer 테스트 13개 통과.

## 2026-06-22 OpenAI large 1536차원 검색 공간 적용

- 목적: 문서·질의 임베딩을 `text-embedding-3-large` 1536차원으로 통일한다.
- 변경 파일: 설정/모델 프로필, OpenAI embedding provider, container wiring, 환경 예시, 테스트 및 관련 문서.
- 변경 동작: OpenAI `/embeddings` 요청에 `dimensions=1536`을 전달하며 문서·질의 provider/model/dimensions 불일치를 기동 시 거부한다.
- Qdrant: 기존 3072차원 컬렉션을 재사용하지 않고 `meetbowl-documents-openai-large-1536`을 사용한다.
- 남은 작업: 과거 회의록 및 검색 대상 문서를 새 컬렉션에 전체 재색인해야 한다.
- 검증: 전체 테스트 52개 통과. 실제 OpenAI API 호출에서 `text-embedding-3-large`, 1536차원 응답을 확인했다.

## 2026-06-23 실제 Final Transcript 기반 회의록 Context 연동

- 목적: RabbitMQ 회의록 생성 경로가 개발용 고정 원문이 아니라 BE가 저장한 Final Transcript를 사용하도록 한다.
- 변경 파일: HTTP Minutes Context Loader, container/config wiring, RabbitMQ 멱등성 tracker, 관련 테스트와 문서.
- 변경 동작: RabbitMQ 이벤트 처리 시 BE 시스템 전용 Context API를 호출하고, REST 직접 생성은 요청에 포함된 Context를 그대로 사용한다.
- 멱등성: AI 회의록 Consumer의 완료·재시도 상태를 Redis에 7일간 보존한다. 중복 결과가 발행되더라도 BE inbox가 최종 저장을 다시 방어한다.
- 제외 범위: FE 회의록 편집·승인 연결과 회의록 공유는 변경하지 않았다.
- 검증: AI 전체 테스트 53개 통과, Python compileall 통과.

## 2026-06-25 RabbitMQ 회의록 생성 실패 관측 로그 추가

- 목적: `meeting.ended`가 `dlq.ai.minutes.generate`로 이동할 때 AI Consumer가 실패 원인을 남기지 않아 운영 장애를 진단할 수 없던 문제를 해결한다.
- 변경 파일: `app/events/rabbit.py`, `tests/test_rabbit_minutes.py`
- 변경 동작: 회의록 처리 실패 시 `eventId`, `meetingId`, AI 오류 코드, 재시도 가능 여부와 오류 유형을 Uvicorn 오류 로그에 기록한다. 잘못된 Envelope는 payload 원문 없이 검증 실패 유형만 기록한다.
- 보안: 회의 원문, 전체 이벤트 payload, API Key, 내부 토큰은 로그에 남기지 않는다.
- 제외 범위: 재시도 횟수·간격, DLQ 정책, 회의록 생성 로직과 Provider 설정은 변경하지 않았다. 실제 운영 실패 원인은 변경 배포 후 DLQ 메시지를 재처리하여 로그로 확인해야 한다.
- 검증: Rabbit 회의록 테스트 6개, AI 전체 테스트 105개 통과, Python compileall 및 `git diff --check` 통과. Ruff는 현재 가상환경에 설치되어 있지 않아 실행하지 못했다.

## 2026-06-25 RabbitMQ 문서 색인 실패 관측 로그 추가

- 목적: `document.index.requested`가 `dlq.ai.index.document`로 이동할 때 S3 다운로드, 텍스트 추출, 임베딩, Qdrant 중 어느 단계에서 실패했는지 AI 서버 로그로 확인한다.
- 변경 파일: `app/core/errors.py`, `app/events/rabbit.py`, `app/providers/s3_file_storage.py`, `app/workflows/document_indexing.py`, `tests/test_rabbit_document_index.py`.
- 변경 동작: 문서 색인 외부 처리 실패를 `s3_download`, `text_extraction`, `embedding`, `qdrant` 단계로 구분한다. Consumer는 `eventId`, `documentId`, `documentType`, 오류 코드, 재시도 여부·횟수, 최종 목적지(`requeue`/`dlq`)와 실패 사유를 Uvicorn 오류 로그에 기록한다.
- 보안: 이벤트 본문, 파일명, storageKey, API Key와 전체 payload는 로그에 남기지 않는다. S3 Adapter 오류 메시지에서도 storageKey를 제거했다.
- 제외 범위: RabbitMQ 재시도 횟수, DLQ 정책, 임베딩·Qdrant 저장 방식은 변경하지 않았다.
- 검증: 문서 색인 관련 테스트 11개, AI 전체 테스트 106개, Python compileall 및 `git diff --check` 통과.

## 2026-06-25 회의록 Transcript sequence 계약 정합성 수정

- 목적: BE의 회의록 생성 Context가 첫 Final Transcript segment의 `sequence`를 0으로 반환할 때 AI가 `AI_CONTEXT_INVALID`로 거부하던 문제를 해결한다.
- 변경 근거: STT는 회의 내 sequence를 0부터 발급하고 BE 도메인도 0 이상을 유효한 값으로 저장한다.
- 변경 파일: `app/schemas/minutes.py`, `tests/test_http_minutes_context_loader.py`.
- 변경 동작: 회의록용 `TranscriptSegment.sequence` 검증 범위를 1 이상에서 0 이상으로 변경해 BE가 전달한 원본 sequence를 변환 없이 사용한다.
- 제외 범위: STT/BE sequence 발급 방식, 실시간 피드백 계약, 회의록 evidence 매핑 로직은 변경하지 않았다.
- 검증: 회의록 Context·품질 테스트 13개, AI 전체 테스트 111개, Python compileall 및 `git diff --check` 통과.

## 2026-06-25 실시간 회의 피드백 출력 축약

- 목적: 회의 중 표시되는 피드백 메시지와 근거가 길어 사용자가 즉시 파악하기 어려운 문제를 개선한다.
- 변경 파일: `app/workflows/meeting_feedback.py`, `app/schemas/feedback.py`, `app/schemas/events.py`, 관련 테스트와 AI 문서.
- 변경 동작: 피드백 메시지에서 회의록 원문을 제거하고 120자 이하 결론형 문장만 생성한다. 출처는 최대 2건, 각 snippet은 120자 이하로 축약한다.
- 변경 근거: 검색과 피드백 유형 판정에는 전체 snippet을 계속 사용하고, 화면 전달 직전에만 축약해 탐지 정확도와 현재 Redis/STT/FE 계약 호환성을 유지한다.
- 제외 범위: `headline` 신규 필드, STT Relay, FE 카드 UI와 누적 정책은 후속 계약 변경으로 남긴다.
- 검증: 피드백 관련 테스트 17개, AI 전체 테스트 112개, Python compileall 및 `git diff --check` 통과.

## 2026-07-01 Redis feedback consumer cluster 호환성 수정

- 목적: ElastiCache Serverless/cluster 환경에서 실시간 피드백 consumer가 `Keys in request don't hash to the same slot` 오류로 반복 실패하던 문제를 해결한다.
- 변경 파일: `app/consumers/redis_feedback.py`
- 변경 동작:
  - 기존에는 여러 `meeting:*:feedback-source` stream을 한 번의 `XREADGROUP` 호출로 함께 읽었다.
  - 이제는 stream별로 개별 `XREADGROUP`를 호출해 Redis cluster의 cross-slot 제약을 피한다.
  - 메시지 처리와 `XACK` 흐름, producer/STT 쪽 stream key 형식은 유지한다.
- 변경 근거:
  - 운영 Redis가 단일 노드가 아니라 cluster/serverless 모드이므로, 멀티키 stream read는 같은 hash slot을 강제하지 않으면 실패한다.
  - producer key 네이밍을 전면 변경하는 것보다 consumer를 단일 stream poll 방식으로 바꾸는 편이 운영 전환 리스크가 작다.
- 제외 범위:
  - `meeting:{meetingId}:feedback-source` / `feedback-result` key naming 계약은 변경하지 않았다.
  - STT relay 로직과 피드백 workflow 판정 규칙은 변경하지 않았다.
- 검증:
  - `python3 -m compileall app` 통과.
