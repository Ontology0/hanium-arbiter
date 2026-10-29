"""Export an auditable session without changing simulated values into measurements."""
from __future__ import annotations

import json
from typing import Any


def session_markdown(state: dict[str, Any]) -> str:
    mode = {"demo": "통제 시뮬레이션 — 스크립트 에이전트", "codex": "실제 모델 호출 — Codex CLI",
            "import": "가져온 대화 — 규칙 기반 협업 상태 점검"}[state["mode"]]
    metrics = state.get("metrics", {})
    measured, unmetered = metrics.get("measured_calls", 0), metrics.get("unmetered_calls", 0)
    tokens = str(metrics.get("input_tokens", 0) + metrics.get("output_tokens", 0)) if measured else "미측정"
    if measured and unmetered:
        tokens += " (일부 호출만 측정)"
    lines = [f"# {state['title']} 실행 결과", "", f"실행 유형: {mode}", "",
             "| 항목 | 결과 |", "|---|---|",
             f"| 실행 ID | {state['id']} |", f"| 정책 | {state['policy']} |",
             f"| 상태 | {state['status']} |", f"| 에이전트 발화 수 | {state['turn']} |",
             f"| 입력·출력 토큰 합계 | {tokens} |",
             f"| 사람에게 요청한 횟수 | {metrics.get('human_requests', len(state.get('requests', [])))} |",
             f"| 산출물 검증 성공 | {metrics.get('success') if metrics.get('success') is not None else '미판정'} |", "",
             "## 과제와 판정", "", state.get("task", {}).get("description", ""), "",
             "산출물은 명시된 체크리스트로 검증합니다. 모델의 완료 주장이나 사람의 선택만으로 사실이 검증되지는 않습니다.", "",
             "## 사람의 결정", ""]
    for decision in state.get("decisions", []):
        lines.append(f"- {decision.get('request_id')}: {decision.get('choice')} — {decision.get('note', '')}")
    if not state.get("decisions"):
        lines.append("결정 기록 없음.")
    lines += ["", "## 대화 기록", ""]
    for message in state.get("messages", []):
        lines += [f"### {message.get('turn', '')} {message.get('agent', '')}", "", message.get("content", ""), ""]
    lines += ["## 최종 산출물", "", "```json", json.dumps(state.get("artifact", {}), ensure_ascii=False, indent=2), "```", "",
              "## 해석 범위", "", "단일 실행의 결과입니다. 과제는 구조화된 계약 산출물이며 실제 저장소의 코드를 수정하거나 실행한 결과와 구분합니다.",
              "시뮬레이션의 발화 수는 실제 LLM 토큰이나 사용자 실험의 개입 부담을 대신하지 않습니다.", ""]
    if state["mode"] == "import":
        lines += ["가져온 대화는 명시적인 표현을 규칙으로 점검한 것입니다. 실제 요청의 전달 여부와 외부 작업 완료는 미판정입니다.",
                  "결정은 로컬에 기록되며, 연결된 에이전트가 결정 조회 API에서 읽기 전에는 외부로 전달되지 않습니다.", ""]
    return "\n".join(lines)
