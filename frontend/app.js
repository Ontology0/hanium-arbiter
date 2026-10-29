"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const number = (value) => Number(value || 0).toLocaleString("en-US");
  const labels = { running: "Running", waiting: "Waiting for a human", completed: "Completed", budget_exhausted: "Turn limit reached", stopped: "Paused", error: "Execution error" };
  const policyNames = { adaptive: "Conflict / stall intervention", periodic: "Periodic intervention", capped: "Fixed turn limit" };
  const typeNames = { agent: "Agent", claim: "Claim", evidence: "Evidence", conflict: "Conflict", request: "Intervention request", humaninputrequest: "Intervention request", commitment: "Commitment", intervention: "Intervention request", decision: "Decision", artifact: "Output", task: "Task", concept: "Concept" };
  const state = { config: null, sessions: [], selected: null, graph: null, mutation: false, timer: null, selection: 0, requestId: null, messagesKey: null,
    activeDecisionId: null, messageSeen: 0, briefState: null, briefTimer: null, briefPosting: false, briefFetching: false, briefVersion: 0, authorityAliases: null,
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

  // Legacy sample IDs remain unchanged in requests and saved authority records.
  // Only identity labels use the explicit aliases supplied for this demo session.
  function identityLabel(value, group) {
    const aliases = state.selected?.demo?.synthetic ? state.selected.demo.display_aliases : null;
    return aliasedIdentity(value, group, aliases);
  }

  function authorityLabel(value, group) {
    return aliasedIdentity(value, group, state.authorityAliases);
  }

  function authorityInstruction(value) {
    let result = text(value);
    // Used only for rule-generated authority instructions, never source messages or quotes.
    for (const map of [state.authorityAliases?.agents, state.authorityAliases?.owners]) {
      for (const [id, label] of Object.entries(map || {})) {
        if (id && typeof label === "string") result = result.split(id).join(label);
      }
    }
    return result;
  }

  function aliasedIdentity(value, group, aliases) {
    const maps = group ? [aliases?.[group]] : [aliases?.agents, aliases?.owners];
    for (const map of maps) {
      if (typeof value === "string" && map && Object.hasOwn(map, value) && typeof map[value] === "string") return map[value];
    }
    return text(value);
  }

  function graphIdentityLabel(node, fallback) {
    if (!node) return text(fallback);
    const type = String(node.type || node.kind || "").toLowerCase();
    const value = node.label || node.id;
    return type === "agent" ? identityLabel(value, "agents") : ["person", "decisionowner"].includes(type) ? identityLabel(value, "owners") : text(value);
  }

  function graphIdentityId(node) {
    const id = String(node.id);
    const type = String(node.type || node.kind).toLowerCase();
    if (type === "agent" && id.startsWith("agent:")) return `agent:${identityLabel(id.slice(6), "agents")}`;
    if (type === "person" && id.startsWith("person:")) return `person:${identityLabel(id.slice(7), "owners")}`;
    return id;
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
    target.append(element("span", "pagination-count", `Page ${current} of ${total} · ${range} of ${number(count)}`));
    const buttons = element("div", "pagination-buttons");
    const add = (label, page, disabled, active = false) => {
      const button = element("button", `page-button ${label === "Previous" || label === "Next" ? "page-direction" : "page-number"}${active ? " current" : ""}`, label);
      button.type = "button"; button.disabled = disabled;
      button.setAttribute("aria-label", label === "Previous" || label === "Next" ? `${label} page` : `Page ${page}`);
      if (active) button.setAttribute("aria-current", "page");
      button.addEventListener("click", () => {
        state.pages[key] = page; onChange();
        target.querySelector('[aria-current="page"]')?.focus({ preventScroll: true });
      });
      buttons.append(button);
    };
    add("Previous", current - 1, current === 1);
    const pages = [...new Set([1, current - 1, current, current + 1, total])].filter((page) => page >= 1 && page <= total).sort((a, b) => a - b);
    let previous = 0;
    pages.forEach((page) => {
      if (previous && page - previous > 1) buttons.append(element("span", "page-ellipsis", "…"));
      add(String(page), page, false, current === page); previous = page;
    });
    add("Next", current + 1, current === total);
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
      const detail = data.detail || data.error || `Request failed (${response.status}).`;
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
    document.body.classList.add("visitor-demo");
    $("deployment-label").textContent = "DEMO";
    $("deployment-notice").hidden = false;
    $("deployment-description").textContent = state.config.deployment.notice || "A separate example workspace for each visitor. No external agents or owners are connected.";
    document.querySelector(".brief-help").textContent = "Explore a previously recorded analysis of the example conversation. Authority changes are evaluated without a new model call.";
    document.querySelector(".intake-description").textContent = "Paste a conversation to identify possible waits and decisions using rules. This demo does not generate new model briefings.";
    document.querySelector(".intake-privacy").textContent = "Saved in this browser's demo workspace. No external agents or Slack are connected. Use sample conversations without sensitive information.";
    $("integration-heading").textContent = "Install and connect in your environment";
    $("integration-description").textContent = "Install the source from GitHub to connect your own agents.";
    document.querySelector(".integration-notice").replaceChildren(element("strong", "", "Demo connection limits"), element("p", "", "This demo URL does not provide a remote MCP server. No external agents, Slack workspaces, or owners are connected."));
  }

  async function resetDemo() {
    if (!visitorDemo() || state.resetting || state.mutation || state.authorityBusy || state.authorityLoading || state.selected?.busy) return;
    state.resetting = true; state.mutation = true;
    clearTimeout(state.timer); clearTimeout(state.briefTimer); controls(); authorityControls(); renderBrief();
    $("reset-demo").textContent = "Resetting…";
    try {
      await api("/api/demo/reset", {});
      state.authorityAliases = null;
      try { localStorage.removeItem("arbiter-session"); } catch { /* Storage is optional. */ }
      location.reload();
    } catch (error) {
      state.resetting = false; state.mutation = false; $("reset-demo").textContent = "Reset my demo";
      controls(); authorityControls(); renderBrief(); schedulePoll(); scheduleBriefPoll(); showError(error);
    }
  }

  function coveredRequests(session) { return array(session?.coordination_advice?.covered_pending_decisions); }

  function remainingRequests(session) {
    const projected = session?.coordination_advice?.remaining_pending_decisions;
    return Array.isArray(projected) ? projected : array(session?.requests).filter((request) => request.status === "pending");
  }

  function sessionStatusLabel(session) {
    if (session.busy) return "Agents running";
    const action = session.coordination_advice?.action;
    if (action === "follow_authority") return "Authority confirmed · execution unverified";
    if (action === "wait_for_human") return "Waiting for a human";
    if (action === "refresh_coordination_context") return "Context review needed";
    if (action === "wait_for_response") return "Waiting for a response";
    return session.mode === "import" && session.status === "stopped" ? array(session.decisions).length ? "Decision recorded" : "No requests" : labels[session.status] || session.status || "";
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
    $("provider-description").textContent = provider?.id === "demo" ? "Replays scripted conversations. This is a controlled simulation, not a live-model experiment." : "Connected agents work on the task. Only reported token usage is recorded.";
    $("create-session").disabled = state.mutation || !scenario || !provider || provider.available === false;
  }

  function renderSessions() {
    const target = $("session-list");
    target.replaceChildren();
    pagination("session-pagination", "sessions", state.sessions.length, 5, renderSessions);
    if (!state.sessions.length) { target.append(element("p", "sidebar-empty", "No sessions yet. Create a session or import a conversation.")); return; }
    pageRows(state.sessions, "sessions", 5).forEach((session) => {
      const button = element("button", `session-item${state.selected?.id === session.id ? " active" : ""}`);
      button.type = "button";
      button.disabled = state.mutation;
      button.setAttribute("aria-pressed", String(state.selected?.id === session.id));
      button.append(element("span", "session-item-title", session.title || session.scenario_id || session.id));
      const meta = element("span", "session-item-meta");
      meta.append(element("span", "", `${session.mode === "demo" ? "Simulation" : session.mode === "import" ? "Imported" : "Live run"} · ${session.turn ?? 0} turns`), element("span", "", sessionStatusLabel(session)));
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
    metricLabels[0].textContent = session.mode === "import" ? "Imported messages" : "Conversation turns";
    metricLabels[1].textContent = "Agent tokens";
    metricLabels[3].textContent = session.mode === "import" ? "Recorded next actions" : "Progress events";
    $("metric-turns").textContent = number(session.turn);
    $("metric-turns-unit").textContent = session.mode === "import" ? "messages" : "turns";
    $("metric-turns-note").textContent = session.mode === "import" ? `${number(session.turn)} source messages` : `Limit: ${number(session.max_turns)} turns`;
    const measured = Number(metrics.measured_calls || 0) > 0;
    $("metric-tokens").textContent = measured ? number(Number(metrics.input_tokens || 0) + Number(metrics.output_tokens || 0)) : "Unmeasured";
    $("metric-tokens").classList.toggle("is-unmeasured", !measured);
    $("metric-tokens-unit").textContent = measured ? "tokens" : "";
    $("metric-tokens-note").textContent = measured ? `Input ${number(metrics.input_tokens)} · output ${number(metrics.output_tokens)}${metrics.unmetered_calls ? ` · Unmeasured calls: ${number(metrics.unmetered_calls)}` : ""}` : session.mode === "demo" ? "Scripted data · no actual tokens" : session.mode === "import" ? "Imported transcript · no usage data" : "No calls with reported usage";
    $("metric-requests").textContent = number(metrics.human_requests ?? array(session.requests).length);
    $("metric-requests-note").textContent = `Decisions saved: ${array(session.decisions).length}${coveredRequests(session).length ? ` · Answered by authority: ${coveredRequests(session).length}` : ""}`;
    $("metric-progress").textContent = number(metrics.progress_events);
    $("metric-progress-note").textContent = session.mode === "import" ? "External execution unverified" : metrics.success === true ? "Completion criteria met" : session.status === "completed" ? "Session ended · review outcome" : "Output and evidence changes";
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
    if (index < 0) { showError(new Error(`Could not find source evidence ${reference}.`)); return; }
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
    form.append(element("h4", "", "Priority and approvals for this decision"), element("p", "precedence-scope", `Applies to: ${check.scope} / ${check.action}`), element("p", "precedence-help", "Order all eligible agents and select only the owners who agreed to this order. This operator record applies to this scope and action only; it does not authenticate remote owners."));
    const group = element("fieldset", "precedence-fields");
    group.append(element("legend", "", "Proposed priority · first agent decides"));
    const order = element("ol", "precedence-order");
    draft.agents.forEach((agent, index) => {
      const row = element("li", "precedence-agent");
      const identity = element("div", "precedence-agent-label"); identity.append(element("strong", "", `${index + 1}. ${authorityLabel(agent, "agents")}`), element("span", "", `Owner: ${authorityLabel(check.owner_by_agent?.[agent] || "Unknown", "owners")}`));
      const actions = element("div", "precedence-moves");
      [[-1, "Up"], [1, "Down"]].forEach(([direction, label]) => {
        const button = element("button", "precedence-button", label); button.type = "button";
        const boundary = index + direction < 0 || index + direction >= draft.agents.length;
        button.dataset.locked = String(boundary); button.disabled = boundary; button.setAttribute("aria-label", `${authorityLabel(agent, "agents")} Priority ${label}`);
        button.addEventListener("click", () => {
          [draft.agents[index], draft.agents[index + direction]] = [draft.agents[index + direction], draft.agents[index]];
          draft.approved.clear(); draft.restored = false; draft.message = "Order changed. Confirm owner approval for the new order.";
          renderAuthorityChecks(true);
          const replaced = [...$("authority-checks").querySelectorAll(".precedence-form")].find((item) => item.dataset.scope === check.scope && item.dataset.action === check.action);
          const moved = [...(replaced?.querySelectorAll(".precedence-moves button") || [])].find((item) => item.getAttribute("aria-label") === `${authorityLabel(agent, "agents")} Priority ${direction === -1 ? "Down" : "Up"}`);
          moved?.focus({ preventScroll: true }); announce(draft.message);
        });
        actions.append(button);
      });
      row.append(identity, actions); order.append(row);
    });
    group.append(order); form.append(group);
    const approvals = element("fieldset", "precedence-approvals"); approvals.append(element("legend", "", "Owners who approved this order"));
    const owners = [...new Set(array(check.required_owners).filter((owner) => typeof owner === "string" && owner))];
    owners.forEach((owner) => {
      const label = element("label", "precedence-owner"); const input = document.createElement("input");
      input.type = "checkbox"; input.name = "approved_by"; input.value = owner; input.checked = draft.approved.has(owner);
      input.addEventListener("change", () => { if (input.checked) draft.approved.add(owner); else draft.approved.delete(owner); draft.restored = false; updateApprovalState(); });
      label.append(input, element("span", "", `${authorityLabel(owner, "owners")} approved this order`)); approvals.append(label);
    });
    form.append(approvals);
    const summary = element("p", "precedence-approval-summary"); summary.setAttribute("role", "status");
    const feedback = element("p", "precedence-local-feedback"); feedback.setAttribute("role", "status");
    const buttons = element("div", "precedence-actions"); const submit = element("button", "precedence-button precedence-submit", "Save priority and approvals"); submit.type = "submit";
    const refresh = element("button", "precedence-button", "Reload current authority"); refresh.type = "button";
    refresh.addEventListener("click", () => refreshAuthorityScope(key)); buttons.append(submit, refresh);
    const updateApprovalState = () => {
      const missing = owners.filter((owner) => !draft.approved.has(owner));
      const revisionMissing = typeof draft.revision !== "string" || !draft.revision;
      const changed = draft.stale || draft.revision !== check.registry_revision;
      summary.textContent = missing.length ? `Missing approvals: ${missing.map((owner) => authorityLabel(owner, "owners")).join(", ")} · This order is not confirmed yet. ${owners.length > 1 ? "Partial approval keeps the authority conflict unresolved." : "Confirm owner approval before saving."}` : "All required owners are selected. Save to evaluate the recorded approvals.";
      feedback.textContent = changed ? "Authority records changed. Reload them before entering the order and approvals." : revisionMissing ? "The authority revision is unavailable. Reload the current records." : draft.message || (draft.restored ? "Restored saved approvals for this exact order." : "Approval boxes are never selected automatically.");
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
      $("precedence-feedback").textContent = result ? "Current authority loaded. Review the order and owner approvals." : "Could not load the latest evaluation. Try again.";
      renderAuthorityChecks(true);
    } finally { state.authorityBusy = false; authorityControls(); }
  }

  async function savePrecedence(check, draft) {
    if (state.authorityBusy || state.authorityLoading || state.resetting || !state.config) return;
    const selection = state.selection; const key = authorityScopeKey(check);
    state.authorityBusy = true; authorityControls(); $("precedence-feedback").textContent = "Saving the priority order and owner approvals.";
    try {
      await api("/api/authority/precedence", { scope: check.scope, action: check.action, agents: [...draft.agents], approved_by: [...draft.approved], expected_revision: draft.revision });
      await loadAuthority();
      if (selection !== state.selection) return;
      state.authorityDrafts.delete(key); state.authorityEditing.delete(key); const result = await refreshBrief(true);
      await refreshCoordinationSnapshot(selection);
      if (selection !== state.selection) return;
      const updated = authorityCheckRows().find((item) => authorityScopeKey(item) === key);
      const detail = !result ? "Could not load the latest evaluation. Try again." : updated?.status === "authorized" ? `Decision owner: ${authorityLabel(updated.decision_owner, "agents")}. Briefing interventions: ${array(result.brief?.intervention_points).length}.` : "Authority is still unresolved. Review the missing approvals and evaluation reason.";
      $("precedence-feedback").textContent = `${check.scope} / ${check.action} record saved. ${detail}`;
      announce($("precedence-feedback").textContent); renderAuthorityChecks(true);
    } catch (error) {
      if (selection === state.selection) {
        if (error.status === 409) draft.stale = true;
        draft.message = `Could not save. ${error.message}`;
        $("precedence-feedback").textContent = draft.message; renderAuthorityChecks(true);
      }
    } finally { state.authorityBusy = false; authorityControls(); }
  }

  function renderAuthorityChecks(force = false) {
    const rows = authorityCheckRows();
    const walkthrough = $("demo-walkthrough");
    walkthrough.hidden = !visitorDemo() || !state.selected?.demo?.synthetic;
    if (!walkthrough.hidden) {
      const authorized = rows.find((check) => check.status === "authorized" && check.decision_owner);
      $("demo-next-action").textContent = authorized ? `${authorityLabel(authorized.decision_owner, "agents")} can ${authorized.action} ${authorized.scope}. External execution is unverified.` : "The decision owner appears after the required approvals are recorded.";
    }
    const panel = $("authority-check-panel"); panel.hidden = !rows.length;
    $("authority-intervention-count").textContent = `Briefing interventions: ${array(state.briefState?.brief?.intervention_points).length} · Authority checks: ${rows.length}`;
    if (!rows.length) return;
    const key = JSON.stringify([state.selected?.id, state.selected?.demo?.display_aliases, rows, state.pages.authorityChecks]);
    if (!force && key === state.authorityChecksKey) { authorityControls(); return; }
    state.authorityChecksKey = key;
    const statuses = { missing: "Delegation needed", authority_gap: "Delegation needed", conflict: "Authority conflict", authority_conflict: "Authority conflict", cross_owner_conflict: "Cross-owner authority conflict", conditional: "Conditions need review", unknown: "Authority needs review", authorized: "Delegation verified", allowed: "Delegation verified", ok: "Delegation verified", resolved: "Decision owner identified", owner_required: "Owner decision needed", missing_owner: "Owner needed", expired: "Expired", revoked: "Authority revoked" };
    const priority = (item) => ["conflict", "authority_conflict", "cross_owner_conflict"].includes(item.status) ? 0 : ["missing", "missing_owner", "authority_gap", "conditional", "unknown"].includes(item.status) ? 1 : 2;
    const ordered = [...rows].sort((a, b) => priority(a) - priority(b));
    const target = $("authority-checks"); target.replaceChildren();
    pageRows(ordered, "authorityChecks", 6).forEach((check) => {
      const article = element("article", "authority-check");
      article.append(element("span", "authority-check-status", statuses[check.status] || check.status || "Unknown"), element("h3", "", `${check.scope || "Scope unknown"} · ${check.action || "Action unknown"}`));
      const details = element("dl", "authority-check-details");
      const fields = [
        ["Eligible agents", array(check.authorized_agents).length ? array(check.authorized_agents).map((agent) => authorityLabel(agent, "agents")).join(", ") : "No verified delegation"],
        ["Decision owner", check.decision_owner ? authorityLabel(check.decision_owner, "agents") : "Unknown"],
      ];
      if (array(check.required_owners).length) fields.push(["Required owners", array(check.required_owners).map((owner) => authorityLabel(owner, "owners")).join(", ")]);
      if (check.owner_by_agent && Object.keys(check.owner_by_agent).length) fields.push(["Agents by owner", Object.entries(check.owner_by_agent).map(([agent, owner]) => `${authorityLabel(owner, "owners")} → ${authorityLabel(agent, "agents")}`).join(", ")]);
      if (array(check.priority_order).length) fields.push(["Applied priority", check.priority_order.map((agent) => authorityLabel(agent, "agents")).join(" → ")]);
      fields.forEach(([label, value]) => details.append(element("dt", "", label), element("dd", "", value)));
      article.append(details);
      if (check.reason) article.append(element("p", "authority-check-reason", check.reason));
      if (["authority_conflict", "cross_owner_conflict"].includes(check.status) || (check.status === "authorized" && state.authorityEditing.has(authorityScopeKey(check)))) { article.classList.add("has-resolution"); article.append(resolutionForm(check)); }
      else if (check.status === "authorized" && check.precedence_applied && array(check.authorized_agents).length > 1) {
        const button = element("button", "precedence-button", "Edit recorded priority"); button.type = "button";
        button.addEventListener("click", () => { state.authorityEditing.add(authorityScopeKey(check)); renderAuthorityChecks(true); }); article.append(button);
      }
      else if (["authority_gap", "conditional", "unknown", "missing", "missing_owner"].includes(check.status)) {
        article.append(element("p", "authority-guidance", "Priority alone cannot resolve this. Verify the owner, delegation scope, conditions, and valid records first."));
        const button = element("button", "precedence-button", "Review delegations"); button.type = "button"; button.addEventListener("click", () => switchTab($("knowledge-tab"))); article.append(button);
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
    if (!grants.length) { target.append(element("p", "authority-empty", "No delegations recorded. Add the agent, owner, scope, and permitted action.")); return; }
    const wrapper = element("div", "authority-table-wrap"); const table = element("table", "authority-table");
    const heading = element("tr"); ["Agent", "Owner", "Scope", "Action", "Status", "Manage"].forEach((label) => { const th = element("th", "", label); th.scope = "col"; heading.append(th); });
    const head = element("thead"); head.append(heading); const body = element("tbody");
    pageRows(grants, "authority", 8).forEach((grant) => {
      const expired = Boolean(grant.expires_at && Number.isFinite(Date.parse(grant.expires_at)) && Date.parse(grant.expires_at) <= Date.now());
      const row = element("tr");
      [authorityLabel(grant.agent, "agents"), authorityLabel(grant.owner, "owners"), grant.scope, grant.action, grant.revoked ? "Revoked" : expired ? "Expired" : "Recorded"].forEach((value) => row.append(element("td", "", text(value))));
      const action = element("td"); const button = element("button", "button secondary", grant.revoked ? "Revoked" : "Revoke"); button.type = "button"; button.dataset.revoked = String(Boolean(grant.revoked));
      button.disabled = Boolean(grant.revoked) || state.authorityBusy || state.authorityLoading;
      button.setAttribute("aria-label", `Revoke ${authorityLabel(grant.agent, "agents")}: ${grant.scope} / ${grant.action}`);
      button.addEventListener("click", () => mutateAuthority(`/api/authority/grants/${encodeURIComponent(grant.id)}/revoke`, {}, "Authority revoked."));
      action.append(button); row.append(action); body.append(row);
    });
    table.append(head, body); wrapper.append(table); target.append(wrapper);
  }

  async function loadAuthority() {
    if (!state.config || state.authorityLoading || state.resetting) return;
    state.authorityLoading = true; authorityControls();
    try {
      state.authority = await api("/api/authority");
      if (state.authority.display_aliases) state.authorityAliases = state.authority.display_aliases;
      renderAuthority();
    }
    catch (error) { $("authority-list").replaceChildren(element("p", "authority-empty", `Could not load authority records. ${error.message}`)); $("authority-pagination").replaceChildren(); }
    finally { state.authorityLoading = false; authorityControls(); }
  }

  async function mutateAuthority(path, payload, message) {
    if (!state.config || state.authorityBusy || state.authorityLoading || state.resetting) return;
    state.authorityBusy = true; authorityControls(); $("authority-feedback").textContent = "";
    try {
      await api(path, payload); await loadAuthority();
      if (path === "/api/authority/grants") { $("authority-form").reset(); state.pages.authority = Math.max(1, Math.ceil(array(state.authority?.grants).length / 8)); renderAuthority(); }
      $("authority-feedback").textContent = message; announce(message); await refreshBrief(true); await refreshCoordinationSnapshot();
    } catch (error) { $("authority-feedback").textContent = `Request failed. ${error.message}`; }
    finally { state.authorityBusy = false; authorityControls(); }
  }

  function createGrant(event) {
    event.preventDefault();
    const data = new FormData($("authority-form"));
    const payload = Object.fromEntries(["agent", "owner", "scope", "action"].map((key) => [key, String(data.get(key) || "").trim()]));
    if (Object.values(payload).some((value) => !value)) { $("authority-feedback").textContent = "Enter an agent, owner, scope, and action."; return; }
    mutateAuthority("/api/authority/grants", { ...payload, conditions: [] }, "Owner and scoped delegation recorded.");
  }

  function renderBrief() {
    const data = state.briefState || {};
    const brief = data.brief;
    const generating = state.briefPosting || data.status === "generating";
    const button = $("generate-brief");
    button.disabled = !liveBriefAvailable() || !state.selected || !array(state.selected.messages).length || generating || state.resetting;
    button.classList.toggle("loading", generating);
    button.textContent = visitorDemo() ? "New analysis unavailable in demo" : generating ? "Generating briefing" : brief ? "Regenerate briefing" : "Generate briefing";
    const status = $("brief-status");
    const stale = Boolean(brief && ((data.conversation_stale === undefined ? data.stale : data.conversation_stale) || (typeof brief.generated_turn === "number" && brief.generated_turn !== state.selected?.turn)));
    status.classList.toggle("is-stale", stale);
    if (generating) status.textContent = "Analyzing the conversation and cited evidence. You can use other tabs while this runs.";
    else if (data.status === "error") status.textContent = `Could not generate or load the briefing. ${data.error || "Please try again."}`;
    else if (stale) status.textContent = visitorDemo() ? "The conversation or decisions have changed. The recorded analysis does not include these changes. Install locally to generate a new analysis." : "The conversation or decisions have changed. Generate a new briefing to include them.";
    else if (brief && data.authority_stale) status.textContent = `Based on turn ${brief.generated_turn ?? "—"}${visitorDemo() ? " · Recorded model analysis" : ""} · Authority re-evaluated using current records. No new model call was made.`;
    else if (brief) status.textContent = `Through turn ${brief.generated_turn ?? "—"} · ${visitorDemo() ? "Recorded model analysis · not a live call" : brief.source === "codex" ? "Generated by a live model" : text(brief.source)}`;
    else status.textContent = visitorDemo() ? "No recorded analysis for this conversation. You can inspect possible waits and decisions; new model briefings are unavailable in this demo." : state.selected ? "No briefing yet. Generate one to summarize the conversation." : "Select a conversation to generate a briefing.";
    const target = $("brief-content"); target.replaceChildren();
    renderAuthorityChecks();
    $("brief-pagination").hidden = !brief;
    if (!brief) return;
    target.append(element("p", "brief-overview", brief.overview || "Overall context not established"));
    if (brief.coverage) {
      const coverage = brief.coverage;
      target.append(element("p", "brief-scope", `Coverage · messages ${coverage.included_messages ?? "—"} / ${coverage.total_messages ?? "—"}${coverage.truncated_messages ? ` · Truncated messages: ${coverage.truncated_messages}` : ""}`));
    }
    const sections = [["agreements", "Agreements"], ["open_questions", "Open questions"], ["intervention_points", "Intervention points"], ["next_actions", "Next actions"]];
    const rows = sections.flatMap(([key, label]) => {
      const items = array(brief[key]);
      return items.length ? items.map((item) => ({ ...item, label })) : [{ text: "Not established in this conversation", evidence_ids: [], label }];
    });
    const list = element("div", "brief-items");
    pageRows(rows, "brief", 6).forEach((item) => {
      const article = element("article", "brief-item");
      article.append(element("span", "brief-category", item.label), element("p", "", item.basis === "authority_registry" ? authorityInstruction(item.text || "Unknown") : item.text || "Unknown"));
      const references = element("div", "brief-references");
      array(item.evidence_ids).forEach((id) => {
        const reference = String(id); const source = element("button", "source-reference", reference); source.type = "button";
        const citation = array(item.evidence).find((entry) => entry.message_id === reference);
        if (citation?.quote) source.title = citation.quote;
        source.setAttribute("aria-label", `View source message ${reference}`); source.addEventListener("click", () => openSource(reference)); references.append(source);
      });
      if (references.childNodes.length) article.append(references);
      list.append(article);
    });
    target.append(list);
    const measured = brief.input_tokens != null && brief.output_tokens != null;
    const usageLabel = visitorDemo() ? "Historic analysis usage" : "Briefing usage";
    target.append(element("p", "brief-usage", measured ? `${usageLabel} · Input ${number(brief.input_tokens)} / output ${number(brief.output_tokens)} tokens` : `${usageLabel} · Unmeasured`));
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
    $("latest-messages").textContent = newCount ? `${newCount} new message${newCount === 1 ? "" : "s"} · View latest` : "View latest messages";
    $("latest-messages").classList.toggle("has-new", newCount > 0);
    $("message-range").textContent = messages.length ? `${start + 1}–${Math.min(start + 10, messages.length)} of ${messages.length} messages · 10 per page` : "No messages yet";
    pagination("message-pagination", "messages", messages.length, 10, () => renderConversation(state.selected));
    const key = `${session.id}:${state.pages.messages}:${state.highlightedMessage}:${JSON.stringify(session.demo?.display_aliases)}:${JSON.stringify(rows)}`;
    if (key === state.messagesKey) return;
    state.messagesKey = key;
    const target = $("conversation");
    target.replaceChildren();
    if (!messages.length) {
      const empty = element("div", "empty-state");
      empty.append(element("span", "empty-symbol", "↔"), element("h3", "", "Ready to start the conversation."), element("p", "", "Run one turn at a time, or continue until a decision is needed."));
      target.append(empty);
      return;
    }
    rows.forEach((message, index) => {
      const agent = identityLabel(message.agent || message.role || "Agent");
      const human = /human|user|\uC0AC\uB78C/i.test(agent);
      const article = element("article", `message${human ? " message-human" : ""}${state.highlightedMessage === start + index ? " source-highlight" : ""}`);
      article.dataset.messageIndex = String(start + index); article.tabIndex = -1;
      const avatar = element("span", "avatar", human ? "H" : agent.slice(0, 1).toUpperCase());
      avatar.setAttribute("aria-hidden", "true");
      const body = element("div", "message-body");
      const meta = element("div", "message-meta");
      meta.append(element("span", "message-agent", agent), element("span", "message-turn", `Turn ${message.turn ?? start + index + 1}`));
      body.append(meta, element("p", "message-text", message.content || ""));
      const chips = element("div", "message-chips");
      array(message.claims).forEach((claim) => chips.append(element("span", "message-chip", `${claim.key || claim.subject || "Claim"}: ${text(claim.value ?? claim.object)}`)));
      array(message.evidence).forEach((evidence) => chips.append(element("span", "message-chip evidence-chip", `Evidence · ${evidence.id || evidence.summary || text(evidence)}`)));
      if (chips.childNodes.length) body.append(chips);
      if (message.input_tokens != null || message.output_tokens != null) body.append(element("p", "message-tokens", `Input ${number(message.input_tokens)} · output ${number(message.output_tokens)} tokens`));
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
      target.append(element("p", "overview-kicker", `${pending.length} pending decisions`), element("h3", "", request.title), element("p", "overview-summary", request.question || request.summary));
      const button = element("button", "button primary", "Review decision →"); button.type = "button";
      button.addEventListener("click", () => openDecision(request.id)); target.append(button);
    } else if (covered.length) {
      const authority = covered[0].covered_by_authority || {};
      target.append(element("p", "overview-kicker", `Answered by authority: ${covered.length}`), element("h3", "", "No repeat approval needed"), element("p", "overview-summary", `${authority.scope || "This scope"} / ${authority.action || "This action"} · Decision owner: ${authorityLabel(authority.decision_owner || "See authority check", "agents")}. Current authority answers this request. External delivery and execution still need verification.`));
      const button = element("button", "button secondary", "View authority-resolved request →"); button.type = "button"; button.addEventListener("click", () => openDecision(covered[0].id)); target.append(button);
    } else {
      const recorded = session.mode === "import" && array(session.decisions).length;
      target.append(element("span", "overview-check", "◎"), element("h3", "", recorded ? "Decision recorded" : session.status === "completed" ? "Session completed" : "No decisions to review"), element("p", "overview-summary", recorded ? "Review the next action and assignee in Decisions. External execution still needs verification." : session.busy ? "Agents are working. Requests for human judgment will appear here." : "Review the conversation and evidence to prepare the next step."));
      const button = element("button", "button secondary", "View conversation →"); button.type = "button"; button.addEventListener("click", () => switchTab($("conversation-tab"))); target.append(button);
    }
    $("overview-task-panel").hidden = Boolean(session.coordination);
    const task = $("overview-task"); task.replaceChildren();
    task.append(element("h3", "", session.title || "Current session"), element("p", "overview-summary", session.task?.description || session.description || ""), element("p", "overview-detector", session.detector?.reason || "No messages yet."));
    const detailButton = element("button", "button secondary", "Explore knowledge →"); detailButton.type = "button"; detailButton.addEventListener("click", () => switchTab($("knowledge-tab"))); task.append(detailButton);
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
      button.append(element("span", "request-item-status", coveredIds.has(request.id) ? "Resolved by current authority" : request.status === "pending" ? "Pending decision" : "Decision record"), element("strong", "", request.title || request.question), element("span", "request-item-meta", `Turn ${request.created_turn ?? "—"} · ${request.kind || "Decision request"}`));
      button.addEventListener("click", () => { state.activeDecisionId = request.id; renderDecisionInbox(state.selected); controls(); }); target.append(button);
    });
    if (!rows.length) target.append(element("p", "inbox-empty", filter === "resolved" ? "No decisions recorded yet." : "No decision requests to display."));
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
      empty.append(element("span", "orbit-symbol", finished || recorded ? "✓" : "◎"), element("h3", "", recorded ? "Decision and next action recorded" : finished ? "Session completed" : "No action needed right now"), element("p", "", recorded ? "The assignee still needs to act. Nothing has been sent to an external service." : finished ? "Review the outcome in the conversation and linked evidence." : "Repeated claims or conflicting knowledge can trigger a request for human judgment."));
      const process = element("div", "process-labels");
      (session.mode === "import" ? ["Review evidence", "→", "Decision record", "→", "Next actions"] : ["Review conflict", "→", "Request judgment", "→", "Resume collaboration"]).forEach((label, index) => process.append(element(index % 2 ? "b" : "span", "", label)));
      empty.append(process);
      target.append(empty);
      const decisions = array(session.decisions);
      if (decisions.length) {
        const last = decisions[decisions.length - 1];
        target.append(element("p", "decision-resolved", `Latest decision · ${last.label || last.choice_label || last.choice || last.note || "Decision recorded."}`));
      }
      return;
    }
    if (covered) {
      const authority = covered.covered_by_authority || {};
      const record = element("article", "decision-active authority-covered-record");
      record.append(element("p", "decision-kind", "Resolved by current authority"), element("h3", "decision-title", request.title || "Authority review request"), element("p", "decision-summary", request.question || request.summary || ""));
      record.append(element("h3", "", `${authority.scope || "Review scope"} / ${authority.action || "Review action"}`), element("p", "decision-record-note", `Decision owner: ${authorityLabel(authority.decision_owner || "Unknown", "agents")}`), element("p", "decision-footnote", "Current delegations and priority answer this request, so approval is not requested again. The original request and human decision history are preserved. External delivery and execution are not verified."));
      const button = element("button", "precedence-button", "View authority check"); button.type = "button"; button.addEventListener("click", () => { switchTab($("overview-tab")); $("authority-check-panel").scrollIntoView({ block: "start" }); }); record.append(button); target.append(record); return;
    }
    if (request.status !== "pending") {
      const decision = array(session.decisions).find((item) => item.request_id === request.id);
      const record = element("article", "decision-active decision-record");
      record.append(element("p", "decision-kind", "Decision record"), element("h3", "decision-title", request.title), element("p", "decision-summary", request.summary));
      const chosen = array(request.options).find((option) => option.id === decision?.choice);
      record.append(element("h3", "", chosen?.label || decision?.choice || "No choice recorded"), element("p", "decision-record-note", decision?.note || "No additional notes"));
      if (request.evidence_ids?.length) record.append(element("p", "decision-sources", `Linked evidence: ${request.evidence_ids.join(", ")}`));
      if (session.mode === "import") record.append(element("p", "decision-footnote", "Recorded in this session. This does not confirm external delivery or execution."));
      target.append(record); return;
    }
    const form = element("form", "decision-active");
    form.append(element("p", "decision-kind", `${request.kind || "Decision request"} · Detected at turn ${request.created_turn ?? session.turn}`), element("h3", "decision-title", request.title || "Human judgment needed"), element("p", "decision-summary", request.summary || ""));
    if (request.evidence_ids?.length) {
      const sources = element("div", "decision-sources");
      sources.append(element("p", "", "Linked evidence"));
      request.evidence_ids.forEach((id) => {
        const evidence = array(session.evidence).find((item) => item.id === id);
        sources.append(element("p", "", `${id}${evidence ? ` · ${evidence.summary || evidence.source || ""}` : ""}`));
      });
      form.append(sources);
    }
    form.append(element("p", "decision-question", request.question || "Choose the criteria for the next step."));
    const choices = element("fieldset", "choice-list");
    choices.append(element("legend", "sr-only", "Decision options"));
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
    const noteLabel = element("label", "decision-note-label", session.mode === "import" ? "Assignee, reasoning, or next action (required)" : "Additional criteria or reasoning (optional)"); noteLabel.htmlFor = "decision-note";
    const note = element("textarea", "decision-note"); note.id = "decision-note"; note.name = "note"; note.maxLength = 4000; note.placeholder = "Add the reasoning agents should use.";
    if (session.mode === "import") { note.required = true; note.placeholder = "Example: Alex will check availability and reply tomorrow morning. Other requests remain on hold."; }
    const submit = element("button", "button decision-submit", "Save decision →"); submit.id = "decision-submit"; submit.type = "submit";
    form.append(noteLabel, note, submit, element("p", "decision-footnote", session.mode === "import" ? "Saves the decision in this session. Nothing is sent externally." : "Saves the decision and reasoning to shared knowledge."));
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const choice = data.get("choice");
      if (!choice) return;
      mutate("/decisions", { request_id: request.id, choice, note: data.get("note") || "" }, session.mode === "import" ? "Decision saved in this session." : "Decision applied. You can resume the session.");
    });
    target.append(form);
    announce(`Human judgment needed. ${request.title || request.question}`);
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
      card.append(element("p", "record-title", `${claim.key || claim.subject || claim.id || "Claim"} = ${text(claim.value ?? claim.object ?? claim.content)}`));
      card.append(element("p", "record-body", `Type: ${claim.kind || claim.type || "Unspecified"} · Scope: ${text(claim.scope || "Shared")}`));
      card.append(element("p", "record-meta", [claim.id, claim.agent || claim.author ? identityLabel(claim.agent || claim.author) : null, claim.turn != null ? `Turn ${claim.turn}` : null].filter(Boolean).join(" · ")));
      claimTarget.append(card);
    });
    if (!claims.length) claimTarget.append(element("p", "muted small", "No claims recorded yet."));
    const evidenceTarget = $("evidence-list"); evidenceTarget.replaceChildren();
    pageRows(evidence, "evidence", 8).forEach((item) => {
      const card = element("article", "record-card");
      card.append(element("p", "record-title", item.summary || item.label || item.id || "Evidence"));
      card.append(element("p", "record-body", `Source: ${text(item.source)}`));
      card.append(element("p", "record-meta", [item.id, item.agent || item.author ? identityLabel(item.agent || item.author) : null].filter(Boolean).join(" · ")));
      evidenceTarget.append(card);
    });
    if (!evidence.length) evidenceTarget.append(element("p", "muted small", "No evidence recorded yet."));
    const artifact = $("artifact-container");
    artifact.replaceChildren(); artifact.hidden = !session.artifact || !Object.keys(session.artifact).length;
    if (!artifact.hidden) artifact.append(element("h3", "", "Current output"), element("pre", "", typeof session.artifact === "string" ? session.artifact : JSON.stringify(session.artifact, null, 2)));
  }

  function renderCoordination(session) {
    const coordination = session.coordination;
    const panel = $("coordination-panel");
    panel.hidden = !coordination;
    if (!coordination) return;
    $("coordination-summary").textContent = coordination.summary || "Review commitments, handoffs, response waits, and decision owners.";
    const target = $("coordination-content"); target.replaceChildren();
    const statusLabels = { promised: "Commitment", promise: "Commitment", requested: "Handoff confirmed", delivered: "Handoff confirmed", delivery_unknown: "Delivery status unknown", human_reported_delivered: "Delivery reported by a person", waiting: "Awaiting response", unassigned: "No decision owner", unknown: "Delivery unverified", resolved: "Decision recorded", pending: "Awaiting response", no_owner: "No decision owner", handoff_unverified: "Handoff unverified", circular_wait: "Circular wait", recorded: "Next action recorded", authority: "Decision owner needed", handoff: "Confirm handoff", coordination: "Review waiting relationships" };
    if (coordination.delivery_status === "human_reported_delivered") {
      const delivery = element("article", "coordination-card");
      delivery.append(element("span", "coordination-label", "Delivery reported by a person"), element("h3", "", "Request already delivered"), element("p", "", "A person reported that the request was delivered. This is not a delivery receipt from the external system."));
      target.append(delivery);
    }
    const groups = [["issues", "Issue to review", "is-issue"], ["next_actions", "Next actions", ""], ["commitments", "Commitment", ""], ["waits", "Awaiting response", ""]];
    groups.forEach(([key, fallback, className]) => array(coordination[key]).forEach((item) => {
      if (target.childNodes.length >= 3) return;
      const card = element("article", `coordination-card ${className}`);
      if (typeof item !== "object" || item === null) { card.append(element("h3", "", fallback), element("p", "", text(item))); target.append(card); return; }
      const resolved = key === "issues" && array(session.requests).some((request) => request.id === `request-${item.id}` && request.status === "resolved");
      const status = resolved ? "resolved" : item.status || item.kind || item.type;
      card.append(element("span", "coordination-label", statusLabels[status] || fallback));
      card.append(element("h3", "", item.title || item.summary || (item.agent || item.owner ? identityLabel(item.agent || item.owner) : fallback)));
      const detail = item.description || item.detail || item.reason || item.content || item.text || item.action || (item.title ? item.summary : null);
      if (detail) card.append(element("p", "", text(detail)));
      const references = [];
      if (item.from || item.actor) references.push(`Requested by: ${identityLabel(item.from || item.actor)}`);
      if (item.to || item.waiting_for) references.push(`Waiting for: ${identityLabel(item.to || item.waiting_for)}`);
      if (item.owner) references.push(`Assignee: ${identityLabel(item.owner)}`);
      if (item.evidence_ids?.length) references.push(`Evidence: ${item.evidence_ids.join(", ")}`);
      else if (item.message_ids?.length) references.push(`Message evidence: ${item.message_ids.join(", ")}`);
      else if (item.message_id) references.push(`Message evidence: ${item.message_id}`);
      if (references.length) card.append(element("p", "", references.join(" · ")));
      if (!detail && !references.length) {
        const remaining = Object.entries(item).filter(([name, value]) => !["id", "title", "summary", "status", "kind", "type"].includes(name) && value !== null && value !== undefined);
        if (remaining.length) card.append(element("p", "", remaining.map(([name, value]) => `${name}: ${text(value)}`).join("\n")));
      }
      target.append(card);
    }));
    if (!target.childNodes.length) target.append(element("p", "muted small", "No waiting relationships or handoff issues identified."));
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
    $("graph-count").textContent = `${nodes.length} nodes · ${edges.length} relationships`;
    const allNodes = new Map(nodes.map((node) => [String(node.id), node]));
    pagination("node-pagination", "nodes", nodes.length, 8, () => renderGraph(state.graph));
    pagination("edge-pagination", "edges", edges.length, 8, () => renderGraph(state.graph));
    pageRows(nodes, "nodes", 8).forEach((node) => nodeList.append(element("li", "", `${typeNames[String(node.type || node.kind).toLowerCase()] || node.type || "Concept"} · ${graphIdentityLabel(node)} (${graphIdentityId(node)})`)));
    pageRows(edges, "edges", 8).forEach((edge) => edgeList.append(element("li", "", `${graphIdentityLabel(allNodes.get(String(edge.source)), edge.source)} → ${edge.label || edge.type || edge.relation || "Relation"} → ${graphIdentityLabel(allNodes.get(String(edge.target)), edge.target)}`)));
    if (!nodes.length) { container.append(element("p", "graph-empty", "Relationships between claims and evidence appear as the conversation progresses.")); return; }
    const normalizedType = (node) => String(node.type || node.kind || "concept").toLowerCase();
    const typeLabel = (node) => typeNames[normalizedType(node)] || node.type || "Concept";
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
    const svg = svgElement("svg", { viewBox: `0 0 ${width} ${height}`, class: "knowledge-svg", role: "img", "aria-label": `Knowledge graph. ${nodes.length} nodes and ${edges.length} relationships. An accessible list is available below.` });
    const edgeLayer = svgElement("g");
    edges.forEach((edge) => {
      const source = locations.get(String(edge.source)); const target = locations.get(String(edge.target));
      if (!source || !target) return;
      const mid = (source.x + target.x) / 2;
      const path = svgElement("path", { d: `M ${source.x} ${source.y} C ${mid} ${source.y}, ${mid} ${target.y}, ${target.x} ${target.y}`, class: "graph-edge" });
      path.append(svgElement("title", {}, `${edge.label || edge.type || edge.relation || "Relation"}`));
      edgeLayer.append(path);
    });
    svg.append(edgeLayer);
    columns.flat().forEach((node) => {
      const point = locations.get(String(node.id));
      const type = normalizedType(node);
      const emphasis = ["conflict", "decision", "request", "humaninputrequest", "intervention"].includes(type);
      const group = svgElement("g", { transform: `translate(${point.x}, ${point.y})` });
      group.append(svgElement("title", {}, `${typeLabel(node)} · ${graphIdentityLabel(node)}`));
      group.append(svgElement("rect", { x: -91, y: -23, width: 182, height: 46, rx: 12, fill: emphasis ? "#171717" : "#ffffff", stroke: emphasis ? "#171717" : "#d4d4d4" }));
      const label = graphIdentityLabel(node);
      group.append(svgElement("text", { x: 0, y: -4, "text-anchor": "middle", class: `graph-node-label${emphasis ? " inverse" : ""}` }, label.length > 17 ? `${label.slice(0, 16)}…` : label));
      group.append(svgElement("text", { x: 0, y: 12, "text-anchor": "middle", class: `graph-node-type${emphasis ? " inverse" : ""}` }, typeLabel(node)));
      svg.append(group);
    });
    container.append(svg);
    if (nodes.length > 32) container.append(element("p", "graph-limit", "The map shows the latest 32 nodes. Browse the complete relationships in the lists below."));
  }

  function render(session) {
    const previousAliases = JSON.stringify(state.authorityAliases);
    state.selected = session;
    if (session.demo?.synthetic && session.demo.display_aliases) state.authorityAliases = session.demo.display_aliases;
    if (previousAliases !== JSON.stringify(state.authorityAliases) && state.authority) renderAuthority();
    $("active-session-title").textContent = session.title || session.scenario_id;
    $("session-status").textContent = sessionStatusLabel(session);
    $("session-status").className = `status-badge ${Object.hasOwn(labels, session.status) ? session.status : "neutral"}`;
    $("policy-label").textContent = session.mode === "import" ? "Imported conversation" : policyNames[session.policy] || session.policy;
    const notice = $("mode-notice"); notice.className = `mode-notice ${session.mode === "demo" ? "is-demo" : "is-real"}`;
    notice.querySelector("p").textContent = session.mode === "demo" ? "Scripted simulation · Explore detection and decision flows. These results do not measure live-model performance or token savings." : session.mode === "import" ? "Imported conversation · Reviews commitments and waiting relationships. Decisions made here are not sent to Pickle or Slack." : "Live agents · Records generated conversations and reported usage. Calls without reported tokens are marked as unmeasured.";
    if (visitorDemo() && session.demo?.synthetic) notice.querySelector("p").textContent = [session.demo.notice, session.demo.seed_notice].filter(Boolean).join(" ") || "Explore an authority conflict using a synthetic conversation and recorded model analysis. No external tasks are executed.";
    $("detector-label").textContent = session.detector?.reason || (session.busy ? "Waiting for the next agent response" : "Monitoring conversation and knowledge state");
    $("stalled-label").textContent = session.detector?.stalled_turns ? `No progress for ${session.detector.stalled_turns} turns` : "";
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
      announce("Session created.");
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
      const session = await api("/api/intake", { transcript, title: $("intake-title").value.trim() || "Imported collaboration", source: $("intake-source").value });
      resetSessionViews(session); state.pages.sessions = 1; render(session); switchTab($("overview-tab"));
      await fetchGraph(session.id, selection);
      await refreshBrief();
      try { localStorage.setItem("arbiter-session", session.id); } catch { /* Storage is optional. */ }
      $("intake-dialog").close();
      announce("Imported conversation checked for waits and decision points.");
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
      if (data.available === false) { target.append(element("p", "experiment-empty", data.message || "No saved experiment results. Run an experiment to compare policies.")); return; }
      const policies = data.policies || {};
      const rows = ["capped", "periodic", "adaptive"].filter((policy) => policies[policy]).map((policy) => ({ policy, ...policies[policy] }));
      target.append(element("p", "experiment-study", data.study_type || "Saved experiment results"));
      if (data.design?.real_model_calls === false) target.append(element("p", "experiment-meta", "Controlled simulation using scripted conversations and automated responses. This is not evidence from live-model or human trials, or a measure of token savings."));
      if (rows.length) {
        const columns = [
          ["Intervention policy", (row) => policyNames[row.policy]],
          ["Successes / runs", (row) => `${row.successes ?? "—"} / ${row.runs ?? "—"}`],
          ["Success rate", (row) => typeof row.success_rate === "number" ? `${(row.success_rate * 100).toFixed(1)}%` : "Unmeasured"],
          ["Unknown outcomes", (row) => text(row.unknown_outcomes)],
          ["Mean turns", (row) => typeof row.mean_turns_all_runs === "number" ? `${row.mean_turns_all_runs.toFixed(2)} turns` : "Unmeasured"],
          ["Total requests", (row) => text(row.total_human_requests)],
          ["Mean requests", (row) => typeof row.mean_human_requests === "number" ? row.mean_human_requests.toFixed(3) : "Unmeasured"],
          ["Measured tokens", (row) => row.input_tokens == null || row.output_tokens == null ? "Unmeasured" : number(row.input_tokens + row.output_tokens)],
        ];
        const wrapper = element("div", "experiment-table-wrap"); const table = element("table", "experiment-table");
        const caption = element("caption", "sr-only", "Results for three intervention policies"); const head = element("thead"); const heading = element("tr");
        columns.forEach(([label]) => { const th = element("th", "", label); th.scope = "col"; heading.append(th); }); head.append(heading);
        const body = element("tbody"); rows.forEach((row) => { const tr = element("tr"); tr.dataset.policy = row.policy; columns.forEach(([, value]) => tr.append(element("td", "", value(row)))); body.append(tr); });
        table.append(caption, head, body); wrapper.append(table); target.append(wrapper);
        target.append(element("p", "experiment-meta", `Success means the local output met its checklist. Runs: ${data.assigned_run_count ?? rows.reduce((total, row) => total + Number(row.runs || 0), 0)} · Mean turns include all runs.`));
      } else target.append(element("p", "experiment-empty", "No policy aggregates available. Inspect the source records."));
      const details = element("details", "graph-details"); details.append(element("summary", "", "View source experiment records"), element("pre", "experiment-raw", JSON.stringify(data, null, 2))); target.append(details);
    } catch (error) { target.replaceChildren(element("p", "experiment-empty", `Could not load results. ${error.message}`)); }
    finally { $("refresh-experiments").disabled = false; }
  }

  async function loadIntegration() {
    if (!state.config || state.resetting) return;
    const target = $("integration-content"); $("refresh-integration").disabled = true;
    try {
      if (visitorDemo()) {
        target.replaceChildren();
        const section = element("section", "integration-section");
        section.append(element("h3", "", "Connect agents in your own environment"), element("p", "integration-description", "This demo contains visitor-specific example conversations and authority records. Install the source in your environment to configure MCP, A2A, and Slack ingestion for your agents."));
        const link = element("a", "source-install-link", "Download and install locally →"); link.href = "/download";
        section.append(link, element("p", "integration-description", "Add the MCP configuration from your own installation to your agent app. The demo URL and example grants are not connection credentials."));
        target.append(section); return;
      }
      const data = await api("/api/integration"); target.replaceChildren();
      const mcp = data.mcp || {};
      const download = element("a", "source-install-link", "Download source and setup instructions →"); download.href = "/download"; target.append(download);
      target.append(element("p", "integration-description", "Add the configuration below to your agent app's MCP server settings. Agents can use the tools without changes to their code."));
      const block = (heading, value) => {
        if (!value) return;
        const section = element("section", "integration-section"); const bar = element("div", "section-heading"); bar.append(element("h3", "", heading));
        const formatted = typeof value === "string" ? value : JSON.stringify(value, null, 2);
        const copy = element("button", "button secondary", "Copy"); copy.type = "button";
        copy.addEventListener("click", async () => { try { await navigator.clipboard.writeText(formatted); copy.textContent = "Copied"; } catch { announce("Automatic copying is unavailable. Select and copy the configuration below."); } });
        bar.append(copy); section.append(bar, element("pre", "integration-code", formatted)); target.append(section);
      };
      if (data.slack) {
        const slack = data.slack;
        const statuses = { not_configured: "Not configured", unconfigured: "Not configured", configured: "Configured", disconnected: "Disconnected", stopped: "Ingestion stopped", listening: "Listening for conversations", connected: "Connected for ingestion", events_received: "Events received", awaiting_events: "No events yet", error: "Connection error" };
        const section = element("section", "integration-section slack-section"); section.id = "slack-integration";
        section.append(element("h3", "", "Slack conversation ingestion"), element("p", "integration-description", "Receives conversations from allowed channels and records them as sessions. Connection and reception status are shown below."));
        const details = element("dl", "slack-details");
        const fields = [
          ["Ingestion status", statuses[slack.status] || slack.status || "Unknown"],
          ["Configuration", slack.configured === true ? "Required settings present" : slack.configured === false ? "Setup required" : "Unknown"],
          ["Allowed channels", array(slack.allowed_channels).length ? array(slack.allowed_channels).map(text).join(", ") : "No allowed channels"],
          ["Received events", slack.received_events == null ? "Unknown" : `${number(slack.received_events)} events`],
          ["Last received", slack.last_received_at || "No events received"],
        ];
        fields.forEach(([label, value]) => details.append(element("dt", "", label), element("dd", "", value))); section.append(details);
        if (slack.setup_url) {
          try {
            const url = new URL(slack.setup_url, location.origin);
            if (url.origin === location.origin && (url.pathname.startsWith("/static/") || url.pathname === "/api/integration/slack-manifest")) {
              const link = element("a", "button secondary", "Download Slack app manifest ↓"); link.href = url.href; link.download = "slack-app-manifest.json"; section.append(link);
            }
          } catch { /* Do not create invalid setup links. */ }
        }
        if (slack.limitations?.length) { const list = element("ul", "integration-limitations"); slack.limitations.forEach((item) => list.append(element("li", "", text(item)))); section.append(list); }
        target.append(section);
        block("Slack ingestion command", slack.command);
      }
      block("MCP server configuration", mcp.config);
      block("Local command", mcp.stdio_command);
      block("Streamable HTTP URL", mcp.streamable_http_url);
      block("Local API URL", data.api_base);
      const tools = array(mcp.tools);
      if (tools.length) {
        const section = element("section", "integration-section"); section.append(element("h3", "", `Available tools: ${tools.length}`)); const list = element("ul", "integration-tools");
        tools.forEach((tool) => list.append(element("li", "", typeof tool === "string" ? tool : `${tool.name || tool.id || tool.key}${tool.description ? ` · ${tool.description}` : ""}`))); section.append(list); target.append(section);
      }
      if (data.limitations?.length) { const list = element("ul", "integration-limitations"); data.limitations.forEach((item) => list.append(element("li", "", text(item)))); target.append(list); }
    } catch (error) { target.replaceChildren(element("p", "experiment-empty", `Could not load connection settings. ${error.message}`)); }
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
    $("stop-button").addEventListener("click", () => mutate("/stop", {}, "Stop requested."));
    $("dismiss-error").addEventListener("click", () => { $("error-banner").hidden = true; });
    $("refresh-sessions").addEventListener("click", () => refreshSessions().catch(showError));
    $("refresh-experiments").addEventListener("click", loadExperiments);
    $("refresh-integration").addEventListener("click", loadIntegration);
    $("reset-demo").addEventListener("click", resetDemo);
    $("generate-brief").addEventListener("click", generateBrief);
    $("refresh-authority").addEventListener("click", loadAuthority);
    $("authority-form").addEventListener("submit", createGrant);
    $("open-authority").addEventListener("click", () => switchTab($("knowledge-tab")));
    const showDemoSection = (selector) => {
      switchTab($("overview-tab"));
      const target = selector.split(",").map((part) => document.querySelector(part.trim())).find(Boolean);
      if (target) { target.tabIndex = -1; target.focus({ preventScroll: true }); target.scrollIntoView({ block: "start" }); }
    };
    $("demo-read-conflict").addEventListener("click", () => showDemoSection("#brief-panel"));
    $("demo-record-approvals").addEventListener("click", () => showDemoSection(".precedence-form, #authority-checks .authority-check"));
    $("demo-check-owner").addEventListener("click", () => showDemoSection("#authority-check-panel"));
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
      state.config.providers = array(state.config.providers).map((provider) => visitorDemo() && provider.id !== "demo" ? { ...provider, available: false, label: `${provider.label || provider.id} · Unavailable in demo` } : provider);
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
