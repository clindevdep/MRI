// v26 UI smoke test (scope switch, PAR batch limit, continue controls).
// Run inside a throwaway container from the image under test, e.g.
//   docker cp tests/ui_test_v26.mjs <ctr>:/app/scripts/ && docker exec <ctr> node /app/scripts/ui_test_v26.mjs
// Expects runs named ui_core (status core_complete) and ui_batch (status batch_complete) in /data/runs.

import { chromium } from 'playwright';
const B = 'http://localhost:8502';
const out = [];
const log = (k, v) => { out.push(`${k}: ${v}`); };
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 2000 } });
const settle = async () => { await page.waitForTimeout(2500); };

// ── New Run page
await page.goto(`${B}/New_Run`); await settle();
const body = async () => (await page.locator('[data-testid="stMain"]').innerText()).replace(/\s+/g, ' ');
let t = await body();
log('newrun.has_scope_title', t.includes('Run scope'));
log('newrun.has_full_run', t.includes('Full run'));
log('newrun.has_core_only', t.includes('Core base generation only'));
log('newrun.has_limit_toggle', t.includes('Limit PAR downloads per session'));
log('newrun.default_unlimited_caption', t.includes('unlimited'));
log('newrun.number_input_hidden_by_default', !t.includes('PAR PDFs to download in this session'));
const sel = async (label) => page.locator('[data-testid="stButtonGroup"] button', { hasText: label }).first();
log('newrun.full_run_selected_default', await (await sel('Full run')).getAttribute('aria-checked') ?? await (await sel('Full run')).getAttribute('kind'));
await page.screenshot({ path: '/tmp/ui_newrun_default.png', fullPage: true });

await page.getByText('Limit PAR downloads per session').click(); await settle();
t = await body();
log('newrun.limit_on_shows_number', t.includes('PAR PDFs to download in this session'));
log('newrun.limit_default_value', await page.getByLabel('PAR PDFs to download in this session').inputValue());
await page.screenshot({ path: '/tmp/ui_newrun_limit.png', fullPage: true });

await (await sel('Core base generation only')).click(); await settle();
t = await body();
log('newrun.core_hides_limit', !t.includes('Limit PAR downloads per session'));
log('newrun.core_caption', t.includes('Stops once the Core Database is built'));
await page.screenshot({ path: '/tmp/ui_newrun_core.png', fullPage: true });

await page.getByText('From Core Database').click(); await settle();
log('newrun.fullmode_switch_disabled', await (await sel('Full run')).isDisabled());
t = await body();
log('newrun.fullmode_caption', t.includes('always runs in full'));

// ── Dashboard: core_complete run
for (const [name, expectBtn] of [['ui_core', 'Download PARs'], ['ui_batch', 'Download next batch']]) {
  await page.goto(`${B}/`); await settle();
  await page.locator('[data-testid="stSelectbox"]').first().click();
  await page.getByRole('option', { name }).click(); await settle();
  t = await body();
  log(`dash.${name}.status`, (t.match(/Status: ([^—]+)/) || [])[1]);
  log(`dash.${name}.scope_caption`, (t.match(/Scope: [^·]+· PAR limit this session: \S+/) || [])[0]);
  log(`dash.${name}.continue_button`, await page.getByRole('button', { name: expectBtn }).count());
  log(`dash.${name}.limit_toggle`, t.includes('Limit PAR downloads per session'));
  await page.screenshot({ path: `/tmp/ui_dash_${name}.png`, fullPage: true });
  await page.getByRole('tab', { name: 'Results' }).click(); await settle();
  t = await body();
  log(`dash.${name}.results_shown`, t.includes('Download All Results'));
  log(`dash.${name}.results_note`, t.includes('Core base generation only — the Core Database is ready') || t.includes('Partial results'));
}
// ui_batch toggle should default ON with value 3 (last session's limit)
log('dash.ui_batch.limit_prefilled', await page.getByLabel('PAR PDFs to download in this session').first().inputValue().catch(e => 'n/a'));

// ── History
await page.goto(`${B}/History`); await settle();
t = await body();
log('history.core_label', t.includes('Core database ready'));
log('history.batch_label', t.includes('Batch complete — more to download'));
await page.getByText('ui_core', { exact: false }).first().click(); await settle();
log('history.ui_core.download_pars_btn', await page.getByRole('button', { name: 'Download PARs' }).count());
log('history.ui_core.view_results_btn', await page.getByRole('button', { name: 'View Results' }).count());
await page.screenshot({ path: '/tmp/ui_history.png', fullPage: true });
const exc = await page.locator('[data-testid="stException"]').count();
log('history.exceptions', exc);
await browser.close();
console.log(out.join('\n'));
