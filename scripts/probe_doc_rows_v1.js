/**
 * Probe: map each "archive" download icon on the product details page to the
 * document it belongs to, so the downloader can skip rows that have no file
 * (documentType PRODUCT / hasContent false) instead of burning a download
 * timeout on them.
 *
 * Usage: node probe_doc_rows_v1.js <procedure_code>
 */
import { chromium } from 'playwright';
import { createSoloIDBrowser } from './src/solo_id_v10.js';

const procedure = process.argv[2] || 'AT/H/1569/001';
const BASE = 'https://mri-production.cts-mrp.eu';
const log = (m) => console.log(m);

(async () => {
  const { browser, page } = await createSoloIDBrowser(chromium, { headless: true });
  try {
    const respPromise = page.waitForResponse(
      (r) => r.request().method() === 'GET' && r.status() === 200 && r.url().includes('/v1/odata/ProductSearch'),
      { timeout: 45000 }
    ).catch(() => null);

    await page.goto(`${BASE}/details?productnumber=${encodeURIComponent(procedure)}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    const resp = await respPromise;
    await page.waitForTimeout(6000);

    if (resp) {
      const payload = await resp.json().catch(() => null);
      const product = Array.isArray(payload?.value) ? payload.value.find(i => i?.productKey === procedure) || payload.value[0] : null;
      log('API documents (in API order):');
      (product?.documents || []).forEach((d, i) =>
        log(`  [${i}] hasContent=${d.hasContent} type=${d.documentType} name=${d.documentName}`));
    }

    // For every archive icon, dump its surrounding row/ancestor text + attributes
    const mapping = await page.$$eval('mat-icon', (els) => {
      const out = [];
      els.forEach((el, idx) => {
        if ((el.textContent || '').trim() !== 'archive') return;
        const info = { iconIndex: idx, ancestors: [] };
        let n = el;
        for (let up = 0; up < 6 && n; up++) {
          n = n.parentElement;
          if (!n) break;
          info.ancestors.push({
            up: up + 1,
            tag: n.tagName.toLowerCase(),
            cls: (n.className || '').toString().slice(0, 80),
            text: (n.innerText || n.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 160),
          });
        }
        const btn = el.closest('button, a');
        info.button = btn ? {
          tag: btn.tagName.toLowerCase(),
          disabled: btn.disabled ?? null,
          ariaLabel: btn.getAttribute('aria-label'),
          title: btn.getAttribute('title'),
          ariaDescribedby: btn.getAttribute('aria-describedby'),
          cls: (btn.className || '').toString().slice(0, 100),
        } : null;
        out.push(info);
      });
      return out;
    });

    log(`\narchive icons found: ${mapping.length}`);
    mapping.forEach((m, i) => {
      log(`\n--- icon #${i + 1} (domIndex ${m.iconIndex})`);
      log(`  button: ${JSON.stringify(m.button)}`);
      m.ancestors.forEach(a => log(`  up${a.up} <${a.tag}> cls="${a.cls}" text="${a.text}"`));
    });

    // Also dump the documents table rows as a whole
    const rows = await page.$$eval('mat-row, tr, .mat-mdc-row, .mat-row', els =>
      els.map(r => (r.innerText || r.textContent || '').replace(/\s+/g, ' ').trim()).filter(Boolean).slice(0, 30)
    ).catch(() => []);
    log(`\ntable rows (${rows.length}):`);
    rows.forEach((r, i) => log(`  [${i}] ${r.slice(0, 180)}`));
  } catch (e) {
    log(`ERROR: ${e.message}`);
  } finally {
    await browser.close().catch(() => {});
  }
})();
