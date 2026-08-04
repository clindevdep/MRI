/**
 * Build the same one-row workbook as the MRI portal's current
 * "Download as excel file" action.  The portal now produces that workbook in
 * the browser from its ProductSearch OData response, rather than serving an
 * Excel file from a download endpoint.
 */
import ExcelJS from 'exceljs';

export const PORTAL_EXCEL_COLUMNS = [
  'MrNumber', 'Productlink', 'Name', 'Domain', 'Outcome', 'DateOfOutcome',
  'UpdatedAt', 'MAHolder', 'RMS', 'ActiveSubstances', 'AtcCodes', 'CMS',
  'DoseForms', 'Documents', 'WithdrawalReasons', 'TypelevelCategory1',
  'TypelevelCategory2', 'TypelevelCategory3', 'TypelevelCategory4',
  'TypelevelCategory5',
];

function list(value) {
  return Array.isArray(value) ? value : [];
}

function text(value) {
  return value == null ? '' : String(value);
}

/** Convert an expanded ProductSearch OData item to the portal's Excel row. */
export function productToPortalExcelRow(product, apiBaseUrl) {
  const productKey = text(product?.productKey);
  const category = product?.typeLevelCategory || {};
  const baseUrl = String(apiBaseUrl || 'https://mri-production.cts-mrp.eu').replace(/\/$/, '');

  return {
    MrNumber: productKey,
    Productlink: `${baseUrl}/details?productnumber=${productKey}`,
    Name: text(product?.name),
    Domain: text(product?.domainKey),
    Outcome: text(product?.outcome),
    DateOfOutcome: text(product?.dateOfOutcome),
    UpdatedAt: text(product?.updatedAt),
    MAHolder: text(product?.maHolder),
    RMS: text(product?.rms?.countryName),
    ActiveSubstances: list(product?.activeSubstances)
      .map(item => [item?.innName, item?.saltName, item?.amount, item?.unitDescription]
        .filter(value => value != null && value !== '').join(' '))
      .join(','),
    AtcCodes: list(product?.atcCodes)
      .map(item => [item?.code, item?.atcCodeName].filter(Boolean).join(' '))
      .join(','),
    CMS: list(product?.cms)
      .map(item => `${text(item?.productName)} (${text(item?.isoCode)})`)
      .join(','),
    DoseForms: list(product?.doseForms).map(item => text(item?.doseFormName)).join(','),
    Documents: list(product?.documents)
      .map(item => item?.hasContent && item?.apiId
        ? `${baseUrl}/v1/odata/Document(documentApiId='${item.apiId}')/Download`
        : item?.url)
      .filter(Boolean)
      .join(' | '),
    WithdrawalReasons: list(product?.withdrawalReasons)
      .map(item => text(item?.description)).join(','),
    TypelevelCategory1: text(category.typeLevelCategory1),
    TypelevelCategory2: text(category.typeLevelCategory2),
    TypelevelCategory3: text(category.typeLevelCategory3),
    TypelevelCategory4: text(category.typeLevelCategory4),
    TypelevelCategory5: text(category.typeLevelCategory5),
  };
}

/** Write and reopen the workbook so an invalid/captive HTML payload can never be marked complete. */
export async function writeValidatedPortalExcel(product, apiBaseUrl, outputPath) {
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet('table');
  const row = productToPortalExcelRow(product, apiBaseUrl);

  sheet.columns = PORTAL_EXCEL_COLUMNS.map(key => ({
    header: key,
    key,
    width: Math.min(Math.max(key.length + 2, 16), 45),
  }));
  sheet.addRow(row);
  await workbook.xlsx.writeFile(outputPath);

  const validationWorkbook = new ExcelJS.Workbook();
  await validationWorkbook.xlsx.readFile(outputPath);
  const validationSheet = validationWorkbook.getWorksheet('table');
  if (!validationSheet || validationSheet.rowCount < 2 || validationSheet.getCell('A2').value !== row.MrNumber) {
    throw new Error('Generated workbook validation failed');
  }
}
