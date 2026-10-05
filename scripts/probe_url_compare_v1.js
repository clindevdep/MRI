/**
 * Probe: with the PATCHED Solo ID context, compare the PAR stage's legacy
 * portal URL against the current one, to confirm whether the host/path the
 * downloader navigates to still reaches a rendered product details page.
 *
 * Usage: node probe_url_compare_v1.js <procedure_code>
 */
import { chromium } from 'playwright';
import { createSoloIDBrowser } from './src/solo_id_v10.js';

const procedure = process.argv[2] || 'AT/H/1569/001';
const enc = encodeURIComponent(procedure);
const URLS = [
  `https://mri.cts-mrp.eu/portal/details?productnumber=${enc}`,      // legacy (what process_molecule_v10 uses)
  `https://mri-production.cts-mrp.eu/details?productnumber=${enc}`,  // current (probe-verified)
];
const log = (m) => console.log(m);

(async () => {
  const { browser, page } = await createSoloIDBrowser(chromium, { headless: true });
  try {
    for (const url of URLS) {
      log(`\n→ ${url}`);
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(e => log(`  goto err: ${e.message.slice(0,80)}`));
      await page.waitForTimeout(7000);
      const finalUrl = page.url();
      const anchors = await page.locator('a[href]').count().catch(() => -1);
      const docTab = await page.locator('text=Documents').count().catch(() => -1);
      const icons = await page.locator('mat-icon:has-text("archive")').count().catch(() => -1);
      const bodyLen = await page.evaluate(() => document.body.innerText.length).catch(() => 0);
      log(`  finalUrl=${finalUrl}`);
      log(`  anchors=${anchors} textDocuments=${docTab} archiveIcons=${icons} bodyTextLen=${bodyLen}`);
      log(`  VERDICT: ${icons > 0 ? 'RENDERS + has archive icons' : 'NO archive icons (unusable)'}`);
    }
  } catch (e) {
    log(`ERROR: ${e.message}`);
  } finally {
    await browser.close().catch(() => {});
  }
})();
