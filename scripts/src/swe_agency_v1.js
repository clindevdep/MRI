/**
 * SWE agency PAR downloader (v1)
 *
 * Procedures whose Reference Member State is Sweden (procedure code prefixed
 * "SE/") publish their Public Assessment Reports on the Swedish agency web
 * (Läkemedelsverket / MPA — docetp.mpa.se), not as attachments on the MRI
 * portal. The MRI portal product page instead links out to those documents.
 *
 * This module follows those outbound links from the already-open MRI portal
 * page and downloads the linked PAR PDFs, reusing the caller's stealth browser
 * context (which routes through the Gluetun EU VPN exit — required because
 * docetp.mpa.se rejects non-EU / bot traffic).
 */

import fs from 'fs';
import path from 'path';

// Agency document hosts we recognise as PAR sources for SE-RMS procedures.
const AGENCY_HOSTS = ['docetp.mpa.se', 'lakemedelsverket.se'];

/** Reference Member State = the country-code prefix of the procedure code. */
export function getRMS(procedureCode) {
  return String(procedureCode || '').split('/')[0].trim().toUpperCase();
}

export function isSwedishRMS(procedureCode) {
  return getRMS(procedureCode) === 'SE';
}

function looksLikePAR(text, href) {
  const hay = `${text || ''} ${href || ''}`.toLowerCase();
  return hay.includes('par') || hay.includes('assessment report') || hay.includes('utredningsrapport');
}

function isAgencyHref(href) {
  if (!href) return false;
  const h = href.toLowerCase();
  return AGENCY_HOSTS.some(host => h.includes(host)) || h.endsWith('.pdf');
}

/**
 * Collect candidate PAR links on the current page that point to a SWE agency.
 * Returns an array of unique { url, text } objects, English PARs first.
 */
export async function extractAgencyParLinks(page) {
  const anchors = await page.$$eval('a[href]', els =>
    els.map(a => ({ url: a.href, text: (a.textContent || '').trim() }))
  ).catch(() => []);

  const seen = new Set();
  const candidates = [];
  for (const a of anchors) {
    if (!isAgencyHref(a.url)) continue;
    // Require a PAR hint unless it is an obvious agency-hosted PDF.
    const agencyHosted = AGENCY_HOSTS.some(host => a.url.toLowerCase().includes(host));
    if (!agencyHosted && !looksLikePAR(a.text, a.url)) continue;
    if (seen.has(a.url)) continue;
    seen.add(a.url);
    candidates.push(a);
  }

  // Prefer English-language PARs (…ENG…PAR…) over local-language ones.
  candidates.sort((x, y) => {
    const eng = s => /\beng\b|english/i.test(`${s.text} ${s.url}`) ? 0 : 1;
    return eng(x) - eng(y);
  });
  return candidates;
}

/**
 * Extract agency "landing page" links that the MRI portal renders as
 * Angular-Material external-link buttons (mat-icon "open_in_new"): the target
 * URL is NOT an <a href> — it lives in the button's tooltip
 * (aria-describedby -> a `cdk-describedby-message` / role="tooltip" element whose
 * text is e.g. "External link: https://www.lakemedelsverket.se/…"). The
 * `a[href]` scanner in extractAgencyParLinks() cannot see these, which is why
 * SE products previously yielded 0 candidate links. Returns unique agency URLs.
 */
export async function extractAgencyLandingLinks(page) {
  const urls = await page.evaluate(() => {
    const out = [];
    document
      .querySelectorAll('[id^="cdk-describedby-message"], [role="tooltip"]')
      .forEach(el => {
        const m = (el.textContent || '').match(/https?:\/\/[^\s"'<>]+/);
        if (m) out.push(m[0]);
      });
    return out;
  }).catch(() => []);

  const seen = new Set();
  const result = [];
  for (const u of urls) {
    const lo = u.toLowerCase();
    if (!AGENCY_HOSTS.some(host => lo.includes(host))) continue;
    if (lo.endsWith('.pdf')) continue; // direct PDFs are handled elsewhere
    if (seen.has(u)) continue;
    seen.add(u);
    result.push(u);
  }
  return result;
}

/** Best-effort dismissal of a Swedish cookie gate that can overlay content. */
async function acceptCookies(pg) {
  for (const label of ['Godkänn alla', 'Godkänn', 'Acceptera alla', 'Acceptera', 'Tillåt alla', 'Accept all']) {
    const b = pg.locator(`text=${label}`).first();
    if (await b.count().catch(() => 0)) {
      await b.click().catch(() => {});
      await pg.waitForTimeout(800);
      return;
    }
  }
}

/**
 * Collect SWE-RMS PAR/sPAR PDF links for the currently-open MRI portal product
 * page. Handles both shapes:
 *   (a) direct agency anchors on the portal page (rare), and
 *   (b) the common 2-hop: portal Material tooltip -> lakemedelsverket
 *       "sok-lakemedelsfakta" facts page -> docetp.mpa.se PAR/sPAR PDF anchors.
 * Only assessment reports (PAR/sPAR) are kept — package leaflets, SmPC and sRMP
 * are excluded. Returns a deduped, English-first array of { url, text }.
 */
export async function collectSwedishAgencyPARs(context, page) {
  const seen = new Set();
  const collected = [];
  const add = a => { if (a && a.url && !seen.has(a.url)) { seen.add(a.url); collected.push(a); } };

  // (a) direct agency anchors already on the portal page
  for (const a of await extractAgencyParLinks(page)) add(a);

  // (b) follow Material-tooltip landing pages and scan those for docetp PDFs
  const landings = await extractAgencyLandingLinks(page);
  for (const landing of landings) {
    let lp;
    try {
      lp = await context.newPage();
      await lp.goto(landing, { waitUntil: 'domcontentloaded', timeout: 40000 });
      await lp.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {});
      await acceptCookies(lp);
      for (const a of await extractAgencyParLinks(lp)) add(a);
    } catch (err) {
      console.log(`      ⚠️  Agency landing page failed (${landing}): ${err.message}`);
    } finally {
      if (lp) await lp.close().catch(() => {});
    }
  }

  // Keep only assessment reports (PAR / sPAR); drop PL / SmPC / sRMP.
  const pars = collected.filter(a => looksLikePAR(a.text, a.url));

  // Prefer English-language documents first.
  pars.sort((x, y) => {
    const eng = s => /\beng\b|english/i.test(`${s.text} ${s.url}`) ? 0 : 1;
    return eng(x) - eng(y);
  });
  return pars;
}

function safeFilename(url, index) {
  try {
    const base = decodeURIComponent(url.split('/').pop().split('?')[0]) || `agency_PAR_${index}.pdf`;
    let name = base.replace(/[^a-zA-Z0-9._ -]/g, '_').trim();
    if (!name.toLowerCase().endsWith('.pdf')) name += '.pdf';
    return name.substring(0, 150);
  } catch {
    return `agency_PAR_${index}.pdf`;
  }
}

/**
 * Download the given agency PAR links into productFolder using the stealth
 * context's request (so cookies / VPN exit / fingerprint are preserved).
 * Only bodies that are real PDFs (start with "%PDF") are saved.
 * Returns { count, files }.
 */
export async function downloadAgencyPARs(context, links, productFolder) {
  fs.mkdirSync(productFolder, { recursive: true });
  const files = [];

  for (let i = 0; i < links.length; i++) {
    const { url } = links[i];
    try {
      const response = await context.request.get(url, { timeout: 30000 });
      if (!response.ok()) {
        console.log(`      ⚠️  Agency link HTTP ${response.status()}: ${url}`);
        continue;
      }
      const body = await response.body();
      if (body.length < 5 || body.slice(0, 5).toString('latin1') !== '%PDF-') {
        console.log(`      ⚠️  Not a PDF (skipped): ${url}`);
        continue;
      }
      const filename = safeFilename(url, i + 1);
      const outPath = path.join(productFolder, filename);
      fs.writeFileSync(outPath, body);
      console.log(`      ✅ [SWE] ${filename} (${(body.length / 1024).toFixed(0)} KB)`);
      files.push(filename);
    } catch (err) {
      console.log(`      ⚠️  Agency download failed: ${err.message}`);
    }
  }

  return { count: files.length, files };
}
