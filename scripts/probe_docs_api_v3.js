/**
 * Probe v3 (decisive): with a PLAIN context, verify end-to-end PAR retrieval
 *   (A) DOM path: click Documents tab -> click archive icons -> download events
 *   (B) API path: Document(...)/Download using the portal's own auth header
 *       (`youdontownmev1` JWT captured from a ProductSearch request)
 *
 * Usage: node probe_docs_api_v3.js <procedure_code> [outDir]
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const procedure = process.argv[2] || 'AT/H/1569/001';
const outDir = process.argv[3] || '/data/runs/_probe';
const saveDir = path.join(outDir, 'v3_' + procedure.replace(/[^A-Za-z0-9]/g, '_'));
fs.mkdirSync(saveDir, { recursive: true });
const BASE = 'https://mri-production.cts-mrp.eu';
const log = (m) => console.log(m);
const AUTH_HEADER = 'youdontownmev1';

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--single-process'] });
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  const report = { procedure, domDownloads: [], apiDownloads: {} };

  try {
    let psHeaders = null;
    page.on('request', (r) => {
      if (r.url().includes('/v1/odata/') && !psHeaders && r.headers()[AUTH_HEADER]) psHeaders = r.headers();
    });

    const respPromise = page.waitForResponse(
      (r) => r.request().method() === 'GET' && r.status() === 200 && r.url().includes('/v1/odata/ProductSearch'),
      { timeout: 45000 }
    ).catch(() => null);

    await page.goto(`${BASE}/details?productnumber=${encodeURIComponent(procedure)}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    const resp = await respPromise;
    await page.waitForTimeout(5000);

    const token = psHeaders ? psHeaders[AUTH_HEADER] : null;
    report.tokenCaptured = !!token;
    log(`token captured: ${!!token}`);

    // documents from API
    let docs = [];
    if (resp) {
      const payload = await resp.json().catch(() => null);
      const product = Array.isArray(payload?.value)
        ? payload.value.find(i => i?.productKey === procedure) || payload.value[0] : null;
      docs = product?.documents || [];
    }
    const parDocs = docs.filter(d => d?.hasContent && (/PubAR/i.test(d?.documentType || '') || /\bPAR\b|^PAR|_PAR/i.test(d?.documentName || '')));
    report.parDocs = parDocs.map(d => ({ apiId: d.apiId, documentName: d.documentName, documentType: d.documentType }));
    log(`PAR docs: ${JSON.stringify(report.parDocs)}`);

    // ── (A) DOM path ───────────────────────────────────────────────
    try {
      const docTab = page.locator('text=Documents').first();
      if (await docTab.count() > 0) {
        await docTab.click({ timeout: 10000 }).catch(e => log(`  tab click: ${e.message.slice(0,80)}`));
        await page.waitForTimeout(2500);
        log('✓ clicked Documents');
      }
      const icons = await page.locator('mat-icon:has-text("archive")').all();
      report.archiveIconCount = icons.length;
      log(`archive icons: ${icons.length}`);
      for (let i = 0; i < icons.length; i++) {
        try {
          const dlPromise = page.waitForEvent('download', { timeout: 25000 });
          await icons[i].click({ timeout: 10000 });
          const d = await dlPromise;
          const fn = d.suggestedFilename();
          const p = path.join(saveDir, `dom_${i + 1}_${fn}`);
          await d.saveAs(p);
          const buf = fs.readFileSync(p);
          report.domDownloads.push({ i: i + 1, filename: fn, bytes: buf.length, sig: buf.subarray(0, 5).toString('binary') });
          log(`  [${i + 1}] ${fn} ${buf.length}B sig=${buf.subarray(0, 4).toString('binary')}`);
        } catch (e) {
          report.domDownloads.push({ i: i + 1, error: e.message.slice(0, 120) });
          log(`  [${i + 1}] ERR ${e.message.slice(0, 80)}`);
        }
      }
    } catch (e) { report.domError = e.message.slice(0, 200); }

    // ── (B) API path with portal auth header ───────────────────────
    if (parDocs.length && token) {
      const d = parDocs[0];
      const dlUrl = `${BASE}/v1/odata/Document(documentApiId='${d.apiId}')/Download`;
      const variants = {
        tokenOnly: { [AUTH_HEADER]: token },
        tokenPdfAccept: { [AUTH_HEADER]: token, accept: 'application/pdf,application/octet-stream,*/*' },
        tokenFullBrowser: {
          [AUTH_HEADER]: token,
          accept: 'application/pdf,application/octet-stream,*/*',
          'user-agent': psHeaders['user-agent'],
          referer: `${BASE}/details?productnumber=${encodeURIComponent(procedure)}`,
        },
      };
      for (const [name, headers] of Object.entries(variants)) {
        try {
          const r = await context.request.get(dlUrl, { headers, timeout: 60000 });
          const b = await r.body();
          const rec = { status: r.status(), bytes: b.length, sig: b.subarray(0, 5).toString('binary'),
                        ct: r.headers()['content-type'] || null, cd: r.headers()['content-disposition'] || null };
          if (b.subarray(0, 4).toString('binary') === '%PDF') {
            const p = path.join(saveDir, `api_${name}.pdf`);
            fs.writeFileSync(p, b); rec.savedTo = p;
          }
          report.apiDownloads[name] = rec;
          log(`  API ${name}: ${JSON.stringify(rec)}`);
        } catch (e) {
          report.apiDownloads[name] = { error: e.message.slice(0, 140) };
          log(`  API ${name}: ERR ${e.message.slice(0, 100)}`);
        }
      }
    }
  } catch (e) {
    report.error = e.message;
    log(`ERROR: ${e.message}`);
  } finally {
    const p = path.join(outDir, `docsapi3_${procedure.replace(/[^A-Za-z0-9]/g, '_')}.json`);
    fs.writeFileSync(p, JSON.stringify(report, null, 2));
    log('\n===== PROBE v3 SUMMARY =====');
    log(JSON.stringify(report, null, 1));
    log(`saved: ${p}  files in: ${saveDir}`);
    await browser.close().catch(() => {});
  }
})();
