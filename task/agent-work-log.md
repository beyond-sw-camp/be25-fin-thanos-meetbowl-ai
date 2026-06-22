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
