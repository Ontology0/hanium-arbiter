# A2A 대화 분석 서비스 연결

Arbiter는 다른 에이전트가 발견하고 호출할 수 있는 **대화 분석 서비스**를 제공한다. HITL 탐지·브리핑 엔진은 기존 로컬 API가 수행하고 A2A 어댑터는 요청, 작업 상태, 분석 결과를 전달한다. MCP가 작업 중인 에이전트의 대화 기록·상태 조회·사람 결정 확인 도구라면, A2A는 다른 에이전트가 Arbiter에 분석 작업을 맡기는 입구다.

구현·테스트 환경은 `uv.lock`의 **a2a-sdk 1.3.0**, A2A **1.0 JSON-RPC** 인터페이스다. 과거 SDK의 0.3 예제를 그대로 사용하지 않는다. 공식 전체 적합성 인증을 받은 구현이라는 의미는 아니다. [공식 Python SDK](https://github.com/a2aproject/a2a-python), [A2A 규격](https://a2a-protocol.org/latest/specification/).

## 실행

프로젝트 루트에서 기존 Arbiter API와 A2A 어댑터를 각각 실행한다.

```bash
uv sync
uv run uvicorn arbiter.app:app --host 127.0.0.1 --port 8787
```

다른 터미널:

```bash
uv run python -m arbiter.a2a_server
```

|항목|주소·설정|
|---|---|
|AgentCard|`http://127.0.0.1:8789/.well-known/agent-card.json`|
|JSON-RPC|`http://127.0.0.1:8789/`|
|기존 API|`http://127.0.0.1:8787`|
|사람 대시보드|`http://127.0.0.1:8787/workspace`|
|A2A 작업 저장소|`.runtime/a2a.sqlite3`|
|기본 분석 제한 시간|300초|

`--port`, `--api-url`, `--db`, `--timeout`으로 조정한다. `ARBITER_API_URL`, `ARBITER_A2A_DB` 환경변수도 지원한다. 인증 없는 개발용 서비스이므로 실행 호스트와 API 주소를 루프백으로 제한한다. 실제 브리핑에는 설치·로그인된 Codex CLI가 필요하며, 없으면 작업이 명시적으로 실패한다. 모의 브리핑으로 자동 대체하지 않는다.

## 공식 클라이언트 예시

다음 코드는 실제 로컬 분석을 요청하므로 모델 호출이 발생할 수 있다. 대화는 로컬 저장소에 보관되고 브리핑을 위해 구성된 Codex 제공자에게 전달된다.

```python
import asyncio
import httpx
from a2a import types
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.helpers.proto_helpers import get_data_parts, new_text_message

async def main():
    async with httpx.AsyncClient(timeout=15, trust_env=False) as http:
        card = await A2ACardResolver(http, "http://127.0.0.1:8789").get_agent_card()
        client = ClientFactory(ClientConfig(
            streaming=False, polling=True, httpx_client=http,
        )).create(card)
        request = types.SendMessageRequest(
            message=new_text_message(
                "agent-a: B의 검토를 기다립니다.\nagent-b: A가 먼저 결정해 주세요.",
                role=types.Role.ROLE_USER,
            ),
            configuration=types.SendMessageConfiguration(return_immediately=True),
            metadata={"source": "slack", "title": "리뷰 책임자 확인"},
        )
        task = None
        async for response in client.send_message(request):
            if response.HasField("task"):
                task = response.task
        assert task is not None
        terminal = {
            types.TaskState.TASK_STATE_COMPLETED, types.TaskState.TASK_STATE_FAILED,
            types.TaskState.TASK_STATE_CANCELED, types.TaskState.TASK_STATE_REJECTED,
        }
        while task.status.state not in terminal:
            await asyncio.sleep(1)
            task = await client.get_task(types.GetTaskRequest(id=task.id))
        print(types.TaskState.Name(task.status.state))
        for artifact in task.artifacts:
            print(get_data_parts(artifact.parts))
        # 진행 중 취소: await client.cancel_task(types.CancelTaskRequest(id=task.id))

asyncio.run(main())
```

입력은 1~40,000자의 텍스트다. 선택 metadata는 `source`(`slack`, `pickle`, `manual`)와 `title`(1~150자)이다. `source="slack"`는 대화의 출처 표기이며 Slack 연결이나 전송을 수행하지 않는다. 기존 task에 메시지를 추가하는 방식은 지원하지 않으므로 변경된 대화는 새 분석으로 요청한다.

## 작업 수명과 결과의 의미

1. `SendMessage`가 텍스트를 받아 로컬 `/api/intake`에 세션을 생성한다.
2. `/api/sessions/{id}/brief`를 시작하고 생성 상태를 조회한다.
3. 근거 인용·구조화 상태·탐지 결과를 포함한 브리핑이 준비되면 `coordination-analysis` JSON artifact를 반환한다.
4. `GetTask`는 SQLite에 저장된 결과를 조회한다. 작업은 제출·진행·완료 또는 실패·취소 상태로 끝난다.

Artifact에는 `session_id`, `dashboard_url`, `analysis_status`, `execution_status`, `brief`, `scope`가 있다. `brief`는 브리핑 API 결과를 보존한다. `analysis_status="completed"`는 **분석 완료**이며, `execution_status="not_verified"`는 실제 외부 업무가 검증되지 않았다는 뜻이다. A2A 응답이 사람의 승인, 참석 확정, Slack 메시지 전송 또는 에이전트 작업 완료를 대신하지 않는다.

`CancelTask`는 결과 전달을 중단하고 로컬 `/brief/cancel`을 호출한다. 이미 시작된 모델 프로세스가 끝날 수 있지만 해당 결과를 적용하지 않는다. 외부 에이전트의 실행은 중단하지 않는다. 취소 API에 연결할 수 없으면 취소 응답 메시지에 그 한계를 기록한다. 분석 제한 시간을 넘으면 실패 상태로 끝나며 늦은 결과 전달을 막는다.

완료된 작업은 재시작 후에도 조회된다. 재시작 시 남은 진행 작업은 재개할 수 없으므로 실패로 전환한다. 서비스가 재시작되었다고 외부 업무나 기존 브리핑이 중단됐다고 주장하지 않는다. SQLite는 단일 로컬 서비스 인스턴스용이며 공유 DB를 사용하는 분산 실행을 구현한 것은 아니다.

## 지원 범위와 검증

지원: AgentCard 발견, `SendMessage`, `GetTask`, `CancelTask`, SQLite 보관. 미지원: streaming, push notification, `ListTasks`, 인증·원격 배포, A2A를 통한 사람 결정 생성. AgentCard의 streaming/push capability는 모두 false다.

```bash
uv run pytest tests/test_a2a.py -q
```

6개 테스트는 공식 SDK 클라이언트와 실제 로컬 HTTP 서버를 사용한다. 발견→분석 요청→조회→artifact, 취소 후 늦은 결과 차단, 빈 입력 오류, 분석 실패, 제한 시간, 저장소 재시작·tenant 구분을 검증한다. **브리핑 API는 통제된 모의 응답**이므로 이 테스트는 A2A 통신·수명주기 검증이며, LLM 분석 정확도나 Slack 현장 효과 실험이 아니다. 구현은 [a2a_server.py](../backend/arbiter/a2a_server.py), 검증 코드는 [test_a2a.py](../tests/test_a2a.py)에 있다.
