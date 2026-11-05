# Culture-Fit Three.js 영상 도식

실제 Three.js 장면·카메라·메시·선·텍스트 평면을 headless Chrome의 WebGL로 렌더한다. 1920×1080, 30fps, H.264, 무음이다. 검정 배경과 흰 글자, 노랑·청록 강조를 사용하며 하단 180px는 최종 영상 자막용으로 비워 둔다. 시연 UI와 구분되는 설명 도식이다.

| 파일 | 길이 | 내용 |
|---|---:|---|
| intro.mp4 | 16초 | 초기 기획 → 7월 개발보고 → 현재 구현 |
| why-now.mp4 | 12초 | MCP의 도구·데이터 연결, A2A의 작업·상태 교환 → 결정권 질문 |
| overview.mp4 | 8초 | 확인 약속 → 질문 전달 → 사람의 결정 → 실행 근거 |
| authority.mp4 | 10초 | 사람 A·B의 위임 충돌과 로컬 공동 승인 기록 |
| outro.mp4 | 15초 | 원문 근거 → 위임 권한 → 사람의 결정 → 다음 행동 |

## 재생성

`work/`는 임시 의존성을 저장하며 Git에서 제외한다. Three.js 0.180.0의 `three.module.js`와 `three.core.js`를 npm 공식 패키지의 jsDelivr 배포본에서 내려받고, `PretendardVariable.ttf`를 해당 폴더에 둔다.

```sh
mkdir -p work
curl -fLsS https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js -o work/three.module.js
curl -fLsS https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.core.js -o work/three.core.js
curl -fLsS https://raw.githubusercontent.com/orioncactus/pretendard/v1.3.9/packages/pretendard/dist/public/variable/PretendardVariable.ttf -o work/PretendardVariable.ttf
uv run --with playwright python render.py
```

macOS Chrome, ffmpeg를 사용한다. `--previews-only`, `--scene authority`, `--port 8891` 옵션을 지원한다. `window.renderAt(sceneName, timeSeconds)`로 같은 시간의 장면을 재현할 수 있다. 실제 UI·백엔드·모델 호출 없이 독립적으로 실행한다.

`render.py`는 실제 폰트 잉크 영역과 네온 여백을 `layout-bounds.json`에 보존한다. `python check_spacing.py`는 0.1초 간격으로 등장·퇴장 중인 요소까지 점검하고 `spacing-validation.json`에 글자 간 겹침, 원·선·글자 간격, 하단 자막 영역 침범 여부를 저장한다. 네온 외곽은 글자 14px, 원 10px와 선의 최대 발광 폭을 포함한다.

권한 도식의 공동 승인은 로컬 운영자의 기록이다. 원격 소유자 신원·동의 인증이나 외부 작업 실행을 나타내지 않는다. 기획·7월 개발보고·현재 구현의 단계를 구분하며 초기 서비스의 완성·효과 검증을 주장하지 않는다.

Three.js 공식 문서: https://threejs.org/manual/

`timeliness.mp4`는 합성 담당용 `why-now.mp4`의 동일 사본이다. 인트로 직후 00:16–00:28에 삽입한다. 해당 장면은 [Anthropic의 MCP 발표(2024-11-25)](https://www.anthropic.com/news/model-context-protocol), [Google의 A2A 발표(2025-04-09)](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/), [Li·Xie의 통합 분석(2025)](https://arxiv.org/abs/2505.03864)을 참고한다. MCP는 도구·데이터 연결, A2A는 에이전트 간 작업·상태 교환으로 표시한다. “누가 결정할 수 있죠?”는 이 연결 환경에서 프로젝트가 다루는 설계 질문이다.
