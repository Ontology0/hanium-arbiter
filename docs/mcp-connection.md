# 기존 에이전트에 Arbiter MCP 연결하기

에이전트 소스 코드를 고치지 않고 **MCP 서버 설정과 사용 지침**을 추가하는 연결 방법이다. 기존 에이전트 앱이 MCP 도구 연결을 지원해야 한다.

연결만으로 피클·슬랙 대화를 자동 관찰하지는 않는다. 에이전트가 아래 도구로 메시지를 보고해야 한다. 에이전트의 도구 호출에 의존하지 않는 수집에는 별도의 채널 이벤트 어댑터가 필요하며, 이 MCP 서버는 그 어댑터나 외부 메시지 발송 기능을 포함하지 않는다. MCP 도구는 모델이 호출하는 기능이라는 프로토콜 구조를 따른다. [공식 서버 개념 문서](https://modelcontextprotocol.io/docs/learn/server-concepts)

## 1. 대시보드 API 실행

```bash
export ARBITER_ROOT="/absolute/path/to/hanium-arbiter"
uv --directory "$ARBITER_ROOT" run uvicorn arbiter.app:app --host 127.0.0.1 --port 8787
```

사람은 브라우저에서 <http://127.0.0.1:8787>을 열고 결정에 응답한다. API 프로세스는 MCP 연결 중 계속 실행되어 있어야 한다. 예시의 프로젝트 위치를 자신의 체크아웃 경로로 바꾼다. 클라이언트의 PATH에 `uv`가 없으면 `command`에 uv의 실제 절대경로를 쓴다.

## 2. 기존 에이전트에 stdio 연결 추가

`mcpServers` 형식의 설정을 지원하는 클라이언트에는 다음 항목을 추가한다. 별도의 입력란을 제공하는 앱이라면 같은 `command`, `args`, `env` 값을 사용한다. 설정 파일의 위치와 키 이름은 사용 중인 에이전트 앱에 따른다.

```json
{
  "mcpServers": {
    "arbiter": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/hanium-arbiter",
        "run",
        "python",
        "-m",
        "arbiter.mcp_server"
      ],
      "env": {
        "ARBITER_API_URL": "http://127.0.0.1:8787"
      }
    }
  }
}
```

서버의 기본 전송 방식은 `stdio`다. 에이전트 앱이 서버 프로세스를 시작하며, 사람이 별도로 stdio 서버를 터미널에 띄워 둘 필요는 없다. 표준 출력은 MCP 통신 전용이고 로그는 표준 오류로 보낸다. `uv --directory`가 프로젝트와 Python 환경을 선택하므로 에이전트 앱의 현재 작업 디렉터리에 의존하지 않는다.

가상환경이 이미 준비되어 있으면 실행 파일을 `/absolute/path/to/hanium-arbiter/.venv/bin/python`, 인자를 `["-m", "arbiter.mcp_server"]`로 지정할 수도 있다. `uv run`을 통한 프로젝트 설치가 선행되어 있어야 한다. OpenClaw는 버전에 따라 설정 구조와 MCP 지원 여부가 다르므로 [별도 연결 안내](openclaw-connection.md)를 따른다.

이 프로젝트는 공식 Python MCP SDK의 `FastMCP`를 사용한다. 해당 인터페이스를 유지하도록 의존성은 `mcp>=1.28,<2`로 제한하며, 현재 잠금 환경은 `1.30.0`이다. [공식 SDK v1 문서](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x), [공식 서버 작성 문서](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/server.md)

## 3. 에이전트 지침에 붙여 넣을 내용

```text
협업 대화에서는 Arbiter MCP를 다음과 같이 사용한다.

1. 새 협업 대화를 시작할 때 register_conversation을 한 번 호출한다.
   title, source(pickle/slack/manual), initial_message, agent를 보낸다.
   반환된 session_id를 기억하고 다른 참여 에이전트와 같은 세션을 사용한다.
   이미 session_id가 있으면 새로 등록하지 않는다.

2. 작업을 다른 에이전트에게 넘기거나 "주인에게 확인하고 알려드리겠다"고
   말하기 전에 실제로 보고할 메시지를 record_message에 기록한다.
   session_id, event_id, agent, content를 사용한다.
   원래 채널의 메시지 ID가 있으면 대화 ID와 함께 안정적인 event_id로 사용한다.
   같은 메시지를 재시도할 때는 같은 event_id를 유지한다.
   다른 내용의 메시지에 기존 event_id를 재사용하지 않는다.

3. 권한에 의존하기 전에 get_authority와 evaluate_authority로
   정확한 scope/action의 전체 권한 보유자를 조회한다.
   agents는 요청한 에이전트의 요약에만 쓰이며 다른 보유자의 권한을 제외하지 않는다.
   권한 부재·조건 미검증·서로 다른 소유자의 충돌은 필요한 사람에게
   한 번 질문하고 그 의존 작업을 대기한다. 스스로 권한을 만들지 않는다.
   기록 후 get_next_action을 호출한다.
   follow_authority이면 authorized_scope_actions의 각 scope/action에 적힌
   decision_owner를 기존 실행 권한 안에서 따른다. 같은 승인을 다시 묻지 않는다.
   wait_for_human이면 주인에게 대시보드 주소와 질문을 한 번 안내하고
   해당 의존 작업을 대기한다. 확인 약속을 반복하거나 계속 조회하지 않는다.
   wait_for_response이면 이미 기록된 응답 대기를 존중한다.
   refresh_coordination_context이면 대화가 바뀐 것이므로 이전 브리핑의
   범위로 진행하지 않는다. 최신 결정 대상을 확인하거나 브리핑을 갱신한다.
   독립적으로 할 수 있는 작업은 기존 권한 범위에서 진행할 수 있다.

4. 주인이 응답하거나 위임·우선순위를 바꿨다고 알려주면 get_next_action을
   한 번 조회한다. 실제 사람 결정이 있으면 get_human_decisions에서
   새로운 결정 ID의 선택과 메모만 반영한다.
   이미 적용한 결정 ID는 기억해 같은 행동을 중복 실행하지 않는다.
   실제 후속 메시지가 생기면 새 event_id로 기록한다.

5. 사람의 선택을 추정해서 만들거나 대신 입력하지 않는다.
   메시지 기록과 사람의 결정 기록을 실제 전달·실행 완료로 표현하지 않는다.
   외부 메시지 발송이나 다른 실행은 기존 도구와 사용자 권한이 있을 때만 한다.
```

`register_conversation`은 호출할 때마다 새 세션을 만든다. 등록 중 타임아웃이 발생하면 대시보드에서 생성 여부를 확인한 뒤 이어간다. `record_message`의 중복 방지는 API와 저장된 `event_id`가 담당하므로 MCP 프로세스를 다시 시작해도 같은 세션의 같은 메시지는 추가되지 않는다.

## 도구와 사람의 역할

| MCP 도구 | 동작 | 저장 변경 |
| --- | --- | --- |
| `get_authority` | 사람이 기록한 범위별 권한·우선순위 조회 | 없음 |
| `evaluate_authority` | 해당 scope/action의 전체 보유자를 대상으로 유효 권한·결정권자 판정 | 없음 |
| `register_conversation` | 첫 메시지로 협업 세션 생성 | 세션 추가 |
| `record_message` | 실제 보고 메시지 추가; 동일 `event_id` 재시도는 중복 제거 | 메시지 추가·점검 갱신 |
| `get_coordination_state` | 최신 권한을 재평가한 대화·브리핑·다음 행동과 저장 기록 조회 | 없음 |
| `list_pending_decisions` | 남은 질문과 현재 권한으로 답할 수 있는 기존 질문을 구분하여 조회 | 없음 |
| `get_human_decisions` | 기록된 사람의 선택과 다음 행동 메모 조회 | 없음 |
| `get_next_action` | API가 판정한 권한 준수·대기·맥락 갱신·사람 결정 반영 안내 | 없음 |

**사람의 결정이나 권한·우선순위를 생성·수정하는 MCP 도구는 없다.** 사람은 대시보드에서 응답하고, 에이전트는 그 결과를 조회한다. 권한 출처는 `local_operator_record`이며 원격 소유자 신원이나 동의를 인증하지 않는다. 도구 목록의 제한은 로컬 HTTP 쓰기 API의 호출자 인증을 대신하지 않는다. 서버는 API만 호출하며 SQLite에 직접 쓰지 않는다. `evaluate_authority`는 POST를 쓰지만 기존 기록만 평가하므로 읽기 전용이다. 도구의 읽기 여부·추가 쓰기·멱등성 힌트도 실제 동작에 맞게 선언한다. [공식 ToolAnnotations 정의](https://modelcontextprotocol.io/specification/2025-06-18/schema#toolannotations)

`get_next_action`은 외부 실행을 확인하지 않으므로 `execution_status: "not_verified"`를 반환한다. `delivery_status: "unknown"`은 실제로 전달하지 않았다는 판정이 아니라 전달 여부를 모른다는 뜻이다. 사람이 이미 전달했다고 입력한 경우도 독립된 전달 영수증과 구분한다.

### 최신 권한과 다음 행동의 공통 계약

`evaluate_authority`가 사용하는 `POST /api/authority/evaluate`는 항상 `evaluation_scope: "all_scope_holders"`로 판정한다. 선택 인자 `agents`는 `requested_agents`·`requested_authorized_agents` 요약만 추가하며, 생략한 에이전트나 다른 소유자의 충돌을 숨길 수 없다. 예를 들어 A·B의 소유자가 다르면 `agents: ["A"]`로 조회해도 공동 승인 전에는 `cross_owner_conflict`다.

MCP의 `get_next_action`과 Skill 도우미의 `next-action`은 모두 `GET /api/sessions/{session_id}/next-action`의 응답을 사용한다. 각 클라이언트가 저장된 질문 수만 보고 다음 행동을 다시 계산하지 않는다. 세션·브리핑·다음 행동 조회는 최신 위임 레지스트리로 권한을 재평가하며, 저장된 모델 추출 결과를 덮어쓰거나 새 모델 호출을 만들지 않는다.

| 현재 상태 | 다음 행동 |
| --- | --- |
| 같은 scope/action의 두 소유자 중 일부만 우선순위 승인 | `wait_for_human`; 소유자 충돌 유지 |
| 두 소유자의 승인과 B 우선순위 기록이 유효하고 다른 대기 사유가 없음 | `follow_authority`; 해당 `decision_owner`는 B |
| 해당 범위의 유효 위임을 모두 철회 | `wait_for_human`; `authority_gap` |
| 브리핑 이후 대화·기록된 결정이 바뀜 | `refresh_coordination_context`; 이전 결정 추출만으로 진행하지 않음 |
| 실제 사람 응답을 기다리도록 기록된 상태 | `wait_for_response`; 권한이 있어도 해당 응답 대기 유지 |

`covered_pending_decisions`에는 현재 권한으로 답할 수 있는 기존 질문만 들어간다. 질문이 권한의 결정권자 확인 유형이고, 근거 발화가 하나의 명확한 scope/action에 대응하며, 그 범위가 승인된 경우에만 재질문 대상에서 제외한다. 다른 범위·유형의 질문이나 근거가 모호한 질문은 `remaining_pending_decisions`에 남는다. 원본 `requests`의 `pending` 상태와 `recorded_pending_decisions`는 보존하며 가짜 사람 응답·결정 ID를 생성하지 않는다. `list_pending_decisions`도 같은 API 응답을 이용하므로 기존 질문 전체와 남은 질문을 구분할 수 있다.

위임 기록만 바뀐 경우 `authority_stale`은 최초 브리핑 당시와 기록이 달라졌다는 표시이며 반환된 권한 판정은 이미 최신이다. `conversation_stale`이 참이면 결정 대상의 추출 자체가 오래되었으므로 맥락 갱신이 필요하다. 대시보드에서 저장하는 우선순위 승인은 정확한 scope/action과 확인한 위임 기록의 `grant_revision`에 연결된다. 화면이 읽은 `registry_revision`을 `expected_revision`으로 보내며, 그 사이 기록이 바뀌면 HTTP 409로 거부되어 최신 기록을 다시 확인해야 한다.

## 로컬 Streamable HTTP 연결

URL 방식만 지원하는 **같은 컴퓨터의** MCP 클라이언트에서는 다음 서버를 실행한다.

```bash
uv --directory "$ARBITER_ROOT" run python -m arbiter.mcp_server --transport streamable-http
```

연결 URL:

```text
http://127.0.0.1:8788/mcp
```

이 서버는 `127.0.0.1`에만 바인딩한다. 다른 컴퓨터나 클라우드의 에이전트에서 이 주소로 연결할 수 없다. 외부 인증·호스팅은 아직 구현하지 않았으며, URL을 등록하는 것만으로 원격 접근이 생기지는 않는다. 포트는 `--port`, 백엔드 API 주소는 `--api-url` 또는 `ARBITER_API_URL`로 변경할 수 있다. 현재 백엔드 주소는 같은 호스트의 loopback origin만 허용한다.

## 구현된 연결 검증

```bash
uv --directory "$ARBITER_ROOT" run pytest tests/test_mcp.py -q
```

현재 `tests/test_mcp.py`의 20개 테스트에는 SDK 클라이언트의 프로토콜 초기화·도구 조회, 다음 행동 판정, 임시 SQLite를 사용하는 실제 API·stdio MCP 프로세스 간 통신 검증이 포함된다. 핵심 확인 항목은 다음과 같다.

1. 세션 등록 후 두 에이전트의 상호 대기 메시지 기록.
2. 같은 `event_id` 재전송 시 메시지·질문 중복 없음.
3. 사람의 응답 전 `wait_for_human` 반환.
4. 사람 역할의 별도 HTTP 요청으로 결정 입력.
5. MCP에서 실제 저장된 결정과 `follow_human_decision` 조회.
6. 조회 반복으로 새로운 질문이 생기지 않으며 결정 생성 도구 호출은 거부됨.
7. 사람 역할의 별도 HTTP 요청으로 두 소유자의 권한을 등록하고, `agents`를 일부만 보내도 소유자 충돌이 유지됨.
8. 부분 승인에서는 대기를 유지하고 공동 승인·우선순위 기록 후 `follow_authority`를 반환. 정확히 관련된 질문만 별도로 분류하고 원본 pending 사건과 빈 사람 결정 목록을 보존.
9. 위임 철회 후 `authority_gap`, 대화 변경 후 `refresh_coordination_context`로 바뀌며 이전 권한 안내로 진행하지 않음.
10. 같은 세션의 MCP·Skill Python 도우미가 동일한 다음 행동 응답을 반환. 이 흐름은 모델 추출 결과를 시험 데이터로 주입하여 새 모델 호출 없이 검증.

추가로 로컬 Streamable HTTP 연결, HTTP 오류·타임아웃, 민감 필드 제외, 도구 메타데이터를 검사한다. 이는 **MCP와 로컬 API 사이의 실제 통신 검증**이며, 피클 앱·슬랙에 실제 연결하거나 메시지를 발송했다는 뜻은 아니다.

2026-10-29 방문자 체험 격리 기능까지 포함한 최신 전체 테스트 실행은 **182개 테스트·8개 하위검증 통과, 10.50초**다. `.runtime/verification-railway.json`은 완료 실행의 기록 요약이며 원시 stdout 로그는 아니다. 앞선 권한 흐름 검증은 `.runtime/verification-20261029.json`에 별도로 보존한다. 테스트 수를 권한 탐지 정확도나 실제 사용자 성과로 해석하지 않는다.
