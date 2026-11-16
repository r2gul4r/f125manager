# AGENTS.md — F1 25 AI Race Engineer 개발 지침

이 문서는 개발 담당 Codex가 항상 따라야 할 작업 규칙이다. 자세한 명세는 `docs/MASTER_PLAN.md`, 진행 상황은 `TASKS.md`, 레퍼런스 감사는 `docs/REPO_AUDIT.md`를 사용한다.

## 1. 사용자와 합의한 결정: 바꾸지 말 것
- **Rust Core + PyO3/maturin + Python/FastAPI + React/TypeScript/Vite + SQLite/압축 원본**.
- **PySide6를 프런트로 사용하지 않는다.** 프런트는 F1 Live Timing 기반 React이며 기본 색은 차콜/검정/흰색/레드다. 예측과 실제 관측 시각표현 분리.
- 실시간 관측·갭·피트 시뮬레이션을 Rust에, 전략 정책·GP 상태·DB·Codex를 Python에, 렌더링을 React에 둔다.
- **그랑프리당 Codex 런타임 스레드 하나**. FP1~결승은 해당 스레드를 재개한다. 영구 기억은 DB/압축 파일에 저장한다.
- Codex/TTS 없이도 타이밍/레이스 수집/전략 규칙 엔진이 작동해야 한다.

## 2. 반드시 실행할 작업 절차
1. 매 작업 시작 시 `docs/MASTER_PLAN.md`, `TASKS.md`, `docs/REPO_AUDIT.md`를 확인한다.
2. 현재 Phase를 식별하고 범위를 최소화한다. **한 번에 모든 단계를 구현하지 않는다.**
3. 코드 작업 전 공식 문서/기존 저장소를 검토하고 실제로 확인한 사실과 추정을 나누어 적는다.
4. 새 패키지는 테스트된 버전과 라이선스를 확인하고 lockfile을 관리한다.
5. 변경에는 테스트와 실행/재현 방법이 따라야 한다. 기능 없는 스텁은 미완료라고 표시한다.
6. 각 단계가 끝나면 `TASKS.md` 체크박스, 변경 로그, 실행 스크립트, 실패 항목을 갱신한다.
7. 다음 단계가 현재 단계의 안정성과 충돌하면 먼저 알려주되, 독립적으로 가능한 작업은 수행한다.

## 3. 기존 저장소 활용 규칙
- Phase 0에서 반드시 저장소를 클론하여 실제 소스, README, 라이선스, 최신 커밋을 확인한다.
- 외부 코드 편입 시 `docs/THIRD_PARTY.md`에 출처 URL, SHA, 라이선스, 파일 및 수정 내역을 기록한다.
- 라이선스가 확인되지 않은 `ef-one-tv` 코드는 **복사 금지**. 기능 구조 참고만 가능.
- MIT 코드라도 저작권/라이선스 고지를 보존한다. 외부 F1 로고/상표/독점 폰트 등은 별도 권리 확인.
- README에 적혔어도 코드 테스트되지 않은 기능은 구현 완료라고 주장하지 않는다.
- 중복 서버 Go+Rust를 동시에 UDP 20777로 돌리는 구조를 만들지 않는다.

## 4. Rust 및 Python 안전·성능 원칙
- 비정상 길이/포맷의 UDP 데이터는 안전하게 거부하며 panic을 외부 입력으로 유도하지 않는다.
- Little Endian, packed 레이아웃 및 2025/2026 차이를 정확히 확인한다. 검증 없는 `transmute`/정렬 가정 금지.
- Rust 수신 스레드는 Python의 느린 쿼리, DB, LLM, 웹 브라우저를 기다리지 않는다.
- snapshot은 최신값 우선으로 갱신, 중요 이벤트는 별도 ordered queue와 ack/overflow 전략을 갖는다.
- UDP는 유실 가능하다. '무손실 보장'이라고 쓰지 말고 누락 추정치를 기록한다.
- FP/예선/결승, 재시작·플래시백, session UID 변경, 전송 중단·재연결 테스트 필수.
- 모든 수치에 단위, 기준 시점, 실제 관측 여부를 표시한다. 상대 비공개 데이터를 아는 척하지 않는다.
- 60Hz 모든 패킷을 React나 Codex에 직접 송신하지 않는다. 10~20Hz snapshot과 이벤트·전략 결과로 분리한다.

## 5. UI 원칙
- 1920×1080 서브모니터 우선, Live Timing 기본 62% + 전략 패널 38%.
- 차콜 `#111115`, `#17171c` / F1풍 빨강 `#e10600` / 흰색·회색. 일반 카드에 청색 네온·청색 그라디언트 금지.
- 보라/초록/노랑은 섹터 랩타임, 컴파운드/플래그는 의미색. 팀 컬러는 작은 라벨로 구분.
- 관측 vs 추정 vs 예측 라벨이 항상 보여야 한다. 예측 숫자는 사실처럼 표현 금지.
- live / mock / replay / stale / disconnected 상태 UI 제공.
- 게임이 없을 때도 `mock mode`의 UI가 동작해야 한다.

## 6. 데이터 / Codex 관리
- `gp_id`(전체 주말)와 F1의 `sessionUID`(개별 세션)는 다른 ID다.
- 데이터는 DB+원본 기록에 저장한다. Codex 스레드는 편의상 지속 컨텍스트이며 유일한 저장소가 아니다.
- 2026 시즌팩, 2025 포맷, AI 난이도, 레이스 거리, 규칙 설정을 보존해 모델 학습 데이터 혼합을 방지.
- `openai-codex`의 현재 공개 API를 확인해 `thread_start`/`thread_resume`를 사용한다.
- 런타임 Codex는 전략용 비필수 동작이며, 유효한 모델 출력만 검증 후 UI/DB에 반영한다.
- DB 읽기는 허용된 도구/쿼리로 제한하고 코드 실행이나 파일 쓰기 권한을 불필요하게 제공하지 않는다.
- 자격증명은 `.env`/OS 비밀 저장소에 두고 프런트, 로그, Git에 절대 포함하지 않는다.

## 7. 필수 검증 명령 (스크립트/환경 구현 후)
- `cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test`
- `python -m pytest` 및 Python 린트/타입 검사
- `npm run lint && npm run test && npm run build`
- mock UDP/replay E2E 및 Playwright UI 스모크 테스트
- Windows에서 PyO3/maturin 및 FastAPI 구동, 2025·2026 fixture 파싱 확인

## 8. 최종 보고 형식
매 Phase 완료 후 다음 항목을 간단히 보고한다.
- 구현 기능 및 커밋/파일 변경 내용
- 검증한 명령과 실제 테스트 결과
- 성능 수치가 있다면 측정 환경 및 방법
- 남은 위험/불확실성 및 차기 Phase
- 사용자 판단이 반드시 필요한 이슈만 질문
