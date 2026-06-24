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
