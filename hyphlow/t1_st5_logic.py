import csv
import re
from pathlib import Path

from rapidfuzz import process, fuzz

from hyphlow import (
    bio_io,
    common_utils,
    manifest_logic_tab,
    report_builder,
    t1_st1_logic,
)

# =========================================================== constants
EXACT = "EXACT"
SIMILAR = "SIMILAR"
NOT_FOUND = "NOT_FOUND"

# Written into the suggestion column when nothing matched. The UI compares
# against it to decide a row is not applicable, so both sides must agree.
NO_MATCH_LABEL = "No safe match"

# A label can be SIMILAR yet end up UNRESOLVED: the user may decline the
# suggestion. These are not the same axis as the three above.
VERIFIED = "VERIFIED"
CORRECTED = "CORRECTED"
UNRESOLVED = "UNRESOLVED"

COLOR_BY_VERDICT = {
    VERIFIED: "green",
    CORRECTED: "orange",
    UNRESOLVED: "red",
}

# Above MIN_MATCH_SCORE without scoring: a prefix relation
# (strain, or accession) is taken as near certain.
PREFIX_MATCH_SCORE = 95.0
MIN_MATCH_SCORE = 80

IGNORE_WORDS = common_utils.IGNORE_WORDS | {"TAGGED", "V3"}


def get_csv_master_names(csv_path, target_col):
    master_names = set()
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        if target_col not in headers:
            return set()
        col_idx = headers.index(target_col)
        for row in reader:
            if len(row) > col_idx:
                val = row[col_idx].strip()
                if val:
                    master_names.add(common_utils.to_label(val))
    return master_names


def match_names(target_names, master_names):
    results = []
    for orig in target_names:
        if orig in master_names:
            results.append((orig, EXACT, orig, 100.0))
            continue

        best_match = None
        best_score = 0.0

        for m_name in master_names:
            if m_name.startswith(orig + "_") or orig.startswith(m_name + "_"):
                best_match = m_name
                best_score = PREFIX_MATCH_SCORE
                break

        if not best_match:
            match = process.extractOne(orig, master_names, scorer=fuzz.ratio)
            if match:
                best_match, best_score, _ = match

        if best_match and best_score >= MIN_MATCH_SCORE:
            results.append((orig, SIMILAR, best_match, best_score))
        else:
            results.append((orig, NOT_FOUND, NO_MATCH_LABEL, best_score))

    return results


def get_file_keywords(filename):
    stem = Path(filename).stem.upper()
    tokens = [
        t
        for t in re.split(r"[^A-Z0-9]", stem)
        if len(t) >= 2 and t not in IGNORE_WORDS and not t.isdigit()
    ]
    return set(tokens)


def run_smart_verification(csv_path, csv_col, fasta_files, nwk_files):
    all_results = {"CSV_FAS": [], "CSV_NWK": [], "FAS_NWK": [], "NWK_FAS": []}
    csv_master_names = set()

    if csv_path:
        csv_master_names = get_csv_master_names(csv_path, csv_col)

    if csv_master_names:
        for fasta in fasta_files:
            f_path = Path(fasta)
            t_names = bio_io.read_fasta_taxa(f_path)
            matches = match_names(t_names, csv_master_names)
            for orig, status, sugg, score in matches:
                all_results["CSV_FAS"].append(
                    ("FASTA", f_path.name, orig, status, sugg, score)
                )

        for nwk in nwk_files:
            n_path = Path(nwk)
            t_names = bio_io.read_tree_taxa(n_path)
            matches = match_names(t_names, csv_master_names)
            for orig, status, sugg, score in matches:
                all_results["CSV_NWK"].append(
                    ("NWK", n_path.name, orig, status, sugg, score)
                )

    for fas in fasta_files:
        f_path = Path(fas)
        fas_keywords = get_file_keywords(f_path.name)
        fas_names = bio_io.read_fasta_taxa(f_path)

        for nwk in nwk_files:
            n_path = Path(nwk)
            nwk_keywords = get_file_keywords(n_path.name)

            if fas_keywords.intersection(nwk_keywords):
                nwk_names = bio_io.read_tree_taxa(n_path)

                matches_to_nwk = match_names(nwk_names, fas_names)
                title_fas_master = f"{f_path.name} vs {n_path.name}"
                for orig, status, sugg, score in matches_to_nwk:
                    all_results["FAS_NWK"].append(
                        ("FAS_NWK", title_fas_master, orig, status, sugg, score)
                    )

                matches_to_fas = match_names(fas_names, nwk_names)
                title_nwk_master = f"{n_path.name} vs {f_path.name}"
                for orig, status, sugg, score in matches_to_fas:
                    all_results["NWK_FAS"].append(
                        ("NWK_FAS", title_nwk_master, orig, status, sugg, score)
                    )
    return all_results


def _base_name_for(file_path):
    org, gene = manifest_logic_tab.resolve_identity(
        t1_st1_logic.CURRENT_PROJECT_PATH, file_path
    )
    return common_utils.make_base_name(org, gene)


def _lookup_status(status_lookup, file_name, orig_clean):
    for (bk_fname, bk_orig), st in status_lookup.items():
        if bk_orig == orig_clean and file_name in bk_fname:
            return st
    return None


def build_status_lookup(blocks_data):
    lookup = {}
    for fname, rows in blocks_data:
        for r in rows:
            lookup[(fname, common_utils.to_label(r[2]))] = r[3]
    return lookup


def _verdict_row(orig, orig_clean, final_name, match_status):
    if final_name:
        return [orig, final_name, CORRECTED, "Reconciliation correction applied."]
    if match_status == SIMILAR:
        # A suggestion existed; the user declined it, so the label in the file
        # is still unverified.
        return [orig, orig_clean, UNRESOLVED, "User declined the suggested match."]
    if match_status == NOT_FOUND:
        return [orig, orig_clean, UNRESOLVED, "No safe match found."]
    return [orig, orig_clean, VERIFIED, "Exact match verified across datasets."]


def apply_and_save_reconciled(
    fasta_files,
    fasta_corrections,
    nwk_files,
    nwk_corrections,
    status_lookup=None,
    progress_cb=None,
):
    proj = t1_st1_logic.CURRENT_PROJECT_PATH
    status_lookup = status_lookup or {}
    saved_fastas = []
    saved_nwks = []
    saved_reports = []
    total = len(fasta_files or []) + len(nwk_files or [])
    done = 0

    if fasta_files:
        fasta_out_dir = common_utils.get_pipeline_path(
            proj, common_utils.RESULTS, "FASTA"
        )
        fasta_rep_dir = common_utils.get_pipeline_path(
            proj, common_utils.REPORTS, "FASTA"
        )

        for fasta in fasta_files:
            f_path = Path(fasta)
            gene = _base_name_for(f_path)

            new_f_path_str, _ = common_utils.generate_smart_filename(
                gene, "FASTA_REC", fasta_out_dir, ".fasta", is_report=False
            )
            new_f_path = Path(new_f_path_str)

            rep_path_str, _ = common_utils.generate_smart_filename(
                gene, "FASTA_REC", fasta_rep_dir, ".xlsx", is_report=True
            )
            rep_path = Path(rep_path_str)

            lines = []
            details_data = []
            with open(f_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.startswith(">"):
                        lines.append(line)
                        continue

                    orig = line.strip().lstrip(">")
                    orig_clean = common_utils.to_label(orig)
                    final_name = fasta_corrections.get(orig_clean)

                    if final_name:
                        lines.append(f">{final_name}\n")
                    else:
                        lines.append(line)
                    details_data.append(
                        _verdict_row(
                            orig,
                            orig_clean,
                            final_name,
                            _lookup_status(status_lookup, f_path.name, orig_clean),
                        )
                    )
            with open(new_f_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            saved_fastas.append(new_f_path)

            manifest_logic_tab.add_row(
                proj,
                *manifest_logic_tab.resolve_identity(proj, f_path),
                "",
                "aln_rec",
                str(new_f_path),
                str(f_path),
            )
            _generate_report(
                rep_path,
                "FASTA Reconciliation",
                f_path.name,
                new_f_path.name,
                details_data,
            )
            saved_reports.append(rep_path)
            done += 1
            if progress_cb:
                progress_cb(done, total)

    if nwk_files:
        nwk_out_dir = common_utils.get_pipeline_path(proj, common_utils.RESULTS, "NWK")
        nwk_rep_dir = common_utils.get_pipeline_path(proj, common_utils.REPORTS, "NWK")

        for nwk in nwk_files:
            n_path = Path(nwk)
            gene = _base_name_for(n_path)

            new_n_path_str, _ = common_utils.generate_smart_filename(
                gene, "NWK_REC", nwk_out_dir, ".nwk", is_report=False
            )
            new_n_path = Path(new_n_path_str)

            rep_path_str, _ = common_utils.generate_smart_filename(
                gene, "NWK_REC", nwk_rep_dir, ".xlsx", is_report=True
            )
            rep_path = Path(rep_path_str)

            details_data = []
            tree, orig_format = bio_io.load_tree(n_path)

            for node in tree.traverse():
                if not (node.is_leaf() and node.name):
                    continue

                orig = node.name
                orig_clean = common_utils.to_label(orig)
                final_name = nwk_corrections.get(orig_clean)

                if final_name:
                    node.name = final_name
                details_data.append(
                    _verdict_row(
                        orig,
                        orig_clean,
                        final_name,
                        _lookup_status(status_lookup, n_path.name, orig_clean),
                    )
                )
            # Write back in the format the file was read in, so internal node
            # labels survive if they were there to begin with.
            tree.write(outfile=str(new_n_path), format=orig_format)
            saved_nwks.append(new_n_path)

            manifest_logic_tab.add_row(
                proj,
                *manifest_logic_tab.resolve_identity(proj, n_path),
                "",
                "tree_rec",
                str(new_n_path),
                str(n_path),
            )
            _generate_report(
                rep_path,
                "NWK Reconciliation",
                n_path.name,
                new_n_path.name,
                details_data,
            )
            saved_reports.append(rep_path)
            done += 1
            if progress_cb:
                progress_cb(done, total)

    return saved_fastas, saved_nwks, saved_reports


def _generate_report(rep_path, title, orig_name, new_name, details_data):
    verified = sum(1 for r in details_data if r[2] == VERIFIED)
    corrected = sum(1 for r in details_data if r[2] == CORRECTED)
    unresolved = sum(1 for r in details_data if r[2] == UNRESOLVED)
    try:
        report_builder.build_report(
            rep_path,
            title=title,
            source=orig_name,
            output=new_name,
            stats=[
                ("Total Target Taxa", len(details_data)),
                ("Verified (No Change)", verified, "green" if verified else None),
                ("Corrected", corrected, "orange" if corrected else None),
                ("Unresolved", unresolved, "red" if unresolved else None),
            ],
            rows=details_data,
            columns=["Original Taxon", "Reconciled Name", "Match Status", "Note"],
            color_column="Match Status",
            color_map=COLOR_BY_VERDICT,
            widths={"A:D": 25},
        )
    except Exception as e:
        raise RuntimeError(
            f"Report generation failed (Check if file is open): {e}"
        ) from e
