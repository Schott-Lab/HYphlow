import csv
import re
import datetime
import warnings
from pathlib import Path
from typing import NamedTuple, Optional

import pandas as pd
import taxopy
from rapidfuzz import fuzz


from hyphlow import common_utils

# =========================================================== constants
VALIDATED = "VALIDATED"
SIMILAR = "SIMILAR"
MULTIPLE_HITS = "MULTIPLE_HITS"
SUBS_NOT_FOUND = "SUBS_NOT_FOUND"
ABOVE_SPECIES = "ABOVE_SPECIES"
OPEN_NOMENCLATURE = "OPEN_NOMENCLATURE"
NOT_FOUND = "NOT_FOUND"
ERROR = "ERROR"
# Tip labels must name a species. A genus- or order-level match sits at a
# different rank from the rest of the tree.

ACCEPTED_RANKS = frozenset({"species", "subspecies"})

# NCBI registers provisional names such as "Testudo sp." at species rank, often
# with a strain code appended, so the marker is not always at the end.
OPEN_MARKERS = re.compile(r"\b(sp|spp|cf|aff|nr)\.", re.IGNORECASE)

# Anything not listed is either applied automatically (VALIDATED) or left untouched.
NEEDS_REVIEW = (
    SIMILAR,
    MULTIPLE_HITS,
    SUBS_NOT_FOUND,
    ABOVE_SPECIES,
    OPEN_NOMENCLATURE,
)

MAX_HITS_SHOWN = 3


class ValidationCancelled(Exception):
    pass


class NameCheck(NamedTuple):
    status: str
    suggested: str
    score: float
    taxid: Optional[int]
    note: str


class ValidationRow(NamedTuple):
    original: str
    status: str
    suggested: str
    score: float
    taxid: Optional[int]
    note: str


CURRENT_PROJECT_NAME = "Untitled Project"
CURRENT_PROJECT_PATH = None

_taxdb_cache = None

# ======================================================= project state


def set_project_name(name):
    global CURRENT_PROJECT_NAME
    CURRENT_PROJECT_NAME = name


def get_project_name():
    return CURRENT_PROJECT_NAME


def set_project_path(selected_path):
    global CURRENT_PROJECT_PATH
    CURRENT_PROJECT_PATH = Path(selected_path)


# =============================================================== paths


def get_results_path():
    return common_utils.get_pipeline_path(CURRENT_PROJECT_PATH, "Results", "CSV")


def get_reports_path():
    return common_utils.get_pipeline_path(CURRENT_PROJECT_PATH, "Reports", "CSV")


def get_error_reports_path():
    if not CURRENT_PROJECT_PATH:
        return None
    path = Path(CURRENT_PROJECT_PATH) / "Reports" / "Error_Reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


# =================================================== taxonomy database


def get_taxdb():
    # Project copy overrides the shared cwd copy.
    global _taxdb_cache
    if _taxdb_cache is None:
        searched = [
            p / "taxopy_db" for p in (CURRENT_PROJECT_PATH, Path.cwd()) if p is not None
        ]
        db_path = next(
            (p for p in searched if (p / "nodes.dmp").exists()), searched[-1]
        )
        try:
            _taxdb_cache = taxopy.TaxDb(taxdb_dir=str(db_path))
        except Exception as e:
            raise RuntimeError(
                "Failed to load TaxDb. Ensure nodes.dmp and names.dmp exist in one of: "
                f"{', '.join(str(p) for p in searched)}. Error: {e}"
            ) from e
    return _taxdb_cache


def load_csv_headers(file_path):
    # Empty file, unreadable file, and bad encoding all give no columns.
    try:
        with open(file_path, encoding="utf-8-sig") as f:
            return next(csv.reader(f))
    except Exception:
        return []


# ===================================================== name validation


def _lookup(search_name, taxdb, fuzzy=False):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return taxopy.taxid_from_name(search_name, taxdb, fuzzy=fuzzy)


def check_name_ncbi(name, taxdb):
    name_clean = name.strip()
    search_name = name_clean.replace("_", " ")
    parts = search_name.split()
    original_fmt = name_clean.replace(" ", "_")

    def scored(candidate):
        # Always against the name as supplied, so every score in the report shares one denominator
        return fuzz.ratio(search_name.lower(), candidate.lower())

    try:
        taxid = _lookup(search_name, taxdb)
        exact = bool(taxid)
        if not taxid:
            taxid = _lookup(search_name, taxdb, fuzzy=True)

        if taxid:
            if exact and len(taxid) > 1:
                names = ", ".join(
                    f"{taxdb.taxid2name.get(t, '?')} (taxid {t})"
                    for t in taxid[:MAX_HITS_SHOWN]
                )
                more = "" if len(taxid) <= MAX_HITS_SHOWN else ", ..."
                return NameCheck(
                    MULTIPLE_HITS,
                    original_fmt,
                    0.0,
                    None,
                    f"{len(taxid)} taxa match this name: {names}{more}",
                )

            best = max(taxid, key=lambda t: scored(taxdb.taxid2name.get(t, "")))
            suggested = taxdb.taxid2name.get(best, "")
            score = scored(suggested)

            rank = taxdb.taxid2rank.get(best, "")
            if rank not in ACCEPTED_RANKS:
                return NameCheck(
                    ABOVE_SPECIES,
                    original_fmt,
                    score,
                    best,
                    f"matched at rank '{rank}': {suggested} (taxid {best})",
                )
            if OPEN_MARKERS.search(suggested):
                return NameCheck(
                    OPEN_NOMENCLATURE,
                    original_fmt,
                    score,
                    best,
                    f"provisional identifier:{suggested} (taxid {best})",
                )
            status = VALIDATED if (exact and score == 100) else SIMILAR
            return NameCheck(status, suggested.replace(" ", "_"), score, best, "")

        # Genus + species only; a name that fails as a trinomial may still resolve at the species level.
        if len(parts) >= 3:
            fallback_name = " ".join(parts[:2])
            fb_taxid = _lookup(fallback_name, taxdb) or _lookup(
                fallback_name, taxdb, fuzzy=True
            )
            if fb_taxid:
                species_id = fb_taxid[0]
                species = taxdb.taxid2name.get(species_id, "")
                return NameCheck(
                    SUBS_NOT_FOUND,
                    original_fmt,
                    scored(species),
                    None,
                    f"subspecies not in NCBI; species found: "
                    f"{species} (taxid {species_id})",
                )
        return NameCheck(NOT_FOUND, original_fmt, 0.0, None, "")
    except Exception as e:
        return NameCheck(ERROR, original_fmt, 0.0, None, str(e))


def run_validation_pipeline(file_path, column_name, progress_cb=None):
    try:
        taxdb = get_taxdb()
    except Exception as e:
        return [
            ValidationRow("System Error", ERROR, "TaxDB Load Failed", 0.0, None, str(e))
        ]

    try:
        with open(file_path, encoding="utf-8-sig") as f:
            headers = next(csv.reader(f), [])
    except Exception as e:
        return [
            ValidationRow("System Error", ERROR, "CSV Read Failed", 0.0, None, str(e))
        ]
    if column_name not in headers:
        return []

    out_dir = get_results_path()
    if not out_dir:
        return [
            ValidationRow(
                "System Error",
                ERROR,
                "No Project Folder",
                0.0,
                None,
                "Select or create a project folder before running validation.",
            )
        ]
    path = Path(file_path)

    v = 1
    mmdd = datetime.datetime.now().strftime("%m%d")
    while (out_dir / f"{path.stem}_fmt_v{v}_{mmdd}.csv").exists():
        v += 1
    out_path = out_dir / f"{path.stem}_fmt_v{v}_{mmdd}.csv"

    results = []

    try:
        with (
            open(file_path, "r", encoding="utf-8-sig") as f_in,
            open(out_path, "w", encoding="utf-8-sig", newline="") as f_out,
        ):
            reader = csv.reader(f_in)
            writer = csv.writer(f_out)
            writer.writerow(next(reader, []))

            col_idx = headers.index(column_name)
            rows = list(reader)
            tot = len(rows)

            for i, row in enumerate(rows):
                if len(row) > col_idx:
                    orig = row[col_idx].strip()
                    if orig:
                        chk = check_name_ncbi(orig, taxdb)

                        if chk.status == VALIDATED:
                            row[col_idx] = chk.suggested
                        else:
                            row[col_idx] = orig.replace(" ", "_")
                        results.append(ValidationRow(orig, *chk))

                writer.writerow(row)
                if progress_cb:
                    progress_cb(i + 1, tot)
    except ValidationCancelled:
        out_path.unlink(missing_ok=True)
        raise

    except Exception as e:
        results.append(
            ValidationRow("System Error", ERROR, "Validation Failed", 0.0, None, str(e))
        )

    return results


def apply_and_save_corrections(original_path, column, correction_dict, all_results):
    res_dir = get_results_path()
    rep_dir = get_reports_path()
    err_dir = get_error_reports_path()

    if not res_dir or not rep_dir:
        return None, None, 0, None

    name_stem = Path(original_path).stem
    mmdd = datetime.datetime.now().strftime("%m%d")

    v = 1
    while (rep_dir / f"Rpt_{name_stem}_fmt_v{v}_{mmdd}.xlsx").exists():
        v += 1

    new_csv_path = res_dir / f"{name_stem}_fmt_v{v}_{mmdd}.csv"
    new_rep_path = rep_dir / f"Rpt_{name_stem}_fmt_v{v}_{mmdd}.xlsx"

    error_list = [r for r in all_results if r.status == ERROR]
    if error_list and err_dir:
        err_file = err_dir / f"FMT_CSV_{name_stem}_Error_Log_v{v}_{mmdd}.txt"
        with open(err_file, "w", encoding="utf-8") as ef:
            ef.write(f"HYphlow System Error Log: {datetime.datetime.now()}\n")
            for r in error_list:
                ef.write(f"[FAIL] {r.original} -> Reason: {r.note}\n")

    applied_dict = {}
    updated_rows = []

    with open(original_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            orig = row[column].strip()
            if orig in correction_dict:
                row[column] = correction_dict[orig]
                applied_dict[orig] = correction_dict[orig]
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
        ) from e

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
            ws_sum.write("B3", Path(original_path).name)
            ws_sum.write("A4", "Validated Output", bold_fmt)
            ws_sum.write("B4", new_csv_path.name)

            validated_cnt = sum(1 for r in all_results if r.status == VALIDATED)
            review_cnt = sum(1 for r in all_results if r.status in NEEDS_REVIEW)

            ws_sum.write("A6", "--- Statistics ---", bold_fmt)
            ws_sum.write("A7", "Total Validated Names", bold_fmt)
            ws_sum.write("B7", len(all_results))
            ws_sum.write("A8", "Automatic Matches", bold_fmt)
            ws_sum.write("B8", validated_cnt, green_bg)
            ws_sum.write("A9", "Flagged for Review", bold_fmt)
            ws_sum.write("B9", review_cnt)
            ws_sum.write("A10", "Corrections Applied", bold_fmt)
            ws_sum.write("B10", len(applied_dict), orange_bg if applied_dict else None)

            details_data = []
            for r in all_results:
                final_name = applied_dict.get(r.original, r.original.replace(" ", "_"))

                if r.status == VALIDATED:
                    action = "AUTO"
                    note = "Exact match verified in NCBI taxonomy."
                elif r.original in applied_dict:
                    action = "APPLIED"
                    note = "Suggested correction accepted by user."
                else:
                    action = "RETAINED"
                    note = r.note or "Original name kept."

                details_data.append(
                    [
                        r.original,
                        final_name,
                        r.taxid,
                        r.status,
                        action,
                        round(r.score, 1),
                        note,
                    ]
                )
            df = pd.DataFrame(
                details_data,
                columns=[
                    "Original Taxon",
                    "Final Name",
                    "NCBI TaxID",
                    "Validation Status",
                    "Action",
                    "Similarity (%)",
                    "Note",
                ],
            )
            df["NCBI TaxID"] = df["NCBI TaxID"].astype("Int64")
            df.to_excel(writer, sheet_name="Detailed Report", index=False)

            ws_det = writer.sheets["Detailed Report"]
            ws_det.set_column("A:B", 26)
            ws_det.set_column("C:C", 12)
            ws_det.set_column("D:E", 18)
            ws_det.set_column("F:F", 14)
            ws_det.set_column("G:G", 52)

            if details_data:
                action_range = f"E2:E{len(details_data) + 1}"
                for value, fmt in (
                    ("AUTO", green_bg),
                    ("APPLIED", orange_bg),
                    ("RETAINED", red_bg),
                ):
                    ws_det.conditional_format(
                        action_range,
                        {
                            "type": "cell",
                            "criteria": "==",
                            "value": f'"{value}"',
                            "format": fmt,
                        },
                    )
    except Exception as e:
        raise RuntimeError(
            f"Report Generation Failed. Check if Excel is open: {e}"
        ) from e

    return str(new_csv_path), str(new_rep_path), len(applied_dict), v
