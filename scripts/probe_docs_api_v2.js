/**
 * Probe v2: with a PLAIN (non-forced-header) context, determine
 *   (A) whether the Angular portal renders the Documents tab / archive icons, and
 *   (B) which transport can actually fetch a PubAR document's bytes.
 *
 * Usage: node probe_docs_api_v2.js <procedure_code> [outDir]
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const procedure = process.argv[2] || 'AT/H/1569/001';
const outDir = process.argv[3] || '/data/runs/_probe';
fs.mkdirSync(outDir, { recursive: true });
const tag = procedure.replace(/[^A-Za-z0-9]/g, '_');
const BASE = 'https://mri-production.cts-mrp.eu';
const log = (m) => console.log(m);

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--single-process'] });
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  const report = { procedure, dom: {}, documents: [], downloads: {} };

  try {
    let psReqHeaders = null;
    page.on('request', (r) => {
      if (r.url().includes('/v1/odata/ProductSearch') && !psReqHeaders) psReqHeaders = r.headers();
    });

    const respPromise = page.waitForResponse(
      (r) => r.request().method() === 'GET' && r.status() === 200 && r.url().includes('/v1/odata/ProductSearch'),
      { timeout: 45000 }
    ).catch(() => null);

    const url = `${BASE}/details?productnumber=${encodeURIComponent(procedure)}`;
    log(`→ goto ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    const resp = await respPromise;
    await page.waitForTimeout(6000); // let Angular finish rendering

    report.psRequestHeaders = psReqHeaders;

    // ── (A) DOM state ──────────────────────────────────────────────
    report.dom.anchors = await page.locator('a[href]').count().catch(() => -1);
    report.dom.matIcons = await page.$$eval('mat-icon', els => {
      const c = {}; els.forEach(e => { const t = (e.textContent || '').trim(); c[t] = (c[t] || 0) + 1; }); return c;
    }).catch(() => ({}));
    report.dom.textDocumentsCount = await page.locator('text=Documents').count().catch(() => -1);
    report.dom.tabs = await page.$$eval('[role="tab"], .mat-mdc-tab, mat-tab', els =>
      els.map(e => (e.textContent || '').replace(/\s+/g, ' ').trim()).filter(Boolean)).catch(() => []);
    report.dom.bodyTextLen = (await page.evaluate(() => document.body.innerText.length).catch(() => 0));
    report.dom.bodySample = (await page.evaluate(() => document.body.innerText.slice(0, 400)).catch(() => ''));

    // ── documents from API ─────────────────────────────────────────
    let parDoc = null;
    if (resp) {
      const payload = await resp.json().catch(() => null);
      const product = Array.isArray(payload?.value)
        ? payload.value.find(i => i?.productKey === procedure) || payload.value[0] : null;
      report.documents = (product?.documents || []).map(d => ({
        apiId: d.apiId, documentName: d.documentName, documentType: d.documentType, hasContent: d.hasContent,
      }));
      parDoc = (product?.documents || []).find(d => d?.hasContent && /PubAR/i.test(d?.documentType || ''))
            || (product?.documents || []).find(d => d?.hasContent && /PAR/i.test(d?.documentName || ''));
    }
    report.parDoc = parDoc ? { apiId: parDoc.apiId, documentName: parDoc.documentName, documentType: parDoc.documentType } : null;
    log(`PAR doc: ${JSON.stringify(report.parDoc)}`);

    if (parDoc) {
      const dlUrl = `${BASE}/v1/odata/Document(documentApiId='${parDoc.apiId}')/Download`;
      report.downloadUrl = dlUrl;

      // (1) plain context.request
      try {
        const r = await context.request.get(dlUrl, { timeout: 45000 });
        const b = await r.body();
        report.downloads.contextRequestPlain = { status: r.status(), bytes: b.length, sig: b.subarray(0, 5).toString('binary'), cd: r.headers()['content-disposition'] || null };
      } catch (e) { report.downloads.contextRequestPlain = { error: e.message.slice(0, 120) }; }

      // (2) context.request with captured ProductSearch headers
      try {
        const h = { ...(psReqHeaders || {}) };
        delete h['content-length'];
        const r = await context.request.get(dlUrl, { headers: h, timeout: 45000 });
        const b = await r.body();
        report.downloads.contextRequestWithHeaders = { status: r.status(), bytes: b.length, sig: b.subarray(0, 5).toString('binary'), cd: r.headers()['content-disposition'] || null };
      } catch (e) { report.downloads.contextRequestWithHeaders = { error: e.message.slice(0, 120) }; }

      // (3) in-page fetch (browser network stack + session)
      try {
        const res = await page.evaluate(async (u) => {
          const r = await fetch(u, { credentials: 'include' });
          const buf = new Uint8Array(await r.arrayBuffer());
          let bin = '';
          const CH = 8192;
          for (let i = 0; i < buf.length; i += CH) bin += String.fromCharCode.apply(null, buf.subarray(i, i + CH));
          return { status: r.status, cd: r.headers.get('content-disposition'), ct: r.headers.get('content-type'), b64: btoa(bin) };
        }, dlUrl);
        const buf = Buffer.from(res.b64, 'base64');
        report.downloads.inPageFetch = { status: res.status, bytes: buf.length, sig: buf.subarray(0, 5).toString('binary'), cd: res.cd, ct: res.ct };
        if (buf.subarray(0, 4).toString('binary') === '%PDF') {
          const outPdf = path.join(outDir, `inpagefetch_${tag}.pdf`);
          fs.writeFileSync(outPdf, buf);
          report.downloads.inPageFetch.savedTo = outPdf;
        }
      } catch (e) { report.downloads.inPageFetch = { error: e.message.slice(0, 200) }; }

      // (4) page.goto + download event
      try {
        const dlPromise = page.waitForEvent('download', { timeout: 30000 });
        await page.goto(dlUrl, { timeout: 30000 }).catch(() => {});
        const d = await dlPromise;
        const p = path.join(outDir, `downloadevent_${tag}_${d.suggestedFilename()}`);
        await d.saveAs(p);
        const st = fs.statSync(p);
        const head = fs.readFileSync(p).subarray(0, 5).toString('binary');
        report.downloads.downloadEvent = { suggestedFilename: d.suggestedFilename(), bytes: st.size, sig: head, savedTo: p };
      } catch (e) { report.downloads.downloadEvent = { error: e.message.slice(0, 200) }; }
    }
  } catch (e) {
    report.error = e.message;
  } finally {
    const p = path.join(outDir, `docsapi2_${tag}.json`);
    fs.writeFileSync(p, JSON.stringify(report, null, 2));
    log('\n===== PROBE v2 SUMMARY =====');
    log(`DOM: anchors=${report.dom.anchors} textDocuments=${report.dom.textDocumentsCount} bodyTextLen=${report.dom.bodyTextLen}`);
    log(`DOM matIcons: ${JSON.stringify(report.dom.matIcons)}`);
    log(`DOM tabs: ${JSON.stringify(report.dom.tabs)}`);
    log(`DOM bodySample: ${JSON.stringify((report.dom.bodySample || '').slice(0, 200))}`);
    log(`docs(${report.documents.length}): ${JSON.stringify(report.documents)}`);
    log(`PAR doc: ${JSON.stringify(report.parDoc)}`);
    log(`psReqHeaders: ${JSON.stringify(report.psRequestHeaders)}`);
    log(`DOWNLOADS: ${JSON.stringify(report.downloads, null, 1)}`);
    log(`saved: ${p}`);
    await browser.close().catch(() => {});
  }
})();
