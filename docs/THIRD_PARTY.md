# 외부 코드 및 데이터

Windows 앱 창은 [pywebview 6.2.1](https://pypi.org/project/pywebview/6.2.1/) 배포판(BSD-3-Clause)과 설치된 Microsoft Edge WebView2 Runtime을 사용한다. Python 패키지 버전은 requirements-web-lock.txt에 고정했다.

- [mgauna-ar/f1game-telemetry-go](https://github.com/mgauna-ar/f1game-telemetry-go/tree/f318f82ef6d87c497fe166d68079de7c1689d44e), MIT © 2025 f1game-telemetry-go contributors. 편입 파일은 web/src/vendor/ 아래에 원본 frontend/src 경로대로 보존함. 예외적으로 utils/parseDriverName.ts는 store/useTelemetryStore.ts의 같은 함수를 분리했고, components/LeaderboardTower.tsx의 해당 import를 교체함. 24대 단일 표는 앱 레이아웃을 사용하고 원본 utils/formatters.ts로 랩·갭·섹터를 표시함. 원본 고지는 web/src/vendor/LICENSE. React 및 React DOM·Zustand(MIT), Lucide React(ISC, Feather 계열 MIT 고지 포함) 등 npm 배포물은 web/package-lock.json에 고정. 원본 아이콘 브랜드·게임 로고·폰트 파일은 따로 가져오지 않음.
- [bacinger/f1-circuits](https://github.com/bacinger/f1-circuits/tree/8094e957b8d6aa8b9f4510c93968556cccd30e02), MIT © 2019–2025 Tomislav Bacinger. assets/f1-circuits/jp-1962.geojson는 원본 데이터 그대로임. LICENSE.md와 SOURCE.txt 동봉. React와 기존 데모가 같은 좌표를 사용함. React 빌드 고지는 web/public/licenses/f1-circuits.txt에 포함함.
- 원본 고지를 프런트 빌드에도 포함함. 자산 재사용 범위는 이 목록과 vendor 경로로 한정함. 나머지 감사 대상은 docs/REPO_AUDIT.md 참고. 직접 검증한 것은 출처·라이선스·선택한 테스트이며 별도의 보안 감사나 실제 게임 주행 검증은 수행하지 않음.

## 2026 서킷 카탈로그

[BoxBox 한국어 결과](https://f1-boxbox.com/ko/formula-1/2026/results/japan)의 23개 GP 결과 페이지와 공개 리플레이를 기준으로 수집했다. GP별 원본 링크, 상세 이미지 주소, 서킷 ID와 레이아웃 ID는 `assets/boxbox/2026.json`에 기록했다. 일정 및 서킷 메타데이터의 원 데이터는 [F1DB](https://github.com/f1db/f1db)이며 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)에 따라 필드를 선별하고 한글 이름을 연결했다.

21개 주행선과 코너 좌표는 BoxBox 리플레이가 사용하는 [MultiViewer](https://api.multiviewer.app/api/v1/circuits/46/2026) 응답에서 추출했다. 자료 기준 연도는 응답의 mapYear로 보존했다. 마드링과 세팡은 BoxBox 자체 리플레이 데이터 모듈의 숫자 배열을 사용했다. 수집 코드는 사이트 JS를 실행하지 않는다. 원본 모듈 URL과 좌표 출처는 각 항목의 mapSource에 있다. F1DB 라이선스는 지도와 F1 Media 이미지에 별도로 적용되지 않는다.

재수집은 프로젝트 루트에서 `python assets/boxbox/import_circuits.py`를 실행한다. 원본 검증이 끝나면 시즌 파일을 교체한다.

A탭은 `web/public/circuits/timing/<id>.webp`를 표시한다. 시즌별 폴더에 보존한 원본의 주소는 `assets/boxbox/2026.json`의 `image` 필드다. 도면은 Formula 1 Media 제공이며 저장소 코드 라이선스 적용 대상에서 제외된다. `assets/boxbox/image-paths.json`은 해당 1252×704 도면 위 차량 표시용 로컬 좌표다. 랩 거리의 동일 간격 480개 지점을 이미지 노면에 맞췄다. 지도 이미지 또는 주행선이 바뀌면 위치 보정도 함께 갱신해야 한다.

상세 도면 21장의 인쇄된 감지점·안내선·섹터 라벨은 `annotations.json`에 기록된 위치에서 제거하고 주변 원본 픽셀로 복원한다. 재생성은 Pillow와 NumPy가 설치된 환경에서 `python assets/game-circuits/clean_artwork.py`로 실행한다. 이 처리에는 게임의 마셜 존 데이터나 차량 좌표를 수정하는 단계가 없다.

## 라이브 UDP 서킷 도면

라이브 선택 기준은 [EA 게임 UDP 규격](https://forums.ea.com/blog/f1-games-game-info-hub-en/ea-sports%E2%84%A2-f1%C2%AE25-2026-season-pack-udp-specification/12187347)의 트랙 ID다. `assets/game-circuits/tracks.json`에 28개 ID와 F1 Media 원본 주소를 기록했다. 역방향 3개는 동일 서킷의 정방향 도면을 공유하고 주행선 진행을 반전한다. `python assets/game-circuits/download.py`가 F1 Media에서 고유 도면 25개를 직접 받아서 원본 해상도로 저장한다. 위 BoxBox 목록은 데모의 시즌 선택에 사용한다.

바레인 ID 3은 [F1 Media 2026 Sakhir 상세 도면](https://media.formula1.com/image/upload/c_fit,h_704/q_auto/v1740000000/common/f1/2026/track/2026tracksakhirdetailed.webp)을 사용한다. 내려받은 원본은 보관하고, 흰 배경·회색 섹터를 스즈카 타이밍 화면의 투명 배경·도로 외곽선·섹터 색으로 변환한다. 출발선, 직선 모드 구역, 코너 번호는 원본에서 추출한다. 이몰라·제다의 구형 원본도 같은 노면 규격으로 변환한다. 변환과 플래그 마스크 생성은 `assets/game-circuits/timing_artwork.py`에 있고 `download.py`가 함께 실행한다.

바레인·이몰라·제다의 주행선은 MultiViewer의 2025 요청(circuitKey 63·6·149) 좌표를 F1 도면에 맞춰 480점으로 재표본화했다. 바레인은 FP1의 상대 차량으로 보정한 랩 거리 순서를 유지한 채 상세 도면의 중앙선에 다시 맞추고 체크 무늬에 랩 0을 정렬했다. 도면 좌표계는 1252×704다.

루사일과 야스 마리나의 원본도 구형 도식이어서 데모와 라이브에서 동일한 타이밍 도면으로 변환한다. 전체 카탈로그의 보정 좌표는 원본 섹터선과 체크무늬(구형 도면은 도로 옆 출발 표식)를 기준으로 한다. 라스베이거스의 첫 코너군은 원본 분홍색 중앙선을 따라 다시 배치했고 경고 마스크의 끊긴 부분은 원본 흰 외곽선에서 복원했다. 지도 좌표 검증과 게임 내 직선거리 보정 실측은 별개이며, 후자는 위 바레인 FP1 기록에 한정된다.

## 대시보드 서체

[Formula1 Display Bold](https://blogfonts.com/formula1-display-bold.font)의 Bold TTF 내부 저작권 표기는 © 2017 Marc Rouault / W+K, 파일 SHA-256은 `1e205a75c9d035833c7204fd84fe2ad780ebedcee98a0432b15a2791b3ae50f6`이다. 원본 파일은 수정 없이 Windows 사용자 글꼴로 설치했고 웹 빌드는 로컬 서체 이름을 참조한다.

- Rust 녹화 포맷은 Cargo.lock에 고정한 zstd 0.13.5, zstd-safe 7.4.1(BSD-3-Clause), zstd-sys 2.1.3+zstd.1.5.7(BSD-3-Clause AND BSD-2-Clause)와 serde/serde_json(MIT OR Apache-2.0)을 사용한다. 패킷 framing과 재생 코드는 프로젝트 구현이다. [zstd-rs](https://github.com/gyscos/zstd-rs) · [Serde](https://serde.rs/)

## 피트 작업 기준

설치된 `game_package/gamedatabases/gamedatabases.2025.bin`의 SHA-256은 `407bf94a75ed3e368487a9fff63925a044d4acfe7df0ad0d86ca2c6c5a1cfbba`다. `python rust-core/extract_pit_rules.py <게임 DB 경로>`로 현재 설치본의 수치와 해시를 출력해 `rust-core/src/pit_rules.json`과 비교할 수 있다. 내장 스냅샷에는 훈련별 정차 시간, 앞날개 교체 추정치, 미니게임 가산, 실수별 지연 범위 및 모드 설정만 담는다. [GVDB 형식](https://f1.swofty.net/reference/gamedb/format.html) · [2026 UDP 규격](https://forums.ea.com/blog/f1-games-game-info-hub-en/ea-sports%E2%84%A2-f1%C2%AE25-2026-season-pack-udp-specification/12187347)
GP 전략 기능은 공식 PyPI 패키지 `openai-codex==0.167.2`와 `openai-codex-cli-bin==0.167.2`를 사용함. SDK 패키지 메타데이터의 라이선스는 Apache-2.0. 소스 복사 없이 SDK API를 호출하며 의존성은 requirements-web-lock.txt에 고정. [공식 저장소](https://github.com/openai/codex)

### 서킷별 피트 추정치

설치된 F1 25 GVDB 및 환경 ERP를 읽는 오프라인 추출기는 `rust-core/extract_track_pits.py`다. Python 3.14 이상에서 게임 루트 경로를 인자로 실행한다. 공개 [GVDB 키 목록](https://f1.swofty.net/reference/gamedb/schema.html)으로 TrackPitData를 찾고 설치 파일에서 확인했다. ERP의 trackmarkup에서 pit_lim_on 구간을 읽고 trackspacedata의 좌우 안쪽 게이트 중점 사이 거리를 더해 제한 구간 길이를 근사한다. 양 끝점을 본선에 투영하고 동급 차량 VP 타임 곡선의 첫 랩을 보간해 본선 예상 시간을 구한다. 길이와 본선 시간은 추정치다. pitStopTime_Dry/Wet 필드에서는 두 조건의 차이만 사용한다. 출력에는 수치만 포함한다. 일반 F1은 메르세데스 기준 곡선을, F2는 해당 시즌 공용 차량 기준 곡선을 사용한다.

피트 MFD 화면 판독은 Windows CPython 3.11 환경에서 [opencv-python-headless 4.12.0.88](https://pypi.org/project/opencv-python-headless/4.12.0.88/), [NumPy 2.2.6](https://pypi.org/project/numpy/2.2.6/), [Pillow 11.3.0](https://pypi.org/project/pillow/11.3.0/)의 배포 wheel을 사용한다. 각각 OpenCV Apache-2.0 및 wheel 패키징·번들 라이선스, NumPy BSD-3-Clause 및 번들 고지, Pillow MIT-CMU가 적용된다. assets/mfd-next-tyre-ko.png는 사용자가 제공한 한국어 피트 MFD 캡처에서 다음 타이어 글자 영역만 이진화한 현지 판독 템플릿이다.
로컬 무전은 선택 설치한 [faster-whisper 1.2.1](https://github.com/SYSTRAN/faster-whisper)과 번들 VAD, [qwentts.cpp](https://github.com/ServeurpersoCom/qwentts.cpp/tree/f1a6924789883bd92eeb59176793a94af55730b3)의 빌드 라이브러리를 사용한다. 두 런타임의 라이선스는 MIT. 앱의 Windows 오디오 입출력과 무전 처리는 `voice/`에 있고, 모델 가중치와 음성 참조 파일은 로컬 런타임에서 읽는다.
