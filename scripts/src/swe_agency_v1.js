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
