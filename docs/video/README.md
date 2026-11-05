# 컬처핏(Culture-Fit) 로컬 기능 시연 영상

이 폴더는 제출 보고서에 연결할 **로컬 검토용 영상 초안**이다. YouTube나 외부 서비스에는 업로드하지 않았다. 제출 양식의 동영상 URL은 별도 게시 후 기입해야 한다. 제출·YouTube 제목은 **Culture-Fit 컬처핏 | Open-source Human-in-the-Loop (HITL) | elevenlabs.io**로 사용한다.

## 산출물

- `culture-fit-demo-1080p.mp4`: 3분 6초, 1920×1080, 30fps, H.264/AAC. 한국어 음성, 화면에 삽입한 한국어 자막, 기본 꺼짐으로 설정한 선택형 한국어 자막 트랙, 챕터 포함. 영상·음성 스트림 모두186.000초이며 영상은5580프레임이다.
- `culture-fit-demo.ko.srt`: UTF-8 한국어 자막.
- `culture-fit-demo.en.srt`: 같은22구간·타이밍의 영문 자막. 한국어판에 겹쳐 넣지 않은 별도 파일.
- `culture-fit-demo-en-1080p.mp4`: 한국어판과 같은186초 영상·같은Harry Kim 한국어 음성에 **하단 설명 자막만 영어로 교체한 판**. 실제 UI·도식·상단 안내는 한국어로 유지된다.
- `validation-en.json`, `caption-layout-en.json`: 영문판 검증과44px·최대2줄 자막 배치 기록.
- `storyboard.json`: 장면별 길이·제목·내레이션 원문·자막 타이밍을 편집하는 자료. 원본 정의는 `production.py`의 `CHAPTERS`.
- `storyboard.md`: 장면 구성과 검증 범위.
- `contact-sheet.jpg`: 주요 시점의 최종 영상 프레임.
- `validation.json`: 해상도·길이·코덱·해시·캡처 방식과 검증 기록.
- `captures/`: 실제 UI 캡처, 합성 예제의 저장 상태, 브라우저 요청 기록.
- [references.json](references.json): 장면별 공식 근거, 논문, 디자인·폰트·음성 출처.
- `narration-source.json`: 실제 음성 출처, 원본 해시, 문장별 편집 기록.
- `narration-alignment.json`: 원고와 로컬 음성 전사의 대응 및 원본 절단 시각.
- `end-credits-preview.png`: 마지막 3초의 작은 근거·음성 출처 한 줄.
- [upload-description.txt](upload-description.txt): 글로벌 개발자용 영어·한국어 소개, 게시용 제목·챕터·전체 공식 출처 목록 초안. 외부 게시는 수행하지 않음.

## 촬영 방법과 범위

Playwright가 설치된 Google Chrome을 실행해 **기존 앱 UI에서 클릭·입력·탭 이동·스크롤**을 수행했다. 뷰포트와 원본 영상은 1600×750이다. 전체 UI는 검은 1920×1080 캔버스 안에 1480×694로 배치하고, 본문은 원본의 (300,0)에서 1260×650 영역을 잘라 1560×805로 확대했다. UI 내용·테마는 그대로다. 61초의 설명 도식은 별도 작성한 실제 Three.js WebGL 애니메이션이며, 실제 UI 녹화는 125초다. 공동 승인 입력은 원본 7.2초를 11초로 느리게 재생해 선택·저장을 읽을 시간을 확보했다. 앱 기능이나 결과를 영상 편집으로 새로 만들어 넣지 않았다.

`127.0.0.1:8797` 데모의 SQLite를 복사한 전용 `docs/video/work/video-demo.sqlite3`와 `127.0.0.1:8798` 서버만 촬영에 사용했다. 운영 서버 8787과 원본 DB에는 촬영을 위한 입력을 하지 않았다. 촬영 전후 앱 소스 해시가 일치하는 것을 확인하고 당시 소스를 `work/source-snapshot/`에 보관했다. 이후 배포 개발로 현재 작업 트리의 앱 소스는 달라질 수 있으며, 영상은 고정된 촬영본을 사용한다. 원본 DB의 기존 실제 모델 브리핑은 합성 대화에 대한 저장본이며 재호출하지 않았다. 영상 복제본의 우선권 목록만 초기화해 권한 충돌에서 공동 승인·우선권 입력 후 갱신되는 흐름을 촬영했다.

대화 입력, 결정 기록, 지식맵, 권한 갱신, 통제 시뮬레이션은 실제 로컬 앱의 동작이다. 촬영용 브라우저 라우트는 `POST .../brief`와 실제 모델 세션 생성을 차단한다. 한국어 음성은 사용자가 승인한 ElevenLabs 웹 Text to Speech에서 **Harry Kim - Conversational / Korean / Eleven v4 / Generation 1**로 생성·다운로드했다. 145.005688초의 원본을 문장별로 나눠 22개 자막 구간에 배치했다. 원본과 생성 기록은 `work/elevenlabs/`, 실제 편집 기록은 `narration-source.json`에 있다. 앱 분석용 모델의 추가 호출은 없으며, 음성 정렬에는 로컬 MLX Whisper를 사용했다. 영상 제목·자막은 공식 Pretendard v1.3.9 글꼴이다. 52px ExtraBold 흰 자막과 선택적인 노랑/청록 네온 강조를 사용했다. 배경음악은 사용하지 않았다.

## 재생성

macOS, Google Chrome, `uv`, `ffmpeg`, `ffprobe`가 필요하다. 로컬 임시 음성으로 바꾸려면 macOS Yuna 음성을 사용할 수 있다. 아래 명령은 프로젝트 루트 기준이다. Playwright/Pillow는 `uv --with` 임시 환경을 사용하므로 프로젝트 의존성을 바꾸지 않는다.

```bash
uv run --with playwright python -m playwright install ffmpeg
uv run --with pillow python docs/video/production.py snapshot
ARBITER_DB="$PWD/docs/video/work/video-demo.sqlite3" uv run uvicorn arbiter.app:app --app-dir backend --host 127.0.0.1 --port 8798
```

8798 서버를 실행한 채 다른 터미널에서 진행한다.

```bash
uv run --with pillow python docs/video/production.py artwork
# 보존한 ElevenLabs 음성을 자막 구간에 배치한다.
uv run --with pillow python docs/video/prepare_elevenlabs.py
uv run --with playwright --with pillow python docs/video/production.py capture
# Three.js 클립은 motion/README.md의 명령으로 먼저 준비한다.
uv run --with pillow python docs/video/production.py render
uv run --with pillow python docs/video/production.py verify
```

`snapshot`은 **8798 서버가 종료된 상태에서만** 실행한다. 원본 `.runtime/authority-demo.sqlite3`가 있으면 실제 모델 브리핑 세션 `177cddcae14345fba16b42eb6772121e`와 합성 위임 기록을 복제한다. 원본 DB가 없으면 함께 보관한 `captures/authority-briefing-source.json`과 `authority-registry-source.json`의 기존 저장본으로 촬영용 DB를 복원한다. 이것은 저장 결과의 재생이며 새 모델 분석이 아니다. 녹화 스크립트는 현재 UI ID와 합성 예제에 맞춰 작성되어 UI 변경 시 선택자를 점검해야 한다.

최종 음성 원본은 `work/elevenlabs/culture-fit-harry-kim-v4-generation1.mp3`이다. 정렬된 원본·문장 경계가 보존되어 있으면 `prepare_elevenlabs.py`로 동일 음성을 재구성한다. 로컬 임시 음성이 필요할 때만 `production.py speech`를 실행한다. 화면·타이틀을 바꾸면 해당 `work/v2-*.mp4`를 지우고 `render`를 다시 실행한다. 모션 도식의 재생성은 `motion/README.md`, 폰트 출처·라이선스는 `fonts/sources.json`과 `fonts/LICENSE`를 참고한다. 원본 녹화·임시 오디오·DB·프레임은 `work/`에 있으며 Git에서 제외한다.

## 설명상의 제한

- 초기 문화·역사 KG-RAG는 기획이다. 완성이나 검증 성과로 설명하지 않는다.
- 7월 GitHub RAG·Telegram·Accept/Reject/Abstain에서 현재 권한 기반 HITL로 이어지는 공통축은 생성형 AI의 검증·관리다. 개별 도메인의 전문적 판단을 대체하지 않고, 여러 에이전트·도메인에서 재사용할 연결 계층을 지향한다.
- 현재 구현은 LLM을 사용한다. 이 영상 촬영에서는 기존 모델 브리핑을 재사용했으며 새 모델 호출은 없다. 촬영 이후 개발 소스는 [`feat/ontology-hitl`](https://github.com/Ontology0/hanium-arbiter/tree/feat/ontology-hitl) 분기(`2cd2bea`)에 공개되었으며 main 반영은 PR 대기 상태다. [공개 체험](https://culture-fit-demo-production.up.railway.app/)은 촬영 이후의 분리 데모로, 영상의 고정 로컬 촬영본과 구분한다.
- 실제 Slack 계정에 연결하지 않았다. 화면의 결정 기록은 메시지 전송·외부 작업의 자동 실행이 아니다.
- 공동 승인은 로컬 운영자의 기록이다. 외부 소유자의 신원·실제 동의를 인증하지 않는다.
- 통제 시뮬레이션의 에이전트 대화와 산출물은 스크립트다. 완료는 로컬 조율 계획 JSON의 체크리스트 충족이다.
- 무한루프 탐지의 일반적 검증, 모델 정확도, 비용·시간 절감률, 실제 사용자 효과를 주장하지 않는다.

## 외부 음성 교체

현재 음성의 실제 출처는 `narration-source.json`에 기록한다. ElevenLabs 무료 계정에서 생성한 음성의 비상업적 공유 시 제목에 `elevenlabs.io` 또는 `11.ai` 출처를 포함해야 한다. 유료 구독·결제는 하지 않았다. [ElevenLabs 공식 게시 안내](https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform)를 따른다.

`import_narration.py`는 로컬 파일만 가져온다. `storyboard.json` 순서대로 `voice-intro-0.mp3`, `voice-intro-1.mp3`, `voice-intake-0.mp3` 등의 이름으로 22개 음성을 준비하면 각 자막 구간에 맞춘다. WAV/MP3/M4A/AIFF/FLAC를 읽으며 길이가 지나치게 긴 구간은 재녹음을 요구한다.

```bash
uv run --with pillow python docs/video/import_narration.py --cue-dir /absolute/path/to/voice-files --provider '확인된 실제 음성 출처'
# 전체 음성은 기존 자막에 이미 맞춘 정확한 186초 파일만 가져온다.
uv run --with pillow python docs/video/import_narration.py --audio /absolute/path/to/aligned-track.wav --provider '확인된 실제 음성 출처'
uv run --with pillow python docs/video/production.py render
uv run --with pillow python docs/video/production.py verify
```

외부 음성을 가져온 뒤 `production.py speech`를 실행하면 로컬 Yuna 음성으로 덮어쓰므로 재합성에는 `render`와 `verify`만 실행한다.

시의성 장면은 인트로 직후 00:16–00:28에 삽입했다. 연결 표준의 등장과 사람 권한 관리의 필요성을 설명하며, 최초 구현이나 효과 실증을 주장하지 않는다. 00:16–00:28 모션 장면과 마지막 03:03–03:06의 24px 회색 한 줄에 근거·음성 출처를 표시했다. 정확한 공식 URL과 장면별 주장 범위는 [references.json](references.json), 모션 구현은 [motion/README.md](motion/README.md)에서 확인한다.


## 음성 정렬의 재현

보존한 `narration-alignment.json`을 사용하는 재합성에는 추가 모델 다운로드나 음성 서비스 호출이 없다. 새 음성을 정렬할 때만 [MLX Whisper 공식 문서](https://github.com/ml-explore/mlx-examples/blob/main/whisper/README.md)에 따라 `mlx-community/whisper-small-mlx`의 한국어 단어 시각을 로컬에서 추출한 뒤 아래 명령을 쓴다. ASR 문자열 일치는 청감 평가와 다르며, 표기 차이와 문장 경계는 편집자가 확인해야 한다.

```bash
python docs/video/align_narration.py --asr docs/video/work/elevenlabs/asr.json --silences docs/video/work/elevenlabs/silences.json --audio-duration 145.005688 --output docs/video/narration-alignment.json
uv run --with pillow python docs/video/prepare_elevenlabs.py
uv run --with pillow python docs/video/production.py render
uv run --with pillow python docs/video/production.py verify
```

`prepare_elevenlabs.py`는 원본 MP3의 해시를 검증하고 재생 속도를 1.0으로 유지한다. 문장이 자막 슬롯보다 길면 자동 가속·잘라내기를 하지 않고 중단하므로, 문장 경계나 자막 시각을 조정한 뒤 다시 실행한다.

내장 선택형 자막은 `default=0`으로 저장해 큰 화면 자막과 자동 중복 표시되지 않도록 했다. [FFmpeg MOV muxer](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/movenc.c)의 첫 자막 트랙 활성화 동작에 대응해 `disable_subtitle_default.py`가 해당 트랙의 enabled 비트만 해제한다. 미디어 샘플·길이·오프셋은 바꾸지 않으며, 최종 `ffprobe`에서 비활성 기본값을 확인한다.


## 영문 자막판 재생성

글로벌 개발자용 소개는 영어·한국어를 함께 제공한다. 영문판은 제품 전체의 영어 UI 시연이나 영어 대화 판정 검증을 뜻하지 않는다. 고정된 한국어 UI·Three.js 도식과 승인된 Harry Kim 한국어 음성을 유지하고 하단 설명 자막만 영어로 바꾼다. 코드의 MIT 라이선스와 영상 음성의 별도 이용 조건은 `upload-description.txt`에 함께 적었다.

```bash
# 먼저 한국어판 render/verify로 최신186초 clean base를 만든다.
uv run --with pillow python docs/video/render_english.py
```

`render_english.py`는 clean base에 영문 자막만 넣고 한국어판의 AAC 패킷을 그대로 복사한다. 22구간 타이밍, 최대2줄, 글자 하단 안전여백, 영상·음성186초/5580프레임, 선택형 자막 기본 꺼짐과 전체 디코드를 검사하여 `validation-en.json`에 저장한다.
