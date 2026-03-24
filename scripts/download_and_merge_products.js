#!/usr/bin/env node
/**
 * Download Excel files for multiple products and merge into single database
 * v07 - Advanced stealth mode with comprehensive anti-fingerprinting
 *
 * Usage: node download_and_merge_products.js <input_json> <output_xlsx> [max_products]
 * Example: node download_and_merge_products.js outputs/candesartan/search_results.json outputs/candesartan/candesartan.xlsx 20
 */

import { chromium } from 'playwright';
import { readFileSync, writeFileSync, mkdirSync, existsSync, unlinkSync } from 'fs';
import { join } from 'path';
import { execSync } from 'child_process';
import { config } from 'dotenv';
import { createStealthBrowser } from './src/advanced_stealth.js';

// Load environment variables (Docker provides env vars via compose)
config();

const INPUT_FILE = process.argv[2] || 'outputs/candesartan/search_results.json';
const OUTPUT_FILE = process.argv[3] || 'outputs/candesartan/candesartan.xlsx';
const MAX_PRODUCTS = parseInt(process.argv[4]) || 20;

// Human behavior simulation utilities
function addJitter(delayMs, variance = 0.3) {
  const min = delayMs * (1 - variance);
  const max = delayMs * (1 + variance);
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

async function humanDelay(minMs = 2000, maxMs = 5000) {
  const delay = Math.random() * (maxMs - minMs) + minMs;
  await new Promise(resolve => setTimeout(resolve, addJitter(delay)));
}

// Realistic user agents pool
const USER_AGENTS = [
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
];

const VIEWPORTS = [
  { width: 1920, height: 1080 },
  { width: 1366, height: 768 },
  { width: 1536, height: 864 }
];

function getRandomUserAgent() {
  return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];
}

function getRandomViewport() {
  return VIEWPORTS[Math.floor(Math.random() * VIEWPORTS.length)];
}

// Proxy configuration
const ENABLE_PROXY = process.env.ENABLE_PROXY !== 'false'; // Default: enabled
const PROXY_CONFIG = ENABLE_PROXY && process.env.PROXYSCRAPE_HOSTNAME ? {
  server: `http://${process.env.PROXYSCRAPE_HOSTNAME}:${process.env.PROXYSCRAPE_PORT}`,
  username: process.env.PROXYSCRAPE_USERNAME,
  password: process.env.PROXYSCRAPE_PASSWORD
} : null;

async function downloadProductExcel(page, productKey, outputPath) {
  const url = `https://mri.cts-mrp.eu/portal/details?productnumber=${productKey}`;

  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });

    // Human-like delay after page load
    await humanDelay(1500, 3000);

    // Find and click Download excel button with human-like behavior
    const downloadBtn = page.locator('button', { hasText: 'Download excel' }).first();

    if (await downloadBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      // Small delay before clicking
      await humanDelay(500, 1000);

      const downloadPromise = page.waitForEvent('download', { timeout: 30000 });
      await downloadBtn.click();
      const download = await downloadPromise;
      await download.saveAs(outputPath);

      // Small delay after download
      await humanDelay(300, 700);
      return true;
    }

    return false;

  } catch (error) {
    console.error(`      Error: ${error.message}`);
    return false;
  }
}

async function main() {
  console.log(`\n${'='.repeat(70)}`);
  console.log(`MRI PRODUCT DATABASE BUILDER (v06)`);
  console.log(`${'='.repeat(70)}\n`);

  // Load products from search results
  console.log(`Reading products from: ${INPUT_FILE}`);
  const products = JSON.parse(readFileSync(INPUT_FILE, 'utf8'));
  const productsToProcess = products.slice(0, MAX_PRODUCTS);
  console.log(`Processing ${productsToProcess.length} products (max: ${MAX_PRODUCTS})\n`);

  // Create temp directory for individual Excel files
  const tempDir = join(process.cwd(), 'temp_excel_downloads');
  mkdirSync(tempDir, { recursive: true });

  console.log('🔐 Browser Fingerprinting-Resistant Mode');

  if (PROXY_CONFIG) {
    console.log(`✓ Proxy enabled: ${PROXY_CONFIG.server}`);
  } else {
    console.log(`⚠ Proxy disabled (direct connection)`);
  }

  // Randomize browser fingerprint
  const viewport = getRandomViewport();
  const userAgent = getRandomUserAgent();

  console.log(`🎭 Random fingerprint: ${viewport.width}x${viewport.height}, ${userAgent.split(' ')[0]}...\n`);

  // Launch browser
  const browserOptions = {
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--disable-software-rasterizer',
      '--disable-blink-features=AutomationControlled',
      '--disable-features=IsolateOrigins,site-per-process',
      `--window-size=${viewport.width},${viewport.height}`,
      '--lang=en-US,en',
      '--disable-web-security',
      '--flag-switches-begin --disable-site-isolation-trials --flag-switches-end'
    ]
  };

  // Add proxy configuration if available
  if (PROXY_CONFIG) {
    browserOptions.proxy = PROXY_CONFIG;
  }

  const browser = await chromium.launch(browserOptions);

  // Enhanced context with realistic browser fingerprint
  const context = await browser.newContext({
    acceptDownloads: true,
    viewport,
    userAgent,
    locale: 'en-US',
    timezoneId: 'America/New_York',
    permissions: ['geolocation'],
    geolocation: { latitude: 40.7128, longitude: -74.0060 },
    colorScheme: 'light',
    extraHTTPHeaders: {
      'Accept-Language': 'en-US,en;q=0.9',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
      'Accept-Encoding': 'gzip, deflate, br',
      'Upgrade-Insecure-Requests': '1',
      'Sec-Fetch-Site': 'none',
      'Sec-Fetch-Mode': 'navigate',
      'Sec-Fetch-User': '?1',
      'Sec-Fetch-Dest': 'document',
      'Cache-Control': 'max-age=0'
    }
  });

  const page = await context.newPage();

  // Override navigator properties to hide automation
  await page.addInitScript(() => {
    // Remove webdriver flag
    Object.defineProperty(navigator, 'webdriver', {
      get: () => false
    });

    // Override plugins
    Object.defineProperty(navigator, 'plugins', {
      get: () => [
        { name: 'Chrome PDF Plugin' },
        { name: 'Chrome PDF Viewer' },
        { name: 'Native Client' }
      ]
    });

    // Override languages
    Object.defineProperty(navigator, 'languages', {
      get: () => ['en-US', 'en']
    });

    // Override permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
      parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
    );

    // Mock Chrome runtime
    window.chrome = {
      runtime: {}
    };
  });

  const downloadedFiles = [];

  try {
    console.log(`${'='.repeat(70)}`);
    console.log(`DOWNLOADING EXCEL FILES`);
    console.log(`${'='.repeat(70)}\n`);

    for (let i = 0; i < productsToProcess.length; i++) {
      const product = productsToProcess[i];
      const productKey = product.procedure_code;
      const safeKey = productKey.replace(/\//g, '_');
      const outputPath = join(tempDir, `${safeKey}.xlsx`);

      console.log(`[${i + 1}/${productsToProcess.length}] ${productKey}`);

      const success = await downloadProductExcel(page, productKey, outputPath);

      if (success) {
        console.log(`   ✓ Downloaded`);
        downloadedFiles.push(outputPath);
      } else {
        console.log(`   ✗ Failed`);
      }

      // Human-like delay between requests (rate limiting)
      await humanDelay(2000, 4000);
    }

  } finally {
    await browser.close();
  }

  console.log(`\n${'='.repeat(70)}`);
  console.log(`MERGING EXCEL FILES`);
  console.log(`${'='.repeat(70)}\n`);

  console.log(`Successfully downloaded: ${downloadedFiles.length} files`);
  console.log(`Merging into: ${OUTPUT_FILE}\n`);

  // Use Python to merge Excel files
  const pythonScript = `
import pandas as pd
from pathlib import Path

# Read all Excel files
files = ${JSON.stringify(downloadedFiles)}
dfs = []

for file in files:
    try:
        df = pd.read_excel(file)
        dfs.append(df)
        print(f"  ✓ Read {Path(file).name}: {len(df)} rows")
    except Exception as e:
        print(f"  ✗ Error reading {Path(file).name}: {e}")

# Merge all dataframes
if dfs:
    merged = pd.concat(dfs, ignore_index=True)
    print(f"\\n✓ Merged {len(dfs)} files into {len(merged)} total rows")

    # Save to output file
    merged.to_excel('${OUTPUT_FILE}', index=False)
    print(f"✓ Saved to: ${OUTPUT_FILE}")

    print(f"\\nColumns ({len(merged.columns)}): {', '.join(merged.columns)}")
else:
    print("✗ No files to merge")
`;

  writeFileSync('temp_merge_script.py', pythonScript);
  execSync('uv run python temp_merge_script.py', { stdio: 'inherit' });

  // Cleanup
  console.log(`\n${'='.repeat(70)}`);
  console.log(`CLEANUP`);
  console.log(`${'='.repeat(70)}\n`);

  // Delete temp files
  for (const file of downloadedFiles) {
    try {
      unlinkSync(file);
    } catch (e) {
      // Ignore errors
    }
  }

  try {
    unlinkSync('temp_merge_script.py');
    const fs = await import('fs');
    fs.rmSync(tempDir, { recursive: true, force: true });
    console.log('✓ Cleaned up temporary files\n');
  } catch (e) {
    console.log('⚠ Some temp files remain in:', tempDir);
  }

  console.log(`${'='.repeat(70)}`);
  console.log(`COMPLETE`);
  console.log(`${'='.repeat(70)}\n`);
  console.log(`Database saved to: ${OUTPUT_FILE}`);
  console.log(`\nNext steps:`);
  console.log(`  1. Review: vd ${OUTPUT_FILE}`);
  console.log(`  2. Check columns match expected format`);
  console.log(`  3. Use for downstream analysis\n`);
}

main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
