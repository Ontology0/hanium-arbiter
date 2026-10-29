# Slack 대화 관제 연결

기존 개인 에이전트와 봇이 Slack 채널에서 주고받는 메시지를 관제 화면에 수집한다. 에이전트 소스 코드나 프롬프트를 바꿀 필요가 없다. 허용한 채널의 메시지를 Slack 앱이 수신하고, 로컬 API가 스레드별 세션에 저장한다. 사람은 대화 흐름, 확인 약속, 대기 관계와 결정 요청을 대시보드에서 확인한다.

이 연결은 읽기 전용이다. Slack 메시지 전송·수정·삭제, 반응 추가, 사람의 결정 대리 입력을 하지 않는다. 대시보드에 기록한 결정도 Slack으로 자동 발송되지 않는다.

## 연결 구조

```text
기존 에이전트·사람의 Slack 메시지
           ↓ Socket Mode
Arbiter Observer 앱 → slack_bridge → 로컬 /api/slack/events
                                      ↓
                          스레드별 세션·중복 방지 저장
                                      ↓
                         사람이 관제 화면에서 확인·결정
```

Socket Mode는 공개 웹훅 URL을 열지 않고 WebSocket으로 이벤트를 받는 방식이다. 연결과 재연결은 공식 Python Slack SDK의 `SocketModeClient`에 맡긴다. [Slack Socket Mode 안내](https://docs.slack.dev/apis/events-api/using-socket-mode/), [공식 Python SDK](https://docs.slack.dev/tools/python-slack-sdk/socket-mode/)

## 준비할 것

1. Slack 앱을 설치할 수 있는 워크스페이스.
2. 관찰할 공개 또는 비공개 채널의 ID.
3. 이 저장소의 [slack-app-manifest.json](../slack-app-manifest.json)으로 생성한 앱.
4. 앱 수준 토큰 `SLACK_APP_TOKEN`과 설치된 봇 토큰 `SLACK_BOT_TOKEN`.

실제 Slack 워크스페이스 설치와 인증은 아직 수행하지 않았다. 아래 설정은 사용자가 앱 설치·토큰·채널을 준비한 환경에서 연결하기 위한 절차다.

## Slack 앱 설정

Slack의 [앱 관리 화면](https://api.slack.com/apps)에서 **Create New App → From a manifest**를 선택하고 워크스페이스를 지정한 다음 manifest JSON을 입력한다. 앱 manifest는 다음 구성을 포함한다. [공식 manifest 문서](https://docs.slack.dev/reference/app-manifest/)

| 항목 | 설정 |
| --- | --- |
| Socket Mode | 사용 |
| 봇 OAuth scope | `channels:history`, `groups:history` |
| 구독 이벤트 | `message.channels`, `message.groups` |
| 메시지 전송 권한 | 없음; `chat:write`를 요청하지 않음 |

앱의 **Basic Information → App-Level Tokens**에서 `connections:write` 범위의 토큰을 생성한다. 이 `xapp-…` 토큰은 Socket Mode 연결에 사용한다. **OAuth & Permissions → Install to Workspace**로 앱을 설치하고 `xoxb-…` 봇 토큰을 확인한다. 관찰할 채널에 **Arbiter Observer** 앱을 추가한다. 비공개 채널도 앱이 참여해야 수신할 수 있다. 앱 수준 토큰은 bot OAuth scope 목록에 넣는 항목이 아니다. [공식 SDK 설정 순서](https://docs.slack.dev/tools/python-slack-sdk/socket-mode/), [message 이벤트 범위](https://docs.slack.dev/reference/events/message/)

공개 채널만 필요하다면 manifest의 `groups:history`와 `message.groups`를 제거한 구성으로 설치할 수 있다. 직접 메시지와 단체 DM은 현재 manifest 구독 범위에 포함하지 않는다.

## 환경변수와 실행

토큰은 환경변수로만 받는다. 코드, manifest, 보고서에 실제 토큰을 넣지 않는다. 각 터미널에서 `ARBITER_ROOT`를 자신이 내려받은 저장소 경로로 설정한다.

**터미널 1 — API와 대시보드:**

```bash
export ARBITER_ROOT="/absolute/path/to/hanium-arbiter"
export SLACK_ALLOWED_CHANNELS="C0123456789,C0987654321"
uv --directory "$ARBITER_ROOT" run uvicorn arbiter.app:app --host 127.0.0.1 --port 8787
```

**터미널 2 — Slack 이벤트 수신:**

```bash
export ARBITER_ROOT="/absolute/path/to/hanium-arbiter"
export SLACK_APP_TOKEN="xapp-여기에_앱_수준_토큰"
export SLACK_BOT_TOKEN="xoxb-여기에_봇_토큰"
export SLACK_ALLOWED_CHANNELS="C0123456789,C0987654321"
export ARBITER_API_URL="http://127.0.0.1:8787"

uv --directory "$ARBITER_ROOT" run python -m arbiter.slack_bridge --check-config
uv --directory "$ARBITER_ROOT" run python -m arbiter.slack_bridge
```

위 토큰과 채널 ID는 자리표시자다. `--check-config`는 형식과 필수 설정만 확인하며 Slack이나 API에 접속하지 않는다. 실제 실행은 API 상태 확인 후 Socket Mode 연결을 시도한다. 두 프로세스의 `SLACK_ALLOWED_CHANNELS`를 같게 설정해야 하며, 빈 목록·`*`·채널 이름 대신 구체적인 ID를 사용한다. API 주소는 같은 컴퓨터의 loopback HTTP(S) origin만 허용한다.

사람은 <http://127.0.0.1:8787>에서 새 Slack 대화 세션을 확인한다. 한 협업 작업을 한 Slack 스레드에서 이어가면 대시보드에서도 같은 세션으로 모인다. 스레드가 없는 각각의 새 메시지는 별도 스레드의 시작으로 취급된다.

## 이벤트 처리 범위

| 이벤트 | 처리 |
| --- | --- |
| 일반 메시지 | 허용 채널이면 API에 전달 |
| 봇 메시지 | `bot_message`, 또는 일반 메시지의 `bot_id`가 있어도 포함 |
| 스레드 답글·`thread_broadcast` | 원본 `thread_ts`를 API에 전달 |
| `message_changed` | 수정 이벤트와 `message.ts`를 보존해 API에 전달 |
| `message_deleted` | 삭제 이벤트와 `deleted_ts`를 보존해 API에 전달 |
| 채널 참가 등 나머지 subtype | ACK 후 제외 |

수정·삭제는 새 일반 메시지로 위장하지 않는다. API가 원래 메시지와 연결해 반영하며, 변경된 현재 대화로 관제 요청을 다시 점검한다. 이전 사람의 결정 이력은 남지만 다른 주제의 새 확인 의무에 자동 적용하지 않는다. 원본을 아직 수집하지 못한 수정·삭제 이벤트의 처리는 API 결과에 따른다. [봇 메시지 구조](https://docs.slack.dev/reference/events/message/bot_message/), [수정 이벤트](https://docs.slack.dev/reference/events/message/message_changed/), [삭제 이벤트](https://docs.slack.dev/reference/events/message/message_deleted/)

채널 허용 목록 밖의 이벤트는 로컬 API로 전달하지 않고 ACK한다. 처리 대상 이벤트는 로컬 API가 성공 응답을 준 뒤 해당 Socket Mode `envelope_id`를 ACK한다. API가 실패하거나 타임아웃이면 ACK를 보류해 Slack의 재전송을 허용한다. 같은 이벤트를 재수신해도 Slack의 원래 `event_id`를 그대로 사용한다. 중복 제거와 스레드 매핑은 API의 영속 저장이 담당하므로 수신 프로세스가 다시 시작되어도 임의의 새 ID를 만들지 않는다. [Socket Mode 이벤트 ACK 규약](https://docs.slack.dev/apis/events-api/using-socket-mode/)

장기간 중단 중의 모든 메시지를 자동 복구하는 백필 기능은 없다. 파일 본문 다운로드·이미지 해석·채널 과거 이력의 일괄 수집도 현재 범위에 없다. 로그에는 메시지 본문·토큰을 출력하지 않으며, SDK 로그에 나타날 수 있는 토큰과 WebSocket 접속 URL도 가린다.

## 검증된 것과 실제 연결 여부

```bash
uv --directory "$ARBITER_ROOT" run pytest tests/test_slack.py -q
```

수신 모듈 테스트는 **합성 Slack 이벤트, 공식 SDK의 요청 객체, 모의 HTTP API**를 사용한다. 채널 필터링, 봇 메시지 포함, 수정·삭제 원형 전달, 성공 후 ACK, 실패 시 재전송 가능 상태, 수신 모듈 재생성 후 이벤트 ID 유지, 토큰 비노출, 쓰기 scope가 없는 manifest를 검증한다.

이 결과는 실제 워크스페이스에 연결하거나 개인 에이전트의 Slack 메시지를 수집했다는 증거가 아니다. 실제 연결 확인에는 앱 설치, 토큰, 채널 참여 및 허용 목록 설정 뒤 **새 Slack 메시지가 해당 대시보드 세션에 나타나는지** 확인하는 절차가 남아 있다.
