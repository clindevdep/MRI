#!/usr/bin/env python3
"""
Extract bioequivalence data from PAR (Public Assessment Report) PDFs.

Expected columns in output:
- Product name: Same as folder name (e.g., Exerdya_FCT_PharmaSwiss_PL0662)
- Strength: Strength of product in study (e.g., 5mg, 20mg)
- Form: Pharmaceutical form (e.g., Film-coated tablet)
- Food: Fasting or fed state
- PK parameter: Cmax or AUC (or AUCt, AUCinf)
- N: Number of subjects evaluated
- Ratio: Point estimate (geometric mean ratio)
- CI: 90% confidence interval
- CV: Intra-subject variability (%)
- Source: Name of source PDF file
"""

import sys
from pathlib import Path
from typing import List, Dict, Any
import re

import pdfplumber
import pandas as pd


def merge_continuation_tables(tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge tables that are split across pages.

    A continuation table is identified by:
    - First row starts with "*Ratio" or "CV"
    - No header row with PK parameters
    - Appears immediately after an incomplete table
    """
    merged_tables = []
    i = 0

    while i < len(tables):
        current_table = tables[i]
        current_data = current_table['data']

        # Check if next table is a continuation
        if i + 1 < len(tables):
            next_table = tables[i + 1]
            next_data = next_table['data']

            # Check if current table is incomplete (no ratio row)
            current_has_ratio = any(
                'ratio' in ' '.join([str(cell or '') for cell in row]).lower()
                for row in current_data
            )

            # Check if next table starts with ratio/CV (continuation)
            next_is_continuation = False
            if next_data and len(next_data) > 0:
                first_row_str = ' '.join([str(cell or '') for cell in next_data[0]]).lower()
                next_is_continuation = (
                    ('ratio' in first_row_str or first_row_str.strip().startswith('cv'))
                    and not current_has_ratio
                )

            if next_is_continuation:
                # Merge tables - ensure continuation rows have same column count
                max_cols = max(len(row) for row in current_data)

                # Pad continuation table rows to match main table column count
                padded_next_data = []
                for row in next_data:
                    if len(row) < max_cols:
                        padded_row = row + [None] * (max_cols - len(row))
                    else:
                        padded_row = row
                    padded_next_data.append(padded_row)

                merged_data = current_data + padded_next_data
                merged_table = {
                    'page': current_table['page'],
                    'table_num': current_table['table_num'],
                    'data': merged_data,
                    'text': current_table['text'] + '\n' + next_table['text'],
                    'full_page_text': current_table.get('full_page_text', ''),
                }
                merged_tables.append(merged_table)
                i += 2  # Skip both tables
                continue

        merged_tables.append(current_table)
        i += 1

    return merged_tables


def extract_tables_from_pdf(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Extract all tables from a PDF file with surrounding context.
    Merges tables that are split across pages.

    Args:
        pdf_path: Path to PDF file

    Returns:
        List of table dictionaries with metadata
    """
    tables = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_tables = page.extract_tables()
            page_text = page.extract_text() or ''
            page_lines = page_text.split('\n')

            for table_num, table in enumerate(page_tables):
                if not table or len(table) < 2:
                    continue

                # Extract context: look for text before this table
                # Use table position to find nearest caption
                context_text = page_text  # Default to full page

                # Try to identify unique table by finding text that appears in first row
                first_row_text = ' '.join([str(c or '') for c in table[0]]).lower()

                # Search for table caption before this specific table
                # Look for "Table" followed by number and text containing strength/condition info
                for line_idx, line in enumerate(page_lines):
                    line_lower = line.lower()
                    # Check if this line might be a caption for this table
                    if ('table' in line_lower or 'pharmacokinetic' in line_lower):
                        # Look ahead to see if we find this table's content
                        lookahead = '\n'.join(page_lines[line_idx:line_idx+15]).lower()

                        # Check if first row content appears soon after this caption
                        if any(cell and str(cell).lower() in lookahead
                               for cell in table[0][:3] if cell):
                            # Found the right caption
                            start_idx = max(0, line_idx - 5)
                            end_idx = min(len(page_lines), line_idx + 25)
                            context_text = '\n'.join(page_lines[start_idx:end_idx])
                            break

                tables.append({
                    'page': page_num,
                    'table_num': table_num,
                    'data': table,
                    'text': context_text,  # Context around this specific table
                    'full_page_text': page_text  # Keep full page text too
                })

    # Merge continuation tables
    tables = merge_continuation_tables(tables)

    return tables


def is_bioequivalence_table(table_data: List[List[str]], page_text: str) -> bool:
    """
    Determine if a table contains bioequivalence data.

    Look for keywords like: Cmax, AUC, ratio, confidence interval, CV, geometric mean
    """
    # Flatten table to string
    table_str = ' '.join([' '.join([str(cell or '') for cell in row]) for row in table_data])
    table_str = table_str.lower()

    # Check for bioequivalence indicators
    be_keywords = [
        'cmax', 'auc', 'ratio', 'confidence interval', 'ci', 'cv',
        'geometric mean', 'gm ratio', 'point estimate', 'intra-subject'
    ]

    keyword_count = sum(1 for kw in be_keywords if kw in table_str)

    return keyword_count >= 3


def extract_bioequivalence_data(
    table_data: List[List[str]],
    product_name: str,
    source_file: str,
    page_text: str = ''
) -> List[Dict[str, Any]]:
    """
    Extract bioequivalence parameters from a table.

    Returns list of dictionaries, one per PK parameter.
    """
    results = []

    if not table_data or len(table_data) < 3:
        return results

    # Find header row (contains AUC, Cmax, etc.)
    # Priority order:
    # 1. Row with "pharmacokinetic parameter" or "geometric mean ratio" (PAR format header)
    # 2. Row with "auc" or "cmax" (could be either header or data)
    header_row = None

    # First pass: look for clear header indicators
    for idx, row in enumerate(table_data):
        row_str = ' '.join([str(cell or '') for cell in row]).lower()
        # PAR format headers have these phrases
        if 'pharmacokinetic' in row_str or 'geometric mean ratio' in row_str or 'pk parameter' in row_str:
            header_row = idx
            break

    # Second pass: if no clear header found, look for AUC/Cmax
    if header_row is None:
        for idx, row in enumerate(table_data):
            row_str = ' '.join([str(cell or '') for cell in row]).lower()
            if 'auc' in row_str or 'cmax' in row_str or 'c\nmax' in row_str:
                header_row = idx
                break

    if header_row is None:
        return results

    # Check if this is PAR format FIRST (before parsing header columns)
    header_str = ' '.join([str(cell or '') for cell in table_data[header_row]]).lower()
    is_par_format_early = ('ratio' in header_str and 'confidence' in header_str)

    # Check if this is Format 5 (Point Estimate + Lower/Upper CL columns)
    is_format5 = ('lower' in header_str and 'upper' in header_str and ('cl' in header_str or 'confidence' in header_str))

    # Detect Lower and Upper CL column indices for Format 5
    lower_cl_col = None
    upper_cl_col = None
    point_estimate_col = None
    if is_format5:
        for col_idx, cell in enumerate(table_data[header_row]):
            if not cell:
                continue
            cell_lower = str(cell).lower()
            if 'lower' in cell_lower and ('cl' in cell_lower or '90' in cell_lower):
                lower_cl_col = col_idx
            elif 'upper' in cell_lower and ('cl' in cell_lower or '90' in cell_lower):
                upper_cl_col = col_idx
            elif 'point estimate' in cell_lower or ('ratio' in cell_lower and 't/r' in cell_lower):
                point_estimate_col = col_idx

    # Parse header to identify column positions
    # Note: Headers may be in column N but data in column N-1 or N+1
    # We'll search nearby columns for data
    # SKIP this for PAR format (PK params are in rows, not columns)
    headers = table_data[header_row]
    pk_params = {}

    if not is_par_format_early:
        # Original format: PK parameters are in header columns
        for col_idx, cell in enumerate(headers):
            if not cell:
                continue

            cell_str = str(cell).replace('\n', '').replace(' ', '').replace('\r', '').lower()

            if 'auc0-t' in cell_str or 'auc0t' in cell_str or ('auc' in cell_str and '0-t' in cell_str):
                pk_params[col_idx] = 'AUC0-t'
            elif 'auc0-inf' in cell_str or 'auc0-∞' in cell_str:
                pk_params[col_idx] = 'AUC0-inf'
            elif 'auc' in cell_str:
                pk_params[col_idx] = 'AUC'
            elif 'cmax' in cell_str or ('c' in cell_str and 'max' in cell_str):
                pk_params[col_idx] = 'Cmax'

        if not pk_params:
            return results

    # Extract N (number of subjects)
    n_subjects = ''
    for row in table_data[header_row:header_row+3]:
        for cell in row:
            cell_str = str(cell or '').strip()
            n_match = re.search(r'N\s*=\s*(\d+)', cell_str, re.IGNORECASE)
            if n_match:
                n_subjects = n_match.group(1)
                break

    # Find ratio row (contains "ratio" and CI values)
    # Two formats supported:
    # 1. Original: row with "ratio" AND "90%" together (e.g., "Ratio (90% CI)")
    # 2. PAR format: header has "ratio" and "confidence", data rows have only numbers
    ratio_row_idx = None
    cv_row_idx = None

    # Check if header indicates PAR format (separate columns for ratio and CI)
    header_str = ' '.join([str(cell or '') for cell in table_data[header_row]]).lower()
    is_par_format = ('ratio' in header_str and 'confidence' in header_str)

    for idx in range(header_row + 1, len(table_data)):
        row_str = ' '.join([str(cell or '') for cell in table_data[idx]]).lower()

        # Match ratio row
        if ratio_row_idx is None:
            # Original format: must have "ratio" AND "90%"
            if 'ratio' in row_str and '90%' in row_str:
                ratio_row_idx = idx
            # PAR format: if header is PAR format, first data row IS the ratio row
            elif is_par_format and idx == header_row + 1:
                # Check if row contains numeric data (not another header)
                has_numeric = any(re.search(r'\d+\.?\d*', str(cell or '')) for cell in table_data[idx])
                if has_numeric:
                    ratio_row_idx = idx

        # Match CV row: must start with "CV" or contain "CV (%)"
        if cv_row_idx is None and ('cv (%)' in row_str or row_str.strip().startswith('cv')):
            cv_row_idx = idx

    if ratio_row_idx is None:
        return results

    # For PAR format, we may have multiple data rows (one per PK parameter)
    # For original format, we have one ratio row with multiple columns
    data_rows = []

    if is_par_format:
        # PAR format: each row after header is a data row (AUC0-t, AUC0-inf, Cmax)
        # Stop when we hit an empty row or a row with non-numeric content
        for idx in range(header_row + 1, len(table_data)):
            row = table_data[idx]
            row_str = ' '.join([str(cell or '') for cell in row]).lower()

            # Stop if row looks like a footer or note (contains asterisk, "calculated", etc.)
            if '*' in row_str or 'calculated' in row_str or 'mean' in row_str:
                break

            # Check if row has numeric data
            has_numeric = any(re.search(r'\d+\.?\d*', str(cell or '')) for cell in row)
            if has_numeric:
                data_rows.append(idx)
            else:
                break  # Empty or text-only row
    else:
        # Original format: one ratio row
        data_rows = [ratio_row_idx]

    cv_row = table_data[cv_row_idx] if cv_row_idx else []

    # Extract food state and strength from page text
    food_state = ''
    strength = ''

    if page_text:
        page_text_lower = page_text.lower()

        # Extract food state - look for the LAST mention (closest to table)
        # This handles cases where multiple studies are on same page
        fasting_pos = max(
            page_text_lower.rfind('fasting'),
            page_text_lower.rfind('fasted condition')
        )
        fed_pos = max(
            page_text_lower.rfind('fed state'),
            page_text_lower.rfind('fed condition')
        )

        # Use the food state that appears later in the text (closer to table)
        if fasting_pos > fed_pos and fasting_pos >= 0:
            food_state = 'Fasting'
        elif fed_pos > fasting_pos and fed_pos >= 0:
            food_state = 'Fed'
        elif fasting_pos >= 0:
            food_state = 'Fasting'
        elif fed_pos >= 0:
            food_state = 'Fed'

        # Extract strength using multiple patterns (generic for any molecule)
        strength_patterns = [
            r'(\d+\.?\d*)\s*mg\s*film[- ]?coated\s*tablet',
            r'(\d+\.?\d*)\s*mg\s*tablet',
            r'with\s+the\s+(\d+\.?\d*)\s*mg',
            r'of\s+(\d+\.?\d*)\s*mg',
            r'(\d+\.?\d*)\s*mg\s*strength',
            r'(\d+\.?\d*)\s*mg\s*dose',
        ]

        for pattern in strength_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                strength_val = match.group(1).strip()
                # Add 'mg' if not already present
                if not strength_val.endswith('mg'):
                    strength_val = strength_val + ' mg'
                strength = strength_val
                break

    # Extract data for each PK parameter
    # Two different approaches based on table format:

    if is_par_format:
        # PAR format: rows represent PK parameters, columns represent metrics
        # Expected structure:
        # Header: | PK parameter | Ratio | CI | CV |
        # Row 1:  | AUC(0-t)    | 99.5% | 90-110% | 35.5 |
        # Row 2:  | AUC(0-inf)  | 99.3% | 90-109% | 35.3 |
        # Row 3:  | Cmax        | 101%  | 91-112% | 37.0 |

        for row_idx in data_rows:
            row = table_data[row_idx]

            # Extract PK parameter from first column
            pk_param = ''
            first_cell = str(row[0] or '').strip() if row else ''
            # Normalize: remove newlines and spaces for matching
            first_cell_normalized = first_cell.lower().replace('\n', '').replace(' ', '').replace('\r', '')

            if 'auc0-t' in first_cell_normalized or 'auc(0-t)' in first_cell_normalized:
                pk_param = 'AUC0-t'
            elif 'auc0-inf' in first_cell_normalized or 'auc(0-inf)' in first_cell_normalized or 'auc0-∞' in first_cell_normalized or 'auc(0-∞)' in first_cell_normalized:
                pk_param = 'AUC0-inf'
            elif 'auc0-tau' in first_cell_normalized or 'auc(0-tau)' in first_cell_normalized:
                pk_param = 'AUC0-tau'
            elif 'cmax,ss' in first_cell_normalized or 'cmaxss' in first_cell_normalized:
                pk_param = 'Cmax,ss'
            elif 'cmin,ss' in first_cell_normalized or 'cminss' in first_cell_normalized:
                pk_param = 'Cmin,ss'
            elif 'cmax' in first_cell_normalized:
                pk_param = 'Cmax'
            elif 'auc' in first_cell_normalized:
                pk_param = 'AUC'

            if not pk_param:
                continue

            # Extract ratio, CI, and CV from subsequent columns
            ratio_val = ''
            ci_val = ''
            cv_val = ''

            # Format 5: Use Lower/Upper CL columns if detected
            if is_format5 and lower_cl_col is not None and upper_cl_col is not None:
                if point_estimate_col is not None and point_estimate_col < len(row):
                    ratio_cell = row[point_estimate_col]
                    if ratio_cell:
                        ratio_match = re.search(r'(\d+\.?\d*)%?', str(ratio_cell).strip())
                        if ratio_match:
                            ratio_val = ratio_match.group(1)

                if lower_cl_col < len(row) and upper_cl_col < len(row):
                    lower = str(row[lower_cl_col] or '').strip()
                    upper = str(row[upper_cl_col] or '').strip()
                    if lower and upper:
                        # Extract numeric values
                        lower_match = re.search(r'(\d+\.?\d*)', lower)
                        upper_match = re.search(r'(\d+\.?\d*)', upper)
                        if lower_match and upper_match:
                            ci_val = f"{lower_match.group(1)} - {upper_match.group(1)}"
            else:
                # Standard PAR format or other row-based formats
                # Search for ratio in columns (usually column 1 or 2)
                for col_idx in range(1, min(len(row), 5)):
                    cell = row[col_idx]
                    if not cell:
                        continue

                    cell_str = str(cell).strip()
                    # Strip parentheses if present (Format 4: apixaban style "(93.50%, 103.50%)")
                    cell_str_clean = cell_str.strip('()')

                    # Skip if this looks like the CI column (has dash/range)
                    if '-' in cell_str_clean or '–' in cell_str_clean:
                        # This is CI column
                        ci_match = re.search(r'(\d+\.?\d*)%?\s*[-–]\s*(\d+\.?\d*)%?', cell_str_clean)
                        if ci_match:
                            ci_val = f"{ci_match.group(1)} - {ci_match.group(2)}"
                        continue

                    # Check if this is ratio (single number, possibly with %)
                    if not ratio_val:
                        ratio_match = re.search(r'^(\d+\.?\d*)%?$', cell_str)
                        if ratio_match:
                            ratio_val = ratio_match.group(1)
                            continue

                    # Check if this is CV (usually last column, single number)
                    if not cv_val:
                        cv_match = re.search(r'^(\d+\.?\d*)$', cell_str)
                        if cv_match and col_idx >= 2:  # CV usually in column 3 or later
                            cv_val = cv_match.group(1)

            # Add result if we have meaningful data
            if ratio_val or ci_val:
                result = {
                    'Product name': product_name,
                    'Strength': strength,
                    'Form': 'Film-coated tablet',
                    'Food': food_state,
                    'PK parameter': pk_param,
                    'N': n_subjects,
                    'Ratio': ratio_val,
                    'CI': ci_val,
                    'CV': cv_val,
                    'Source': source_file
                }
                results.append(result)

    else:
        # Original format: columns represent PK parameters, one ratio row
        # First, collect all ratio values in the row (for split tables where columns don't align)
        ratio_row = table_data[ratio_row_idx]
        ratio_values = []
        for col_idx in range(len(ratio_row)):
            cell = ratio_row[col_idx]
            if cell and str(cell).strip() and str(cell).strip() not in ['--', '*Ratio\n(90% CI)', '*Ratio (90% CI)']:
                cell_str = str(cell).replace('\n', ' ').replace('\r', ' ')
                # Match ratio with CI in formats: "98 (91-106)" or "98.38 (93.50%,103.50%)"
                if re.search(r'\d+\.?\d*\s*\(\s*\d+\.?\d*%?\s*[,-]\s*\d+\.?\d*%?\s*\)', cell_str):
                    cv_val = ''
                    if cv_row and col_idx < len(cv_row) and cv_row[col_idx]:
                        cv_str = str(cv_row[col_idx]).strip()
                        cv_match = re.search(r'(\d+\.?\d*)', cv_str)
                        if cv_match:
                            cv_val = cv_match.group(1)
                    ratio_values.append({
                        'col': col_idx,
                        'ratio_cell': cell,
                        'cv': cv_val
                    })

        # Match ratio values to PK parameters
        # Track which ratio values have been used to avoid duplicates
        used_ratio_cols = set()
        pk_params_sorted = sorted(pk_params.items())  # Sort by column index

        for idx, (pk_col, pk_param) in enumerate(pk_params_sorted):
            ratio_cell = None
            cv_cell = None
            matched_col = None

            # Try direct column matching first
            for offset in [0, -1, -2, -3, 1, 2, 3]:
                check_idx = pk_col + offset
                if check_idx in used_ratio_cols:  # Skip already used columns
                    continue
                if 0 <= check_idx < len(ratio_row):
                    cell = ratio_row[check_idx]
                    if cell and str(cell).strip() and str(cell).strip() != '--':
                        cell_str = str(cell).replace('\n', ' ').replace('\r', ' ')
                        # Match ratio with CI in formats: "98 (91-106)" or "98.38 (93.50%,103.50%)"
                        if re.search(r'\d+\.?\d*\s*\(\s*\d+\.?\d*%?\s*[,-]\s*\d+\.?\d*%?\s*\)', cell_str):
                            ratio_cell = cell
                            matched_col = check_idx
                            if cv_row and check_idx < len(cv_row):
                                cv_cell = cv_row[check_idx]
                            break

            # If not found by column, use sequential matching
            if not ratio_cell and idx < len(ratio_values):
                # Find first unused ratio value
                for rv in ratio_values:
                    if rv['col'] not in used_ratio_cols:
                        ratio_cell = rv['ratio_cell']
                        matched_col = rv['col']
                        cv_val_from_list = rv['cv']
                        break

            if not ratio_cell or matched_col is None:
                continue

            # Mark this column as used
            used_ratio_cols.add(matched_col)

            ratio_str = str(ratio_cell).strip()

            # Extract ratio and CI
            # Original format only: "0.99\n(0.91 - 1.06)" or "0.99 (0.91 - 1.06)"
            ratio_val = ''
            ci_val = ''

            # Try to extract ratio (numeric value before parenthesis)
            ratio_match = re.search(r'(\d+\.?\d*)', ratio_str)
            if ratio_match:
                ratio_val = ratio_match.group(1)

            # Try to extract CI (values in parentheses)
            # Format can be: (91-106) or (93.50%,103.50%) or (93.50%, 103.50%)
            ci_match = re.search(r'\((\d+\.?\d*)%?\s*[,-]\s*(\d+\.?\d*)%?\)', ratio_str)
            if ci_match:
                ci_val = f"{ci_match.group(1)} - {ci_match.group(2)}"

            # Extract CV
            cv_val = ''
            if cv_cell:
                cv_str = str(cv_cell).strip()
                cv_match = re.search(r'(\d+\.?\d*)', cv_str)
                if cv_match:
                    cv_val = cv_match.group(1)
            elif 'cv_val_from_list' in locals():
                cv_val = cv_val_from_list

            # Only add if we have meaningful data
            if ratio_val or ci_val:
                result = {
                    'Product name': product_name,
                    'Strength': strength,
                    'Form': 'Film-coated tablet',
                    'Food': food_state,
                    'PK parameter': pk_param,
                    'N': n_subjects,
                    'Ratio': ratio_val,
                    'CI': ci_val,
                    'CV': cv_val,
                    'Source': source_file
                }
                results.append(result)

    return results


def process_par_document(pdf_path: Path, product_name: str) -> List[Dict[str, Any]]:
    """
    Process a single PAR document and extract bioequivalence data.
    """
    print(f"Processing: {pdf_path.name}")

    all_results = []
    tables = extract_tables_from_pdf(pdf_path)

    print(f"  Found {len(tables)} tables")

    for table_info in tables:
        if is_bioequivalence_table(table_info['data'], table_info['text']):
            print(f"  → Bioequivalence table found on page {table_info['page']}")

            results = extract_bioequivalence_data(
                table_info['data'],
                product_name,
                pdf_path.name,
                table_info['text']
            )

            all_results.extend(results)

    print(f"  Extracted {len(all_results)} bioequivalence records")
    return all_results


def main():
    """Extract bioequivalence data from all PAR documents."""
    # Get molecule name or path from command line argument
    if len(sys.argv) < 2:
        print("Usage: python extract_bioequivalence.py <molecule_name_or_path>")
        print("Examples:")
        print("  python extract_bioequivalence.py tadalafil")
        print("  python extract_bioequivalence.py /path/to/molecule_folder")
        sys.exit(1)

    arg = sys.argv[1]

    # Check if argument is a path or molecule name
    if '/' in arg or Path(arg).exists():
        # Treat as path
        molecule_dir = Path(arg).resolve()
        if not molecule_dir.exists():
            print(f"Error: Directory not found: {molecule_dir}")
            sys.exit(1)
    else:
        # Treat as molecule name (legacy behavior)
        molecule_name = arg
        project_root = Path(__file__).parent.parent
        molecule_dir = project_root / 'outputs' / molecule_name

        if not molecule_dir.exists():
            print(f"Error: Directory not found: {molecule_dir}")
            print(f"Usage: python {Path(__file__).name} <molecule_name_or_path>")
            print(f"Example: python {Path(__file__).name} candesartan")
            sys.exit(1)

    all_be_data = []

    # Process each product folder
    for product_dir in sorted(molecule_dir.iterdir()):
        if not product_dir.is_dir():
            continue

        product_name = product_dir.name
        print(f"\n{'=' * 60}")
        print(f"Product: {product_name}")
        print('=' * 60)

        # Process all PDF files in product folder
        pdf_files = list(product_dir.glob('*.pdf'))

        if not pdf_files:
            print("  No PDF files found")
            continue

        for pdf_file in pdf_files:
            results = process_par_document(pdf_file, product_name)
            all_be_data.extend(results)

    # Create output DataFrame
    if all_be_data:
        df = pd.DataFrame(all_be_data)

        # Reorder columns
        column_order = [
            'Product name', 'Strength', 'Form', 'Food', 'PK parameter',
            'N', 'Ratio', 'CI', 'CV', 'Source'
        ]
        df = df[column_order]

        # Save to CSV in same directory as molecule folder
        output_file = molecule_dir.parent / f"{molecule_dir.name}_bioequivalence.csv"
        df.to_csv(output_file, index=False)

        print(f"\n{'=' * 60}")
        print(f"SUMMARY")
        print('=' * 60)
        print(f"Total bioequivalence records extracted: {len(df)}")
        print(f"Output saved to: {output_file}")
        print(f"\nPreview:")
        print(df.to_string(index=False))
    else:
        print("\nNo bioequivalence data found in any documents.")


if __name__ == '__main__':
    main()
