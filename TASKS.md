# TASKS.md — Phase별 개발 체크리스트

- [x] 0.2.40 · 경기 종료 피트 복기에 당시 예측과 실제 순위·앞뒤차·갭 차이, 관측된 수리·페널티·상대 피트·유효랩 페이스 차이를 표시한다. 실측 손실이 있으면 그 값만 바꿔 몇 자리가 달라지는지 계산한다. 같은 조건에서 내 피트 손실 중앙값이 이후 별도 경기 2회 이상에서 기존 평균보다 평균 절대오차가 낮고 과반 경기에서 이겼을 때 자동 적용한다. 몬자 L12 재생 직전 P1·뒤 COR 3.233초, 실제 P1·뒤 COR 2.718초. 바레인 과거 엔진 기록 P21·20.000초, 실제 P21·19.486초. 두 녹화 시점 모두 보정 방식을 검증할 후속 경기 0건. 재현은 `python tests/monza_pit_displays.py data/recordings/1794738164870921-629b389d612e65cc`, `python -m pytest`, `cargo test`, `cd web && npm test`. Rust 15·Python 75·웹 7개 및 Chrome 복기 검증 통과. 변경한 Python 파일 린트/타입 검사 통과. 저장소 전체 Ruff에는 기존 코드 지적이 남아 있음.

- [x] 0.2.39 · 피트 출구에서 복귀 순위·앞뒤 슬롯을 고정하고 같은 랩 거리의 통과 게임 시각 차이를 표시한다. 뒤차 통과 전에는 대기, 확인할 수 없는 간격은 측정 불가. 종전 UDP interval 및 첫 갱신값을 복기 실측에서 제거. 몬자 L12 출구 P1·뒤 COR 2.718초. 재현은 `python tests/monza_pit_displays.py data/recordings/1794738164870921-629b389d612e65cc` 및 `cargo test`. 예측의 원본 표시 기록은 그대로 보존한다.

- [x] 0.2.38 · 경기별로 브라우저가 표시한 피트 복귀 순위·앞뒤 드라이버·갭을 녹화 시계와 되감기 분기 ID로 저장한다. My Race 경기 종료 및 Session Analysis에서 진입 직전과 1·2·3랩 전의 마지막 표시값, 실제 출구 및 첫 간격 갱신을 비교한다. 몬자 복사본으로 Chrome에 표시한 L9–12의 P3/P1/P1/P1을 저장 및 재조회해 양쪽 드라이버와 밀리초까지 일치 확인. 기존 녹화에는 화면 기록이 없다. 재현은 `python tests/monza_pit_displays.py data/recordings/1794738164870921-629b389d612e65cc`. 실제 게임의 다음 정차는 아직 미검증.

- [x] 몬자 결승 42:10 순차 재생 검수. 진행 중인 섹터의 거리 비례 페이스를 최근 유효 섹터 기록과 현재 랩의 완료 섹터로 보정하고 플래시백 직후 이력·재고가 모두 비어 있는 동안의 임시 소프트 추천을 막았다. 몬자 19랩 25/50/75% 시점 평균 절대오차(ms) 985/2163/866 → 912/827/719. 바레인 별도 녹화 6랩 1232/1410/402 → 1128/1036/385. 몬자 L12 진입 직전 재계산 P1·뒤 COR, 실제 P1·뒤 COR. 당시 저장 예측·실측 피트 손실은 없음. 재현은 `python tests/monza_forecast_review.py data/recordings/1794738164870921-629b389d612e65cc`, `python tests/monza_one_stop_replay.py data/recordings/1794738164870921-629b389d612e65cc`, `python tests/codex_lap_replay.py data/recordings`.

- [x] 447px 타이밍 순위표의 배지와 페널티 칸을 분리하고 24명 배지 정렬·페널티 여백을 Chrome에서 검증했다. 720p 마이레이스의 피트 표와 가로 화면 설정 패널의 넘침도 수정했다. 재현은 서버 실행 후 `python tests/web_smoke.py http://127.0.0.1:8765`, `python tests/desktop_smoke.py http://127.0.0.1:8765`. 라이브 타이밍 9개 화면 크기와 브라우저·데스크톱 셸 6개 조합 통과.

- [x] Race Events를 6행×2열로 배치하고 랩 번호와 드라이버 배지 사이 여백을 확보했다. 새 이벤트는 좌상단에 추가하고 6번째는 우상단 7번째로 이동한다. `cd web && npm test` 및 Chrome에서 네 해상도 배치·새 이벤트 이동 검증. 전체 web_smoke는 447px 타이밍 순위표 배지 정렬 검사에서 중단.

- [x] 0.2.37 · 예측에서 연속된 여러 차량의 누락된 선두 갭을 같은 패킷의 유효한 앞뒤 간격으로 복원. 간격 불일치·피트 구간에서 연결이 끊기면 마지막 플랜의 기준 랩을 유지한다. 120초가 넘는 재생 공백도 같은 경기 분기·스틴트 안에서 복원한다. 몬자 전체 1초 표본 중 전략 대상 2,281개에서 새 예측 1,754개, 이전 예측 516개, 출발 타이밍·플래시백 타이어 자료 대기 11개. `cargo test`, `python -m pytest`, `python tests/codex_lap_replay.py data/recordings`으로 회귀 검증.

- [x] 0.2.36 · 현재 랩 피트 서비스에도 전략 엔진과 같은 검증된 선두 격차를 사용한다. 피트 진입부터 출구까지 마지막 A/B/C를 진입 전 랩·타이어 기준으로 열람할 수 있고 출구에서 교체한다. 몬자 18:57 / 39:56의 서비스별 손실·복귀 순위, 19:12 직접 탐색과 읽기 전용 플랜, 출구에서 하드 기준 재계산을 확인했다. 재현은 `python tests/codex_lap_replay.py data/recordings`.

- [x] 공통 헤더의 트랙 상태와 Menu 사이에 정사각형 새로고침 버튼 추가. 실제 WebView2 창에서 버튼 클릭 후 대시보드 재로드 확인. 재현은 `python tests/native_window_smoke.py http://127.0.0.1:8765`.

- [x] 0.2.35 · 몬자 18:13 L12에서 한 바퀴 뒤인 P24 PER의 선두 갭이 누락돼 A/B/C 전체가 비던 문제 수정. 전략 계산은 같은 패킷의 P23 선두 갭과 P24의 유효한 앞차 간격을 합산한다. 정차 측정값에는 대입하지 않는다. 18:10~18:20의 101개 시점과 18:13 A/B/C 아코디언을 검증했다. 재현은 `python tests/codex_lap_replay.py data/recordings`.

- [x] 0.2.34 · 플래시백에서 최신 Race Events와 기존 이벤트 ID를 보존하고, 재생 중 경기 분기가 바뀌면 선택 플랜과 Codex 상태를 초기화. 피트 중 상대 갭 누락으로 현재 예측을 만들 수 없는 시점은 보관된 예측을 읽기 전용으로 펼친다. 재생 위치를 직접 이동하면 같은 분기 직전 120초에서 예측을 복원한다. 몬자 12:08(L8)·13:16(L9) A/B/C 호버/클릭 및 플래시백 전후 로그 유지 검증. 배지 공통 테두리·여백, 최고 랩 보라색, 위험도별 글자색 및 컷 확률 하단 배치 적용. 재현은 `python tests/codex_lap_replay.py data/recordings`.

- [x] 몬자 L12 실제 출구(P1, 뒤 COR)에 기존 페이스와 최근 최대 3개 유효 스틴트 랩 평균을 대조. L7~11의 1초 간격 유효 시점 189개에서 앞뒤차 조합 일치는 기존 22회, 상대만 평균 8회, 전원 평균 9회. 되감기 전 시점들을 같은 스톱 한 건에 대조한 결과라 운영 모델은 유지. L12 진입 직전 원본은 PER의 선두 갭 누락으로 예측이 없고, 당시 P23과 P24 사이 간격으로 복원하면 세 방식 모두 P1·뒤 COR. 재현은 `python tests/monza_rejoin_pace.py data/recordings/1794738164870921-629b389d612e65cc`.

- [x] My Race 플랜별 예상 복귀 앞뒤차가 잠시 뒤집힐 때는 마지막 일치 예측을 표시한다. 같은 조합의 갭은 즉시 갱신하고 새 조합은 2초 지속 또는 기존 조합이 4초간 사라지면 교체한다. 몬자 11:01~11:31 녹화를 100ms 간격으로 비교한 조합 변경 횟수는 A 40→5, B 4→3, C 44→6. 재현 입력은 L12/L7/L13 정차. 시간 경계·재생 역행·피트 상태 변경 회귀 테스트는 `web/tests/raceEditor.test.mjs`.

- [x] Windows 바로가기는 전용 WebView2 창에서 대시보드를 연다. 앱 전용 프로필과 번역 제외 설정 적용. 실기에서 대시보드 로드, 프로필 확장 목록, 전체화면 진입·복귀, 두 번째 실행에서 Fit 설정 복원을 확인했다. 재현은 `python tests/native_window_smoke.py http://127.0.0.1:8765`.

- [x] 리플레이 플랜 선택 성공 문구 제거. 몬자 녹화 A/B/C 전환 시 상단 Selected plan 갱신과 중복 문구 제거 확인 (`python tests/codex_lap_replay.py data/recordings`).

- [x] My Race에서 인게임 UDP Action 3으로 Request Codex plan 실행. 설정 화면에 매핑 표시. 로컬 UDP BUTN 패킷을 반복 전송해 눌림당 1건인지, Chrome에서 마우스 클릭과 요청 본문이 같은지 검증. 재현은 `tests/my_race_smoke.py`의 `check_live_sessions`.

- [x] Risk details 트래픽 배지와 갭을 한 대씩 두 줄로 정렬하고 둘째 줄 옆 +N으로 나머지를 펼침. 피트 진입·복귀 순위 아래에 순위 변동을 분리. 몬자 11:01 B의 두 배지 및 +4 배치·펼치기 검증 (`python tests/codex_lap_replay.py data/recordings`).

- [x] 선택한 플랜에도 After pit 표 유지. Pit service와 After pit 사이에는 좌우 배치 시 세로선, 상하 배치 시 가로선을 표시하고 상단 예상 복귀 순위를 확대. 몬자 리플레이 A/B/C 선택·호버 및 1920px·447px 구분선 검증. 재현은 `python tests/codex_lap_replay.py data/recordings`.

- [x] My Race의 Plan A 대비 손실 열 제거. 복귀 트래픽은 가장 가까운 두 대의 예상 순위 배지·갭을 표시하고 나머지는 +N으로 펼친다. 트래픽과 컷 위험의 배지 크기 통일 및 확대. 몬자 11:01 Plan A의 2대와 Plan B의 6대(+4 펼치기·접기)를 Chromium에서 확인. 재현은 `python tests/codex_lap_replay.py data/recordings`.

- [x] 피트 복귀 트래픽은 타이어 교체 후 내 앞 3.000초 이내 차량을 집계하고 같은 기준으로 플랜의 트래픽 위험을 판정. 바레인 2024 FIA 회견에서 사인츠가 설명한 2~3초 더티에어 구간을 참고한 앱 기준. Risk details에서 Plan A 대비 추가 순위 손실과 언더컷·오버컷 경쟁차 배지 및 시나리오 비율 표시. 몬자 11:01 Plan A에서 P3→P18, BOR +1.138s / LIN +1.519s, COR / PIA 양쪽 0% 확인. 재현은 `python tests/codex_lap_replay.py data/recordings`, 3.000초 포함·3.001초 제외는 `python -m pytest tests/test_my_race.py`.

- [x] 리플레이 슬라이더는 드래그를 놓을 때 한 번만 이동하며 Rust가 녹화별 중간 상태를 최대 16개 보관해 되감기를 가속한다. 몬자 40:00→39:50 단일 Rust 측정 1.067s→0.025s, 6개 시점 순차 복원 대조 및 Chrome 재생/일시정지 후 역방향 드래그 검증. 재현은 `python tests/codex_lap_replay.py data/recordings`.

- [x] 선택 플랜은 상단에 복귀 정보를 표시하고 다른 플랜을 펼칠 때만 After pit 비교 표를 표시. 앞뒤 배지·간격 확대 및 피트 서비스와 표 높이 정렬. 몬자 1920×1080 재생 A/B/C 선택·호버, 같은 피트 랩 후보 구분, 좌우 표 높이 오차 1px 미만 검증. 재현은 `python tests/codex_lap_replay.py data/recordings`.

- [x] My Race 전체화면에서 복귀 순위·앞뒤차의 배지와 간격을 같은 줄에 배치하고, Plans의 수치 열과 Risk details 5열 표를 중앙 정렬. 몬자 1920×1080 A/B/C/A 전환에서 배지·시간 중심 차이 1px 미만, 셀 정렬·구분선 검증. 재현은 `python tests/codex_lap_replay.py data/recordings`.

- [x] My Race 플랜별 After pit·Risk details 적용. 타이어만 교체할 때의 진입·복귀 순위, 앞뒤 배지와 밀리초 간격 추세, Plan A 대비 순위 손실, 1초 이내 트래픽, 두 경쟁차의 첫 정차 시점 5개 시나리오별 언더컷·오버컷을 표시. 몬자 브라우저 A→B→C→A(14:10)와 Plan C 언더컷 2/5(05:02), 합성 오버컷 5/5·0/5 검증. 재현은 `python tests/codex_lap_replay.py data/recordings` 및 `python -m pytest tests/test_my_race.py`.

- [x] My Race에서 현재 주행 랩, 예측에 사용한 랩, 피트 예정 랩을 각 정보의 제목에 명시. 복귀 예측은 계산 기준 랩에서 예정 랩까지의 차이로 조회. 몬자 L9/L12 화면 및 바레인 일시정지·랩 변경 재생 검증. 웹 lint·테스트·빌드 통과.

- [x] 피트 서비스와 라이벌 표의 카테고리 경계를 2px, 1·3·5랩 및 언더컷·오버컷 사이 경계를 1px로 구분. 몬자 재생의 세 화면 폭에서 검증 (`python tests/codex_lap_replay.py data/recordings`).

- [x] My Race 피트 서비스·라이벌 피트 표의 제목과 모든 셀을 중앙 정렬. 몬자 녹화의 1920·1280·447px 브라우저 화면에서 정렬과 표 경계 확인 (`python tests/codex_lap_replay.py data/recordings`).

- [x] My Race 아코디언의 라이벌 타이어를 전용 Tyre 열에 표시하고 피트 확률·페이스 이득 등 열 그룹을 세로선으로 구분. 넓은 패널의 피트 서비스·라이벌 표 폭을 40:60으로 조정. 몬자 재생에서 장착 컴파운드와 1920·1280·447px 배치 검증 (`python tests/codex_lap_replay.py data/recordings`). 웹 lint·테스트 6건·빌드 통과.

- [x] My Race 실시간·녹화 재생의 A/B/C 계산에서 이미 선택한 후보의 후속 스톱을 분리했다. 선택만으로 표시 중인 후보가 교체되지 않는다. 몬자 09:26(6랩) 브라우저 A→B→C→A 및 실사용 8765 재생 A→B에서 각 확정 일정과 세 후보를 대조했다. 재현은 `python tests/codex_lap_replay.py data/recordings`. Python 66건·웹 6건·lint·빌드 통과.

- [x] My Race 플랜 행과 아코디언이 같은 남은 피트 일정을 사용한다. 현재 랩의 장착 타이어부터 표시하고 피트 서비스에서 정차 시간 열을 제거했다. 넓은 패널에서는 오른쪽에 라이벌 피트 표와 현재 타이어를 표시한다. 몬자 6~11랩 재생 및 L9의 지난 L7 소프트 계획을 추가한 회귀 사례에서 아코디언을 펼친 채 원스톱→투스톱 갱신 검증. 재현은 `python tests/codex_lap_replay.py data/recordings`. 웹 lint·테스트 6건·빌드 통과.

- [x] My Race는 확정한 플랜 ID에만 복귀 미리보기를 숨기며 데모에서도 선택 ID를 전달한다. 상단 복귀 순위·앞차·뒤차를 분리하고 피트 서비스 표를 내용 폭으로 줄여 정차 시간을 Stop time으로 표시. `python tests/codex_lap_replay.py data/recordings`에서 A/B 모두 L12인 몬자 재생으로 B→C→A 확정 및 각 행 호버를 확인. 바레인 화면 폭 검사, 데모 가상 휠, 웹 lint·테스트·빌드 통과.

- [x] My Race 가독성 시안 적용. 고정 높이 주변 차량 표, 페이스 예측 카드, 선택 플랜의 다음 타이어·복귀 간격과 A/B/C 체크·추천·미리보기 구분. 피트 서비스는 정차·손실·순위 표만 표시하고 라이벌 표는 현재 랩 포함 1/3/5랩 누적 피트 가능성과 플레이어 기준 한 랩 이득을 분리. 몬자 9랩 ALB 0/20/40% 및 바레인 여러 화면 폭·한 번 확정 검증. 재현은 `tests/codex_lap_replay.py`, `tests/recorded_ui_smoke.py`에 `data/recordings` 전달. 웹 lint·6개 테스트·빌드 통과.

- [x] My Race의 가로 패널을 관측 46%·피트 전략 54%로 조정. 몬자 1920×1080 재생에서 펼친 플랜을 확인하고 바레인 재생으로 긴 갭과 두 자리 순위의 셀 경계를 검증했다. 재현은 `python tests/recorded_ui_smoke.py data/recordings`.

- [x] My Race 플랜 미리보기(0.2.30)에 타이어 교체와 앞날개 추가 교체의 예상 정차·손실·복귀 순위, 현재 앞뒤 라이벌의 피트 예상 랩·1/3/5랩 확률·한 랩 언더컷/오버컷 이득을 표시. 다음 스톱이 늦어도 그 랩의 차량 간격으로 서비스별 복귀 순위를 계산한다. 몬자 9랩에서 12랩 피트 예상은 타이어만 2.39초 정차·20.39초 손실·P2, 앞날개 포함 7.59초·25.59초·P3(게임 기준). `python tests/codex_lap_replay.py data/recordings`로 A/B/C 전환 검증. 바레인 Chrome 재생, Rust 10·Python 66·웹 6개 테스트 통과. 8765 서버에 배포.

- [x] My Race 플랜 아코디언의 일반적인 완주 순위 변동 문구 제거. 웹 lint·테스트 6건·빌드 통과.

- [x] My Race 피트 복귀 앞·뒤 간격 (0.2.29). Rust에서 같은 복귀 시점의 예상 순서로 양쪽 인접 차의 간격을 계산. 넓힌 플랜 아코디언과 확정 플랜에 순위·피트 손실·Ahead(+)/Behind(−) 표시. 몬자 L9→L12 H 예상 P2, ALB +403ms / COL −411ms를 브라우저와 대조. 재현: `python tests/codex_lap_replay.py data/recordings`.

### FP 세이브 변경 기록

- [x] 서버 수명주기에 독립 감시 스레드 연결. Steam 중간 세션·프로필 원본을 읽어 변경 버전과 UDP 시각·랩·되감기 구간을 로컬 SQLite에 저장. 하이라이트 파일 제외. 재생 화면과 무관하게 실제 수신기만 감시.
- [x] 원본 해시·수정시각 보존, FP 직전·직후 변경, 복사본 중복 제거, 되감기 랩 취소, 재시작 후 조회, 로컬 UDP→보고서 경로 검증. `python -m pytest tests/test_practice_saves.py`. 전체 Python 66건 통과, 새 모듈 ruff·mypy 통과.
- [x] 몬자 FP1 녹화 재생과 별도 테스트 세이브로 완료 5랩·미분류 5랩 대조. 8765 실사용 서버에서 Steam 감시 파일 4개·Armed 확인.
- [ ] 다음 실게임 FP의 변경 버전에서 프로그램 ID·완료 랩 대응을 검증하고 프로그램별 랩 수를 대조한다.

- [x] My Race 왼쪽 패널 마지막 줄에 Recent pace를 배치하고 최근 완료 랩을 가용 폭에 균등 분배. 피트 복귀 순위 비교표는 Session Analysis에서 표시. 바레인 녹화 UI로 447~1920px 다섯 화면 폭과 비교표의 예상·실제 순위 확인 (`python tests/recorded_ui_smoke.py data/recordings`).

### 몬자 결승 원스톱과 My Race 플랜 (0.2.28)

- [x] 만료된 Codex 후보만 같은 GP 스레드에 자동 재요청. 응답 전 기존 일정은 흐리게 표시하고 빨간 ×로 마우스·휠 확정을 차단. 새 후보를 Rust로 재평가한 뒤 해당 행을 활성화. 몬자 10→11랩에서 B만 재요청하고 A/C 일정과 기존 선택을 보존하는 과정을 Chrome에서 확인. 재현: `python tests/codex_lap_replay.py data/recordings --expiry` (로컬 SDK 대역).
- [x] 몬자 6랩에서 로컬 SDK 응답 1건을 받아 A/B/C 적용 후 11랩까지 일정을 비교. 10→11랩은 1배속 연속 재생으로 각 프레임까지 대조. A의 L12 하드 복귀 예상은 같은 9랩의 5초 사이 P2(앞 1초권 ALB 0.403초)에서 P3(앞 1초권 0대)로 변경. Rust 응답과 Chrome 표시를 `python tests/codex_lap_replay.py data/recordings`로 검증.

- [x] 몬자 결승 출발 전 FP 필터에 플레이어 미디엄 2랩과 필드 28랩 채택. 플레이어 미디엄 중앙값 1:21.912, 마모 3.91%p/랩. 게임 프로그램 식별자는 확인되지 않아 연속 주행 표본으로 취급.
- [x] 실제 사용 컴파운드와 장착 세트 잔여 수명으로 추가 정차 없는 완주 후보 평가. 되감기 직후 피트 이력이 복원되기 전에는 새 후보 계산을 보류. 앱에서 선택한 플랜을 선택 당시 세션·랩·랩 경과시간과 함께 보존.
- [x] 주행 중 Codex 응답 한 건으로 A/B/C의 피트 랩·타이어를 제안하고 Rust에서 후보별 일정과 복귀를 재평가. 유효한 후보는 다음 랩에도 유지. 행을 한 번 눌러 확정. 상단에는 선택한 계획의 다음 정차·예상 손실·복귀 순위와 앞 1초 이내 차량별 간격 표시.
- [x] `python tests/monza_one_stop_replay.py data/recordings/1794738164870921-629b389d612e65cc` 통과. L10 기준 L12 하드 예상 손실 20.363초, P1, 앞 1초 이내 0대. L13~16 및 되감기 후 하드 완주 추천 검증.
- [x] Rust 10, Python 64, 웹 단위 테스트 5 통과. 바레인 교차 랩·일시정지 브라우저 회귀와 녹화 UI에서 로컬 SDK 응답을 사용한 세 후보 갱신 및 한 번 선택 검증. 실사용 8765에서 0.2.28과 Last recording 확인. 실제 Codex 서비스의 새 몬자 응답은 미검증.

### 몬자 FP 타이밍 및 전략 표본 검수

- [x] 순위표 S3는 직전 랩의 게임 히스토리 값을 계측선 통과 후 5초 동안 표시. 마지막 랩 섹터 순위는 별도로 유지.
- [x] 미니섹터는 공식 S1/S2 통과 시각에 맞춰 구간을 비교. 몬자 첫 아웃랩과 동일한 랩 번호로 계측이 시작되는 경우 및 섹터 경계의 10ms 시계 보정을 재현해 수정. FP1 녹화 `1794735823068975-42765713e5577ea7`에서 첫 계측 랩 S1의 2~4번째 구간을 100ms 거리 표본으로 별도 보간해 3대의 보라/초록 표시를 대조.
- [x] 출발 전략, FP 마모 추정, Codex에 전달하는 FP 표본을 동일 세션·차량·노면·컴파운드의 연속 세트 주행으로 제한. 인접 랩이 4% 이내이며 가장 빠른 연속 쌍과 비슷한 페이스인 구간만 사용. EA UDP에 프로그램 결과 식별자 없음. 원본은 보존. 몬자 FP1 중 건조 조건 50개 후보에서 24개 채택. 플레이어 M 2랩, 중앙값 1:21.912.
- [x] Rust 10, Python 64, 웹 단위 테스트 5 통과. `tests/recorded_ui_smoke.py data/recordings`에서 바레인 그리드 및 몬자 S3 표시/해제 검증. 0.2.27 서버 인계 확인.

> 상태: Phase 0·1 검증 완료. Phase 6의 React A/B탭을 모의 데이터로 선행 구현함. Phase 2~5의 라이브 타이밍 수신 경로를 선행 연결함. `docs/MASTER_PLAN.md`의 단계별 설명과 완료 기준을 함께 읽는다. 각 단계의 [ ]는 테스트와 산출물 확인 후에만 [x]로 변경한다.

## Phase 0 — 레퍼런스 검증 및 채택 결정
- [x] F1 Telemetry Go 저장소/라이선스/실행을 실제로 확인하고 UI 재사용 범위 결정
- [x] f1-2026-telemetry 패킷 테스트와 EA 공식 2025/2026 규격 대조
- [x] Lift and Coast 전략/AI 구조, Pitwall 시뮬레이션/백테스트 실제 코드 검토
- [x] Race Engineer 및 ef-one-tv 코드 감사 및 라이선스 상태 기록
- [x] Rust F1 25 crate의 2025/2026 지원 여부 확인
- [x] docs/REPO_AUDIT.md, docs/THIRD_PARTY.md에 SHA, 파일별 선택 근거 작성
**Gate:** 검증된 직접 채택/참고/제외 목록 존재

## Phase 1 — 개발 기반
- [x] Rust workspace + PyO3/maturin + Python/FastAPI + React/Vite/TS 구성
- [x] Windows 실행 스크립트와 .env.example, 예외 처리, 포트 설정
- [x] lint/typecheck/test/build 기본 명령 작동
- [x] Mock WS→React Hello Live 테스트
**Gate:** 설치 후 F1 없이 health + UI가 실행

## Phase 2 — 파서
- [x] 라이브 타이밍 범위의 v1 Motion/Session/Lap/Event/Participants/Telemetry/Status/Session History를 포맷별 길이·슬롯·버전으로 구분. Windows Rust 수신기 → WebSocket 검증은 `python -m pytest tests/test_live_udp.py`.
- [ ] UDP header 및 packet type + size + version validation
- [ ] 2025 주요 패킷 파서+fixture, 2026 별도 패킷 파서+fixture
- [ ] 패킷 잘림·에러·unknown version·malformed inputs 처리
- [ ] 공식/다른 구현과 크기/필드 값 교차 검증
**Gate:** 2025/2026 정상 패킷 구분 및 회귀 테스트

## Phase 3 — 수신·녹화·재생
- [x] 0.2.11 녹화 피트 복귀 검증. 원본 패킷을 순서대로 재생해 진입 직전 모델값을 고정하고 My Race와 Session Analysis에서 당시 저장값·재계산·관측 순위를 구분함. 바레인 2랩 P22→P21, 3랩 P22→P21, 11랩 P21→P20. 구형 목록에서 분할된 3랩 진입~4랩 출구는 실제 연속 피트 1건. 별도 7랩 관측 P22→P22에는 재계산 원본 없음. 재현은 `python tests/recording_library_smoke.py data/recordings`. 독립 검증은 Python 3.14에서 `python tests/external_pit_backtest.py <결승.f1bin>`. [Cognizant 공개 카탈루냐 결승](https://github.com/cognizant-ai-lab/f1/releases/tag/test-data-v2)의 SHA256 9831d529a55aec976766c2e75242c6b67d18f9241c7d5c28b3621c5c4eb39483 검증. 22대 전부 동일 모델·초기 손실 20초로 재생, 상대 차량 슬롯 18의 L1 P20→P20. [바쿠 샘플](https://github.com/NoGoat/Track-N-Race/releases/tag/1.3.1-test)은 전체 타이밍 1,038프레임에 피트 진입 없음. 외부 데이터는 임시 폴더에서만 검사함.
- [x] 2026-11-15 바레인 원본 9개를 끝까지 재생하고 909개 시점의 타이밍·지도·랩 평균·전략·피트 시각 및 중간 지점 되감기를 대조함. 플래시백 뒤에도 남은 P21 복귀와 앞날개 수리 시간을 세션 목록에 복원함. 재생 중 분석 탭에서 같은 녹화를 열고 휠로 A/B/C 상세·상대를 조회할 수 있음. 타이밍이 없는 녹화 구간과 미기록 출구를 별도 표시하고 순위표 S3에 직전 완료 랩 기록을 표시함. 재현은 `python tests/recording_library_smoke.py data/recordings`, 웹 빌드 후 `python tests/recorded_ui_smoke.py data/recordings`. 주행 원본은 바레인에 한정되며 L7의 P22/P22는 원본 외 별도 실시간 관측임.
- [ ] Tokio UDP 수신, 수신 지표, 비차단 파서 경로
- [x] Rust 수신 스레드 → 유한 큐 → 세션별 timestamp·원본 UDP zstd 체크섬 청크와 피트 예측·관측 인덱스 자동 기록
- [ ] chunk index/checksum, 손상 파일 복구 동작
- [x] 앱 재시작 후 Session Analysis에서 같은 녹화를 My Race로 열고 일시정지·1/4/16배속·되감기·결과 이동. 2025/2026 루프백 회귀로 피트 전 예측 고정, 출구 관측, 세션 분리와 손상 파일 검출 확인(tests/test_recordings.py).
**Gate:** 녹화→재생 파싱 결과 동일, 유실 추정 지표 표시

- [x] 0.2.10 My Race 추격·방어 표시. 실시간 추세는 계속 계산하고 화면은 같은 상대와 비교 가능한 최근 최대 3개 완료 랩 차이를 평균해 랩 단위로 갱신함. 바레인 5랩의 스트롤 추격을 1초 간격으로 98회 재생한 결과 실시간 ETA는 38종, 표시 페이스는 랩당 1.050초 벌어짐으로 일정함. 2025/2026 UDP, Chrome 녹화 회귀로 확인.
- [x] 0.2.9 바레인 실주행 검수. 5랩 98.4초 동안 플랜·추격 페이스가 같은 랩에서 갱신됨. L7 진입 직전 P22, L8 출구 P22, 8.016초 앞날개 수리 확인. 당시 Windows 인덱스 교체 실패로 원본은 피트 전에 끊겼고, 실시간 관측 결과를 Session Analysis에서 별도로 보존·재확인함. 녹화 인덱스 잠금 중에도 청크를 쓰고 해제 후 다시 게시하도록 수정. 재현은 `python -m pytest tests/test_recordings.py -k locked_manifest`.
- [x] 0.2.8 My Race 실측 입력 점검. 현재 섹터와 차량별 유효 랩, 공개 상대 세트와 교체 소요, 시간 벌칙 및 서킷별 그린·SC·VSC 표본을 사용함. 게임 전략 랩의 복귀 예상과 다른 랩의 모델값을 구분함. 바레인 피트 직전의 P13 선두 격차 누락은 같은 프레임의 인접 차 시계로 13.833초 복원. 재현은 `python -m pytest tests/test_live_udp.py tests/test_recordings.py` 및 아래 바레인 Chrome 회귀 명령.
- [x] 0.2.7 라이브·재생 전략 및 세션 분석. 2025/2026 예보·세트 재고·장착 수명·게임 피트 윈도와 주행 페이스로 A/B/C와 후속 정차를 계산함. 세션 분석은 게임·녹화에서 거리 기준 실측 채널을 읽으며 플래시백 대상 이후 샘플을 버림. 바레인 마지막 유효 분기 115개 샘플, 3개 완료 랩, 게임 윈도 L10 및 모델 추천 C(L11 S → L20 M) 확인. 재현은 `python -m pytest tests/test_live_udp.py` 및 아래 바레인 Chrome 회귀 명령.
- [x] 0.2.6 라이브·재생 추격/방어 예측. 유효한 현재 차간격과 최대 30초의 동일 상대 추세를 랩당 초와 1초권 예상 랩 수로 변환. 바레인 2랩 정차 8.0초·앞날개 수리·P21, 같은 경기 녹화 475335ms에서 BOT 22.583초·약 9랩, 993589ms에서 BOT 23.083초·랩당 1.1초 확대 확인. FLBK 이후에도 되감기 목표 프레임 전에 끝난 정차를 유지. 회귀는 `python -m pytest tests/test_live_udp.py tests/test_recordings.py` 및 `tests/bahrain_crossing_smoke.py`.
- [x] Rust 0.2.4 실서버 교체. 바레인 녹화 1랩에서 진행 거리와 경과 시간으로 A/B/C 갱신, 4랩 옐로에서 추격 페이스와 예상 복귀 P22 표시, 일시정지 상태 보존, 11랩 앞날개 수리 8.0초·실제 P20 확인. 재현은 `python tests/bahrain_crossing_smoke.py data/recordings/1794655466089283-cab8d764d84f0aae`. 패킷 단위 정상·수리 정차 분리는 `python -m pytest tests/test_recordings.py`. 서버 교체 후 별도 UID의 바레인 결승 실수신과 새 녹화 확인. 첫 랩 연속 0.5초 표본에서 같은 상대의 실시간 페이스 갱신, 옐로·VSC의 플랜 유지, 2랩 실서버 HAM P8·예상 복귀 P22 확인. 새 경기의 실제 피트 복귀 오차는 피트 진출 후 검증 대상.

실게임 바레인 FP1 2026 자동 기록 및 Chrome 재생 확인. 실결승 피트 복귀 오차의 현장 검증은 남아 있음.

## Phase 4 — RaceState / Reducer
- [x] 실게임 2026 바레인 FP1 자동 인식, 세션 시간, 22대 순위·지도 이동, 플레이어 타이어·랩 이력 및 진단 수신 확인. UDP ID 28개로 F1 Media 원본 25장을 직접 조회. 바레인 FP1에서 115초간 측정, HAM의 전 코스 100개 거리 구간·실제 출발선 통과·메인 직선·T5→T6 진입 확인. 상대 차량으로 보정 후 HAM의 도면 투영 오차 중앙값 6.4→3.9px(1252×704). 별도 로컬 UDP·헤드리스 Chrome에서 FP1→Q1→Race 전환과 레이스 전용 전략 활성화 검증. 재현은 `python tests/my_race_smoke.py`. 실주행 결승 전략 및 실물 휠은 미검증.
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
- [x] 스즈카 원본과 같은 1252×704 좌표계에서 흰 외곽선 두께(밝기 반높이의 중앙값)를 대조함. 바레인 1.94→2.69px, 스즈카 2.74px. 양쪽 선 중심 간격은 모두 34px. 보정 좌표를 따라 렌더링 곡선을 매끈하게 연결하고 플래그 마스크에도 같은 곡선과 폭을 적용함. 직선 단면 회귀는 `tests/my_race_smoke.py`.
- [x] 바레인 2026 Sakhir 상세 원본에 스즈카 노면 폭·섹터 색·코너 표식·경고 테두리 적용. 이몰라와 제다에도 동일 규격 사용. 바레인 FP1 저장 기록에서 HAM 이동 방향 1,171구간 일치. Chrome에서 실제 FP1 기록과 SC 가정 프레임을 각각 렌더링. 회귀는 `python tests/my_race_smoke.py`.
- [x] My Race에서 휠로 선택한 A/B/C의 상세를 직접 열고 상대 변경·원래 플랜 복귀. SDL 가상 휠로 젖은 노면의 추천 B안 L21 I를 L22 W로 수정한 뒤 취소 시 전송 없음·기존 계획 유지, 확정 시 수정안 1회 전송·서버 응답 반영 검증. 출발 전 스톱 추가·삭제·적용도 휠로 검증. 재현은 `python tests/my_race_smoke.py`.
- [x] Session Analysis에 휠용 GP 선택 추가. Chrome과 SDL 가상 휠로 바레인 결승 선택, 두 랩·채널·거리·섹터 비교, 스틴트별 리플레이 재생·일시정지·랩 이동 검증. 재현은 `python tests/my_race_smoke.py`.
- [x] Session Analysis에서 GP 세션 검색·랩 비교·리플레이를 통합하고 Diagnostics는 Settings로 이동. Previous screen·Next screen 휠 매핑으로 세 탭을 양방향 순환하고 분석 탭에서 POV로 항목·값 선택, Cancel로 마지막 주행 화면 복귀. SDL 가상 휠과 Chrome에서 기존 전략 입력, 분석 기능, 6개 데스크톱 창·해상도 조합 검증(`tests/my_race_smoke.py`, `tests/demo_panels_smoke.py`, `tests/desktop_smoke.py`).
- [x] Windows Start.cmd 전용 앱 창. Menu → Settings → Display에서 전체화면·창모드 전환, 전용 창에서 Fill window(기본)·Fit 16:9 선택과 복원. 전략 상세를 별도 열에 배치하고 720p·1080p·1440p와 1600×1000·2560×1080에서 타이밍 24행, 전략 편집, 설정·분석 패널의 무스크롤 레이아웃 검증. 재현은 `python tests/desktop_smoke.py`.
- [x] 순위표 타이어 이력의 각 링을 스틴트 칸 오른쪽에 고정함. Chrome 447·819·1396·1920px 폭에서 24명 × 3칸의 열별 중심 좌표 편차 0px 확인. 회귀 검사는 `tests/web_smoke.py`의 `check_stint_alignment`.
- [x] 공용 타이어 배지 대문자 기준선과 S·I·W 광학 중심 보정. Chrome에서 14~82 CSS px 다섯 크기, 1·1.5·2 장치 배율, 다섯 컴파운드의 75개 조합을 캡처함. 링 중심 대비 글자 외곽 중심의 축별 오차 최대 0.50 CSS px, 밝기 가중 중심 오차 최대 0.69 CSS px. 재현은 데모 실행 후 `python tests/tyre_ink_smoke.py`.
- [x] My Race는 데모 프레임으로 Pre-race·Racing·DNF와 날씨·노면을 자동 표시함. 전략표 A/B/C, 상대 선택, 초안 미리보기·확정·취소를 휠로 조작함.
- [x] 데모 레이스에서 약한 비→젖은 노면→고인 물→배수→건조에 따라 추천 플랜과 컴파운드를 갱신함. 순위표·My Race·텔레메트리·GP 기록은 공용 타이어 배지를 사용함. 재현은 `tests/my_race_smoke.py`의 44~99초 구간과 `tests/demo_panels_smoke.py`.
- [x] React 더미 프런트에서 최근 페이스·대기 사유·스틴트·계획 비교·피트 윈도우·상대 피트·예상 순위, 텔레메트리·GP 기록/랩 재생·진단을 제공함. 실제 엔진·UDP·DB 단계는 별도 진행. 검증은 tests/demo_panels_smoke.py 및 기존 A/B 스모크.
- [x] My Race의 현재 타이어와 확정 피트 계획에서 같은 컴파운드 링·이름을 표시함. Chrome에서 하드 링과 계획 변경 후 인터미디엇 표시를 검증함.
- [x] React B탭 모의 주변 5대·완료 랩 페이스·전략 미리보기와 확정, 출발 전 편집, DNF
- [x] SDL 가상 휠 버튼·POV → React A/B 선택·편집·확정·취소 및 재실행 매핑 복원
- [ ] 실물 MOZA 앱솔루트 다이얼 및 스틱 조작 확인
- [x] 다크 차콜/레드 테마 토큰, 헤더/플래그, 타이밍 타워
- [x] 순위표·섹터표 배지의 번호와 이름은 팀색 바탕을 공유함. 1920×1080 기준 순위표는 84×32px에 팀색 여백 4px, 섹터표는 83×30px에 3px. `tests/web_smoke.py`로 배지 치수와 여백을 검증하고 Chrome 캡처에서 36개 배지의 상·하·우 가장자리 팀색을 확인함.
- [x] 두 표의 이름과 순위에 별도 글자 크기·자간을 적용함. 1920×1080 Chrome 캡처에서 VER·NOR·HAM의 글자 높이 12px, 순위 14의 높이 13px 확인. 좁은 화면을 포함한 기존 정렬 검사 통과.
- [x] A/B 대시보드 전체를 로컬 Formula1 Display Bold로 전환함. Chrome에서 헤더·타이밍·지도·섹터·전략 선택지의 실제 서체와 한글 맑은 고딕 대체를 확인. 프런트 빌드·단위 테스트·화면 회귀 검사 통과.
- [x] 헤더에 Live Timing과 My Race만 표시함. 819×883에서 My Race의 Nearby Drivers·Pace Forecast 배지 크기, 팀색 여백, 번호와 이름 서체를 Live Timing과 비교하는 Chrome 테스트 통과.
- [x] 초기 My Race 기능표와 React 구현의 차이를 docs/B-my-race-react-plan.md에 기록함. 두 탭의 헤더 Menu → Settings에서 휠 매핑과 단축키 안내에 접근하고 전략 버튼은 후보 옆에서 조작함. Chrome A/B 및 가상 휠 등록·저장·재실행 검사 통과.
- [x] 모의 24대 A탭, 섹터색·최근 랩 섹터 순위, 타이어, PIT, 스즈카 지도 및 2열 이벤트 로그
- [x] UDP Session의 2025·2026 마셜 존 시작점과 깃발을 Rust→WS→지도에 연결. 같은 섹터의 분리된 두 구간, 출발선을 걸친 구간, 황색 해제를 임시 UDP와 Chrome 픽셀로 검증함. 재현은 `python -m pytest tests/test_live_udp.py` 및 `python tests/my_race_smoke.py`.
- [x] 사용자가 실경기에서 구간 황색기 표시를 확인함. 전체 서킷의 실게임 발령·해제 시점 대조는 미검증.
- [x] 싱가포르 실경기 구간 황색기 사용자 확인. 26개 도면을 재검수하고 상세 도면 21장의 감지점·안내선과 섹터 표식 자리 총 126곳을 복원함. Chrome 전후 캡처에서 싱가포르 기존 외곽선 절단 3곳 복구와 126곳 섹터선 연결 확인. 28개 트랙 ID 및 역방향 마셜 존 검사는 임시 UDP로 통과. 재현은 `python assets/game-circuits/clean_artwork.py`, 프런트 빌드 후 `python tests/my_race_smoke.py`, `python tests/web_smoke.py http://127.0.0.1:8765/`.
- [x] 싱가포르 T17→18 감지점 아래 직선과 해당 경고 테두리를 옆 원본 단면으로 복원함. 1252×704 도면에서 표식 양옆에 맞춘 직선 대비 파란선 중심의 최대 편차가 1.00→0.17px. 빌드 및 임시 UDP Chrome 회귀 통과, 전후 캡처는 `output/playwright/map-review/singapore-t17-t18-comparison.png`.
- [x] 상세 도면 21장 감지점 63곳을 원본과 확대 대조하고 노면·흰 외곽선·깃발 마스크를 보정함. 별도 렌더 방식의 5장도 비교함. 원본 노출부로 독립 측정한 직선 24곳의 최대 중심 편차 3.451→0.182px, 안내선이 가로지른 경고 테두리 67곳 1.172→0.349px(1252×704 기준). 재현은 `python assets/game-circuits/clean_artwork.py`, `python tests/circuit_detector_pixels.py`. 빌드 후 임시 UDP Chrome 28개 트랙 ID와 데모 23개 지도 회귀 통과. 확대 전후 비교는 `output/playwright/detector-audit/comparison.png`.
- [x] 바레인 원본 도면의 섹터 표식 자리에서 휘던 T3→4 및 T13→14의 경로 좌표를 직선에 투영함. 기존 랩 인덱스로 차량·노면과 마셜 존 외곽선을 동기화하고 두 구간의 최대 가로 오차가 0.06px 미만임을 확인함. 회귀는 `python tests/my_race_smoke.py`.
- [x] 26개 지도 원본과 한 바퀴당 480개 차량 위치를 대조함. 멜버른·상하이·모나코·실버스톤(2곳)·바쿠의 섹터 표식 아래 직선을 복원하고, 라스베이거스 T1~4 경로와 경고 테두리, 루사일·야스 마리나 도면, 체크무늬와 랩 시작점 정렬을 수정함. `python tests/my_race_smoke.py`로 28개 ID의 정·역방향 마커 및 구간 황색, `python tests/web_smoke.py http://127.0.0.1:8765/`로 23개 데모 선택과 플래그 상태를 확인함.
- [x] 실게임 2026 바레인 FP1 참가 차량 22대·플레이어 및 양쪽 대시보드 연결. 2025는 합성 데이터그램으로 검증.
- [x] 바레인 결승 녹화에서 2·3랩 차량이 함께 있던 랩 패킷 시각 848개 모두 예상 복귀 P22와 A/B/C 표시. 실제 한 바퀴 차는 계산 보류. Chrome에서 같은 기록에 일시정지·수신 중단·재개를 적용해 기준 랩과 마지막 예측 유지 확인. 재현은 프런트 빌드 후 `python tests/bahrain_crossing_smoke.py data/recordings/1794655466089283-cab8d764d84f0aae`.
- [ ] 내 차/실질 경쟁 상대 강조 및 예측/관측 라벨
- [ ] Connection/Mock/Replay/No data 상태, 탭 구조 구현
- [x] 1920×1080 Chrome 뷰포트와 승인 시안 비교 (design-qa.md)
**Gate:** 게임 없어도 mock Live Timing 완성, 실측 연결 가능

## Phase 7 — GP 라이브러리
- [ ] DB migration/schema 및 데이터 저장·검색 repository
- [ ] 한 GP 아래 FP/예선/레이스/재시도 분류
- [ ] 랩/스틴트/피트/전략/예측/결정/이벤트/원본 파일 참조 저장
- [ ] History/Replay 화면 + GP 필터 + Export/Backup
**Gate:** 앱 재시작 이후 과거 GP 100% 재탐색·재생

## Phase 8 — 레이스 전 전략
- [x] 0.2.12 My Race에 타이어 단독·앞날개 추가 복귀 예상과 진입 전 값을 표시. 부위별 손상 전후, 타이어 교체 증거, 그린·SC·VSC 전환, 정차 지연, 원본 손실을 기록함. 보정 시 실제 정차 시간을 빼고 가정한 정상 시간(2.5초/8초)을 적용. 작업별 기준보다 0.75초 넘는 정차와 조건 전환은 표본에서 제외. 경미한 손상 유지·수리와 지연 동시 발생·재시작 복원은 `python -m pytest tests/test_recordings.py`, 바레인 진입 직전 검증은 `python tests/recording_library_smoke.py data/recordings`, 실제 UI는 웹 빌드 후 `python tests/recorded_ui_smoke.py data/recordings`. 녹화 당시 두 작업별 예측은 없었으며 이번 재계산에서 L2 P22/P22→P21, L3 P22/P22→P21(그린→VSC), L11 P21/P21→P20. 게임은 크루 실수 원인을 직접 전송하지 않음.
- [x] 0.2.13 실제 설치 GVDB에서 추출한 차종·동일 성능·훈련별 정차 범위와 앞날개 예상 추가 시간을 사용. 세션의 Automatic/Broadcast는 수동 턴인 가산을 적용하지 않음. 타이어 단독/앞날개 추가, Green/SC/VSC, 피트 설정별로 작업 정차 시간과 피트 복귀 손실의 실측 평균을 각각 집계. 지연 의심·판정 보류·작업 미확인은 기록에 유지하고 평균 제외. 기존 녹화는 원본 재생으로 재판정. 바레인 Broadcast L2 8.000초, L3 8.016초(Green→VSC), L11 8.000초는 추정 범위 초과로 제외. L7 별도 라이브 기록은 원본 공백으로 미분류. 재현은 `python tests/recording_library_smoke.py data/recordings`, `python tests/recorded_ui_smoke.py data/recordings`. 게임이 자동 서비스에 적용하는 내부 애니메이션 시간과 크루 실수 발생 여부는 확인되지 않음.
- [x] 0.2.14 작업 정차 이상치는 같은 포맷·서킷·차종·성능·모드·피트 설정·정차 중 깃발·작업의 실제 분포에서 판정. 구분 간격은 게임 DB의 최소 작업 지연(현재 500ms). 가장 많이 모인 시간대(동수면 빠른 쪽)의 중앙값보다 max(최소 지연, 4×중앙절대편차)를 초과한 스톱만 지연 의심으로 제외. 첫 표본은 포함하고 새 기록마다 원본 정차/손실 쌍을 다시 평가. 깃발 전환 시 정차 시간은 작업 중 깃발로, 전체 손실은 제외. 이전 녹화는 raw 재생, v6는 진입 전 과거 표본과 실측 쌍을 보관. 바레인 재시작 검증 Green 8.000초(2건), VSC 8.016초(1건). Rust 5·Python 50·웹 7개, 녹화 9개와 Chrome My Race 검증. 재현은 바로 위 녹화/화면 스모크 명령 및 `cargo test`, `python -m pytest`. checklist-vibe CLI 미설치로 fmt/clippy·ruff·mypy·웹 lint를 사용.
- [x] 0.2.15 바레인 타이어 단독 피트에서 플레이어 선두 갭 0으로 누락됐던 순손실을 복원. 동일 상대의 갭으로 측정할 수 없으면, 진입·출구의 두 랩 거리 지점을 트랙에서 모두 통과한 상대 2대 이상의 게임 시간과 비교. 변경 없는 그린 L2 2.783초 정차, 비교 12대·순손실 약 19.49초·P21→P21. 기존 v6까지 원본 재생으로 이력 복원, 진입 시점의 저장 예측은 보존. 재현은 `python tests/recording_library_smoke.py data/recordings` 및 `cargo test`.

- [x] 서킷·UDP 포맷별 정상 피트 손실을 Rust에서 보정해 복귀 순위와 A/B/C에 반영. 원본 녹화와 피트 인덱스에서 재시작 시 복원하며 재생에는 당시까지의 기록만 사용. 합성 경주 24초·28초 → 26초, 다른 트랙 기본값, SC 제외, 구버전 녹화, 되감기를 `python -m pytest -q tests/test_recordings.py`로 검증. My Race는 최근 피트의 예상·실제 순위와 앞뒤 차이를 표시함. 바레인 실경기 완료 표본은 아직 없음.
- [x] UDP 연결 전 스즈카 데모에서 Rust가 정상 완료 랩·피트 손실·타이어·노면·후속 스톱으로 A/B/C의 잔여 시간과 복귀를 계산한다. Python이 가장 빠른 후보를 추천하고 동일 결과를 My Race 비교·휠 미리보기에 사용한다. 재현은 `python -m pytest -q tests/test_my_race.py` 및 웹 빌드 후 `python tests/my_race_smoke.py`.
- [ ] clean stint 선택, compound wear/pace model, 모델 데이터 품질
- [ ] 피트 손실·경기 길이·레이스 규칙 반영
- [ ] Plan A/B/C 시뮬레이션 + Python 정책 비교
- [ ] 전략 결정 DB 기록 + Strategy 탭
**Gate:** 실제/모의 FP 데이터로 설명 가능한 전략 추천

## Phase 9 — 상대 및 실질 순위 예측
- [x] Rust에서 같은 앞뒤 차량의 게임 시간·격차를 0.25초 간격으로 표본화하고 최근 2~10초 추세를 첫 랩부터 표시. 상대 교체·피트·플래시백 후 새 표본을 수집함. 라이브·재생에서 전략 재계산 대기 중에는 마지막 A/B/C와 기준 랩을 읽기 전용으로 표시. 바레인 녹화로 첫 랩, 피트 진입, 6랩 갱신을 Chrome에서 검증. 재현은 `python tests/bahrain_crossing_smoke.py data/recordings/1794655466089283-cab8d764d84f0aae`.
- [x] 데모에서 다섯 수명·페이스 시나리오의 상대 피트 비중, 언더컷·오버컷 한 랩 차이, 피트 사이클 보정 순위·완주 순위 범위를 계산한다. 실제 게임 보정·백테스트는 미완료.
- [ ] 갭/페이스 차이 기반 추격, DRS 진입/추월 구분
- [ ] 상대 다음 1/3/5랩 피트 가능성 모델 + 불확실성
- [ ] Net Position/Projected Finish + 몬테카를로, SC/VSC/우천 반영
- [ ] 예측 성능 리포트: MAE/Brier/calibration + baseline
- [ ] 모델의 미래 데이터 누수 방지 검증
**Gate:** 모의/저장된 GP에서 예측과 실제 결과 교차 검증

## Phase 10 — GP별 Codex
- 바레인 L2 진입 직전 274004ms 실계정 검증 완료. 사용자가 승인한 요약 1회 전송, Codex가 L9 S를 제안. Rust 후속 L18 H 포함 A와 동일 48:35.076/P21. 실행 중인 0.2.17 Chrome My Race에서 재생 확정 후 SQLite의 제안 1행과 라이브 확정 0행 확인. 화면: `output/playwright/B-bahrain-codex-L2.png`.
- [x] 0.2.17 My Race의 Ask Codex → 공식 Python SDK로 GP별 스레드 생성·SQLite 복원 → 제안한 다음 피트 랩·타이어를 Rust A/B/C와 동일 프레임에서 비교 → 휠 확정. 재생은 별도 전략 대화에서 해당 시점까지의 데이터만 사용하며, 재생 확정은 원본에 쓰지 않음. 라이브 확정은 세션·분기별로 복원. 바레인 FP1/결승에서 seasonLink/weekendLink 일치 확인. 두 링크 중 주말 ID가 없는 포맷/세션은 세션 UID로 격리.
- 재현: `python -m pytest tests/test_gp_advisor.py`, `python tests/recorded_ui_smoke.py data/recordings`. 기본 스모크는 모델 응답만 대체(바레인 2랩, L7 M → L17 H 확정), `--real-codex`는 선택한 원본 프레임 요약을 실제 Codex에 전송함. 가상 경기 요약으로 실제 SDK 시작/재개 두 턴 검증. 실물 휠은 미검증. checklist-vibe CLI 미설치로 Rust/Python/프런트 검사 실행.
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

## 2026-11-14 · 게임 UDP 연동
- 기본 웹·앱 창을 라이브 입력에 연결하고 데모는 `?source=demo`에 유지. 게임 2026, 바레인 FP1, HAM P17, 22명, 하드 및 1:37.521 완료 랩을 수신. Chrome에서 Live Timing/My Race 확인. 레이스 A/B/C와 52랩 경기 중 L35 로컬 계획 확정, 구 세션 격리 및 재연결은 합성 패킷으로 검증. 실결승 전략 정확도·원본 녹화/재생·장시간 유실 추정은 미검증.

## 2026-11-12 변경 기록

- Phase 0: 원본 여섯 리포지터리 SHA와 라이선스 및 채택 근거는 docs/REPO_AUDIT.md. React 원본 8개, 2026 Python 파서 48개, 전략 규칙 12개, Pitwall 69개 테스트 통과.
- Phase 1: Windows에서 Start.cmd로 localhost 앱 실행. cargo fmt/clippy/test(1), pytest(웹 4), React lint/test(1)/타입 검사/build, Python ruff/mypy 및 Chrome 1920×1080 E2E 통과. 기존 데모 6개 회귀 통과. CI 정의를 추가했으며 GitHub Actions 원격 실행은 미검증.
- 모의 22대가 표시되고 드라이버 선택이 유지됨. 게임의 2026년 24대 실측, 레코더, DB, 휠의 React 연동은 이후 범위. Phase 2 시작점은 포맷별 길이/버전 검증 및 실제 원본 fixture 대조.
- React A탭을 지정 시안에 맞춰 단일 24행으로 전환함. KIM·SEO는 모의 참가자임. 방송 캡처 기준으로 표와 오른쪽 영역 폭을 약 67:33으로 조정함. 이벤트는 2열×3행으로 표시함. 테스트 재현은 README의 E2E 명령 참고.
- A탭 지도 안의 제목·차량 정보 행을 제거함. 1920×1080에서 상단 헤더 52px, 섹터 순위 153px, 이벤트 패널 461px, 이벤트 제목 29px로 측정됨.
- 이벤트 로그를 열당 10행으로 조정함. 모의 레이스에서 같은 선두 유지 보고와 단순 랩 완료를 생략하고, 새 항목 하나를 1.6초간 강조함. Chrome에서 1920×1080 이벤트 행 높이 42.3px, 순위표 행 높이 40.8px를 확인함.
- 2026-11-13 모의 레이스 이벤트를 열당 8개로 조정하고 각 이벤트에 당시의 상세 정보를 표시함. 1920×1080 한 행 52.9px, 1280×720 한 행 33.8px로 측정함.
- 이벤트 항목 왼쪽에 랩·선수 전용 열을 고정함. Chrome 네 해상도에서 오른쪽 이벤트명과 상세 정보의 시작점 및 겹침 여부를 검증함.
- 선수 칸에 SC·VSC용 아이콘 배지와 황색기·녹색기 아이콘을 추가함. Chrome에서 네 상태와 720p 배지 폭을 검증함.
- SC·VSC를 검은 바탕·황색 테두리 문자판으로 변경함. 황색·녹색·적색 깃발은 배지 전체를 채우는 단색 직사각형으로 표시하며, Chrome 재생 테스트에서 다섯 배지를 확인함.
- 모의 레이스에서 YOU·상대차의 흑백기 경고, 시간 페널티, 드라이브스루·스톱 앤 고를 선수·사유와 함께 표시함. 실게임 흑백기 판정 기준은 미검증.
- 순위·선수 코드를 팀색 배지로 합치고, 선수별 미이행 시간과 DT·S/G를 배지 옆에 표시함. 모의 이행 이벤트로 일부 또는 전부 해제되는 동작과 네 해상도에서의 24행 표시를 검증함.
- A탭 PEN 독립 열과 메인·섹터 공용 팀색 순위 배지 적용. 스즈카 구간 거리별 색상과 트랙 위 원형 드라이버 마커 적용. 10Hz 모의 좌표를 보간하고 Chrome E2E에서 2초간 마커 좌표 갱신 60.0회/초 및 네 해상도 24행 검증.
- 스즈카 지도를 T1 우하단 방향으로 조정하고 주요 코너 12곳, 입체교차, 체크 스타트선, 2026 일본 GP 기준 SM 2구간을 노면에 표시함. 구간 끝은 도면 근사값. Chrome E2E 네 해상도 통과, 지도 마커 60.0회/초 측정.
- BoxBox 2026 결과 23라운드와 리플레이 지도 좌표를 수집하고 A탭 상단 선택에 연결함. Chrome에서 23개 서로 다른 경로, 선택별 24대와 움직임, 스즈카 전용 오버레이, 네 해상도 표시를 검증함.
- BoxBox 2026 결과 페이지의 상세 도면 23장을 A탭에 적용하고 각 이미지의 노면에 모의 차량 좌표를 보정함. Chrome에서 23장 디코딩·전환, 차량 이동과 네 해상도 검증 완료.
- A탭에서 안내 박스와 지도 위 흰 섹터 라벨을 마스킹하고 가려진 색선을 연결함. Chrome에서 23개 서킷 전환 및 마커 동작 확인.
- 남은 스피드 트랩·오버테이크 점을 복원된 노면으로 덮고, 23개 도면의 테두리를 섹터별 경고색으로 표시함. 스즈카에서 S2/전체 황색·적색·해제 픽셀 비교와 23개 서킷 전환 확인. 몬차의 잘못 축소된 마커 경로도 재정렬함.
- 지도 경고 테두리와 플래그 배지의 채도·밝기를 높이고 경고 테두리를 굵게 표시함. Chrome에서 구간·전체 황색, 적색과 해제 시 원래 도면 복원을 검증함.
- 옐로우는 형광 노랑, SC·VSC는 전체 서킷 밝은 주황으로 표시하고 레드 색을 유지함. 경고에만 굵은 테두리와 고정 발광 효과를 적용하고 Chrome에서 범위·색·해제를 확인함.
- A탭 PEN 열을 제거하고 오른쪽 패널을 확장함. 이벤트는 열당 6개, 메인·섹터 순위는 같은 크기의 RankDriver 배지를 사용함. 1576×883에서 지도 572×414px, 이벤트 행 42.7px를 측정했고 Chrome 5개 해상도에서 배지 크기·팀색과 24명 표시를 검증함.
- OpenF1 일본 GP 결승(session_key=11253)의 팀색 11개를 적용하고 HAD·LIN의 소속을 정정함. 가상 팀은 보라색 #9856EF. Chrome 1576×883에서 메인·섹터 배지, 이벤트와 지도 색상을 대조함.
- A탭 배지 표시색을 사용자 캡처에서 추출함. 레드불·페라리·알핀·윌리엄스 약자 칸은 흰색, 레이싱 불스 순위 칸은 흰색으로 고정함. 원본 타이밍 색은 유지하고 Chrome에서 24대 렌더링을 확인함.
- 애스턴 마틴 주행 배지는 밝은 초록과 흰 약자 칸으로 표시함. 선수별 리타이어 상태를 순위·섹터·이벤트·지도에 연결함. 모의 ALO 피트인, 103초 리타이어, 팀 동료 YOU 및 다음 레이스 색 복원을 Chrome에서 검증함.
- 2026-11-13 B탭 24대 모의 프레임, P8→P7, 21랩 하드→19랩 확정/취소, 출발 전 3회 교체·DNF와 A탭 회귀 검증. Windows Rust 2개·Python 24개·프런트 5개 통과. Chrome 1920×1080·1576×883 캡처는 output/playwright에 저장. SDL 가상 휠 버튼 55/56·POV·확정/취소 및 매핑 복원 통과. 실물 휠 미연결.
- React A/B의 탭·서킷·계기·전략 조작·휠 매핑은 영어로 표시하고 경기 이벤트·예측 설명은 한국어로 유지함. Windows 로컬 Roboto Condensed·Roboto Mono·Noto Sans KR 적용. 프런트 lint·단위 5개·타입 검사·빌드, Chrome A탭 5개 해상도 및 B탭 1920×1080·1576×883 가상 휠 회귀 통과. output/playwright의 A/B 캡처 4장 갱신.
- React B탭 Pace Forecast의 Chase·Defend에 공용 RankDriver 배지 적용. Chrome에서 상대 교체·선두/최하위 빈칸과 734×883 팀색·배지 겹침 검증. 재현은 tests/my_race_smoke.py.
- 선수 배지 24개의 약자를 고정폭으로 맞추고 YOU 강조 테두리로 생긴 가로 1px 이동을 제거함. 이벤트 로그에도 현재 순위·팀색 공용 배지를 적용하고 734×883에서 본문 간격을 3→8px로 조정함. tests/web_smoke.py로 6개 해상도의 이름칸 경계·문자 폭·중앙 정렬 검증. 기존 단일 이벤트 갱신 검사는 첫 실행 실패 후 재실행 통과. B탭 회귀·웹 단위 5개·lint·빌드 통과.
- A탭 순위 숫자를 배지의 실제 색 면 중앙에 정렬하고 타이밍 표·주변 패널 글꼴을 축소함. 스틴트별 사용 랩·컴파운드 3칸, 차량별 섹터당 모의 미니섹터 8칸과 완주 구간 시간, 플래그 경고광 블러 4→2 반영. 734×883 HAM 순위 좌우 여백 5.50/5.52 CSS px. Python 26개, 웹 단위 5개, A/B 브라우저 회귀 통과. output/playwright/A-live-734x883-SC.png 참고.
- 447×883 Chrome에서 이름판의 소수점 치수와 행 간격을 정수화함. 고정 모의 프레임에서 24명 이름판 27×18 CSS px, 1배 캡처 실채움 18px, 1.45배 캡처 25~26px 확인. 447px 뷰포트 회귀를 tests/web_smoke.py에 추가함. 프런트 단위 5개·lint·build 및 A탭 회귀 통과.
- My Race에서 수동 경기 상태 선택기와 비교 팝업을 제거함. 데모 한 주기는 그리드 18초, 기존 주행 샘플 108초, 플레이어 DNF 10초임. 새 경기에서 확정 계획을 초기화함. 프런트 빌드 후 `tests/my_race_smoke.py`로 자동 전환·SDL 가상 휠과 두 화면 크기를, `tests/demo_panels_smoke.py`로 마우스 조작을 재현할 수 있음. 실물 휠·게임 UDP 검증은 남아 있음.
- [x] 0.2.16 마지막 녹화를 마이레이스에 복원할 때, 녹화 시작 전에 끝난 원본으로 이전 실측을 재계산함. 일반 리플레이와 진입 당시 저장 예측은 보존. 바레인 그린 자동 피트의 전체 손실은 타이어 19.486초(1건), 앞날개 추가 25.184초(1건). 정차는 각각 2.783초(1건), 8.000초(2건). 녹화 10개 회귀는 `python tests/recording_library_smoke.py data/recordings`. 실서버 Chrome My Race에서도 P22/P22와 전체 손실 각 1건 확인. checklist-vibe CLI 미설치, Rust clippy·테스트와 Python lint·타입 검사·테스트 실행.

- [x] 0.2.18 출발 전 전략. Rust가 FP 결승선 통과 시점의 연료·네 바퀴 마모와 같은 세트의 유효 랩을 수집함. 동일 시즌·주말·서킷의 이전 FP 녹화에서 개인/필드·노면별로 집계. 마이레이스에 권장 연료(예비 1랩), 게임 탑재량, 컴파운드별 페이스·마모·랩타임 변화와 가용 세트로 완주하는 일정을 표시함. 같은 GP의 Codex가 해당 요약과 출발 후보를 받아 제안하고 휠로 확정 가능.
- 바레인 FP1은 개인 0랩 / AI 136랩. 결승 녹화 17,000ms에서 1.217kg/랩, 29랩 출발 36.6kg, 실차 설정 43.3kg. 실제 Codex 1회 응답과 재생 확정은 H → L14 M → L23 S. 세 후보 모델 시간이 같았음. 새 실경기에서 개인 소비 및 완주 잔량을 대조하는 검증은 남아 있음.
- 재현은 프로젝트 가상환경에서 `python tests/bahrain_grid.py`와 `python tests/recorded_ui_smoke.py data/recordings`. 기본은 로컬 검증. Rust 7 / Python 54 / 웹 8 테스트, Chrome 재생과 8765 배포 서버의 그리드 스냅샷 확인.

- [x] 0.2.19 출발 연료 추천을 제거함. 출발 전 일정은 해당 GP의 노면·컴파운드별 FP 페이스 변화와 가용 세트로 평가함. 표본이 없으면 계산 대기, 최저 예상 시간이 같으면 공동 후보를 모두 표시함. 레이스 중 게임 권장 피트 창을 A/B/C의 탐색 제약에서 제외하고 게임의 예상 복귀 순위가 자체 예측을 덮어쓰던 경로를 제거함. 과거 기록의 당시 값은 보존함.
- 바레인 L2 진입 직전 데이터에서 게임의 피트 창을 L2 또는 L28로 바꿔도 앱의 A/B/C와 복귀 예측 동일. 실제 추천 A는 L9 S → L18 H. 2025·2026 UDP, Python 54개, Rust 7개, 웹 8개, Chrome 재생 및 휠 확정 검증 완료.
- Kev 0.8B 고정판을 바레인 FP1에서 오프라인 평가함. 차량별 첫 유효 3연속 동일 세트 랩을 골라 앞 2랩으로 다음 깨끗한 랩이 직전보다 0.5초 넘게 빨라지는지, 비슷한지, 느려지는지 분류. 후보 순서를 세 번 회전한 평균 점수로 17건 중 11건 적중. 직전 랩 유지 11건, 앞 2랩 평균 10건. 경기 전략 채택 근거 부족으로 엔진에 연결하지 않음. 재현은 프로젝트 Python으로 `tests/evaluate_kev_pace.py --kev-python <Kev Python> --hf-cache <모델 캐시>`.

- [x] My Race 가독성. 순위·앞뒤 간격은 각 열의 실제 폭에 맞춰 표시하고 추천 피트 일정, 서비스별 예상 복귀와 손실, A/B/C를 순서대로 배치함. 바레인 재생의 1920×1080·1280×720·819×883·447×883에서 0~9 각 숫자를 반복한 다섯 자리 초와 소수점·단위까지 열 경계 검사. 재현은 python tests/recorded_ui_smoke.py data/recordings. 실서버 720p·1080p에서 하단 조작 버튼 위치 확인. 웹 lint·단위 8개·빌드 통과.

- [x] 0.2.20 My Race 순위·앞·뒤 숫자를 같은 크기로 표시하고 긴 간격에만 함께 축소함. 추천안과 날씨를 나누고 전체 피트 일정 및 남은 스톱 수, 세트 수명·재고·노면에 따른 위험 랩을 표시함. 예측값은 유지하면서 반복적인 수신 상태 설명을 제거함. 바레인 1랩 C는 L9 소프트 수명 초과, A는 L9 S → L18 H로 확인. 재현은 tests/recorded_ui_smoke.py, tests/bahrain_crossing_smoke.py 및 tests/my_race_smoke.py. 새 Rust 엔진은 다음 서버 시작 시 적용되고 0.2.19에서도 확인 가능한 현재 세트 위험을 표시함.
- [x] My Race의 독립 Projected pit exit 행을 제거하고 이번 랩·다음 랩 복귀 예상을 Choose a pit lap에 통합. 피트 진입 또는 계산 대기 시 보관한 예측도 해당 영역에 표시. 바레인 2→3랩·피트 진입·황기·일시정지 브라우저 회귀와 웹 lint·단위 8개·빌드 통과.
- [x] My Race 서비스 비교 표를 피트 랩 선택 아래로 이동. 두 작업이 이번 랩 예측과 같은 순위면 순위 열을 접고, 차이가 있거나 일부 값이 없으면 개별 순위를 표시함. 바레인 실서버 Chrome에서 P22 중복 제거·720p/1864×883 조작 버튼 위치 확인. 웹 lint·테스트 8개·빌드 통과.
- [x] My Race의 피트 서비스별 예상 비교 표를 제거함. 8765 Chrome 및 바레인 녹화 재생에서 Choose a pit lap의 이번·다음 랩 복귀 예상과 서비스 표 부재 확인. 웹 lint·테스트 8개·빌드 통과.
- [x] 0.2.21 Choose a pit lap의 이번·다음 랩 버튼에 타이어 교체와 앞날개 추가 예상 복귀 순위·피트 손실을 각각 두 줄로 표시. 다음 랩은 Rust의 랩별 상대 예상 시각과 녹색기 서비스별 손실로 계산. 바레인 녹화 복원 및 8765 Chrome에서 두 선택지 각각 P22·19.5초 / P22·25.2초, 720p 및 1864×883 줄 너비 확인. pytest 56·Rust 7·웹 8, 녹화/랩 경계 브라우저 테스트 통과.

- [x] 0.2.22 첫 방문 F1 피트 손실을 설치된 28개 레이아웃의 리미터 표식·피트 경로·본선 VP 기준 곡선과 실제 세션 제한속도로 추정. 검증된 같은 서킷·날씨·서비스·중립화 상태의 실측으로 보정. 녹화 v8은 날씨를 보존하고 이전 녹화의 원래 예측과 구분. 바레인 초기 추정 18.389초, 실측 타이어 19.486초·앞날개 포함 25.184초. 게임 내부 전략 계산 및 모든 서킷의 실주행 오차는 미검증.
- [x] My Race의 Plans 제목·타이어·화살표 배치, 잔여 시간, 예상 마모율과 수명 초과율을 수정. 마지막 녹화 화면에서도 플랜·라이벌 상세와 마우스 편집·확정 및 재생용 Codex 요청 지원. 재현은 `python tests/bahrain_crossing_smoke.py data/recordings/1794655466089283-cab8d764d84f0aae`, `python tests/recorded_ui_smoke.py data/recordings`. 외부 응답 대역 사용. Rust 8, pytest 57, 웹 8 통과.
- [x] My Race 주행 플랜 표에 전체 교체 일정·첫 피트 윈도·예상 완주 순위·위험을 정렬함. A/B/C 선택 뒤 휠 확정 한 번으로 적용하고 좌측 입력으로 편집, 우측 입력으로 상대 상세 열기. Codex 요청 버튼을 Request Codex plan으로 명시. 웹 lint·단위 8개·빌드 및 tests/bahrain_crossing_smoke.py, tests/recorded_ui_smoke.py, tests/my_race_smoke.py 통과. 8765 Chrome 1864×883에서 P8–9와 C 마모 경고 표시 확인.
- [x] 0.2.23 경기 추천은 재고·노면상 가능한 A/B/C에서 순위 상승 시나리오 수, 평균·최악 완주 순위, 수명 부족과 시간 순으로 선정. 바레인 녹화 283000ms P8에서 A/B는 2/5건, C는 3/5건으로 C 추천. 앱 Settings의 Codex 모델·추론 설정은 로컬 SDK 카탈로그를 사용하고 SQLite에 보존. 실계정의 8개 모델 표시와 격리된 DB 저장, 모의 SDK 요청·재개 확인. 한국어 피트 MFD의 선택 줄·컴파운드를 판독하며 다음 타이어 설정. 바레인 실제 2랩 M→H, 앞날개 수리 아니요 확인. 후속 스톱 전환은 모의 정차 테스트. Rust 8개, Python 60개, 웹 8개·빌드, 바레인 녹화 및 SDL 휠 UI 스모크 통과. 실게임 추가 검증 대상은 S/I/W 및 실제 두 번째 정차.
- [x] 로컬 F1 25 시즌팩에서 SimHub(UDP 20777)가 My Race(127.0.0.1:20778)로 전달하도록 설정. Start.cmd용 .env에 수신 포트를 저장. SimHub 로그와 /api/health에서 실게임 2026 패킷 2,151→7,323건, Live, 녹화 드롭 0건 및 PXN GT One 로드 확인.
- [x] 0.2.24 Race Events는 최근 6개를 한 열에 표시. 실게임 출발등 카운트 및 플레이어가 관여하지 않은 추월 제외, PENA 대상·처분·시간·사유·관련 차량·발생 랩과 DT/SG 이행 반영. 바레인 녹화 1794724994897316-ae6be442029afb29 110초에 NOR 경고·상대 RUS를 Chrome에서 확인. cargo fmt/clippy/test(8), Python pytest(60)·ruff·mypy, 웹 lint/test(8)/build 통과. 전체 tests/web_smoke.py는 447px 순위표의 미이행 페널티 표시가 배지 위치를 밀어 정렬 검사에서 중단. 체크리스트 CLI 미설치. 기존 SimHub 포워딩으로 8765 서버 교체.
- [x] 0.2.25 Live Timing 최고 랩은 보라색 글자. S1/S2 현재 랩과 마지막 완료 랩 S3는 유효 개인·필드 기록으로 색을 산정하고 8칸 거리 진행은 중립색으로 표시. 몬차 FP1 1794726558388733-644c7a3ab57cf2a8 종료 시 STA 1:21.994 및 S3 26.931의 Chrome 계산 색과 배경 확인. 실주행은 BUTN 상위 12비트 상승 에지를 전용 큐로 전달하고 UDP/직접 입력 중 하나만 사용. 명시적 재생·데모는 SDL 사용. Rust 8, Python 61, 웹 8, fmt/clippy/ruff/mypy 및 tests/my_race_smoke.py 통과. 실제 8765 서버 SimHub 경유 Live 확인. 휠 물리 버튼은 사용자가 게임 안에서 지정 예정. checklist-vibe CLI 미설치.
- [x] UDP Action 1/2/3을 로터리 절대 위치의 Live Timing/My Race/Session Analysis 바로가기로 변경. 4 취소, 5/6 상하, 7/8 좌우, 9 확정. 기존 직접 입력 순환 바인딩은 호환. 웹 lint·8개 단위·build 및 실물 휠 입력을 대역 처리한 check_live_sessions의 3→1→1→3→2 통과. 실사용 백엔드 재시작 없이 정적 프런트 배포. FN 레이어와 실물 버튼 지정은 별도 게임 프로필 설정.
- [x] My Race 주행 중 A/B/C 행에 마우스를 올리거나 휠로 이동하면 해당 행 아래에 교체 일정이 열린다. 선택 시 일정을 고정하고 같은 행의 확정으로 첫 교체 타이어를 실시간 MFD에 전달한다. Box this lap/next lap 즉시 확정 경로를 제거하고 두 랩의 서비스별 복귀 순위는 조회용으로 유지했다. MFD는 게임 창과 목표 컴파운드의 안정된 판독을 확인한다.
- [x] 바레인 녹화의 라이브 WebSocket 경로에서 Plan B(8랩 S) 미리보기·취소 0회, 확정 시 MFD 대역에 S 1회, 녹화 모드 추가 전송 0회를 확인했다. 재현은 `python tests/bahrain_crossing_smoke.py data/recordings/1794655466089283-cab8d764d84f0aae`. 웹 단위 테스트 8개, 린트·빌드 및 실물 장치를 제외한 Python 테스트 61개 통과. 실게임 일시정지 중 서버를 교체하고 마지막 바레인 5/29랩 플랜의 로딩을 확인했다. 이번 실행에서 실제 게임 MFD의 타이어 변경은 미검증이다.
- [x] 0.2.26은 LapData 거리·시계로 섹터당 8개 구간의 통과 시간을 보간해 세션 최고·개인 개선·완료를 비교한다. My Race는 기본 페이스의 예상 완주 순위, 행 안의 스틴트·복귀 교통·위험 요약, 개별 피트 랩 박스를 표시한다. 상세 화면·중복 피트 손실·게임 피트 윈도우·주행 중 Custom stop을 제거했다. UDP 1 이전 탭, 2 다음 탭, 3 미할당. Rust 9·Python 61·웹 8, fmt/clippy 및 Chrome 가상 휠과 tests/bahrain_crossing_smoke.py 통과. 8765에 적용하고 바레인 1794732144522972-5b1b502b3a138f2e의 570000ms에서 P5/P5/P5와 7·8랩 피트 박스를 확인했다. 마지막 8랩 스냅샷은 활성 차량 2대의 비교 갭이 없어 최신 예측 대기. 실물 버튼 재시험과 checklist-vibe CLI는 미실행.
- [x] 바레인 1794733579218090-b0df7ec70998b0e3 최종 2/29랩 P10, A/B/C 시나리오 모두 [11,14,17,19,20], 현재 스틴트 비교 표본 0. My Race에 현재 순위와 잠정 완주 예상을 함께 표시. 게임 MFD는 확정 명령을 직렬화하고 최신 목표만 실행하며 안정된 화면 3회 판독·좌우 개별 이동·목표를 지나친 경우 직전 선택 복원 확인을 적용. Python 63, 웹 8, 브라우저 바레인 확정 경로, ruff/mypy 및 웹 빌드 통과. 실사용 8765 서버 교체 후 현재 P10 → 잠정 완주 예상 P17 확인. 당시 풀웻 직전 MFD 화면과 수정 후 실게임 연속 변경은 미검증. checklist-vibe CLI 미설치.
- [x] My Race 수동 Edit Strategy 제거. A/B/C 호버·휠 이동은 미리보기, 클릭·휠 확정 한 번으로 표시 일정 적용. FP 기반 그리드 추천도 직접 선택 가능. 같은 랩의 A/B/C와 추천을 유지하고 세션·날씨·플래그·타이어·피트·확정 일정 변경 시 갱신한다. 실시간 피트 복귀값은 매 프레임 갱신. 바레인 1794733579218090-b0df7ec70998b0e3 1초 샘플 187개에서 랩 내 추천·일정 변경 60→6회. 웹 lint/test/build, tests/my_race_smoke.py 및 tests/bahrain_crossing_smoke.py(호버 입력 0·클릭 MFD 대역 입력 1) 통과. 실물 MFD 전환은 이번 검증 제외. checklist-vibe CLI 미설치.
- [x] Settings → Race radio의 Microphone mode를 켜면 UDP 3으로 한국어·영어 질문을 받고 현재 경기 스냅샷을 영어 무전으로 읽는다. 끄면 UDP 3은 기존 Codex 플랜 요청으로 복귀한다. 실게임 11랩 “Driver in front” → “Bottas, 9.8 seconds ahead.” 마이크의 발화 종료 추정부터 WASAPI 출력 파형까지 3.119초. 원본 LapData에서 같은 시점 9,800ms 확인. 현재 지원 범위는 피트·앞날개·갭·타이어·날씨·순위 조회이며 자유 대화 및 음성 전략 변경은 미구현.
