# 실측 충돌 사례집 — Graduation-Project (2026-06)

> 이 문서의 모든 주장은 공개 저장소 `Ontology0/Graduation-Project` 의
> 커밋 SHA·PR·이슈·CI 체크런으로 재현 가능하다. 재현 명령은 부록에 있다.
> 우리 기준으로 전부 **VERIFIED** 등급이다 (외부 저장소를 직접 체크아웃해 대조함).
>
> 수집일: 2026-08-12 · 수집 도구: `git log/show`, `gh api`

## 왜 이 문서인가

제안서의 문제 정의가 "가상의 시나리오"가 아니라 **우리 팀에서 이미 일어난 일**임을
보이기 위해서다. 아래 저장소는 우리 팀의 졸업 프로젝트로, 사람 3명과 코딩 에이전트
2종이 같은 코드베이스에 커밋했다. 중재기가 없던 환경에서 v0.3이 정의한 충돌 유형
(C1·C4)과 거버넌스 문제가 실제로 발생했다.

## 참여 주체 (5)

| 주체 | 정체 | 커밋 관여 |
|---|---|---|
| ryeong03 / 령 | 세령 (로컬 CLI / GitHub 웹, 동일인) | 저자 100 + 67 |
| bbberylll | 팀원 B | 저자 96 |
| dev-ldy03 | 팀원 C (계정 2개) | 저자 43 + 29 |
| Claude Sonnet 4.6 | 코딩 에이전트 (세령 소유) | co-author 39, 단독 저자 2 |
| Cursor | 코딩 에이전트 | co-author 47 |

활동 구간: 2026-03 ~ 2026-07. 5주체가 동시에 몰린 구간은 2026-05-26 ~ 06-04, 06-20.

---

## 사례 1 — C4 중복·상충 구현: 에이전트 산출물이 52분 만에 통째로 폐기됨

**날짜**: 2026-06-01 (시각은 KST)

```
15:28  ryeong03+Claude   telegram_bot.py 수정 커밋 (276a772)
15:32  PR #52 열림 (ryeong03)
15:36  Claude(단독 저자)  _strip_html_tags 헬퍼 추가 (a41e508)
                          — 이미 브랜치에 _format_for_telegram_html 도 있음
15:50  bbberylll          PR #52 를 dev 에 머지 (c6a1c00)
16:26  dev-ldy03          이슈 #60 "Telegram HTML 포맷 안정화" 개설
                          — 방금 머지된 수정과 겹치는 증상들을 나열
16:28  dev-ldy03          telegram_format.py 신규 모듈 커밋 (523af81)
                          — telegram_bot.py 에서 두 함수 삭제(-88줄) 후 재구현
                          — 분기점이 c6a1c00, 즉 PR #52 머지 직후라서
                            git 텍스트 충돌은 0건
16:31  PR #61 열림
16:38  령                 PR #61 머지
```

두 구현을 직접 대조한 결과:

| 함수 | PR #52 (Claude) | PR #61 (dev-ldy03) | 판정 |
|---|---|---|---|
| `_strip_html_tags` ↔ `strip_html_tags` | `re.sub(r"<[^>]+>", "", text)` + 빈 줄 축약 | 동일 본문 (+`or ""` 방어만 추가) | **순수 중복** |
| `_format_for_telegram_html` ↔ `format_for_telegram_html` | escape 후 정규식으로 `**`·`` ` `` 치환 | 코드스팬을 먼저 분리한 뒤 치환 + `_strip_markdown_noise` | **같은 이름·같은 목적·다른 동작** |

### 이 사례가 보여주는 것

- **git 은 이 충돌을 잡지 못했다.** 분기점이 머지 직후라 텍스트 충돌이 성립하지 않았고,
  두 PR 모두 리뷰 없이 몇 분 안에 머지됐다.
- 이슈 #60은 PR #52 머지 **36분 뒤에** 열렸고, 본문은 #52가 이미 (일부) 고친 증상을
  다시 나열한다. PR #61 본문의 `Closes #` 는 빈 플레이스홀더로 남아 있다.
  → 두 소유자가 서로의 작업을 모른 채 같은 문제를 풀었다는 정황.
- v0.3 의 C4 탐지 방법("함수 시그니처 유사도")이 정확히 이 상황을 겨냥한다.
  `strip_html_tags` 는 시그니처·본문이 사실상 동일했다.

**중재기가 있었다면**: 15:36(a41e508)과 16:28(523af81) 두 SHA의 산출물에서 함수
시그니처 유사도로 C4를 탐지하고, 소유자 양쪽에 판정 카드를 보냈을 것이다. 사람이
할 일은 16:38의 사후 발견이 아니라 16:2X 시점의 채택 선택이 된다.

---

## 사례 2 — 검증 없는 머지: 자동 편집이 만든 문법 오류가 dev 에 15분간 존재

**날짜**: 2026-06-04 (KST)

```
01:54  령   ci.yml + requirements-ci.txt 를 dev 에 직접 push (5bef84a, f4a08a4)
01:58  령   둘 다 revert — 커밋 메시지에 "added directly to dev by mistake" 자백
01:58  령   evaluate.py 임계값 수정 커밋 (004cbb3)
            — 이 커밋에서 sed 자동 편집이 문자열 안의 \n 이스케이프 3곳을
              실제 개행으로 치환 → Python 문법 오류 (미종결 문자열)
02:05  령   PR #75 셀프 머지 → 깨진 evaluate.py 가 dev 에 들어감
02:09  령   1곳 복구 (5f74694, 브랜치명 fix/evaluate-syntax-error)
02:10  PR #77 머지 — 그러나 불완전
02:19  령   나머지 2곳(256·272행) 복구 (92afffa)
02:20  PR #78 머지 — 이 시점에야 dev 가 다시 파싱 가능
```

### 이 사례가 보여주는 것

- **import 조차 안 되는 코드가 리뷰·검증 없이 dev 에 머지**됐고, 복구에 PR 3개가
  들었다. `python -m py_compile` 한 번이면 잡혔을 오류다. → FR-12(직접 재현)와
  등급 체계(실행해본 것만 VERIFIED)의 존재 이유.
- 같은 새벽에 "dev 직접 push 실수 → revert" 가 커밋 메시지로 남아 있다.
  → 브랜치 보호 부재가 가설이 아니라 기록된 사건이라는 근거.

---

## 사례 3 — C1 인터페이스 불일치: 19일 뒤 통합 시점에 계약이 깨진 걸 발견

**날짜**: 2026-06-01 작성 → 2026-06-20 통합 (KST)

```
06-01  bbberylll   5-arm 평가 하네스 작성 (#56). 추론부는 predict_placeholder,
                   주석에 "until full RAG/LoRA inference is wired"
06-20  ryeong03+Cursor  실제 RAGPipeline 연결 시도 (910fc03). 그런데:
       ① 하네스가 필요로 하는 인덱스 초기화 메서드가 파이프라인에 없음
          → 제공자 쪽에 RAGPipeline.reset_index() 를 새로 추가해야 붙음
       ② 평가 케이스 ID 와 파일럿 데이터 ID 가 다른 체계
          → source_record_id 메타데이터로 잇는 브리지 함수(pilot_case_for) 필요
       ③ CI 체크런: pytest failure ×2 — evaluate.py 가 pipeline 을 모듈 레벨
          import → CI 환경엔 torch 가 없어서 수집 단계부터 실패
20:29  2분 뒤 lazy import 로 후속 수정 (93f5809)
20:34  PR #81 머지
```

### 이 사례가 보여주는 것

- 서로 다른 소유자가 만든 소비자(평가 하네스)와 제공자(파이프라인)의 계약 불일치가
  **19일 동안 잠복**하다 통합 시점에 세 겹으로 터졌다 (메서드 부재 / ID 체계 불일치 /
  실행 환경 의존성). v0.3 C1 의 교과서 사례(스펙↔호출부)보다 범위가 넓지만 같은
  부류 — 산출물 간 정적 대조로 ①②는 push 시점에 탐지 가능했다.
- CI 실패는 자동 기록이 남는 검증(VERIFIED)이 실제로 문제를 잡은 순간이기도 하다.
  단, 잡힌 시점이 통합일이지 작성일이 아니라는 게 요점이다.

---

## 제안서에 쓸 요약

| 충돌 유형 | 실측 사례 | 핵심 수치 |
|---|---|---|
| C4 중복·상충 구현 | 사례 1 — 동일 함수 2벌, git 충돌 0건 | 에이전트 산출물 작성→폐기 52분 |
| C1 인터페이스 불일치 | 사례 3 — 메서드 부재·ID 체계 불일치 | 잠복 19일, CI 빨간불→수정 2분 |
| 거버넌스 (검증·브랜치) | 사례 2 — 문법 오류 머지, dev 직접 push 자백 | 깨진 코드가 dev 에 15분, 복구 PR 3개 |

한 줄 문구: **"사람 3명 + 에이전트 2종이 커밋한 우리 팀 저장소에서, git 이 잡지 못한
충돌 3건을 커밋 로그로 실측했다. 본 시스템의 충돌 유형 C1·C4 는 이 실측에서 나왔다."**

---

## 부록 — 재현 명령

```bash
git clone https://github.com/Ontology0/Graduation-Project.git && cd Graduation-Project

# 참여 주체
git log --all --format='%an <%ae>' | sort | uniq -c | sort -rn
git log --all --format='%B' | grep -i '^Co-authored-by:' | sort | uniq -c

# 사례 1
git show a41e508 -- src/chatbot/telegram_bot.py     # Claude 의 _strip_html_tags
git show 523af81 --stat                             # -88줄 삭제 후 재구현
git log -1 --format='%p' 523af81                    # 부모 = c6a1c00 (PR#52 머지)
gh pr view 52 -R Ontology0/Graduation-Project
gh issue view 60 -R Ontology0/Graduation-Project

# 사례 2
git show 004cbb3                                    # sed 가 망가뜨린 \n 3곳
git log --oneline 7e7ec11 06dd115 -1 --format='%s'  # "directly to dev by mistake"

# 사례 3
git show 910fc03 -- src/rag/pipeline.py             # 제공자에 reset_index 신설
git show 93f5809 -- src/evaluation/evaluate.py      # lazy import 수정
gh api repos/Ontology0/Graduation-Project/commits/910fc03.../check-runs \
  --jq '.check_runs[] | "\(.name): \(.conclusion)"'  # pytest: failure
```
