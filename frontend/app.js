"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const number = (value) => Number(value || 0).toLocaleString("ko-KR");
  const labels = { running: "진행 중", waiting: "사람의 결정 대기", completed: "완료", budget_exhausted: "대화 한도 도달", stopped: "일시 중지", error: "실행 오류" };
  const policyNames = { adaptive: "충돌·정체 기반 개입", periodic: "주기적 개입", capped: "고정 횟수 제한" };
  const typeNames = { agent: "에이전트", claim: "주장", evidence: "근거", conflict: "충돌", request: "개입 요청", humaninputrequest: "개입 요청", commitment: "확인 약속", intervention: "개입 요청", decision: "결정", artifact: "산출물", task: "과제", concept: "개념" };
  const state = { config: null, sessions: [], selected: null, graph: null, mutation: false, timer: null, selection: 0, requestId: null, messagesKey: null,
    activeDecisionId: null, messageSeen: 0, briefState: null, briefTimer: null, briefPosting: false, briefFetching: false, briefVersion: 0,
    highlightedMessage: null, authority: null, authorityBusy: false, authorityLoading: false, authorityDrafts: new Map(), authorityEditing: new Set(), authorityChecksKey: null, briefFetchTask: null, resetting: false,
    pages: { sessions: 1, messages: 1, requests: 1, claims: 1, evidence: 1, nodes: 1, edges: 1, brief: 1, authority: 1, authorityChecks: 1 } };

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function text(value) {
    if (value === undefined || value === null) return "—";
    return typeof value === "object" ? JSON.stringify(value) : String(value);
  }

  function array(value) {
    if (Array.isArray(value)) return value;
    return value && typeof value === "object" ? Object.entries(value).map(([key, item]) => typeof item === "object" && item !== null ? { key, ...item } : { key, value: item }) : [];
  }

  function pageRows(rows, key, size) {
    const total = Math.max(1, Math.ceil(rows.length / size));
    state.pages[key] = Math.min(Math.max(1, state.pages[key]), total);
    return rows.slice((state.pages[key] - 1) * size, state.pages[key] * size);
  }

  function pagination(id, key, count, size, onChange) {
    const target = $(id); target.replaceChildren();
    const total = Math.max(1, Math.ceil(count / size));
    state.pages[key] = Math.min(Math.max(1, state.pages[key]), total);
    const current = state.pages[key];
    const range = count ? `${(current - 1) * size + 1}–${Math.min(current * size, count)}` : "0";
    target.append(element("span", "pagination-count", `${current} / ${total} 페이지 · ${range} / ${number(count)}개`));
    const buttons = element("div", "pagination-buttons");
    const add = (label, page, disabled, active = false) => {
      const button = element("button", `page-button ${label === "이전" || label === "다음" ? "page-direction" : "page-number"}${active ? " current" : ""}`, label);
      button.type = "button"; button.disabled = disabled;
      button.setAttribute("aria-label", label === "이전" || label === "다음" ? `${label} 페이지` : `${page}페이지`);
      if (active) button.setAttribute("aria-current", "page");
      button.addEventListener("click", () => {
        state.pages[key] = page; onChange();
        target.querySelector('[aria-current="page"]')?.focus({ preventScroll: true });
      });
      buttons.append(button);
    };
    add("이전", current - 1, current === 1);
    const pages = [...new Set([1, current - 1, current, current + 1, total])].filter((page) => page >= 1 && page <= total).sort((a, b) => a - b);
    let previous = 0;
    pages.forEach((page) => {
      if (previous && page - previous > 1) buttons.append(element("span", "page-ellipsis", "…"));
      add(String(page), page, false, current === page); previous = page;
    });
    add("다음", current + 1, current === total);
    target.append(buttons);
  }

  function resetSessionViews(session) {
    ["messages", "requests", "claims", "evidence", "nodes", "edges", "brief", "authorityChecks"].forEach((key) => { state.pages[key] = 1; });
    state.activeDecisionId = null; state.messageSeen = array(session.messages).length;
    state.requestId = null; state.messagesKey = null;
    clearTimeout(state.briefTimer); state.briefState = null; state.briefPosting = false; state.briefFetching = false; state.briefVersion += 1; state.highlightedMessage = null;
    state.authorityDrafts.clear(); state.authorityEditing.clear(); state.authorityChecksKey = null; $("precedence-feedback").textContent = "";
    $("request-filter").value = "all";
  }

  async function api(path, body) {
    const options = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    const response = await fetch(path, options);
    let data;
    try { data = await response.json(); } catch { data = {}; }
    if (!response.ok) {
      const detail = data.detail || data.error || `요청을 처리하지 못했습니다 (${response.status}).`;
      const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function showError(error) {
    $("error-text").textContent = error.message || String(error);
    $("error-banner").hidden = false;
  }

  function announce(message) { $("screen-reader-status").textContent = message; }

  function endpoint(suffix = "") { return `/api/sessions/${encodeURIComponent(state.selected.id)}${suffix}`; }

  function visitorDemo() { return state.config?.deployment?.mode === "visitor_demo"; }

  function liveBriefAvailable() { return Boolean(state.config) && !visitorDemo() && state.config.deployment?.live_model_available !== false; }

  function applyDeployment() {
    if (!visitorDemo()) return;
    $("deployment-label").textContent = "DEMO";
    $("deployment-notice").hidden = false;
    $("deployment-description").textContent = state.config.deployment.notice || "방문자별로 분리된 예시 체험입니다. 실제 외부 에이전트·소유자와 연결되지 않습니다.";
    document.querySelector(".brief-help").textContent = "예시 대화에 대해 이전에 생성한 모델 분석을 확인합니다. 실시간 모델 호출은 없으며, 변경한 권한 기록은 모델 호출 없이 다시 판정합니다.";
    document.querySelector(".intake-description").textContent = "대화를 붙여 넣어 규칙 기반의 대기·결정 후보를 확인할 수 있습니다. 이 체험에서는 새 모델 브리핑을 생성하지 않습니다.";
    document.querySelector(".intake-privacy").textContent = "이 브라우저의 체험 기록으로 저장됩니다. 외부 에이전트·Slack과 연결되지 않으며, 민감한 실제 대화 대신 예시를 사용하세요.";
    $("integration-heading").textContent = "내 환경에 설치하고 연결하기";
    $("integration-description").textContent = "실제 에이전트와 연결하려면 GitHub 소스를 자신의 환경에 설치하세요.";
    document.querySelector(".integration-notice").replaceChildren(element("strong", "", "방문자 체험의 연결 범위"), element("p", "", "이 체험 주소는 원격 MCP 서버가 아닙니다. 외부 에이전트·Slack·소유자와 연결되어 있지 않습니다."));
  }

  async function resetDemo() {
    if (!visitorDemo() || state.resetting || state.mutation || state.authorityBusy || state.authorityLoading || state.selected?.busy) return;
    state.resetting = true; state.mutation = true;
    clearTimeout(state.timer); clearTimeout(state.briefTimer); controls(); authorityControls(); renderBrief();
    $("reset-demo").textContent = "초기화 중…";
    try {
      await api("/api/demo/reset", {});
      try { localStorage.removeItem("arbiter-session"); } catch { /* Storage is optional. */ }
      location.reload();
    } catch (error) {
      state.resetting = false; state.mutation = false; $("reset-demo").textContent = "내 체험 초기화";
      controls(); authorityControls(); renderBrief(); schedulePoll(); scheduleBriefPoll(); showError(error);
    }
  }

  function coveredRequests(session) { return array(session?.coordination_advice?.covered_pending_decisions); }

  function remainingRequests(session) {
    const projected = session?.coordination_advice?.remaining_pending_decisions;
    return Array.isArray(projected) ? projected : array(session?.requests).filter((request) => request.status === "pending");
  }

  function sessionStatusLabel(session) {
    if (session.busy) return "에이전트 실행 중";
    const action = session.coordination_advice?.action;
    if (action === "follow_authority") return "권한 확인 · 실행 미확인";
    if (action === "wait_for_human") return "사람의 결정 대기";
    if (action === "refresh_coordination_context") return "대화 맥락 확인 필요";
    if (action === "wait_for_response") return "상대 응답 대기";
    return session.mode === "import" && session.status === "stopped" ? array(session.decisions).length ? "결정 기록 완료" : "확인 요청 없음" : labels[session.status] || session.status || "";
  }

  async function refreshCoordinationSnapshot(selection = state.selection) {
    if (!state.selected || selection !== state.selection) return null;
    const id = state.selected.id;
    try {
      const session = await api(`/api/sessions/${encodeURIComponent(id)}`);
      if (selection !== state.selection || id !== state.selected?.id) return null;
      if (session.brief_view) state.briefState = session.brief_view;
      render(session); return session;
    } catch { return null; }
  }

  function setOptions(target, rows, selected) {
    target.replaceChildren();
    rows.forEach((row) => {
      const option = element("option", "", row.label || row.title || row.id);
      option.value = row.id;
      option.disabled = row.available === false;
      option.selected = row.id === selected;
      target.append(option);
    });
    target.disabled = !rows.some((row) => row.available !== false);
    if (!target.value || target.selectedOptions[0]?.disabled) {
      const firstAvailable = rows.find((row) => row.available !== false);
      if (firstAvailable) target.value = firstAvailable.id;
    }
  }

  function updateFormDescription() {
    const config = state.config;
    if (!config) return;
    const scenario = config.scenarios.find((item) => item.id === $("scenario-select").value);
    $("scenario-description").textContent = scenario?.description || "";
    const provider = config.providers.find((item) => item.id === $("mode-select").value);
    $("provider-description").textContent = provider?.id === "demo" ? "시연은 미리 구성된 대화를 재생합니다. 실제 LLM 실험과 구분됩니다." : "연결된 에이전트가 과제를 수행합니다. 측정된 사용량만 기록합니다.";
    $("create-session").disabled = state.mutation || !scenario || !provider || provider.available === false;
  }

  function renderSessions() {
    const target = $("session-list");
    target.replaceChildren();
    pagination("session-pagination", "sessions", state.sessions.length, 5, renderSessions);
    if (!state.sessions.length) { target.append(element("p", "sidebar-empty", "아직 세션이 없습니다. 위에서 첫 협업을 만들어 보세요.")); return; }
    pageRows(state.sessions, "sessions", 5).forEach((session) => {
      const button = element("button", `session-item${state.selected?.id === session.id ? " active" : ""}`);
      button.type = "button";
      button.disabled = state.mutation;
      button.setAttribute("aria-pressed", String(state.selected?.id === session.id));
      button.append(element("span", "session-item-title", session.title || session.scenario_id || session.id));
      const meta = element("span", "session-item-meta");
      meta.append(element("span", "", `${session.mode === "demo" ? "시연" : session.mode === "import" ? "가져온 대화" : "실제 실행"} · ${session.turn ?? 0}턴`), element("span", "", sessionStatusLabel(session)));
      button.append(meta);
      button.addEventListener("click", () => selectSession(session.id));
      target.append(button);
    });
  }

  async function refreshSessions() {
    if (!state.config || state.resetting) return;
    const result = await api("/api/sessions");
    state.sessions = Array.isArray(result) ? result : array(result.sessions);
    renderSessions();
  }

  function updateSessionSummary(session) {
    const index = state.sessions.findIndex((item) => item.id === session.id);
    if (index >= 0) state.sessions[index] = session;
    else state.sessions.unshift(session);
    renderSessions();
  }

  function controls() {
    const session = state.selected;
    const canRun = session && session.mode !== "import" && ["running", "stopped", "error"].includes(session.status) && !session.busy && !state.mutation;
    document.querySelector(".session-actions").hidden = session?.mode === "import";
    $("step-button").disabled = !canRun;
    $("run-button").disabled = !canRun;
    $("run-button").classList.toggle("loading", Boolean(session?.busy));
    $("stop-button").disabled = !session || state.mutation || !session.busy;
    $("create-session").disabled = state.mutation || !state.config || !$("mode-select").value;
    $("create-session").classList.replace("primary", "secondary");
    $("open-intake").disabled = state.mutation || !state.config;
    $("open-intake").classList.toggle("primary", !session || session.mode === "import");
    $("open-intake").classList.toggle("secondary", Boolean(session && session.mode !== "import"));
    $("session-form").querySelectorAll("select").forEach((select) => { select.disabled = state.mutation || !state.config; });
    $("session-list").querySelectorAll("button").forEach((button) => { button.disabled = state.mutation; });
    const submit = $("decision-submit");
    if (submit) submit.disabled = state.mutation || Boolean(session?.busy);
    $("refresh-sessions").disabled = state.mutation || !state.config;
    $("reset-demo").disabled = !visitorDemo() || state.mutation || state.authorityBusy || state.authorityLoading || Boolean(session?.busy);
  }

  function renderMetrics(session) {
    const metrics = session.metrics || {};
    const metricLabels = document.querySelectorAll(".metric-label");
    metricLabels[0].textContent = session.mode === "import" ? "가져온 발화" : "진행한 대화";
    metricLabels[1].textContent = "에이전트 토큰";
    metricLabels[3].textContent = session.mode === "import" ? "기록한 다음 행동" : "확인된 진행 변화";
    $("metric-turns").textContent = number(session.turn);
    $("metric-turns-note").textContent = session.mode === "import" ? `제공된 원문 ${number(session.turn)}개 발화` : `최대 ${number(session.max_turns)}턴`;
    const measured = Number(metrics.measured_calls || 0) > 0;
    $("metric-tokens").textContent = measured ? number(Number(metrics.input_tokens || 0) + Number(metrics.output_tokens || 0)) : "미측정";
    $("metric-tokens-unit").textContent = measured ? "tokens" : "";
    $("metric-tokens-note").textContent = measured ? `입력 ${number(metrics.input_tokens)} · 출력 ${number(metrics.output_tokens)}${metrics.unmetered_calls ? ` · 미측정 ${number(metrics.unmetered_calls)}회` : ""}` : session.mode === "demo" ? "시연 데이터 · 실제 토큰 없음" : session.mode === "import" ? "가져온 대화 · 사용량 정보 없음" : "사용량이 보고된 호출 없음";
    $("metric-requests").textContent = number(metrics.human_requests ?? array(session.requests).length);
    $("metric-requests-note").textContent = `결정 완료 ${array(session.decisions).length}회${coveredRequests(session).length ? ` · 권한으로 확인 ${coveredRequests(session).length}건` : ""}`;
    $("metric-progress").textContent = number(metrics.progress_events);
    $("metric-progress-note").textContent = session.mode === "import" ? "외부 실행·완료는 미확인" : metrics.success === true ? "완료 조건 충족" : session.status === "completed" ? "세션 종료 · 결과 확인" : "산출물·근거 변화";
  }

  function openSource(reference) {
    if (!state.selected) return;
    const messages = array(state.selected.messages);
    let index = messages.findIndex((message) => message.id === reference);
    const numbered = /^m(\d+)$/.exec(reference);
    if (index < 0 && numbered) index = Number(numbered[1]) - 1;
    if (index < 0 || index >= messages.length) {
      index = messages.findIndex((message) => array(message.evidence).some((item) => item.id === reference) || message.evidence_ids?.includes(reference));
    }
    if (index < 0) { showError(new Error(`원문에서 ${reference} 근거를 찾지 못했습니다.`)); return; }
    state.pages.messages = Math.floor(index / 10) + 1; state.highlightedMessage = index;
    renderConversation(state.selected); switchTab($("conversation-tab"));
    const message = $("conversation").querySelector(`[data-message-index="${index}"]`);
    message?.focus({ preventScroll: true }); message?.scrollIntoView({ block: "center" });
  }

  function authorityCheckRows() {
    return array(state.briefState?.authority_checks ?? state.briefState?.brief?.authority_checks ?? state.selected?.authority_checks);
  }

  function authorityScopeKey(check) { return JSON.stringify([check.scope, check.action]); }

  function precedenceDraft(check) {
    const key = authorityScopeKey(check);
    let draft = state.authorityDrafts.get(key);
    if (!draft) {
      const agents = [...new Set(array(check.authorized_agents).filter((agent) => typeof agent === "string" && agent))];
      const saved = array(state.authority?.precedence).find((record) => record.issuer === "local-human" && check.grant_revision && record.grant_revision === check.grant_revision && record.scope === check.scope && record.action === check.action && Array.isArray(record.agents) && record.agents.length === agents.length && new Set(record.agents).size === agents.length && record.agents.every((agent) => agents.includes(agent)));
      const approved = saved ? array(saved.approved_by).filter((owner) => array(check.required_owners).includes(owner)) : [];
      draft = { agents: saved ? [...saved.agents] : agents, approved: new Set(approved), revision: check.registry_revision, restored: approved.length > 0, message: "", stale: false };
      state.authorityDrafts.set(key, draft);
    }
    return draft;
  }

  function resolutionForm(check) {
    const key = authorityScopeKey(check); const draft = precedenceDraft(check);
    const form = element("form", "precedence-form"); form.dataset.scope = check.scope; form.dataset.action = check.action;
    form.append(element("h4", "", "이 결정의 우선순위와 승인 기록"), element("p", "precedence-scope", `적용 대상: ${check.scope} / ${check.action}`), element("p", "precedence-help", "모든 유효 에이전트의 순서를 정하고, 이 순서에 실제 동의한 소유자만 표시하세요. 이 범위와 행동에만 적용하는 로컬 운영자의 기록이며 원격 본인 인증을 뜻하지 않습니다."));
    const group = element("fieldset", "precedence-fields");
    group.append(element("legend", "", "우선순위 제안 · 위에서부터 먼저 결정"));
    const order = element("ol", "precedence-order");
    draft.agents.forEach((agent, index) => {
      const row = element("li", "precedence-agent");
      const identity = element("div", "precedence-agent-label"); identity.append(element("strong", "", `${index + 1}. ${agent}`), element("span", "", `소유자: ${check.owner_by_agent?.[agent] || "확인 안 됨"}`));
      const actions = element("div", "precedence-moves");
      [[-1, "위로"], [1, "아래로"]].forEach(([direction, label]) => {
        const button = element("button", "precedence-button", label); button.type = "button";
        const boundary = index + direction < 0 || index + direction >= draft.agents.length;
        button.dataset.locked = String(boundary); button.disabled = boundary; button.setAttribute("aria-label", `${agent} 우선순위 ${label}`);
        button.addEventListener("click", () => {
          [draft.agents[index], draft.agents[index + direction]] = [draft.agents[index + direction], draft.agents[index]];
          draft.approved.clear(); draft.restored = false; draft.message = "순서를 바꿨습니다. 새 순서에 대한 소유자 승인을 다시 확인하세요.";
          renderAuthorityChecks(true);
          const replaced = [...$("authority-checks").querySelectorAll(".precedence-form")].find((item) => item.dataset.scope === check.scope && item.dataset.action === check.action);
          const moved = [...(replaced?.querySelectorAll(".precedence-moves button") || [])].find((item) => item.getAttribute("aria-label") === `${agent} 우선순위 ${direction === -1 ? "아래로" : "위로"}`);
          moved?.focus({ preventScroll: true }); announce(draft.message);
        });
        actions.append(button);
      });
      row.append(identity, actions); order.append(row);
    });
    group.append(order); form.append(group);
    const approvals = element("fieldset", "precedence-approvals"); approvals.append(element("legend", "", "이 순서에 동의한 소유자"));
    const owners = [...new Set(array(check.required_owners).filter((owner) => typeof owner === "string" && owner))];
    owners.forEach((owner) => {
      const label = element("label", "precedence-owner"); const input = document.createElement("input");
      input.type = "checkbox"; input.name = "approved_by"; input.value = owner; input.checked = draft.approved.has(owner);
      input.addEventListener("change", () => { if (input.checked) draft.approved.add(owner); else draft.approved.delete(owner); draft.restored = false; updateApprovalState(); });
      label.append(input, element("span", "", `${owner}의 동의를 확인했습니다`)); approvals.append(label);
    });
    form.append(approvals);
    const summary = element("p", "precedence-approval-summary"); summary.setAttribute("role", "status");
    const feedback = element("p", "precedence-local-feedback"); feedback.setAttribute("role", "status");
    const buttons = element("div", "precedence-actions"); const submit = element("button", "precedence-button precedence-submit", "우선순위와 승인 기록 저장"); submit.type = "submit";
    const refresh = element("button", "precedence-button", "최신 권한 다시 확인"); refresh.type = "button";
    refresh.addEventListener("click", () => refreshAuthorityScope(key)); buttons.append(submit, refresh);
    const updateApprovalState = () => {
      const missing = owners.filter((owner) => !draft.approved.has(owner));
      const revisionMissing = typeof draft.revision !== "string" || !draft.revision;
      const changed = draft.stale || draft.revision !== check.registry_revision;
      summary.textContent = missing.length ? `미확인 소유자: ${missing.join(", ")} · 제안한 순서는 아직 확정되지 않았습니다.${owners.length > 1 ? " 일부 승인만 저장하면 권한 충돌로 판정됩니다." : " 소유자 동의를 확인한 뒤 저장할 수 있습니다."}` : "모든 관련 소유자의 동의를 표시했습니다. 저장 후 서버 판정을 확인하세요.";
      feedback.textContent = changed ? "권한 기록이 바뀌었습니다. 최신 권한을 다시 확인한 뒤 순서와 승인을 입력하세요." : revisionMissing ? "권한 기록의 버전을 확인할 수 없습니다. 최신 권한을 다시 확인해 주세요." : draft.message || (draft.restored ? "저장된 동일 순서의 승인 기록을 불러왔습니다." : "승인 체크는 자동으로 선택하지 않습니다.");
      const blocked = revisionMissing || changed || draft.agents.length < 2 || !check.scope || !check.action || !owners.length || (owners.length <= 1 && missing.length > 0);
      submit.dataset.locked = String(blocked); submit.disabled = blocked || state.authorityBusy || state.authorityLoading;
    };
    form.append(summary, feedback, buttons); updateApprovalState();
    form.addEventListener("submit", (event) => { event.preventDefault(); if (!submit.disabled) savePrecedence(check, draft); });
    return form;
  }

  async function refreshAuthorityScope(key) {
    if (state.authorityBusy || state.authorityLoading) return;
    const selection = state.selection; state.authorityBusy = true; authorityControls();
    try {
      await loadAuthority();
      if (selection !== state.selection) return;
      state.authorityDrafts.delete(key); state.authorityEditing.delete(key); const result = await refreshBrief(true);
      await refreshCoordinationSnapshot(selection);
      if (selection !== state.selection) return;
      $("precedence-feedback").textContent = result ? "최신 권한으로 다시 확인했습니다. 입력할 순서와 소유자 승인 기록을 확인하세요." : "최신 판정을 불러오지 못했습니다. 다시 확인해 주세요.";
      renderAuthorityChecks(true);
    } finally { state.authorityBusy = false; authorityControls(); }
  }

  async function savePrecedence(check, draft) {
    if (state.authorityBusy || state.authorityLoading || state.resetting || !state.config) return;
    const selection = state.selection; const key = authorityScopeKey(check);
    state.authorityBusy = true; authorityControls(); $("precedence-feedback").textContent = "우선순위와 승인 기록을 저장하고 있습니다.";
    try {
      await api("/api/authority/precedence", { scope: check.scope, action: check.action, agents: [...draft.agents], approved_by: [...draft.approved], expected_revision: draft.revision });
      await loadAuthority();
      if (selection !== state.selection) return;
      state.authorityDrafts.delete(key); state.authorityEditing.delete(key); const result = await refreshBrief(true);
      await refreshCoordinationSnapshot(selection);
      if (selection !== state.selection) return;
      const updated = authorityCheckRows().find((item) => authorityScopeKey(item) === key);
      const detail = !result ? "최신 판정을 불러오지 못했습니다. 다시 확인해 주세요." : updated?.status === "authorized" ? `결정 담당: ${updated.decision_owner}. 브리핑 개입 지점 ${array(result.brief?.intervention_points).length}개.` : "아직 권한이 확정되지 않았습니다. 미확인 소유자와 판정 이유를 확인하세요.";
      $("precedence-feedback").textContent = `${check.scope} / ${check.action}의 기록을 저장했습니다. ${detail}`;
      announce($("precedence-feedback").textContent); renderAuthorityChecks(true);
    } catch (error) {
      if (selection === state.selection) {
        if (error.status === 409) draft.stale = true;
        draft.message = `저장하지 못했습니다. ${error.message}`;
        $("precedence-feedback").textContent = draft.message; renderAuthorityChecks(true);
      }
    } finally { state.authorityBusy = false; authorityControls(); }
  }

  function renderAuthorityChecks(force = false) {
    const rows = authorityCheckRows();
    const panel = $("authority-check-panel"); panel.hidden = !rows.length;
    $("authority-intervention-count").textContent = `브리핑 개입 지점 ${array(state.briefState?.brief?.intervention_points).length}개 · 권한 판정 ${rows.length}개`;
    if (!rows.length) return;
    const key = JSON.stringify([state.selected?.id, rows, state.pages.authorityChecks]);
    if (!force && key === state.authorityChecksKey) { authorityControls(); return; }
    state.authorityChecksKey = key;
    const statuses = { missing: "위임 확인 필요", authority_gap: "위임 확인 필요", conflict: "권한 충돌", authority_conflict: "권한 충돌", cross_owner_conflict: "소유자 간 권한 충돌", conditional: "조건 확인 필요", unknown: "권한 확인 필요", authorized: "위임 확인됨", allowed: "위임 확인됨", ok: "위임 확인됨", resolved: "결정권자 확인됨", owner_required: "소유자 판단 필요", missing_owner: "소유자 확인 필요", expired: "기간 만료", revoked: "권한 철회됨" };
    const priority = (item) => ["conflict", "authority_conflict", "cross_owner_conflict"].includes(item.status) ? 0 : ["missing", "missing_owner", "authority_gap", "conditional", "unknown"].includes(item.status) ? 1 : 2;
    const ordered = [...rows].sort((a, b) => priority(a) - priority(b));
    const target = $("authority-checks"); target.replaceChildren();
    pageRows(ordered, "authorityChecks", 6).forEach((check) => {
      const article = element("article", "authority-check");
      article.append(element("span", "authority-check-status", statuses[check.status] || check.status || "확인 안 됨"), element("h3", "", `${check.scope || "범위 확인 안 됨"} · ${check.action || "행동 확인 안 됨"}`));
      const details = element("dl", "authority-check-details");
      const fields = [
        ["위임된 에이전트", array(check.authorized_agents).length ? array(check.authorized_agents).map(text).join(", ") : "확인된 위임 없음"],
        ["결정 담당 에이전트", check.decision_owner ? text(check.decision_owner) : "확인 안 됨"],
      ];
      if (array(check.required_owners).length) fields.push(["필요한 소유자 판단", array(check.required_owners).map(text).join(", ")]);
      if (check.owner_by_agent && Object.keys(check.owner_by_agent).length) fields.push(["소유자별 에이전트", Object.entries(check.owner_by_agent).map(([agent, owner]) => `${owner} → ${agent}`).join(", ")]);
      if (array(check.priority_order).length) fields.push(["적용된 우선순위", check.priority_order.join(" → ")]);
      fields.forEach(([label, value]) => details.append(element("dt", "", label), element("dd", "", value)));
      article.append(details);
      if (check.reason) article.append(element("p", "authority-check-reason", check.reason));
      if (["authority_conflict", "cross_owner_conflict"].includes(check.status) || (check.status === "authorized" && state.authorityEditing.has(authorityScopeKey(check)))) { article.classList.add("has-resolution"); article.append(resolutionForm(check)); }
      else if (check.status === "authorized" && check.precedence_applied && array(check.authorized_agents).length > 1) {
        const button = element("button", "precedence-button", "기록된 우선순위 수정"); button.type = "button";
        button.addEventListener("click", () => { state.authorityEditing.add(authorityScopeKey(check)); renderAuthorityChecks(true); }); article.append(button);
      }
      else if (["authority_gap", "conditional", "unknown", "missing", "missing_owner"].includes(check.status)) {
        article.append(element("p", "authority-guidance", "우선순위만으로 확정할 수 없습니다. 소유자·위임 범위·조건과 유효한 기록을 먼저 확인하세요."));
        const button = element("button", "precedence-button", "위임 기록 확인"); button.type = "button"; button.addEventListener("click", () => switchTab($("knowledge-tab"))); article.append(button);
      }
      target.append(article);
    });
    pagination("authority-check-pagination", "authorityChecks", ordered.length, 6, renderAuthorityChecks);
    authorityControls();
  }

  function authorityControls() {
    const busy = state.authorityBusy || state.authorityLoading || state.resetting || !state.config;
    $("authority-form").querySelectorAll("input, button").forEach((control) => { control.disabled = busy; });
    $("authority-list").querySelectorAll("button").forEach((button) => { button.disabled = busy || button.dataset.revoked === "true"; });
    $("refresh-authority").disabled = busy;
    $("authority-checks").querySelectorAll(".precedence-form input, .precedence-form button").forEach((control) => { control.disabled = busy || control.dataset.locked === "true"; });
    $("reset-demo").disabled = !visitorDemo() || busy || state.mutation || Boolean(state.selected?.busy);
  }

  function renderAuthority() {
    const grants = array(state.authority?.grants);
    const target = $("authority-list"); target.replaceChildren();
    pagination("authority-pagination", "authority", grants.length, 8, renderAuthority);
    if (!grants.length) { target.append(element("p", "authority-empty", "등록된 위임이 없습니다. 에이전트의 소유자와 위임 범위·행동을 먼저 기록하세요.")); return; }
    const wrapper = element("div", "authority-table-wrap"); const table = element("table", "authority-table");
    const heading = element("tr"); ["에이전트", "소유자", "작업 범위", "행동", "상태", "관리"].forEach((label) => { const th = element("th", "", label); th.scope = "col"; heading.append(th); });
    const head = element("thead"); head.append(heading); const body = element("tbody");
    pageRows(grants, "authority", 8).forEach((grant) => {
      const expired = Boolean(grant.expires_at && Number.isFinite(Date.parse(grant.expires_at)) && Date.parse(grant.expires_at) <= Date.now());
      const row = element("tr");
      [grant.agent, grant.owner, grant.scope, grant.action, grant.revoked ? "철회됨" : expired ? "기간 만료" : "등록됨"].forEach((value) => row.append(element("td", "", text(value))));
      const action = element("td"); const button = element("button", "button secondary", grant.revoked ? "철회됨" : "철회"); button.type = "button"; button.dataset.revoked = String(Boolean(grant.revoked));
      button.disabled = Boolean(grant.revoked) || state.authorityBusy || state.authorityLoading;
      button.setAttribute("aria-label", `${grant.agent}의 ${grant.scope} ${grant.action} 권한 철회`);
      button.addEventListener("click", () => mutateAuthority(`/api/authority/grants/${encodeURIComponent(grant.id)}/revoke`, {}, "권한을 철회했습니다."));
      action.append(button); row.append(action); body.append(row);
    });
    table.append(head, body); wrapper.append(table); target.append(wrapper);
  }

  async function loadAuthority() {
    if (!state.config || state.authorityLoading || state.resetting) return;
    state.authorityLoading = true; authorityControls();
    try { state.authority = await api("/api/authority"); renderAuthority(); }
    catch (error) { $("authority-list").replaceChildren(element("p", "authority-empty", `권한 목록을 불러오지 못했습니다. ${error.message}`)); $("authority-pagination").replaceChildren(); }
    finally { state.authorityLoading = false; authorityControls(); }
  }

  async function mutateAuthority(path, payload, message) {
    if (!state.config || state.authorityBusy || state.authorityLoading || state.resetting) return;
    state.authorityBusy = true; authorityControls(); $("authority-feedback").textContent = "";
    try {
      await api(path, payload); await loadAuthority();
      if (path === "/api/authority/grants") { $("authority-form").reset(); state.pages.authority = Math.max(1, Math.ceil(array(state.authority?.grants).length / 8)); renderAuthority(); }
      $("authority-feedback").textContent = message; announce(message); await refreshBrief(true); await refreshCoordinationSnapshot();
    } catch (error) { $("authority-feedback").textContent = `요청을 처리하지 못했습니다. ${error.message}`; }
    finally { state.authorityBusy = false; authorityControls(); }
  }

  function createGrant(event) {
    event.preventDefault();
    const data = new FormData($("authority-form"));
    const payload = Object.fromEntries(["agent", "owner", "scope", "action"].map((key) => [key, String(data.get(key) || "").trim()]));
    if (Object.values(payload).some((value) => !value)) { $("authority-feedback").textContent = "에이전트, 소유자, 작업 범위, 행동을 모두 입력해 주세요."; return; }
    mutateAuthority("/api/authority/grants", { ...payload, conditions: [] }, "소유자와 위임한 범위·행동을 기록했습니다.");
  }

  function renderBrief() {
    const data = state.briefState || {};
    const brief = data.brief;
    const generating = state.briefPosting || data.status === "generating";
    const button = $("generate-brief");
    button.disabled = !liveBriefAvailable() || !state.selected || !array(state.selected.messages).length || generating || state.resetting;
    button.classList.toggle("loading", generating);
    button.textContent = visitorDemo() ? "체험에서는 새 분석 생성 불가" : generating ? "브리핑 생성 중" : brief ? "브리핑 다시 생성" : "대화 브리핑 생성";
    const status = $("brief-status");
    const stale = Boolean(brief && ((data.conversation_stale === undefined ? data.stale : data.conversation_stale) || (typeof brief.generated_turn === "number" && brief.generated_turn !== state.selected?.turn)));
    status.classList.toggle("is-stale", stale);
    if (generating) status.textContent = "대화와 인용 근거를 확인하고 있습니다. 생성하는 동안 다른 탭을 사용할 수 있습니다.";
    else if (data.status === "error") status.textContent = `브리핑을 생성하거나 불러오지 못했습니다. ${data.error || "다시 시도해 주세요."}`;
    else if (stale) status.textContent = visitorDemo() ? "이후 대화나 결정이 바뀌었습니다. 기록된 분석은 변경된 대화를 반영하지 않습니다. 새 모델 분석은 자신의 환경에 설치한 뒤 사용할 수 있습니다." : "이후 대화나 결정이 바뀌었습니다. 최신 내용을 반영하려면 브리핑을 다시 생성하세요.";
    else if (brief && data.authority_stale) status.textContent = `${brief.generated_turn ?? "—"}턴 대화 기준${visitorDemo() ? " · 기록된 모델 분석" : ""} · 변경된 권한 기록으로 판정을 갱신했습니다. 추가 모델 호출 없이 현재 위임과 개입 지점을 확인할 수 있습니다.`;
    else if (brief) status.textContent = `${brief.generated_turn ?? "—"}턴까지의 대화 기준 · ${visitorDemo() ? "기록된 모델 분석 · 실시간 호출 아님" : brief.source === "codex" ? "실제 모델 생성" : text(brief.source)}`;
    else status.textContent = visitorDemo() ? "이 대화에는 기록된 모델 분석이 없습니다. 체험에서는 대기·결정 후보를 확인할 수 있으며 새 모델 브리핑은 생성하지 않습니다." : state.selected ? "아직 생성된 브리핑이 없습니다. 대화를 바탕으로 정리하려면 생성 버튼을 누르세요." : "대화를 선택하면 브리핑을 생성할 수 있습니다.";
    const target = $("brief-content"); target.replaceChildren();
    renderAuthorityChecks();
    $("brief-pagination").hidden = !brief;
    if (!brief) return;
    target.append(element("p", "brief-overview", brief.overview || "대화의 전체 맥락은 확인 안 됨"));
    if (brief.coverage) {
      const coverage = brief.coverage;
      target.append(element("p", "brief-scope", `분석 범위 · 대화 ${coverage.included_messages ?? "—"} / ${coverage.total_messages ?? "—"}개${coverage.truncated_messages ? ` · 일부 내용이 잘린 발화 ${coverage.truncated_messages}개` : ""}`));
    }
    const sections = [["agreements", "합의"], ["open_questions", "미해결 질문"], ["intervention_points", "개입 지점"], ["next_actions", "다음 행동"]];
    const rows = sections.flatMap(([key, label]) => {
      const items = array(brief[key]);
      return items.length ? items.map((item) => ({ ...item, label })) : [{ text: "제공된 대화에서 확인 안 됨", evidence_ids: [], label }];
    });
    const list = element("div", "brief-items");
    pageRows(rows, "brief", 6).forEach((item) => {
      const article = element("article", "brief-item");
      article.append(element("span", "brief-category", item.label), element("p", "", item.text || "확인 안 됨"));
      const references = element("div", "brief-references");
      array(item.evidence_ids).forEach((id) => {
        const reference = String(id); const source = element("button", "source-reference", reference); source.type = "button";
        const citation = array(item.evidence).find((entry) => entry.message_id === reference);
        if (citation?.quote) source.title = citation.quote;
        source.setAttribute("aria-label", `${reference} 대화 원문 확인`); source.addEventListener("click", () => openSource(reference)); references.append(source);
      });
      if (references.childNodes.length) article.append(references);
      list.append(article);
    });
    target.append(list);
    const measured = brief.input_tokens != null && brief.output_tokens != null;
    const usageLabel = visitorDemo() ? "기록된 모델 분석 사용량" : "브리핑 모델 사용량";
    target.append(element("p", "brief-usage", measured ? `${usageLabel} · 입력 ${number(brief.input_tokens)} / 출력 ${number(brief.output_tokens)} tokens` : `${usageLabel} · 미측정`));
    pagination("brief-pagination", "brief", rows.length, 6, renderBrief);
  }

  function scheduleBriefPoll() {
    clearTimeout(state.briefTimer);
    if (state.selected && (state.briefState?.status === "generating" || state.briefPosting)) state.briefTimer = setTimeout(refreshBrief, 1000);
  }

  async function refreshBrief(force = false) {
    if (!state.selected || state.briefPosting) return null;
    const selection = state.selection;
    if (state.briefFetching) {
      if (!force) return null;
      await state.briefFetchTask;
      if (selection !== state.selection) return null;
    }
    const id = state.selected.id; const version = state.briefVersion;
    state.briefFetching = true;
    state.briefFetchTask = (async () => {
      try {
        const data = await api(`/api/sessions/${encodeURIComponent(id)}/brief`);
        if (selection !== state.selection || version !== state.briefVersion) return null;
        state.briefState = data; renderBrief(); return data;
      } catch (error) {
        if (selection === state.selection && version === state.briefVersion) { state.briefState = { ...state.briefState, status: "error", error: error.message }; renderBrief(); }
        return null;
      } finally {
        if (selection === state.selection && version === state.briefVersion) { state.briefFetching = false; scheduleBriefPoll(); }
      }
    })();
    return state.briefFetchTask;
  }

  async function generateBrief() {
    if (!liveBriefAvailable() || state.resetting || !state.selected || state.briefPosting || state.briefState?.status === "generating") return;
    const selection = state.selection; const id = state.selected.id;
    clearTimeout(state.briefTimer); state.briefPosting = true; state.briefVersion += 1;
    state.briefState = { ...state.briefState, status: "generating", error: null }; renderBrief();
    try {
      const data = await api(`/api/sessions/${encodeURIComponent(id)}/brief`, {});
      if (selection !== state.selection) return;
      state.briefState = { ...state.briefState, ...data };
    } catch (error) {
      if (selection === state.selection) state.briefState = { ...state.briefState, status: "error", error: error.message };
    } finally {
      if (selection === state.selection) { state.briefPosting = false; renderBrief(); scheduleBriefPoll(); }
    }
  }

  function renderConversation(session) {
    const messages = array(session.messages);
    $("message-count").textContent = String(messages.length);
    $("conversation-tab-count").textContent = String(messages.length);
    const rows = pageRows(messages, "messages", 10);
    const start = (state.pages.messages - 1) * 10;
    const newCount = Math.max(0, messages.length - state.messageSeen);
    $("latest-messages").disabled = !messages.length;
    $("latest-messages").textContent = newCount ? `새 대화 ${newCount}개 · 최신 보기` : "최신 대화 보기";
    $("latest-messages").classList.toggle("has-new", newCount > 0);
    $("message-range").textContent = messages.length ? `${start + 1}–${Math.min(start + 10, messages.length)} / 전체 ${messages.length}개 · 페이지당 10개` : "아직 대화가 없습니다";
    pagination("message-pagination", "messages", messages.length, 10, () => renderConversation(state.selected));
    const key = `${session.id}:${state.pages.messages}:${state.highlightedMessage}:${JSON.stringify(rows)}`;
    if (key === state.messagesKey) return;
    state.messagesKey = key;
    const target = $("conversation");
    target.replaceChildren();
    if (!messages.length) {
      const empty = element("div", "empty-state");
      empty.append(element("span", "empty-symbol", "↔"), element("h3", "", "준비됐습니다. 대화를 시작하세요."), element("p", "", "한 턴씩 확인하거나, 결정이 필요한 순간까지 실행할 수 있습니다."));
      target.append(empty);
      return;
    }
    rows.forEach((message, index) => {
      const agent = message.agent || message.role || "에이전트";
      const human = /human|user|사람/i.test(agent);
      const article = element("article", `message${human ? " message-human" : ""}${state.highlightedMessage === start + index ? " source-highlight" : ""}`);
      article.dataset.messageIndex = String(start + index); article.tabIndex = -1;
      const avatar = element("span", "avatar", human ? "H" : agent.slice(0, 1).toUpperCase());
      avatar.setAttribute("aria-hidden", "true");
      const body = element("div", "message-body");
      const meta = element("div", "message-meta");
      meta.append(element("span", "message-agent", agent), element("span", "message-turn", `턴 ${message.turn ?? start + index + 1}`));
      body.append(meta, element("p", "message-text", message.content || ""));
      const chips = element("div", "message-chips");
      array(message.claims).forEach((claim) => chips.append(element("span", "message-chip", `${claim.key || claim.subject || "주장"}: ${text(claim.value ?? claim.object)}`)));
      array(message.evidence).forEach((evidence) => chips.append(element("span", "message-chip evidence-chip", `근거 · ${evidence.id || evidence.summary || text(evidence)}`)));
      if (chips.childNodes.length) body.append(chips);
      if (message.input_tokens != null || message.output_tokens != null) body.append(element("p", "message-tokens", `입력 ${number(message.input_tokens)} · 출력 ${number(message.output_tokens)} tokens`));
      article.append(avatar, body);
      target.append(article);
    });
  }

  function openDecision(requestId) {
    const requests = array(state.selected?.requests);
    const index = requests.findIndex((request) => request.id === requestId);
    $("request-filter").value = "all";
    state.pages.requests = index < 0 ? 1 : Math.floor(index / 5) + 1;
    state.activeDecisionId = requestId;
    if (state.selected) renderDecisionInbox(state.selected);
    switchTab($("decisions-tab"));
  }

  function renderOverview(session) {
    const pending = remainingRequests(session); const covered = coveredRequests(session);
    $("overview-pending-count").textContent = String(pending.length);
    $("decision-tab-count").textContent = String(pending.length);
    const target = $("overview-decision"); target.replaceChildren();
    if (pending.length) {
      const request = pending[0];
      target.append(element("p", "overview-kicker", `판단 대기 ${pending.length}건`), element("h3", "", request.title), element("p", "overview-summary", request.question || request.summary));
      const button = element("button", "button primary", "결정 확인하기 →"); button.type = "button";
      button.addEventListener("click", () => openDecision(request.id)); target.append(button);
    } else if (covered.length) {
      const authority = covered[0].covered_by_authority || {};
      target.append(element("p", "overview-kicker", `권한 기록으로 확인 ${covered.length}건`), element("h3", "", "같은 승인을 다시 입력하지 않아도 됩니다"), element("p", "overview-summary", `${authority.scope || "해당 범위"} / ${authority.action || "해당 행동"}의 담당은 ${authority.decision_owner || "권한 판정 참조"}입니다. 현재 권한으로 답할 수 있는 질문이며 외부 전달·실행 완료는 별도 확인해야 합니다.`));
      const button = element("button", "button secondary", "권한으로 확인된 요청 보기 →"); button.type = "button"; button.addEventListener("click", () => openDecision(covered[0].id)); target.append(button);
    } else {
      const recorded = session.mode === "import" && array(session.decisions).length;
      target.append(element("span", "overview-check", "◎"), element("h3", "", recorded ? "판단을 기록했습니다" : session.status === "completed" ? "협업이 완료됐습니다" : "지금은 확인할 결정이 없습니다"), element("p", "overview-summary", recorded ? "다음 행동과 담당자를 결정함에서 확인하세요. 외부 실행 여부는 별도 확인이 필요합니다." : session.busy ? "에이전트가 작업 중입니다. 판단이 필요하면 이곳에 표시합니다." : "대화와 근거를 확인하면서 다음 진행을 준비할 수 있습니다."));
      const button = element("button", "button secondary", "대화 확인하기 →"); button.type = "button"; button.addEventListener("click", () => switchTab($("conversation-tab"))); target.append(button);
    }
    $("overview-task-panel").hidden = Boolean(session.coordination);
    const task = $("overview-task"); task.replaceChildren();
    task.append(element("h3", "", session.title || "현재 협업"), element("p", "overview-summary", session.task?.description || session.description || ""), element("p", "overview-detector", session.detector?.reason || "아직 대화가 없습니다."));
    const detailButton = element("button", "button secondary", "지식 관계 확인하기 →"); detailButton.type = "button"; detailButton.addEventListener("click", () => switchTab($("knowledge-tab"))); task.append(detailButton);
  }

  function renderDecisionInbox(session) {
    const filter = $("request-filter").value;
    const coveredIds = new Set(coveredRequests(session).map((request) => request.id));
    const remainingIds = new Set(remainingRequests(session).map((request) => request.id));
    const requests = array(session.requests).filter((request) => filter === "all" || (filter === "pending" ? remainingIds.has(request.id) : request.status === "resolved" || coveredIds.has(request.id)));
    const rows = pageRows(requests, "requests", 5);
    let selected = rows.find((request) => request.id === state.activeDecisionId);
    if (!selected) selected = rows.find((request) => remainingIds.has(request.id)) || rows[0];
    state.activeDecisionId = selected?.id || null;
    const target = $("request-list"); target.replaceChildren();
    rows.forEach((request) => {
      const button = element("button", `request-item${request.id === selected?.id ? " active" : ""}`); button.type = "button";
      button.setAttribute("aria-pressed", String(request.id === selected?.id));
      button.append(element("span", "request-item-status", coveredIds.has(request.id) ? "현재 권한 기록으로 해소" : request.status === "pending" ? "결정 대기" : "결정 기록"), element("strong", "", request.title || request.question), element("span", "request-item-meta", `${request.created_turn ?? "—"}턴 · ${request.kind || "결정 요청"}`));
      button.addEventListener("click", () => { state.activeDecisionId = request.id; renderDecisionInbox(state.selected); controls(); }); target.append(button);
    });
    if (!rows.length) target.append(element("p", "inbox-empty", filter === "resolved" ? "아직 기록한 결정이 없습니다." : "표시할 결정 요청이 없습니다."));
    pagination("request-pagination", "requests", requests.length, 5, () => { state.activeDecisionId = null; renderDecisionInbox(state.selected); controls(); });
    renderDecision(session, selected);
  }

  function renderDecision(session, request) {
    const target = $("decision-content");
    const panel = target.closest(".decision-panel");
    const covered = coveredRequests(session).find((item) => item.id === request?.id);
    panel.classList.toggle("has-request", request?.status === "pending" && !covered);
    const requestKey = request ? `${session.id}:${request.id}:${request.status}:${covered ? JSON.stringify(covered.covered_by_authority) : ""}` : null;
    if (request && state.requestId === requestKey) return;
    state.requestId = requestKey;
    target.replaceChildren();
    if (!request) {
      const empty = element("div", "empty-state decision-empty");
      const finished = session.status === "completed";
      const recorded = session.mode === "import" && array(session.decisions).length > 0;
      empty.append(element("span", "orbit-symbol", finished || recorded ? "✓" : "◎"), element("h3", "", recorded ? "판단과 다음 행동을 기록했습니다" : finished ? "협업이 완료됐습니다" : "지금은 지켜봐도 괜찮아요"), element("p", "", recorded ? "담당자가 다음 행동을 수행해야 합니다. 외부 서비스에는 아직 전달하지 않았습니다." : finished ? "대화 기록과 연결된 근거에서 결과를 확인하세요." : "반복되는 주장이나 지식 충돌로 진행이 멈추면 판단을 요청합니다."));
      const process = element("div", "process-labels");
      (session.mode === "import" ? ["근거 확인", "→", "결정 기록", "→", "다음 행동"] : ["충돌 확인", "→", "판단 요청", "→", "협업 재개"]).forEach((label, index) => process.append(element(index % 2 ? "b" : "span", "", label)));
      empty.append(process);
      target.append(empty);
      const decisions = array(session.decisions);
      if (decisions.length) {
        const last = decisions[decisions.length - 1];
        target.append(element("p", "decision-resolved", `최근 반영된 결정 · ${last.label || last.choice_label || last.choice || last.note || "결정이 기록되었습니다."}`));
      }
      return;
    }
    if (covered) {
      const authority = covered.covered_by_authority || {};
      const record = element("article", "decision-active authority-covered-record");
      record.append(element("p", "decision-kind", "현재 권한 기록으로 해소"), element("h3", "decision-title", request.title || "권한 확인 요청"), element("p", "decision-summary", request.question || request.summary || ""));
      record.append(element("h3", "", `${authority.scope || "범위 확인"} / ${authority.action || "행동 확인"}`), element("p", "decision-record-note", `결정 담당 에이전트: ${authority.decision_owner || "확인 안 됨"}`), element("p", "decision-footnote", "현재 유효한 위임과 우선권으로 답할 수 있어 같은 승인을 다시 요청하지 않습니다. 원래 질문의 저장 상태와 사람 결정 이력은 그대로 보존합니다. 외부 전달·실행 완료를 뜻하지 않습니다."));
      const button = element("button", "precedence-button", "권한 판정 보기"); button.type = "button"; button.addEventListener("click", () => { switchTab($("overview-tab")); $("authority-check-panel").scrollIntoView({ block: "start" }); }); record.append(button); target.append(record); return;
    }
    if (request.status !== "pending") {
      const decision = array(session.decisions).find((item) => item.request_id === request.id);
      const record = element("article", "decision-active decision-record");
      record.append(element("p", "decision-kind", "결정 기록"), element("h3", "decision-title", request.title), element("p", "decision-summary", request.summary));
      const chosen = array(request.options).find((option) => option.id === decision?.choice);
      record.append(element("h3", "", chosen?.label || decision?.choice || "선택 기록 없음"), element("p", "decision-record-note", decision?.note || "추가 메모 없음"));
      if (request.evidence_ids?.length) record.append(element("p", "decision-sources", `연결된 근거: ${request.evidence_ids.join(", ")}`));
      if (session.mode === "import") record.append(element("p", "decision-footnote", "이 세션에 기록한 판단입니다. 외부 전달이나 실행 완료를 의미하지 않습니다."));
      target.append(record); return;
    }
    const form = element("form", "decision-active");
    form.append(element("p", "decision-kind", `${request.kind || "결정 요청"} · ${request.created_turn ?? session.turn}턴에서 감지`), element("h3", "decision-title", request.title || "판단이 필요합니다"), element("p", "decision-summary", request.summary || ""));
    if (request.evidence_ids?.length) {
      const sources = element("div", "decision-sources");
      sources.append(element("p", "", "연결된 근거"));
      request.evidence_ids.forEach((id) => {
        const evidence = array(session.evidence).find((item) => item.id === id);
        sources.append(element("p", "", `${id}${evidence ? ` · ${evidence.summary || evidence.source || ""}` : ""}`));
      });
      form.append(sources);
    }
    form.append(element("p", "decision-question", request.question || "다음 진행에 필요한 기준을 선택해 주세요."));
    const choices = element("fieldset", "choice-list");
    choices.append(element("legend", "sr-only", "결정 선택지"));
    array(request.options).forEach((option, index) => {
      const label = element("label", "choice-card");
      const input = document.createElement("input");
      input.type = "radio"; input.name = "choice"; input.value = option.id; input.required = true;
      input.id = `choice-${index}`;
      const copy = element("span", "choice-copy");
      copy.append(element("span", "choice-title", option.label || option.id));
      if (option.description) copy.append(element("span", "choice-description", option.description));
      label.append(input, copy); choices.append(label);
    });
    form.append(choices);
    const noteLabel = element("label", "decision-note-label", session.mode === "import" ? "담당자, 근거 또는 다음 행동 (필수)" : "추가 기준이나 이유 (선택)"); noteLabel.htmlFor = "decision-note";
    const note = element("textarea", "decision-note"); note.id = "decision-note"; note.name = "note"; note.maxLength = 4000; note.placeholder = "에이전트에게 전달할 판단 근거를 적어 주세요.";
    if (session.mode === "import") { note.required = true; note.placeholder = "예: 민수가 본인 일정 확인 후 내일 오전까지 답변. 다른 요청은 보류."; }
    const submit = element("button", "button decision-submit", "결정 반영하기 →"); submit.id = "decision-submit"; submit.type = "submit";
    form.append(noteLabel, note, submit, element("p", "decision-footnote", session.mode === "import" ? "결정을 이 세션에 기록합니다. 외부에 전달하지 않습니다." : "결정과 근거를 공유 지식에 기록합니다."));
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const choice = data.get("choice");
      if (!choice) return;
      mutate("/decisions", { request_id: request.id, choice, note: data.get("note") || "" }, session.mode === "import" ? "결정을 이 세션에 기록했습니다." : "결정을 반영했습니다. 이어서 실행할 수 있습니다.");
    });
    target.append(form);
    announce(`판단이 필요합니다. ${request.title || request.question}`);
  }

  function renderRecords(session) {
    const claims = array(session.claims);
    const evidence = array(session.evidence);
    $("claims-count").textContent = String(claims.length);
    $("evidence-count").textContent = String(evidence.length);
    pagination("claim-pagination", "claims", claims.length, 8, () => renderRecords(state.selected));
    pagination("evidence-pagination", "evidence", evidence.length, 8, () => renderRecords(state.selected));
    const claimTarget = $("claims-list"); claimTarget.replaceChildren();
    pageRows(claims, "claims", 8).forEach((claim) => {
      const card = element("article", "record-card");
      card.append(element("p", "record-title", `${claim.key || claim.subject || claim.id || "주장"} = ${text(claim.value ?? claim.object ?? claim.content)}`));
      card.append(element("p", "record-body", `종류: ${claim.kind || claim.type || "미지정"} · 범위: ${text(claim.scope || "공통")}`));
      card.append(element("p", "record-meta", [claim.id, claim.agent || claim.author, claim.turn != null ? `${claim.turn}턴` : null].filter(Boolean).join(" · ")));
      claimTarget.append(card);
    });
    if (!claims.length) claimTarget.append(element("p", "muted small", "아직 기록된 주장이 없습니다."));
    const evidenceTarget = $("evidence-list"); evidenceTarget.replaceChildren();
    pageRows(evidence, "evidence", 8).forEach((item) => {
      const card = element("article", "record-card");
      card.append(element("p", "record-title", item.summary || item.label || item.id || "근거"));
      card.append(element("p", "record-body", `출처: ${text(item.source)}`));
      card.append(element("p", "record-meta", [item.id, item.agent || item.author].filter(Boolean).join(" · ")));
      evidenceTarget.append(card);
    });
    if (!evidence.length) evidenceTarget.append(element("p", "muted small", "아직 기록된 근거가 없습니다."));
    const artifact = $("artifact-container");
    artifact.replaceChildren(); artifact.hidden = !session.artifact || !Object.keys(session.artifact).length;
    if (!artifact.hidden) artifact.append(element("h3", "", "현재 산출물"), element("pre", "", typeof session.artifact === "string" ? session.artifact : JSON.stringify(session.artifact, null, 2)));
  }

  function renderCoordination(session) {
    const coordination = session.coordination;
    const panel = $("coordination-panel");
    panel.hidden = !coordination;
    if (!coordination) return;
    $("coordination-summary").textContent = coordination.summary || "약속, 전달 확인, 응답 대기, 결정 담당자를 확인합니다.";
    const target = $("coordination-content"); target.replaceChildren();
    const statusLabels = { promised: "확인 약속", promise: "확인 약속", requested: "요청 전달 확인", delivered: "요청 전달 확인", delivery_unknown: "전달 상태 미확인", human_reported_delivered: "전달 확인 · 사람의 보고", waiting: "응답 대기", unassigned: "결정권자 없음", unknown: "전달 미확인", resolved: "결정 기록됨", pending: "응답 대기", no_owner: "결정권자 없음", handoff_unverified: "요청 전달 미확인", circular_wait: "서로 응답 대기", recorded: "다음 행동 기록됨", authority: "결정권자 확인 필요", handoff: "요청 전달 여부 확인", coordination: "대기 관계 확인" };
    if (coordination.delivery_status === "human_reported_delivered") {
      const delivery = element("article", "coordination-card");
      delivery.append(element("span", "coordination-label", "전달 확인 · 사람의 보고"), element("h3", "", "이미 전달한 요청입니다"), element("p", "", "사람이 전달 사실을 확인했습니다. 외부 시스템의 전달 영수증과는 구분해 기록합니다."));
      target.append(delivery);
    }
    const groups = [["issues", "확인할 문제", "is-issue"], ["next_actions", "다음 행동", ""], ["commitments", "확인 약속", ""], ["waits", "응답 대기", ""]];
    groups.forEach(([key, fallback, className]) => array(coordination[key]).forEach((item) => {
      if (target.childNodes.length >= 3) return;
      const card = element("article", `coordination-card ${className}`);
      if (typeof item !== "object" || item === null) { card.append(element("h3", "", fallback), element("p", "", text(item))); target.append(card); return; }
      const resolved = key === "issues" && array(session.requests).some((request) => request.id === `request-${item.id}` && request.status === "resolved");
      const status = resolved ? "resolved" : item.status || item.kind || item.type;
      card.append(element("span", "coordination-label", statusLabels[status] || fallback));
      card.append(element("h3", "", item.title || item.summary || item.agent || item.owner || fallback));
      const detail = item.description || item.detail || item.reason || item.content || item.text || item.action || (item.title ? item.summary : null);
      if (detail) card.append(element("p", "", text(detail)));
      const references = [];
      if (item.from || item.actor) references.push(`요청: ${text(item.from || item.actor)}`);
      if (item.to || item.waiting_for) references.push(`대기 대상: ${text(item.to || item.waiting_for)}`);
      if (item.owner) references.push(`담당: ${text(item.owner)}`);
      if (item.evidence_ids?.length) references.push(`근거: ${item.evidence_ids.join(", ")}`);
      else if (item.message_ids?.length) references.push(`대화 근거: ${item.message_ids.join(", ")}`);
      else if (item.message_id) references.push(`대화 근거: ${item.message_id}`);
      if (references.length) card.append(element("p", "", references.join(" · ")));
      if (!detail && !references.length) {
        const remaining = Object.entries(item).filter(([name, value]) => !["id", "title", "summary", "status", "kind", "type"].includes(name) && value !== null && value !== undefined);
        if (remaining.length) card.append(element("p", "", remaining.map(([name, value]) => `${name}: ${text(value)}`).join("\n")));
      }
      target.append(card);
    }));
    if (!target.childNodes.length) target.append(element("p", "muted small", "현재 확인된 대기 관계나 전달 문제는 없습니다."));
  }

  function svgElement(tag, attributes = {}, content) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (content !== undefined) node.textContent = String(content);
    return node;
  }

  function renderGraph(graph) {
    const nodes = array(graph?.nodes); const edges = array(graph?.edges);
    const container = $("graph-container"); container.replaceChildren();
    const nodeList = $("graph-node-list"); nodeList.replaceChildren();
    const edgeList = $("graph-edge-list"); edgeList.replaceChildren();
    $("graph-count").textContent = `${nodes.length}개 노드 · ${edges.length}개 관계`;
    const allNodes = new Map(nodes.map((node) => [String(node.id), node]));
    pagination("node-pagination", "nodes", nodes.length, 8, () => renderGraph(state.graph));
    pagination("edge-pagination", "edges", edges.length, 8, () => renderGraph(state.graph));
    pageRows(nodes, "nodes", 8).forEach((node) => nodeList.append(element("li", "", `${typeNames[String(node.type || node.kind).toLowerCase()] || node.type || "개념"} · ${node.label || node.id} (${node.id})`)));
    pageRows(edges, "edges", 8).forEach((edge) => edgeList.append(element("li", "", `${allNodes.get(String(edge.source))?.label || edge.source} → ${edge.label || edge.type || edge.relation || "연결"} → ${allNodes.get(String(edge.target))?.label || edge.target}`)));
    if (!nodes.length) { container.append(element("p", "graph-empty", "대화가 시작되면 주장과 근거 사이의 관계가 표시됩니다.")); return; }
    const normalizedType = (node) => String(node.type || node.kind || "concept").toLowerCase();
    const typeLabel = (node) => typeNames[normalizedType(node)] || node.type || "개념";
    const columns = [[], [], [], []];
    nodes.slice(-32).forEach((node) => {
      const type = normalizedType(node);
      const column = ["agent", "task"].includes(type) ? 0 : ["claim", "concept", "commitment"].includes(type) ? 1 : ["evidence", "artifact"].includes(type) ? 2 : 3;
      columns[column].push(node);
    });
    const height = Math.max(220, Math.min(600, Math.max(...columns.map((items) => items.length)) * 64 + 36));
    const width = 920;
    const locations = new Map();
    columns.forEach((items, column) => items.forEach((node, index) => locations.set(String(node.id), { x: 115 + column * 230, y: (index + 1) * height / (items.length + 1) })));
    const svg = svgElement("svg", { viewBox: `0 0 ${width} ${height}`, class: "knowledge-svg", role: "img", "aria-label": `지식 관계 지도. ${nodes.length}개 노드와 ${edges.length}개 관계. 아래 관계 목록으로도 확인할 수 있습니다.` });
    const edgeLayer = svgElement("g");
    edges.forEach((edge) => {
      const source = locations.get(String(edge.source)); const target = locations.get(String(edge.target));
      if (!source || !target) return;
      const mid = (source.x + target.x) / 2;
      const path = svgElement("path", { d: `M ${source.x} ${source.y} C ${mid} ${source.y}, ${mid} ${target.y}, ${target.x} ${target.y}`, class: "graph-edge" });
      path.append(svgElement("title", {}, `${edge.label || edge.type || edge.relation || "연결"}`));
      edgeLayer.append(path);
    });
    svg.append(edgeLayer);
    columns.flat().forEach((node) => {
      const point = locations.get(String(node.id));
      const type = normalizedType(node);
      const emphasis = ["conflict", "decision", "request", "humaninputrequest", "intervention"].includes(type);
      const group = svgElement("g", { transform: `translate(${point.x}, ${point.y})` });
      group.append(svgElement("title", {}, `${typeLabel(node)} · ${node.label || node.id}`));
      group.append(svgElement("rect", { x: -91, y: -23, width: 182, height: 46, rx: 12, fill: emphasis ? "#171717" : "#ffffff", stroke: emphasis ? "#171717" : "#d4d4d4" }));
      const label = String(node.label || node.id);
      group.append(svgElement("text", { x: 0, y: -4, "text-anchor": "middle", class: `graph-node-label${emphasis ? " inverse" : ""}` }, label.length > 17 ? `${label.slice(0, 16)}…` : label));
      group.append(svgElement("text", { x: 0, y: 12, "text-anchor": "middle", class: `graph-node-type${emphasis ? " inverse" : ""}` }, typeLabel(node)));
      svg.append(group);
    });
    container.append(svg);
    if (nodes.length > 32) container.append(element("p", "graph-limit", "지도는 최근 32개 노드를 표시합니다. 전체 연결은 아래 목록에서 확인하세요."));
  }

  function render(session) {
    state.selected = session;
    $("active-session-title").textContent = session.title || session.scenario_id;
    $("session-status").textContent = sessionStatusLabel(session);
    $("session-status").className = `status-badge ${Object.hasOwn(labels, session.status) ? session.status : "neutral"}`;
    $("policy-label").textContent = session.mode === "import" ? "가져온 대화 분석" : policyNames[session.policy] || session.policy;
    const notice = $("mode-notice"); notice.className = `mode-notice ${session.mode === "demo" ? "is-demo" : "is-real"}`;
    notice.querySelector("p").textContent = session.mode === "demo" ? "시연 모드 · 미리 구성한 대화로 감지와 결정 흐름을 확인합니다. 실제 모델 성능이나 토큰 절감의 증거가 아닙니다." : session.mode === "import" ? "가져온 대화 · 붙여 넣은 기록에서 약속과 대기 관계를 분석합니다. 이 화면의 결정은 Pickle이나 Slack에 전송되지 않습니다." : "실제 에이전트 실행 · 에이전트가 생성한 대화와 보고된 사용량을 기록합니다. 토큰이 보고되지 않은 호출은 미측정으로 표시합니다.";
    if (visitorDemo() && session.demo?.synthetic) notice.querySelector("p").textContent = [session.demo.notice, session.demo.seed_notice].filter(Boolean).join(" ") || "익명 합성 대화와 기록된 모델 분석으로 권한 충돌을 체험합니다. 외부 작업은 실행하지 않습니다.";
    $("detector-label").textContent = session.detector?.reason || (session.busy ? "다음 에이전트의 응답을 기다리고 있습니다" : "대화와 지식 상태를 관찰하고 있습니다");
    $("stalled-label").textContent = session.detector?.stalled_turns ? `${session.detector.stalled_turns}턴 동안 진행 변화 없음` : "";
    $("session-id-label").textContent = `SESSION ${session.id}`;
    if (session.status === "error" && session.last_error) showError(new Error(session.last_error));
    ["json", "markdown"].forEach((format) => {
      const link = $(`export-${format}`); link.href = endpoint(`/export?format=${format}`); link.classList.remove("disabled-link"); link.removeAttribute("aria-disabled");
    });
    renderMetrics(session); renderOverview(session); renderBrief(); renderConversation(session); renderDecisionInbox(session); renderRecords(session); renderCoordination(session); updateSessionSummary(session); controls();
  }

  function schedulePoll() {
    clearTimeout(state.timer);
    if (state.selected?.busy || state.selected?.mode === "import") state.timer = setTimeout(poll, state.selected.busy ? 1000 : visitorDemo() ? 5000 : 2000);
  }

  async function fetchGraph(id, selection) {
    try {
      const graph = await api(`/api/sessions/${encodeURIComponent(id)}/graph`);
      if (state.selected?.id === id && state.selection === selection) { state.graph = graph; renderGraph(graph); }
    } catch (error) { if (state.selection === selection) showError(error); }
  }

  async function poll() {
    if (state.mutation || state.authorityBusy || state.authorityLoading || !state.selected) { schedulePoll(); return; }
    const id = state.selected.id; const selection = state.selection;
    try {
      const session = await api(`/api/sessions/${encodeURIComponent(id)}`);
      if (state.selection !== selection) return;
      render(session);
      await fetchGraph(id, selection);
      await refreshBrief();
    } catch (error) { if (state.selection === selection) showError(error); }
    schedulePoll();
  }

  async function selectSession(id) {
    if (state.mutation) return;
    clearTimeout(state.timer);
    const selection = ++state.selection;
    try {
      const session = await api(`/api/sessions/${encodeURIComponent(id)}`);
      if (selection !== state.selection) return;
      resetSessionViews(session); render(session);
      try { localStorage.setItem("arbiter-session", id); } catch { /* Storage is optional. */ }
      await fetchGraph(id, selection);
      await refreshBrief();
      schedulePoll();
    } catch (error) { showError(error); }
  }

  async function mutate(suffix, body, announcement) {
    if (state.mutation || !state.selected) return;
    state.mutation = true; clearTimeout(state.timer); controls();
    const selection = state.selection;
    try {
      $("error-banner").hidden = true;
      const session = await api(endpoint(suffix), body || {});
      if (selection !== state.selection) return;
      render(session);
      if (announcement) announce(announcement);
      await fetchGraph(session.id, selection);
      await refreshBrief();
    } catch (error) { showError(error); }
    finally { state.mutation = false; controls(); schedulePoll(); }
  }

  async function createSession(event) {
    event.preventDefault();
    if (state.mutation || !state.config) return;
    const provider = state.config.providers.find((item) => item.id === $("mode-select").value);
    if (!provider || provider.available === false || (visitorDemo() && provider.id !== "demo")) return;
    state.mutation = true; clearTimeout(state.timer); controls();
    const selection = ++state.selection;
    try {
      $("error-banner").hidden = true;
      const session = await api("/api/sessions", { scenario_id: $("scenario-select").value, policy: $("policy-select").value, mode: $("mode-select").value, max_turns: 18 });
      resetSessionViews(session); state.pages.sessions = 1; render(session); switchTab($("overview-tab"));
      try { localStorage.setItem("arbiter-session", session.id); } catch { /* Storage is optional. */ }
      await fetchGraph(session.id, selection);
      await refreshBrief();
      announce("새 협업 세션을 만들었습니다.");
    } catch (error) { showError(error); }
    finally { state.mutation = false; controls(); schedulePoll(); }
  }

  async function importTranscript(event) {
    event.preventDefault();
    if (state.mutation || !state.config) return;
    const transcript = $("intake-transcript").value.trim();
    if (!transcript) return;
    state.mutation = true; clearTimeout(state.timer); controls();
    $("intake-submit").disabled = true; $("intake-submit").classList.add("loading"); $("intake-error").hidden = true;
    const selection = ++state.selection;
    try {
      const session = await api("/api/intake", { transcript, title: $("intake-title").value.trim() || "가져온 협업 대화", source: $("intake-source").value });
      resetSessionViews(session); state.pages.sessions = 1; render(session); switchTab($("overview-tab"));
      await fetchGraph(session.id, selection);
      await refreshBrief();
      try { localStorage.setItem("arbiter-session", session.id); } catch { /* Storage is optional. */ }
      $("intake-dialog").close();
      announce("가져온 대화에서 대기 관계와 결정 지점을 분석했습니다.");
    } catch (error) { $("intake-error").textContent = error.message; $("intake-error").hidden = false; }
    finally { state.mutation = false; $("intake-submit").disabled = false; $("intake-submit").classList.remove("loading"); controls(); schedulePoll(); }
  }

  async function loadExperiments() {
    if (!state.config || state.resetting) return;
    const target = $("experiment-content");
    $("refresh-experiments").disabled = true;
    try {
      const data = await api("/api/experiments");
      target.replaceChildren();
      if (data.available === false) { target.append(element("p", "experiment-empty", data.message || "아직 저장된 실험 결과가 없습니다. 실험을 실행하면 정책별 측정 결과를 확인할 수 있습니다.")); return; }
      const policies = data.policies || {};
      const rows = ["capped", "periodic", "adaptive"].filter((policy) => policies[policy]).map((policy) => ({ policy, ...policies[policy] }));
      target.append(element("p", "experiment-study", data.study_type || "저장된 실험 결과"));
      if (data.design?.real_model_calls === false) target.append(element("p", "experiment-meta", "정해진 대화와 자동 응답으로 수행한 통제 시뮬레이션입니다. 실제 LLM·사람 실험이나 토큰 절감의 증거가 아닙니다."));
      if (rows.length) {
        const columns = [
          ["개입 정책", (row) => policyNames[row.policy]],
          ["성공 / 실행", (row) => `${row.successes ?? "—"} / ${row.runs ?? "—"}`],
          ["성공률", (row) => typeof row.success_rate === "number" ? `${(row.success_rate * 100).toFixed(1)}%` : "미측정"],
          ["결과 미확인", (row) => text(row.unknown_outcomes)],
          ["평균 대화", (row) => typeof row.mean_turns_all_runs === "number" ? `${row.mean_turns_all_runs.toFixed(2)}턴` : "미측정"],
          ["전체 개입 요청", (row) => text(row.total_human_requests)],
          ["평균 개입 요청", (row) => typeof row.mean_human_requests === "number" ? row.mean_human_requests.toFixed(3) : "미측정"],
          ["측정된 토큰", (row) => row.input_tokens == null || row.output_tokens == null ? "미측정" : number(row.input_tokens + row.output_tokens)],
        ];
        const wrapper = element("div", "experiment-table-wrap"); const table = element("table", "experiment-table");
        const caption = element("caption", "sr-only", "세 가지 개입 정책의 실험 결과"); const head = element("thead"); const heading = element("tr");
        columns.forEach(([label]) => { const th = element("th", "", label); th.scope = "col"; heading.append(th); }); head.append(heading);
        const body = element("tbody"); rows.forEach((row) => { const tr = element("tr"); tr.dataset.policy = row.policy; columns.forEach(([, value]) => tr.append(element("td", "", value(row)))); body.append(tr); });
        table.append(caption, head, body); wrapper.append(table); target.append(wrapper);
        target.append(element("p", "experiment-meta", `성공은 로컬 산출물의 체크리스트 충족 기준입니다. 총 ${data.assigned_run_count ?? rows.reduce((total, row) => total + Number(row.runs || 0), 0)}회 실행 · 평균 대화는 모든 실행을 포함합니다.`));
      } else target.append(element("p", "experiment-empty", "정책별 집계가 없습니다. 원본 기록을 확인하세요."));
      const details = element("details", "graph-details"); details.append(element("summary", "", "원본 실험 기록 보기"), element("pre", "experiment-raw", JSON.stringify(data, null, 2))); target.append(details);
    } catch (error) { target.replaceChildren(element("p", "experiment-empty", `결과를 불러오지 못했습니다. ${error.message}`)); }
    finally { $("refresh-experiments").disabled = false; }
  }

  async function loadIntegration() {
    if (!state.config || state.resetting) return;
    const target = $("integration-content"); $("refresh-integration").disabled = true;
    try {
      if (visitorDemo()) {
        target.replaceChildren();
        const section = element("section", "integration-section");
        section.append(element("h3", "", "실제 연결은 자신의 환경에서"), element("p", "integration-description", "이곳에서는 방문자별 예시 대화와 권한 기록만 체험합니다. 소스를 설치한 환경에서 MCP·A2A 설정과 Slack 수신을 구성하면 실제 에이전트의 대화를 연결할 수 있습니다."));
        const link = element("a", "source-install-link", "GitHub 소스와 설치 안내 →"); link.href = "https://github.com/Ontology0/hanium-arbiter";
        section.append(link, element("p", "integration-description", "연결할 에이전트 앱에 자신의 설치 환경에서 제공되는 MCP 설정을 추가하세요. 이 체험의 URL이나 예시 권한을 실제 연결 설정으로 사용하지 마세요."));
        target.append(section); return;
      }
      const data = await api("/api/integration"); target.replaceChildren();
      const mcp = data.mcp || {};
      target.append(element("p", "integration-description", "현재 사용하는 에이전트 앱의 MCP 서버 설정에 아래 구성을 추가하세요. 에이전트 코드를 수정할 필요 없이 제공된 도구를 호출하는 방식입니다."));
      const block = (heading, value) => {
        if (!value) return;
        const section = element("section", "integration-section"); const bar = element("div", "section-heading"); bar.append(element("h3", "", heading));
        const formatted = typeof value === "string" ? value : JSON.stringify(value, null, 2);
        const copy = element("button", "button secondary", "복사"); copy.type = "button";
        copy.addEventListener("click", async () => { try { await navigator.clipboard.writeText(formatted); copy.textContent = "복사됨"; } catch { announce("자동 복사가 지원되지 않습니다. 아래 설정 내용을 직접 선택해 복사하세요."); } });
        bar.append(copy); section.append(bar, element("pre", "integration-code", formatted)); target.append(section);
      };
      if (data.slack) {
        const slack = data.slack;
        const statuses = { not_configured: "미설정", unconfigured: "미설정", configured: "설정됨", disconnected: "연결 안 됨", stopped: "수신 중지", listening: "대화 수신 대기", connected: "수신 연결됨", events_received: "이벤트 수신 이력 있음", awaiting_events: "수신 이벤트 없음", error: "연결 오류" };
        const section = element("section", "integration-section slack-section"); section.id = "slack-integration";
        section.append(element("h3", "", "Slack · 첫 번째 대화 연결"), element("p", "integration-description", "허용한 채널의 대화를 수신해 협업 세션으로 기록합니다. 실제 연결·수신 상태는 아래에서 확인하세요."));
        const details = element("dl", "slack-details");
        const fields = [
          ["수신 상태", statuses[slack.status] || slack.status || "확인 안 됨"],
          ["설정", slack.configured === true ? "필수 설정 있음" : slack.configured === false ? "설정 필요" : "확인 안 됨"],
          ["허용 채널", array(slack.allowed_channels).length ? array(slack.allowed_channels).map(text).join(", ") : "허용 채널 미설정"],
          ["수신 이벤트", slack.received_events == null ? "확인 안 됨" : `${number(slack.received_events)}건`],
          ["마지막 수신", slack.last_received_at || "수신 기록 없음"],
        ];
        fields.forEach(([label, value]) => details.append(element("dt", "", label), element("dd", "", value))); section.append(details);
        if (slack.setup_url) {
          try {
            const url = new URL(slack.setup_url, location.origin);
            if (url.origin === location.origin && (url.pathname.startsWith("/static/") || url.pathname === "/api/integration/slack-manifest")) {
              const link = element("a", "button secondary", "Slack 앱 설정 파일 받기 ↓"); link.href = url.href; link.download = "slack-app-manifest.json"; section.append(link);
            }
          } catch { /* Do not create invalid setup links. */ }
        }
        if (slack.limitations?.length) { const list = element("ul", "integration-limitations"); slack.limitations.forEach((item) => list.append(element("li", "", text(item)))); section.append(list); }
        target.append(section);
        block("Slack 수신 실행 명령", slack.command);
      }
      block("MCP 서버 설정", mcp.config);
      block("로컬 실행 명령", mcp.stdio_command);
      block("Streamable HTTP 주소", mcp.streamable_http_url);
      block("로컬 API 주소", data.api_base);
      const tools = array(mcp.tools);
      if (tools.length) {
        const section = element("section", "integration-section"); section.append(element("h3", "", `사용할 수 있는 도구 ${tools.length}개`)); const list = element("ul", "integration-tools");
        tools.forEach((tool) => list.append(element("li", "", typeof tool === "string" ? tool : `${tool.name || tool.id || tool.key}${tool.description ? ` · ${tool.description}` : ""}`))); section.append(list); target.append(section);
      }
      if (data.limitations?.length) { const list = element("ul", "integration-limitations"); data.limitations.forEach((item) => list.append(element("li", "", text(item)))); target.append(list); }
    } catch (error) { target.replaceChildren(element("p", "experiment-empty", `연결 설정을 불러오지 못했습니다. ${error.message}`)); }
    finally { $("refresh-integration").disabled = false; }
  }

  function switchTab(tab, updateHash = true) {
    const group = tab.closest('[role="tablist"]');
    group.querySelectorAll('[role="tab"]').forEach((item) => {
      const active = item === tab; item.classList.toggle("active", active); item.setAttribute("aria-selected", String(active)); item.tabIndex = active ? 0 : -1; $(item.getAttribute("aria-controls")).hidden = !active;
    });
    if (group.id === "workspace-tabs" && updateHash) history.replaceState(null, "", `#${tab.id.replace(/-tab$/, "")}`);
    if (tab.id === "experiments-tab") loadExperiments();
    if (tab.id === "integration-tab") loadIntegration();
    if (tab.id === "knowledge-tab") loadAuthority();
  }

  function applyHash() {
    const name = location.hash.slice(1);
    const allowed = ["overview", "conversation", "decisions", "knowledge", "experiments", "integration"];
    if (allowed.includes(name)) switchTab($(`${name}-tab`), false);
  }

  async function initialize() {
    controls(); authorityControls(); renderBrief();
    $("open-intake").addEventListener("click", () => { $("intake-dialog").showModal(); $("intake-transcript").focus(); });
    $("close-intake").addEventListener("click", () => { if (!state.mutation) $("intake-dialog").close(); });
    $("intake-dialog").addEventListener("cancel", (event) => { if (state.mutation) event.preventDefault(); });
    $("intake-form").addEventListener("submit", importTranscript);
    $("session-form").addEventListener("submit", createSession);
    $("scenario-select").addEventListener("change", updateFormDescription);
    $("mode-select").addEventListener("change", updateFormDescription);
    $("step-button").addEventListener("click", () => mutate("/step", {}));
    $("run-button").addEventListener("click", () => mutate("/run", {}));
    $("stop-button").addEventListener("click", () => mutate("/stop", {}, "중지를 요청했습니다."));
    $("dismiss-error").addEventListener("click", () => { $("error-banner").hidden = true; });
    $("refresh-sessions").addEventListener("click", () => refreshSessions().catch(showError));
    $("refresh-experiments").addEventListener("click", loadExperiments);
    $("refresh-integration").addEventListener("click", loadIntegration);
    $("reset-demo").addEventListener("click", resetDemo);
    $("generate-brief").addEventListener("click", generateBrief);
    $("refresh-authority").addEventListener("click", loadAuthority);
    $("authority-form").addEventListener("submit", createGrant);
    $("open-authority").addEventListener("click", () => switchTab($("knowledge-tab")));
    $("request-filter").addEventListener("change", () => { state.pages.requests = 1; state.activeDecisionId = null; if (state.selected) { renderDecisionInbox(state.selected); controls(); } });
    $("latest-messages").addEventListener("click", () => {
      if (!state.selected) return;
      const count = array(state.selected.messages).length;
      state.pages.messages = Math.max(1, Math.ceil(count / 10)); state.messageSeen = count;
      renderConversation(state.selected);
    });
    document.querySelectorAll('[role="tablist"]').forEach((group) => {
      const tabs = [...group.querySelectorAll('[role="tab"]')];
      tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => switchTab(tab));
        tab.addEventListener("keydown", (event) => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
          tabs[next].focus(); switchTab(tabs[next]);
        });
      });
    });
    window.addEventListener("hashchange", applyHash);
    // Establish the visitor cookie before parallel requests read visitor-owned records.
    try {
      state.config = await api("/api/config");
      state.config.scenarios = array(state.config.scenarios); state.config.policies = array(state.config.policies);
      state.config.providers = array(state.config.providers).map((provider) => visitorDemo() && provider.id !== "demo" ? { ...provider, available: false, label: `${provider.label || provider.id} · 체험에서 사용 불가` } : provider);
      applyDeployment();
      setOptions($("scenario-select"), state.config.scenarios);
      setOptions($("policy-select"), state.config.policies, "adaptive");
      setOptions($("mode-select"), state.config.providers, "demo");
      updateFormDescription(); controls(); authorityControls(); renderBrief();
    } catch (error) { showError(error); return; }
    const results = await Promise.allSettled([refreshSessions(), loadExperiments(), loadAuthority()]);
    if (results[0].status === "rejected") showError(results[0].reason);
    applyHash();
    let saved; try { saved = localStorage.getItem("arbiter-session"); } catch { /* Storage is optional. */ }
    const initial = state.sessions.find((item) => item.id === saved) || state.sessions[0];
    if (initial) await selectSession(initial.id);
  }

  initialize().catch(showError);
})();
