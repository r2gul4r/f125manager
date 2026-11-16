# TASKS.md — Phase별 개발 체크리스트

> 상태: 모두 미구현. `docs/MASTER_PLAN.md`의 단계별 설명과 완료 기준을 함께 읽는다. 각 단계의 [ ]는 테스트와 산출물 확인 후에만 [x]로 변경한다.

## Phase 0 — 레퍼런스 검증 및 채택 결정
- [ ] F1 Telemetry Go 저장소/라이선스/실행을 실제로 확인하고 UI 재사용 범위 결정
- [ ] f1-2026-telemetry 패킷 테스트와 EA 공식 2025/2026 규격 대조
- [ ] Lift and Coast 전략/AI 구조, Pitwall 시뮬레이션/백테스트 실제 코드 검토
- [ ] Race Engineer 및 ef-one-tv 코드 감사 및 라이선스 상태 기록
- [ ] Rust F1 25 crate의 2025/2026 지원 여부 확인
- [ ] docs/REPO_AUDIT.md, docs/THIRD_PARTY.md에 SHA, 파일별 선택 근거 작성
**Gate:** 검증된 직접 채택/참고/제외 목록 존재

## Phase 1 — 개발 기반
- [ ] Rust workspace + PyO3/maturin + Python/FastAPI + React/Vite/TS 구성
- [ ] Windows 실행 스크립트와 .env.example, 예외 처리, 포트 설정
- [ ] lint/typecheck/test/build 기본 명령 작동
- [ ] Mock WS→React Hello Live 테스트
**Gate:** 설치 후 F1 없이 health + UI가 실행

## Phase 2 — 파서
- [ ] UDP header 및 packet type + size + version validation
- [ ] 2025 주요 패킷 파서+fixture, 2026 별도 패킷 파서+fixture
- [ ] 패킷 잘림·에러·unknown version·malformed inputs 처리
- [ ] 공식/다른 구현과 크기/필드 값 교차 검증
**Gate:** 2025/2026 정상 패킷 구분 및 회귀 테스트

## Phase 3 — 수신·녹화·재생
- [ ] Tokio UDP 수신, 수신 지표, 비차단 파서 경로
- [ ] 원본 UDP+timestamp framing 및 zstd chunk 기록
- [ ] chunk index/checksum, 손상 파일 복구 동작
- [ ] 동일 기록 오프라인/가속 재생
**Gate:** 녹화→재생 파싱 결과 동일, 유실 추정 지표 표시

## Phase 4 — RaceState / Reducer
- [ ] 24대까지 차량/참가자·현재 순위·lap/sector/tyre/pit 상태 유지
- [ ] FP/Q/R 전환 및 UID/참가자 변경 처리
- [ ] flashback, 중복 패킷, 역순 패킷, reconnect, stale 필드 처리
- [ ] 이벤트 고유 ID/중복 제거/보존 큐 및 Replay 결정론 테스트
**Gate:** 동일 녹화 재생 시 동일 스냅샷/이벤트

## Phase 5 — Rust↔Python↔WebSocket
- [ ] PyO3 engine start/stop/snapshot/drain_events/metrics 구현
- [ ] FastAPI WS/REST, Pydantic 및 TS 스키마 계약
- [ ] 느린 WS 소비자, WS 재연결, Rust 엔진 독립 지속 테스트
**Gate:** Rust 데이터가 Python→React까지 자동 흐름

## Phase 6 — F1 Live Timing React UI
- [ ] 다크 차콜/레드 테마 토큰, 헤더/플래그, 타이밍 타워
- [ ] 전체 참가 차량(2025 22, 2026 24), 섹터색, 타이어, PIT 등
- [ ] 내 차/실질 경쟁 상대 강조 및 예측/관측 라벨
- [ ] Connection/Mock/Replay/No data 상태, 탭 구조 구현
- [ ] 1920x1080 보조모니터 테스트 및 유저 제공 디자인 비교
**Gate:** 게임 없어도 mock Live Timing 완성, 실측 연결 가능

## Phase 7 — GP 라이브러리
- [ ] DB migration/schema 및 데이터 저장·검색 repository
- [ ] 한 GP 아래 FP/예선/레이스/재시도 분류
- [ ] 랩/스틴트/피트/전략/예측/결정/이벤트/원본 파일 참조 저장
- [ ] History/Replay 화면 + GP 필터 + Export/Backup
**Gate:** 앱 재시작 이후 과거 GP 100% 재탐색·재생

## Phase 8 — 레이스 전 전략
- [ ] clean stint 선택, compound wear/pace model, 모델 데이터 품질
- [ ] 피트 손실·경기 길이·레이스 규칙 반영
- [ ] Plan A/B/C 시뮬레이션 + Python 정책 비교
- [ ] 전략 결정 DB 기록 + Strategy 탭
**Gate:** 실제/모의 FP 데이터로 설명 가능한 전략 추천

## Phase 9 — 상대 및 실질 순위 예측
- [ ] 갭/페이스 차이 기반 추격, DRS 진입/추월 구분
- [ ] 상대 다음 1/3/5랩 피트 가능성 모델 + 불확실성
- [ ] Net Position/Projected Finish + 몬테카를로, SC/VSC/우천 반영
- [ ] 예측 성능 리포트: MAE/Brier/calibration + baseline
- [ ] 모델의 미래 데이터 누수 방지 검증
**Gate:** 모의/저장된 GP에서 예측과 실제 결과 교차 검증

## Phase 10 — GP별 Codex
- [ ] Python SDK 인증/스레드 수명주기/timeout/retry 체계
- [ ] GP 시작 새 thread, FP~결승 동일 thread, 새 GP 별도 thread
- [ ] DB 기반 상태/기록 검색과 안전한 read-only tool 인터페이스
- [ ] 구조화된 전략 답변 + AI 실패 시 규칙 엔진 fallback
- [ ] Codex 결정을 자동 게임 제어 없이 사용자에게 제안/기록
**Gate:** GP A 재개와 GP B 새 스레드, 오프라인 모드 정상

## Phase 11 — 음성(후속)
- [ ] PTT(휠·키보드), STT/TTS 추상화, Radio FX 설정
- [ ] 주행 위험 구간 알림 제어/priority queue/중복 무전 억제
- [ ] 한 GP 내 대화와 선택 전략 기록, 화면 자막 병행
**Gate:** 음성 실패해도 모든 핵심 기능 유지

## Phase 12 — 성능·배포
- [ ] 실측 p50/p95/p99, 데이터 age, packet metrics, DB throughput
- [ ] 게임 병행 장시간 플레이/플래시백/중단 복구 테스트
- [ ] Windows 사용자 설치·실행·로그·백업 안내 및 패키징
- [ ] 회귀 테스트 문서/최종 릴리스 체크리스트
**Gate:** 사용자 환경에서 재현 가능한 측정/복구 절차
