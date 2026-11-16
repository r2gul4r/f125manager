# 저장소 감사 기록 — Phase 0 템플릿

> 이 문서는 아직 실제 코드를 로컬에서 실행·검증하지 않은 **사전 웹 조사** 상태다. Phase 0을 실행한 Codex가 실제 SHA, 라이선스, 테스트 결과를 채워야 한다.

| 저장소 | 사전 조사 결과 | SHA (실사 후) | 실제 실행 결과 | 결정 |
|---|---|---|---|---|
| mgauna-ar/f1game-telemetry-go | MIT, Go + React, 피트월/AI/리플레이 | 미확인 | 미실행 | UI/데이터 모델 우선 감사 |
| simracingstudio/f1-2026-telemetry | MIT, 2026 포맷 Python 파서 및 크기 테스트 | 미확인 | 미실행 | Rust 검증 기준 |
| MartianRiver/lift-and-coast | MIT, AI 레이스 엔지니어·전략 구조 | 미확인 | 미실행 | 전략 이벤트 참고 |
| Ark07Yad/pitwall | MIT, 실제 F1 몬테카를로 전략 엔진 | 미확인 | 미실행 | 모델/백테스트 원칙 참고 |
| iamtushar324/race-engineer | MIT, Go+React+Python 음성, REST/WS | 미확인 | 미실행 | 계약/이벤트 참고 |
| d3jn/ef-one-tv | 라이선스 파일 미확인 | 미확인 | 미실행 | 코드 복사 금지, 원칙 참고 |
| f1-game-library-models-25 | Rust 2025 파서, 2026 미검증 | 미확인 | 미실행 | 버전 확인 후 선택 |
| openai/codex sdk/python | Python SDK thread_start/resume | 미확인 | 미실행 | Phase 10에 채택 |

## 각 저장소 점검 체크
- [ ] clone, SHA, 마지막 업데이트 확인
- [ ] LICENSE / 서브라이선스 / 에셋 권리 확인
- [ ] README 기능과 실제 API/코드 교차 확인
- [ ] 테스트/예제 실행 방법 및 성공·실패 로그 기록
- [ ] 버전: 2025/2026/2026 업데이트 여부
- [ ] 외부 통신/키/스토리지 요구사항 확인
- [ ] 복사 가능한 파일·의존성·변경 범위 기록
- [ ] 직접 재사용/포팅/아이디어 참고/제외 결정
