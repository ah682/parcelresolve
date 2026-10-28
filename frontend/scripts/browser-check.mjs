import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright-core';
import { checkPresentationStates, inspectTextContrast } from './presentation-checks.mjs';

const baseURL = process.env.PARCELRESOLVE_BROWSER_URL ?? 'http://127.0.0.1:8873';
const output = process.env.PARCELRESOLVE_BROWSER_OUTPUT ?? 'frontend/qa';
const candidates = [process.env.CHROME_BIN, '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/brave-browser'];
const executablePath = candidates.find(candidate => candidate && existsSync(candidate));
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ ...(executablePath ? { executablePath } : {}), headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, reducedMotion: 'reduce' });
const page = await context.newPage();
const errors = [];
const checks = [];
const requests = [];
const contrastSnapshots = [];
async function auditContrast(label) { const result = await inspectTextContrast(page); contrastSnapshots.push({ label, ...result }); await writeFile(path.join(output, 'contrast.json'), JSON.stringify(contrastSnapshots, null, 2) + '\n'); }
page.on('pageerror', error => errors.push(error.message));
page.on('response', response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
page.on('request', request => { if (request.method() === 'POST') requests.push(new URL(request.url()).pathname); });
const record = (name, details = {}) => { checks.push({ name, passed: true, ...details }); console.log(`PASS ${name}`); };
async function data(route) {
  return await page.evaluate(async route => { const response = await fetch(`/api${route}`, { headers: { Authorization: 'Bearer demo-operator' } }); if (!response.ok) throw new Error(`Read failed: ${response.status}`); return await response.json(); }, route);
}
async function selected() { const id = await page.locator('.case-selected').getAttribute('data-case'); assert.ok(id, 'A case is selected'); return await data(`/cases/${id}`); }
async function choose(order) {
  await page.locator('#search').fill(order);
  await page.locator('.case-row').filter({ has: page.locator('.order-number', { hasText: `#${order}` }) }).first().click();
  await page.waitForFunction(order => document.querySelector('.detail-breadcrumb')?.textContent?.includes(`ORDER #${order}`), order);
  await page.waitForFunction(() => document.querySelector('#case-detail')?.getAttribute('aria-busy') === 'false');
}
async function action(kind) {
  const button = page.locator(`#case-detail [data-action="${kind}"]`);
  assert.equal(await button.count(), 1, `One ${kind} control exists`);
  await button.click();
  await page.waitForFunction(() => document.querySelector('#case-detail')?.getAttribute('aria-busy') === 'false');
  return selected();
}
async function complete(order, hold = false, interruptHold = false) {
  await choose(order);
  let view = await selected();
  if (hold && view.permitted.hold) {
    if (interruptHold) {
      await page.getByRole('button', { name: 'Simulation lab', exact: true }).click();
      await page.locator('#fault-action').selectOption('warehouse_hold');
      await page.locator('#fault-type').selectOption('lost_response');
      await page.getByRole('button', { name: 'Queue simulation', exact: true }).click();
      await page.waitForFunction(() => !document.querySelector('dialog'));
    }
    view = await action('hold');
    if (interruptHold) {
      assert.equal(view.status, 'needs-information');
      assert.equal(view.permitted.approve, false);
      assert.equal(view.permitted.execute, false);
      assert.ok(view.warehouse_attempts.some(attempt => attempt.status === 'uncertain'));
      assert.ok((await page.locator('.warehouse-progress').innerText()).includes('Hold outcome is unconfirmed'));
      await auditContrast('Uncertain warehouse hold');
      view = await action('retry');
      assert.equal(view.warehouse_attempts.length, 1, 'Reconciliation reuses the recorded warehouse operation');
      record('Lost warehouse response stays unconfirmed until the same operation is reconciled');
    }
    assert.ok(view.warehouse_attempts?.some(attempt => attempt.status === 'succeeded' && attempt.verified_at), `${order}: hold has durable verified read-back`);
    assert.ok((await page.locator('.warehouse-progress').innerText()).includes('Acknowledgment verified by read-back'));
    await auditContrast(`Verified hold and proposed plan ${order}`);
  }
  if (!view.plan && view.permitted.investigate) view = await action('investigate');
  if (view.permitted.approve) {
    view = await action('approve');
    assert.equal(await page.locator('[data-action="execute"]').evaluate(el => el === document.activeElement), true, 'Keyboard focus advances from approval to execution');
  }
  assert.ok(view.permitted.execute, `${order}: plan approved for execution`);
  assert.equal(view.approved, true, `${order}: backend records approval independently of role`);
  assert.equal(await page.locator('.detail-title-row .status').innerText(), 'Ready to execute');
  return action('execute');
}
try {
  await page.goto(baseURL, { waitUntil: 'networkidle' });
  const meta = await data('/meta');
  assert.equal(meta.mode, 'local simulator', 'Browser tests require the local simulator');
  assert.equal(meta.capabilities.live_mutations, false);
  assert.equal(meta.interpreter_mode, 'deterministic');
  await page.locator('.case-row').first().waitFor();
  assert.equal(await page.locator('.case-row').count(), 6, 'Run with freshly reset demo data');
  assert.ok((await page.locator('.mode-badge').innerText()).includes('Local simulator'));
  assert.ok((await page.locator('#interpreter-label').innerText()).includes('Deterministic'));
  record('Live local API loaded six seeded cases with honest mode labels');
  const observedCases = await data('/cases');
  const preLabelCase = observedCases.cases.find(c => c.order_id === '1042');
  const presentationSnapshots = { meta, caseView: await data(`/cases/${preLabelCase.id}`) };
  await auditContrast('Initial joined evidence');

  await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true });
  for (const width of [1440, 1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: width < 700 ? 844 : 1100 });
    const overflow = await page.evaluate(() => ({ viewport: window.innerWidth, width: document.documentElement.scrollWidth }));
    assert.ok(overflow.width <= overflow.viewport, `No horizontal document overflow at ${width}px: ${overflow.width}`);
    assert.ok(await page.locator('h1').isVisible());
    if (width === 390) await page.screenshot({ path: path.join(output, 'mobile.png'), fullPage: true });
  }
  record('Responsive layouts at 320, 390, 768, 1024 and 1440px without document overflow');
  await page.setViewportSize({ width: 1440, height: 1100 });

  await page.locator('#search').fill('a-customer-who-does-not-exist');
  assert.equal(await page.locator('.case-row').count(), 0);
  assert.ok((await page.locator('#queue-list').innerText()).includes('No matching cases'));
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  assert.equal(await page.locator('.case-row').count(), 6);
  record('Case search and recoverable empty state');

  await choose('1043');
  assert.ok((await page.locator('.snapshot-grid').innerText()).includes('Label printed'));
  assert.ok((await page.locator('.snapshot-grid').innerText()).includes('Awaiting confirmation'));
  assert.equal(await page.locator('[data-action="approve"]').count(), 0);
  assert.ok(await page.locator('[data-action="hold"]').isVisible());
  await page.locator('#tab-evidence').click();
  assert.ok(await page.locator('.timeline').isVisible());
  await auditContrast('Evidence timeline');
  await page.locator('#tab-evidence').press('ArrowRight');
  assert.equal(await page.locator('#tab-customer').getAttribute('aria-selected'), 'true');
  assert.ok((await page.locator('.draft-card-footer').innerText()).includes('No message has been sent'));
  await auditContrast('Customer draft');
  await page.locator('#tab-recovery').click();
  record('Printed label is distinct from physical dispatch; evidence and keyboard-accessible draft tabs');

  await page.locator('#role').selectOption('viewer');
  await page.waitForFunction(() => document.querySelector('.viewer-notice'));
  assert.equal(await page.locator('#case-detail [data-action="hold"]:enabled').count(), 0);
  assert.equal(await page.locator('#case-detail [data-action="approve"]:enabled').count(), 0);
  await page.locator('#role').selectOption('operator');
  await page.waitForFunction(() => document.querySelector('#case-detail')?.getAttribute('aria-busy') === 'false' && !document.querySelector('.viewer-notice'));
  record('Read-only role removes mutation authority and explains the role');

  let result = await complete('1042');
  assert.equal(result.status, 'resolved');
  assert.equal(result.order.payment.refunds.length, 1);
  record('Pre-label cancellation approved, executed and verified through UI');
  result = await complete('1043', true, true);
  assert.equal(result.status, 'resolved');
  assert.ok(result.order.labels.every(label => label.status === 'void'));
  assert.ok((await page.locator('.snapshot-grid').innerText()).includes('Label voided'));
  record('Post-label cancellation requires hold, approval, void and final verification');
  result = await complete('1044', true);
  assert.equal(result.status, 'resolved');
  assert.equal(result.order.labels.filter(label => label.status === 'active').length, 1);
  assert.equal(result.order.address.line1, '27 Willow Lane');
  record('Address correction with one replacement label completes through UI');

  result = await complete('1045');
  if (result.status === 'reconciling') result = await action('retry');
  assert.equal(result.status, 'resolved');
  assert.equal(result.order.payment.refunds.length, 1);
  record('Lost refund response reconciles to one refund through UI');
  result = await complete('1046', true);
  assert.equal(result.status, 'escalated');
  assert.ok((await page.locator('.case-notice').innerText()).includes('operator review'));
  record('Carrier void rejection remains visibly escalated');
  await choose('1047');
  result = await selected();
  assert.equal(result.status, 'escalated');
  assert.equal(result.permitted.execute, false);
  record('Partially dispatched case stays under operator review');

  await page.getByRole('button', { name: 'New request', exact: true }).click();
  await page.locator('#order-select').selectOption('1048');
  await page.locator('#request-text').fill('Please help with this order.');
  await page.getByRole('button', { name: 'Create request', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('dialog') && document.querySelector('.detail-breadcrumb')?.textContent?.includes('1048'));
  await page.locator('[data-action="clarify"]').click();
  await page.locator('#clarify-intent').selectOption('cancel');
  await page.getByRole('button', { name: 'Save clarification', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('dialog'));
  result = await selected();
  if (!result.plan) result = await action('investigate');
  assert.equal(result.intent, 'cancel');
  await page.getByRole('button', { name: 'Simulation lab', exact: true }).click();
  await page.locator('#fault-action').selectOption('refund');
  await page.locator('#fault-type').selectOption('before_write');
  await page.getByRole('button', { name: 'Queue simulation', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('dialog'));
  await action('approve');
  result = await action('execute');
  assert.equal(result.status, 'failed');
  assert.equal(result.order.commercial_state, 'cancelled');
  assert.equal(result.order.payment.refunds.length, 0);
  await page.locator('[data-action="dismiss-toast"]').click().catch(() => {});
  await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: path.join(output, 'partial-failure.png'), fullPage: true });
  await auditContrast('Incomplete refund recovery');
  result = await action('retry');
  assert.equal(result.status, 'resolved');
  assert.equal(result.order.payment.refunds.length, 1);
  record('New request, ambiguity clarification, fault injection, partial failure and safe retry');

  await page.locator('#tab-customer').click();
  assert.ok((await page.locator('.draft-body').innerText()).length > 30);
  assert.equal(requests.some(route => /send|notif|message/.test(route)), false);
  assert.equal(errors.length, 0, errors.join('\n'));
  record('Customer explanation remains a local draft; no console/page/network errors');
  const presentation = await checkPresentationStates(browser, baseURL, presentationSnapshots);
  await writeFile(path.join(output, 'presentation-report.json'), JSON.stringify(presentation, null, 2) + '\n');
  const contrastFailures = contrastSnapshots.flatMap(snapshot => snapshot.failures.map(failure => ({ ...failure, snapshot: snapshot.label })));
  assert.equal(contrastFailures.length, 0, `Text contrast issues: ${JSON.stringify(contrastFailures)}`);
  record('Visible text meets measured contrast thresholds in recovery, evidence, draft and failure views', { checked: contrastSnapshots.reduce((sum,snapshot) => sum+snapshot.checked,0), minimum_ratio: Math.min(...contrastSnapshots.map(snapshot => snapshot.minimum_ratio)), scope: 'Computed solid-background text; not a complete accessibility certification.' });
  await writeFile(path.join(output, 'report.json'), JSON.stringify({ passed: true, created_at: new Date().toISOString(), base_url: baseURL, synthetic: true, integration_mode: meta.mode, interpreter_mode: meta.interpreter_mode, browser: await browser.version(), checks, presentation_checks: presentation.checks, presentation_disclosure: presentation.disclosure, errors, mutation_routes: requests }, null, 2) + '\n');
  console.log(`Browser acceptance passed: ${checks.length} checks. Evidence: ${output}`);
} catch (error) {
  await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }).catch(() => {});
  await writeFile(path.join(output, 'report.json'), JSON.stringify({ passed: false, created_at: new Date().toISOString(), checks, errors, failure: String(error), mutation_routes: requests }, null, 2) + '\n');
  throw error;
} finally { await context.close(); await browser.close(); }
