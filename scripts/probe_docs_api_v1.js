/**
 * Diagnostic probe: can we obtain PAR documents for a product via the portal's
 * OData ProductSearch API (the v22 pattern) instead of DOM-scraping a
 * "Documents" tab (which the current Angular portal no longer renders)?
 *
 * Usage: node probe_docs_api_v1.js <procedure_code> [mode] [outDir]
 *   mode: solo (solo_id_v10 fingerprint) | plain (vanilla context)
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { createSoloIDBrowser } from './src/solo_id_v10.js';

const procedure = process.argv[2] || 'DE/H/8231/004';
const mode = process.argv[3] || 'solo';
const outDir = process.argv[4] || '/data/runs/_probe';
fs.mkdirSync(outDir, { recursive: true });
const tag = `${procedure.replace(/[^A-Za-z0-9]/g, '_')}_${mode}`;
const BASES = ['https://mri-production.cts-mrp.eu', 'https://mri.cts-mrp.eu'];
const log = (m) => console.log(m);

(async () => {
  let browser, context, page;
  if (mode === 'solo') {
    ({ browser, context, page } = await createSoloIDBrowser(chromium, { headless: true }));
  } else {
    browser = await chromium.launch({ headless: true, args: ['--single-process'] });
    context = await browser.newContext({ acceptDownloads: true });
    page = await context.newPage();
  }

  const report = { procedure, mode, attempts: [] };
  try {
    for (const base of BASES) {
      const attempt = { base, productSearchCaptured: false, badResponses: [], consoleErrors: [], documents: [], downloads: [] };
      const seen = [];
      const onResp = (r) => {
        const u = r.url();
        if (u.includes('/v1/odata/')) seen.push(`${r.status()} ${u.slice(0, 160)}`);
        if (r.status() >= 400) attempt.badResponses.push(`${r.status()} ${u.slice(0, 160)}`);
      };
      const onErr = (m) => { if (m.type() === 'error') attempt.consoleErrors.push(m.text().slice(0, 200)); };
      page.on('response', onResp);
      page.on('console', onErr);

      const url = `${base}/details?productnumber=${encodeURIComponent(procedure)}`;
      log(`\n→ [${mode}] goto ${url}`);
      const respPromise = page.waitForResponse(
        (r) => r.request().method() === 'GET' && r.status() === 200 && r.url().includes('/v1/odata/ProductSearch'),
        { timeout: 45000 }
      ).catch(() => null);

      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch((e) => log(`  goto error: ${e.message}`));
      const resp = await respPromise;
      attempt.finalUrl = page.url();
      attempt.odataSeen = seen.slice(0, 15);

      if (resp) {
        attempt.productSearchCaptured = true;
        attempt.productSearchUrl = resp.url().slice(0, 300);
        const payload = await resp.json().catch(() => null);
        const product = Array.isArray(payload?.value)
          ? payload.value.find((i) => i?.productKey === procedure) || payload.value[0]
          : null;
        attempt.productFound = !!product;
        if (product) {
          attempt.productKey = product.productKey;
          attempt.topLevelKeys = Object.keys(product);
          attempt.documents = (product.documents || []).map((d) => ({ ...d }));
          log(`  ✓ ProductSearch captured; documents: ${attempt.documents.length}`);

          // Try downloading every document that claims content
          for (const d of attempt.documents) {
            if (!d?.apiId || d?.hasContent !== true) continue;
            const dl = `${base}/v1/odata/Document(documentApiId='${d.apiId}')/Download`;
            try {
              const r = await context.request.get(dl, { timeout: 60000 });
              const buf = await r.body();
              attempt.downloads.push({
                name: d.name || d.documentName || d.type || '(unnamed)',
                hasContent: d.hasContent, url: dl,
                status: r.status(), bytes: buf.length,
                sig: buf.subarray(0, 5).toString('binary'),
                ctype: (r.headers()['content-type'] || '').slice(0, 60),
                cdisp: (r.headers()['content-disposition'] || '').slice(0, 120),
              });
            } catch (e) {
              attempt.downloads.push({ name: d.name || '(unnamed)', url: dl, error: e.message.slice(0, 160) });
            }
          }
        }
      } else {
        log('  ✗ ProductSearch NOT captured');
      }

      page.off('response', onResp);
      page.off('console', onErr);
      report.attempts.push(attempt);
      if (attempt.productSearchCaptured) break; // first working base is enough
    }
  } catch (e) {
    report.error = e.message;
    log(`ERROR: ${e.message}`);
  } finally {
    const p = path.join(outDir, `docsapi_${tag}.json`);
    fs.writeFileSync(p, JSON.stringify(report, null, 2));
    log(`\n===== SUMMARY (${mode}) =====`);
    for (const a of report.attempts) {
      log(`base=${a.base} captured=${a.productSearchCaptured} productFound=${a.productFound} docs=${a.documents.length}`);
      log(`  finalUrl=${a.finalUrl}`);
      if (a.odataSeen?.length) log(`  odata: ${JSON.stringify(a.odataSeen.slice(0, 5))}`);
      if (a.badResponses.length) log(`  bad: ${JSON.stringify(a.badResponses.slice(0, 5))}`);
      if (a.consoleErrors.length) log(`  consoleErr: ${JSON.stringify(a.consoleErrors.slice(0, 3))}`);
      for (const d of a.downloads) log(`  DOC ${JSON.stringify(d)}`);
      a.documents.forEach((d, i) => log(`  docObj[${i}]: ${JSON.stringify(d)}`));
    }
    log(`saved: ${p}`);
    await browser.close().catch(() => {});
  }
})();
