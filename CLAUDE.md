# CLAUDE.md

한이음 드림업 2026 — 에이전트 간 충돌 중재 시스템. AI 어시스턴트용 작업 지침.

## 이 저장소의 규칙

이 프로젝트는 "근거 없는 주장은 CLAIMED, 재현된 것만 VERIFIED" 를 구현하는 시스템이다.
**우리 저장소의 작업도 같은 기준을 지킨다.** 아래는 취향이 아니라 이 프로젝트의 정체성이다.

### 1. 요구사항은 goal.md 가 유일한 소스

- 요구사항 추가·수정·삭제는 `docs/goal.md` 에서만 한다
- `checklist.json` 을 직접 손으로 고치지 않는다. 도구로만 바꾼다
- goal.md 를 고치면 훅이 `tools/sync_checklist.py` 를 돌려 자동 대조한다
- 훅이 안 돌았어도 `pytest` 가 잡는다 (`tests/test_checklist.py::test_checklist_is_in_sync_with_goal`)

요구사항 ID(`UR-01`, `FR-11`, `NFR-04`)는 **재사용 금지**다. 이력이 ID에 붙어 있다.
요구사항을 빼려면 지우지 말고 우선순위를 `dropped` 로 바꿔라.

### 2. 상태 변경은 이유와 함께만

`checklist.json` 의 `status` 는 `tools/record_decision.py` 로만 바꾼다:

```bash
python3 tools/record_decision.py \
  --by 세령 \
  --affects FR-11 \
  --question "무엇을 두고 갈렸는가" \
  --decision "무엇으로 정했는가" \
  --why "왜" \
  --set-status FR-11=in_progress
```

`--why` 는 필수다. 이유 없는 기록은 3개월 뒤에 아무 값이 없다.

### 3. 기록하는 것은 '사람의 결정'이다

AI 가 무슨 코드를 썼는지는 git log 에 이미 다 있다. 다시 적지 마라.
`record_decision.py` 에 남길 것은 **사람이 갈림길에서 고른 것**이다:

| 남긴다 | 남기지 않는다 |
|---|---|
| 두 방식 중 하나를 사람이 골랐다 | 함수를 리팩터링했다 |
| 제안을 사람이 거절하고 다른 걸 시켰다 | 테스트를 추가했다 |
| 범위를 줄이기로 했다 | 오타를 고쳤다 |
| 미뤄둔 이슈를 결론냈다 | 의존성을 올렸다 |

`--by` 에는 사람 이름을 넣는다. AI 이름을 넣지 않는다.
**AI 가 스스로 판단해서 결정을 기록하지 않는다.** 사람에게 물어보고, 답을 받은 뒤에 기록한다.

### 4. 테스트 없이 done 없음

`status` 를 `done` 으로 바꾸려면 `tests` 에 대응 테스트를 적어야 한다.
적어둔 테스트가 실재하지 않으면 테스트가 실패한다. (NFR-06)

```bash
python3 tools/record_decision.py ... --set-status FR-11=done
# 그 전에 checklist.json 의 FR-11.tests 에 "tests/test_evidence.py::test_grading" 같은 항목이 있어야 함
```

### 5. 지어내지 않는다

- 측정하지 않은 수치, 벤치마크 점수, 정확도를 쓰지 않는다
- 구현 안 된 것을 구현된 것처럼 문서에 적지 않는다
- 상태는 **구현됨 / 계획됨 / 미정** 세 가지로 구분해서 말한다

현재 이 저장소는 **요구사항 정의 단계**다. 백엔드·프론트엔드 코드는 아직 없다.

## 명령어

| 할 일 | 명령 |
|---|---|
| 테스트 | `pytest` |
| goal.md 대조 | `python3 tools/sync_checklist.py` |
| 어긋났는지만 확인 | `python3 tools/sync_checklist.py --check` |
| 매핑표 재생성 | `python3 tools/gen_traceability.py` |
| 결정 기록 | `python3 tools/record_decision.py --help` |
| 진행 현황 | `python3 tools/status_report.py` |

## 구조

```
hanium-arbiter/
├── docs/
│   ├── goal.md           요구사항 정의 (단일 소스, 사람이 씀)
│   ├── design/v0.3.md    설계 문서
│   ├── decision_log.md   설계 수준 결정 (산문)
│   ├── traceability.md   요구사항↔화면↔ERD 매핑표 (도구가 생성, 손대지 말 것)
│   └── evidence/         실측 근거 자료 (제안서·보고서용)
├── checklist.json        상태·이력 (도구가 씀, 손대지 말 것)
├── tools/                동기화·기록 도구
├── tests/                pytest
├── backend/              FastAPI (미착수)
├── frontend/             React (미착수)
└── experiments/          실험 트랙 F16 (미착수)
```

`docs/decision_log.md` 와 `checklist.json` 의 `decisions` 는 층위가 다르다.
전자는 **설계 방향**(스택 선택, 범위 확정), 후자는 **요구사항 단위 결정**이다.

## Git

- 작업은 `dev` 브랜치에서. `main` 은 제출 스냅샷
- 커밋 형식: `태그: 내용` — `feat` `fix` `docs` `refactor` `chore` `test`
- 시크릿·토큰·`.env` 를 커밋하지 않는다
