// Memory Control Center — Frontend
// Consumes V2 API endpoints from dashboard_api.py

const API = '';
let currentProject = '';
let currentTab = 'dashboard';

// ================================================================
// UTILITIES
// ================================================================

async function fetchAPI(endpoint) {
    try {
        const r = await fetch(`${API}${endpoint}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return await r.json();
    } catch (e) {
        console.error('API error:', endpoint, e);
        return null;
    }
}

function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    if (attrs) {
        for (const [k, v] of Object.entries(attrs)) {
            if (v === null || v === undefined) continue;
            if (k === 'class') el.className = v;
            else if (k === 'onclick') el.onclick = v;
            else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
            else if (k === 'textContent') el.textContent = v;
            else el.setAttribute(k, v);
        }
    }
    for (const c of children) {
        if (c === null || c === undefined) continue;
        if (typeof c === 'string') el.appendChild(document.createTextNode(c));
        else if (Array.isArray(c)) c.forEach(x => {
            if (x === null || x === undefined) return;
            if (typeof x === 'string') el.appendChild(document.createTextNode(x));
            else el.appendChild(x);
        });
        else el.appendChild(c);
    }
    return el;
}

function timeAgo(dateStr) {
    if (!dateStr) return '';
    try {
        const d = new Date(dateStr.replace(' ', 'T'));
        const secs = (Date.now() - d.getTime()) / 1000;
        if (secs < 60) return 'just now';
        if (secs < 3600) return Math.floor(secs / 60) + 'm ago';
        if (secs < 86400) return Math.floor(secs / 3600) + 'h ago';
        if (secs < 2592000) return Math.floor(secs / 86400) + 'd ago';
        return d.toLocaleDateString('ro-RO');
    } catch { return dateStr ? dateStr.substring(0, 16) : ''; }
}

function fmtDate(dateStr) {
    if (!dateStr) return '';
    try {
        const d = new Date(dateStr.replace(' ', 'T'));
        return d.toLocaleString('ro-RO', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    } catch { return dateStr.substring(0, 16); }
}

function trunc(s, n) { return s && s.length > n ? s.substring(0, n) + '...' : (s || ''); }

function setContent(id, el) {
    const c = typeof id === 'string' ? document.querySelector(`#${id} .panel-body`) || document.getElementById(id) : id;
    if (!c) return;
    c.textContent = '';
    c.className = c.className.replace(' ph', '');
    if (typeof el === 'string') c.textContent = el;
    else if (el) c.appendChild(el);
}

function emptyState(msg) {
    return h('div', { class: 'empty-state' }, h('div', { class: 'empty-icon' }, '\u2014'), msg);
}

function errorState(msg) {
    return h('div', { class: 'error-state' }, msg || 'Failed to load data');
}

function badge(text, color) {
    return h('span', { class: `badge badge-${color}` }, text);
}

// ================================================================
// POST API HELPER + TOAST
// ================================================================

async function postAPI(endpoint, body) {
    try {
        const r = await fetch(`${API}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await r.json();
        if (!r.ok && !data.needs_confirm) {
            toast(data.message || `Error ${r.status}`, 'error');
            return data;
        }
        return data;
    } catch (e) {
        console.error('POST error:', endpoint, e);
        toast('Network error', 'error');
        return null;
    }
}

function toast(msg, type) {
    const c = document.getElementById('toast-container');
    if (!c) return;
    const t = h('div', { class: `toast toast-${type || 'info'}` }, msg);
    c.appendChild(t);
    setTimeout(() => t.classList.add('toast-show'), 10);
    setTimeout(() => { t.classList.remove('toast-show'); setTimeout(() => t.remove(), 300); }, 3000);
}

// ================================================================
// QUICK ACTIONS — TOPBAR
// ================================================================

async function doSetIntent(value) {
    if (!value) return;
    const data = await postAPI('/api/intent/set', { intent: value });
    if (data && data.success) {
        toast(`Intent: ${value}`, 'success');
        loadDashboard();
    }
    // Reset select
    const sel = document.getElementById('topbar-intent');
    if (sel) sel.value = '';
}

async function showSetModelDialog() {
    const body = document.getElementById('modal-body');
    if (!body) return;
    body.textContent = '';

    body.appendChild(h('h2', { style: { marginBottom: '16px', color: 'var(--accent)' } }, 'Set Current Model'));

    const modelInput = h('input', { type: 'text', placeholder: 'Model ID (e.g. claude-opus-4)', style: { width: '100%', marginBottom: '10px', padding: '8px', background: 'var(--card)', border: '1px solid var(--border)', borderRadius: '6px', color: 'var(--text)' } });
    const providerInput = h('input', { type: 'text', placeholder: 'Provider (default: anthropic)', style: { width: '100%', marginBottom: '16px', padding: '8px', background: 'var(--card)', border: '1px solid var(--border)', borderRadius: '6px', color: 'var(--text)' } });

    const btn = h('button', { class: 'btn btn-sm', onclick: async () => {
        const model_id = modelInput.value.trim();
        if (!model_id) { toast('Model ID required', 'error'); return; }
        const data = await postAPI('/api/model/set', { model_id, provider: providerInput.value.trim() || 'anthropic' });
        if (data && data.success) {
            toast(`Model: ${model_id}`, 'success');
            closeModal();
            loadDashboard();
        }
    }}, 'Set Model');

    body.appendChild(modelInput);
    body.appendChild(providerInput);
    body.appendChild(btn);
    document.getElementById('modal').style.display = 'block';
    modelInput.focus();
}

async function showCreateCheckpointDialog() {
    const body = document.getElementById('modal-body');
    if (!body) return;
    body.textContent = '';

    body.appendChild(h('h2', { style: { marginBottom: '16px', color: 'var(--accent)' } }, 'Create Checkpoint'));

    const nameInput = h('input', { type: 'text', placeholder: 'Checkpoint name (required)', style: { width: '100%', marginBottom: '10px', padding: '8px', background: 'var(--card)', border: '1px solid var(--border)', borderRadius: '6px', color: 'var(--text)' } });
    const descInput = h('input', { type: 'text', placeholder: 'Description (optional)', style: { width: '100%', marginBottom: '16px', padding: '8px', background: 'var(--card)', border: '1px solid var(--border)', borderRadius: '6px', color: 'var(--text)' } });

    const btn = h('button', { class: 'btn btn-sm', onclick: async () => {
        const name = nameInput.value.trim();
        if (!name) { toast('Name required', 'error'); return; }
        const data = await postAPI('/api/checkpoints/create', { name, description: descInput.value.trim(), project: currentProject });
        if (data && data.success) {
            toast(data.message, 'success');
            closeModal();
            loadDashboard();
        }
    }}, 'Create Checkpoint');

    body.appendChild(nameInput);
    body.appendChild(descInput);
    body.appendChild(btn);
    document.getElementById('modal').style.display = 'block';
    nameInput.focus();
}

async function doRestoreCheckpoint(id, name) {
    // First call without confirm — get info
    const info = await postAPI('/api/checkpoints/restore', { id });
    if (!info) return;

    if (info.needs_confirm) {
        if (!confirm(info.message)) return;
        const data = await postAPI('/api/checkpoints/restore', { id, confirm: true });
        if (data && data.success) {
            toast(data.message, 'success');
            loadDashboard();
        }
    } else if (info.success) {
        toast(info.message, 'success');
        loadDashboard();
    }
}

// ================================================================
// QUICK ACTIONS — FACTS (pin/unpin/promote)
// ================================================================

async function doTogglePin(factId, currentlyPinned) {
    const endpoint = currentlyPinned ? '/api/facts/unpin' : '/api/facts/pin';
    const data = await postAPI(endpoint, { id: factId });
    if (data && data.success) {
        toast(data.message, 'success');
        if (currentTab === 'facts') loadFactsTab();
        else loadDashboard();
    }
}

async function doPromoteFact(factId) {
    const data = await postAPI('/api/facts/promote', { id: factId });
    if (data && data.success) {
        toast(data.message, 'success');
        if (currentTab === 'facts') loadFactsTab();
        else loadDashboard();
    }
}

// ================================================================
// QUICK ACTIONS — TASKS (status update)
// ================================================================

async function doTaskStatus(taskId, newStatus) {
    const data = await postAPI('/api/tasks/update-status', { id: taskId, status: newStatus });
    if (data && data.success) {
        toast(data.message, 'success');
        if (currentTab === 'goals-tasks') loadGoalsTasksTab();
        else loadDashboard();
    }
}

// ================================================================
// TAB NAVIGATION
// ================================================================

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        const pane = document.getElementById(`tab-${tab}`);
        if (pane) pane.classList.add('active');
        currentTab = tab;
        loadTabData(tab);
    });
});

function loadTabData(tab) {
    switch (tab) {
        case 'dashboard': loadDashboard(); break;
        case 'decisions': loadDecisionsTab(); break;
        case 'facts': loadFactsTab(); break;
        case 'goals-tasks': loadGoalsTasksTab(); break;
        case 'timeline': loadTimelineTab(); break;
        case 'context': loadContextTab(); break;
        case 'health': loadHealthTab(); break;
        case 'activity': loadActivityTab(); break;
        case 'errors': loadErrorsTab(); break;
        case 'branches': loadBranchesTab(); break;
        case 'events': loadEventsTab(); break;
        case 'sessions': loadSessions(); break;
        case 'orchestration': loadOrch(); break;
    }
}

// ================================================================
// DASHBOARD (main tab) — single /api/dashboard call
// ================================================================

async function loadDashboard() {
    const qs = currentProject ? `?project=${encodeURIComponent(currentProject)}` : '';
    const data = await fetchAPI(`/api/dashboard${qs}`);
    if (!data) {
        setContent('overview-cards', errorState('Failed to load dashboard'));
        return;
    }

    if (data.summary) {
        currentProject = data.summary.project_path || '';
        // Fetch current branch for topbar chip
        const brData = await fetchAPI(`/api/branches?project=${encodeURIComponent(currentProject)}`);
        if (brData) window._currentBranch = brData.current || 'main';
        renderTopbar(data.summary);
    }

    renderOverviewCards(data.health || {});
    renderDashDecisions(data.decisions || []);
    renderDashFacts(data.facts || []);
    renderDashGoals(data.goals || []);
    renderDashTasks(data.tasks || []);
    renderDashErrors(data.resolutions || [], data.patterns || []);
    renderDashTimeline(data.timeline || []);
    renderDashActivity(data.activity_recent || []);

    const fi = document.getElementById('footer-info');
    if (fi && data.summary) fi.textContent = data.summary.project_path || '';
}

function refreshDashboard() { loadDashboard(); }

// ================================================================
// TOPBAR META
// ================================================================

function renderTopbar(s) {
    const el = document.getElementById('topbar-meta');
    if (!el) return;
    el.textContent = '';

    const chip = (label, value, cls) => {
        const c = h('span', { class: `meta-chip ${cls || ''}` },
            h('span', { class: 'chip-label' }, label + ': '),
            h('span', { class: 'chip-value' }, value || 'none'));
        return c;
    };

    el.appendChild(chip('Project', s.project_name || 'none', 'chip-accent'));
    if (s.model) el.appendChild(chip('Model', s.model));
    if (s.intent) el.appendChild(chip('Intent', s.intent));
    if (s.last_checkpoint) el.appendChild(chip('Checkpoint', s.last_checkpoint.name));

    // Branch chip (show when not on main)
    if (window._currentBranch && window._currentBranch !== 'main') {
        const brChip = h('span', { class: 'branch-chip', onclick: () => {
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            const btn = document.querySelector('[data-tab="branches"]');
            if (btn) btn.classList.add('active');
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            const pane = document.getElementById('tab-branches');
            if (pane) pane.classList.add('active');
            currentTab = 'branches';
            loadBranchesTab();
        }}, '\u{1F33F} ' + window._currentBranch);
        el.appendChild(brChip);
    }

    const snapColors = { valid: 'chip-success', expired: 'chip-warning', none: '', invalid: 'chip-warning' };
    el.appendChild(chip('Snapshot', s.snapshot_status || 'none', snapColors[s.snapshot_status] || ''));
}

// ================================================================
// OVERVIEW CARDS
// ================================================================

function renderOverviewCards(h_data) {
    const el = document.getElementById('overview-cards');
    if (!el) return;
    el.textContent = '';

    const card = (val, label, cls) => {
        return h('div', { class: `ov-card ${cls}` },
            h('div', { class: 'ov-val' }, String(val ?? 0)),
            h('div', { class: 'ov-label' }, label));
    };

    el.appendChild(card(h_data.decisions, 'Decisions', 'ov-accent'));
    el.appendChild(card(h_data.facts, 'Facts', 'ov-purple'));
    el.appendChild(card(h_data.goals, 'Goals', 'ov-success'));
    el.appendChild(card(h_data.tasks, 'Tasks', 'ov-cyan'));
    el.appendChild(card(h_data.patterns, 'Patterns', 'ov-warning'));
    el.appendChild(card(h_data.checkpoints, 'Checkpoints', 'ov-accent'));

    const conflicts = h_data.conflicts || 0;
    el.appendChild(card(conflicts, 'Conflicts', conflicts > 0 ? 'ov-danger' : ''));

    const stale = (h_data.stale ? (h_data.stale.stale_facts || 0) + (h_data.stale.stale_tasks || 0) : 0);
    el.appendChild(card(stale, 'Stale', stale > 0 ? 'ov-warning-border' : ''));
}

// ================================================================
// DASHBOARD PANELS
// ================================================================

function renderDashDecisions(decisions) {
    const body = document.querySelector('#dash-decisions .panel-body');
    if (!body) return;
    body.textContent = '';
    body.className = 'panel-body';

    if (!decisions.length) { body.appendChild(emptyState('No active decisions')); return; }

    decisions.forEach(d => {
        const li = h('div', { class: 'li' },
            h('div', { class: 'li-title' },
                d.has_conflict ? h('span', { class: 'marker-conflict', title: 'Conflict detected' }, '\u26A0') : null,
                trunc(d.title, 55)),
            h('div', { class: 'li-sub' },
                badge(d.category || 'general', 'blue'),
                ' ',
                badge(d.confidence || '', 'gray'),
                ' \u00B7 ',
                timeAgo(d.created_at)));
        body.appendChild(li);
    });
}

function renderDashFacts(facts) {
    const body = document.querySelector('#dash-facts .panel-body');
    if (!body) return;
    body.textContent = '';
    body.className = 'panel-body';

    if (!facts.length) { body.appendChild(emptyState('No facts recorded')); return; }

    facts.forEach(f => {
        const pinBtn = h('button', { class: 'btn-action', title: f.is_pinned ? 'Unpin' : 'Pin',
            onclick: (e) => { e.stopPropagation(); doTogglePin(f.id, f.is_pinned); }},
            f.is_pinned ? '\u2716' : '\uD83D\uDCCC');
        const li = h('div', { class: 'li li-actions' },
            h('div', { class: 'li-content' },
                h('div', { class: 'li-title' },
                    f.is_pinned ? h('span', { class: 'marker-pinned', title: 'Pinned' }, '\uD83D\uDCCC') : null,
                    trunc(f.fact, 55)),
                h('div', { class: 'li-sub' },
                    badge(f.fact_type || 'fact', 'purple'),
                    f.category ? [' ', badge(f.category, 'gray')] : null)),
            h('div', { class: 'li-btns' }, pinBtn));
        body.appendChild(li);
    });
}

function renderDashGoals(goals) {
    const body = document.querySelector('#dash-goals .panel-body');
    if (!body) return;
    body.textContent = '';
    body.className = 'panel-body';

    if (!goals.length) { body.appendChild(emptyState('No active goals')); return; }

    goals.forEach(g => {
        const total = g.total_tasks || 0;
        const done = g.done_tasks || 0;
        const pct = total > 0 ? Math.round(done / total * 100) : 0;

        const li = h('div', { class: 'li' },
            h('div', { class: 'li-title' }, trunc(g.title, 50)),
            h('div', { class: 'li-sub' },
                badge(g.priority || 'medium', g.priority === 'high' || g.priority === 'critical' ? 'red' : 'gray'),
                total > 0 ? ` ${done}/${total} tasks` : ' no tasks'),
            total > 0 ? h('div', { class: 'progress' },
                h('div', { class: `progress-fill ${pct === 100 ? 'complete' : ''}`, style: { width: pct + '%' } })) : null);
        body.appendChild(li);
    });
}

function renderDashTasks(tasks) {
    const body = document.querySelector('#dash-tasks .panel-body');
    if (!body) return;
    body.textContent = '';
    body.className = 'panel-body';

    if (!tasks.length) { body.appendChild(emptyState('No active tasks')); return; }

    const statusIcon = { in_progress: '\u25B6', blocked: '\u26D4', todo: '\u25CB', done: '\u2713' };
    const statusColor = { in_progress: 'blue', blocked: 'red', todo: 'gray', done: 'green' };

    tasks.forEach(t => {
        const btns = [];
        if (t.status !== 'in_progress') btns.push(h('button', { class: 'btn-action btn-action-sm', title: 'Start',
            onclick: (e) => { e.stopPropagation(); doTaskStatus(t.id, 'in_progress'); }}, '\u25B6'));
        if (t.status !== 'done') btns.push(h('button', { class: 'btn-action btn-action-sm', title: 'Done',
            onclick: (e) => { e.stopPropagation(); doTaskStatus(t.id, 'done'); }}, '\u2713'));
        if (t.status !== 'blocked') btns.push(h('button', { class: 'btn-action btn-action-sm', title: 'Block',
            onclick: (e) => { e.stopPropagation(); doTaskStatus(t.id, 'blocked'); }}, '\u26D4'));
        const li = h('div', { class: 'li li-actions' },
            h('div', { class: 'li-content' },
                h('div', { class: 'li-title' },
                    h('span', { class: `status-${t.status}` }, (statusIcon[t.status] || '\u25CB') + ' '),
                    trunc(t.title, 50)),
                h('div', { class: 'li-sub' },
                    badge(t.priority || 'medium', statusColor[t.status] || 'gray'),
                    t.blocked_by ? [' ', badge('blocked: ' + trunc(t.blocked_by, 20), 'red')] : null)),
            h('div', { class: 'li-btns' }, ...btns));
        body.appendChild(li);
    });
}

function renderDashErrors(resolutions, patterns) {
    const body = document.querySelector('#dash-errors .panel-body');
    if (!body) return;
    body.textContent = '';
    body.className = 'panel-body';

    if (!resolutions.length && !patterns.length) {
        body.appendChild(emptyState('No error intelligence'));
        return;
    }

    if (resolutions.length) {
        body.appendChild(h('div', { class: 'li', style: { borderBottom: '1px solid var(--border)' } },
            h('div', { class: 'li-sub', style: { color: 'var(--text-muted)', fontWeight: '600', fontSize: '0.72rem', textTransform: 'uppercase' } }, 'Recent Resolutions')));
        resolutions.forEach(r => {
            body.appendChild(h('div', { class: 'li' },
                h('div', { class: 'li-title' }, trunc(r.error_summary, 50)),
                h('div', { class: 'li-sub', style: { color: 'var(--success)' } }, '\u2713 ' + trunc(r.resolution, 55))));
        });
    }

    if (patterns.length) {
        body.appendChild(h('div', { class: 'li', style: { borderBottom: '1px solid var(--border)' } },
            h('div', { class: 'li-sub', style: { color: 'var(--text-muted)', fontWeight: '600', fontSize: '0.72rem', textTransform: 'uppercase' } }, 'Detected Patterns')));
        patterns.forEach(p => {
            body.appendChild(h('div', { class: 'li' },
                h('div', { class: 'li-title' }, trunc(p.error_signature, 45)),
                h('div', { class: 'li-sub' }, badge('x' + p.count, 'yellow'), ' ', trunc(p.solution, 40))));
        });
    }
}

function renderDashTimeline(events) {
    const body = document.querySelector('#dash-timeline .panel-body');
    if (!body) return;
    body.textContent = '';
    body.className = 'panel-body';

    if (!events.length) { body.appendChild(emptyState('No recent events')); return; }

    const icons = {
        checkpoint_create: '\uD83D\uDCBE', checkpoint_restore: '\u21A9',
        decision: '\uD83D\uDCCB', fact_promoted: '\uD83D\uDCCC',
        pattern_detected: '\u26A0', goal_completed: '\u2713',
        default: '\u2022'
    };

    events.forEach(e => {
        const icon = icons[e.type] || icons.default;
        body.appendChild(h('div', { class: 'tl-item' },
            h('div', { class: 'tl-icon' }, icon),
            h('div', { class: 'tl-content' },
                h('div', { class: 'tl-title' }, trunc(e.title, 50)),
                e.detail ? h('div', { class: 'tl-detail' }, trunc(e.detail, 40)) : null),
            h('div', { class: 'tl-date' }, timeAgo(e.date))));
    });
}

function renderDashActivity(activity) {
    const body = document.querySelector('#dash-activity .panel-body');
    if (!body) return;
    body.textContent = '';
    body.className = 'panel-body';

    if (!activity.length) { body.appendChild(emptyState('No recent activity')); return; }

    activity.forEach(a => {
        const ok = a.success ? '\u2713' : '\u2717';
        const okCls = a.success ? 'badge-green' : 'badge-red';
        body.appendChild(h('div', { class: 'li' },
            h('div', { class: 'li-title' },
                h('span', { class: `badge ${okCls}`, style: { marginRight: '6px' } }, ok),
                trunc(a.action_summary, 50)),
            h('div', { class: 'li-sub' },
                badge(a.action_type || 'action', 'blue'),
                a.agent_name ? [' ', badge(a.agent_name, 'purple')] : null,
                a.model_id ? [' ', badge(a.model_id, 'gray')] : null,
                ' \u00B7 ', timeAgo(a.created_at))));
    });
}

// ================================================================
// ACTIVITY TAB (detail)
// ================================================================

async function loadActivityTab() {
    const type = document.getElementById('activity-type')?.value || '';
    const failed = document.getElementById('activity-failed')?.checked;
    const pq = currentProject ? '&project=' + encodeURIComponent(currentProject) : '';
    let qs = `?limit=50${pq}`;
    if (type) qs += `&type=${type}`;
    if (failed) qs += '&failed=true';

    const data = await fetchAPI(`/api/activity${qs}`);
    const el = document.getElementById('activity-list');
    if (!el) return;
    el.textContent = '';

    if (!data || !data.activity) { el.appendChild(errorState()); return; }
    if (!data.activity.length) { el.appendChild(emptyState('No activity found')); return; }

    data.activity.forEach(a => {
        const ok = a.success ? '\u2713' : '\u2717';
        const okCls = a.success ? 'badge-green' : 'badge-red';
        el.appendChild(h('div', { class: 'li' },
            h('div', { class: 'li-title' },
                h('span', { class: `badge ${okCls}`, style: { marginRight: '6px' } }, ok),
                a.action_summary || ''),
            h('div', { class: 'li-sub' },
                badge(a.action_type || 'action', 'blue'), ' ',
                a.agent_name ? badge(a.agent_name, 'purple') : null, ' ',
                a.model_id ? badge(a.model_id, 'gray') : null,
                a.entity_type ? [' \u00B7 ', a.entity_type + '#' + (a.entity_id || '')] : null,
                a.duration_ms ? [' \u00B7 ', a.duration_ms + 'ms'] : null,
                ' \u00B7 ', fmtDate(a.created_at)),
            a.error_message ? h('div', { class: 'li-desc', style: { color: 'var(--danger)' } }, a.error_message) : null));
    });
}

// ================================================================
// DECISIONS TAB (detail)
// ================================================================

async function loadDecisionsTab() {
    const status = document.getElementById('decisions-status')?.value || 'active';
    const qs = `?status=${status}${currentProject ? '&project=' + encodeURIComponent(currentProject) : ''}&limit=30`;
    const data = await fetchAPI(`/api/decisions${qs}`);
    const el = document.getElementById('decisions-list');
    if (!el) return;
    el.textContent = '';

    if (!data || !data.decisions) { el.appendChild(errorState()); return; }
    if (!data.decisions.length) { el.appendChild(emptyState(`No ${status} decisions`)); return; }

    data.decisions.forEach(d => {
        el.appendChild(h('div', { class: 'li' },
            h('div', { class: 'li-title' },
                d.has_conflict ? h('span', { class: 'marker-conflict' }, '\u26A0') : null,
                d.title),
            h('div', { class: 'li-sub' },
                badge(d.category || 'general', 'blue'), ' ',
                badge(d.status || 'active', d.status === 'active' ? 'green' : 'gray'), ' ',
                badge(d.confidence || '', 'gray'),
                d.model_used ? [' \u00B7 ', h('span', { class: 'badge badge-gray' }, d.model_used)] : null,
                ' \u00B7 ', timeAgo(d.created_at)),
            d.description ? h('div', { class: 'li-desc' }, trunc(d.description, 200)) : null,
            d.rationale ? h('div', { class: 'li-desc', style: { fontStyle: 'italic' } }, trunc(d.rationale, 150)) : null));
    });
}

// ================================================================
// FACTS TAB (detail)
// ================================================================

async function loadFactsTab() {
    const pinned = document.getElementById('facts-filter')?.value || '';
    let qs = `?limit=30${currentProject ? '&project=' + encodeURIComponent(currentProject) : ''}`;
    if (pinned) qs += `&pinned=${pinned}`;
    const data = await fetchAPI(`/api/facts${qs}`);
    const el = document.getElementById('facts-list');
    if (!el) return;
    el.textContent = '';

    if (!data || !data.facts) { el.appendChild(errorState()); return; }
    if (!data.facts.length) { el.appendChild(emptyState('No facts found')); return; }

    data.facts.forEach(f => {
        const pinBtn = h('button', { class: 'btn-action', title: f.is_pinned ? 'Unpin' : 'Pin',
            onclick: (e) => { e.stopPropagation(); doTogglePin(f.id, f.is_pinned); }},
            f.is_pinned ? '\u2716' : '\uD83D\uDCCC');
        const promoteBtn = (!f.is_pinned || f.confidence !== 'confirmed') ?
            h('button', { class: 'btn-action', title: 'Promote (pin + confirm)',
                onclick: (e) => { e.stopPropagation(); doPromoteFact(f.id); }}, '\u2B06') : null;
        el.appendChild(h('div', { class: 'li li-actions' },
            h('div', { class: 'li-content' },
                h('div', { class: 'li-title' },
                    f.is_pinned ? h('span', { class: 'marker-pinned' }, '\uD83D\uDCCC') : null,
                    f.fact),
                h('div', { class: 'li-sub' },
                    badge(f.fact_type || 'fact', 'purple'), ' ',
                    f.category ? badge(f.category, 'blue') : null, ' ',
                    badge(f.confidence || '', 'gray'),
                    f.source ? [' \u00B7 ', f.source] : null,
                    ' \u00B7 ', timeAgo(f.created_at))),
            h('div', { class: 'li-btns' }, pinBtn, promoteBtn)));
    });
}

// ================================================================
// GOALS & TASKS TAB
// ================================================================

async function loadGoalsTasksTab() {
    const goalStatus = document.getElementById('goals-status')?.value || 'active';
    const taskStatus = document.getElementById('tasks-status')?.value || '';
    const pq = currentProject ? '&project=' + encodeURIComponent(currentProject) : '';

    const [goalsData, tasksData] = await Promise.all([
        fetchAPI(`/api/goals?status=${goalStatus}${pq}&limit=20`),
        fetchAPI(`/api/tasks${taskStatus ? '?status=' + taskStatus : '?'}${pq}&limit=30`)
    ]);

    // Goals
    const gl = document.getElementById('goals-detail');
    if (gl) {
        gl.textContent = '';
        if (!goalsData || !goalsData.goals) { gl.appendChild(errorState()); }
        else if (!goalsData.goals.length) { gl.appendChild(emptyState(`No ${goalStatus} goals`)); }
        else {
            goalsData.goals.forEach(g => {
                const total = g.total_tasks || 0, done = g.done_tasks || 0;
                const pct = total > 0 ? Math.round(done / total * 100) : 0;
                gl.appendChild(h('div', { class: 'li' },
                    h('div', { class: 'li-title' }, g.title),
                    h('div', { class: 'li-sub' },
                        badge(g.priority || 'medium', g.priority === 'high' || g.priority === 'critical' ? 'red' : 'gray'), ' ',
                        badge(g.status || 'active', g.status === 'active' ? 'green' : g.status === 'completed' ? 'blue' : 'gray'),
                        total > 0 ? ` \u00B7 ${done}/${total} tasks (${pct}%)` : '',
                        g.target_date ? ` \u00B7 Target: ${g.target_date}` : ''),
                    g.description ? h('div', { class: 'li-desc' }, trunc(g.description, 150)) : null,
                    total > 0 ? h('div', { class: 'progress' },
                        h('div', { class: `progress-fill ${pct === 100 ? 'complete' : ''}`, style: { width: pct + '%' } })) : null));
            });
        }
    }

    // Tasks
    const tl = document.getElementById('tasks-detail');
    if (tl) {
        tl.textContent = '';
        if (!tasksData || !tasksData.tasks) { tl.appendChild(errorState()); }
        else if (!tasksData.tasks.length) { tl.appendChild(emptyState('No tasks found')); }
        else {
            const statusIcon = { in_progress: '\u25B6', blocked: '\u26D4', todo: '\u25CB', done: '\u2713' };
            tasksData.tasks.forEach(t => {
                const btns = [];
                if (t.status !== 'in_progress') btns.push(h('button', { class: 'btn-action btn-action-sm', title: 'Start',
                    onclick: (e) => { e.stopPropagation(); doTaskStatus(t.id, 'in_progress'); }}, '\u25B6'));
                if (t.status !== 'done') btns.push(h('button', { class: 'btn-action btn-action-sm', title: 'Done',
                    onclick: (e) => { e.stopPropagation(); doTaskStatus(t.id, 'done'); }}, '\u2713'));
                if (t.status !== 'blocked') btns.push(h('button', { class: 'btn-action btn-action-sm', title: 'Block',
                    onclick: (e) => { e.stopPropagation(); doTaskStatus(t.id, 'blocked'); }}, '\u26D4'));
                tl.appendChild(h('div', { class: 'li li-actions' },
                    h('div', { class: 'li-content' },
                        h('div', { class: 'li-title' },
                            h('span', { class: `status-${t.status}` }, (statusIcon[t.status] || '\u25CB') + ' '),
                            t.title),
                        h('div', { class: 'li-sub' },
                            badge(t.priority || 'medium', t.status === 'blocked' ? 'red' : t.status === 'in_progress' ? 'blue' : 'gray'), ' ',
                            badge(t.status, t.status === 'done' ? 'green' : t.status === 'in_progress' ? 'blue' : t.status === 'blocked' ? 'red' : 'gray'),
                            t.blocked_by ? [' \u00B7 blocked: ', trunc(t.blocked_by, 30)] : null,
                            ' \u00B7 ', timeAgo(t.created_at)),
                        t.description ? h('div', { class: 'li-desc' }, trunc(t.description, 150)) : null),
                    h('div', { class: 'li-btns' }, ...btns)));
            });
        }
    }
}

// ================================================================
// TIMELINE TAB
// ================================================================

async function loadTimelineTab() {
    const days = document.getElementById('timeline-days')?.value || '30';
    const pq = currentProject ? '&project=' + encodeURIComponent(currentProject) : '';
    const data = await fetchAPI(`/api/timeline?days=${days}${pq}&limit=50`);
    const el = document.getElementById('timeline-detail');
    if (!el) return;
    el.textContent = '';

    if (!data || !data.timeline) { el.appendChild(errorState()); return; }
    if (!data.timeline.length) { el.appendChild(emptyState(`No events in last ${days} days`)); return; }

    const icons = {
        checkpoint_create: '\uD83D\uDCBE', checkpoint_restore: '\u21A9',
        decision: '\uD83D\uDCCB', fact_promoted: '\uD83D\uDCCC',
        pattern_detected: '\u26A0', goal_completed: '\u2713'
    };

    data.timeline.forEach(e => {
        el.appendChild(h('div', { class: 'tl-item' },
            h('div', { class: 'tl-icon' }, icons[e.type] || '\u2022'),
            h('div', { class: 'tl-content' },
                h('div', { class: 'tl-title' }, e.title || ''),
                h('div', { class: 'tl-detail' },
                    badge(e.type || 'event', 'gray'),
                    e.detail ? ` \u00B7 ${trunc(e.detail, 50)}` : '')),
            h('div', { class: 'tl-date' }, fmtDate(e.date))));
    });
}

// ================================================================
// CONTEXT TAB
// ================================================================

async function loadContextTab() {
    const mode = document.getElementById('context-mode')?.value || 'compact';
    const pq = currentProject ? '&project=' + encodeURIComponent(currentProject) : '';
    const data = await fetchAPI(`/api/context?mode=${mode}${pq}`);
    const el = document.getElementById('context-preview');
    if (!el) return;
    el.textContent = '';
    el.className = '';

    if (!data) { el.appendChild(errorState()); return; }
    if (data.error) { el.appendChild(errorState(data.error)); return; }

    // Meta section
    if (data.meta) {
        const meta = data.meta;
        el.appendChild(h('div', { class: 'ctx-section' },
            h('div', { class: 'ctx-header' }, `Context (mode: ${meta.mode || mode})`),
            h('div', { class: 'ctx-body' },
                h('div', { class: 'ctx-item' }, `Model: ${meta.model || 'none'} (${meta.provider || 'none'})`),
                meta.intent ? h('div', { class: 'ctx-item' }, `Intent: ${meta.intent}`) : null,
                meta.project ? h('div', { class: 'ctx-item' }, `Project: ${meta.project}`) : null)));
    }

    // Sections
    const sections = [
        ['Decisions', data.decisions],
        ['Facts', data.facts],
        ['Goals', data.goals],
        ['Tasks', data.tasks],
        ['Resolutions', data.resolutions]
    ];

    sections.forEach(([title, items]) => {
        if (!items || !items.length) return;
        const body = h('div', { class: 'ctx-body' });
        items.forEach(item => {
            const text = item.title || item.fact || item.text || item.error_summary || JSON.stringify(item);
            body.appendChild(h('div', { class: 'ctx-item' }, '\u2022 ' + trunc(text, 80)));
        });
        el.appendChild(h('div', { class: 'ctx-section' },
            h('div', { class: 'ctx-header' }, `${title} (${items.length})`),
            body));
    });

    if (!el.children.length) el.appendChild(emptyState('Empty context'));
}

// ================================================================
// HEALTH TAB
// ================================================================

async function loadHealthTab() {
    const pq = currentProject ? `?project=${encodeURIComponent(currentProject)}` : '';
    const data = await fetchAPI(`/api/health${pq}`);
    const el = document.getElementById('health-detail');
    if (!el) return;
    el.textContent = '';
    el.className = '';

    if (!data) { el.appendChild(errorState()); return; }

    const grid = h('div', { class: 'health-grid' });

    const hc = (label, val, cls) => h('div', { class: `health-card ${cls || ''}` },
        h('div', { class: 'hc-label' }, label),
        h('div', { class: 'hc-val' }, String(val ?? 0)));

    grid.appendChild(hc('Active Decisions', data.decisions, 'hc-ok'));
    grid.appendChild(hc('Active Facts', data.facts, 'hc-ok'));
    grid.appendChild(hc('Active Goals', data.goals, 'hc-ok'));
    grid.appendChild(hc('Active Tasks', data.tasks, 'hc-ok'));
    grid.appendChild(hc('Error Patterns', data.patterns));
    grid.appendChild(hc('Checkpoints', data.checkpoints));
    grid.appendChild(hc('Resolutions', data.resolutions));
    grid.appendChild(hc('Conflicts', data.conflicts, data.conflicts > 0 ? 'hc-danger' : ''));

    if (data.stale) {
        const sf = data.stale.stale_facts || 0;
        const st = data.stale.stale_tasks || 0;
        if (sf > 0) grid.appendChild(hc('Stale Facts', sf, 'hc-warn'));
        if (st > 0) grid.appendChild(hc('Stale Tasks', st, 'hc-warn'));
    }

    el.appendChild(grid);
}

// ================================================================
// ERRORS TAB
// ================================================================

async function loadErrorsTab() {
    const filter = document.getElementById('errors-filter')?.value || 'all';
    const pq = currentProject ? '&project=' + encodeURIComponent(currentProject) : '';
    const data = await fetchAPI(`/api/errors?filter=${filter}${pq}&limit=50`);
    const el = document.getElementById('errors-list');
    if (!el) return;
    el.textContent = '';

    if (!data || !data.errors) { el.appendChild(errorState()); return; }
    if (!data.errors.length) { el.appendChild(emptyState('No errors found')); return; }

    data.errors.forEach(e => {
        const resolved = e.solution && e.solution_worked;
        const statusBadge = resolved
            ? badge('\u2713 Resolved', 'green')
            : (e.solution ? badge('? Attempted', 'yellow') : badge('\u2717 Unresolved', 'red'));

        el.appendChild(h('div', { class: 'li err-item' },
            h('div', { class: 'li-title' },
                h('span', { style: { color: resolved ? 'var(--success)' : 'var(--danger)', marginRight: '6px' } },
                    resolved ? '\u2713' : '\u2717'),
                trunc(e.error_message || '', 80)),
            h('div', { class: 'li-sub' },
                badge(e.error_type || 'error', 'red'), ' ',
                e.language ? badge(e.language, 'blue') : null, ' ',
                e.framework ? badge(e.framework, 'purple') : null, ' ',
                statusBadge,
                ' \u00B7 ', timeAgo(e.created_at)),
            e.solution ? h('div', { class: 'li-desc', style: { color: 'var(--success)', marginTop: '6px' } },
                '\u2192 ' + trunc(e.solution, 150)) : null,
            e.file_path ? h('div', { class: 'li-desc', style: { fontSize: '0.75rem', color: 'var(--text-muted)' } },
                e.file_path) : null));
    });
}

// ================================================================
// SESSIONS TAB (V1 API)
// ================================================================

let sessionsPage = 1;

async function loadSessions(page) {
    if (page !== undefined) sessionsPage = page;
    const filter = document.getElementById('session-filter')?.value || '';
    const url = `/api/sessions?page=${sessionsPage}&limit=15${filter ? '&project=' + encodeURIComponent(filter) : ''}`;
    const data = await fetchAPI(url);
    const el = document.getElementById('sessions-list');
    if (!el) return;
    el.textContent = '';

    if (!data || !data.sessions) { el.appendChild(errorState()); return; }
    if (!data.sessions.length) { el.appendChild(emptyState('No sessions found')); return; }

    data.sessions.forEach(s => {
        const proj = s.project_path ? s.project_path.split('/').pop() : 'Unknown';
        el.appendChild(h('div', { class: 'v1-item', onclick: () => showSessionDetail(s.session_id) },
            h('h4', null, proj),
            h('div', { class: 'meta' }, `${fmtDate(s.started_at)} \u00B7 ${s.total_messages || 0} msgs \u00B7 ${s.total_tool_calls || 0} tools`),
            h('div', { class: 'meta', style: { fontSize: '0.72rem', marginTop: '4px' } }, 'ID: ' + (s.session_id || '').substring(0, 40) + '...')));
    });

    // Pagination
    const pg = document.getElementById('sessions-pagination');
    if (pg) {
        pg.textContent = '';
        if (data.pages > 1) {
            for (let i = 1; i <= Math.min(data.pages, 10); i++) {
                const btn = h('button', { class: i === sessionsPage ? 'active' : '', onclick: () => loadSessions(i) }, String(i));
                pg.appendChild(btn);
            }
        }
    }
}

async function showSessionDetail(sessionId) {
    const data = await fetchAPI(`/api/session/${sessionId}`);
    if (!data) return;
    const body = document.getElementById('modal-body');
    if (!body) return;
    body.textContent = '';
    const proj = data.project_path ? data.project_path.split('/').pop() : 'Unknown';
    body.appendChild(h('h2', { style: { marginBottom: '16px', color: 'var(--accent)' } }, 'Session: ' + proj));

    const info = [['ID', data.session_id], ['Path', data.project_path || 'N/A'],
        ['Started', fmtDate(data.started_at)], ['Ended', fmtDate(data.ended_at) || 'In progress'],
        ['Messages', data.total_messages || 0], ['Tools', data.total_tool_calls || 0]];
    info.forEach(([k, v]) => body.appendChild(h('p', null, h('strong', null, k + ': '), String(v))));

    if (data.messages && data.messages.length) {
        body.appendChild(h('h3', { style: { margin: '16px 0 8px' } }, `Messages (${data.messages.length})`));
        data.messages.forEach(m => {
            body.appendChild(h('div', { class: `v1-item role-${m.role}`, style: { margin: '6px 0' } },
                h('div', { class: 'meta' }, `${m.role} \u00B7 ${fmtDate(m.timestamp)}`),
                h('div', { class: 'content' }, trunc(m.content, 300))));
        });
    }

    document.getElementById('modal').style.display = 'block';
}

// ================================================================
// SEARCH TAB (V1 API)
// ================================================================

async function doSearch() {
    const query = document.getElementById('search-query')?.value || '';
    const mode = document.getElementById('search-mode')?.value || 'hybrid';
    if (!query.trim()) return;

    const el = document.getElementById('search-results');
    if (!el) return;
    el.textContent = '';
    el.appendChild(h('div', { class: 'ph' }, 'Searching...'));

    const data = await fetchAPI(`/api/search?q=${encodeURIComponent(query)}&mode=${mode}&limit=20`);
    el.textContent = '';

    if (!data) { el.appendChild(errorState()); return; }
    if (!data.results || !data.results.length) { el.appendChild(emptyState('No results found')); return; }

    el.appendChild(h('p', { style: { marginBottom: '12px', color: 'var(--text-muted)', fontSize: '0.85rem' } },
        `Found ${data.count} results (mode: ${data.mode})`));

    data.results.forEach(r => {
        el.appendChild(h('div', { class: `v1-item role-${r.role || 'unknown'}` },
            h('div', { class: 'meta' }, `${r.source_table || 'messages'} #${r.id}`),
            h('div', { class: 'content' }, trunc(r.content || r.document || '', 300)),
            h('div', { class: 'meta', style: { marginTop: '4px' } }, fmtDate(r.timestamp))));
    });
}

// Enter key for search
document.getElementById('search-query')?.addEventListener('keypress', e => {
    if (e.key === 'Enter') doSearch();
});

// ================================================================
// BRANCHES TAB
// ================================================================

async function loadBranchesTab() {
    const qs = currentProject ? `?project=${encodeURIComponent(currentProject)}` : '';
    const data = await fetchAPI(`/api/branches${qs}`);
    const el = document.getElementById('branches-content');
    if (!el) return;
    el.textContent = '';
    el.className = '';

    if (!data || !data.branches) {
        el.appendChild(errorState('Failed to load branches'));
        return;
    }

    window._currentBranch = data.current || 'main';

    const branches = data.branches;
    if (!branches.length) {
        el.appendChild(emptyState('No branches found'));
        return;
    }

    // Branch list
    const list = h('div', { class: 'branch-list' });
    branches.forEach(b => {
        const isCurrent = b.name === data.current;
        const btns = [];

        if (!isCurrent) {
            btns.push(h('button', { class: 'btn-action', title: 'Switch to this branch',
                onclick: (e) => { e.stopPropagation(); doBranchSwitch(b.name); }}, '\u21C0'));
        }
        if (b.name !== 'main') {
            btns.push(h('button', { class: 'btn-action', title: 'Compare with main',
                onclick: (e) => { e.stopPropagation(); showBranchCompare('main', b.name); }}, '\u2194'));
            btns.push(h('button', { class: 'btn-action', title: 'Merge into main',
                onclick: (e) => { e.stopPropagation(); showMergePreview(b.name, 'main'); }}, '\u{1F500}'));
        }

        const card = h('div', { class: `branch-card ${isCurrent ? 'branch-current' : ''}` },
            h('div', { class: 'branch-info' },
                h('div', { class: 'branch-name' },
                    b.name,
                    isCurrent ? badge('current', 'blue') : null,
                    b.name === 'main' ? badge('default', 'gray') : null),
                h('div', { class: 'branch-meta' },
                    `${b.entity_count || 0} entities`,
                    b.parent_branch ? ` \u00B7 from: ${b.parent_branch}` : '',
                    b.description ? ` \u00B7 ${trunc(b.description, 40)}` : '',
                    b.created_at ? ` \u00B7 ${timeAgo(b.created_at)}` : '')),
            h('div', { class: 'branch-actions' }, ...btns));
        list.appendChild(card);
    });
    el.appendChild(list);

    // Compare panel (initially empty)
    const comparePanel = h('div', { id: 'branch-compare-panel' });
    el.appendChild(comparePanel);

    // Refresh topbar to show/hide branch chip
    const dashQs = currentProject ? `?project=${encodeURIComponent(currentProject)}` : '';
    const dashData = await fetchAPI(`/api/dashboard${dashQs}`);
    if (dashData && dashData.summary) renderTopbar(dashData.summary);
}

async function doBranchSwitch(name) {
    const data = await postAPI('/api/branches/switch', { branch: name, project: currentProject });
    if (data && data.success) {
        toast(data.message, 'success');
        window._currentBranch = name;
        loadBranchesTab();
    }
}

async function showBranchCompare(branchA, branchB) {
    const qs = `?project=${encodeURIComponent(currentProject)}&a=${encodeURIComponent(branchA)}&b=${encodeURIComponent(branchB)}`;
    const data = await fetchAPI(`/api/branches/compare${qs}`);
    const panel = document.getElementById('branch-compare-panel');
    if (!panel) return;
    panel.textContent = '';

    if (!data || data.error) {
        panel.appendChild(errorState(data ? data.error : 'Failed to compare'));
        return;
    }

    const s = data.summary || {};

    if (s.identical) {
        panel.appendChild(h('div', { class: 'panel', style: { marginTop: '16px' } },
            h('div', { class: 'panel-hdr' }, h('h3', null, `Compare: ${s.branch_a} \u2194 ${s.branch_b}`)),
            h('div', { class: 'panel-body' },
                h('div', { class: 'empty-state' }, 'Branches are identical \u2014 no differences'))));
        return;
    }

    const content = h('div', { class: 'panel', style: { marginTop: '16px' } });
    content.appendChild(h('div', { class: 'panel-hdr' },
        h('h3', null, `Compare: ${s.branch_a} \u2194 ${s.branch_b}`),
        h('button', { class: 'btn btn-sm', onclick: () => showMergePreview(s.branch_b, s.branch_a) }, 'Merge Preview')));

    const body = h('div', { class: 'panel-body compare-section' });

    // Summary bar
    const summaryDiv = h('div', { class: 'merge-summary' },
        h('div', { class: 'merge-summary-row' },
            h('span', { class: 'merge-summary-label' }, `Only in ${s.branch_a}:`),
            h('span', { class: 'merge-summary-value compare-only-a' }, String(s.only_in_a))),
        h('div', { class: 'merge-summary-row' },
            h('span', { class: 'merge-summary-label' }, `Only in ${s.branch_b}:`),
            h('span', { class: 'merge-summary-value compare-only-b' }, String(s.only_in_b))),
        h('div', { class: 'merge-summary-row' },
            h('span', { class: 'merge-summary-label' }, 'Conflicts:'),
            h('span', { class: 'merge-summary-value compare-conflict' }, String(s.conflicts))));
    body.appendChild(summaryDiv);

    const TABLE_LABELS = {
        decisions: 'Decisions', learned_facts: 'Facts', goals: 'Goals',
        tasks: 'Tasks', error_resolutions: 'Resolutions'
    };

    // Per-category details
    const allTables = new Set([
        ...Object.keys(data.only_a || {}),
        ...Object.keys(data.only_b || {}),
        ...Object.keys(data.conflicts || {})
    ]);

    allTables.forEach(table => {
        const catDiv = h('div', { class: 'compare-category' });
        catDiv.appendChild(h('div', { class: 'compare-category-hdr' }, TABLE_LABELS[table] || table));

        const onlyA = (data.only_a || {})[table] || [];
        const onlyB = (data.only_b || {})[table] || [];
        const conflicts = (data.conflicts || {})[table] || [];

        if (onlyA.length) {
            catDiv.appendChild(h('div', { class: 'compare-side-label compare-only-a' }, `Only in ${s.branch_a}:`));
            onlyA.forEach(item => {
                catDiv.appendChild(h('div', { class: 'compare-item' }, `#${item.id} ${trunc(item.title, 50)}`));
            });
        }
        if (onlyB.length) {
            catDiv.appendChild(h('div', { class: 'compare-side-label compare-only-b' }, `Only in ${s.branch_b}:`));
            onlyB.forEach(item => {
                catDiv.appendChild(h('div', { class: 'compare-item' }, `#${item.id} ${trunc(item.title, 50)}`));
            });
        }
        if (conflicts.length) {
            catDiv.appendChild(h('div', { class: 'compare-side-label compare-conflict' }, `\u26A0 Conflicts (${conflicts.length}):`));
            conflicts.forEach(cf => {
                catDiv.appendChild(h('div', { class: 'compare-item compare-conflict' },
                    `#${cf.a.id} (${s.branch_a}) \u2194 #${cf.b.id} (${s.branch_b}): ${trunc(cf.title, 40)}`));
            });
        }
        body.appendChild(catDiv);
    });

    content.appendChild(body);
    panel.appendChild(content);
}

async function showMergePreview(source, target) {
    const qs = `?project=${encodeURIComponent(currentProject)}&a=${encodeURIComponent(target)}&b=${encodeURIComponent(source)}`;
    const data = await fetchAPI(`/api/branches/compare${qs}`);

    const body = document.getElementById('modal-body');
    if (!body) return;
    body.textContent = '';

    body.appendChild(h('h2', { style: { marginBottom: '16px', color: 'var(--accent)' } },
        `Merge Preview: ${source} \u2192 ${target}`));

    if (!data || data.error) {
        body.appendChild(errorState(data ? data.error : 'Failed to load preview'));
        document.getElementById('modal').style.display = 'block';
        return;
    }

    const s = data.summary || {};

    if (s.identical) {
        body.appendChild(h('div', { class: 'empty-state' }, 'Branches are identical \u2014 nothing to merge'));
        document.getElementById('modal').style.display = 'block';
        return;
    }

    // Summary
    const summaryDiv = h('div', { class: 'merge-summary' },
        h('div', { class: 'merge-summary-row' },
            h('span', { class: 'merge-summary-label' }, `Entities to merge (from ${source}):`),
            h('span', { class: 'merge-summary-value' }, String(s.only_in_b))),
        h('div', { class: 'merge-summary-row' },
            h('span', { class: 'merge-summary-label' }, `Already in ${target}:`),
            h('span', { class: 'merge-summary-value' }, String(s.only_in_a))),
        h('div', { class: 'merge-summary-row' },
            h('span', { class: 'merge-summary-label' }, 'Conflicts:'),
            h('span', { class: `merge-summary-value ${s.conflicts > 0 ? 'compare-conflict' : ''}` }, String(s.conflicts))));
    body.appendChild(summaryDiv);

    if (s.conflicts > 0) {
        body.appendChild(h('div', { style: { color: 'var(--warning)', fontSize: '0.85rem', marginBottom: '12px' } },
            '\u26A0 Conflicts will be auto-resolved (source entities moved to target branch)'));
    }

    // Entity details from source (only_b since we compare target vs source)
    const TABLE_LABELS = {
        decisions: 'Decisions', learned_facts: 'Facts', goals: 'Goals',
        tasks: 'Tasks', error_resolutions: 'Resolutions'
    };
    const onlyB = data.only_b || {};
    if (Object.keys(onlyB).length) {
        body.appendChild(h('div', { style: { fontSize: '0.82rem', fontWeight: '600', color: 'var(--text-dim)', marginTop: '12px', marginBottom: '6px' } },
            'Entities to be merged:'));
        for (const [table, items] of Object.entries(onlyB)) {
            const label = TABLE_LABELS[table] || table;
            items.forEach(item => {
                body.appendChild(h('div', { class: 'compare-item' }, `[${label}] #${item.id} ${trunc(item.title, 45)}`));
            });
        }
    }

    // Merge button
    const mergeBtn = h('button', { class: 'btn', style: { marginTop: '20px', width: '100%' },
        onclick: async () => {
            mergeBtn.disabled = true;
            mergeBtn.textContent = 'Merging...';
            const result = await postAPI('/api/branches/merge', {
                source, target, confirm: true, project: currentProject
            });
            if (result && result.success) {
                toast(result.message, 'success');
                closeModal();
                loadBranchesTab();
            } else {
                mergeBtn.disabled = false;
                mergeBtn.textContent = `Merge ${source} \u2192 ${target}`;
            }
        }
    }, `Merge ${source} \u2192 ${target}`);
    body.appendChild(mergeBtn);

    document.getElementById('modal').style.display = 'block';
}

// ================================================================
// EVENTS TAB — Agent Event Stream
// ================================================================

const EVENT_ICONS = {
    agent_started: '\u25B6', agent_finished: '\u2705', agent_error: '\u274C',
    context_requested: '\uD83D\uDCE5', context_received: '\uD83D\uDCE4',
    decision_created: '\u2696', fact_created: '\uD83D\uDCDD', goal_created: '\uD83C\uDFAF',
    task_created: '\u2611', task_updated: '\uD83D\uDD04', resolution_created: '\uD83D\uDD27',
    branch_switched: '\uD83D\uDD00', branch_compared: '\u2194', branch_merged: '\uD83D\uDD00',
    checkpoint_created: '\uD83D\uDCBE', checkpoint_restored: '\u21A9',
    api_call: '\uD83C\uDF10', ui_action: '\uD83D\uDDB1',
};

const EVENT_COLORS = {
    agent_started: 'cyan', agent_finished: 'green', agent_error: 'red',
    context_requested: 'blue', context_received: 'blue',
    decision_created: 'purple', fact_created: 'yellow', goal_created: 'blue',
    task_created: 'blue', task_updated: 'gray', resolution_created: 'green',
    branch_switched: 'purple', branch_compared: 'gray', branch_merged: 'purple',
    checkpoint_created: 'cyan', checkpoint_restored: 'cyan',
    api_call: 'gray', ui_action: 'gray',
};

async function loadEventsTab() {
    const type = document.getElementById('events-type')?.value || '';
    const agent = document.getElementById('events-agent')?.value.trim() || '';
    const model = document.getElementById('events-model')?.value.trim() || '';
    const branch = document.getElementById('events-branch')?.value.trim() || '';
    const failedOnly = document.getElementById('events-failed')?.checked;
    const pq = currentProject ? '&project=' + encodeURIComponent(currentProject) : '';
    let qs = `?limit=100${pq}`;
    if (type) qs += `&type=${type}`;
    if (agent) qs += `&agent=${encodeURIComponent(agent)}`;
    if (model) qs += `&model=${encodeURIComponent(model)}`;
    if (branch) qs += `&branch=${encodeURIComponent(branch)}`;
    if (failedOnly) qs += '&failed=true';

    const data = await fetchAPI(`/api/events${qs}`);
    const el = document.getElementById('events-list');
    if (!el) return;
    el.textContent = '';

    if (!data || !data.events) { el.appendChild(errorState()); return; }
    if (!data.events.length) { el.appendChild(emptyState('No events found')); return; }

    // Group by session for replay button
    const sessions = {};
    data.events.forEach(ev => {
        const sid = ev.session_id || '_none';
        if (!sessions[sid]) sessions[sid] = [];
        sessions[sid].push(ev);
    });

    // Render events
    data.events.forEach(ev => {
        const icon = EVENT_ICONS[ev.event_type] || '\u2022';
        const color = EVENT_COLORS[ev.event_type] || 'gray';
        const ok = ev.success_flag !== 0;

        const chips = [];
        if (ev.event_type) chips.push(badge(ev.event_type.replace(/_/g, ' '), color));
        if (ev.event_phase && ev.event_phase !== 'end') chips.push(badge(ev.event_phase, 'gray'));
        if (ev.agent_name) chips.push(badge(ev.agent_name, 'purple'));
        if (ev.model_name) chips.push(badge(ev.model_name, 'gray'));
        if (ev.branch_name) chips.push(badge(ev.branch_name, 'cyan'));
        if (ev.duration_ms) chips.push(badge(ev.duration_ms + 'ms', 'gray'));

        const row = h('div', { class: `li ev-item${ok ? '' : ' ev-failed'}`, onclick: () => showEventDetail(ev) },
            h('div', { class: 'li-title' },
                h('span', { class: 'ev-icon', textContent: icon }),
                ok ? null : h('span', { class: 'ev-fail-marker', textContent: '\u2717' }),
                ev.title || ev.event_type.replace(/_/g, ' ')),
            h('div', { class: 'li-sub' }, chips, ' \u00B7 ', fmtDate(ev.created_at)),
            ev.summary ? h('div', { class: 'li-desc' }, trunc(ev.summary, 200)) : null);

        el.appendChild(row);
    });

    // Replay buttons for sessions with 3+ events
    const replaySessions = Object.entries(sessions).filter(([sid, evs]) => sid !== '_none' && evs.length >= 3);
    if (replaySessions.length > 0) {
        const replayBar = h('div', { class: 'ev-replay-bar' },
            h('span', { class: 'ev-replay-label' }, 'Agent Replay:'),
            replaySessions.map(([sid, evs]) => {
                const agentName = evs.find(e => e.agent_name)?.agent_name || sid.substring(0, 8);
                return h('button', { class: 'btn-sm ev-replay-btn', onclick: () => showEventReplay(evs, agentName) },
                    agentName + ` (${evs.length})`);
            }));
        el.insertBefore(replayBar, el.firstChild);
    }
}

function showEventDetail(ev) {
    const body = document.getElementById('modal-body');
    if (!body) return;
    body.textContent = '';

    body.appendChild(h('h2', { style: { marginBottom: '16px', color: 'var(--accent)' } },
        (EVENT_ICONS[ev.event_type] || '') + ' ' + (ev.title || ev.event_type)));

    const fields = [
        ['Type', ev.event_type], ['Phase', ev.event_phase], ['Status', ev.status],
        ['Agent', ev.agent_name], ['Model', ev.model_name], ['Provider', ev.provider],
        ['Branch', ev.branch_name], ['Session', ev.session_id],
        ['Success', ev.success_flag !== 0 ? 'Yes' : 'No'],
        ['Duration', ev.duration_ms ? ev.duration_ms + 'ms' : null],
        ['Started', ev.started_at], ['Finished', ev.finished_at],
        ['Created', ev.created_at],
        ['Related', ev.related_table ? ev.related_table + '#' + ev.related_id : null],
        ['Parent Event', ev.parent_event_id],
        ['Project', ev.project_path],
    ];

    const grid = h('div', { class: 'ev-detail-grid' });
    fields.forEach(([label, val]) => {
        if (val === null || val === undefined) return;
        grid.appendChild(h('div', { class: 'ev-detail-label' }, label));
        grid.appendChild(h('div', { class: 'ev-detail-value' }, String(val)));
    });
    body.appendChild(grid);

    if (ev.summary) {
        body.appendChild(h('h3', { style: { margin: '16px 0 8px', color: 'var(--text-dim)', fontSize: '0.85rem' } }, 'Summary'));
        body.appendChild(h('div', { class: 'ev-detail-text' }, ev.summary));
    }

    if (ev.detail) {
        body.appendChild(h('h3', { style: { margin: '16px 0 8px', color: 'var(--text-dim)', fontSize: '0.85rem' } }, 'Detail'));
        body.appendChild(h('div', { class: 'ev-detail-text' }, ev.detail));
    }

    if (ev.metadata_json) {
        body.appendChild(h('h3', { style: { margin: '16px 0 8px', color: 'var(--text-dim)', fontSize: '0.85rem' } }, 'Metadata'));
        try {
            const meta = typeof ev.metadata_json === 'string' ? JSON.parse(ev.metadata_json) : ev.metadata_json;
            body.appendChild(h('pre', { class: 'ev-detail-pre' }, JSON.stringify(meta, null, 2)));
        } catch { body.appendChild(h('pre', { class: 'ev-detail-pre' }, ev.metadata_json)); }
    }

    document.getElementById('modal').style.display = 'block';
}

function showEventReplay(events, agentName) {
    const body = document.getElementById('modal-body');
    if (!body) return;
    body.textContent = '';

    // Sort chronologically
    const sorted = [...events].sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));

    body.appendChild(h('h2', { style: { marginBottom: '8px', color: 'var(--accent)' } },
        '\uD83D\uDD01 Agent Replay: ' + agentName));

    // Summary bar
    const totalDuration = sorted.reduce((sum, e) => sum + (e.duration_ms || 0), 0);
    const errors = sorted.filter(e => !e.success_flag).length;
    const types = [...new Set(sorted.map(e => e.event_type))];
    body.appendChild(h('div', { class: 'ev-replay-summary' },
        h('span', null, sorted.length + ' events'),
        totalDuration > 0 ? h('span', null, '\u00B7 ' + totalDuration + 'ms total') : null,
        errors > 0 ? h('span', { style: { color: 'var(--danger)' } }, '\u00B7 ' + errors + ' errors') : null,
        h('span', { class: 'badge badge-gray' }, types.length + ' types')));

    // Timeline
    const timeline = h('div', { class: 'ev-replay-timeline' });
    sorted.forEach((ev, i) => {
        const icon = EVENT_ICONS[ev.event_type] || '\u2022';
        const color = EVENT_COLORS[ev.event_type] || 'gray';
        const ok = ev.success_flag !== 0;

        const item = h('div', { class: `ev-replay-item${ok ? '' : ' ev-failed'}` },
            h('div', { class: 'ev-replay-line' },
                h('div', { class: `ev-replay-dot ev-dot-${color}` }),
                i < sorted.length - 1 ? h('div', { class: 'ev-replay-connector' }) : null),
            h('div', { class: 'ev-replay-content' },
                h('div', { class: 'ev-replay-hdr' },
                    h('span', { class: 'ev-icon' }, icon),
                    h('span', { class: 'ev-replay-title' }, ev.title || ev.event_type.replace(/_/g, ' ')),
                    badge(ev.event_type.replace(/_/g, ' '), color),
                    ev.duration_ms ? h('span', { class: 'ev-replay-dur' }, ev.duration_ms + 'ms') : null),
                h('div', { class: 'ev-replay-time' }, fmtDate(ev.created_at)),
                ev.summary ? h('div', { class: 'ev-replay-desc' }, trunc(ev.summary, 150)) : null));

        timeline.appendChild(item);
    });

    body.appendChild(timeline);
    document.getElementById('modal').style.display = 'block';
}

// ================================================================
// MODAL
// ================================================================

function closeModal() { document.getElementById('modal').style.display = 'none'; }
window.addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ================================================================
// INIT
// ================================================================

document.addEventListener('DOMContentLoaded', () => { loadDashboard(); });

// ================================================================
// ORCHESTRATION (18E)
// ================================================================

async function loadOrch() {
    const view = document.getElementById('orch-view')?.value || 'projects';
    switch (view) {
        case 'projects': await loadOrchProjects(); break;
        case 'tasks': await loadOrchTasks(); break;
        case 'agents': await loadOrchAgents(); break;
        case 'deliberation': await loadOrchDeliberation(); break;
        case 'messages': await loadOrchMessages(); break;
        case 'reviews': await loadOrchReviews(); break;
    }
}

function _orchPopulateProjectFilter(projects) {
    const filter = document.getElementById('orch-project-filter');
    const currentVal = filter.value;
    while (filter.options.length > 1) filter.remove(1);
    projects.forEach(function(p) {
        var opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.title;
        filter.appendChild(opt);
    });
    filter.value = currentVal;
}

async function loadOrchProjects() {
    var el = document.getElementById('orch-content');
    el.textContent = 'Loading...';
    var data = await fetchAPI('/api/v1/orch/projects');
    el.textContent = '';
    if (!data) { el.appendChild(errorState()); return; }
    if (!data.length) { el.appendChild(emptyState('No projects yet')); return; }

    _orchPopulateProjectFilter(data);

    var statusColors = { active: 'blue', completed: 'green', paused: 'yellow', failed: 'red' };
    data.forEach(function(p) {
        var stats = (p.done_count || 0) + '/' + (p.task_count || 0) + ' done';
        var extra = '';
        if (p.pending_count) extra += ', ' + p.pending_count + ' pending';
        if (p.in_progress_count) extra += ', ' + p.in_progress_count + ' in progress';
        el.appendChild(h('div', { class: 'li', onclick: function() {
            document.getElementById('orch-project-filter').value = p.id;
            document.getElementById('orch-view').value = 'tasks';
            loadOrch();
        }, style: { cursor: 'pointer' } },
            h('div', { class: 'li-title' }, p.title),
            h('div', { class: 'li-sub' },
                badge(p.status || 'active', statusColors[p.status] || 'gray'),
                badge(p.orchestrator_cli || '?', 'purple'),
                h('span', {}, ' ' + stats + extra),
                h('span', { class: 'text-muted' }, ' ' + timeAgo(p.created_at))
            )
        ));
    });
}

async function loadOrchTasks() {
    var el = document.getElementById('orch-content');
    el.textContent = 'Loading...';
    var projId = document.getElementById('orch-project-filter')?.value || '';
    var qs = projId ? '?project_id=' + projId : '';
    var data = await fetchAPI('/api/v1/orch/tasks' + qs);
    el.textContent = '';
    if (!data) { el.appendChild(errorState()); return; }
    if (!data.length) { el.appendChild(emptyState('No tasks')); return; }

    var priorityColors = { critical: 'red', high: 'yellow', medium: 'blue', low: 'gray' };
    var statusColors = { pending: 'gray', assigned: 'cyan', in_progress: 'blue', done: 'green', failed: 'red', blocked: 'yellow' };
    var groups = {};
    data.forEach(function(t) {
        var s = t.status || 'pending';
        if (!groups[s]) groups[s] = [];
        groups[s].push(t);
    });

    ['in_progress', 'pending', 'assigned', 'blocked', 'done', 'failed'].forEach(function(status) {
        var tasks = groups[status];
        if (!tasks) return;
        el.appendChild(h('div', { class: 'sec-title', style: { margin: '12px 0 4px', fontSize: '13px', opacity: 0.7 } },
            status.toUpperCase() + ' (' + tasks.length + ')'));
        tasks.forEach(function(t) {
            var parts = [
                badge(t.status, statusColors[t.status] || 'gray'),
                badge(t.priority || 'medium', priorityColors[t.priority] || 'blue'),
            ];
            if (t.assigned_cli) parts.push(badge(t.assigned_cli, 'purple'));
            if (t.lease_expires_at && t.status === 'in_progress') {
                var exp = new Date(t.lease_expires_at);
                var mins = Math.round((exp - Date.now()) / 60000);
                parts.push(h('span', { class: mins < 5 ? 'text-warn' : 'text-muted' }, ' lease: ' + mins + 'min'));
            }
            el.appendChild(h('div', { class: 'li' },
                h('div', { class: 'li-title' }, t.title),
                h('div', { class: 'li-sub' }, ...parts),
                t.description ? h('div', { class: 'li-desc' }, t.description) : null
            ));
        });
    });
}

async function loadOrchAgents() {
    var el = document.getElementById('orch-content');
    el.textContent = 'Loading...';
    var data = await fetchAPI('/api/v1/orch/agents');
    el.textContent = '';
    if (!data) { el.appendChild(errorState()); return; }
    if (!data.length) { el.appendChild(emptyState('No agents registered yet')); return; }

    var dotClass = { online: 'status-online', busy: 'status-busy', offline: 'status-offline' };
    data.forEach(function(a) {
        var status = a.status || 'offline';
        el.appendChild(h('div', { class: 'li' },
            h('div', { class: 'li-title' },
                h('span', { class: 'status-dot ' + (dotClass[status] || 'status-offline') }),
                ' ' + a.cli_name),
            h('div', { class: 'li-sub' },
                badge(status, status === 'online' ? 'green' : status === 'busy' ? 'yellow' : 'gray'),
                a.current_task_id ? h('span', {}, ' Task #' + a.current_task_id) : null,
                a.last_seen ? h('span', { class: 'text-muted' }, ' ' + timeAgo(a.last_seen)) : null
            )
        ));
    });
}

async function loadOrchDeliberation() {
    var el = document.getElementById('orch-content');
    el.textContent = 'Loading...';
    var projId = document.getElementById('orch-project-filter')?.value || '';
    var qs = projId ? '?project_id=' + projId : '';
    var data = await fetchAPI('/api/v1/orch/deliberation' + qs);
    el.textContent = '';
    if (!data) { el.appendChild(errorState()); return; }
    if (!data.length) { el.appendChild(emptyState('No deliberation sessions')); return; }

    var typeColors = { quick: 'gray', deep: 'blue', expert: 'purple' };
    var consensusColors = { full: 'green', high: 'green', moderate: 'yellow', low: 'yellow', none: 'red' };
    data.forEach(function(s) {
        var parts = [
            badge(s.session_type || 'quick', typeColors[s.session_type] || 'gray'),
            badge(s.status || 'active', s.status === 'completed' ? 'green' : 'blue'),
        ];
        if (s.status !== 'completed') {
            parts.push(h('span', {}, ' Round ' + s.current_round + '/' + s.total_rounds));
        }
        if (s.consensus_level) {
            parts.push(badge(s.consensus_level, consensusColors[s.consensus_level] || 'gray'));
        }
        var clis = (s.participating_clis || []).join(', ');

        var item = h('div', { class: 'li', style: { cursor: 'pointer' } },
            h('div', { class: 'li-title' }, s.topic),
            h('div', { class: 'li-sub' }, ...parts),
            h('div', { class: 'li-desc' }, 'Participants: ' + clis +
                (s.proposal_count ? ' | ' + s.proposal_count + ' proposals' : '') +
                (s.vote_count ? ' | ' + s.vote_count + ' votes' : ''))
        );

        item.addEventListener('click', async function() {
            var existing = item.querySelector('.delib-detail');
            if (existing) { existing.remove(); return; }
            var detail = await fetchAPI('/api/v1/orch/deliberation/' + s.id);
            if (!detail) return;
            var detailEl = h('div', { class: 'delib-detail', style: { padding: '8px 0 0', borderTop: '1px solid var(--border)' } });
            if (detail.proposals && detail.proposals.length) {
                var byRound = {};
                detail.proposals.forEach(function(p) {
                    if (!byRound[p.round_number]) byRound[p.round_number] = [];
                    byRound[p.round_number].push(p);
                });
                Object.keys(byRound).sort().forEach(function(rn) {
                    detailEl.appendChild(h('div', { style: { fontWeight: '600', fontSize: '12px', margin: '6px 0 2px', opacity: '0.7' } },
                        'Round ' + rn + ' (' + (byRound[rn][0]?.round_phase || '?') + ')'));
                    byRound[rn].forEach(function(p) {
                        var text = p.content.length > 200 ? p.content.substring(0, 200) + '...' : p.content;
                        detailEl.appendChild(h('div', { style: { padding: '2px 0 2px 12px', fontSize: '13px' } },
                            badge(p.cli_name, 'purple'), ' ' + text
                        ));
                    });
                });
            }
            if (detail.votes && detail.votes.length) {
                detailEl.appendChild(h('div', { style: { fontWeight: '600', fontSize: '12px', margin: '6px 0 2px', opacity: '0.7' } }, 'Votes'));
                detail.votes.forEach(function(v) {
                    detailEl.appendChild(h('div', { style: { padding: '2px 0 2px 12px', fontSize: '13px' } },
                        badge(v.cli_name, 'purple'), ' voted: ' + v.voted_for));
                });
            }
            item.appendChild(detailEl);
        });
        el.appendChild(item);
    });
}

async function loadOrchMessages() {
    var el = document.getElementById('orch-content');
    el.textContent = 'Loading...';
    var data = await fetchAPI('/api/v1/orch/messages?limit=30');
    el.textContent = '';
    if (!data) { el.appendChild(errorState()); return; }
    if (!data.length) { el.appendChild(emptyState('No messages')); return; }

    var typeColors = { info: 'blue', question: 'yellow', answer: 'green', review: 'purple', correction: 'red', handoff: 'cyan' };
    data.forEach(function(m) {
        var to = m.to_cli || 'broadcast';
        el.appendChild(h('div', { class: 'li' },
            h('div', { class: 'li-title' },
                badge(m.from_cli, 'purple'),
                h('span', { style: { opacity: '0.5', margin: '0 4px' } }, '\u2192'),
                badge(to, to === 'broadcast' ? 'cyan' : 'gray')),
            h('div', { class: 'li-sub' },
                badge(m.message_type || 'info', typeColors[m.message_type] || 'gray'),
                h('span', { class: 'text-muted' }, ' ' + timeAgo(m.created_at))
            ),
            h('div', { class: 'li-desc' }, m.content)
        ));
    });
}

async function loadOrchReviews() {
    var el = document.getElementById('orch-content');
    el.textContent = 'Loading...';
    var projId = document.getElementById('orch-project-filter')?.value || '';
    var qs = projId ? '?project_id=' + projId : '';
    var data = await fetchAPI('/api/v1/orch/reviews' + qs);
    el.textContent = '';
    if (!data) { el.appendChild(errorState()); return; }
    if (!data.length) { el.appendChild(emptyState('No reviews yet')); return; }

    var verdictColors = { approve: 'green', changes_requested: 'yellow', blocked: 'red', security_risk: 'red' };
    var sevColors = { info: 'gray', warning: 'yellow', critical: 'red' };
    data.forEach(function(r) {
        el.appendChild(h('div', { class: 'li' },
            h('div', { class: 'li-title' },
                'Task #' + r.task_id + ': ' + (r.task_title || '?')),
            h('div', { class: 'li-sub' },
                badge(r.verdict, verdictColors[r.verdict] || 'gray'),
                badge(r.severity || 'info', sevColors[r.severity] || 'gray'),
                badge(r.reviewer_cli, 'purple'),
                h('span', { style: { opacity: '0.5', margin: '0 4px' } }, 'reviewed'),
                badge(r.original_cli || '?', 'cyan'),
                h('span', { class: 'text-muted' }, ' ' + timeAgo(r.created_at))
            ),
            r.comments ? h('div', { class: 'li-desc' }, r.comments.substring(0, 300)) : null
        ));
    });
}
