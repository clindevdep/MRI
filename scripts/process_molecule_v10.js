/**
 * Process Molecule v10 - Solo ID Strategy (PAR Downloads)
 *
 * Downloads PAR documents with unique identity per product.
 * Tracks progress in download_tracker.json for resume support.
 * Saves to: {run_folder}/{molecule}/{ProductName}/xxx.pdf
 *
 * Usage:
 *   node process_molecule_v10.js --core <xlsx> --molecule <name> --max <n>
 *   node process_molecule_v10.js <molecule> [max_products]   (legacy)
 */

import { chromium } from 'playwright';
import { createSoloIDBrowser, humanDelay, humanClick } from './src/solo_id_v10.js';
import fs from 'fs';
import path from 'path';
import ExcelJS from 'exceljs';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ── Argument parsing (supports both --flag and positional) ───────────────

function parseArgs() {
  const args = process.argv.slice(2);
  const parsed = { core: null, molecule: null, max: 10000 };

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--core' && args[i + 1]) {
      parsed.core = args[++i];
    } else if (args[i] === '--molecule' && args[i + 1]) {
      parsed.molecule = args[++i];
    } else if (args[i] === '--max' && args[i + 1]) {
      parsed.max = parseInt(args[++i]) || 10000;
    } else if (!args[i].startsWith('--') && !parsed.molecule) {
      // Legacy positional: first non-flag = molecule
      parsed.molecule = args[i];
    } else if (!args[i].startsWith('--') && parsed.molecule && !parsed._maxSet) {
      // Legacy positional: second non-flag = max_products
      parsed.max = parseInt(args[i]) || 10;
      parsed._maxSet = true;
    }
  }

  return parsed;
}

const ARGS = parseArgs();
const MOLECULE = ARGS.molecule;
const MAX_PRODUCTS = ARGS.max;
const CORE_DB_PATH = ARGS.core;

if (!MOLECULE) {
  console.log('Usage: node process_molecule_v10.js --core <xlsx> --molecule <name> --max <n>');
  console.log('       node process_molecule_v10.js <molecule> [max_products]');
  console.log('Example: node process_molecule_v10.js --core /data/runs/ketoprofen_core_database.xlsx --molecule ketoprofen --max 10000');
  process.exit(1);
}

const RUN_FOLDER = process.cwd();
const MOLECULE_FOLDER = path.join(RUN_FOLDER, MOLECULE);
const TRACKER_PATH = path.join(MOLECULE_FOLDER, 'download_tracker.json');

// ── Tracker helpers ──────────────────────────────────────────────────────

function loadTracker() {
  if (fs.existsSync(TRACKER_PATH)) {
    return JSON.parse(fs.readFileSync(TRACKER_PATH, 'utf8'));
  }
  return null;
}

function createTracker(products) {
  const tracker = {
    molecule: MOLECULE,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    max_products: MAX_PRODUCTS,
    products: {}
  };
  for (const product of products) {
    tracker.products[product.procedure_code] = {
      procedure_code: product.procedure_code,
      product_name: product.product_name,
      folder_name: product.folder_name,
      status: 'pending',
      par_count: 0,
      par_files: [],
      attempt_count: 0,
      last_error: null,
      completed_at: null
    };
  }
  return tracker;
}

function saveTracker(tracker) {
  tracker.updated_at = new Date().toISOString();
  fs.mkdirSync(path.dirname(TRACKER_PATH), { recursive: true });
  fs.writeFileSync(TRACKER_PATH, JSON.stringify(tracker, null, 2));
}

// ── Core database reader ─────────────────────────────────────────────────

async function readCoreDatabase() {
  // Resolve core database path
  let corePath = CORE_DB_PATH;

  if (!corePath || !fs.existsSync(corePath)) {
    // Fallback: search in run folder
    const candidates = [
      path.join(RUN_FOLDER, `${MOLECULE}_core_database.xlsx`),
      path.join(RUN_FOLDER, `${MOLECULE}_database.xlsx`)
    ];
    corePath = candidates.find(p => fs.existsSync(p));
  }

  if (!corePath || !fs.existsSync(corePath)) {
    console.log(`❌ Core database not found.`);
    if (CORE_DB_PATH) console.log(`   Specified: ${CORE_DB_PATH}`);
    console.log(`   Searched: ${RUN_FOLDER}`);
    process.exit(1);
  }

  console.log(`📖 Reading core database: ${corePath}`);

  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.readFile(corePath);
  const worksheet = workbook.worksheets[0];
  const products = [];

  // Read header row to find column indices
  const headers = [];
  worksheet.getRow(1).eachCell((cell, colNumber) => {
    headers[colNumber] = String(cell.value || '').toLowerCase().trim();
  });

  // Flexible column detection
  function findCol(...candidates) {
    for (const candidate of candidates) {
      const idx = headers.findIndex(h => h && h.includes(candidate.toLowerCase()));
      if (idx >= 0) return idx;
    }
    return -1;
  }

  const mrNumberCol = findCol('mrnumber', 'productnumber', 'procedure_code', 'procedure', 'code');
  const nameCol = findCol('name', 'productname', 'product');
  const maHolderCol = findCol('maholder', 'holder', 'applicant');
  const doseFormCol = findCol('doseforms', 'form', 'dosage');

  // Use column 1 and 2 as fallback
  const procCol = mrNumberCol >= 0 ? mrNumberCol : 1;
  const nCol = nameCol >= 0 ? nameCol : 2;

  worksheet.eachRow((row, rowNumber) => {
    if (rowNumber === 1) return;

    const mrNumber = row.getCell(procCol).value;
    const name = row.getCell(nCol).value;
    const maHolder = maHolderCol >= 0 ? row.getCell(maHolderCol).value : '';
    const doseForm = doseFormCol >= 0 ? row.getCell(doseFormCol).value : '';

    if (mrNumber) {
      const productName = createProductFolderName(name, maHolder, doseForm, mrNumber);
      products.push({
        procedure_code: String(mrNumber).trim(),
        product_name: String(name || 'Unknown').trim(),
        folder_name: productName,
        ma_holder: String(maHolder || '').trim(),
        dose_form: String(doseForm || '').trim()
      });
    }
  });

  console.log(`   ✅ Found ${products.length} products in core database`);
  return products;
}

/**
 * Create smart folder name from product metadata
 */
function createProductFolderName(name, maHolder, doseForm, mrNumber) {
  let productName = String(name || 'Unknown').trim();

  let company = String(maHolder || '').trim();
  company = company
    .replace(/\b(GmbH|S\.?A\.?|Ltd\.?|Limited|Inc\.?|Corp\.?|AG|N\.?V\.?|B\.?V\.?)\b/gi, '')
    .replace(/\b(Third Party Sales|Group|Pharma|Pharmaceutical|Pharmaceuticals)\b/gi, '')
    .trim()
    .replace(/\s+/g, '')
    .substring(0, 15);

  let formAbbrev = 'UNK';
  const doseFormStr = String(doseForm || '').toLowerCase();
  if (doseFormStr.includes('film-coated tablet')) formAbbrev = 'FCT';
  else if (doseFormStr.includes('tablet')) formAbbrev = 'TAB';
  else if (doseFormStr.includes('capsule')) formAbbrev = 'CAP';
  else if (doseFormStr.includes('solution')) formAbbrev = 'SOL';
  else if (doseFormStr.includes('suspension')) formAbbrev = 'SUS';

  const mrStr = String(mrNumber || '');
  const parts = mrStr.split('/');
  const rms = parts[0] || 'XX';
  const code = parts[2] || '0000';

  const folderName = `${productName}_${company || 'Company'}_${formAbbrev}_${rms}_${code}`
    .replace(/[^a-zA-Z0-9_]/g, '_')
    .replace(/_+/g, '_')
    .substring(0, 100);

  return folderName;
}

/**
 * Download PAR documents for a single product using unique identity
 */
async function downloadProductPARs(product, productIndex, totalProducts, tracker) {
  const entry = tracker.products[product.procedure_code];
  console.log(`\n[${productIndex}/${totalProducts}] 🎯 Processing: ${product.procedure_code}`);
  console.log(`   Product: ${product.product_name}`);
  console.log(`   Folder: ${product.folder_name}`);

  const productFolder = path.join(MOLECULE_FOLDER, product.folder_name);
  fs.mkdirSync(productFolder, { recursive: true });

  // Mark in-progress
  entry.status = 'in_progress';
  entry.attempt_count = (entry.attempt_count || 0) + 1;
  saveTracker(tracker);

  const { browser, context, page, fingerprint } = await createSoloIDBrowser(
    chromium,
    { headless: true }
  );

  let downloadCount = 0;
  const parFiles = [];

  try {
    const url = `https://mri.cts-mrp.eu/portal/details?productnumber=${encodeURIComponent(product.procedure_code)}`;

    console.log(`   → Navigating via direct URL...`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await humanDelay(2000, 4000);

    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {
      console.log(`   ⚠️  Network not fully idle, continuing anyway`);
    });

    // Check for ban indicators
    const pageContent = await page.content();
    if (pageContent.includes('Access Denied') || pageContent.includes('403 Forbidden')) {
      console.log(`   🚫 Portal blocking detected!`);
      entry.status = 'failed';
      entry.last_error = 'Portal blocking detected (403/Access Denied)';
      saveTracker(tracker);
      await browser.close();
      process.exit(3);
    }

    console.log(`   → Looking for Documents tab...`);
    const documentsTab = page.locator('text=Documents').first();

    await documentsTab.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {
      console.log(`   ⚠️  Documents tab not immediately visible`);
    });

    if (await documentsTab.count() > 0) {
      await humanClick(page, 'text=Documents');
      await humanDelay(2000, 3000);

      console.log(`   → Finding download icons...`);
      const downloadIcons = await page.locator('mat-icon:has-text("archive")').all();
      console.log(`   → Found ${downloadIcons.length} documents`);

      for (let i = 0; i < downloadIcons.length; i++) {
        try {
          const downloadPromise = page.waitForEvent('download', { timeout: 20000 });
          await downloadIcons[i].click();
          const download = await downloadPromise;
          const filename = download.suggestedFilename();

          if (filename.endsWith('.xlsx')) {
            console.log(`      ${i + 1}. Skipped: ${filename} (Excel)`);
            continue;
          }

          if (!filename.toUpperCase().includes('PAR')) {
            console.log(`      ${i + 1}. Skipped: ${filename} (not a PAR)`);
            continue;
          }

          const outputPath = path.join(productFolder, filename);
          await download.saveAs(outputPath);
          console.log(`      ${i + 1}. ✅ ${filename}`);
          downloadCount++;
          parFiles.push(filename);

          await humanDelay(500, 1500);
        } catch (error) {
          console.log(`      ${i + 1}. ⚠️  Failed: ${error.message}`);
        }
      }
    } else {
      console.log(`   ⚠️  Documents tab not found`);
    }

    // Update tracker
    entry.status = 'completed';
    entry.par_count = downloadCount;
    entry.par_files = parFiles;
    entry.completed_at = new Date().toISOString();
    entry.last_error = null;

    if (downloadCount === 0) {
      console.log(`   ⚠️  No PAR documents downloaded`);
    } else {
      console.log(`   ✅ Downloaded ${downloadCount} PAR document(s)`);
    }

    return downloadCount;
  } catch (error) {
    console.log(`   ❌ Error: ${error.message}`);
    entry.status = 'failed';
    entry.last_error = error.message;
    return 0;
  } finally {
    saveTracker(tracker);
    await browser.close();
    console.log(`   🔒 Browser closed (identity destroyed)`);

    const betweenProductDelay = 2000 + Math.random() * 6000;
    console.log(`   ⏱️  Waiting ${Math.round(betweenProductDelay/1000)}s before next product...`);
    await new Promise(resolve => setTimeout(resolve, betweenProductDelay));
  }
}

/**
 * Main execution
 */
async function main() {
  console.log(`\n═══════════════════════════════════════════════════════`);
  console.log(`  Process Molecule v10 - Solo ID Strategy`);
  console.log(`  (PAR Downloads with Unique Identity per Product)`);
  console.log(`═══════════════════════════════════════════════════════`);
  console.log(`  Molecule: ${MOLECULE}`);
  console.log(`  Max products: ${MAX_PRODUCTS}`);
  console.log(`  Core DB: ${CORE_DB_PATH || '(auto-detect)'}`);
  console.log(`  Run folder: ${RUN_FOLDER}`);
  console.log(`  Output: ${MOLECULE_FOLDER}`);
  console.log(`═══════════════════════════════════════════════════════\n`);

  const allProducts = await readCoreDatabase();
  const products = allProducts.slice(0, MAX_PRODUCTS);

  // Load or create tracker
  let tracker = loadTracker();
  if (tracker) {
    console.log(`✓ Resuming from existing tracker`);
    // Ensure all products are in tracker
    for (const product of products) {
      if (!tracker.products[product.procedure_code]) {
        tracker.products[product.procedure_code] = {
          procedure_code: product.procedure_code,
          product_name: product.product_name,
          folder_name: product.folder_name,
          status: 'pending',
          par_count: 0,
          par_files: [],
          attempt_count: 0,
          last_error: null,
          completed_at: null
        };
      }
    }
  } else {
    tracker = createTracker(products);
    console.log(`✓ Created new tracker for ${products.length} products`);
  }
  saveTracker(tracker);

  // Filter to pending/failed only
  const pending = products.filter(p => {
    const entry = tracker.products[p.procedure_code];
    return entry && entry.status !== 'completed';
  });

  const completed = products.length - pending.length;
  console.log(`📥 Downloading PARs: ${pending.length} pending, ${completed} already completed\n`);

  if (pending.length === 0) {
    console.log(`✅ All products already processed.\n`);
    return;
  }

  let totalPARs = 0;
  const productsWithPARs = [];
  let consecutiveFailures = 0;

  for (let i = 0; i < pending.length; i++) {
    const product = pending[i];
    const parCount = await downloadProductPARs(product, i + 1, pending.length, tracker);

    if (parCount > 0) {
      totalPARs += parCount;
      productsWithPARs.push({ ...product, par_count: parCount });
      consecutiveFailures = 0;
    } else {
      const entry = tracker.products[product.procedure_code];
      if (entry.status === 'failed') {
        consecutiveFailures++;
        if (consecutiveFailures >= 5) {
          console.log(`\n🚫 5 consecutive failures — portal may be blocking.`);
          saveTracker(tracker);
          process.exit(3);
        }
      }
    }
  }

  // Final summary
  const allCompleted = Object.values(tracker.products).filter(p => p.status === 'completed').length;
  const allFailed = Object.values(tracker.products).filter(p => p.status === 'failed').length;
  const allPARs = Object.values(tracker.products).reduce((sum, p) => sum + (p.par_count || 0), 0);

  console.log(`\n═══════════════════════════════════════════════════════`);
  console.log(`  Download Complete`);
  console.log(`═══════════════════════════════════════════════════════`);
  console.log(`  Total products: ${Object.keys(tracker.products).length}`);
  console.log(`  Completed: ${allCompleted}`);
  console.log(`  Failed: ${allFailed}`);
  console.log(`  Total PAR documents: ${allPARs}`);
  console.log(`  Tracker: ${TRACKER_PATH}`);
  console.log(`  Output: ${MOLECULE_FOLDER}`);
  console.log(`═══════════════════════════════════════════════════════\n`);
}

main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
