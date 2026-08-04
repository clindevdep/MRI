import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import ExcelJS from 'exceljs';
import {
  PORTAL_EXCEL_COLUMNS,
  productToPortalExcelRow,
  writeValidatedPortalExcel,
} from '../scripts/src/mri_product_export_v22.js';

const product = {
  productKey: 'SE/H/1839/003', name: 'Elvanse', domainKey: 'H', outcome: 'Positive',
  dateOfOutcome: '2026-08-01', updatedAt: '2026-08-02', maHolder: 'Example MAH',
  rms: { countryName: 'Sweden' },
  activeSubstances: [{ innName: 'Lisdexamfetamine', saltName: 'dimesylate', amount: 20, unitDescription: 'mg' }],
  atcCodes: [{ code: 'N06BA12', atcCodeName: 'Lisdexamfetamine' }],
  cms: [{ productName: 'Elvanse', isoCode: 'SE' }], doseForms: [{ doseFormName: 'Capsule' }],
  documents: [{ hasContent: true, apiId: 'doc-1' }, { hasContent: false, url: 'https://agency.example/par.pdf' }],
  withdrawalReasons: [], typeLevelCategory: { typeLevelCategory1: 'Human' },
};

test('mirrors the portal row shape and safely handles absent optional fields', () => {
  const row = productToPortalExcelRow(product, 'https://portal.example');
  assert.deepEqual(Object.keys(row), PORTAL_EXCEL_COLUMNS);
  assert.equal(row.MrNumber, 'SE/H/1839/003');
  assert.equal(row.ActiveSubstances, 'Lisdexamfetamine dimesylate 20 mg');
  assert.match(row.Documents, /Document\(documentApiId='doc-1'\)\/Download/);
  assert.match(row.Documents, /agency\.example/);
  assert.equal(productToPortalExcelRow({ productKey: 'X' }).RMS, '');
});

test('writes a readable xlsx containing the expected portal-style row', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'mri-v22-test-'));
  const output = join(directory, 'product.xlsx');
  try {
    await writeValidatedPortalExcel(product, 'https://portal.example', output);
    const workbook = new ExcelJS.Workbook();
    await workbook.xlsx.readFile(output);
    const sheet = workbook.getWorksheet('table');
    assert.equal(sheet.getCell('A1').value, 'MrNumber');
    assert.equal(sheet.getCell('A2').value, 'SE/H/1839/003');
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
