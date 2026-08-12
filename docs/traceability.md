# 추적 매핑표 — 요구사항 ↔ 화면 ↔ ERD

> 이 파일은 `tools/gen_traceability.py` 가 생성한다. **손으로 고치지 마라.**
> 원본: `docs/goal.md` (요구사항·엔티티 열) + `docs/design/v0.3.md` (화면·ERD).
> 고치려면 원본을 고치고 다시 생성하라.

## 1. 요구사항별 매핑

| ID | 요구사항 | 우선순위 | 화면 | 엔티티 |
|---|---|---|---|---|
| UR-01 | 사용자는 만들고 싶은 앱을 자연어로 입력할 수 있다 | must | S3 새 프로젝트 | `project` |
| UR-02 | 사용자는 시스템이 도출한 요구사항을 확인·수정·승인할 수 있다. 승인본이 이후 모든 판정의 기준점이 된다 | must | S4 요구사항 확인 | `requirement` |
| UR-03 | 사용자는 자기 에이전트를 등록할 수 있다 (소유자·전송 경로·git 권한·브랜치 규칙) | must | S5 에이전트 등록 | `agent`, `user` |
| UR-04 | 사용자는 태스크 배정 제안을 수락하거나 거절할 수 있다 | must | S6 진행 모니터 | `role_assignment` |
| UR-05 | 사용자는 충돌 상세에서 후보별 근거를 좌우 비교로 볼 수 있다. 근거마다 등급 배지가 노출된다 | must | S7 충돌 상세 | `conflict`, `conflict_candidate`, `evidence` |
| UR-06 | 사용자는 에스컬레이션된 건에 대해 선택지를 고르거나 직접 지시를 입력할 수 있다 | must | S8 사람 결정 | `escalation` |
| UR-07 | 사용자는 충돌→근거→판정→결과 타임라인을 조회할 수 있다 | must | S9 결정 이력 | `conflict`, `arbitration` |
| UR-08 | 사용자는 생성 결과를 샌드박스에서 빌드·프리뷰할 수 있다 | should | S10 프리뷰 | **없음** |
| UR-09 | 사용자는 판정·에스컬레이션 결과를 사람 채널 알림 카드로 받는다 | must | S8 사람 결정 | `notification` |
| UR-10 | 사용자는 프로젝트를 생성·조회·전환할 수 있다 | must | S2 프로젝트 목록 | `project` |
| UR-11 | 연구자는 전략별 실험 지표를 대시보드에서 비교할 수 있다 | later | S11 실험 대시보드 | `experiment_run` |
| FR-01 | 시스템은 자연어 요청을 요구사항 목록과 태스크로 분해한다 | must | — (백엔드) | `requirement`, `task` |
| FR-02 | 시스템은 승인된 요구사항을 판정 기준점으로 고정 보관한다 | must | — (백엔드) | `requirement` |
| FR-03 | 시스템은 태스크별 배정 제안을 생성하고 수락·거절을 수집한다 | must | — (백엔드) | `role_assignment` |
| FR-04 | 시스템은 중복 수락과 미배정을 충돌(C0)로 처리한다 | must | — (백엔드) | `role_assignment`, `conflict` |
| FR-05 | 시스템은 `POST /reports`로 에이전트의 작업 보고를 수신한다 (경로 A) | must | — (백엔드) | `report` |
| FR-06 | 시스템은 브랜치 push를 감지해 산출물을 수집한다 (경로 B) | must | — (백엔드) | `report`, `commit_ref` |
| FR-07 | 시스템은 경로 A/B 보고를 동일 스키마로 정규화한다 | must | — (백엔드) | `report` |
| FR-08 | 시스템은 보고에 포함된 commit SHA의 실재 여부를 검증한다 | must | — (백엔드) | `commit_ref` |
| FR-09 | 시스템은 해당 SHA를 체크아웃해 산출물을 추출한다 (API 스펙·DB 스키마·호출부) | must | — (백엔드) | `commit_ref`, `artifact` |
| FR-10 | 시스템은 C0~C4 충돌을 자동 탐지한다 | must | — (백엔드) | `conflict`, `conflict_candidate` |
| FR-11 | 시스템은 각 후보의 근거를 CLAIMED / REFERENCED / VERIFIED로 등급화한다 | must | — (백엔드) | `evidence` |
| FR-12 | 시스템은 REFERENCED 근거를 직접 재현(테스트 실행·스캔·diff)해 VERIFIED로 승격한다 | must | — (백엔드) | `evidence`, `verification_run` |
| FR-13 | 시스템은 재현 실행의 입력·출력·종료코드를 증거로 저장한다 | must | — (백엔드) | `verification_run` |
| FR-14 | 시스템은 근거를 정렬해 채택안·이유·확신도를 판정한다 | must | — (백엔드) | `arbitration` |
| FR-15 | 시스템은 근거가 부족한 후보에게 검증 요청을 보내고 타임아웃을 관리한다 | must | — (백엔드) | `request_ticket` |
| FR-16 | 시스템은 채택 후 상충하는 쪽 소유자 에이전트에게 수정 요청을 발행한다. 코드를 직접 수정하지 않는다 | must | — (백엔드) | `request_ticket` |
| FR-17 | 시스템은 중재 전략을 교체 가능한 형태로 구현한다 (동일 충돌을 전략만 바꿔 재실행 가능) | must | — (백엔드) | `arbitration` |
| FR-18 | 시스템은 판정 불가·고위험 건을 선택지로 만들어 사람에게 넘긴다 | must | — (백엔드) | `escalation` |
| FR-19 | 시스템은 사람의 응답을 수집해 판정에 반영한다 | must | — (백엔드) | `escalation`, `arbitration` |
| FR-20 | 시스템은 판정·에스컬레이션 결과를 사람 채널로 발송한다 | must | — (백엔드) | `notification` |
| FR-21 | 시스템은 충돌→근거→판정→결과를 타임라인으로 조회 가능하게 한다 | must | — (백엔드) | `conflict`, `evidence`, `arbitration` |
| FR-22 | 시스템은 격리 샌드박스에서 결과물을 빌드하고 프리뷰 URL을 제공한다 | should | — (백엔드) | **없음** |
| FR-23 | 시스템은 합성 충돌을 주입하고 전략별로 반복 실행해 지표를 집계한다 | later | — (백엔드) | `experiment_run` |
| FR-24 | 시스템은 에이전트×충돌유형 적중률을 누적한다 | later | — (백엔드) | `agent_reliability` |
| FR-25 | 시스템은 계정 인증과 프로젝트 CRUD를 제공한다 | must | S1 로그인 | `user`, `project` |

## 2. 화면별 요구사항 (역방향)

| 화면 | 요구사항 |
|---|---|
| S1 로그인 | FR-25 |
| S2 프로젝트 목록 | UR-10 |
| S3 새 프로젝트 | UR-01 |
| S4 요구사항 확인 | UR-02 |
| S5 에이전트 등록 | UR-03 |
| S6 진행 모니터 | UR-04 |
| S7 충돌 상세 | UR-05 |
| S8 사람 결정 | UR-06, UR-09 |
| S9 결정 이력 | UR-07 |
| S10 프리뷰 | UR-08 |
| S11 실험 대시보드 | UR-11 |

## 3. 엔티티별 요구사항 (역방향)

| 엔티티 | 요구사항 |
|---|---|
| `user` | UR-03, FR-25 |
| `agent` | UR-03 |
| `project` | UR-01, UR-10, FR-25 |
| `requirement` | UR-02, FR-01, FR-02 |
| `task` | FR-01 |
| `role_assignment` | UR-04, FR-03, FR-04 |
| `report` | FR-05, FR-06, FR-07 |
| `commit_ref` | FR-06, FR-08, FR-09 |
| `artifact` | FR-09 |
| `conflict` | UR-05, UR-07, FR-04, FR-10, FR-21 |
| `conflict_candidate` | UR-05, FR-10 |
| `evidence` | UR-05, FR-11, FR-12, FR-21 |
| `verification_run` | FR-12, FR-13 |
| `arbitration` | UR-07, FR-14, FR-17, FR-19, FR-21 |
| `request_ticket` | FR-15, FR-16 |
| `escalation` | UR-06, FR-18, FR-19 |
| `notification` | UR-09, FR-20 |
| `agent_reliability` | FR-24 |
| `experiment_run` | UR-11, FR-23 |

## 4. 공백

- 대응 엔티티 없는 요구사항: UR-08, FR-22

