#!/usr/bin/env node
/**
 * Enhanced MRI Portal Search - v14 Ultra-Aggressive Lazy Loading
 * Fixes persistent 74/105 issue with multiple scrolling strategies
 *
 * Usage: node search_molecule_stealth_v14.js <molecule_name> [max_results]
 */

import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'fs';
import { join } from 'path';
import { config } from 'dotenv';
import { createStealthBrowser } from './advanced_stealth.js';

// Load environment variables (Docker provides env vars via compose)
config();

const MOLECULE = process.argv[2] || 'apixaban';
const MAX_RESULTS = parseInt(process.argv[3]) || 30;

// Proxy configuration (optional - uses VPN by default)
const ENABLE_PROXY = process.env.ENABLE_PROXY === 'true';
const PROXY_CONFIG = ENABLE_PROXY && process.env.PROXYSCRAPE_HOSTNAME ? {
  server: `http://${process.env.PROXYSCRAPE_HOSTNAME}:${process.env.PROXYSCRAPE_PORT}`,
  username: process.env.PROXYSCRAPE_USERNAME,
  password: process.env.PROXYSCRAPE_PASSWORD
} : null;

/**
 * Human-like delay with jitter
 */
function addJitter(delayMs, variance = 0.3) {
  const min = delayMs * (1 - variance);
  const max = delayMs * (1 + variance);
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

async function humanDelay(minMs = 2000, maxMs = 5000) {
  const delay = Math.random() * (maxMs - minMs) + minMs;
  await new Promise(resolve => setTimeout(resolve, addJitter(delay)));
}

/**
 * Human-like mouse movement to element
 */
async function humanMouseMove(page, element) {
  try {
    const box = await element.boundingBox();
    if (!box) return;

    const startX = Math.random() * 100;
    const startY = Math.random() * 100;
    const targetX = box.x + Math.random() * box.width;
    const targetY = box.y + Math.random() * box.height;
    const steps = Math.floor(Math.random() * 20) + 10;

    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const eased = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
      const x = startX + (targetX - startX) * eased;
      const y = startY + (targetY - startY) * eased;
      await page.mouse.move(x, y);
      await new Promise(resolve => setTimeout(resolve, addJitter(10, 0.5)));
    }

    await humanDelay(100, 300);
  } catch (err) {
    // Element not interactable, skip
  }
}

/**
 * Human-like click with realistic behavior
 */
async function humanClick(page, selector, options = {}) {
  const timeout = options.timeout || 30000;
  let element;

  if (options.nth !== undefined) {
    element = page.locator(selector).nth(options.nth);
  } else {
    element = page.locator(selector).first();
  }

  await element.waitFor({ state: 'visible', timeout });
  await humanMouseMove(page, element);
  await humanDelay(200, 500);
  const clickDelay = Math.random() > 0.9 ? 50 : 0;
  await element.click({ delay: clickDelay });
  await humanDelay(300, 700);
}

/**
 * Human-like typing with variable speed
 */
async function humanType(page, selector, text) {
  const element = await page.locator(selector).first();
  await element.waitFor({ state: 'visible', timeout: 10000 });

  await humanMouseMove(page, element);
  await element.click();
  await humanDelay(200, 400);

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (Math.random() < 0.05) {
      await new Promise(resolve => setTimeout(resolve, addJitter(500, 0.5)));
    }
    const baseDelay = Math.random() * 200 + 100;
    await page.keyboard.type(char);
    await new Promise(resolve => setTimeout(resolve, addJitter(baseDelay, 0.3)));
  }

  await humanDelay(300, 600);
}

/**
 * Random scrolling to simulate reading
 */
async function humanScroll(page) {
  const scrolls = Math.floor(Math.random() * 3) + 1;

  for (let i = 0; i < scrolls; i++) {
    const scrollY = Math.random() * 500 + 200;
    const direction = Math.random() > 0.2 ? 1 : -1;

    await page.evaluate((y) => {
      window.scrollBy({ top: y, behavior: 'smooth' });
    }, scrollY * direction);

    await humanDelay(500, 1500);
  }
}

/**
 * Session warmup
 */
async function sessionWarmup(page, baseUrl) {
  console.log('🔥 Warming up session (human behavior simulation)...');

  await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 60000 });
  await humanDelay(2000, 4000);
  await humanScroll(page);
  await humanDelay(1000, 2000);

  const viewport = page.viewportSize();
  for (let i = 0; i < 5; i++) {
    const x = Math.random() * viewport.width;
    const y = Math.random() * viewport.height;
    const steps = Math.floor(Math.random() * 10) + 5;
    await page.mouse.move(x, y, { steps });
    await humanDelay(300, 800);
  }

  console.log('✅ Session warmed up');
}

/**
 * ULTRA-AGGRESSIVE lazy loading strategy
 */
async function ultraAggressiveLoad(page, totalResults, MAX_RESULTS) {
  const maxWaitTime = 300000; // 5 minutes
  const pollInterval = 300; // Check every 300ms (faster!)
  const scrollInterval = 100; // Scroll every 100ms (very aggressive!)
  const stabilityCheckCount = 30; // Rows must be stable for 30 checks = 9 seconds
  const targetRows = Math.min(MAX_RESULTS, totalResults, 1000);

  const startTime = Date.now();
  let currentRowCount = 0;
  let previousRowCount = 0;
  let stableCount = 0;
  let lastScrollTime = 0;
  let scrollAttempts = 0;

  console.log('   🚀 ULTRA-AGGRESSIVE LOADING MODE');
  console.log(`   Target: ${targetRows} rows`);
  console.log(`   Stability threshold: ${stabilityCheckCount} checks (~${(stabilityCheckCount * pollInterval / 1000).toFixed(1)}s)`);

  while (Date.now() - startTime < maxWaitTime) {
    // Count visible rows
    const currentRows = await page.locator('tr, mat-row, .product-row').all();
    currentRowCount = 0;

    for (const row of currentRows) {
      const text = await row.textContent().catch(() => '');
      if (/[A-Z]{2}\/H\/\d{4,5}\/\d{3}/.test(text)) {
        currentRowCount++;
      }
    }

    console.log(`   ℹ Loaded ${currentRowCount}/${targetRows} rows (scrolls: ${scrollAttempts})...`);

    // Success!
    if (currentRowCount >= targetRows) {
      console.log(`   ✅ SUCCESS! All ${currentRowCount} results loaded`);
      return true;
    }

    // Stability checking
    if (currentRowCount === previousRowCount && currentRowCount > 10) {
      stableCount++;
      console.log(`   ⏸ Row count stable (${stableCount}/${stabilityCheckCount})...`);

      if (stableCount >= stabilityCheckCount) {
        console.log(`   ⚠ WARNING: Row count stable at ${currentRowCount}/${targetRows}`);
        console.log(`   ⚠ Portal may have only loaded ${currentRowCount} rows`);
        console.log(`   ⚠ This could be a portal limitation or incomplete lazy loading`);
        return false;
      }
    } else {
      stableCount = 0; // Reset if count changed
    }
    previousRowCount = currentRowCount;

    // ULTRA-AGGRESSIVE SCROLLING
    const now = Date.now();
    if (now - lastScrollTime >= scrollInterval) {
      scrollAttempts++;

      // Strategy 1: Find and scroll ALL possible containers
      await page.evaluate(() => {
        const selectors = [
          '.mat-table-container',
          '.cdk-virtual-scroll-viewport',
          '.mat-paginator-container',
          '.mat-table',
          '[role="table"]',
          '.table-container',
          '.results-container',
          '.mat-drawer-content',
          '.mat-sidenav-content',
          'mat-table',
          'table',
          '.datatable',
          '.data-table'
        ];

        let scrolled = false;
        for (const selector of selectors) {
          const containers = document.querySelectorAll(selector);
          containers.forEach(container => {
            container.scrollTop = container.scrollHeight;
            scrolled = true;
          });
        }

        // Also scroll window
        window.scrollTo(0, document.body.scrollHeight);
        return scrolled;
      }).catch(() => {});

      // Strategy 2: Scroll last row into view
      const lastRow = page.locator('tr, mat-row, .product-row').last();
      if (await lastRow.count() > 0) {
        await lastRow.scrollIntoViewIfNeeded().catch(() => {});
      }

      // Strategy 3: Scroll multiple rows into view
      const rowCount = await page.locator('tr, mat-row, .product-row').count();
      if (rowCount > 5) {
        for (let i = rowCount - 5; i < rowCount; i++) {
          const row = page.locator('tr, mat-row, .product-row').nth(i);
          await row.scrollIntoViewIfNeeded().catch(() => {});
        }
      }

      // Strategy 4: Page Down key press every 10 scrolls
      if (scrollAttempts % 10 === 0) {
        await page.keyboard.press('PageDown').catch(() => {});
        console.log(`   📄 Pressed PageDown (attempt ${scrollAttempts})`);
      }

      // Strategy 5: End key press every 20 scrolls
      if (scrollAttempts % 20 === 0) {
        await page.keyboard.press('End').catch(() => {});
        console.log(`   🔚 Pressed End (attempt ${scrollAttempts})`);
      }

      lastScrollTime = now;
    }

    await page.waitForTimeout(pollInterval);
  }

  console.log(`   ❌ TIMEOUT after ${maxWaitTime/1000}s - loaded ${currentRowCount}/${targetRows} rows`);
  return false;
}

/**
 * Main search function
 */
async function searchMolecule(page, moleculeName) {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`🔍 Searching for: ${moleculeName}`);
  console.log(`📊 Max results: ${MAX_RESULTS}`);
  console.log(`${'='.repeat(60)}\n`);

  try {
    await sessionWarmup(page, 'https://mri.cts-mrp.eu/portal/');

    console.log('1. Opening Product search...');
    await page.screenshot({ path: 'debug_0_homepage.png' });

    const pageTitle = await page.title().catch(() => 'Unknown');
    console.log(`   Page title: ${pageTitle}`);

    const productSearchBtn = page.locator('text=Product search').first();
    const btnCount = await productSearchBtn.count();
    console.log(`   "Product search" buttons found: ${btnCount}`);

    if (btnCount === 0) {
      console.log('   ⚠️  Product search button not found');
      const bodyText = await page.locator('body').textContent().catch(() => '');
      console.log(`   Page contains: ${bodyText.substring(0, 200)}...`);
    }

    await humanClick(page, 'text=Product search', { timeout: 30000 });

    console.log('2. Opening Advanced search...');
    await humanDelay(1500, 2500);
    await humanClick(page, 'text=Advanced search');
    await page.screenshot({ path: 'debug_1_advanced_search.png' });

    console.log('3. Setting up INN filter...');
    await humanDelay(1000, 2000);

    const innsElement = page.getByText('INNs', { exact: true }).first();
    const dropArea = page.getByText('Drop area').first();

    await innsElement.waitFor({ state: 'visible', timeout: 10000 });
    await dropArea.waitFor({ state: 'visible', timeout: 10000 });

    await humanMouseMove(page, innsElement);
    await humanDelay(200, 400);

    const innsBox = await innsElement.boundingBox();
    const dropBox = await dropArea.boundingBox();

    if (innsBox && dropBox) {
      await page.mouse.move(innsBox.x + innsBox.width / 2, innsBox.y + innsBox.height / 2);
      await humanDelay(150, 300);
      await page.mouse.down();
      await humanDelay(100, 200);

      const steps = Math.floor(Math.random() * 20) + 15;
      await page.mouse.move(
        dropBox.x + dropBox.width / 2,
        dropBox.y + dropBox.height / 2,
        { steps }
      );

      await humanDelay(100, 200);
      await page.mouse.up();
      console.log('   ✓ Dragged INNs to drop area');
    }

    await humanDelay(2000, 3000);
    await page.screenshot({ path: 'debug_2_after_drag.png' });

    console.log('4. Entering molecule name...');
    await humanDelay(1000, 1500);

    const innsInput = page.locator('input[data-placeholder="INNs"], input[placeholder="INNs"]').first();
    await humanType(page, 'input[data-placeholder="INNs"], input[placeholder="INNs"]', moleculeName);

    await page.screenshot({ path: 'debug_3_typed_molecule.png' });

    console.log('5. Handling autocomplete...');
    await humanDelay(800, 1500);

    const autocompleteOptions = page.locator('mat-option');
    try {
      await autocompleteOptions.first().waitFor({ state: 'visible', timeout: 5000 });
    } catch (e) {
      console.log('   (No autocomplete options appeared)');
    }

    const optionsCount = await autocompleteOptions.count();
    console.log(`   Found ${optionsCount} autocomplete options`);

    let exactMatchIndex = -1;

    if (optionsCount > 0) {
      for (let i = 0; i < optionsCount; i++) {
        const text = await autocompleteOptions.nth(i).textContent();
        const cleanText = (text || '').trim();
        console.log(`   [${i}] "${cleanText}"`);

        if (cleanText.toLowerCase() === moleculeName.toLowerCase()) {
          exactMatchIndex = i;
          console.log(`   ✓ Found exact match at index ${i}`);
        }
      }
    }

    if (exactMatchIndex !== -1) {
      console.log(`   Selecting option ${exactMatchIndex}: "${moleculeName}"`);
      await humanClick(page, 'mat-option', { nth: exactMatchIndex });
    } else {
      console.log('   No exact match found in autocomplete. Pressing Enter...');
      await innsInput.press('Enter');
    }

    await humanDelay(1000, 2000);
    await page.screenshot({ path: 'debug_4_molecule_selected.png' });

    console.log('6. Executing query...');
    await humanDelay(1500, 2500);

    const executeBtn = page.locator('button:has-text("Execut")').first();
    await humanClick(page, 'button:has-text("Execut")');

    console.log('   ⏳ Waiting for results...');
    await humanDelay(3000, 5000);

    await page.screenshot({ path: 'debug_5_results_loading.png' });

    console.log('7. Reading results count...');
    await humanDelay(2000, 3000);

    let totalResults = 0;
    const pageText = await page.locator('body').textContent();
    const totalMatch = pageText.match(/Total\s+results?\s*:?\s*(\d+)/i);

    if (totalMatch) {
      totalResults = parseInt(totalMatch[1]);
      console.log(`   ✓ Found ${totalResults} total results`);
    }

    console.log('8. Setting pagination to 1000...');
    await humanDelay(2000, 3000);

    await page.waitForTimeout(2000);

    const button1000 = page.locator('button:has-text("1000"), a:has-text("1000"), div:has-text("1000")').filter({ hasText: /^1000$/ });
    const count = await button1000.count();

    console.log(`   Found ${count} elements with text "1000"`);

    let paginationSet = false;
    if (count > 0) {
      for (let i = 0; i < count; i++) {
        try {
          const elem = button1000.nth(i);
          const isVisible = await elem.isVisible().catch(() => false);

          if (isVisible) {
            console.log(`   Clicking pagination button "1000"...`);
            await humanDelay(300, 700);
            await elem.click();
            await humanDelay(2000, 3000);

            await page.locator('.loading, .spinner, mat-spinner, mat-progress-spinner').first()
              .waitFor({ state: 'hidden', timeout: 10000 })
              .catch(() => {});

            // USE ULTRA-AGGRESSIVE LOADING
            paginationSet = await ultraAggressiveLoad(page, totalResults, MAX_RESULTS);
            break;
          }
        } catch (error) {
          console.log(`   ⚠ Error clicking button ${i}: ${error.message}`);
        }
      }
    }

    if (!paginationSet) {
      console.log('   ⚠ Pagination not set or loading incomplete');
    }

    await page.screenshot({ path: 'debug_6_full_results.png', fullPage: true });

    console.log('9. Extracting product data...');
    await humanDelay(2000, 3000);

    const products = [];
    const rows = await page.locator('tr, mat-row, .product-row').all();

    console.log(`   Found ${rows.length} rows to process`);

    for (const row of rows) {
      try {
        const text = await row.textContent();
        const codeMatch = text.match(/([A-Z]{2}\/H\/\d{4,5}\/\d{3})/);

        if (codeMatch) {
          const procedureCode = codeMatch[1];

          let productName = 'Unknown';
          const nameMatch = text.match(/([A-Za-z]+(?:\s+[A-Za-z]+){0,3})\s+\d+\s*(?:mg|g)/);
          if (nameMatch) {
            productName = nameMatch[1].trim();
          }

          products.push({
            procedure_code: procedureCode,
            product_name: productName,
            full_text: text.substring(0, 200).replace(/\s+/g, ' ')
          });

          console.log(`   [${products.length}] ${productName} - ${procedureCode}`);

          if (products.length >= MAX_RESULTS) break;
        }
      } catch (error) {
        // Skip problematic rows
      }
    }

    return { products, totalResults };

  } catch (error) {
    console.error(`❌ Error during search: ${error.message}`);
    await page.screenshot({ path: 'debug_error.png', fullPage: true });
    throw error;
  }
}

/**
 * Main execution
 */
async function main() {
  console.log('🛡️  Advanced Stealth Mode - MRI Portal Scraper v14');
  console.log('━'.repeat(60));
  console.log('🔒 VPN Status: Connected via Surfshark');
  console.log(`📍 Exit IP: 217.138.216.70`);

  if (PROXY_CONFIG) {
    console.log(`🌐 Additional Proxy: ${PROXY_CONFIG.server}`);
  } else {
    console.log(`🌐 Using VPN connection (no additional proxy)`);
  }

  console.log('━'.repeat(60));
  console.log();

  let browser, context, page;

  try {
    const stealthSetup = await createStealthBrowser(
      { chromium },
      {
        headless: true,
        proxy: PROXY_CONFIG,
        launchOptions: {}
      }
    );

    browser = stealthSetup.browser;
    context = stealthSetup.context;
    page = stealthSetup.page;

    console.log('✅ Stealth browser initialized\n');

    const { products, totalResults } = await searchMolecule(page, MOLECULE);

    console.log(`\n${'='.repeat(60)}`);
    console.log('📋 SEARCH RESULTS');
    console.log(`${'='.repeat(60)}`);
    console.log(`Found: ${products.length} products (Total: ${totalResults})`);
    console.log(`Molecule: ${MOLECULE}\n`);

    if (products.length < totalResults) {
      console.log(`⚠️  WARNING: Only ${products.length}/${totalResults} products extracted`);
      console.log(`   This indicates incomplete lazy loading`);
      console.log(`   Check debug_6_full_results.png to verify\n`);
    }

    if (products.length > 0) {
      const moleculeLower = MOLECULE.toLowerCase();
      const firstProductText = products[0].full_text.toLowerCase();

      if (firstProductText.includes(moleculeLower)) {
        console.log(`✅ Validation passed: Results contain "${MOLECULE}"\n`);
      } else {
        console.log(`⚠️  Warning: Results may not match "${MOLECULE}"`);
        console.log(`   First result: ${products[0].product_name}\n`);
      }

      const outputDir = join(process.cwd(), 'outputs', MOLECULE.toLowerCase());
      mkdirSync(outputDir, { recursive: true });

      const outputFile = join(outputDir, 'search_results.json');
      writeFileSync(outputFile, JSON.stringify(products, null, 2));
      console.log(`💾 Saved: ${outputFile}`);

      const listFile = join(outputDir, 'product_list.txt');
      const list = products.map((p, i) =>
        `${i + 1}. ${p.product_name} - ${p.procedure_code}`
      ).join('\n');
      writeFileSync(listFile, list);
      console.log(`💾 Saved: ${listFile}\n`);

    } else {
      console.log('⚠️  No products found');
      console.log('📸 Check debug screenshots\n');
    }

  } catch (error) {
    console.error('💥 Fatal error:', error);
    process.exit(1);

  } finally {
    if (browser) {
      console.log('🔒 Closing browser...');
      await browser.close();
    }
  }
}

main();
