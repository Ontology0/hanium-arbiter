# OpenClaw 연결: Skill 코드·설명 + 선택적 MCP

이 저장소의 `skills/arbiter-coordination/`는 `SKILL.md`와 Python 표준 라이브러리 도우미를 함께 포함한다. 에이전트 코드를 수정하지 않고 기존 실행 도구로 로컬 Arbiter API에 대화를 보고하고 권한·사람 결정을 조회할 수 있다. MCP를 지원하는 클라이언트에는 같은 서버의 도구를 제공한다. 패키지를 레지스트리에 배포하거나 사용자의 전역 설정을 자동 변경하지 않는다.

## 버전에 맞는 경로 선택

| 경로 | 예제 파일 | 확인 범위 |
| --- | --- | --- |
| Skill + Python 도우미 | `integrations/openclaw/openclaw.skills.example.json` | 설치된 OpenClaw **2026.3.11**의 격리된 설정 검증 통과, 스킬 발견 `eligible=true` 확인 |
| OpenClaw 네이티브 MCP + Skill | `integrations/openclaw/openclaw.mcp.example.json` | 최신 공식 문서의 `mcp.servers` 형식. 설치된 **2026.3.11은 지원하지 않음** |

실제로 `2026.3.11`의 `openclaw config validate --json`은 최상위 `mcp`에 `Unrecognized key: "mcp"`를 반환했다. 최신 문서에 설정이 있다고 구버전에서 연결된 것으로 간주하면 안 된다. 지원 버전에서 직접 검증하기 전에는 MCP 예제를 기존 설정에 합치지 않는다. 자동 업그레이드는 하지 않는다.

공식 근거: [OpenClaw Skills](https://docs.openclaw.ai/tools/skills), [MCP·Skills 설정](https://docs.openclaw.ai/gateway/config-extensions/). 전자는 `SKILL.md`와 `skills.load.extraDirs`를 설명하고, 후자는 현재 버전의 `mcp.servers`를 설명한다.

## 1. 로컬 API 준비

아래 경로는 자신의 체크아웃 위치로 바꾼다.

```sh
export ARBITER_ROOT="/absolute/path/to/hanium-arbiter"
export ARBITER_API_URL="http://127.0.0.1:8787"
uv --directory "$ARBITER_ROOT" sync
uv --directory "$ARBITER_ROOT" run python -m uvicorn arbiter.app:app --host 127.0.0.1 --port 8787
```

대시보드는 `http://127.0.0.1:8787/`이다. OpenClaw 실행 도구와 API가 같은 호스트·네트워크 공간에 있어야 한다. 컨테이너나 원격 샌드박스의 `127.0.0.1`은 호스트 API가 아니다. 현재 도우미와 MCP 브리지는 로컬 연결만 지원하며 외부 인증·다중 사용자 본인 확인 서버는 제공하지 않는다.

## 2. Skill 설정 검증과 연결

Python 3.10 이상이 필요하며 도우미 자체에는 pip 의존성이 없다. 먼저 전역 설정을 건드리지 않고 예제만 검증한다.

```sh
export ARBITER_ROOT="/absolute/path/to/hanium-arbiter"
ARBITER_CHECK_DIR="$(mktemp -d)"
OPENCLAW_STATE_DIR="$ARBITER_CHECK_DIR/state" \
OPENCLAW_CONFIG_PATH="$ARBITER_ROOT/integrations/openclaw/openclaw.skills.example.json" \
openclaw config validate --json
```

이 명령은 설정 구조를 검사하며 에이전트 실행·모델 호출·실제 연결을 수행하지 않는다. 적용할 때는 예제의 `skills` 항목을 기존 OpenClaw 설정에 병합하고 다른 스킬 경로를 보존한다. 전체 설정 파일을 예제로 덮어쓰지 않는다. OpenClaw를 시작하는 환경에도 `ARBITER_ROOT`가 있어야 한다. 서비스 환경에 변수를 제공하기 어렵다면 예제의 `${ARBITER_ROOT}/skills`를 실제 절대경로로 바꾼다. 실행 중 세션에서 스킬이 보이지 않으면 새 세션에서 확인한다.

도우미 연결 확인:

```sh
python3 "$ARBITER_ROOT/skills/arbiter-coordination/scripts/arbiter_client.py" get-authority
python3 "$ARBITER_ROOT/skills/arbiter-coordination/scripts/arbiter_client.py" evaluate \
  --scope "review:proposal" --action approve --agents reviewer-a reviewer-b
```

권한이 없으면 `authority_gap`을 반환하는 것이 정상이다. 테스트를 통과시키려고 에이전트가 스스로 권한을 등록하지 않는다. 사람이 대시보드에서 소유자·범위·행위별 권한과 필요한 우선순위를 먼저 기록한다. `evaluate`의 `--agents`는 요청한 에이전트들의 요약만 선택한다. API는 항상 `evaluation_scope: "all_scope_holders"`로 같은 scope/action의 전체 보유자를 판정하므로 일부 에이전트만 지정해도 다른 소유자의 권한·충돌이 제외되지 않는다.

기존 세션의 다음 행동은 다음과 같이 조회한다. 세션 ID는 실제 등록 결과로 바꾼다.

```sh
python3 "$ARBITER_ROOT/skills/arbiter-coordination/scripts/arbiter_client.py" next-action \
  --session-id "실제-session-id"
```

도우미는 `GET /api/sessions/{session_id}/next-action`을 그대로 사용하며 MCP의 `get_next_action`과 같은 판정 결과를 받는다. 클라이언트가 원본 `requests`의 pending 개수만으로 계속 대기해야 한다고 다시 판단하지 않는다.

## 3. OpenClaw에 전달할 사용 지침

다음 문구를 기존 에이전트에 줄 수 있다. 해당 에이전트의 기존 실행 도구 사용 승인은 그대로 적용된다.

> `arbiter-coordination` 스킬을 사용해 이 협업 대화를 기록해 주세요. 기존 세션이 있으면 재사용하고 없으면 한 번 등록한 뒤 session_id를 보관하세요. 인계 전에는 실제 메시지를 안정적인 event_id로 보고하고, 정확한 scope/action의 전체 보유자에 대해 권한을 조회하세요. `next-action`이 `follow_authority`이면 `authorized_scope_actions`의 각 결정권자를 기존 실행 권한 안에서 따르고 같은 승인을 다시 묻지 마세요. `wait_for_human`이면 남은 질문을 필요한 사람에게 한 번 안내하고 해당 의존 작업을 대기하세요. `wait_for_response`는 이미 기록된 응답 대기를 존중하세요. `refresh_coordination_context`이면 최신 대화의 결정 대상을 확인하거나 브리핑을 갱신하기 전까지 이전 범위로 진행하지 마세요. 사람이 응답하거나 위임을 바꿨다고 알려주면 다음 행동을 한 번 다시 읽고 중복 실행 없이 이어가세요. 사람을 대신해 권한이나 결정을 만들지 마세요.

스킬이나 MCP를 연결하는 것만으로 다른 에이전트의 메시지가 자동 수집되지는 않는다. 명시적인 보고 호출이 필요하다. Slack 채널을 자동 관찰하려면 별도 [읽기 전용 Slack 수신기](slack-connection.md)를 설치한다. 한 Slack 스레드에 이미 세션이 있으면 그 세션을 공유해 중복 등록을 피한다.

## 4. MCP 지원 버전에서 연결

`openclaw.mcp.example.json`은 **설치된 2026.3.11용이 아니다**. `mcp.servers`를 지원하는 버전에서 같은 격리 검증 명령의 설정 경로만 바꿔 검사하고, 지원을 확인한 뒤 기존 설정에 병합한다. `uv`가 서비스 PATH에 없으면 `command`를 그 환경의 uv 절대경로로 바꾼다.

서버 자체의 stdio 실행 명령:

```sh
uv --directory "$ARBITER_ROOT" run python -m arbiter.mcp_server
```

선택적으로 같은 호스트의 Streamable HTTP를 사용할 수 있다.

```sh
uv --directory "$ARBITER_ROOT" run python -m arbiter.mcp_server --transport streamable-http
```

주소는 `http://127.0.0.1:8788/mcp`다. 외부 에이전트에서 이 주소를 그대로 사용하는 원격 호스팅 기능은 아니다.

| MCP 도구 | 표준 라이브러리 CLI | 역할 |
| --- | --- | --- |
| `get_authority` | `get-authority` | 사람이 관리하는 권한 레지스트리 조회 |
| `evaluate_authority` | `evaluate` | 정확한 scope/action의 전체 보유자 판정; agents는 요청 대상 요약만 선택 |
| `register_conversation` | `register` | 최초 대화 등록, 반복하면 새 세션 생성 |
| `record_message` | `report` | 실제 메시지 보고, 같은 event_id 중복 제거는 API가 담당 |
| `get_coordination_state` | `state` | 최신 권한을 재평가한 세션·브리핑·coordination_advice 조회 |
| `list_pending_decisions` | `next-action`의 질문 필드 | 남은 질문·권한으로 답할 수 있는 기존 질문·원본 pending 기록 구분 |
| `get_human_decisions` | `decisions` | 기록된 사람 결정 읽기 |
| `get_next_action` | `next-action` | 같은 API 응답으로 권한 준수·대기·맥락 갱신 등 안내 |

`evaluate_authority`는 HTTP POST를 쓰지만 기존 기록만 읽는 판정이므로 MCP `readOnlyHint=true`다. 사람 결정 작성, 권한 부여·회수, 우선순위 수정 도구는 제공하지 않는다. 도구 목록 제한은 인증 경계 자체가 아니며, 로컬 API에 접근 가능한 다른 프로그램까지 차단하는 보안 격리는 구현하지 않았다.

## 최신 권한 반영과 질문 보존

세션·브리핑·다음 행동 조회는 최신 권한 기록을 재평가한다. 저장된 모델 추출 결과를 바꾸거나 추가 모델 호출을 하지 않는다. 위임만 바뀌면 `authority_stale` 표시는 남을 수 있지만 반환된 권한은 최신이다. 대화·기록된 결정이 바뀌어 `conversation_stale`이 참이면 `refresh_coordination_context`를 반환하며 과거 추출만으로 진행시키지 않는다.

현재 권한으로 답할 수 있는 기존 결정권자 질문은 `covered_pending_decisions`로 분리된다. 질문의 근거 발화가 하나의 승인된 scope/action에 명확히 대응해야 하며, 다른 종류·범위의 질문과 모호한 질문은 `remaining_pending_decisions`에 남는다. `recorded_pending_decisions`와 세션의 원본 `requests`는 보존되고 사람 응답이나 결정 ID는 만들어지지 않는다. 실제 남은 질문은 `next-action`의 결과를 기준으로 확인한다.

대시보드에서 서로 다른 두 소유자의 승인과 B 우선순위를 기록하면, 다른 대기 사유가 없는 관련 결정에서 `follow_authority`와 `decision_owner: "B"`를 받을 수 있다. 일부 소유자만 승인하면 `wait_for_human`을 유지하며 해당 범위의 유효 위임을 모두 철회하면 `authority_gap`으로 다시 대기한다. 이미 기록된 실제 응답 대기 역시 권한 확인만으로 해제하지 않는다.

우선순위 승인은 정확한 scope/action과 확인한 위임 기록의 `grant_revision`에 연결된다. 대시보드는 읽은 `registry_revision`을 `expected_revision`으로 보내며, 저장 전에 권한 기록이 바뀌면 HTTP 409로 거부한다. 이때 최신 기록을 다시 읽고 사람이 검토해야 한다. 이 절차는 로컬 기록의 일관성 검사이며 원격 소유자 본인 인증은 아니다.

## 판정과 검증의 한계

권한 기록의 출처는 `local_operator_record`다. 서로 다른 소유자의 우선순위에는 관련 소유자 전원의 승인 기록이 필요하지만, 원격 소유자의 신원을 인증했다는 뜻은 아니다. 권한과 우선권은 사실의 진위·메시지 전달·실행 완료의 증거도 아니다. `evaluate` 자체는 질문을 자동 발송하거나 사람의 승인을 만들지 않는다.

검증 결과: `test_mcp.py` **20개**, `test_skill_client.py` **13개**, 합계 **33개 통과**. 실제 임시 API·SQLite·stdio MCP 연결에서는 agents 일부 지정으로 충돌을 숨길 수 없는 점, 부분 승인과 공동 승인, 관련 질문만 재질문 대상에서 제외하는 처리, 원본 pending·사람 결정 보존, 철회·대화 변경 후 재판정을 확인했다. 구조화된 브리핑을 시험 데이터로 주입했으며 이 흐름에서 모델은 호출하지 않았다. Python 도우미의 `next-action`도 같은 API 응답을 반환했다.

2026-10-29 방문자 체험 격리 기능까지 포함한 최신 전체 테스트 실행은 **182개·8개 하위검증 통과(10.50초)**다. 별도 권한 흐름 UI 점검은 **18개 행동 검증 통과·모델 요청 0회**이며, OpenClaw의 실제 모델 실행 검증은 아니다. 최신 전체 실행은 `.runtime/verification-railway.json`, 앞선 권한 흐름 검증은 `.runtime/verification-20261029.json`에 보존한다. 두 파일은 완료 실행의 기록 요약이며 원시 pytest stdout 로그가 아니다.

OpenClaw에서는 격리된 설정 검증과 `skills info arbiter-coordination --json`의 `eligible=true`를 확인했다. 스킬의 정적 형식 검증도 통과했다. **OpenClaw 에이전트의 실제 모델 실행 및 실제 Pickle·Slack 연결 성공으로 보고하지 않는다.**
