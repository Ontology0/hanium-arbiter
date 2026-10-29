# Railway 방문자 체험 배포

공개 체험은 `arbiter.deployment:app`, 개인 설치는 `arbiter.app:app`을 실행합니다. 공개 체험에서는 합성 대화와 과거 단일 사례의 모델 분석을 재생하고, 방문자가 위임·공동 승인·우선권을 바꿔 볼 수 있습니다. 새 모델 호출과 Slack 수신은 서버에서 차단합니다. 공개 체험 주소는 MCP·A2A 서버 주소가 아닙니다.

## 실행과 저장

```bash
ARBITER_DEMO_DATA_DIR=.runtime/visitor-demo \
  uv run uvicorn arbiter.deployment:app --host 127.0.0.1 --port 8799 --workers 1
```

서명된 임의 방문자 쿠키마다 별도의 SQLite 파일을 사용합니다. 쿠키는 사람이나 에이전트 소유자의 신원을 인증하지 않습니다. 같은 브라우저 프로필의 탭들은 같은 체험을 공유합니다. 시크릿 창이나 별도 브라우저 프로필은 새 체험을 만듭니다.

- `/api/health`: 방문자 생성 없는 상태 확인.
- `/api/config`: 공개 체험 설정과 방문자 쿠키 발급.
- `POST /api/demo/reset`: 자신의 저장 공간을 삭제하고 새 체험으로 교체. 실행 중이면 409.
- 기본 보존 기간은 **생성 후 24시간**입니다. 만료된 비활성 체험은 주기적으로 정리합니다.
- 쿠키 서명키와 방문자 등록부는 볼륨에 보존하여 서버 재시작 후에도 같은 체험을 이어갑니다.

## Railway 설정

| 항목 | 설정 |
|---|---|
| 빌드 | 저장소의 `Dockerfile`, Python 3.12, `uv sync --frozen --no-dev` |
| 실행 | `uvicorn arbiter.deployment:app --host 0.0.0.0 --port "$PORT" --workers 1` |
| 볼륨 | `/data`에 연결 |
| 복제본 | 1개; 동일 볼륨의 중복 워커는 파일 잠금으로 시작 거부 |
| Healthcheck | `/api/health` |
| `PORT` | `8080` |
| `ARBITER_DEMO_DATA_DIR` | `/data` |
| `ARBITER_DEMO_SECURE_COOKIE` | `1` |
| `FORWARDED_ALLOW_IPS` | Railway 프록시 환경에서 `*` |

방문자 DB는 `/data/visitors/<임의ID>.sqlite3`에 저장합니다. Railway 환경에서는 쿠키에 `Secure`, `HttpOnly`, `SameSite=Lax`를 적용하고, 방문자 응답은 `private, no-store`, `Vary: Cookie`로 반환합니다. 다른 출처의 브라우저 변경 요청은 거부합니다.

기본 한도는 저장 방문자 200명, 메모리 내 앱 32개, 방문자당 120요청/분, 본문 256KiB, 방문자 저장 공간 8MiB, 전체 체험 DB 256MiB입니다. 세션 12개·위임 기록 100개·가져온 대화당 메시지 200개로 제한합니다. 요청 처리 중인 앱과 실행 중인 시뮬레이션은 캐시에서 제거하지 않습니다. 용량 검사는 쓰기 직전 한도 확인이므로 마지막 한 요청의 저장분은 한도를 소폭 초과할 수 있습니다.

## 업로드 범위

`.dockerignore`와 `.railwayignore`는 기본 제외 목록으로 작성되어 있습니다. 로컬 `.runtime`, `.env`, 계정 인증 파일, 개인 연락처, 보고서와 영상은 포함하지 않습니다. Dockerfile도 백엔드 Python 코드, 프런트 5개 파일, 공개 실험 요약, Slack 앱 매니페스트만 복사합니다.

중첩 Git 저장소의 상위 프로젝트가 잘못 포함되지 않도록 검토한 실행 파일만 별도 임시 폴더에 복사하고, 다음처럼 명시적으로 그 폴더를 업로드합니다.

```bash
railway up /absolute/path/to/runtime-staging --path-as-root \
  --project PROJECT_ID --service SERVICE_ID --environment production --ci
```

배포 후 서로 다른 두 쿠키로 세션·권한 격리, 다른 방문자 세션의 404, 자신의 초기화, 기록된 분석의 권한 재판정, 모델 호출 거부를 확인합니다. 실제 소유자 인증·외부 작업 실행·Slack 실연동을 검증한 것으로 해석하지 않습니다.
