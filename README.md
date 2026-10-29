# 컬처핏(Culture-Fit)

에이전트 간 대화의 결정 대상과 사람의 위임 권한을 연결해, 담당 에이전트에게 우선권을 주거나 관련 소유자에게 필요한 질문을 제시하는 한이음 로컬 프로토타입입니다. 재사용 가능한 오픈소스 Skill·MCP·A2A로 제공하는 것이 목표입니다.

공식 프로젝트명은 컬처핏(Culture-Fit)이며 구현 패키지와 실행 명령은 기존 코드명 `arbiter`를 사용합니다.

[방문자 체험 데모](https://culture-fit-demo-production.up.railway.app) · [관제 화면](https://culture-fit-demo-production.up.railway.app/workspace) · [Railway 배포 안내](docs/railway-deployment.md)

공개 체험은 방문자마다 권한·대화를 분리하고, 합성 대화와 기록된 모델 분석을 제공합니다. 새 모델 호출·외부 Slack 연결은 사용하지 않습니다. 자신의 환경에서 실행하면 아래의 로컬 연결 기능을 설정할 수 있습니다.

“주인에게 확인하고 알려드리겠다”는 말만 반복하는 개인 에이전트와 서로 검토를 미루는 협업 에이전트를 주요 사례로 다룹니다. **확인 약속, 실제 전달, 사람의 답변, 외부 작업 완료를 서로 다른 상태로 기록합니다.**

## 실행

Python 3.11 이상과 [uv](https://docs.astral.sh/uv/)가 필요합니다.

```bash
cd hanium-arbiter
uv sync --frozen
uv run uvicorn arbiter.app:app --host 127.0.0.1 --port 8787
```

- 메인: <http://127.0.0.1:8787/>
- 관제: <http://127.0.0.1:8787/workspace>
- MCP 연결 설정: <http://127.0.0.1:8787/workspace#integration>
- HTTP API 명세: <http://127.0.0.1:8787/docs>

통제 시뮬레이션과 대화 가져오기는 모델 계정 없이 실행됩니다. 실제 모델 모드는 설치·로그인된 Codex CLI를 호출하며 계정의 사용량을 소비합니다. 상태는 `.runtime/arbiter.sqlite3`에 보존합니다. `ARBITER_DB`로 DB 경로를 바꿀 수 있습니다.

## 구현 범위

| 기능 | 현재 동작 |
|---|---|
| 대화 수신 | 텍스트 붙여넣기, 이벤트 HTTP API, MCP 도구 호출 |
| 외부 대화 점검 | 한국어 명시적 확인 약속·대기 표현에서 후보 추출, 발화 근거 연결 |
| 온톨로지 | Person·Agent·Task·Claim·Evidence·Decision·Commitment와 관계를 명시적으로 저장·표시 |
| 권한 판정 | 사람의 위임 기록에서 정확한 범위·행동·조건·만료·회수를 대조하고, 소유자가 다르면 공동 승인 기록이 있는 우선권만 적용 |
| 결정 브리핑 | 실제 모델이 결정 대상과 원문 인용을 추출한 뒤 권한 규칙으로 개입 후보를 판정. 명시적 생성 요청 시 호출하며 의미 추출의 정확도는 별도 평가 필요 |
| 지식 충돌 | 구조화된 주장에 대해 범위·항목·값을 비교, 최신 주장으로 갱신하거나 철회 |
| 진행 감지 | 새로 충족된 산출물 조건·새 유효 근거·사람의 결정을 진행으로 계산 |
| HITL | 구체적 선택 질문, 응답 기록, 담당자·다음 행동 메모, 결정 후 재개 |
| 실행 관리 | 누적 턴 한도, 수동 중지, 동시 실행 방지, 정상적인 사람 응답 대기 시 자동 실행 중지 |
| 관제 화면 | 현황·대화·결정함·지식맵·실험·연결 설정 탭, 명시적 페이지 이동 |
| 실험 | 8개 통제 시나리오 × 3개 정책 비교, 실행별 JSON·CSV·요약 |
| 내보내기 | 대화·판정·결정·실측 사용량을 JSON 또는 Markdown으로 저장 |

구조화된 시나리오의 주장 충돌과 외부 자연어 대화의 규칙 기반 점검은 별개 경로입니다. 임의의 피클·Slack 대화에서 일반적인 의미 충돌을 자동 추론한다고 주장하지 않습니다. 온톨로지는 경량 타입·관계 모델이며 OWL 추론기나 SPARQL 서버는 아닙니다.

근거는 `CLAIMED`(주장), `REFERENCED`(참조 존재), `VERIFIED`(로컬 검사)로 구분합니다. 현재 `VERIFIED`는 **해당 JSON 산출물의 조건 검사**에 한정됩니다. 임의 저장소 체크아웃·테스트 실행, 메시지 전송, 실제 참석 여부를 검증하지 않습니다.

## 기존 에이전트에 연결

```bash
uv run python -m arbiter.mcp_server
```

MCP 서버는 실행 중인 로컬 API를 사용합니다. [설정 예시·호스트 지침·검증 범위](docs/mcp-connection.md)를 참고하세요. 대화 등록·보고, 상태·결정 조회에 더해 `get_authority`, `evaluate_authority`를 포함한 8개 도구를 제공합니다.

MCP 지원 호스트에 서버를 등록하고 대화를 보고하도록 지시하면 에이전트 소스 코드를 수정하지 않고 사용할 수 있습니다. 연결만으로 기존 대화를 자동 수집하지 않습니다. 사람의 결정을 생성하거나 권한을 부여하는 MCP 도구는 제공하지 않습니다.

- [Slack 연결](docs/slack-connection.md): Socket Mode로 허용된 채널의 봇 메시지를 스레드별로 저장. 실제 워크스페이스 토큰 설정·연결은 아직 하지 않았습니다.
- [A2A 서비스](docs/a2a-connection.md): Agent Card, 분석 요청, 작업 조회·취소, SQLite 저장. 로컬 8789 포트이며 공식 SDK 1.3.0으로 해당 경로를 검증했습니다. 스트리밍·웹훅·외부 인증은 미구현입니다.
- [OpenClaw 연결](docs/openclaw-connection.md): 설치된 2026.3.11에서 인식·설정 검증한 [Skill과 실행 코드](skills/arbiter-coordination/SKILL.md). 최신 버전용 MCP 설정 예제는 별도로 제공합니다.

위임·공동 승인 정보는 로컬 운영자가 입력합니다. 실제 원격 소유자의 신원이나 동의를 인증하지 않으며, 반환된 우선권은 외부 작업 실행이나 사실 검증을 의미하지 않습니다. 패키지 공개 배포는 아직 하지 않았습니다.

## 검증과 결과

```bash
uv run pytest -q
uv run python experiments/run_comparison.py --help
```

저장된 [비교 결과](experiments/results/latest/report.md)는 결정적 시나리오 24회 실행입니다. 사람 응답은 명시적 모의 응답입니다.

| 정책 | 조건 충족 | 평균 턴 | 사람 질문 합계 |
|---|---:|---:|---:|
| 횟수 제한 | 2/8 | 14.75 | 0 |
| 주기적 HITL | 8/8 | 5.00 | 7 |
| 정체 감지 HITL | 8/8 | 5.00 | 6 |

정체 감지와 주기적 HITL의 평균 턴은 동일합니다. 이 조건에서는 정상 진행 사례의 질문 1건을 줄였습니다. 횟수 제한 정책은 사람의 정보를 받지 않으므로 성공률 차이를 개입 시점만의 효과로 해석할 수 없습니다. 토큰은 미측정이며 실제 LLM·실사용자 성능이나 통계적 유의성을 입증하지 않습니다. 재현 조건과 한계는 [실험 안내](experiments/README.md)에 있습니다.

MCP 테스트는 실제 stdio·Streamable HTTP 클라이언트와 임시 API 프로세스 사이의 등록·보고·결정 조회를 검증합니다. 권한 코어·API·브리핑·Slack 이벤트·A2A·Skill 도우미를 포함한 방문자 격리를 포함한 최종 테스트는 182개와 8개 하위 사례가 통과했습니다. 실제 Codex [브리핑 점검 2회](experiments/results/briefing-smoke/README.md)에서는 첫 의미 정규화 오류와 지침 보완 후 결과를 모두 보존했습니다. 모의 참석 응답을 실제 소유자의 답변으로 취급하지 않은 이전 실제 모델 사례도 완료 실패로 유지했습니다.

## 공개 소스와 참고 설계

- [MCP 연결](docs/mcp-connection.md), [Slack 연결](docs/slack-connection.md), [A2A 서비스](docs/a2a-connection.md), [OpenClaw 연결](docs/openclaw-connection.md)
- [Railway 방문자 체험 배포](docs/railway-deployment.md)
- [실험 안내](experiments/README.md), [통제 실험 원자료](experiments/results/latest/summary.json), [실제 모델 단일 사례 점검](experiments/results/briefing-smoke/README.md)
- [이전 v0.3 설계](docs/design/v0.3.md) / [이전 결정 이력](docs/decision_log.md): 당시 계획을 보존한 문서이며 현재 구현 범위와 구분합니다.

제출용 보고서·포스터·영상과 원본 첨부는 별도로 관리하며, 이 공개 소스 배포에는 포함하지 않습니다.

기술적 배경은 [AutoGen 종료 조건](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/termination.html), [A2A와 MCP의 역할](https://a2a-protocol.org/latest/topics/a2a-and-mcp/), [Li·Xie의 통합 분석](https://arxiv.org/abs/2505.03864)을 참고했습니다. 프로토콜은 통신 기반을 제공하고, 본 프로젝트는 그 위에서 의미·근거·권한에 따른 개입을 다룹니다.
