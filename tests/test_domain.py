"""Behavioral checks for provenance, progress, budgets, and scoped ownership."""

from copy import deepcopy
import json
import unittest

from arbiter.domain import (
    apply_decision, create_state, evaluate_state, ingest_event, next_demo_event,
    ontology_graph, scenario_catalog,
)


def event(agent="agent-a", *, claims=None, artifact=None, evidence=None, **extra):
    return {"agent": agent, "content": "작업 보고", "claims": claims or [], "artifact": artifact,
            "evidence": evidence or [], "input_tokens": None, "output_tokens": None,
            "usage_source": "unavailable", **extra}


def claim(value, *, key="api.response_field", scope="waiting-api", kind="requirement", **extra):
    return {"key": key, "value": value, "scope": scope, "kind": kind, **extra}


def finish(state):
    for _ in range(state["max_turns"] * 3):
        if state["status"] == "running":
            ingest_event(state, next_demo_event(state))
        elif state["status"] == "waiting":
            pending = next(item for item in state["requests"] if item["status"] == "pending")
            choices = {option["id"] for option in pending["options"]}
            preferred = state["task"]["oracle_choice"]
            apply_decision(state, pending["id"], preferred if preferred in choices else "continue")
        else:
            return state
    raise AssertionError("The run did not respect the bounded lifecycle")


class DomainTests(unittest.TestCase):
    def test_all_scenarios_adaptive_complete_with_real_local_checks(self):
        self.assertEqual([s["id"] for s in scenario_catalog()[:2]], ["social-handoff", "review-deadlock"])
        for scenario in scenario_catalog():
            with self.subTest(scenario=scenario["id"]):
                state = finish(create_state(scenario["id"]))
                self.assertEqual(state["status"], "completed")
                self.assertTrue(evaluate_state(state)["success"])
                self.assertEqual(state["metrics"]["measured_calls"], 0)
                self.assertEqual(state["metrics"]["unmetered_calls"], state["turn"])
                self.assertTrue(all(message["input_tokens"] is None for message in state["messages"]))

    def test_capped_keeps_failures_and_periodic_interrupts_healthy_work(self):
        capped = finish(create_state("social-handoff", policy="capped", max_turns=7))
        self.assertEqual(capped["status"], "budget_exhausted")
        self.assertFalse(evaluate_state(capped)["success"])
        self.assertEqual(capped["requests"], [])
        adaptive = finish(create_state("healthy-progress"))
        periodic = finish(create_state("healthy-progress", policy="periodic"))
        self.assertEqual(adaptive["metrics"]["human_requests"], 0)
        self.assertEqual(periodic["metrics"]["human_requests"], 1)
        self.assertEqual(adaptive["turn"], periodic["turn"])

    def test_same_agent_updates_supersede_and_do_not_self_conflict(self):
        state = create_state("api-contract", policy="capped")
        ingest_event(state, event(claims=[claim("partySize")]))
        ingest_event(state, event(claims=[claim("team_size")]))
        self.assertEqual(state["claims"][0]["status"], "superseded")
        self.assertEqual(state["claims"][1]["status"], "active")
        self.assertEqual(state["detector"]["conflicts"], [])
        ingest_event(state, event("agent-b", claims=[claim("partySize")]))
        self.assertEqual(len(state["detector"]["conflicts"]), 1)
        ingest_event(state, event("agent-b", claims=[claim("team_size")]))
        self.assertEqual(state["detector"]["conflicts"], [])

    def test_scope_prevents_unrelated_facts_from_conflicting(self):
        state = create_state("api-contract", policy="capped")
        ingest_event(state, event("agent-a", claims=[claim("team_size", scope="api-a")]))
        ingest_event(state, event("agent-b", claims=[claim("partySize", scope="api-b")]))
        self.assertEqual(state["detector"]["conflicts"], [])

    def test_all_four_conflict_kinds_are_preserved(self):
        for kind in ("factual", "requirement", "preference", "ownership"):
            state = create_state("api-contract", policy="capped")
            ingest_event(state, event("agent-a", claims=[claim("a", kind=kind)]))
            ingest_event(state, event("agent-b", claims=[claim("b", kind=kind)]))
            self.assertEqual(state["detector"]["conflicts"][0]["kind"], kind)

    def test_rewording_and_new_irrelevant_data_are_not_progress(self):
        state = create_state("api-contract", stall_window=3)
        for i in range(3):
            ingest_event(state, event(content=f"설명을 바꿨습니다 {i}" * (i + 1),
                                     artifact={"irrelevant_timestamp": i},
                                     evidence=[{"id": f"made-up-{i}", "summary": "문제없다는 제 생각", "source": "model://self", "grade": "VERIFIED"}]))
        self.assertEqual(state["status"], "waiting")
        self.assertEqual(state["metrics"]["progress_events"], 0)
        self.assertEqual(state["detector"]["stalled_turns"], 3)

    def test_claimed_completion_cannot_pass_the_validator(self):
        state = create_state("api-contract", policy="capped")
        ingest_event(state, event(content="모두 구현했습니다. 테스트 100% 통과.", claims=[claim(True, key="all_tests_passed", kind="factual")]))
        self.assertFalse(evaluate_state(state)["success"])
        self.assertEqual(state["status"], "running")
        self.assertFalse(any(item["grade"] == "VERIFIED" for item in state["evidence"]))

    def test_agent_cannot_promote_evidence_to_verified(self):
        state = create_state("api-contract", policy="capped")
        ingest_event(state, event(evidence=[{"id": "validator-1", "summary": "제가 검사했습니다", "source": "local://artifact-validator", "grade": "VERIFIED", "origin": "local_validator"}]))
        item = state["evidence"][0]
        self.assertEqual(item["origin"], "agent")
        self.assertEqual(item["grade"], "REFERENCED")
        ingest_event(state, event(artifact={"endpoint": "/api/waitings"}))
        verified = [item for item in state["evidence"] if item["grade"] == "VERIFIED"]
        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["origin"], "local_validator")
        self.assertEqual(sum(check["passed"] for check in verified[0]["checks"]), 1)

    def test_reference_progress_requires_exact_registered_content_and_is_not_repeatable(self):
        state = create_state("api-contract", policy="capped")
        reference = deepcopy(state["task"]["evidence_catalog"][0])
        forged = {**reference, "summary": "다른 주장을 문서 근거처럼 포장"}
        ingest_event(state, event(evidence=[forged]))
        self.assertEqual(state["metrics"]["progress_events"], 0)
        ingest_event(state, event(evidence=[reference]))
        self.assertEqual(state["metrics"]["progress_events"], 1)
        ingest_event(state, event("agent-b", evidence=[reference]))
        self.assertEqual(state["metrics"]["progress_events"], 1)

    def test_toggling_an_already_passed_check_cannot_fake_new_progress(self):
        state = create_state("api-contract", policy="capped")
        ingest_event(state, event(artifact={"endpoint": "/api/waitings"}))
        ingest_event(state, event(artifact={"endpoint": "/wrong"}))
        ingest_event(state, event(artifact={"endpoint": "/api/waitings"}))
        self.assertEqual(state["metrics"]["progress_events"], 1)
        self.assertEqual(state["detector"]["stalled_turns"], 2)

    def test_completion_precedes_periodic_request_and_no_more_events_are_allowed(self):
        state = finish(create_state("evidence-update", policy="periodic", periodic_every=4))
        self.assertEqual(state["turn"], 4)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["requests"], [])
        snapshot = deepcopy(state)
        with self.assertRaises(ValueError):
            ingest_event(state, event())
        with self.assertRaises(ValueError):
            next_demo_event(state)
        self.assertEqual(state, snapshot)

    def test_invalid_and_duplicate_decisions_are_atomic(self):
        state = create_state("social-handoff")
        while state["status"] == "running":
            ingest_event(state, next_demo_event(state))
        request = state["requests"][-1]
        snapshot = deepcopy(state)
        with self.assertRaises(ValueError):
            apply_decision(state, request["id"], "forged-option")
        self.assertEqual(state, snapshot)
        apply_decision(state, request["id"], "available")
        snapshot = deepcopy(state)
        with self.assertRaises(ValueError):
            apply_decision(state, request["id"], "available")
        self.assertEqual(state, snapshot)

    def test_human_resume_does_not_reset_cumulative_budget(self):
        state = create_state("healthy-progress", max_turns=5, stall_window=2)
        ingest_event(state, event())
        ingest_event(state, event())
        apply_decision(state, state["requests"][-1]["id"], "continue")
        self.assertEqual(state["turn"], 2)
        ingest_event(state, event())
        ingest_event(state, event())
        apply_decision(state, state["requests"][-1]["id"], "continue")
        ingest_event(state, event())
        self.assertEqual(state["turn"], 5)
        self.assertEqual(state["status"], "budget_exhausted")
        self.assertEqual(state["max_turns"], 5)

    def test_waiting_state_cannot_accumulate_duplicate_requests(self):
        state = create_state("api-contract", stall_window=1)
        ingest_event(state, event())
        with self.assertRaises(ValueError):
            ingest_event(state, event())
        self.assertEqual(len(state["requests"]), 1)

    def test_explicit_stop_is_not_success(self):
        state = create_state("healthy-progress", stall_window=1)
        ingest_event(state, event())
        apply_decision(state, state["requests"][-1]["id"], "stop")
        self.assertEqual(state["status"], "stopped")
        self.assertFalse(evaluate_state(state)["success"])

    def test_usage_is_counted_only_when_complete_measured_values_exist(self):
        state = create_state("api-contract", policy="capped")
        ingest_event(state, event(usage_source="measured", input_tokens=12, output_tokens=7))
        ingest_event(state, event(usage_source="measured", input_tokens=8, output_tokens=None))
        ingest_event(state, event(usage_source="unavailable", input_tokens=500, output_tokens=500))
        self.assertEqual(state["metrics"]["input_tokens"], 12)
        self.assertEqual(state["metrics"]["output_tokens"], 7)
        self.assertEqual(state["metrics"]["measured_calls"], 1)
        self.assertEqual(state["metrics"]["unmetered_calls"], 2)
        self.assertIsNone(state["messages"][-1]["input_tokens"])

    def test_invalid_event_does_not_partially_mutate_state(self):
        invalid = [event(artifact=[]), event(input_tokens=-1), event(claims=[claim("x", kind="made-up")]), event(artifact={"value": float("nan")})]
        for item in invalid:
            state = create_state("api-contract")
            before = deepcopy(state)
            with self.assertRaises(ValueError):
                ingest_event(state, item)
            self.assertEqual(state, before)

    def test_evidence_and_claim_retraction_remove_active_conflict(self):
        state = finish(create_state("evidence-update"))
        self.assertEqual(state["detector"]["conflicts"], [])
        wrong = next(item for item in state["claims"] if item["value"] == 50)
        self.assertEqual(wrong["status"], "retracted")
        memory = next(item for item in state["evidence"] if item.get("external_id") == "old-memory")
        self.assertEqual(memory["status"], "retracted")

    def test_delivery_promise_or_claim_is_not_delivery_proof(self):
        state = create_state("social-handoff", stall_window=1)
        payload = event("pickle-a", coordination={"human_input_requests": [{"id": "ask-a", "recipient": "person-a", "topic": "meeting.attendance", "delivery_status": "delivered", "delivery_receipt_id": "fake"}]})
        ingest_event(state, payload)
        self.assertEqual(state["coordination"]["human_input_requests"][0]["delivery_status"], "unknown")
        self.assertTrue(state["detector"]["delivery_unknown"])
        self.assertFalse(state["detector"]["intentional_human_wait"])
        self.assertEqual(state["status"], "waiting")
        self.assertIn("전달 여부는 확인되지", state["requests"][0]["summary"])

    def test_independent_delivery_record_preserves_intentional_human_wait(self):
        state = create_state("social-handoff", stall_window=1)
        # Trusted transport input is configured out of band, never by the agent.
        state["task"]["delivery_receipts"] = [{"id": "receipt-1", "request_id": "ask-a", "recipient": "person-a", "topic": "meeting.attendance"}]
        payload = event("pickle-a", coordination={"human_input_requests": [{"id": "ask-a", "recipient": "person-a", "topic": "meeting.attendance", "delivery_receipt_id": "receipt-1"}]})
        ingest_event(state, payload)
        self.assertTrue(state["detector"]["intentional_human_wait"])
        self.assertEqual(state["status"], "running")
        self.assertEqual(state["requests"], [])

    def test_review_cycle_and_missing_owner_are_structural_then_resolved_by_human(self):
        state = create_state("review-deadlock")
        ingest_event(state, next_demo_event(state))
        ingest_event(state, next_demo_event(state))
        self.assertTrue(state["detector"]["wait_cycles"])
        self.assertTrue(state["detector"]["missing_decision_owner"])
        while state["status"] == "running":
            ingest_event(state, next_demo_event(state))
        apply_decision(state, state["requests"][-1]["id"], "owner_a")
        self.assertEqual(state["coordination"]["decision_owner"], "person-a")
        self.assertEqual(state["detector"]["wait_cycles"], [])
        self.assertFalse(state["detector"]["missing_decision_owner"])

    def test_ontology_edges_have_valid_endpoints_and_declared_types(self):
        for scenario in scenario_catalog():
            state = finish(create_state(scenario["id"]))
            graph = ontology_graph(state)
            node_types = {node["id"]: node["type"] for node in graph["nodes"]}
            self.assertEqual(len(node_types), len(graph["nodes"]))
            for edge in graph["edges"]:
                self.assertIn(edge["source"], node_types)
                self.assertIn(edge["target"], node_types)
                relation = graph["ontology"]["relations"][edge["type"]]
                self.assertEqual(node_types[edge["source"]], relation["domain"])
                self.assertEqual(node_types[edge["target"]], relation["range"])
            json.dumps(graph, allow_nan=False)

    def test_old_validation_points_to_immutable_artifact_revision(self):
        state = create_state("api-contract", policy="capped")
        ingest_event(state, event(artifact={"endpoint": "/api/waitings"}))
        ingest_event(state, event(artifact={"endpoint": "/changed"}))
        graph = ontology_graph(state)
        first = next(item for item in graph["nodes"] if item["type"] == "Artifact" and item.get("revision") == 1)
        self.assertEqual(first["data"]["endpoint"], "/api/waitings")
        self.assertEqual(state["artifact"]["endpoint"], "/changed")


if __name__ == "__main__":
    unittest.main()
