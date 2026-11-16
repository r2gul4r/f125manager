# F1 25 AI Race Engineer — Codex 개발 마스터 계획서

> 작성 기준: 2026-11-12 / 대상: Windows PC에서 F1 25(+ 2026 Season Pack)를 플레이하는 개인용 프로젝트
> 상태: **설계안**. 기존 저장소 README의 기능 선언과 실제 코드 동작은 구별한다. 구현 시작 전 Phase 0에서 코드를 검증한다.

## 0. Codex에게 내리는 최상위 지시

당신은 이 프로젝트의 개발 담당자다. **기존 코드를 먼저 조사하여 재사용할 수 있는 기능을 검증한 뒤**, 아래 단계의 순서에 따라 구현한다. 일괄적으로 거대한 코드를 생성하지 말고 각 단계별로 코드·테스트·실행 방법·남은 위험을 제공한다. 사용자가 이미 확정한 기술 스택과 요구사항을 변경하지 말 것. 상세 작업 규칙은 루트 `AGENTS.md`, 세부 체크리스트는 `TASKS.md`, 처음 시작 지시는 `CODEX_START_PROMPT.md`를 따른다.

### 확정된 기술 스택

- **Rust:** 2025/2026 UDP 파싱, 실시간 차량 상태, 갭·미래 페이스·피트 시뮬레이션, 원본 패킷 기록/재생. Tokio 등은 현재 의존성 버전을 검사하여 채택.
- **PyO3 + maturin:** Python이 Rust 네이티브 엔진을 안전하게 호출하는 인터페이스. Rust의 UDP 루프는 Python/LLM/GUI 처리를 기다리지 않는다.
- **Python + FastAPI:** 전략 선택 컨트롤러, 설정, GP 세션 라이프사이클, DB, Codex SDK, WebSocket 및 REST API. 학습용 ML은 추후 여기에서 수행.
- **React + TypeScript + Vite:** F1 공식 Live Timing의 정보 구조와 어두운 팔레트를 참고한 **독자적인** 서브모니터용 피트월 UI. **PySide6는 사용하지 않는다.**
- **SQLite(WAL) + 압축 원본 텔레메트리 파일:** 모든 GP 기록 영구 보존. 테이블에는 인덱스·세션 메타데이터·요약·예측·판단 기록을 저장하며 고주파 원본 UDP는 압축 블록 파일로 저장하고 DB가 인덱싱한다.
- **Codex Python SDK (`openai-codex`):** **그랑프리 주말당 1개 스레드**를 생성하고 FP/예선/결승 동안 재사용. 실시간 필수 경고에는 Codex를 기다리지 않는다.
- **AI 음성/PTT:** 대시보드·전략 모델 구현 후 후속 단계. 첫 버전에서는 TTS를 요구하지 않는다.

### 최상위 아키텍처

```text
[F1 25 / 2026 Season Pack]
          | UDP (설정에서 2025 또는 2026, 최대 60Hz)
          v
[Rust Core: Receiver -> Versioned Parser -> RaceState -> Recorder]
          |                      |                   |
          |                      +--> Pace/Pit/Net Position Simulation
          |                      +--> Ordered Events / Replay
          v
[PyO3 boundary: latest snapshot, drain_events, run_simulation, stats]
          |
[Python FastAPI Orchestrator]
   +-- [Grand Prix Session Manager] -- [Codex per-GP Thread, later]
   +-- [Strategy Controller]         [SQLite Race Library]
   +-- [REST / WebSocket]            [compressed raw UDP files]
          |
[React/TypeScript Pit Wall: localhost -> secondary monitor]
   +-- Live Timing
   +-- Strategy
   +-- Telemetry/Practice
   +-- History/Replay
```

중요: Rust-Python은 **같은 프로세스의 PyO3 확장 모듈**로 시작한다. Python 프로세스가 죽으면 Rust 수신 루프도 종료될 수 있다. 이 한계를 허용한 MVP이며, 실제 장애 문제가 확인될 때에만 Rust 독립 프로세스+IPC로 이전한다.

## 1. 제품 목표 / 비목표

### 제품 목표
1. FP1~FP3/예선/결승의 모든 관측 가능한 차량 데이터를 안정적으로 수집·기록한다.
2. 서브모니터에 전체 참가 차량의 순위/갭/인터벌/섹터/랩타임/타이어/피트/플래그를 실시간 표시한다.
3. 연습 주행을 바탕으로 레이스 전 타이어·피트 전략 A/B/C를 계산한다.
4. 레이스 중 상대의 미래 페이스, DRS권 진입 예상, 실제 추월 가능성, 다음 피트 확률을 추정한다.
5. 실제 트랙 순위 / 피트 사이클 이후 실질 순위(Net) / 예상 최종 순위를 **서로 구분**한다.
6. 언더컷·오버컷, 재합류 트래픽, SC/VSC, 우천 변수 등을 반영한 전략 시나리오를 비교한다.
7. 운전자가 선택한 플랜, 예측과 실제 결과, AI와 나눈 대화를 GP별로 저장하고 다음 GP에서 재검색한다.
8. 후속 단계에서 Codex와 팀라디오를 붙이되 실시간 수신과 예측은 모델 응답으로 블로킹하지 않는다.

### 이번 MVP의 비목표
- 실제 F1 팀의 비공개 전략 및 F1 25 상대의 **미래 확정 피트 랩**을 알아내는 기능은 없다. 예측 확률만 제공.
- F1 게임 UDP는 텔레메트리 **출력**이다. 게임의 피트 명령/타이어 선택을 UDP로 직접 변경한다고 가정하지 않는다.
- 60Hz 모든 화면 애니메이션, TTS 및 보노 목소리 구현, 상용화, 온라인 서버 배포는 MVP 밖.
- 게임 내부 모딩, 비공개 데이터 획득, 안티치트 우회는 범위 밖.

## 2. 기존 프로젝트 감사 및 재사용 결정 (Phase 0 선행)

아래의 기능 설명은 공개 저장소 문서 기준이다. **실제로 동작하는지, 파일별 라이선스와 API 안정성은 직접 점검해야 한다.** 특정 저장소를 통째로 기반으로 삼기보다는 핵심 설계와 개별 모듈을 선택적으로 채택한다. 모든 외부 코드 도입 시 저장소 URL, pinned commit SHA, 라이선스, 복사 파일, 수정사항을 `docs/THIRD_PARTY.md`에 기록한다.

| 프로젝트 | 저장소 | 확인된 역할 / 활용 방침 | 주의 |
|---|---|---|---|
| **F1 Telemetry Go** | https://github.com/mgauna-ar/f1game-telemetry-go | **가장 우선 참고**. Go 백엔드·React 타이밍 타워/피트월/레이스 기록/AI UI의 정보 구조를 분석. MIT 라이선스 확인. 프런트 컴포넌트는 의존성·라이선스 점검 후 일부 재사용 가능 | Go 서버를 실서비스에 그대로 함께 띄우지 않는다. 포트 20777 중복 점유 금지. README와 동작 일치 검증 |
| **Sim Racing Studio 2026 Parser** | https://github.com/simracingstudio/f1-2026-telemetry | **2026 Rust 파서 검증용 기준**. 2026 패킷 구조·크기 테스트·예시를 활용. MIT | Python 구현을 그대로 실시간 파서로 운용하지 않고 Rust 구현과 교차검증 |
| **EA 공식 UDP 규격** | https://forums.ea.com/blog/f1-games-game-info-hub-en/ea-sports%E2%84%A2-f1%C2%AE25-2026-season-pack-udp-specification/12187347 | 2025/2026 바이너리 구조의 **1차 진실원**. 현재 규격의 버전 및 시즌 업데이트 확인 | 게임의 UDP 설정과 실제 헤더를 기준으로 포맷 분기. 실제 녹화 패킷으로 검증 |
| **Lift and Coast** | https://github.com/MartianRiver/lift-and-coast | MIT. 피트월 전략, AI 이벤트·상태·요약·무전 트리거 구조 참고. 일부 Python 모듈은 적합성 확인 후 채택 | LLM 음성 런타임 의존성, 지원 OS, 빠른 경고와 전략 계산 분리 검증 |
| **Pitwall** | https://github.com/Ark07Yad/pitwall | MIT. 몬테카를로 피트 전략, 재합류/추월/SC 모델, 백테스트·사전 예측 로그 원칙 재사용 | 실제 F1 라이브 피드용. F1 25에 수치/확률을 그대로 적용 금지. 게임에서 재보정 |
| **Race Engineer** | https://github.com/iamtushar324/race-engineer | MIT. 기존 REST/WS 계약, CommsGate, 이벤트 중복제거 및 Mock 모드 구조 참고 | Go 중심 앱. Rust 백엔드와 중복 실행하지 않고 API 설계만 비교 |
| **ef-one-tv** | https://github.com/d3jn/ef-one-tv | 2026 포맷 상태 합성·예상 피트 재합류·원본 리플레이 아이디어 참고 | 저장소 루트에서 명시적 LICENSE를 확인하지 못함. **라이선스 확인 전 복사·수정·편입 금지** |
| **Rust f1-game-library-models-25** | https://docs.rs/f1-game-library-models-25/latest/f1_game_library_models_25/ | 2025 파서의 적용 가능성 및 Rust zero-copy 파싱 구조 평가 | **2026 지원 확인 안 됨**. 2026 파서는 공식 규격을 기반으로 별도 구현·테스트 필요 |
| **OpenAI Codex Python SDK** | https://github.com/openai/codex/tree/main/sdk/python | `openai-codex`, `thread_start` / `thread_resume`로 GP 단위 스레드 유지 | 원격 모델 지연·비용·연결 실패 고려. 읽기 중심, 샌드박스 사용, 모델 미응답이어도 레이스 기능 유지 |

### Phase 0 감사 작업 (구현보다 먼저)
- 저장소를 로컬의 `references/` 하위에 **별도 클론**하되 애플리케이션 저장소의 실행 의존성과 분리한다.
- README, LICENSE, 실제 소스, 테스트, 릴리스, 마지막 커밋, 2026 포맷 지원, 입력/출력 계약을 검사한다.
- `F1 Telemetry Go`의 모의 레이스/화면을 실행해 UI와 기능별로 스크린샷 및 재사용 후보 목록을 만든다. 우리 서비스와 동시에 UDP 바인딩하지 않는다.
- 각 프로젝트에서 **직접 채택 / 구현 방식 참고 / 제외**를 결정하고 `docs/THIRD_PARTY.md`에 이유를 기록한다.
- 저장소 설명만으로 확인되지 않은 기능은 '미검증'으로 표기한다. 작은 프로젝트의 완성도/지연 성능을 추정하지 않는다.
- `docs/REPO_AUDIT.md`에 실제 검사한 파일 경로, commit SHA, 재사용 조건, 검증 결과를 남긴다.

## 3. 기능 책임 경계

### Rust = 관측 사실과 반복 가능한 계산
- 단일 UDP 소켓 관리(포트 기본값 20777), 바이너리 검증, 포맷 2025/2026 구분, 큐·버퍼·수신 통계.
- SessionUID, `frameIdentifier`, `overallFrameIdentifier`, 시간, 차량 인덱스, 선수 식별, 타이어/피트/순위 등 최신 RaceState 관리.
- 패킷 누락·중복·역순, 플래시백/재시작 탐지. **UDP의 패킷 유실 0 보장은 불가능**하므로 누락을 계측한다.
- 실시간 갭·인터벌·클린랩 추세, 경고용 이벤트, 상대 추격 예측, 전략 시뮬레이션의 결정론적 계산.
- 원본 패킷 비동기 기록 및 정확한 오프라인 리플레이. 최신 스냅샷과 이벤트 순차 큐를 분리한다.
- 시뮬레이션에 필요한 학습된 파라미터는 Python에서 전달받되 Python 호출/모델 응답을 기다리며 UDP 수신을 멈추지 않는다.

### Python = 전략 정책·기억·시스템 통합
- 현재 GP와 하위 세션(FP1~결승)의 수명주기 및 설정 관리.
- Rust가 반환한 여러 시나리오를 목표 순위/위험 성향/유저 전략 선택에 따라 평가하여 추천.
- `SQLite` 라이브러리·검색·통계·학습용 데이터셋·모델 버전 및 분석 로그 관리.
- FastAPI REST/WS로 React에 전달. 새로운 데이터가 와도 UI는 자기 속도로 렌더한다.
- 향후 Codex GP 스레드 및 구조화된 질문·답변, 알림 우선순위, STT/TTS 어댑터 담당.

### React = 표시와 가벼운 상호작용
- 계산 모델을 소유하거나 재구현하지 않는다. 실제 관측과 예측을 서로 다른 UI 표현으로 구분.
- 10~20Hz 스냅샷 렌더링, 이벤트 피드, 설정/탭 전환, GP 히스토리 탐색, 전략 A/B/C 비교.
- 자체 차트 계산·복잡한 예측은 서버에 위임한다. 부하가 큰 시계열은 다운샘플 후 Canvas 기반 차트 활용.

## 4. 데이터 계약 및 레이스 상태 설계

### 핵심 원칙
- Rust 원본 데이터는 `sessionUID`(문자열/hex로 보관), `frame_id`, `overall_frame_id`, `packet_format`, `packet_id`, 수신 시각을 함께 저장.
- `sessionUID`는 게임의 세션 식별자, `gp_id`는 우리 시스템의 **FP~결승 전체 그랑프리 식별자**다. 둘을 혼동하지 않는다.
- 경기 재시작, 같은 트랙 재방문, 동일 GP의 추가 시도는 각각 별도 `session_attempt_id`를 갖는다.
- 플레이어·상대의 일부 데이터는 비공개이거나 결측일 수 있다. `null`, 수집 시각, 출처 및 신뢰도와 함께 전송하고 임의 숫자로 보정하지 않는다.
- 측정(`observed`), 추정(`estimated`), 예측(`predicted`)에 다른 태그와 색/툴팁을 부여한다.
- 단위는 SI로 정규화(초, m, °C 등)하고 frontend에서 보기 좋게 출력한다. 주행 위치 거리와 시간 격차를 임의 동일시하지 않는다.

### Rust↔Python 제안 API (구현 전 확정할 계약)

```python
engine = race_core.RaceEngine(config)
engine.start_udp()                 # Rust 백그라운드 수신 시작
snapshot = engine.get_snapshot()   # 최신 완성 상태 하나
for event in engine.drain_events(max_items=200):
    handle_event(event)            # 보존·중복제거 가능한 이벤트
metrics = engine.get_metrics()     # packet loss proxy, decode latency, queue depths
prediction = engine.predict_rival(car_id, horizon_laps=10)
scenarios = engine.simulate_strategies(request)
engine.stop()
```

- 실제 PyO3 API는 동작 시험 후 결정. `get_snapshot()`은 무거운 Python 객체를 매 패킷 생성하지 않도록 **UI 주기에 맞춰** 호출.
- 이벤트는 고유 `event_id`와 monotonic ordering을 갖고, Python이 ack 한 뒤 제거할 수 있도록 설계한다. 큐 초과 시 디스크 spool 또는 유실 지표를 기록한다.
- snapshot에는 `as_of_frame`, `collected_at`, `stale_ms`, `packet_format`, `session_uid`, `cars[]`, `flags`, `weather`, `pit_window` 등을 포함한다.
- prediction에는 `as_of_frame`, `model_version`, `input_data_quality`, `prediction_window`, `confidence`, `assumptions`, `source`를 항상 포함한다.

### HTTP 및 WebSocket 계약(초기안)

| 인터페이스 | 내용 |
|---|---|
| `GET /api/health` | Rust 수신 및 DB/WS 건강 상태 |
| `GET /api/live/snapshot` | 최신 관측 스냅샷 |
| `GET /api/gps` / `POST /api/gps` | GP 생성/목록 |
| `GET /api/gps/{id}` | GP 메타데이터/하위 세션 |
| `GET /api/gps/{id}/sessions` | FP, Qualifying, Race 등 |
| `GET /api/gps/{id}/laps` | 필터·페이지네이션된 랩 |
| `GET /api/gps/{id}/predictions` | 누적 예측 및 검증 결과 |
| `POST /api/strategy/evaluate` | Rust 전략 시뮬레이션 실행 |
| `POST /api/strategy/commit` | 사용자의 전략 선택을 DB에 기록 |
| `GET /api/history/similar` | 조건 일치 과거 GP 검색 |
| `WS /ws/live` | `race.snapshot`, `race.event`, `prediction.updated`, `strategy.updated`, `connection.status` |

- 외부 네트워크 접근은 기본적으로 금지하며 `127.0.0.1`에 바인딩. 개발·테스트 외에는 브라우저에서 Python 코드 실행 등 위험한 권한을 노출하지 않는다.
- OpenAPI/Pydantic 스키마에서 TypeScript 타입을 생성하거나 공통 `contracts/`에 JSON Schema를 유지해 형태 드리프트를 방지한다.

## 5. 데이터베이스 & 파일 저장 설계

SQLite는 WAL 모드, foreign key ON, 명시적 마이그레이션을 사용한다. DB 저장 책임은 Python의 단일 repository/service 계층으로 일원화하고, Rust Recorder는 원본 파일을 원자적으로 완성한 뒤 색인용 메타데이터를 전달한다.

| 테이블 | 주요 필드/역할 |
|---|---|
| `grand_prix` | id, season, track, event_date, game_build, regulation, race_length, ai_difficulty, codex_thread_id, status |
| `sessions` | id, gp_id, game_session_uid_hex, type(FP/Q/R), weather, settings, attempt, started/ended |
| `participants` | session_id, car_index, driver_id, team, car_number, is_player, privacy |
| `laps` | session_id, participant_id, lap_no, lap_time_ms, sectors_ms, valid, conditions |
| `stints` | session_id, participant_id, compound, start/end laps, observed wear, degradation_fit |
| `pit_stops` | session_id, participant_id, in/out lap, loss_s, compound_before/after |
| `race_events` | stable event_id, session_id, frame_id, type, payload, observed_at |
| `predictions` | id, session_id, frame_id, target_car, kind, model_version, result_json, assumptions, predicted_at |
| `prediction_outcomes` | prediction_id, realized_value, error, evaluation_method |
| `strategies` | id, session_id, plan_name, stops_json, simulation_json, status, version |
| `strategy_decisions` | strategy_id, event_id, recommended, selected, reason, timestamp, source |
| `codex_interactions` | gp_id, thread_id, turn_id, prompt_summary, response_json, token_usage, model, timestamp |
| `race_library` / `driver_profiles` | 서킷/설정별 요약, 사용자 주행 특성·기록 검색 인덱스 |
| `telemetry_chunks` | session_id, start/end frame, filename, bytes, checksum, schema_version |
| `model_registry` | 모델 이름, 버전, 학습 데이터 필터, 검증 점수, artifact path |

- 원본 UDP는 `data/gps/<gp_id>/<session_id>/raw/part-NNN.f1raw.zst` 식으로 보관. **이것은 우리가 정의하는 자체 포맷**이며, 헤더에 version, len, monotonic rx timestamp, UDP payload를 저장한다.
- 중간에 종료되더라도 복구 가능하도록 `.tmp` → flush/fsync → atomic rename 후 DB 인덱스 커밋을 검토한다.
- 데이터 보존 목표는 원본/예측/대화/전략을 모두 보존하는 것. 파일 누락 탐지·백업·용량 관리·Export ZIP을 제공한다.
- 예측 모델 학습에 미래 결과가 유입되지 않도록 예측 시각 기준 특성만 사용하고, 모델 버전을 함께 기록한다.

## 6. UI/UX — F1 Live Timing 스타일, F1 피트월 기능 추가

### 시각 디자인
- **매우 어두운 배경** `#111115 / #17171c`, 패널 `#202025`, 기본 글자 `#f1f1f1`, 보조 회색 `#99999f`, **주요 포인트 레드** `#e10600`.
- 섹터/랩 기록: 보라(전체 최고), 초록(개인 최고), 노랑(기록 있음/비최고). 타이어 색: Soft 빨강, Medium 노랑, Hard 흰색, Intermediate 초록, Wet 파랑 등 **타이어/플래그의 의미색은 예외**.
- **일반 UI 요소에 임의의 청색 그라디언트, 네온 블루 카드 사용 금지.** 팀별 식별색은 작은 사이드 바/레이블에만 사용.
- 실제 F1 Live Timing의 정보 구조는 참고하되 브랜드 로고, 독점 이미지, 폰트 파일을 그대로 패키징하지 않는다.
- 1920×1080 보조모니터 우선, 2560×1440 및 작은 화면에서는 컬럼 숨김·스크롤 가능한 반응형 구성.

### 기본 레이아웃

```text
┌──────────────────────────────────────────────────────────────────────┐
│ GRAND PRIX / SESSION   LAP 18/58     FLAGS   TRACK TEMP   CONNECTED │
├───────────────────────────────────┬──────────────────────────────────┤
│ LIVE TIMING (약 62%)             │ AI STRATEGY PIT WALL (약 38%)     │
│ POS | DRIVER | INT | GAP | LAP    │ TRACK P / NET P / PROJECTED P    │
│ S1 S2 S3 | TYRE | AGE | PIT       │ PLAN A/B/C, NEXT BOX WINDOW      │
│ 모든 차량 (2025:22/2026:24 대응)  │ RIVAL CATCH, PIT PROB., TRAFFIC │
│                                  │ ENGINEER EVENT/RECOMMENDATION   │
├───────────────────────────────────┴──────────────────────────────────┤
│ RACE CONTROL / PIT / FLAG / MODEL EVENTS                            │
└──────────────────────────────────────────────────────────────────────┘
```

### 필수 화면
1. `LIVE`: 전체 차량 라이브 타이밍, 내 차 강조, 주요 경쟁 차량 고정, 관측 vs 예측 라벨.
2. `STRATEGY`: 타이어 스틴트 그래프, Plan A/B/C 비교, 피트 후 재합류 위치, 타이어/피트 윈도우(추정 범위 포함).
3. `TELEMETRY`: 연습 주행 속도/스로틀/브레이크/ERS/타이어/섹터 추세, 클린랩 비교.
4. `LIBRARY`: GP→세션→스틴트→랩→전략·결정·예측 오차 탐색, 검색/필터/재생.
5. `SETTINGS/DIAGNOSTICS`: UDP 포맷/속도, 패킷 손실 추정, Codex 연결 상태, UI/저장 상태.

UI는 게임이 없는 상태에서도 JSON fixture/mock으로 항상 실행 가능해야 한다. 기본 화면은 임의의 F1 운전자 실명이나 팀 데이터를 하드코딩하지 않으며, fixture는 명시적으로 `demo` 배지를 표시한다.

## 7. 전략 엔진 명세

### (A) 레이스 전 기본 전략
- FP 데이터에서 클린랩을 선별하고 컴파운드별 평균 페이스, 열화 기울기, 온도, 연료 감소 효과와 불확실성을 분리한다.
- 서킷별 피트레인 시간 손실을 실측하거나 설정값으로 제공한다. 날씨, 타이어 규칙, 레이스 길이, 안전차 변수 반영.
- 최소 샘플이 없으면 **낮은 신뢰도 + 기본 전략**을 제공하고 확신하는 문구를 사용하지 않는다.
- Plan A/B/C의 피트 랩, 컴파운드, 기대 레이스 타임, 추정 순위, 리스크를 비교한다.

### (B) 실시간 갭 및 추격/추월 예측
- 게임이 제공하는 시간 갭/인터벌을 우선 사용하고, 없는 경우 주행 거리와 최근 페이스로 재구성하되 정확도 수준을 낮춘다.
- 최근 n랩의 클린 에어 페이스·타이어 열화·DRS 영향·트래픽을 고려하여 랩별 갭 분포를 업데이트한다.
- **DRS 범위 진입 예상 랩**과 **실제 추월 성공 가능성**을 구분한다. 단순히 갭이 0이 된다고 추월로 간주하지 않는다.
- 상대 또는 자신이 피트/SC/우천으로 조건이 바뀌면 이전 예측을 무효화하고 새 버전으로 계산한다.

### (C) 상대 피트 예측
- 공개된 타이어 컴파운드·스틴트 길이·최근 페이스·남은 거리·위치·SC를 입력해 `P(pit in next 1/3/5 laps)` 및 예상 랩 구간을 계산한다.
- **정답 피트 랩은 제공되지 않음**을 UI에 명시. 기본 규칙 모델에서 시작하여 `XGBoost` 등은 충분한 게임 기록이 모였을 때만 학습한다.
- 게임 AI 난이도, 레이스 거리, 2025/2026 시즌팩, 트랙·차량 성능 등 환경 차이를 피처로 보존한다.

### (D) Net Position / Projected Finish
- `Track Position`: 실제 트랙 순위 (관측).
- `Net Position`: 상대 남은 스톱 정책을 포함한 **피트 사이클 정리 이후**의 예상 순위 (시뮬레이션).
- `Projected Finish`: 남은 전체 레이스에서의 예상 순위 분포 (시뮬레이션).
- Monte Carlo에서 피트 타이밍/컴파운드, 타이어 열화, 피트 손실, 교통, SC/VSC, 추월 난이도를 샘플링하고 결과 분포를 제시한다.
- 예측 확률은 반드시 calibration/backtest로 검증하며, 데이터가 부족하면 순위 **범위**만 출력할 수 있다.

### (E) 전략 의사결정
- Rust는 대안들을 평가하고 숫자/가정을 반환한다. Python 정책 엔진은 `safe / balanced / attack` 선호도에 따라 추천을 고른다.
- AI가 추천한 전략과 운전자가 최종 선택한 전략은 다르다. `proposed → committed → superseded/completed` 상태를 기록한다.
- 단기 무전 트리거: 피트 윈도우 접근, 상대 피트, SC/VSC, 날씨 변화, 클리어 에어 상실/획득, 목표 순위 변화.
- 규칙 기반 임계치·쿨다운·중복제거를 먼저 구현하고, 나중에 LLM으로 자연어로 설명한다.

## 8. GP별 Codex 세션 + 장기 기억 설계

**코덱스 개발 에이전트**와 **앱 안의 코덱스 전략 에이전트**는 별개다.

- `grand_prix.id` 생성 시, 활성 AI 옵션이 켜져 있다면 공식 **Codex Python SDK**로 신규 `thread_start(...)` 호출. 반환된 thread ID를 DB에 기록한다.
- FP1, FP2, FP3, Qualifying, Race는 같은 GP 스레드를 `thread_resume(thread_id)`하여 이어간다.
- GP 종료 시 최종 보고서, 예측과 실제 결과 비교, 전략 결정 이력을 DB에 저장한다. 다음 GP는 새 스레드를 생성한다.
- 과거 GP 기록은 매번 전체를 컨텍스트에 넣지 않는다. 현재 서킷·조건과 유사한 과거 GP의 **검색된 요약 및 근거 레코드**만 함께 제공한다.
- 사용자 음성 질문은 Python `Race Manager`가 구조화된 현재 상황(시점/차량/시나리오)을 주고 읽기용 도구(`get_current_race`, `get_strategy_options`, `get_similar_gps`, `get_prediction_evidence`)를 통해 응답하게 한다.
- Codex 응답은 JSON Schema로 구조화(`intent`, `summary`, `recommendation`, `evidence_ids`, `confidence`, `expiry_frame`)하고 검증 실패 시 재시도/규칙 기반 응답으로 대체한다.
- Codex에게 게임/DB 전체 파일 시스템의 쓰기·명령 실행 권한을 불필요하게 제공하지 않는다. 비신뢰 텔레메트리/외부 데이터는 프롬프트 지시가 아닌 **데이터**로 취급한다.
- 응답 지연, 계정 로그인·이용 제한, 네트워크 실패, 모델 응답 장시간 대기는 정상 실패 경로로 다룬다. **실시간 피트 경고는 Codex 없이 계산/표시 가능해야 한다.**

## 9. 단계별 구현 로드맵 및 완료 조건

> 단계별 완료 조건을 만족한 다음 단계로 넘어간다. `TASKS.md`의 체크박스와 매 단계의 회귀 테스트를 갱신한다.

### Phase 0 — 레퍼런스 감사/라이선스 검증
- **작업:** 위 오픈소스 클론·코드 구조·테스트·실제 모의 실행·라이선스·commit SHA 기록.
- **산출물:** `docs/REPO_AUDIT.md`, `docs/THIRD_PARTY.md`, 채택 결정 표, 재사용 후보 파일 목록.
- **완료 조건:** 최소 F1 Telemetry Go, f1-2026-telemetry, Lift and Coast, Pitwall의 재사용/제외 근거가 코드 기반으로 기록.

### Phase 1 — 모노레포·빌드 기반
- **작업:** Rust 크레이트 + PyO3/maturin + Python uv/venv + FastAPI + React/Vite/TS + 테스트/린트/CI 초기화.
- **산출물:** 모듈 임포트·API health·React 정적 화면·한 명령 실행 스크립트.
- **완료 조건:** Windows 개발 환경에서 원클릭(스크립트) 실행, `cargo test`, `pytest`, `npm test` 성공.

### Phase 2 — 버전별 UDP 파서
- **작업:** EA 2025/2026 헤더/주요 패킷 파싱. packet length/format/id 검증, f1-2026-telemetry와 fixture 교차 검증.
- **산출물:** Rust parser, 패킷별 fixtures, 구조체/문서.
- **완료 조건:** 정상/잘림/알 수 없는 포맷/역순/중복 테스트 통과. 2025, 2026 인식 구분 명확.

### Phase 3 — Rust 수신기·레코더·리플레이
- **작업:** 비차단 수신, 종료·예외 처리, raw chunk 기록, 동일 속도/가속 재생, packet metrics.
- **산출물:** `start_udp`, `stop`, recorder/replay CLI 또는 테스트 harness.
- **완료 조건:** 모의 60Hz 데이터 장시간 리플레이 시 무의도적 샘플 드롭 없음, 누락·순서·손상 통계 측정. **UDP 유실 0 보장 표현 금지**.

### Phase 4 — RaceState·이벤트
- **작업:** 차량 매핑, FP/Q/R 세션 전환, 타이어/피트/섹터, session UID, 플래시백·재시작 및 stale 상태.
- **산출물:** 최신 레이스 스냅샷, 순서 보존 이벤트, 세션 전환 reducer 테스트.
- **완료 조건:** 2025 22대/2026 24대 대응. 같은 기록 재생 시 같은 상태·이벤트 반환.

### Phase 5 — PyO3/FastAPI 통합
- **작업:** Rust 백그라운드 엔진 Python 바인딩, `/api/*`, `/ws/live`, health/metrics, 프로세스 종료.
- **산출물:** 타입 계약/샘플 JSON, 간단한 WebSocket 테스트 클라이언트.
- **완료 조건:** Python 요청·느린 UI·WS 연결 실패가 Rust UDP 루프를 막지 않음. 잘못된 모델 요청 실패 격리.

### Phase 6 — React Live Timing 1차
- **작업:** F1 스타일 디자인 토큰, 타이밍 타워, 헤더·플래그·타이어·섹터·레이스 이벤트, 연결/오류/데모 상태.
- **산출물:** 1920×1080 기준 Live 탭, 목 데이터·실시간 데이터 전환.
- **완료 조건:** 임의 청색 강조 없이 차콜·레드 기반. 2026 24대 표시. 10~20Hz 안정 갱신, 새 경기/재연결 정상.

### Phase 7 — 영구 GP 라이브러리
- **작업:** 위 DB 스키마/마이그레이션, GP·하위 세션 생성/검색, 파일 인덱스, 세션 요약, History/Replay UI.
- **산출물:** SQLite + raw 패킷 파일 + 동일 세션 복구 + 백업/Export.
- **완료 조건:** GP 종료·앱 재실행 후 랩·피트·전략·예측·원본 패킷 모두 조회 가능. 다른 GP와 데이터 혼합 없음.

### Phase 8 — 프리레이스 전략 엔진
- **작업:** 연습 스틴트 필터링, 컴파운드 열화 추정, 피트 비용, A/B/C 전략 비교, 낮은 데이터 신뢰도 처리.
- **산출물:** Rust 전략 시뮬레이터, Python 정책 선택, Strategy 탭.
- **완료 조건:** 동일 입력→동일 결과, 타이어/레이스 거리/피트 비용 변화에 상식적인 반응, 계획/선택 DB 기록.

### Phase 9 — 상대/순위 미래 예측
- **작업:** 상대 추격·DRS·추월 가능성, 상대 피트 확률, 언더컷/오버컷, Net/Projected Position, Monte Carlo.
- **산출물:** 예측 신뢰도/버전/전제 조건, Rival 패널, Backtest CLI.
- **완료 조건:** PIT/SC/VSC/우천/플래시백에 이전 예측 무효화. 과거 데이터를 예측 시점 이전으로 제한. 베이스라인과 정확도 비교.

### Phase 10 — GP별 Codex 전략 대화
- **작업:** `openai-codex` 인증/스레드 생성·재개/세션 복구/구조화 출력, 제한된 데이터 조회 함수, 대화 로그.
- **산출물:** GP당 1 thread, FP→결승 컨텍스트 유지, 저장된 분석 사건만 조회, Codex 비활성 모드.
- **완료 조건:** GP A 재개 시 같은 thread, GP B 새 thread. Codex 실패 시 대시보드/전략 계산 지속. 대화·결정 DB 보존.

### Phase 11 — 음성/PTT (후속)
- **작업:** GT ONE/키보드 PTT, STT, 교체 가능한 TTS, 우선순위 및 무전 중복제거, 짧은 정형 무전 캐시.
- **산출물:** 데이터 기반 양방향 팀라디오 및 자동 이벤트 음성.
- **완료 조건:** LLM 응답 중에도 Rust/React 동작. 음성 없이도 동일한 판단·로그 제공.

### Phase 12 — 운영 품질·최적화·패키징
- **작업:** 기록 재생 성능 비교, 장시간 안정성, 게임+대시보드 CPU/GPU 영향 분석, 백업/복구, 빌드·배포 정리.
- **산출물:** 성능 리포트, Windows 설치/실행 스크립트, 오류·유실 분석, 릴리스 문서.
- **완료 조건:** 측정 로그와 실패 복구 시나리오가 문서화되며 기능별 회귀 테스트 통과.

## 10. 품질 기준(초기 목표값, 실측 결과 아님)

- `UDP`: 설정 60Hz 스트림을 수신·기록할 수 있어야 함. 원래 게임이 실제로 전송하는 패킷 종류별 주기는 서로 다를 수 있다.
- `Rust decoder+RaceState`: 사용자 PC에서 **p99 5ms 이내 목표**. 초과 시 로그와 프로파일링, 목표 조정 근거 기록.
- `UI`: 최신 관측값 10~20회/초 표시, **p95 데이터 age 150ms 이내 목표**(로컬/정상 게임 전제). React 불필요한 전체 리렌더링 금지.
- `전략 시뮬레이션`: 일반 이벤트 발생 후 **1초 이내 첫 추천 목표**, 복잡한 확률분포는 추가 계산 허용. UDP 수신은 계속 진행.
- `DB`: 세션 종료 후 모든 중요 이벤트와 예측 로그가 존재하고, 원본 chunk checksum 일치.
- `예측 품질`: 피트 예측 절대 오차(MAE), DRS권 도달 예측 MAE, 순위 예측 MAE, 확률 예측 Brier score 및 calibration을 단순 베이스라인과 비교.
- `테스트`: parser fixtures, property/fuzz, reducer replay determinism, DB migrations, HTTP/WS 계약, Playwright mock UI, 2025/2026 회귀 테스트.
- **절대 표현 금지:** 미검증 성능 수치, 100% 패킷 무손실, 상대의 확정 피트 예정 랩, 비공개 데이터 실측.

## 11. 추천 개발 순서와 첫 결과물

1. **참고 프로젝트 감사부터** 하되, 참고 저장소를 합쳐 거대한 코드를 만들지 말 것.
2. 프로젝트 뼈대와 목 데이터 기반 React Live Timing을 빨리 구성하여 디자인을 확인한다.
3. Rust 2026 UDP 파서+recorder+replay를 구현하고 **모의 레이스**로 검증한다.
4. 실제 F1 25 UDP를 기록한 뒤 WebSocket으로 실측 정보를 띄운다.
5. GP별 영구 라이브러리와 Replay를 만든다.
6. 그 후 예측과 Codex, 마지막으로 TTS를 붙인다.

**첫 번째 제품 수준의 완료 기준:** 게임을 켜면 서브모니터에 전체 차량 Live Timing이 나오고, GP/세션/랩/타이어/피트/이벤트가 영구 저장되며, 게임을 끈 뒤 같은 기록을 재생할 수 있다. 아직 LLM/TTS는 필요 없다.

## 12. 최초 실행 전 사용자가 직접 확인할 것

- Windows / Rust toolchain / Python / Node.js 설치, 필요 시 MSVC Build Tools 및 maturin.
- 게임 설정: UDP ON, `127.0.0.1:20777`, 포맷 `2025` 또는 `2026`(시즌팩 사용 시), 속도 20~60Hz 중 테스트 대상 명시.
- **같은 UDP 포트에 다른 프로그램이 먼저 바인딩하지 않도록** SimHub/F1 Telemetry Go 실행 상태 확인.
- Codex SDK 인증/요금·이용 한도는 Phase 10에서 별도 검증. 앱이 토큰/자격증명을 프런트로 내보내면 안 된다.
- 기존 오픈소스의 각 LICENSE, 서브라이선스, 서드파티 폰트/이미지 별도 점검.

## 13. 중요한 기술적 결정 기록(ADR)

1. **ADR-001:** 초기엔 Rust + PyO3 + Python + React. 다른 언어로 갈아타는 건 측정된 병목이나 유지보수 이득이 있을 때만.
2. **ADR-002:** Rust는 실시간 '사실/계산'의 원천, Python은 전략 정책/DB/AI, React는 화면. 같은 로직 중복 금지.
3. **ADR-003:** Codex는 GP당 1스레드, 모든 기록의 실제 영구 원본은 DB·파일. Codex 대화 메모리를 DB로 간주하지 않음.
4. **ADR-004:** 2025/2026 패킷 파서 각각 테스트. 스키마가 다르면 억지로 필드를 채우지 않음.
5. **ADR-005:** 외부 소스는 커밋·라이선스를 고정하고, 라이선스 불명확한 저장소에서 복사하지 않음.
6. **ADR-006:** 기본 사용자 경험은 F1 Live Timing의 차콜·레드 정보 배치. 브랜드 자산 무단 패키징은 피함.
7. **ADR-007:** 예측·추천에는 항상 근거 시점, 모델 버전, 관측/추정 분류, 실패 조건을 남김.

---

## 검증한 주요 출처(계획서 작성 시점)

- EA 공식 F1 25 / 2026 UDP 스펙: https://forums.ea.com/blog/f1-games-game-info-hub-en/ea-sports%E2%84%A2-f1%C2%AE25-2026-season-pack-udp-specification/12187347
- F1 Telemetry Go (MIT): https://github.com/mgauna-ar/f1game-telemetry-go
- F1 2026 Parser (MIT): https://github.com/simracingstudio/f1-2026-telemetry
- Lift and Coast (MIT): https://github.com/MartianRiver/lift-and-coast
- Pitwall (MIT): https://github.com/Ark07Yad/pitwall
- Race Engineer (MIT): https://github.com/iamtushar324/race-engineer
- ef-one-tv (라이선스 확인 전 코드 복사 금지): https://github.com/d3jn/ef-one-tv
- Rust F1 25 라이브러리: https://docs.rs/f1-game-library-models-25/latest/f1_game_library_models_25/
- Codex Python SDK: https://github.com/openai/codex/blob/main/sdk/python/README.md
- PyO3: https://pyo3.rs/
- FastAPI WebSocket: https://fastapi.tiangolo.com/reference/websockets/

**참고:** 모든 기능 선언을 코드 실행으로 검증한 것은 아니다. 이 계획서의 Phase 0에서 실제 채택 범위를 확정한다.
