// v26 UI smoke test (scope switch, PAR batch limit, continue controls).
// Run inside a throwaway container from the image under test, e.g.
//   docker cp tests/ui_test_v26.mjs <ctr>:/app/scripts/ && docker exec <ctr> node /app/scripts/ui_test_v26.mjs
// Expects runs named ui_core (status core_complete) and ui_batch (status batch_complete, par_limit 3) in /data/runs.
import { chromium } from 'playwright';
const B = 'http://localhost:8502';
const out = [];
const log = (k, v) => { out.push(`${k}: ${v}`); };
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 2000 } });
const settle = async () => { await page.waitForTimeout(2500); };
const body = async () => (await page.locator('[data-testid="stMain"]').innerText()).replace(/\s+/g, ' ');
const sw = () => page.locator('[data-testid="stCheckbox"]', { hasText: 'Core base generation only' }).locator('input');
const limit = () => page.getByRole('spinbutton', { name: 'PAR PDF limit for this session (0 = unlimited)' });

// ── New Run page
await page.goto(`${B}/New_Run`); await settle();
let t = await body();
log('newrun.no_segmented_control', await page.locator('[data-testid="stButtonGroup"]').count() === 0);
log('newrun.switch_present', await sw().count() === 1);
log('newrun.switch_off_by_default', !(await sw().isChecked()));
log('newrun.full_run_caption', t.includes('Full run — Core Database'));
log('newrun.no_limit_toggle', !t.includes('Limit PAR downloads per session'));
log('newrun.limit_default_0', (await limit().inputValue()) === '0');
await page.screenshot({ path: '/tmp/ui_newrun_default.png', fullPage: true });

await page.getByText('Core base generation only').first().click(); await settle();
t = await body();
log('newrun.switch_on', await sw().isChecked());
log('newrun.core_hides_limit', await limit().count() === 0);
log('newrun.core_caption', t.includes('stops once the Core Database is built'));
await page.screenshot({ path: '/tmp/ui_newrun_core.png', fullPage: true });

await page.getByText('From Core Database').click(); await settle();
log('newrun.fullmode_switch_disabled', await sw().isDisabled());
log('newrun.fullmode_caption', (await body()).includes('always runs in full'));

// ── Dashboard
for (const [name, btn, expLimit] of [['ui_core', 'Download PARs', '0'], ['ui_batch', 'Download next batch', '3']]) {
  await page.goto(`${B}/`); await settle();
  await page.locator('[data-testid="stSelectbox"]').first().click();
  await page.getByRole('option', { name }).click(); await settle();
  log(`dash.${name}.continue_button`, await page.getByRole('button', { name: btn }).count() === 1);
  log(`dash.${name}.limit_prefilled_${expLimit}`, (await limit().first().inputValue()) === expLimit);
  await page.screenshot({ path: `/tmp/ui_dash_${name}.png`, fullPage: true });
}

// ── History
await page.goto(`${B}/History`); await settle();
t = await body();
log('history.core_label', t.includes('Core database ready'));
log('history.batch_label', t.includes('Batch complete — more to download'));
log('history.exceptions_0', await page.locator('[data-testid="stException"]').count() === 0);
await browser.close();
console.log(out.join('\n'));
