/**
 * Process Molecule v10 - Solo ID Strategy (PAR Downloads)
 *
 * Downloads PAR documents with unique identity per product
 * Saves to: {run_folder}/{molecule}/{ProductName}/xxx.pdf
 *
 * Usage: node process_molecule_v10.js <molecule> [max_products]
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

const MOLECULE = process.argv[2];
const MAX_PRODUCTS = parseInt(process.argv[3]) || 10;

if (!MOLECULE) {
  console.log('Usage: node process_molecule_v10.js <molecule> [max_products]');
  console.log('Example: node process_molecule_v10.js tadalafil 30');
  console.log('\nNote: Requires core database from search_molecule_v10.js');
  process.exit(1);
}

// Use current working directory (where script was run from)
const RUN_FOLDER = process.cwd();
const MOLECULE_FOLDER = path.join(RUN_FOLDER, MOLECULE);

// Also check repository outputs folder for core database
const REPO_OUTPUTS = path.join(__dirname, 'outputs', MOLECULE.toLowerCase());

/**
 * Read product list from core database Excel
 */
async function readCoreDatabase() {
  // Try run folder first, then repository outputs
  let corePath = path.join(REPO_OUTPUTS, `${MOLECULE}_core_database.xlsx`);

  if (!fs.existsSync(corePath)) {
    corePath = path.join(RUN_FOLDER, `${MOLECULE}_core_database.xlsx`);
  }

  if (!fs.existsSync(corePath)) {
    console.log(`❌ Core database not found in:`);
    console.log(`   ${REPO_OUTPUTS}`);
    console.log(`   ${RUN_FOLDER}`);
    console.log(`\nRun search first: node search_molecule_v10.js ${MOLECULE}`);
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
    headers[colNumber] = cell.value;
  });

  // Find key columns
  const mrNumberCol = headers.indexOf('MrNumber') || headers.indexOf('Procedure') || 1;
  const nameCol = headers.indexOf('Name') || headers.indexOf('ProductName') || 2;
  const maHolderCol = headers.indexOf('MAHolder') || headers.indexOf('Holder');
  const doseFormCol = headers.indexOf('DoseForms') || headers.indexOf('Form');

  // Read data rows
  worksheet.eachRow((row, rowNumber) => {
    if (rowNumber === 1) return; // Skip header

    const mrNumber = row.getCell(mrNumberCol).value;
    const name = row.getCell(nameCol).value;
    const maHolder = maHolderCol ? row.getCell(maHolderCol).value : '';
    const doseForm = doseFormCol ? row.getCell(doseFormCol).value : '';

    if (mrNumber) {
      // Create smart product name (similar to previous version)
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
  // Extract product name
  let productName = String(name || 'Unknown').trim();

  // Extract company name from MAHolder (remove legal suffixes)
  let company = String(maHolder || '').trim();
  company = company
    .replace(/\b(GmbH|S\.?A\.?|Ltd\.?|Limited|Inc\.?|Corp\.?|AG|N\.?V\.?|B\.?V\.?)\b/gi, '')
    .replace(/\b(Third Party Sales|Group|Pharma|Pharmaceutical|Pharmaceuticals)\b/gi, '')
    .trim()
    .replace(/\s+/g, '')
    .substring(0, 15);

  // Extract form abbreviation
  let formAbbrev = 'UNK';
  const doseFormStr = String(doseForm || '').toLowerCase();
  if (doseFormStr.includes('film-coated tablet')) formAbbrev = 'FCT';
  else if (doseFormStr.includes('tablet')) formAbbrev = 'TAB';
  else if (doseFormStr.includes('capsule')) formAbbrev = 'CAP';
  else if (doseFormStr.includes('solution')) formAbbrev = 'SOL';
  else if (doseFormStr.includes('suspension')) formAbbrev = 'SUS';

  // Extract RMS country and code from MrNumber (e.g., "NL/H/1208/003" -> "NL", "1208")
  const mrStr = String(mrNumber || '');
  const parts = mrStr.split('/');
  const rms = parts[0] || 'XX';
  const code = parts[2] || '0000';

  // Construct folder name: ProductName_Company_Form_RMS_Code
  const folderName = `${productName}_${company || 'Company'}_${formAbbrev}_${rms}_${code}`
    .replace(/[^a-zA-Z0-9_]/g, '_')
    .replace(/_+/g, '_')
    .substring(0, 100);

  return folderName;
}

/**
 * Download PAR documents for a single product using unique identity
 */
async function downloadProductPARs(product, productIndex, totalProducts) {
  console.log(`\n[${productIndex}/${totalProducts}] 🎯 Processing: ${product.procedure_code}`);
  console.log(`   Product: ${product.product_name}`);
  console.log(`   Folder: ${product.folder_name}`);

  // Create product folder in run directory
  const productFolder = path.join(MOLECULE_FOLDER, product.folder_name);
  fs.mkdirSync(productFolder, { recursive: true });

  // Create completely new browser with unique identity for THIS product only
  const { browser, context, page, fingerprint } = await createSoloIDBrowser(
    chromium,
    { headless: true }
  );

  let downloadCount = 0;

  try {
    // Construct DIRECT URL from procedure code
    const url = `https://mri.cts-mrp.eu/portal/details?productnumber=${encodeURIComponent(product.procedure_code)}`;

    console.log(`   → Navigating via direct URL...`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await humanDelay(2000, 4000);

    // Wait for page to be fully interactive
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {
      console.log(`   ⚠️  Network not fully idle, continuing anyway`);
    });

    // Look for Documents tab
    console.log(`   → Looking for Documents tab...`);
    const documentsTab = page.locator('text=Documents').first();

    // Wait for tab to appear (up to 5 seconds)
    await documentsTab.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {
      console.log(`   ⚠️  Documents tab not immediately visible`);
    });

    if (await documentsTab.count() > 0) {
      await humanClick(page, 'text=Documents');
      await humanDelay(2000, 3000);

      // Find all download icons (mat-icon with "archive")
      console.log(`   → Finding download icons...`);
      const downloadIcons = await page.locator('mat-icon:has-text("archive")').all();

      console.log(`   → Found ${downloadIcons.length} documents`);

      // Download each document
      for (let i = 0; i < downloadIcons.length; i++) {
        try {
          const downloadPromise = page.waitForEvent('download', { timeout: 20000 });
          await downloadIcons[i].click();
          const download = await downloadPromise;
          const filename = download.suggestedFilename();

          // Skip Excel files
          if (filename.endsWith('.xlsx')) {
            console.log(`      ${i + 1}. Skipped: ${filename} (Excel)`);
            continue;
          }

          // Filter for PAR files only
          if (!filename.toUpperCase().includes('PAR')) {
            console.log(`      ${i + 1}. Skipped: ${filename} (not a PAR)`);
            continue;
          }

          // Save to product folder
          const outputPath = path.join(productFolder, filename);
          await download.saveAs(outputPath);
          console.log(`      ${i + 1}. ✅ ${filename}`);
          downloadCount++;

          // Small delay between downloads
          await humanDelay(500, 1500);
        } catch (error) {
          console.log(`      ${i + 1}. ⚠️  Failed: ${error.message}`);
        }
      }
    } else {
      console.log(`   ⚠️  Documents tab not found`);
    }

    if (downloadCount === 0) {
      console.log(`   ⚠️  No PAR documents downloaded`);
    } else {
      console.log(`   ✅ Downloaded ${downloadCount} PAR document(s)`);
    }

    return downloadCount;
  } catch (error) {
    console.log(`   ❌ Error: ${error.message}`);
    return 0;
  } finally {
    // CRITICAL: Close browser to release resources and ensure next product gets new identity
    await browser.close();
    console.log(`   🔒 Browser closed (identity destroyed)`);

    // Random delay between products (2-8 seconds)
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
  console.log(`  Run folder: ${RUN_FOLDER}`);
  console.log(`  Output: ${MOLECULE_FOLDER}`);
  console.log(`═══════════════════════════════════════════════════════\n`);

  // Read products from core database
  const allProducts = await readCoreDatabase();
  const products = allProducts.slice(0, MAX_PRODUCTS);

  console.log(`📥 Downloading PARs for ${products.length} products\n`);

  // Download PARs for each product with unique identity
  let totalPARs = 0;
  const productsWithPARs = [];

  for (let i = 0; i < products.length; i++) {
    const product = products[i];
    const parCount = await downloadProductPARs(
      product,
      i + 1,
      products.length
    );

    totalPARs += parCount;
    if (parCount > 0) {
      productsWithPARs.push({ ...product, par_count: parCount });
    }
  }

  console.log(`\n═══════════════════════════════════════════════════════`);
  console.log(`  Download Complete`);
  console.log(`═══════════════════════════════════════════════════════`);
  console.log(`  Total products processed: ${products.length}`);
  console.log(`  Products with PARs: ${productsWithPARs.length}`);
  console.log(`  Total PAR documents: ${totalPARs}`);
  console.log(`  Output location: ${MOLECULE_FOLDER}`);
  console.log(`═══════════════════════════════════════════════════════\n`);

  // Print summary
  if (productsWithPARs.length > 0) {
    console.log(`📋 Products with PARs:\n`);
    productsWithPARs.forEach(p => {
      console.log(`   ${p.folder_name.padEnd(50)} ${p.par_count} PAR(s)`);
    });
    console.log();
  }

  console.log(`✅ All PAR documents saved to: ${MOLECULE_FOLDER}\n`);
}

main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
