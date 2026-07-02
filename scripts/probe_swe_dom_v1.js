/**
 * One-off diagnostic probe: load an SE product's MRI portal details page,
 * open the Documents tab, and dump the DOM so we can tell whether docetp/MPA
 * PAR links are genuinely absent or merely rendered as non-anchor Material
 * elements the swe_agency `a[href]` scanner would miss.
 *
 * Usage: node probe_swe_dom_v1.js <procedure_code> [outDir]
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { createSoloIDBrowser, humanDelay, humanClick } from './src/solo_id_v10.js';

const procedure = process.argv[2] || 'SE/H/2048/001';
const outDir = process.argv[3] || '/data/runs/_probe';
fs.mkdirSync(outDir, { recursive: true });
const tag = procedure.replace(/[^A-Za-z0-9]/g, '_');

const log = (m) => console.log(m);

(async () => {
  const { browser, context, page } = await createSoloIDBrowser(chromium, { headless: true });
  try {
    const url = `https://mri.cts-mrp.eu/portal/details?productnumber=${encodeURIComponent(procedure)}`;
    log(`→ goto ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await humanDelay(2000, 4000);
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => log('  (network not idle)'));

    const content = await page.content();
    if (content.includes('Access Denied') || content.includes('403 Forbidden')) {
      log('🚫 BLOCKED (403/Access Denied) — probe inconclusive, IP likely rate-limited');
      await browser.close(); process.exit(3);
    }

    // Open Documents tab (same as downloader)
    const documentsTab = page.locator('text=Documents').first();
    await documentsTab.waitFor({ state: 'visible', timeout: 5000 }).catch(() => log('  (Documents tab not immediately visible)'));
    if (await documentsTab.count() > 0) {
      await humanClick(page, 'text=Documents');
      await humanDelay(2000, 3000);
      log('✓ clicked Documents tab');
    } else {
      log('⚠️  Documents tab not found');
    }

    // 1) All anchors
    const anchors = await page.$$eval('a[href]', els =>
      els.map(a => ({ href: a.href, text: (a.textContent || '').trim().slice(0, 80) })));

    // 2) All mat-icons (names) — reveals archive/open_in_new/launch/pdf icons
    const matIcons = await page.$$eval('mat-icon', els => {
      const c = {};
      els.forEach(e => { const t = (e.textContent || '').trim(); c[t] = (c[t] || 0) + 1; });
      return c;
    }).catch(() => ({}));

    // 3) Any element referencing agency hosts / PAR anywhere (attrs + text)
    const agencyRefs = await page.evaluate(() => {
      const needles = ['docetp', 'mpa.se', 'lakemedelsverket', 'läkemedelsverket'];
      const hits = [];
      const all = document.querySelectorAll('*');
      for (const el of all) {
        const attrs = [...el.attributes].map(a => `${a.name}=${a.value}`).join(' ');
        const txt = (el.textContent || '').slice(0, 120);
        const hay = (attrs + ' ' + txt).toLowerCase();
        if (needles.some(n => hay.includes(n))) {
          hits.push({ tag: el.tagName.toLowerCase(), attrs: attrs.slice(0, 200), text: txt.trim().slice(0, 100) });
        }
        if (hits.length > 40) break;
      }
      return hits;
    });

    // 4) iframes
    const iframes = await page.$$eval('iframe', els => els.map(f => f.src));

    // 5) rows in the documents table (structure)
    const docRows = await page.evaluate(() => {
      const rows = [...document.querySelectorAll('mat-row, tr, .mat-mdc-row')].slice(0, 30);
      return rows.map(r => (r.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 160)).filter(Boolean);
    });

    const report = { procedure, url, counts: {
        anchors: anchors.length,
        agencyAnchors: anchors.filter(a => /docetp|mpa\.se|lakemedelsverket/i.test(a.href)).length,
        matIcons, iframes: iframes.length, agencyRefs: agencyRefs.length,
      },
      agencyAnchors: anchors.filter(a => /docetp|mpa\.se|lakemedelsverket/i.test(a.href)),
      agencyRefs, iframes, docRows,
      allAnchorsSample: anchors.slice(0, 40),
    };

    const jsonPath = path.join(outDir, `probe_${tag}.json`);
    const htmlPath = path.join(outDir, `probe_${tag}.html`);
    fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2));
    fs.writeFileSync(htmlPath, content);

    log('\n===== PROBE SUMMARY =====');
    log(`anchors: ${report.counts.anchors} | agency anchors: ${report.counts.agencyAnchors}`);
    log(`mat-icons: ${JSON.stringify(matIcons)}`);
    log(`agency refs (any element): ${agencyRefs.length}`);
    log(`iframes: ${iframes.length} ${JSON.stringify(iframes).slice(0, 200)}`);
    log(`doc rows: ${JSON.stringify(docRows).slice(0, 400)}`);
    if (agencyRefs.length) log(`AGENCY REFS: ${JSON.stringify(agencyRefs, null, 1).slice(0, 800)}`);
    log(`\nsaved: ${jsonPath}\n       ${htmlPath}`);
  } catch (e) {
    log(`ERROR: ${e.message}`);
  } finally {
    await browser.close();
  }
})();
