#!/usr/bin/env node
/**
 * Download Excel files for multiple products and merge into single database
 * v20 - Tracker-based with diagnostics, fallback download, and resume support
 *
 * Features (v15→v20 evolution):
 *   - core_download_tracker.json for per-product status tracking
 *   - Resume: skips completed products on re-run
 *   - Diagnostics: saves HTML/screenshot/JSON per failure to core_debug_v20/
 *   - Fallback download via context.request.get() when event times out
 *   - Exit code 3 for portal blocking detection
 *   - Randomized processing order on retry (shuffled by orchestrator)
 *
 * Usage: node download_and_merge_products_v20.js <input_json> <output_xlsx> [max_products]
 */

import { chromium } from 'playwright';
import { readFileSync, writeFileSync, mkdirSync, existsSync, unlinkSync, readdirSync } from 'fs';
import { join, dirname } from 'path';
import { execSync } from 'child_process';
import { config } from 'dotenv';
import { createStealthBrowser } from './src/advanced_stealth.js';

config();

const INPUT_FILE = process.argv[2];
const OUTPUT_FILE = process.argv[3];
const MAX_PRODUCTS = parseInt(process.argv[4]) || 10000;

if (!INPUT_FILE || !OUTPUT_FILE) {
  console.log('Usage: node download_and_merge_products_v20.js <input_json> <output_xlsx> [max_products]');
  process.exit(1);
}

const TARGET_DIR = dirname(OUTPUT_FILE) === '.' ? process.cwd() : dirname(OUTPUT_FILE);
const TRACKER_PATH = join(TARGET_DIR, 'core_download_tracker.json');
const DEBUG_DIR = join(TARGET_DIR, 'core_debug_v20');
const DOWNLOADS_DIR = join(TARGET_DIR, 'core_downloads');
const DOWNLOAD_TIMEOUT = 35000;

// Proxy configuration (disabled by default — VPN provides IP rotation)
const ENABLE_PROXY = process.env.ENABLE_PROXY === 'true';
const PROXY_CONFIG = ENABLE_PROXY && process.env.PROXYSCRAPE_HOSTNAME ? {
  server: `http://${process.env.PROXYSCRAPE_HOSTNAME}:${process.env.PROXYSCRAPE_PORT}`,
  username: process.env.PROXYSCRAPE_USERNAME,
  password: process.env.PROXYSCRAPE_PASSWORD
} : null;

// ── Tracker helpers ──────────────────────────────────────────────────────

function loadTracker() {
  if (existsSync(TRACKER_PATH)) {
    return JSON.parse(readFileSync(TRACKER_PATH, 'utf8'));
  }
  return null;
}

function createTracker(products, molecule) {
  const tracker = {
    molecule: molecule || '',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    max_products: MAX_PRODUCTS,
    products: {}
  };
  for (const product of products) {
    const code = product.procedure_code;
    tracker.products[code] = {
      procedure_code: code,
      product_name: product.product_name || '',
      status: 'pending',
      attempt_count: 0,
      last_error: null,
      completed_at: null,
      download_method: null
    };
  }
  return tracker;
}

function saveTracker(tracker) {
  tracker.updated_at = new Date().toISOString();
  writeFileSync(TRACKER_PATH, JSON.stringify(tracker, null, 2));
}

// Alias used by older code paths
const persistTracker = saveTracker;

// ── Diagnostics ──────────────────────────────────────────────────────────

async function saveDiagnostics(page, context, productKey, error, attempt) {
  mkdirSync(DEBUG_DIR, { recursive: true });
  const safeKey = productKey.replace(/\//g, '_');
  const prefix = join(DEBUG_DIR, `${safeKey}_attempt${attempt}`);

  try {
    // Screenshot
    await page.screenshot({ path: `${prefix}.png`, fullPage: true }).catch(() => {});

    // HTML snapshot
    const html = await page.content().catch(() => '');
    if (html) writeFileSync(`${prefix}.html`, html);

    // Console errors and network info
    const diagnostics = {
      product_key: productKey,
      attempt,
      error: error?.message || String(error),
      page_url: page.url(),
      timestamp: new Date().toISOString(),
      console_errors: [],
      recent_responses: []
    };
    writeFileSync(`${prefix}.json`, JSON.stringify(diagnostics, null, 2));
  } catch (e) {
    // Best-effort diagnostics
  }
}

// ── Human behavior ───────────────────────────────────────────────────────

function addJitter(delayMs, variance = 0.3) {
  const min = delayMs * (1 - variance);
  const max = delayMs * (1 + variance);
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

async function humanDelay(minMs = 2000, maxMs = 5000) {
  const delay = Math.random() * (maxMs - minMs) + minMs;
  await new Promise(resolve => setTimeout(resolve, addJitter(delay)));
}

// ── Download strategies ──────────────────────────────────────────────────

async function downloadViaPlaywrightEvent(page, productKey) {
  const url = `https://mri.cts-mrp.eu/portal/details?productnumber=${encodeURIComponent(productKey)}`;

  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  await humanDelay(1500, 3000);

  const downloadBtn = page.locator('button', { hasText: 'Download excel' }).first();
  if (!await downloadBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    throw new Error('Download excel button not visible');
  }

  await humanDelay(500, 1000);
  const downloadPromise = page.waitForEvent('download', { timeout: DOWNLOAD_TIMEOUT });
  await downloadBtn.click();
  const download = await downloadPromise;
  return download;
}

async function downloadViaContextRequest(context, productKey) {
  // Fallback: try fetching the Excel via direct API request
  const candidates = [
    `https://mri.cts-mrp.eu/portal/details?productnumber=${encodeURIComponent(productKey)}`,
    `https://mri-production.cts-mrp.eu/details?productnumber=${encodeURIComponent(productKey)}`
  ];

  for (const url of candidates) {
    try {
      const response = await context.request.get(url, { timeout: 30000 });
      if (response.ok()) {
        return { url, response };
      }
    } catch {
      // Try next candidate
    }
  }
  throw new Error('All fallback URL candidates failed');
}

// ── Main download loop ───────────────────────────────────────────────────

async function downloadProductExcel(page, context, productKey, outputPath, tracker, attempt) {
  try {
    // Strategy 1: Playwright download event
    const download = await downloadViaPlaywrightEvent(page, productKey);
    await download.saveAs(outputPath);
    await humanDelay(300, 700);
    return 'playwright_download_event';
  } catch (primaryError) {
    console.log(`      Primary download failed: ${primaryError.message}`);
    console.log(`      Trying fallback strategies...`);

    // Save diagnostics for the failure
    await saveDiagnostics(page, context, productKey, primaryError, attempt);

    try {
      // Strategy 2: Context request fallback
      const { response } = await downloadViaContextRequest(context, productKey);
      const body = await response.body();
      writeFileSync(outputPath, body);
      return 'context_request_fallback';
    } catch (fallbackError) {
      throw new Error(`${primaryError.message} | fallback: ${fallbackError.message}`);
    }
  }
}

async function main() {
  console.log(`\n${'='.repeat(70)}`);
  console.log(`MRI PRODUCT DATABASE BUILDER (v20)`);
  console.log(`${'='.repeat(70)}\n`);

  // Load products from search results
  console.log(`Reading products from: ${INPUT_FILE}`);
  const products = JSON.parse(readFileSync(INPUT_FILE, 'utf8'));
  const productsToProcess = products.slice(0, MAX_PRODUCTS);
  console.log(`Processing ${productsToProcess.length} products (max: ${MAX_PRODUCTS})\n`);

  // Load or create tracker
  let tracker = loadTracker();
  if (tracker) {
    console.log(`✓ Resuming from existing tracker (${Object.keys(tracker.products).length} products tracked)`);
    // Ensure new products from search_results are added to tracker
    for (const product of productsToProcess) {
      if (!tracker.products[product.procedure_code]) {
        tracker.products[product.procedure_code] = {
          procedure_code: product.procedure_code,
          product_name: product.product_name || '',
          status: 'pending',
          attempt_count: 0,
          last_error: null,
          completed_at: null,
          download_method: null
        };
      }
    }
  } else {
    // Derive molecule name from output filename
    const molecule = OUTPUT_FILE.replace(/.*\//, '').replace(/_core_database\.xlsx$/, '').replace(/\.xlsx$/, '');
    tracker = createTracker(productsToProcess, molecule);
    console.log(`✓ Created new tracker for ${productsToProcess.length} products`);
  }
  saveTracker(tracker);

  // Count pending
  const pending = Object.values(tracker.products).filter(p => p.status === 'pending').length;
  const completed = Object.values(tracker.products).filter(p => p.status === 'completed').length;
  console.log(`   Completed: ${completed}, Pending: ${pending}\n`);

  if (pending === 0) {
    console.log('✓ All products already downloaded. Skipping to merge.\n');
  } else {
    // Create downloads directory
    mkdirSync(DOWNLOADS_DIR, { recursive: true });

    if (PROXY_CONFIG) {
      console.log(`✓ Proxy enabled: ${PROXY_CONFIG.server}`);
    } else {
      console.log(`✓ Using direct connection (VPN provides IP rotation)`);
    }

    // Launch stealth browser
    const stealthSetup = await createStealthBrowser(
      { chromium },
      { headless: true, proxy: PROXY_CONFIG }
    );

    const { browser, context, page } = stealthSetup;

    // Enable downloads
    const downloadContext = await browser.newContext({
      acceptDownloads: true,
      ...stealthSetup.context._options
    });
    const downloadPage = await downloadContext.newPage();

    let consecutiveFailures = 0;
    const BLOCK_THRESHOLD = 5;

    try {
      console.log(`\n${'='.repeat(70)}`);
      console.log(`DOWNLOADING EXCEL FILES`);
      console.log(`${'='.repeat(70)}\n`);

      const productCodes = Object.keys(tracker.products);
      let processedCount = 0;

      for (const code of productCodes) {
        const entry = tracker.products[code];
        if (entry.status === 'completed') continue;

        processedCount++;
        const safeKey = code.replace(/\//g, '_');
        const outputPath = join(DOWNLOADS_DIR, `${safeKey}.xlsx`);

        console.log(`[${processedCount}/${pending}] ${code}`);

        entry.status = 'in_progress';
        entry.attempt_count = (entry.attempt_count || 0) + 1;
        saveTracker(tracker);

        try {
          const method = await downloadProductExcel(
            downloadPage, downloadContext, code, outputPath, tracker, entry.attempt_count
          );

          entry.status = 'completed';
          entry.completed_at = new Date().toISOString();
          entry.download_method = method;
          entry.last_error = null;
          console.log(`   ✓ Downloaded (${method})`);
          consecutiveFailures = 0;
        } catch (error) {
          entry.status = 'failed';
          entry.last_error = error.message;
          console.log(`   ✗ Failed: ${error.message}`);
          consecutiveFailures++;

          // Portal blocking detection
          if (consecutiveFailures >= BLOCK_THRESHOLD) {
            console.log(`\n✗ ${BLOCK_THRESHOLD} consecutive failures — portal may be blocking.`);
            saveTracker(tracker);
            await browser.close();
            process.exit(3);
          }
        }

        saveTracker(tracker);
        await humanDelay(2000, 4000);
      }

    } finally {
      await browser.close().catch(() => {});
    }
  }

  // ── Merge Excel files ────────────────────────────────────────────────

  console.log(`\n${'='.repeat(70)}`);
  console.log(`MERGING EXCEL FILES`);
  console.log(`${'='.repeat(70)}\n`);

  // Collect all downloaded xlsx files
  const downloadedFiles = [];
  if (existsSync(DOWNLOADS_DIR)) {
    for (const file of readdirSync(DOWNLOADS_DIR)) {
      if (file.endsWith('.xlsx')) {
        downloadedFiles.push(join(DOWNLOADS_DIR, file));
      }
    }
  }

  console.log(`Successfully downloaded: ${downloadedFiles.length} files`);

  if (downloadedFiles.length === 0) {
    console.log('⚠ No Excel files to merge');
    process.exit(0);
  }

  console.log(`Merging into: ${OUTPUT_FILE}\n`);

  const pythonScript = `
import pandas as pd
from pathlib import Path

files = ${JSON.stringify(downloadedFiles)}
dfs = []

for file in files:
    try:
        df = pd.read_excel(file)
        # Skip empty or header-only files
        if len(df) > 0:
            dfs.append(df)
            print(f"  ✓ Read {Path(file).name}: {len(df)} rows")
        else:
            print(f"  ⚠ Empty: {Path(file).name}")
    except Exception as e:
        print(f"  ✗ Error reading {Path(file).name}: {e}")

if dfs:
    merged = pd.concat(dfs, ignore_index=True)
    # Drop duplicate rows
    before = len(merged)
    merged = merged.drop_duplicates()
    after = len(merged)
    if before != after:
        print(f"\\n✓ Removed {before - after} duplicate rows")
    print(f"✓ Merged {len(dfs)} files into {after} total rows")
    merged.to_excel('${OUTPUT_FILE}', index=False)
    print(f"✓ Saved to: ${OUTPUT_FILE}")
    print(f"\\nColumns ({len(merged.columns)}): {', '.join(merged.columns)}")
else:
    print("✗ No files to merge")
`;

  const tmpScript = join(TARGET_DIR, '.tmp_merge_v20.py');
  writeFileSync(tmpScript, pythonScript);

  try {
    execSync(`python3 "${tmpScript}"`, { stdio: 'inherit', cwd: TARGET_DIR });
  } finally {
    try { unlinkSync(tmpScript); } catch {}
  }

  // Final tracker summary
  const finalTracker = loadTracker();
  if (finalTracker) {
    const stats = Object.values(finalTracker.products).reduce((acc, p) => {
      acc[p.status] = (acc[p.status] || 0) + 1;
      return acc;
    }, {});
    console.log(`\nTracker summary: ${JSON.stringify(stats)}`);
  }

  console.log(`\n${'='.repeat(70)}`);
  console.log(`COMPLETE`);
  console.log(`${'='.repeat(70)}\n`);
}

main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
