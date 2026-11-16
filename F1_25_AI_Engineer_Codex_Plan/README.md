# F1 25 AI Race Engineer — Codex 전달용 개발 계획 패키지

이 패키지는 **소스 코드가 아니라 Codex에게 넘길 상세 개발 계획과 작업 지침**이다.

## 시작

1. 이 폴더를 새 프로젝트 루트에 복사한다.
2. Codex를 프로젝트 루트에서 실행한다.
3. `CODEX_START_PROMPT.md`의 본문을 첫 메시지로 전달한다.
4. Codex는 `AGENTS.md`와 `docs/MASTER_PLAN.md`, `TASKS.md`를 읽고 **Phase 0부터** 개발한다.

## 구성

- `docs/MASTER_PLAN.md`: 전체 요구사항, 역할 분담, 데이터 계약, DB, UI, 기존 저장소, 13개 Phase
- `AGENTS.md`: 개발 담당 Codex의 상시 작업 규칙
- `TASKS.md`: Phase별 체크리스트·완료 조건
- `CODEX_START_PROMPT.md`: 복사해 Codex 첫 메시지로 사용할 프롬프트
- `docs/REPO_AUDIT.md`: Phase 0 외부 저장소 검증 결과 기록 템플릿
- `docs/THIRD_PARTY.md`: 실제 코드 재사용 시 저작권/라이선스 기록

참고: 계획서 속 기능·성능 주장은 **설계 목표**와 **실측 검증 사실**을 구분하며, 코드 실행은 아직 하지 않았다.
