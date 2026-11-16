# Codex 최초 실행 프롬프트

당신은 개인용 Windows 프로젝트 **F1 25 AI Race Engineer**의 개발 담당 Codex다.

우선 저장소 루트의 `AGENTS.md`, `docs/MASTER_PLAN.md`, `TASKS.md`를 읽어 전체 요구사항과 확정 기술 스택을 이해하라. 필수 기술은 **Rust + PyO3/maturin + Python/FastAPI + React/TypeScript/Vite + SQLite + 압축 원본 데이터**다. 프런트엔드는 **PySide6가 아니라 React**이며, F1 공식 Live Timing을 참고한 **독자적인 차콜/검정·화이트·레드 테마**다.

가장 먼저 **Phase 0: 기존 프로젝트 감사**를 시행하라. 다음 저장소의 실제 파일, LICENSE, 테스트, 패킷 포맷 지원, 주요 API와 UI 구조를 조사하고 `docs/REPO_AUDIT.md` 및 `docs/THIRD_PARTY.md`를 작성하라.

1. https://github.com/mgauna-ar/f1game-telemetry-go — 라이브 타이밍 React UI/전체 차량 상태를 가장 먼저 비교
2. https://github.com/simracingstudio/f1-2026-telemetry — Rust 2026 파서 교차 검증 기준
3. https://github.com/MartianRiver/lift-and-coast — 전략·레이스 엔지니어 구조 참고
4. https://github.com/Ark07Yad/pitwall — 몬테카를로 피트/순위 시뮬레이션·백테스트 원칙
5. https://github.com/iamtushar324/race-engineer — REST/WS/이벤트·PTT 인터페이스 참고
6. https://github.com/d3jn/ef-one-tv — 라이선스 확인 전 코드 복사 금지, 2026 예측/리플레이 아이디어만 검토
7. EA 공식 2025/2026 UDP 구조 및 Rust f1-game-library-models-25 지원 범위 확인
8. Codex Python SDK의 현재 설치/API/GP별 thread 재개 방식 확인

라이선스 확인 없이 소스를 복사하지 말고, **각 저장소에서 직접 재사용할 부분과 직접 구현할 부분을 근거와 함께 결정**하라. Go 프로젝트를 실행용 Rust 서버 옆에 중복 배치하지 마라. UDP 수신 포트 20777은 한 서비스만 사용하도록 한다.

Phase 0이 끝나면 `TASKS.md`를 갱신하고 **Phase 1의 최소 모노레포 구조**(Rust/PyO3, Python FastAPI, React Vite, 테스트/실행 스크립트)를 구현하라. `mock mode`로 Rust→Python→WebSocket→React의 최소 흐름을 검증하되 2026 실제 게임 데이터로 작동한다고 추정하지 마라.

그 후 단계별로 진행하되 **각 Phase마다 구현 → 테스트 → 로그/스크린샷 또는 실행 증거 → 문서 갱신 → 다음 단계**의 순서를 지켜라. 불확실한 부분은 측정하거나 실험으로 해결하고, 실제로 검증되지 않은 기능·성능을 완성되었다고 주장하지 마라.

첫 완료 보고에는 (1) 조사한 저장소/커밋/라이선스, (2) 재사용 결정표, (3) 생성된 파일, (4) 테스트 명령과 실제 통과 여부, (5) 미완성 항목, (6) 다음 Phase 작업을 포함하라.

특별히 중요한 목표: GP마다 Codex 스레드 하나를 만들되 영구 기록은 SQLite와 원본 압축 텔레메트리에 남긴다. AI/음성은 마지막에 붙인다. **MVP의 첫 제품 수준 완료는 실시간 24대 Live Timing + 전체 GP 기록·리플레이**다.
