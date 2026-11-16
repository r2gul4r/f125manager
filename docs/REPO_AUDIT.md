# Phase 0 · 소스 감사

2026-11-12에 아래 여섯 저장소를 별도 작업 폴더에 클론함. Windows에서 실행한 범위와 소스만 검토한 범위를 구분함.

| 원본 (고정 SHA, 커밋 날짜) | 라이선스 | 실제 확인한 경로와 결과 | 채택 결정 |
|---|---|---|---|
| [F1 Telemetry Go](https://github.com/mgauna-ar/f1game-telemetry-go/tree/f318f82ef6d87c497fe166d68079de7c1689d44e), 11-07 | MIT | frontend/src/components/LeaderboardTower.tsx와 테스트 8개 통과. props와 Zustand 구독을 병용함. 원본은 11대씩 두 열로 나눔. Mock 경기로 Windows Chrome에서 22행을 표시함. | React 타워·필요한 하위 구성요소 직접 편입. 서버는 Rust/Python. BattlePanel 및 LivePitStrategy는 Phase 6/8 검토. Go UDP 서버는 구동하지 않음. |
| [f1-2026-telemetry](https://github.com/simracingstudio/f1-2026-telemetry/tree/1f82d688e3859c2f12bb85bf7d5573f6a8af718e), 09-21 | MIT | f1_2026_telemetry/packets.py 및 tests/test_packets.py. 해당 저장소 루트에서 python -m pytest -q, 48개 통과. 구조체 크기·합성 패킷 결과. | 2026 파서 비교 기준. Rust 수신 경로에 Python 파서를 중복 배치하지 않음. |
| [Lift and Coast](https://github.com/MartianRiver/lift-and-coast/tree/87985cbb779a20a1e287907144539b8bff0c64a3), 10-19 | MIT | engineer/strategy.py의 날씨·스틴트 규칙, engineer/radio.py 검토. jellyfish·wordfreq를 설치한 감사 환경에서 python -m unittest -q tests.test_strategy, 12개 통과. | 정책과 무전 트리거 설계를 참고. 음성 의존성에 macOS/ARM 조건이 있어 Windows 런타임으로 통째 편입하지 않음. |
| [Pitwall](https://github.com/Ark07Yad/pitwall/tree/64003485c824973986d598afbc0d321ad976d8a3), 11-04 | MIT | src/pitwall/sim/race.py·decision.py 검토. PYTHONPATH=src에서 pytest tests/test_sim.py tests/test_scorecard.py, 69개 통과. 실제 F1 피드 기반 모델. | 시드 고정·순위 분포·예측 사후 평가 방식을 참고. EA 게임에 실측 보정하기 전에는 이 모델의 수치를 사용하지 않음. |
| [Race Engineer](https://github.com/iamtushar324/race-engineer/tree/42cf7f7723cdfd5491a69633785fee946250d472), 05-18 | MIT | telemetry-core/internal/api/live_ws.go, internal/ingestion/check_dual_ptt_test.go 및 API 테스트를 정적 확인. 외부 음성 서비스 미실행. | WS 재연결·이벤트·PTT 설계만 참고. 원격 AI 의존성을 Phase 1에 도입하지 않음. |
| [ef-one-tv](https://github.com/d3jn/ef-one-tv/tree/5e45a42abab9959141787985b6b2aba496b39509), 09-13 | 명시적 라이선스 미확인 | recorder.py·mock_sender.py의 timestamp와 datagram 길이를 보존하는 기록 방식 및 2026 overlay 구조 정적 확인. | 아이디어만 참고. 소스/에셋 미편입. |

## 포맷 교차 확인

[EA 공식 게시물](https://forums.ea.com/blog/f1-games-game-info-hub-en/ea-sports%E2%84%A2-f1%C2%AE25-2026-season-pack-udp-specification/12187347)에 2025 v3·2026 Season Pack·Season 8 업데이트가 따로 있음. 2025 v3 및 초기 2026 PDF는 [출처가 표시된 사본](https://github.com/bobbythehuman/Race-Telemetry-Package/tree/19c6b8d00d2965fe7f4cf4648fc314b7a103fbc8/Supporting_Docs)에서 본문을 대조함. 재배포하지 않음.

| 포맷 | 차량 슬롯 | Motion / Session / Lap / Participants (바이트) |
|---|---:|---|
| 2025 | 22 | 1349 / 753 / 1285 / 1284 |
| 2026 | 24 | 1325 / 926 / 1399 / 1470 |

Phase 2에서는 실제 녹화와 Season 8 문서까지 별도로 대조해야 함. Rust crate f1-game-library-models-25 0.5.0의 [원본 SHA](https://github.com/11bthornton/f1-game-library-models/tree/90da18dface17693cb6f77cac9b608496d8cffc9)에서 패키징된 src/lib.rs는 MAX_CARS_IN_SESSION=22, LAP_DATA_PACKET_SIZE=1285를 사용함. Cargo 메타데이터 license는 unknown이나 패키지 LICENSE에 MIT 허가문, NOTICE에 Unicode 고지 있음. 2025 전용 비교 후보로 두고 2026용으로 채택하지 않음.

## GP별 Codex 스레드

별도 감사 venv에 openai-codex 0.167.2(Apache-2.0) 설치. openai_codex/client.py의 Codex.thread_start와 thread_resume(thread_id, …)가 thread/start 및 thread/resume RPC를 호출하는 것을 확인함. 인증·유료 호출·실제 스레드 재개는 Phase 10 과제임. 런타임 의존성에서 제외함.

## Windows 모의 실행

Rust 정렬/간격 계산 → PyO3 → FastAPI /ws/demo → 원본 React 타워 경로 검증. Phase 1에서 표의 입력은 스즈카 합성 데이터임. 게임 포트·실물 휠·GP 저장 성능은 검증 범위 밖임.
