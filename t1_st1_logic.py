import sys
import os
import csv
import warnings
import re
from pathlib import Path
import taxopy
from rapidfuzz import fuzz
import pandas as pd
import datetime

import common_utils

CURRENT_PROJECT_PATH = None
_taxdb_cache = None
CURRENT_PROJECT_NAME = "Untitled Project"


def set_project_name(name):
    global CURRENT_PROJECT_NAME
    CURRENT_PROJECT_NAME = name


def get_project_name():
    return CURRENT_PROJECT_NAME


def set_project_path(selected_path):
    global CURRENT_PROJECT_PATH
    CURRENT_PROJECT_PATH = Path(selected_path)


def get_results_path():
    return common_utils.get_pipeline_path(CURRENT_PROJECT_PATH, "Results", "CSV")


def get_reports_path():
    return common_utils.get_pipeline_path(CURRENT_PROJECT_PATH, "Reports", "CSV")


def get_error_reports_path():
    return common_utils.get_pipeline_path(CURRENT_PROJECT_PATH, "Error_reports", "CSV")


def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return Path(base_path) / relative_path


def get_taxdb():
    global _taxdb_cache
    if _taxdb_cache is None:
        db_path = Path.cwd() / "taxopy_db"
        try:
            _taxdb_cache = taxopy.TaxDb(taxdb_dir=str(db_path))
        except Exception as e:
            raise RuntimeError(
                f"Failed to load TaxDb. Ensure nodes.dmp and names.dmp exist in {db_path}. Error: {e}"
            )
    return _taxdb_cache


def load_csv_headers(file_path):
    try:
        with open(file_path, encoding="utf-8-sig") as f:
            return next(csv.reader(f))
    except StopIteration:
        return []
    except Exception:
        return []


def check_name_ncbi(name, taxdb):
    name_clean = name.strip()
    search_name = name_clean.replace("_", " ")
    parts = search_name.split()

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            taxid = taxopy.taxid_from_name(search_name, taxdb)
            if not taxid:
                taxid = taxopy.taxid_from_name(search_name, taxdb, fuzzy=True)

        if taxid:
            taxon = taxopy.Taxon(taxid[0], taxdb)
            suggested = taxon.name
            score = fuzz.ratio(search_name.lower(), suggested.lower())
            suggested_fmt = suggested.replace(" ", "_")

            if score == 100:
                return ("PERFECT", suggested_fmt, score, "")
            return ("SIMILAR", suggested_fmt, score, "")

        if len(parts) >= 3:
            fallback_name = " ".join(parts[:2])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fb_taxid = taxopy.taxid_from_name(fallback_name, taxdb)
            if fb_taxid:
                taxon = taxopy.Taxon(fb_taxid[0], taxdb)
                return (
                    "SUBS_NOT_FOUND",
                    taxon.name.replace(" ", "_"),
                    fuzz.ratio(fallback_name.lower(), taxon.name.lower()),
                    "",
                )

        return ("NOT_FOUND", name_clean.replace(" ", "_"), 0.0, "")
    except Exception as e:
        return ("ERROR", name_clean.replace(" ", "_"), 0.0, str(e))


def run_validation_pipeline(file_path, column_name, progress_cb=None):
    try:
        taxdb = get_taxdb()
    except Exception as e:
        return [("System Error", "ERROR", "TaxDB Load Failed", 0.0, str(e))]

    names = []
    try:
        with open(file_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get(column_name):
                    names.append(row[column_name].strip())
    except Exception as e:
        return [("System Error", "ERROR", "CSV Read Failed", 0.0, str(e))]

    out_dir = get_results_path()
    path = Path(file_path)

    v = 1
    mmdd = datetime.datetime.now().strftime("%m%d")
    while (out_dir / f"{path.stem}_fmt_v{v}_{mmdd}.csv").exists():
        v += 1
    out_path = out_dir / f"{path.stem}_fmt_v{v}_{mmdd}.csv"

    results = []

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f_in, open(
            out_path, "w", encoding="utf-8-sig", newline=""
        ) as f_out:

            reader = csv.reader(f_in)
            writer = csv.writer(f_out)
            headers = next(reader, [])
            writer.writerow(headers)

            if column_name not in headers:
                return []

            col_idx = headers.index(column_name)
            rows = list(reader)
            tot = len(rows)

            for i, row in enumerate(rows):
                if len(row) > col_idx:
                    orig = row[col_idx].strip()
                    if orig:
                        clean_name = orig.replace(" ", "_")
                        status, sugg_name, score, err = check_name_ncbi(orig, taxdb)

                        if status == "PERFECT":
                            row[col_idx] = sugg_name
                            results.append((orig, "PERFECT", sugg_name, 100.0, ""))
                        else:
                            row[col_idx] = clean_name
                            results.append((orig, status, sugg_name, score, err))

                writer.writerow(row)
                if progress_cb:
                    progress_cb(i + 1, tot)

    except Exception as e:
        results.append(("System Error", "ERROR", "Validation Failed", 0.0, str(e)))

    return results


def apply_and_save_corrections(
    original_path, column, corrections_dict, all_results, target_version=None
):
    res_dir = get_results_path()
    rep_dir = get_reports_path()
    err_dir = get_error_reports_path()

    if not res_dir or not rep_dir:
        return None, None, 0, None

    name_stem = Path(original_path).stem
    mmdd = datetime.datetime.now().strftime("%m%d")

    if target_version is not None:
        v = target_version
    else:
        v = 1
        while (rep_dir / f"Rpt_{name_stem}_fmt_v{v}_{mmdd}.xlsx").exists():
            v += 1

    new_csv_path = res_dir / f"{name_stem}_fmt_v{v}_{mmdd}.csv"
    new_rep_path = rep_dir / f"Rpt_{name_stem}_fmt_v{v}_{mmdd}.xlsx"

    error_list = [r for r in all_results if r[1] == "ERROR"]
    if error_list:
        err_file = err_dir / f"FMT_CSV_{name_stem}_Error_Log_v{v}_{mmdd}.txt"
        with open(err_file, "w", encoding="utf-8") as ef:
            ef.write(f"HYphlow System Error Log: {datetime.datetime.now()}\n")
            for orig, st, sg, sc, err_msg in error_list:
                ef.write(f"[FAIL] {orig} -> Reason: {err_msg}\n")

    applied_dict = {}
    updated_rows = []

    with open(original_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            orig = row[column].strip()
            if orig in corrections_dict:
                row[column] = corrections_dict[orig]
                applied_dict[orig] = corrections_dict[orig]
            else:
                row[column] = orig.replace(" ", "_")
            updated_rows.append(row)

    try:
        with open(new_csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(updated_rows)
    except Exception as e:
        raise RuntimeError(
            f"Failed to save CSV file. Check if it is open in another program: {e}"
        )

    try:
        with pd.ExcelWriter(new_rep_path, engine="xlsxwriter") as writer:
            workbook = writer.book
            bold_fmt = workbook.add_format({"bold": True})
            green_bg = workbook.add_format(
                {"bg_color": "#EBF9EE", "font_color": "#16A34A", "bold": True}
            )
            red_bg = workbook.add_format(
                {"bg_color": "#FFECEB", "font_color": "#FF3B30", "bold": True}
            )
            orange_bg = workbook.add_format(
                {"bg_color": "#FFF9E5", "font_color": "#FF9500", "bold": True}
            )

            ws_sum = workbook.add_worksheet("Summary")
            ws_sum.set_column("A:B", 30)

            ws_sum.write("A1", "HYphlow CSV Validation Report", bold_fmt)
            ws_sum.write("A2", "Date & Time", bold_fmt)
            ws_sum.write("B2", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            ws_sum.write("A3", "Original File", bold_fmt)
            ws_sum.write("B3", os.path.basename(original_path))
            ws_sum.write("A4", "Validated Output", bold_fmt)
            ws_sum.write("B4", new_csv_path.name)

            perfect_cnt = sum(1 for r in all_results if r[1] == "PERFECT")
            similar_cnt = sum(
                1 for r in all_results if r[1] in ["SIMILAR", "SUBS_NOT_FOUND"]
            )
            error_cnt = sum(1 for r in all_results if r[1] in ["NOT_FOUND", "ERROR"])

            ws_sum.write("A6", "--- Statistics ---", bold_fmt)
            ws_sum.write("A7", "Total Validated Names", bold_fmt)
            ws_sum.write("B7", len(all_results))
            ws_sum.write("A8", "Perfect Matches", bold_fmt)
            ws_sum.write("B8", perfect_cnt, green_bg)
            ws_sum.write("A9", "Corrections Applied", bold_fmt)
            ws_sum.write(
                "B9", len(applied_dict), orange_bg if len(applied_dict) > 0 else None
            )

            details_data = []
            for orig, status, sugg, score, err in all_results:
                final_name = applied_dict.get(orig, orig.replace(" ", "_"))

                if status == "PERFECT":
                    disp_status = "PERFECT"
                    note = "Exact match verified in NCBI taxonomy."
                elif orig in applied_dict:
                    disp_status = "MODIFIED"
                    note = "Validation correction applied."
                else:
                    disp_status = "IGNORED"
                    note = "User ignored suggested correction or no match found."

                details_data.append([orig, final_name, disp_status, note])

            df = pd.DataFrame(
                details_data,
                columns=[
                    "Original Taxon",
                    "NCBI Taxon",
                    "Match Status",
                    "Note",
                ],
            )
            df.to_excel(writer, sheet_name="Detailed Report", index=False)

            ws_det = writer.sheets["Detailed Report"]
            ws_det.set_column("A:D", 30)

            row_range = f"C2:C{len(details_data)+1}"
            ws_det.conditional_format(
                row_range,
                {
                    "type": "cell",
                    "criteria": "==",
                    "value": '"PERFECT"',
                    "format": green_bg,
                },
            )
            ws_det.conditional_format(
                row_range,
                {
                    "type": "cell",
                    "criteria": "==",
                    "value": '"MODIFIED"',
                    "format": orange_bg,
                },
            )
            ws_det.conditional_format(
                row_range,
                {
                    "type": "cell",
                    "criteria": "==",
                    "value": '"IGNORED"',
                    "format": red_bg,
                },
            )

    except Exception as e:
        raise RuntimeError(f"Report Generation Failed. Check if Excel is open: {e}")

    return str(new_csv_path), str(new_rep_path), len(applied_dict), v
