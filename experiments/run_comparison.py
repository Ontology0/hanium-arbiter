"""Run an auditable, deterministic control-flow comparison without model calls.

Run from the project root:
    PYTHONPATH=backend python experiments/run_comparison.py --output experiments/results/latest
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import traceback
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from arbiter.domain import (
    apply_decision,
    create_state,
    evaluate_state,
    ingest_event,
    next_demo_event,
    scenario_catalog,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICIES = ("capped", "periodic", "adaptive")
POLICY_LABELS = {
    "capped": "고정 턴 상한",
    "periodic": "주기적 HITL",
    "adaptive": "온톨로지 기반 적응형 HITL",
}
EXPERIMENT_VERSION = "1.0"
CSV_FIELDS = (
    "scenario_id", "scenario_title", "category", "policy", "status", "success",
    "turns", "human_requests", "human_answers", "progress_events", "passed_checks",
    "total_checks", "input_tokens", "output_tokens", "measured_calls", "unmetered_calls",
    "max_turns", "periodic_every", "stall_window", "error", "session_file",
)


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), *args],
            check=True, capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def provenance() -> dict[str, Any]:
    """Hash the actual working source, even if HEAD does not contain these edits."""
    sources = [PROJECT_ROOT / "backend" / "arbiter" / name for name in ("__init__.py", "domain.py", "scenarios.py")]
    sources.append(Path(__file__).resolve())
    hashes = {
        str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sources
    }
    status = _git("status", "--porcelain")
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "git": {
            "branch": _git("branch", "--show-current"),
            "revision": _git("rev-parse", "HEAD"),
            "dirty": bool(status) if status is not None else None,
            "status": status,
        },
        "source_sha256": hashes,
        "source_hash_scope": "evaluation script and imported local domain/fixture modules",
    }


def choose_scripted_answer(state: dict[str, Any], request: dict[str, Any]) -> str:
    """Use the same explicit oracle policy in each arm; never use policy identity."""
    option_ids = {option["id"] for option in request["options"]}
    expected = state["task"].get("oracle_choice")
    if expected in option_ids:
        return expected
    if "continue" in option_ids:
        return "continue"
    raise ValueError("Card has neither the fixture oracle choice nor a continue option")


def run_session(
    scenario: dict[str, Any],
    policy: str,
    parameters: dict[str, int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Retain failures and the exact event/decision inputs for every assigned run."""
    state: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    evaluation: dict[str, Any] = {}
    error: str | None = None
    error_traceback: str | None = None
    answers = 0
    try:
        state = create_state(scenario["id"], policy=policy, mode="demo", **parameters)
        # A controller bug must produce a recorded failed run, not hang the whole batch.
        action_budget = parameters["max_turns"] * 10 + 20
        while state["status"] in {"running", "waiting"}:
            if len(trace) >= action_budget:
                raise RuntimeError("Controller action guard exceeded; batch retained this failure")
            if state["status"] == "waiting":
                pending = [request for request in state["requests"] if request["status"] == "pending"]
                if not pending:
                    raise RuntimeError("State is waiting but has no pending request")
                request = pending[0]
                choice = choose_scripted_answer(state, request)
                trace.append({
                    "kind": "scripted_human_answer", "turn_before": state["turn"],
                    "request_id": request["id"], "choice": choice,
                    "answer_policy": "fixture_oracle_if_offered_else_continue",
                })
                apply_decision(
                    state, request["id"], choice,
                    note="통제 시뮬레이션의 자동 응답: 실제 사용자 참여 아님",
                )
                answers += 1
            else:
                event = next_demo_event(state)
                if not isinstance(event, dict):
                    raise RuntimeError("Running scenario did not yield an event dictionary")
                trace.append({"kind": "agent_event", "turn_before": state["turn"], "event": deepcopy(event)})
                ingest_event(state, event)
        evaluation = evaluate_state(state)
    except Exception as exc:  # Record one failure and continue the assigned comparison.
        error = f"{type(exc).__name__}: {exc}"
        error_traceback = traceback.format_exc()

    metrics = state.get("metrics", {})
    status = "error" if error else state.get("status", "error")
    row = {
        "scenario_id": scenario["id"],
        "scenario_title": scenario.get("title", scenario["id"]),
        "category": scenario.get("category", "unspecified"),
        "policy": policy,
        "status": status,
        "success": None if error or evaluation.get("success") is None else bool(evaluation["success"]),
        "turns": state.get("turn", 0),
        "human_requests": metrics.get("human_requests", len(state.get("requests", []))),
        "human_answers": answers,
        "progress_events": metrics.get("progress_events", 0),
        "passed_checks": evaluation.get("passed", 0),
        "total_checks": evaluation.get("total", 0),
        # Scripted demo events have no measured provider usage. Do not turn missing
        # telemetry into zero-token claims, even if the core accumulator starts at 0.
        "input_tokens": None,
        "output_tokens": None,
        "measured_calls": metrics.get("measured_calls", 0),
        "unmetered_calls": metrics.get("unmetered_calls", 0),
        **parameters,
        "error": error,
        "session_file": f"sessions/{scenario['id']}__{policy}.json",
    }
    session = {
        "study_type": "통제 시뮬레이션",
        "scenario": scenario,
        "policy": policy,
        "parameters": parameters,
        "answer_policy": "fixture_oracle_if_offered_else_continue",
        "result": row,
        "trace": trace,
        "evaluation": evaluation,
        "final_state": state,
        "error_traceback": error_traceback,
    }
    return row, session


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for policy in POLICIES:
        policy_rows = [row for row in rows if row["policy"] == policy]
        successful = [row for row in policy_rows if row["success"] is True]
        failed = [row for row in policy_rows if row["success"] is False]
        unknown = [row for row in policy_rows if row["success"] is None]
        summaries[policy] = {
            "runs": len(policy_rows),
            "successes": len(successful),
            "failures": len(failed),
            "unknown_outcomes": len(unknown),
            "success_rate": len(successful) / len(policy_rows) if policy_rows else None,
            "total_turns": sum(row["turns"] for row in policy_rows),
            "mean_turns_all_runs": mean(row["turns"] for row in policy_rows) if policy_rows else None,
            "mean_turns_successful_runs": mean(row["turns"] for row in successful) if successful else None,
            "total_human_requests": sum(row["human_requests"] for row in policy_rows),
            "mean_human_requests": mean(row["human_requests"] for row in policy_rows) if policy_rows else None,
            "total_human_answers": sum(row["human_answers"] for row in policy_rows),
            "total_progress_events": sum(row["progress_events"] for row in policy_rows),
            "status_counts": dict(sorted(Counter(row["status"] for row in policy_rows).items())),
            "input_tokens": None,
            "output_tokens": None,
        }
    return summaries


def _markdown(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _number(value: Any) -> str:
    return "해당 없음" if value is None else f"{value:.2f}"


def render_report(summary: dict[str, Any]) -> str:
    parameters = summary["parameters"]
    metadata = summary["provenance"]
    lines = [
        "# 온톨로지 기반 HITL 정책 비교 — 통제 시뮬레이션",
        "",
        f"> 실행 시각(UTC): {metadata['created_at_utc']} · {summary['scenario_count']}개 시나리오 × 3개 정책 · 정책·시나리오 조합별 1회",
        "",
        "## 실험 범위와 질문",
        "",
        "사람을 대리하는 개인 에이전트 사이에서 인계 확인이 끝나지 않거나 결정 담당자가 없어 협업이 멈추는 상황을 중심으로, "
        "개입 시점을 달리하면 정해진 작업 조건을 충족하는지와 대화 이벤트·개입 요청 수가 어떻게 달라지는지 확인한다. "
        "사실·요구사항 충돌도 별도 사례로 포함한다. "
        "실제 실행한 백엔드 정책과 로컬 체크리스트 검증기의 결과를 집계했다.",
        "",
        "**본 결과는 스크립트 에이전트와 자동 사용자 응답을 사용한 통제 시뮬레이션이다. 실제 LLM 실험이나 사람 대상 사용자 연구가 아니다.** "
        "실제 API 호출·토큰 비용·응답 지연·사용자 판단 시간은 측정하지 않았다.",
        "성공은 각 사례의 산출물 JSON이 로컬 체크리스트를 충족했다는 뜻이다. 외부 메시지 전달이나 실제 구현 코드의 동작을 검증한 결과가 아니다.",
        "",
        "## 비교 조건",
        "",
        "| 항목 | 고정 조건 |",
        "|---|---|",
        f"| 누적 대화 상한 | 모든 정책 최대 {parameters['max_turns']}개 에이전트 이벤트 |",
        f"| 주기적 질문 간격 | {parameters['periodic_every']}턴 |",
        f"| 적응형 정체 창 | {parameters['stall_window']}턴 |",
        "| 실행 모드 | demo — 외부 모델·API 키 불필요 |",
        "| 사용자 응답 정책 | 모든 정책에서 동일: 요청 카드에 시나리오의 oracle_choice가 있으면 선택하고, 없으면 continue 선택 |",
        "| 성공 판정 | 코어의 evaluate_state가 로컬 작업 체크리스트 충족 여부를 판정 |",
        "| 표본 구성 | 내장 시나리오 전체를 각 정책에서 한 번씩 실행; 오류·미판정·상한 초과도 분모에 포함 |",
        "| 턴 정의 | ingest_event로 처리한 에이전트 이벤트 수; 사용자 답변은 별도로 집계 |",
        "",
        "고정 턴 상한 정책은 질문 없이 상한까지 진행한다. 주기적 정책은 정해진 간격으로 질문한다. "
        "적응형 정책은 온톨로지의 위임·대기 관계·주장·근거·충돌·진행 상태와 정체 규칙에 따라 개입 요청을 만든다. "
        "정책별로 다른 입력 문장을 따로 꾸미지 않고 동일한 시나리오 생성기를 사용하며, 결정 후 대화 분기는 선택된 결정에 따른다.",
        "",
        "## 실행 결과",
        "",
        "| 정책 | 성공/전체 | 미판정 | 확인 성공률 | 평균 턴(전체) | 평균 턴(성공만) | 개입 요청 합계 | 평균 개입 요청 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for policy in POLICIES:
        metrics = summary["policies"][policy]
        rate = metrics["success_rate"]
        rate_label = "해당 없음" if rate is None else f"{rate:.1%}"
        lines.append(
            f"| {POLICY_LABELS[policy]} | {metrics['successes']}/{metrics['runs']} | {metrics['unknown_outcomes']} | {rate_label} | "
            f"{_number(metrics['mean_turns_all_runs'])} | {_number(metrics['mean_turns_successful_runs'])} | "
            f"{metrics['total_human_requests']} | {_number(metrics['mean_human_requests'])} |"
        )
    periodic = summary["policies"]["periodic"]
    adaptive = summary["policies"]["adaptive"]
    lines += [
        "",
        f"주기적·적응형 정책의 확인 성공은 각각 {periodic['successes']}건·{adaptive['successes']}건이고, "
        f"전체 턴 합계는 {periodic['total_turns']}턴·{adaptive['total_turns']}턴이다. "
        f"개입 요청 합계는 {periodic['total_human_requests']}건·{adaptive['total_human_requests']}건이다.",
    ]
    if periodic["total_turns"] == adaptive["total_turns"]:
        lines.append("이 실행에서 적응형 정책의 전체 대화 턴 수는 주기적 정책과 같았다.")
    periodic_by_case = {row["scenario_id"]: row for row in summary["runs"] if row["policy"] == "periodic"}
    request_differences = []
    for row in summary["runs"]:
        if row["policy"] == "adaptive":
            baseline = periodic_by_case[row["scenario_id"]]
            if row["human_requests"] != baseline["human_requests"]:
                request_differences.append(
                    f"{_markdown(row['scenario_title'])}(주기적 {baseline['human_requests']}건, 적응형 {row['human_requests']}건)"
                )
    if request_differences:
        lines.append("개입 요청 수가 달랐던 사례는 " + ", ".join(request_differences) + "이다.")
    lines += [
        "",
        "확인 성공률은 전체 배정 실행 중 성공이 확인된 비율이다. 미판정은 분모에 남기되 실패 판정과 별도로 센다. "
        "평균 턴(전체)은 실패·미판정 실행도 포함한다. 성공만의 평균은 정책별로 성공한 시나리오 집합이 달라질 수 있으므로 직접적인 효율 우열로 해석하지 않는다. "
        "개입 요청 수는 사람이 실제로 수행한 노동량이 아니라 시스템이 생성한 요청 수이다.",
        "",
        "### 시나리오별 원시 집계",
        "",
        "| 시나리오 | 분류 | 정책 | 종료 상태 | 성공 | 턴 | 개입 요청 | 자동 답변 | 검증 조건 |",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["runs"]:
        lines.append(
            f"| {_markdown(row['scenario_title'])} | {_markdown(row['category'])} | {row['policy']} | "
            f"{row['status']} | {'미판정' if row['success'] is None else '예' if row['success'] else '아니오'} | {row['turns']} | {row['human_requests']} | "
            f"{row['human_answers']} | {row['passed_checks']}/{row['total_checks']} |"
        )
    errors = [row for row in summary["runs"] if row["error"]]
    if errors:
        lines += ["", "### 실행 오류", ""]
        for row in errors:
            lines.append(f"- `{row['scenario_id']}/{row['policy']}`: {_markdown(row['error'])}")
    else:
        lines += ["", "실행 예외는 없었다. 상한 소진 등 작업 미완료는 위 표의 실패로 유지했다."]
    lines += [
        "",
        "## 해석 범위와 한계",
        "",
        "- 내장 시나리오는 개발자가 작성한 소규모 기능 검증용 사례이다. 외부 벤치마크나 무작위로 수집한 실제 협업 대화를 대표하지 않는다.",
        "- 일부 스크립트는 특정 사용자 결정 이후 후속 산출물을 내도록 설계되어 있다. 성공률 차이는 이 조건에서의 제어 흐름을 보여주며 실제 에이전트 협업에서의 성능 우월성을 입증하지 않는다.",
        "- 사용자 응답기는 시나리오의 의도된 선택을 아는 oracle이다. 잘못된 선택, 응답 지연, 무응답과 사람의 부담은 이번 비교에 포함하지 않았다.",
        "- 에이전트 이벤트에 구조화된 주장·근거가 제공된다. 자연어에서 온톨로지 항목을 정확하게 추출하는 능력은 별도 평가가 필요하다.",
        "- 실제 대화의 단일 교환만으로 무한 대화를 확정할 수 없다. 미확인 인계와 확인된 실패를 구분해야 하며, 이번 실험은 의도적으로 작성한 교착 사례를 사용한다.",
        "- 개입 요청 생성은 로컬 상태 변경이다. 개인 에이전트나 Slack의 실제 사용자에게 메시지를 전달했다고 해석하지 않는다.",
        "- 각 결정적 사례는 한 번씩 실행했다. 반복 실행을 독립 표본으로 세지 않으며 유의확률·신뢰구간을 제시하지 않는다.",
        "- 토큰 사용량은 미측정(null)이다. 대화 이벤트 감소를 토큰 비용 절감률로 바꾸어 주장하지 않는다.",
        "- 개입의 적절성에 대한 독립 사람 라벨이 없어 불필요한 개입률·감지 정밀도·재현율은 산출하지 않았다.",
        "",
        "## 재현과 결과 파일",
        "",
        "프로젝트 루트에서 다음 명령을 실행한다.",
        "",
        "```bash",
        "PYTHONPATH=backend python experiments/run_comparison.py "
        f"--output experiments/results/latest --max-turns {parameters['max_turns']} "
        f"--periodic-every {parameters['periodic_every']} --stall-window {parameters['stall_window']}",
        "```",
        "",
        "- [runs.csv](runs.csv): 실패를 포함한 시나리오·정책별 지표. 토큰 칸의 빈 값은 0이 아니라 미측정이다.",
        "- [summary.json](summary.json): 실행 환경·설정·집계·소스 SHA-256과 세션 파일 목록.",
        "- `sessions/*.json`: 실제 주입 이벤트, 자동 답변, 최종 상태, 개별 검증 결과와 오류 traceback.",
        "",
        f"기록한 Git 브랜치: `{metadata['git']['branch']}` · revision: `{metadata['git']['revision']}` · "
        f"작업 트리 변경 있음: `{metadata['git']['dirty']}`. 변경 상태에서는 revision만으로 구현을 식별할 수 없으므로 "
        "`summary.json`의 실제 소스 해시를 함께 확인한다.",
        "같은 소스와 설정에서 결과 지표는 재현되지만 실행 시각과 세션 식별자는 실행마다 달라진다.",
        "",
        "다음 검증 단계는 실제 모델 대화, 사전에 분리한 평가 사례, 독립적인 개입 필요성 라벨, 실제 사용자 응답을 추가하여 "
        "작업 성공률·전체 토큰·사용자 소요 시간을 함께 측정하는 것이다.",
        "",
    ]
    return "\n".join(lines)


def run_comparison(output: Path, *, max_turns: int = 18, periodic_every: int = 4, stall_window: int = 3) -> dict[str, Any]:
    parameters = {"max_turns": max_turns, "periodic_every": periodic_every, "stall_window": stall_window}
    if any(type(value) is not int or value <= 0 for value in parameters.values()):
        raise ValueError("All comparison parameters must be positive integers")
    scenarios = scenario_catalog()
    if not scenarios:
        raise ValueError("Scenario catalog is empty; no comparison can be reported")
    output = Path(output)
    (output / "sessions").mkdir(parents=True, exist_ok=True)
    metadata = provenance()
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        for policy in POLICIES:
            row, session = run_session(scenario, policy, parameters)
            rows.append(row)
            _write_json(output / row["session_file"], session)
    summary = {
        "study_type": "통제 시뮬레이션",
        "provenance": metadata,
        "parameters": parameters,
        "scenario_count": len(scenarios),
        "scenario_ids": [scenario["id"] for scenario in scenarios],
        "runs_per_scenario_policy": 1,
        "assigned_run_count": len(scenarios) * len(POLICIES),
        "design": {
            "agent_source": "deterministic_scripted_fixture",
            "human_response_source": "automated_fixture_oracle",
            "real_model_calls": False,
            "real_human_participants": False,
            "scenario_selection": "entire_builtin_catalog",
            "statistical_inference": "none; deterministic cases are not independent repeated samples",
            "success_scope": "local JSON artifact checklist only",
        },
        "answer_policy": "fixture_oracle_if_offered_else_continue",
        "usage": {"source": "unavailable", "input_tokens": None, "output_tokens": None},
        "policies": summarize(rows),
        "runs": rows,
    }
    with (output / "runs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    _write_json(output / "summary.json", summary)
    (output / "report.md").write_text(render_report(summary), encoding="utf-8")
    return summary


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("experiments/results/latest"))
    parser.add_argument("--max-turns", type=_positive_int, default=18)
    parser.add_argument("--periodic-every", type=_positive_int, default=4)
    parser.add_argument("--stall-window", type=_positive_int, default=3)
    args = parser.parse_args()
    summary = run_comparison(
        args.output, max_turns=args.max_turns,
        periodic_every=args.periodic_every, stall_window=args.stall_window,
    )
    print(f"통제 시뮬레이션: {summary['assigned_run_count']}개 실행, 결과: {args.output.resolve()}")
    for policy in POLICIES:
        result = summary["policies"][policy]
        print(
            f"{policy}: success={result['successes']}/{result['runs']}, unknown={result['unknown_outcomes']}, "
            f"mean_turns={result['mean_turns_all_runs']:.2f}, "
            f"human_requests={result['total_human_requests']}"
        )
    errors = sum(row["status"] == "error" for row in summary["runs"])
    if errors:
        print(f"{errors}개 실행 오류도 결과에 포함했습니다.", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
