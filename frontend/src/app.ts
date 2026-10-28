import { intakeMode } from './intake-mode';

type Money = { minor: number; currency: string };
type Address = { name: string; line1: string; city: string; postcode: string; country: string };
type CaseStatus = 'received' | 'investigating' | 'needs-information' | 'proposal-ready' | 'awaiting-approval' | 'executing' | 'reconciling' | 'resolved' | 'escalated' | 'failed';
type CaseSummary = {
  id: string; order_id: string; customer_name: string; intent: string; status: CaseStatus;
  reason: string; updated_at: string; amount: Money; issue_count: number; approved?: boolean;
};
type Action = { id: string; kind: string; title: string; amount?: Money | null; label_id?: string | null; address?: Address | null };
type Plan = { id: string; hash: string; resource_version: number; actions: Action[]; created_at: string; hold_ack_id?: string | null };
type Evidence = { id: string; source: string; kind: string; message: string; created_at: string; data: Record<string, unknown> };
type Attempt = { verified_at?: string | null; operator_id?: string; resource_version?: number; result_version?: number | null; retryable?: boolean; id: string; kind: string; action_id: string; status: string; idempotency_key: string; provider_id?: string | null; error?: string | null; created_at: string; updated_at: string };
type Order = {
  id: string; version: number; store_id: string; woo_id: number; shipstation_order_id: number;
  customer_name: string; commercial_state: string; address: Address;
  payment: { captured: Money; refunds: { id?: string; amount: Money }[] };
  lines: { id: string; sku: string; title: string; quantity: number; unit_price: Money; refunded_quantity: number; dispatched_quantity: number }[];
  labels: { id: string; shipment_id: string; status: string; tracking: string | null; address: Address }[];
  shipments: { id: string; status: string; line_quantities: Record<string, number> }[];
  warehouse: { state: string; ack_id?: string | null; acknowledged_at?: string | null; expires_at?: string | null; reliable: boolean };
  tracking: string[]; observed_at: string;
};
type CaseView = CaseSummary & {
  request: { text: string; intent: string; target_address: Address | null };
  order: Order | null; plan: Plan | null;
  approvals: { id: string; plan_hash: string; resource_version: number; created_at: string; operator_id: string; amount?: Money | null }[];
  attempts: Attempt[]; warehouse_attempts?: Attempt[]; evidence: Evidence[]; disagreements: { code: string; severity: string; message: string }[];
  draft: string | null; interpreter_mode: string;
  permitted: { investigate: boolean; approve: boolean; execute: boolean; hold: boolean; retry: boolean };
};
type Meta = { mode: string; interpreter_mode: string; operator: { id: string; name: string; role: string }; capabilities: { live_mutations: boolean } };
type ListResult = { cases: CaseSummary[]; stats: { open: number; needs_attention: number; awaiting_approval: number; resolved: number } };
type Filter = 'all' | 'attention' | 'approval' | 'resolved';
type Tab = 'recovery' | 'evidence' | 'customer';

const icons: Record<string, string> = {
  box: '<path d="m4 7 8-4 8 4v10l-8 4-8-4Z"/><path d="m4 7 8 4 8-4M12 11v10M8 5l8 4"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  flask: '<path d="M9 3h6M10 3v7L4.5 19A1.3 1.3 0 0 0 5.6 21h12.8a1.3 1.3 0 0 0 1.1-2L14 10V3M8 14h8"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2-3 4M12 17h.01"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 6.1A8 8 0 0 1 20 12M4 12a8 8 0 0 0 13.9 5.9"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  alert: '<path d="m10.3 4.7-8 14A1.5 1.5 0 0 0 3.6 21h16.8a1.5 1.5 0 0 0 1.3-2.3l-8-14a1.6 1.6 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
  credit: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 10h18M7 15h3"/>',
  truck: '<path d="M14 17H8M3 17H2V5h12v12h2M14 9h5l3 4v4h-2"/><circle cx="6" cy="17" r="2"/><circle cx="18" cy="17" r="2"/>',
  warehouse: '<path d="m3 9 9-6 9 6v12H3Z"/><path d="M7 21V11h10v10M7 15h10M7 18h10"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H4v13h4"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4M12 14v3"/>',
  pause: '<path d="M9 5v14M15 5v14"/>',
  play: '<path d="m8 4 12 8-12 8Z"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  note: '<path d="M14 3H5v18h14V8ZM14 3v5h5M8 12h8M8 16h5"/>',
  external: '<path d="M14 3h7v7M21 3l-9 9M10 3H3v18h18v-7"/>',
};
function icon(name: string, className = ''): string { return `<svg class="icon ${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] ?? icons.box}</svg>`; }
function esc(value: unknown): string { return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!); }
function money(amount: Money | null | undefined): string {
  if (!amount || !Number.isSafeInteger(amount.minor)) return '—';
  try {
    const minor = BigInt(amount.minor);
    const fraction = (minor % 100n).toString().padStart(2, '0');
    return new Intl.NumberFormat('en-GB', { style: 'currency', currency: amount.currency })
      .formatToParts(minor / 100n).map(part => part.type === 'fraction' ? fraction : part.value).join('');
  } catch { return `${amount.minor} ${amount.currency} minor units`; }
}
function human(value: string | null | undefined): string { return (value ?? 'Unknown').replaceAll('_', ' ').replaceAll('-', ' ').replace(/^./, c => c.toUpperCase()); }
function shortId(value: string): string { return value.replace(/^case-/, '').slice(0, 10); }
function time(value: string): string { const d = new Date(value); return Number.isNaN(d.getTime()) ? 'Time unavailable' : d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }); }
function fullTime(value: string): string { const d = new Date(value); return Number.isNaN(d.getTime()) ? 'Time unavailable' : d.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); }
function initials(value: string): string { return value.split(/\s+/).filter(Boolean).slice(0, 2).map(s => s[0]).join('').toUpperCase() || '?'; }
function address(a: Address | null | undefined): string { return a ? [a.name, a.line1, `${a.city} ${a.postcode}`, a.country].filter(Boolean).map(esc).join('<br>') : 'Address unavailable'; }
function attention(c: CaseSummary): boolean { return ['needs-information', 'escalated', 'failed', 'reconciling'].includes(c.status); }
const statusLabels: Record<CaseStatus, string> = { received: 'New request', investigating: 'Investigating', 'needs-information': 'Needs confirmation', 'proposal-ready': 'Plan ready', 'awaiting-approval': 'Needs approval', executing: 'In progress', reconciling: 'Needs reconciliation', resolved: 'Verified', escalated: 'Operator review', failed: 'Incomplete' };
function statusPill(status: CaseStatus, approved = false): string { return `<span class="status status-${esc(status)}"><span class="status-dot"></span>${esc(status === 'awaiting-approval' && approved ? 'Ready to execute' : statusLabels[status] ?? human(status))}</span>`; }

const state = {
  meta: null as Meta | null, cases: [] as CaseSummary[], stats: { open: 0, needs_attention: 0, awaiting_approval: 0, resolved: 0 },
  selected: null as CaseView | null, selectedId: null as string | null, filter: 'all' as Filter, query: '', tab: 'recovery' as Tab,
  loading: true, detailLoading: false, busy: false, error: '', detailError: '', role: 'operator', modal: '', loadSequence: 0,
  selectionSequence: 0,
};
const app = document.querySelector<HTMLDivElement>('#app')!;
const token = () => state.role === 'viewer' ? 'demo-viewer' : 'demo-operator';
async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method, headers: { Authorization: `Bearer ${token()}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(25000),
  });
  let data: unknown;
  try { data = await response.json(); } catch { throw new Error(`The desk could not read the server response (${response.status}).`); }
  if (!response.ok) { const detail = (data as { detail?: unknown }).detail; throw new Error(typeof detail === 'string' ? detail : `Request could not be completed (${response.status}).`); }
  return data as T;
}
function errorText(error: unknown): string { return error instanceof Error ? (error.name === 'TimeoutError' ? 'The service took too long to respond. Refresh the case before trying again.' : error.message) : 'Something went wrong. Refresh the case to see its latest state.'; }
function announce(message: string): void {
  const live = document.querySelector('#activity-announcement');
  if (live) live.textContent = message;
}
function focusCase(): void { document.querySelector<HTMLElement>('#case-heading')?.focus({ preventScroll: true }); }
function toast(message: string, bad = false): void {
  const host = document.querySelector('#notifications')!;
  host.innerHTML = `<div class="toast ${bad ? 'toast-error' : ''}" role="${bad ? 'alert' : 'status'}">${icon(bad ? 'alert' : 'check')}<span>${esc(message)}</span><button data-action="dismiss-toast" class="icon-button" aria-label="Dismiss notification">${icon('close')}</button></div>`;
  window.setTimeout(() => { if (host.textContent?.includes(message)) host.innerHTML = ''; }, bad ? 12000 : 6500);
}

function mount(): void {
  app.innerHTML = `
    <aside class="sidebar" aria-label="Main navigation">
      <a class="brand-mark" href="#" aria-label="ParcelResolve recovery desk" data-action="home">${icon('box')}</a>
      <div class="sidebar-rule"></div>
      <nav class="sidebar-nav">
        <button class="nav-button active" data-action="home" aria-label="Recovery queue" title="Recovery queue">${icon('grid')}<span>Queue</span></button>
        <button class="nav-button" data-action="audit" aria-label="Case activity" title="Case activity">${icon('activity')}<span>Activity</span></button>
        <button class="nav-button" data-action="simulation" aria-label="Simulation lab" title="Simulation lab">${icon('flask')}<span>Lab</span></button>
      </nav>
      <div class="sidebar-bottom"><button class="nav-button" data-action="guide" aria-label="Desk guide" title="Desk guide">${icon('help')}<span>Guide</span></button><span class="sidebar-version">LOCAL / 01</span></div>
    </aside>
    <div class="app-body">
      <header class="topbar"><div class="wordmark">Parcel<span>Resolve</span><span class="wordmark-divider"></span><span class="workspace-label">Recovery workspace</span></div>
        <div class="topbar-right"><span class="mode-badge"><span></span>Local simulator</span><div class="role-control"><span class="operator-avatar" aria-hidden="true">OP</span><label class="sr-only" for="role">Demo role</label><select id="role" aria-label="Demo role"><option value="operator">Operator</option><option value="viewer">Read only</option></select>${icon('down')}</div></div>
      </header>
      <main id="main" tabindex="-1">
        <section class="page-heading"><div><div class="eyebrow">OPERATIONS / EXCEPTION RECOVERY</div><h1>Keep every order accounted for.</h1><p>Resolve the exception. Verify the outcome.</p></div><button class="button primary" data-action="new-case">${icon('plus')}New request</button></section>
        <section id="metrics" class="metrics" aria-label="Case counts"></section>
        <div id="service-error"></div>
        <section class="desk" aria-label="Recovery workspace">
          <aside class="queue"><div class="queue-heading"><h2>Recovery queue <span id="queue-count" aria-live="polite" aria-atomic="true">0</span></h2><button class="icon-button" data-action="refresh" aria-label="Refresh cases" title="Refresh cases">${icon('refresh')}</button></div>
            <div class="queue-search">${icon('search')}<label class="sr-only" for="search">Search by customer, order or case</label><input id="search" type="search" placeholder="Search orders or customers…" autocomplete="off"><kbd>/</kbd></div>
            <div class="queue-filters" aria-label="Filter cases"><button data-filter="all" class="selected" aria-pressed="true">All cases</button><button data-filter="attention" aria-pressed="false">Needs attention</button><button data-filter="resolved" aria-pressed="false">Verified</button></div>
            <div id="queue-list" class="queue-list" role="region" aria-label="Cases" aria-busy="true"></div><div class="queue-footer">${icon('shield')}Evidence before action, always.</div>
          </aside>
          <article id="case-detail" class="case-detail" aria-label="Selected recovery case" aria-busy="false"></article>
        </section>
        <footer class="page-footer"><span><span class="small-dot"></span>All changes stay in this local simulator.</span><span id="interpreter-label">Connecting to the local desk…</span></footer>
      </main>
    </div>`;
  document.querySelector('#search')!.addEventListener('input', event => { state.query = (event.target as HTMLInputElement).value; renderQueue(); });
  document.querySelector('#role')!.addEventListener('change', async event => { state.role = (event.target as HTMLSelectElement).value; state.selected = null; await load(); toast(state.role === 'viewer' ? 'Read-only role active. Recovery actions are unavailable.' : 'Local operator role active.'); });
  renderAll();
}
function renderMetrics(): void {
  const stats = state.stats;
  const items = [
    { label: 'Open cases', value: stats.open, sub: 'Across the recovery desk', icon: 'box', filter: 'all', tone: '' },
    { label: 'Needs attention', value: stats.needs_attention, sub: 'Evidence or operator review', icon: 'alert', filter: 'attention', tone: 'amber' },
    { label: 'Awaiting approval', value: stats.awaiting_approval, sub: 'A plan is ready to review', icon: 'shield', filter: 'approval', tone: 'blue' },
    { label: 'Verified recoveries', value: stats.resolved, sub: 'Confirmed by read-back', icon: 'check', filter: 'resolved', tone: 'green' },
  ];
  document.querySelector('#metrics')!.innerHTML = items.map(item => `<button class="metric ${item.tone} ${state.filter === item.filter ? 'metric-selected' : ''}" data-filter="${item.filter}" aria-pressed="${state.filter === item.filter}" aria-label="${item.label}: ${item.value}. Filter cases."><span class="metric-label">${item.label}${icon(item.icon)}</span><span class="metric-value">${state.loading ? '<span class="skeleton metric-skeleton"></span>' : item.value.toString().padStart(2, '0')}</span><span class="metric-caption">${item.sub}</span></button>`).join('');
}
function renderQueue(): void {
  const matches = state.cases.filter(c => (state.filter === 'all' || (state.filter === 'attention' && attention(c)) || (state.filter === 'approval' && !c.approved && ['awaiting-approval', 'proposal-ready'].includes(c.status)) || (state.filter === 'resolved' && c.status === 'resolved')) && `${c.order_id} ${c.customer_name} ${c.id}`.toLowerCase().includes(state.query.toLowerCase()));
  document.querySelector('#queue-count')!.textContent = String(matches.length);
  document.querySelectorAll<HTMLButtonElement>('.queue-filters button').forEach(button => { const selected = button.dataset.filter === state.filter; button.classList.toggle('selected', selected); button.setAttribute('aria-pressed', String(selected)); });
  const host = document.querySelector('#queue-list')!;
  host.setAttribute('aria-busy', String(state.loading));
  const focusedCase = document.activeElement instanceof HTMLElement && host.contains(document.activeElement) ? document.activeElement.dataset.case : undefined;
  if (state.loading) { host.innerHTML = '<span class="sr-only" role="status">Loading recovery cases…</span>' + Array.from({ length: 4 }, () => '<div class="queue-skeleton"><span class="skeleton w-55"></span><span class="skeleton w-80"></span><span class="skeleton w-40"></span></div>').join(''); return; }
  if (!matches.length) { host.innerHTML = `<div class="queue-empty">${icon('search')}<strong>${state.error ? 'Cases unavailable' : state.cases.length ? 'No matching cases' : 'Your desk is clear'}</strong><p>${state.error ? 'Reconnect to the local service to load cases.' : state.cases.length ? 'Try another name, order or filter.' : 'Create a request to start a recovery.'}</p>${state.query || state.filter !== 'all' ? '<button class="text-button" data-action="clear-filter">Clear filters</button>' : ''}</div>`; return; }
  host.innerHTML = matches.map((c, index) => `<button class="case-row ${c.id === state.selectedId ? 'case-selected' : ''}" data-case="${esc(c.id)}" aria-current="${c.id === state.selectedId ? 'true' : 'false'}"><div class="case-row-top"><span class="order-number">#${esc(c.order_id)}</span><time datetime="${esc(c.updated_at)}" title="${esc(fullTime(c.updated_at))}">${esc(time(c.updated_at))}</time></div><div class="case-customer"><span class="customer-avatar avatar-${index % 4}">${esc(initials(c.customer_name))}</span><span><strong>${esc(c.customer_name)}</strong><span>${c.intent === 'address' ? 'Address correction' : c.intent === 'cancel' ? 'Cancellation request' : 'Request needs clarification'}</span></span>${icon('chevron', 'row-chevron')}</div><div class="case-row-bottom">${statusPill(c.status, c.approved ?? false)}<span class="case-amount">${esc(money(c.amount))}</span></div></button>`).join('');
  if (focusedCase) host.querySelector<HTMLButtonElement>(`[data-case="${CSS.escape(focusedCase)}"]`)?.focus({ preventScroll: true });
}
function renderAll(): void { renderMetrics(); renderQueue(); renderServiceError(); renderDetail(); }
function renderServiceError(): void { document.querySelector('#service-error')!.innerHTML = state.error ? `<div class="service-error" role="alert">${icon('alert')}<div><strong>Couldn’t connect to the local desk</strong><p>${esc(state.error)}</p></div><button class="button secondary" data-action="refresh">Try again</button></div>` : ''; }
function shippingState(o: Order): { label: string; detail: string; tone: string } {
  const active = o.labels.filter(l => l.status === 'active');
  if (active.length) return { label: active.length > 1 ? `${active.length} active labels` : 'Label printed', detail: 'A label is not dispatch evidence', tone: active.length > 1 ? 'warning' : '' };
  if (o.labels.length) return { label: 'Label voided', detail: 'No active shipping label', tone: 'good' };
  return { label: 'Not yet labelled', detail: 'No label has been created', tone: '' };
}
function warehouseState(o: Order): { label: string; detail: string; tone: string } {
  const w = o.warehouse;
  const anyDispatched = o.lines.some(line => line.dispatched_quantity > 0);
  const partial = w.state === 'partially_dispatched' || (anyDispatched && o.lines.some(line => line.dispatched_quantity < line.quantity));
  if (partial) return { label: 'Partially dispatched', detail: 'Some items have left the warehouse', tone: 'danger' };
  const dispatched = w.state === 'dispatched' || anyDispatched;
  if (dispatched) return { label: 'Physically dispatched', detail: 'Parcel movement is confirmed', tone: 'danger' };
  const holdCurrent = w.state === 'held' && !!w.ack_id && w.reliable && !!w.acknowledged_at && !!w.expires_at && new Date(w.expires_at).getTime() > Date.now() && Date.now() - new Date(w.acknowledged_at).getTime() >= 0 && Date.now() - new Date(w.acknowledged_at).getTime() <= 300000;
  if (holdCurrent) return { label: 'Hold acknowledged', detail: `Current until ${time(w.expires_at!)}`, tone: 'good' };
  if (w.state === 'held' || w.ack_id) return { label: 'Hold needs revalidation', detail: 'A current reliable hold is required', tone: 'warning' };
  if (w.state === 'not_dispatched' || w.state === 'not-dispatched') return { label: 'Not dispatched', detail: 'Warehouse state observed', tone: '' };
  return { label: 'Awaiting confirmation', detail: 'Physical dispatch is unconfirmed', tone: 'warning' };
}
function renderDetail(): void {
  const host = document.querySelector('#case-detail')!;
  host.setAttribute('aria-busy', String(state.detailLoading || state.busy));
  if (state.detailLoading || (state.loading && !state.selected)) { host.innerHTML = '<span class="sr-only" role="status">Loading case evidence…</span><div class="detail-loading" aria-hidden="true"><span class="skeleton w-40"></span><span class="skeleton heading-skeleton"></span><span class="skeleton w-80"></span><div class="loading-cards"><span class="skeleton"></span><span class="skeleton"></span><span class="skeleton"></span></div><span class="skeleton large-skeleton"></span></div>'; return; }
  if (!state.selected) { host.innerHTML = `<div class="detail-empty"><div class="empty-icon">${icon(state.detailError ? 'alert' : 'box')}</div><h2>${state.detailError ? 'This case couldn’t be loaded' : 'A clearer path to recovery.'}</h2><p>${esc(state.detailError || (state.error ? 'Start the local service, then refresh to reconnect.' : 'Select a case to bring its order, payment, shipping and warehouse evidence together.'))}</p>${state.detailError ? '<button class="button secondary" data-action="refresh">Retry</button>' : ''}</div>`; return; }
  const c = state.selected;
  const o = c.order;
  const shipping = o ? shippingState(o) : null;
  const warehouse = o ? warehouseState(o) : null;
  const refunded = o?.payment.refunds.reduce((sum, refund) => sum + refund.amount.minor, 0) ?? 0;
  const captured = o?.payment.captured;
  const financial = captured ? (refunded > 0 ? `${money({ minor: refunded, currency: captured.currency })} refunded` : `${money(captured)} captured`) : 'Not available';
  const snapshotCards = o && shipping && warehouse ? [
    { icon: 'box', eyebrow: 'COMMERCE', label: human(o.commercial_state), detail: 'WooCommerce order state', tone: o.commercial_state === 'cancelled' ? 'good' : '' },
    { icon: 'credit', eyebrow: 'PAYMENT', label: financial, detail: refunded ? 'Refund observed in payment ledger' : 'Captured payment', tone: refunded ? 'good' : '' },
    { icon: 'truck', eyebrow: 'SHIPPING LABEL', ...shipping },
    { icon: 'warehouse', eyebrow: 'PHYSICAL WAREHOUSE', ...warehouse },
  ].map(card => `<div class="snapshot-card ${card.tone}"><span class="snapshot-label">${icon(card.icon)}${card.eyebrow}</span><strong>${esc(card.label)}</strong><span class="snapshot-caption">${esc(card.detail)}</span></div>`).join('') : '<div class="snapshot-unavailable">Order evidence is unavailable. Refresh before taking action.</div>';
  host.innerHTML = `
    <header class="detail-header"><div class="detail-breadcrumb"><span>CASE ${esc(shortId(c.id).toUpperCase())}</span>${icon('chevron')}<span>ORDER #${esc(c.order_id)}</span><span class="source-chip">WooCommerce + ShipStation</span></div><div class="detail-title-row"><div><h2 id="case-heading" tabindex="-1">${c.intent === 'address' ? 'Correct the delivery address' : c.intent === 'cancel' ? 'Recover a cancellation' : 'Clarify the customer request'}</h2><p>${esc(c.customer_name)}<span class="dot-separator" aria-hidden="true">·</span>${esc(money(c.amount))}<span class="dot-separator" aria-hidden="true">·</span>${o ? `Order revision ${esc(o.version)}` : 'Snapshot unavailable'}</p></div>${statusPill(c.status, c.approved ?? false)}</div></header>
    <div class="request-strip"><span class="request-icon">${icon('mail')}</span><div><span class="section-eyebrow">CUSTOMER REQUEST</span><p>“${esc(c.request.text)}”</p></div><span class="interpretation-label" title="${esc(intakeMode(c.interpreter_mode).description)}">${icon('note')}${esc(intakeMode(c.interpreter_mode).label)}</span></div>
    <section class="snapshot-grid" aria-label="Current evidence across systems">${snapshotCards}</section>
    <div class="case-tabs" role="tablist" aria-label="Case details"><button id="tab-recovery" role="tab" data-tab="recovery" tabindex="${state.tab === 'recovery' ? '0' : '-1'}" aria-selected="${state.tab === 'recovery'}" aria-controls="case-content" class="${state.tab === 'recovery' ? 'active' : ''}">${icon('shield')}Recovery plan</button><button id="tab-evidence" role="tab" data-tab="evidence" tabindex="${state.tab === 'evidence' ? '0' : '-1'}" aria-selected="${state.tab === 'evidence'}" aria-controls="case-content" class="${state.tab === 'evidence' ? 'active' : ''}">${icon('activity')}Evidence & audit<span class="tab-count">${c.evidence.length}</span></button><button id="tab-customer" role="tab" data-tab="customer" tabindex="${state.tab === 'customer' ? '0' : '-1'}" aria-selected="${state.tab === 'customer'}" aria-controls="case-content" class="${state.tab === 'customer' ? 'active' : ''}">${icon('mail')}Customer draft</button></div>
    <div id="case-content" class="case-content" role="tabpanel" tabindex="0" aria-labelledby="tab-${state.tab}">${state.tab === 'recovery' ? recoveryContent(c) : state.tab === 'evidence' ? evidenceContent(c) : customerContent(c)}</div>
    <div class="detail-footer"><span>${icon('clock')}Observed ${o ? esc(fullTime(o.observed_at)) : '—'}</span><button class="text-button" data-action="refresh-case" ${state.busy ? 'disabled' : ''}>${icon('refresh')}Refresh evidence</button></div>`;
}
function disabled(condition: boolean): string { return condition || state.busy || !!state.error || state.role === 'viewer' ? 'disabled' : ''; }
function recoveryContent(c: CaseView): string {
  const alertTone = c.status === 'resolved' ? 'success' : ['escalated', 'failed'].includes(c.status) ? 'review' : 'attention';
  const alertIcon = c.status === 'resolved' ? 'shield' : 'alert';
  const needsClarification = c.intent === 'unknown' || (c.intent === 'address' && !c.request.target_address);
  const alertTitle = needsClarification ? 'Clarify the customer’s request' : c.status === 'resolved' ? 'Recovery verified across the connected records' : c.status === 'escalated' ? 'This recovery needs an operator review' : c.status === 'reconciling' ? 'An action outcome needs to be reconciled' : c.status === 'failed' ? 'Recovery is incomplete' : c.status === 'needs-information' ? 'More evidence is needed before recovery' : c.status === 'received' ? 'Start with the evidence' : c.status === 'executing' ? 'Recovery is in progress' : c.status === 'awaiting-approval' && c.approved ? 'The approved recovery is ready to execute' : 'A controlled recovery is ready for review';
  const primaryMessage = c.reason || (c.status === 'received' ? 'Investigate this request to check identities, quantities, payment and dispatch evidence.' : 'Review the current evidence and the proposed actions below.');
  const relevantIssues = c.disagreements.filter(issue => issue.message !== primaryMessage);
  const alert = `<div class="case-notice notice-${alertTone}" role="status">${icon(alertIcon)}<div><strong>${alertTitle}</strong><p>${esc(primaryMessage)}</p>${relevantIssues.length ? `<ul class="issue-list">${relevantIssues.map(issue => `<li>${esc(issue.message)}</li>`).join('')}</ul>` : ''}</div></div>`;
  const hold = c.permitted.hold && c.order && (c.intent === 'address' || c.order.labels.some(l => l.status === 'active') || c.order.warehouse.state === 'unknown') && warehouseState(c.order).label !== 'Hold acknowledged' ? `<div class="hold-panel"><span class="hold-icon">${icon('warehouse')}</span><div><strong>Confirm a warehouse hold</strong><p>${c.intent === 'address' ? 'A current, reliable stop acknowledgment is required before changing the delivery address and creating a label.' : 'A printed label cannot establish that a parcel is still in the warehouse. Record a current, reliable stop acknowledgment.'}</p><span class="simulation-note">This control creates a simulated warehouse acknowledgment.</span></div><button class="button secondary" data-action="hold" ${disabled(!c.permitted.hold)}>${icon('pause')}Confirm hold</button></div>` : '';
  const attempts = c.attempts.length ? `<section class="attempt-panel"><div class="section-title"><h3>Execution progress</h3><span>${c.attempts.filter(a => a.status === 'succeeded').length} of ${c.attempts.length} confirmed</span></div>${c.attempts.map(a => `<div class="attempt-row"><span class="attempt-icon ${a.status}">${icon(a.status === 'succeeded' ? 'check' : a.status === 'uncertain' ? 'search' : a.status === 'failed' ? 'alert' : 'clock')}</span><div><strong>${esc(human(a.kind))}</strong>${a.error ? `<p>${esc(a.error)}</p>` : a.provider_id ? `<p>Provider reference ${esc(a.provider_id)}</p>` : '<p>Intent recorded before the action</p>'}</div><span class="attempt-state ${a.status}">${a.status === 'uncertain' ? 'Outcome unconfirmed' : a.status === 'succeeded' ? 'Confirmed' : esc(human(a.status))}</span></div>`).join('')}</section>` : '';
  let plan = '';
  if (c.plan) {
    const p = c.plan;
    const approved = c.approved === true;
    const refund = p.actions.find(a => a.kind === 'refund')?.amount;
    plan = `<section class="plan-panel"><div class="section-title"><div><span class="section-eyebrow">PROPOSED RECOVERY</span><h3>${c.intent === 'address' ? 'Correct the address, then replace the label' : 'Bring this order to a consistent state'}</h3></div><span class="plan-count">${p.actions.length} ${p.actions.length === 1 ? 'action' : 'actions'}</span></div><ol class="action-list">${p.actions.map((a, i) => {
      const attempt = [...c.attempts].reverse().find(at => at.action_id === a.id);
      return `<li class="action-item"><span class="action-number ${attempt?.status === 'succeeded' ? 'action-done' : ''}">${attempt?.status === 'succeeded' ? icon('check') : String(i + 1).padStart(2, '0')}</span><div class="action-description"><strong>${esc(a.title || human(a.kind))}</strong><span>${esc(actionDescription(a))}</span>${a.address ? `<div class="action-address">${address(a.address)}</div>` : ''}</div>${a.amount ? `<strong class="action-money">${esc(money(a.amount))}</strong>` : `<span class="action-kind">${a.kind === 'void_label' ? 'LABEL' : a.kind === 'create_label' ? 'LABEL' : a.kind === 'update_address' ? 'ADDRESS' : 'ORDER'}</span>`}</li>`;
    }).join('')}</ol><div class="plan-binding">${icon('lock')}<span>Approval is bound to these actions${refund ? ` and ${esc(money(refund))}` : ''} · Order revision ${esc(p.resource_version)}<span class="plan-hash" title="${esc(p.hash)}"> · Plan ${esc(p.hash.slice(0, 8))}</span></span></div>${approved ? `<div class="approved-note">${icon('check')}This exact plan has an operator approval.</div>` : ''}</section>`;
  } else if (c.status !== 'resolved' && !['escalated', 'failed'].includes(c.status)) {
    plan = `<div class="no-plan"><span class="no-plan-icon">${icon('shield')}</span><div><h3>${c.status === 'received' ? 'An evidence-led plan starts here' : 'The recovery plan is waiting on evidence'}</h3><p>${c.status === 'received' ? 'Inspect the joined records to determine the supported recovery and its exact amount.' : 'Once the missing evidence is established, investigate again to build a plan.'}</p></div></div>`;
  }
  const permitted = c.permitted;
  const anyActions = permitted.investigate || permitted.approve || permitted.execute || permitted.retry;
  const actions = anyActions ? `<div class="recovery-actions"><span class="action-helper">${state.role === 'viewer' ? `${icon('eye')}Read-only role · Actions require an operator` : state.busy ? `${icon('clock')}Checking and recording the latest state…` : permitted.approve ? `${icon('shield')}Review the full plan before approval` : permitted.execute ? `${icon('shield')}State is revalidated before every action` : permitted.retry ? `${icon('search')}Reconcile provider evidence before resuming` : `${icon('eye')}Investigation reads the current records`}</span><div class="action-buttons">${permitted.investigate ? `<button class="button ${permitted.approve || permitted.execute || permitted.retry ? 'secondary' : 'primary'}" data-action="investigate" ${disabled(false)}>${icon('search')}${c.plan ? 'Re-investigate' : 'Investigate request'}</button>` : ''}${permitted.retry ? `<button class="button primary" data-action="retry" ${disabled(false)}>${icon('refresh')}Reconcile & resume</button>` : ''}${permitted.approve ? `<button class="button primary" data-action="approve" ${disabled(!c.plan)}>${icon('shield')}Approve${c.plan?.actions.some(a => a.kind === 'refund') ? ` ${esc(money(c.plan.actions.find(a => a.kind === 'refund')?.amount))} recovery` : ' recovery plan'}</button>` : ''}${permitted.execute ? `<button class="button primary" data-action="execute" ${disabled(false)}>${icon('play')}Execute approved plan</button>` : ''}</div></div>` : (c.status === 'resolved' ? `<div class="resolved-footnote">${icon('check')}Final state verified. The customer explanation is available in <button class="text-button" data-tab="customer">Customer draft</button>.</div>` : `<div class="review-footnote">${icon('eye')}Keep this case under operator review. No unsupported recovery is authorized.</div>`);
  const recent = [...c.evidence].slice(-3).reverse();
  const recentEvidence = recent.length ? `<section class="recent-evidence"><div class="section-title"><h3>Latest evidence</h3><button class="text-button" data-tab="evidence">View full audit ${icon('arrow')}</button></div>${recent.map(e => `<div class="recent-event"><span class="event-dot"></span><span>${esc(e.message)}</span><time datetime="${esc(e.created_at)}">${esc(time(e.created_at))}</time></div>`).join('')}</section>` : '';
  const clarify = needsClarification ? `<div class="clarify-panel"><p>${c.intent === 'unknown' ? 'Confirm the intended request before a recovery plan can be prepared.' : 'Record the complete corrected delivery address before continuing.'}</p><button class="button secondary" data-action="clarify" ${disabled(false)}>${icon('note')}Clarify request</button></div>` : '';
  const viewer = state.role === 'viewer' ? `<div class="viewer-notice">${icon('eye')}Read-only role · Switch to Operator to record recovery actions.</div>` : '';
  return `${viewer}${alert}${clarify}${hold}${warehouseAttempts(c)}${attempts}${plan}${actions}${recentEvidence}`;
}
function warehouseAttempts(c: CaseView): string {
  const attempts = c.warehouse_attempts ?? [];
  if (!attempts.length) return '';
  return `<section class="warehouse-progress attempt-panel" aria-label="Warehouse acknowledgment history"><div class="section-title"><h3>Warehouse acknowledgment</h3><span>Simulated provider</span></div>${attempts.map(a => `<div class="attempt-row"><span class="attempt-icon ${esc(a.status)}">${icon(a.status === 'succeeded' && a.verified_at ? 'check' : a.status === 'failed' ? 'alert' : 'clock')}</span><div><strong>${a.status === 'succeeded' && a.verified_at ? 'Acknowledgment verified by read-back' : a.status === 'uncertain' ? 'Hold outcome is unconfirmed' : a.status === 'failed' ? 'Hold was not established' : 'Warehouse hold intent recorded'}</strong><p>${esc(a.error || (a.verified_at ? `Verified ${fullTime(a.verified_at)}${a.provider_id ? ` · Reference ${a.provider_id}` : ''}` : 'Provider evidence must be reconciled before recovery can continue.'))}</p></div><span class="attempt-state ${esc(a.status)}">${a.status === 'succeeded' && a.verified_at ? 'Verified' : a.status === 'succeeded' ? 'Receipt recorded' : esc(human(a.status))}</span></div>`).join('')}<p class="warehouse-history-note">Historical acknowledgments do not extend a hold. The physical warehouse card shows whether the current stop is still valid.</p></section>`;
}
function actionDescription(a: Action): string {
  switch (a.kind) {
    case 'cancel_order': return 'Update the commerce order and verify its final status.';
    case 'refund': return 'Refund the backend-calculated unrefunded captured amount.';
    case 'void_label': return `Void ${a.label_id ? `label ${a.label_id}` : 'the active shipping label'} and verify the carrier response.`;
    case 'update_address': return 'Apply the reviewed delivery address to the order.';
    case 'create_label': return 'Create one replacement label for the corrected address.';
    default: return human(a.kind);
  }
}
function evidenceContent(c: CaseView): string {
  const o = c.order;
  const events = [...c.evidence].reverse();
  return `<div class="evidence-intro"><div><span class="section-eyebrow">JOINED RECORD</span><h3>The evidence behind every decision.</h3><p>Order, shipping, warehouse and recovery events in one audit trail.</p></div><span class="record-count">${events.length} records</span></div>${o ? `<div class="identity-strip"><span>Commerce order<strong>${esc(o.woo_id)}</strong></span><span>Shipping order<strong>${esc(o.shipstation_order_id)}</strong></span><span>Warehouse hold<strong>${esc(o.warehouse.ack_id || 'Not acknowledged')}</strong></span></div><details class="line-details"><summary>Items & shipment assignments<span>${o.lines.length} ${o.lines.length === 1 ? 'item' : 'items'}${icon('down')}</span></summary><div class="table-scroll"><table><thead><tr><th scope="col">Item</th><th scope="col">Ordered</th><th scope="col">Dispatched</th><th scope="col">Refunded</th></tr></thead><tbody>${o.lines.map(l => `<tr><td><strong>${esc(l.title)}</strong><small>${esc(l.sku)}</small></td><td>${l.quantity}</td><td>${l.dispatched_quantity}</td><td>${l.refunded_quantity}</td></tr>`).join('')}</tbody></table></div><div class="shipping-records">${o.labels.length ? o.labels.map(l => `<span>${icon('truck')}Label ${esc(l.id)} · ${esc(human(l.status))}<small>Tracking: ${esc(l.tracking || 'None')}</small></span>`).join('') : '<span>No shipping labels have been created.</span>'}${o.shipments.map(s => `<span>${icon('box')}Shipment ${esc(s.id)} · ${esc(human(s.status))}<small>Item assignments: ${esc(Object.entries(s.line_quantities).map(([key, qty]) => `${key} × ${qty}`).join(', '))}</small></span>`).join('')}</div></details>` : ''}
    <ol class="timeline">${events.length ? events.map((e, i) => `<li><div class="timeline-marker ${i === 0 ? 'latest' : ''}">${icon(e.source.toLowerCase().includes('warehouse') ? 'warehouse' : e.source.toLowerCase().includes('payment') ? 'credit' : e.kind.includes('approv') ? 'shield' : e.kind.includes('verif') ? 'check' : 'activity')}</div><div class="timeline-event"><div class="timeline-meta"><span>${esc(human(e.source))}</span><time datetime="${esc(e.created_at)}">${esc(fullTime(e.created_at))}</time></div><strong>${esc(human(e.kind))}</strong><p>${esc(e.message)}</p>${e.data && Object.keys(e.data).length ? `<details class="event-data"><summary>Evidence details</summary><pre>${esc(JSON.stringify(e.data, null, 2))}</pre></details>` : ''}</div></li>`).join('') : '<li class="timeline-empty">Evidence will appear when the request is investigated.</li>'}</ol>${c.approvals.length ? `<section class="approval-history"><h3>Approval history</h3>${c.approvals.map(a => `<div>${icon('shield')}<span><strong>${esc(a.operator_id)}</strong> approved plan ${esc(a.plan_hash.slice(0, 8))} at order revision ${esc(a.resource_version)}<small>${esc(fullTime(a.created_at))}</small></span></div>`).join('')}</section>` : ''}`;
}
function customerContent(c: CaseView): string {
  return `<div class="customer-draft-heading"><span class="draft-illustration">${icon('mail')}</span><span class="section-eyebrow">LOCAL CUSTOMER DRAFT</span><h3>A clear update, grounded in the evidence.</h3><p>Review this explanation before copying it to your support workflow.</p></div><div class="draft-card"><div class="draft-card-top"><span>To <strong>${esc(c.customer_name)}</strong></span><span class="draft-only">Draft only</span></div><div class="draft-body">${c.draft ? esc(c.draft).replaceAll('\n', '<br>') : 'Investigate this request to prepare an explanation based on the observed evidence.'}</div><div class="draft-card-footer"><span>${icon('lock')}No message has been sent.</span><button class="button secondary" data-action="copy-draft" ${!c.draft ? 'disabled' : ''}>${icon('copy')}Copy draft</button></div></div><div class="draft-note">${icon('eye')}The draft reflects the latest recorded case state. Revisit it if the order or warehouse evidence changes.</div>`;
}

async function load(): Promise<void> {
  const sequence = ++state.loadSequence;
  state.selectionSequence++;
  state.loading = true; state.error = ''; renderAll();
  try {
    const [meta, result] = await Promise.all([api<Meta>('/meta'), api<ListResult>('/cases')]);
    if (sequence !== state.loadSequence) return;
    state.meta = meta; state.cases = result.cases; state.stats = result.stats;
    document.querySelector('#interpreter-label')!.textContent = `Intake: ${intakeMode(meta.interpreter_mode).label}`;
    document.querySelector('#interpreter-label')!.setAttribute('title', intakeMode(meta.interpreter_mode).description);
    state.loading = false; renderMetrics(); renderQueue(); renderServiceError();
    const target = state.selectedId && result.cases.some(c => c.id === state.selectedId) ? state.selectedId : (result.cases.find(c => c.status === 'needs-information') ?? result.cases.find(c => c.status !== 'resolved') ?? result.cases[0])?.id;
    if (target) await selectCase(target); else { state.selected = null; renderDetail(); }
  } catch (error) { if (sequence !== state.loadSequence) return; state.error = errorText(error); state.loading = false; renderAll(); if (!state.meta) document.querySelector('#interpreter-label')!.textContent = 'Intake mode unavailable'; }
}
async function selectCase(id: string): Promise<void> {
  const sequence = ++state.selectionSequence;
  state.selectedId = id; state.detailLoading = true; state.detailError = ''; renderQueue(); renderDetail();
  try { const c = await api<CaseView>(`/cases/${encodeURIComponent(id)}`); if (sequence !== state.selectionSequence) return; state.selected = c; }
  catch (error) { if (sequence !== state.selectionSequence) return; state.selected = null; state.detailError = errorText(error); }
  finally { if (sequence === state.selectionSequence) { state.detailLoading = false; renderDetail(); if (state.selected) announce(`Order ${state.selected.order_id}, ${state.selected.customer_name}. ${statusLabels[state.selected.status]}.`); } }
}
async function refreshList(): Promise<void> { const result = await api<ListResult>('/cases'); state.cases = result.cases; state.stats = result.stats; renderMetrics(); renderQueue(); }
async function mutate(action: string, body: unknown = {}): Promise<void> {
  const c = state.selected; if (!c || state.busy || state.role === 'viewer') return;
  const selection = state.selectionSequence;
  const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement.dataset.action : undefined;
  state.busy = true; renderDetail(); announce(`${human(action)} in progress. Checking and recording evidence.`);
  try {
    const result = await api<CaseView>(`/cases/${encodeURIComponent(c.id)}/${action}`, 'POST', body);
    if (state.selectedId === c.id && selection === state.selectionSequence) state.selected = result;
    await refreshList();
    const messages: Record<string, string> = { investigate: 'The latest records have been investigated.', hold: result.order && warehouseState(result.order).label === 'Hold acknowledged' ? 'A simulated warehouse hold was verified.' : 'Warehouse hold outcome recorded. Review the evidence before continuing.', approve: 'Approval recorded for this exact plan.', execute: result.status === 'resolved' ? 'Recovery completed and verified.' : 'Execution finished. Review the latest case state.', retry: result.status === 'resolved' ? 'Recovery reconciled and verified.' : 'Provider evidence reconciled. Review the latest state.', fault: 'Simulation fault queued for the next matching action.' };
    toast(messages[action] ?? 'Case updated.');
  } catch (error) {
    toast(errorText(error), true);
    // A failed browser response is not proof that a mutation failed. Read back the case.
    try {
      if (state.selectedId === c.id) {
        const result = await api<CaseView>(`/cases/${encodeURIComponent(c.id)}`);
        if (state.selectedId === c.id && selection === state.selectionSequence) state.selected = result;
      }
      await refreshList();
    } catch { /* Keep the last evidence and explicit error. */ }
  } finally {
    state.busy = false; renderDetail();
    if (state.selectedId === c.id && previousFocus) {
      const next = previousFocus === 'approve' && state.selected?.permitted.execute ? 'execute' : previousFocus;
      const button = document.querySelector<HTMLButtonElement>(`#case-detail [data-action="${next}"]:not(:disabled)`);
      if (button) button.focus({ preventScroll: true }); else focusCase();
    }
  }
}
function setFilter(filter: Filter): void { const metricFocused = document.activeElement?.closest('#metrics'); state.filter = filter; renderMetrics(); renderQueue(); if (metricFocused) document.querySelector<HTMLButtonElement>(`#metrics [data-filter="${filter}"]`)?.focus({ preventScroll: true }); announce(`${document.querySelector('#queue-count')?.textContent ?? '0'} matching cases.`); }
function setTab(tab: Tab): void { state.tab = tab; renderDetail(); document.querySelector<HTMLButtonElement>(`#tab-${tab}`)?.focus({ preventScroll: true }); document.querySelectorAll('.sidebar-nav .nav-button').forEach(b => b.classList.toggle('active', b.getAttribute('data-action') === (tab === 'evidence' ? 'audit' : 'home'))); }

let modalReturnFocus: HTMLElement | null = null;
function modalShell(title: string, subtitle: string, content: string, wide = false): HTMLDialogElement {
  modalReturnFocus = document.activeElement as HTMLElement | null;
  document.querySelector('#modal-root')!.innerHTML = `<dialog class="modal ${wide ? 'modal-wide' : ''}" aria-labelledby="modal-title"><div class="modal-heading"><div><span class="section-eyebrow">PARCELRESOLVE / LOCAL DESK</span><h2 id="modal-title">${title}</h2><p>${subtitle}</p></div><button class="icon-button" data-action="close-modal" aria-label="Close dialog">${icon('close')}</button></div>${content}</dialog>`;
  const dialog = document.querySelector<HTMLDialogElement>('dialog')!;
  dialog.addEventListener('click', event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) closeModal(); } });
  dialog.addEventListener('cancel', event => { event.preventDefault(); closeModal(); });
  dialog.showModal();
  return dialog;
}
function closeModal(): void { document.querySelector<HTMLDialogElement>('dialog')?.close(); document.querySelector('#modal-root')!.innerHTML = ''; state.modal = ''; if (modalReturnFocus?.isConnected) modalReturnFocus.focus({ preventScroll: true }); else focusCase(); }
function formError(message: string): void {
  const el = document.querySelector<HTMLElement>('#form-error');
  if (el) { el.textContent = message; el.classList.remove('hidden'); el.tabIndex = -1; el.focus({ preventScroll: true }); el.scrollIntoView({ block: 'nearest' }); }
}
function validateForm(form: HTMLFormElement): boolean {
  for (const field of form.querySelectorAll<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>('input,textarea,select')) {
    field.removeAttribute('aria-invalid'); field.removeAttribute('aria-describedby');
    if (field.disabled || field.closest('fieldset:disabled')) continue;
    if ((field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) && field.required) field.value = field.value.trim();
    if (!field.checkValidity()) {
      const label = field.labels?.[0]?.textContent?.trim() || 'This field';
      formError(`${label}: ${field.validationMessage}`); field.setAttribute('aria-invalid', 'true'); field.setAttribute('aria-describedby', 'form-error'); field.focus(); return false;
    }
  }
  const error = form.querySelector('#form-error'); if (error) error.classList.add('hidden');
  return true;
}
async function newCaseModal(): Promise<void> {
  if (state.role === 'viewer') { toast('Read-only access cannot create a request. Switch to the local operator role.', true); return; }
  state.modal = 'new-case';
  const dialog = modalShell('Start a recovery request', 'Choose a demo order and record what the customer needs.', `<div class="modal-body"><div class="modal-loading"><span class="spinner"></span>Loading demo orders…</div></div>`);
  try {
    const result = await api<{ orders: { id: string; customer_name: string; commercial_state: string }[] }>('/orders');
    if (!dialog.isConnected) return;
    if (!result.orders.length) {
      document.querySelector('.modal-body')!.innerHTML = '<div class="queue-empty"><strong>No demo orders available</strong><p>Seed the local demo or reconnect to the order service before creating a recovery request.</p></div><button class="button secondary" data-action="close-modal">Back to the desk</button>';
      return;
    }
    const content = `<form id="new-case-form" novalidate><div class="modal-body"><div id="form-error" class="form-error hidden" role="alert"></div><label class="field-label" for="order-select">Demo order</label><select class="field" id="order-select" name="order_id" required><option value="">Select an order…</option>${result.orders.map(o => `<option value="${esc(o.id)}">#${esc(o.id)} · ${esc(o.customer_name)} · ${esc(human(o.commercial_state))}</option>`).join('')}</select><label class="field-label" for="request-text">Customer request</label><textarea class="field" id="request-text" name="text" rows="4" minlength="3" maxlength="4000" required placeholder="Please cancel my order before it is dispatched."></textarea><label class="field-label" for="intent-select">Request type</label><select class="field" id="intent-select" name="intent"><option value="unknown">Interpret the request text</option><option value="cancel">Cancellation</option><option value="address">Address correction</option></select><p class="field-hint">${icon('note')}${esc(intakeMode(state.meta?.interpreter_mode).description)} Amounts, permissions and recovery actions remain controlled by backend rules.</p><fieldset id="address-fields" class="address-fields hidden" disabled><legend>Corrected delivery address</legend><div class="field-grid"><label>Recipient name<input class="field" name="name" required maxlength="100" autocomplete="shipping name"></label><label>Country code<input class="field" name="country" value="GB" required minlength="2" maxlength="2" pattern="[A-Za-z]{2}" autocomplete="shipping country"></label></div><label>Address line<input class="field" name="line1" required maxlength="200" autocomplete="shipping address-line1"></label><div class="field-grid"><label>City<input class="field" name="city" required maxlength="100" autocomplete="shipping address-level2"></label><label>Postcode<input class="field" name="postcode" required maxlength="20" autocomplete="shipping postal-code"></label></div></fieldset></div><div class="modal-footer"><span>${icon('flask')}Simulator records only</span><div><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Create request${icon('arrow')}</button></div></div></form>`;
    document.querySelector('.modal-loading')!.parentElement!.outerHTML = content;
    document.querySelector('#intent-select')!.addEventListener('change', event => { const active = (event.target as HTMLSelectElement).value === 'address'; const fields = document.querySelector<HTMLFieldSetElement>('#address-fields')!; fields.classList.toggle('hidden', !active); fields.disabled = !active; });
    document.querySelector<HTMLSelectElement>('#order-select')!.focus();
    document.querySelector('#new-case-form')!.addEventListener('submit', async event => {
      event.preventDefault(); const form = event.target as HTMLFormElement; if (form.dataset.submitting === 'true' || !validateForm(form)) return;
      const data = new FormData(form); const intent = String(data.get('intent')); const button = form.querySelector<HTMLButtonElement>('[type="submit"]')!;
      const body: { order_id: string; text: string; intent?: string; target_address?: Address } = { order_id: String(data.get('order_id')), text: String(data.get('text')).trim() };
      if (intent !== 'unknown') body.intent = intent;
      if (intent === 'address') body.target_address = { name: String(data.get('name')).trim(), line1: String(data.get('line1')).trim(), city: String(data.get('city')).trim(), postcode: String(data.get('postcode')).trim(), country: String(data.get('country')).toUpperCase() };
      form.dataset.submitting = 'true'; form.setAttribute('aria-busy', 'true'); button.disabled = true; button.textContent = intent === 'unknown' ? 'Interpreting & creating…' : 'Creating…';
      try { const c = await api<CaseView>('/cases', 'POST', body); if (!dialog.isConnected) { await refreshList(); return; } closeModal(); state.selectedId = c.id; state.selected = c; state.tab = 'recovery'; state.filter = 'all'; state.query = ''; (document.querySelector('#search') as HTMLInputElement).value = ''; await refreshList(); renderDetail(); focusCase(); toast('Customer request added to the recovery queue.'); }
      catch (error) { if (!dialog.isConnected) return; form.dataset.submitting = 'false'; form.setAttribute('aria-busy', 'false'); formError(errorText(error)); button.disabled = false; button.innerHTML = `Create request${icon('arrow')}`; }
    });
  } catch (error) { const body = dialog.querySelector('.modal-body'); if (dialog.isConnected && body) body.innerHTML = `<div class="form-error" role="alert">${esc(errorText(error))}</div><button class="button secondary" data-action="close-modal">Close</button>`; }
}
const faultOptions = [
  ['lost_response', 'Write succeeds, response is lost', 'The provider applies the action, but the desk must reconcile the missing response.'],
  ['before_write', 'Failure before the write', 'The provider rejects the attempt before applying any effect.'],
  ['unavailable', 'Service unavailable', 'The action cannot reach an available provider.'],
  ['rate_limit', 'Rate limited', 'The provider asks the desk to wait before trying again.'],
  ['void_rejected', 'Carrier rejects a label void', 'The carrier refuses the void, leaving an active label to review.'],
  ['stale_read', 'Stale provider read', 'The read-back can return an older snapshot.'],
  ['dispatch_race', 'Dispatch at the action boundary', 'A warehouse dispatch races with the approved recovery.'],
  ['unknown_outcome', 'Outcome cannot be established', 'The action result remains uncertain and requires operator review.'],
] as const;
function clarificationModal(): void {
  const c = state.selected; if (!c || state.role === 'viewer') return;
  state.modal = 'clarify';
  const dialog = modalShell('Clarify the request', `Record the supported customer intent for order #${esc(c.order_id)}.`, `<form id="clarify-form" novalidate><div class="modal-body"><div id="form-error" class="form-error hidden" role="alert"></div><label class="field-label" for="clarify-intent">Confirmed request</label><select class="field" id="clarify-intent" name="intent"><option value="cancel" ${c.intent !== 'address' ? 'selected' : ''}>Cancellation</option><option value="address" ${c.intent === 'address' ? 'selected' : ''}>Address correction</option></select><fieldset id="clarify-address" class="address-fields ${c.intent === 'address' ? '' : 'hidden'}" ${c.intent === 'address' ? '' : 'disabled'}><legend>Corrected delivery address</legend><label>Recipient name<input class="field" name="name" required maxlength="100" value="${esc(c.request.target_address?.name ?? c.customer_name)}"></label><label>Address line<input class="field" name="line1" required maxlength="200" value="${esc(c.request.target_address?.line1 ?? '')}"></label><div class="field-grid"><label>City<input class="field" name="city" required maxlength="100" value="${esc(c.request.target_address?.city ?? '')}"></label><label>Postcode<input class="field" name="postcode" required maxlength="20" value="${esc(c.request.target_address?.postcode ?? '')}"></label></div><label>Country code<input class="field" name="country" required minlength="2" maxlength="2" pattern="[A-Za-z]{2}" value="${esc(c.request.target_address?.country ?? 'GB')}"></label></fieldset><p class="field-hint">The desk will investigate the updated request and derive a plan from current evidence.</p></div><div class="modal-footer"><span>${icon('note')}Operator clarification</span><div><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Save clarification${icon('check')}</button></div></div></form>`);
  document.querySelector('#clarify-intent')!.addEventListener('change', event => { const active = (event.target as HTMLSelectElement).value === 'address'; const fields = document.querySelector<HTMLFieldSetElement>('#clarify-address')!; fields.classList.toggle('hidden', !active); fields.disabled = !active; });
  document.querySelector('#clarify-form')!.addEventListener('submit', async event => {
    event.preventDefault(); const form = event.target as HTMLFormElement; if (form.dataset.submitting === 'true' || !validateForm(form)) return; const data = new FormData(form); const button = form.querySelector<HTMLButtonElement>('[type="submit"]')!;
    const intent = String(data.get('intent')); const body: { intent: string; target_address?: Address } = { intent };
    if (intent === 'address') body.target_address = { name: String(data.get('name')).trim(), line1: String(data.get('line1')).trim(), city: String(data.get('city')).trim(), postcode: String(data.get('postcode')).trim(), country: String(data.get('country')).toUpperCase() };
    form.dataset.submitting = 'true'; form.setAttribute('aria-busy', 'true'); button.disabled = true;
    try { const result = await api<CaseView>(`/cases/${encodeURIComponent(c.id)}/clarify`, 'POST', body); if (!dialog.isConnected) { await refreshList(); return; } if (state.selectedId === c.id) state.selected = result; closeModal(); await refreshList(); renderDetail(); focusCase(); toast('Clarification saved and current evidence investigated.'); }
    catch (error) { if (!dialog.isConnected) return; form.dataset.submitting = 'false'; form.setAttribute('aria-busy', 'false'); formError(errorText(error)); button.disabled = false; }
  });
}
function simulationModal(): void {
  if (!state.selected) { toast('Select a case to test a recovery path.', true); return; }
  state.modal = 'simulation';
  const c = state.selected;
  const options = [['warehouse_hold', 'Confirm warehouse hold'], ['refund', 'Refund payment'], ['cancel_order', 'Cancel commerce order'], ['void_label', 'Void shipping label'], ['update_address', 'Update delivery address'], ['create_label', 'Create replacement label']];
  const dialog = modalShell('Test the recovery path', `Queue a fault for order #${esc(c.order_id)} in the local simulator.`, `<form id="fault-form" novalidate><div class="modal-body"><div class="simulation-banner">${icon('flask')}<span><strong>Local simulation only</strong>No merchant, carrier or warehouse is contacted.</span></div><div id="form-error" class="form-error hidden" role="alert"></div><label class="field-label" for="fault-action">Action to interrupt</label><select class="field" id="fault-action" name="action_kind">${options.map(([value, label]) => `<option value="${value}" ${value === 'refund' ? 'selected' : ''}>${label}</option>`).join('')}</select><label class="field-label" for="fault-type">Failure scenario</label><select class="field" id="fault-type" name="fault">${faultOptions.filter(([key]) => key !== 'void_rejected').map(([value, label]) => `<option value="${value}" ${value === 'lost_response' ? 'selected' : ''}>${label}</option>`).join('')}</select><p class="fault-description" id="fault-description">${faultOptions[0][2]}</p><p class="field-hint">The fault is queued for the next matching operation on this order. Review and approve the recovery plan as usual, then execute to observe the result.</p></div><div class="modal-footer"><span>${icon('shield')}Normal approval rules apply</span><div><button class="button secondary" type="button" data-action="close-modal">Cancel</button><button class="button primary" type="submit" ${state.role === 'viewer' ? 'disabled' : ''}>Queue simulation${icon('arrow')}</button></div></div></form>`);
  document.querySelector('#fault-action')!.addEventListener('change', event => {
    const action = (event.target as HTMLSelectElement).value;
    const select = document.querySelector<HTMLSelectElement>('#fault-type')!;
    select.innerHTML = faultOptions.filter(([key]) => key !== 'void_rejected' || action === 'void_label').map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
    document.querySelector('#fault-description')!.textContent = faultOptions[0][2];
  });
  document.querySelector('#fault-type')!.addEventListener('change', event => { document.querySelector('#fault-description')!.textContent = faultOptions.find(([key]) => key === (event.target as HTMLSelectElement).value)?.[2] ?? ''; });
  document.querySelector('#fault-form')!.addEventListener('submit', async event => {
    event.preventDefault(); const form = event.target as HTMLFormElement; if (form.dataset.submitting === 'true' || !validateForm(form)) return; const data = new FormData(form); const button = form.querySelector<HTMLButtonElement>('[type="submit"]')!; form.dataset.submitting = 'true'; form.setAttribute('aria-busy', 'true'); button.disabled = true;
    try { const result = await api<CaseView>(`/cases/${encodeURIComponent(c.id)}/fault`, 'POST', { action_kind: data.get('action_kind'), fault: data.get('fault') }); if (!dialog.isConnected) { await refreshList(); return; } if (state.selectedId === c.id) state.selected = result; closeModal(); await refreshList(); renderDetail(); focusCase(); toast('Fault queued. Run the matching approved action to see the recovery behavior.'); }
    catch (error) { if (!dialog.isConnected) return; form.dataset.submitting = 'false'; form.setAttribute('aria-busy', 'false'); formError(errorText(error)); button.disabled = state.role === 'viewer'; }
  });
}
function guideModal(): void {
  state.modal = 'guide';
  modalShell('A calm path through the exception.', 'Use the evidence to decide. Use verification to close.', `<div class="modal-body guide-content"><ol><li><span>01</span><div><h3>Investigate the request</h3><p>Bring order, payment, label and warehouse records together. A printed label is not proof of physical dispatch.</p></div></li><li><span>02</span><div><h3>Establish a safe recovery</h3><p>Post-label recovery needs a current, reliable warehouse hold. Partial dispatch and uncertain outcomes stay under operator review.</p></div></li><li><span>03</span><div><h3>Approve the exact plan</h3><p>Review every action and amount. Your approval applies to this plan and this order revision. Changed evidence invalidates it.</p></div></li><li><span>04</span><div><h3>Execute, reconcile, verify</h3><p>The desk records each intent before acting and reads back the final state. Uncertain actions are reconciled before resuming.</p></div></li></ol><div class="simulation-banner">${icon('flask')}<span><strong>This workspace is a local simulator.</strong>Customer explanations are drafts. No messages or live shipping/payment changes are sent. Intake is deterministic unless an explicitly configured model mode is shown.</span></div></div><div class="modal-footer"><span>One store · One warehouse · Evidence first</span><button class="button primary" data-action="close-modal">Back to the desk${icon('arrow')}</button></div>`, true);
}

document.addEventListener('click', async event => {
  const target = (event.target as HTMLElement).closest<HTMLElement>('[data-action], [data-case], [data-filter], [data-tab]'); if (!target || target.hasAttribute('disabled')) return;
  if (target instanceof HTMLAnchorElement) event.preventDefault();
  if (target.dataset.case) { state.tab = 'recovery'; await selectCase(target.dataset.case); return; }
  if (target.dataset.filter) { setFilter(target.dataset.filter as Filter); return; }
  if (target.dataset.tab) { setTab(target.dataset.tab as Tab); return; }
  switch (target.dataset.action) {
    case 'home': setTab('recovery'); setFilter('all'); break;
    case 'audit': setTab('evidence'); break;
    case 'refresh': if (!state.busy) await load(); break;
    case 'refresh-case': if (state.selectedId && !state.busy) { await selectCase(state.selectedId); await refreshList().catch(error => toast(errorText(error), true)); } break;
    case 'clear-filter': state.query = ''; (document.querySelector('#search') as HTMLInputElement).value = ''; setFilter('all'); break;
    case 'new-case': await newCaseModal(); break;
    case 'simulation': simulationModal(); break;
    case 'clarify': clarificationModal(); break;
    case 'guide': guideModal(); break;
    case 'close-modal': closeModal(); break;
    case 'dismiss-toast': document.querySelector('#notifications')!.innerHTML = ''; break;
    case 'investigate': case 'hold': case 'execute': case 'retry': await mutate(target.dataset.action); break;
    case 'approve': if (state.selected?.plan) await mutate('approve', { plan_hash: state.selected.plan.hash, resource_version: state.selected.plan.resource_version }); break;
    case 'copy-draft': if (state.selected?.draft) { try { await navigator.clipboard.writeText(state.selected.draft); toast('Customer draft copied. No message was sent.'); } catch { toast('Clipboard is unavailable. Select the draft text and copy it manually.', true); } } break;
  }
});
document.addEventListener('keydown', event => {
  if (event.key === '/' && !(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) && !state.modal) { event.preventDefault(); document.querySelector<HTMLInputElement>('#search')?.focus(); }
  const tabButton = (event.target as HTMLElement).closest<HTMLElement>('[role="tab"]');
  if (tabButton && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
    event.preventDefault(); const tabs: Tab[] = ['recovery', 'evidence', 'customer']; const current = tabs.indexOf(state.tab); const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (current + (event.key === 'ArrowRight' ? 1 : 2)) % 3; setTab(tabs[next]!); document.querySelector<HTMLButtonElement>(`#tab-${state.tab}`)?.focus();
  }
});
// Expiring warehouse acknowledgments must not remain visually current. This is a
// display-only refresh; every consequential check is still performed server-side.
window.setInterval(() => {
  if (!state.selected?.order || state.busy || state.detailLoading || state.modal) return;
  const expires = state.selected.order.warehouse.expires_at;
  if (expires && new Date(expires).getTime() <= Date.now() && document.querySelector('.snapshot-grid')?.textContent?.includes('Hold acknowledged')) renderDetail();
}, 10000);
mount();
void load();
