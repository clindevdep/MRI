/**
 * One-off diagnostic probe: load a lakemedelsverket "sok-lakemedelsfakta"
 * facts page (the URL found in the MRI portal's Material tooltip) and dump how
 * the actual PAR / (s)PAR PDF is linked from there — anchors, PDFs, docetp
 * refs, Material tooltip buttons.
 *
 * Usage: node probe_facts_v1.js <url> [outDir]
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { createSoloIDBrowser, humanDelay } from './src/solo_id_v10.js';

const url = process.argv[2] || 'https://www.lakemedelsverket.se/sv/sok-lakemedelsfakta/lakemedel/20170420000035';
const outDir = process.argv[3] || '/data/runs/_probe';
fs.mkdirSync(outDir, { recursive: true });
const tag = 'facts_' + url.replace(/[^A-Za-z0-9]/g, '_').slice(-40);
const log = (m) => console.log(m);

(async () => {
  const { browser, context, page } = await createSoloIDBrowser(chromium, { headless: true });
  try {
    log(`→ goto ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 40000 });
    await humanDelay(2500, 4000);
    await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => log('  (network not idle)'));

    const content = await page.content();
    if (/Access Denied|403 Forbidden/.test(content)) {
      log('🚫 BLOCKED (403) — probe inconclusive'); await browser.close(); process.exit(3);
    }

    // Try to accept a cookie banner (Swedish gov sites often gate content)
    for (const t of ['Godkänn alla', 'Godkänn', 'Acceptera alla', 'Acceptera', 'Tillåt alla', 'Accept all']) {
      const b = page.locator(`text=${t}`).first();
      if (await b.count() > 0) { await b.click().catch(() => {}); await humanDelay(800, 1500); log(`  (clicked cookie: ${t})`); break; }
    }

    // Expand any accordions/expanders that may hide the documents
    const expanders = await page.locator('button[aria-expanded="false"], .accordion button, summary').all();
    for (const e of expanders.slice(0, 15)) { await e.click().catch(() => {}); }
    await humanDelay(1000, 1800);

    const anchors = await page.$$eval('a[href]', els =>
      els.map(a => ({ href: a.href, text: (a.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 90) })));

    const pdfs = anchors.filter(a => /\.pdf(\?|$)/i.test(a.href));
    const docetp = anchors.filter(a => /docetp|mpa\.se/i.test(a.href));
    const parText = anchors.filter(a => /par|utredningsrapport|assessment|offentlig/i.test(a.text + ' ' + a.href));

    const matIcons = await page.$$eval('mat-icon', els => {
      const c = {}; els.forEach(e => { const t = (e.textContent || '').trim(); c[t] = (c[t] || 0) + 1; }); return c;
    }).catch(() => ({}));

    // tooltip-style external links (same pattern as the MRI portal)
    const tooltipLinks = await page.evaluate(() => {
      const out = [];
      document.querySelectorAll('[id^="cdk-describedby-message"], [role="tooltip"]').forEach(d => {
        const t = (d.textContent || '').trim(); if (/https?:\/\//.test(t)) out.push(t.slice(0, 160));
      });
      return out;
    });

    const report = { url, counts: {
        anchors: anchors.length, pdfs: pdfs.length, docetpAnchors: docetp.length,
        parTextAnchors: parText.length, matIcons, tooltipLinks: tooltipLinks.length },
      pdfs, docetp, parText, tooltipLinks, headings: await page.$$eval('h1,h2,h3', els => els.map(h => (h.textContent||'').trim().slice(0,90)).filter(Boolean).slice(0,20)) };

    fs.writeFileSync(path.join(outDir, `probe_${tag}.json`), JSON.stringify(report, null, 2));
    fs.writeFileSync(path.join(outDir, `probe_${tag}.html`), content);

    log('\n===== FACTS-PAGE PROBE SUMMARY =====');
    log(`anchors: ${anchors.length} | pdfs: ${pdfs.length} | docetp anchors: ${docetp.length} | PAR-text anchors: ${parText.length}`);
    log(`mat-icons: ${JSON.stringify(matIcons)}`);
    log(`tooltip links: ${JSON.stringify(tooltipLinks).slice(0, 400)}`);
    if (pdfs.length) log(`PDFs:\n${pdfs.map(p => '  • ' + p.text + ' -> ' + p.href).join('\n').slice(0, 1200)}`);
    if (docetp.length) log(`DOCETP:\n${docetp.map(p => '  • ' + p.text + ' -> ' + p.href).join('\n').slice(0, 1200)}`);
    if (parText.length) log(`PAR-TEXT:\n${parText.map(p => '  • ' + p.text + ' -> ' + p.href).join('\n').slice(0, 1200)}`);
    log(`headings: ${JSON.stringify(report.headings).slice(0, 400)}`);
    log(`\nsaved: ${outDir}/probe_${tag}.json + .html`);
  } catch (e) {
    log(`ERROR: ${e.message}`);
  } finally {
    await browser.close();
  }
})();
