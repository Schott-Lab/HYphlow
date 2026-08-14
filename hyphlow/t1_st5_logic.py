import csv
import re
import datetime
from pathlib import Path
from rapidfuzz import process, fuzz
from ete3 import Tree
import pandas as pd

from hyphlow import common_utils
from hyphlow import t1_st1_logic
from hyphlow import manifest_logic_tab



def get_csv_master_names(csv_path, target_col):
    master_names = set()
    try:
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
                        master_names.add(val.replace(" ", "_"))
    except Exception as e:
        print(f"CSV read error: {e}")
    return master_names


def _get_fasta_names(f_path):
    names = set()
    try:
        with open(f_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(">"):
                    names.add(line.strip().lstrip(">").replace(" ", "_"))
    except Exception as e:
        print(f"[ERROR] Failed to read FASTA file {f_path}: {e}")
    return names


def _get_nwk_names(n_path):
    names = set()
    try:
        try:
            tree = Tree(str(n_path), format=1)
        except:
            tree = Tree(str(n_path))
        for leaf in tree.get_leaves():
            names.add(leaf.name.replace(" ", "_"))
    except Exception as e:
        print(f"[ERROR] Failed to read NWK file {n_path}: {e}")
    return names


def match_names(target_names, master_names):
    results = []
    for orig in target_names:
        if orig in master_names:
            results.append((orig, "PERFECT", orig, 100.0))
        else:
            best_match = None
            best_score = 0.0

            for m_name in master_names:
                if m_name.startswith(orig + "_") or orig.startswith(m_name + "_"):
                    best_match = m_name
                    best_score = 95.0
                    break

            if not best_match:
                match = process.extractOne(orig, master_names, scorer=fuzz.ratio)
                if match:
                    best_match, score, _ = match
                    best_score = score

            if best_match and best_score >= 80:
                results.append((orig, "SIMILAR", best_match, best_score))
            else:
                results.append((orig, "NOT_FOUND", "No safe match", best_score))

    return results


def get_file_keywords(filename):
    ignore_words = {
        "FMT",
        "FAS",
        "FASTA",
        "NWK",
        "TREE",
        "ALIGN",
        "OUTPUT",
        "REC",
        "PR",
        "MASTER",
        "CSV",
        "TAGGED",
        "V1",
        "V2",
        "V3",
    }
    stem = Path(filename).stem.upper()
    tokens = [
        t
        for t in re.split(r"[^A-Z0-9]", stem)
        if len(t) >= 2 and t not in ignore_words and not t.isdigit()
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
            t_names = _get_fasta_names(f_path)
            matches = match_names(t_names, csv_master_names)
            for orig, status, sugg, score in matches:
                all_results["CSV_FAS"].append(
                    ("FASTA", f_path.name, orig, status, sugg, score)
                )

        for nwk in nwk_files:
            n_path = Path(nwk)
            t_names = _get_nwk_names(n_path)
            matches = match_names(t_names, csv_master_names)
            for orig, status, sugg, score in matches:
                all_results["CSV_NWK"].append(
                    ("NWK", n_path.name, orig, status, sugg, score)
                )

    for fas in fasta_files:
        f_path = Path(fas)
        fas_keywords = get_file_keywords(f_path.name)
        fas_names = _get_fasta_names(f_path)

        for nwk in nwk_files:
            n_path = Path(nwk)
            nwk_keywords = get_file_keywords(n_path.name)

            if fas_keywords.intersection(nwk_keywords):
                nwk_names = _get_nwk_names(n_path)

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


def apply_and_save_reconciled(
    fasta_files, fasta_corrections, nwk_files, nwk_corrections, result_blocks=None
):
    if result_blocks is None:
        result_blocks = []

    saved_fastas = []
    saved_nwks = []
    saved_reports = []

    status_lookup = {}
    for block in result_blocks:
        for r in block.corrections:
            orig = r[2]
            status = r[3]
            status_fmt = "SIMILAR" if status == "SIMILAR" else "MISMATCH"
            status_lookup[(block.fname, orig.replace(" ", "_"))] = status_fmt

    if fasta_files:
        fasta_out_dir = common_utils.get_pipeline_path(
            t1_st1_logic.CURRENT_PROJECT_PATH, "Results", "FASTA"
        )
        fasta_rep_dir = common_utils.get_pipeline_path(
            t1_st1_logic.CURRENT_PROJECT_PATH, "Reports", "FASTA"
        )

        for fasta in fasta_files:
            f_path = Path(fasta)
            gene = _base_name_for(f_path)

            new_f_path_str, v = common_utils.generate_smart_filename(
                gene, "FASTA_REC", fasta_out_dir, ".fasta", is_report=False
            )
            new_f_path = Path(new_f_path_str)

            rep_path_str, _ = common_utils.generate_smart_filename(
                gene, "FASTA_REC", fasta_rep_dir, ".xlsx", is_report=True
            )
            rep_path = Path(rep_path_str)

            lines = []
            details_data = []
            try:
                with open(f_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith(">"):
                            orig = line.strip().lstrip(">")
                            orig_clean = orig.replace(" ", "_")

                            lookup_status = None
                            for (bk_fname, bk_orig), st in status_lookup.items():
                                if bk_orig == orig_clean and f_path.name in bk_fname:
                                    lookup_status = st
                                    break

                            if orig_clean in fasta_corrections:
                                final_name = fasta_corrections[orig_clean]
                                lines.append(f">{final_name}\n")
                                details_data.append(
                                    [
                                        orig,
                                        final_name,
                                        "SIMILAR",
                                        "Reconciliation correction applied.",
                                    ]
                                )
                            else:
                                lines.append(line)
                                if lookup_status == "MISMATCH":
                                    details_data.append(
                                        [
                                            orig,
                                            orig_clean,
                                            "MISMATCH",
                                            "No safe match found or user skipped correction.",
                                        ]
                                    )
                                elif lookup_status == "SIMILAR":
                                    details_data.append(
                                        [
                                            orig,
                                            orig_clean,
                                            "SIMILAR",
                                            "User ignored suggested correction.",
                                        ]
                                    )
                                else:
                                    details_data.append(
                                        [
                                            orig,
                                            orig_clean,
                                            "PERFECT",
                                            "Exact match verified across datasets.",
                                        ]
                                    )
                        else:
                            lines.append(line)

                with open(new_f_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                saved_fastas.append(new_f_path)
                try:
                    manifest_logic_tab.add_row(
                        t1_st1_logic.CURRENT_PROJECT_PATH,
                        *manifest_logic_tab.resolve_identity(
                            t1_st1_logic.CURRENT_PROJECT_PATH, f_path
                        ),
                        "",
                        "aln_rec",
                        str(new_f_path),
                        str(f_path),
                    )
                except Exception as e:
                    print("manifest write failed:", e)
                _generate_report(
                    rep_path,
                    "FASTA Reconciliation",
                    f_path.name,
                    new_f_path.name,
                    details_data,
                    "FASTA Details",
                )
                saved_reports.append(rep_path)
            except Exception as e:
                print(f"Error processing {fasta}: {e}")

    if nwk_files:
        nwk_out_dir = common_utils.get_pipeline_path(
            t1_st1_logic.CURRENT_PROJECT_PATH, "Results", "NWK"
        )
        nwk_rep_dir = common_utils.get_pipeline_path(
            t1_st1_logic.CURRENT_PROJECT_PATH, "Reports", "NWK"
        )

        for nwk in nwk_files:
            n_path = Path(nwk)
            gene = _base_name_for(n_path)

            new_n_path_str, v = common_utils.generate_smart_filename(
                gene, "NWK_REC", nwk_out_dir, ".nwk", is_report=False
            )
            new_n_path = Path(new_n_path_str)

            rep_path_str, _ = common_utils.generate_smart_filename(
                gene, "NWK_REC", nwk_rep_dir, ".xlsx", is_report=True
            )
            rep_path = Path(rep_path_str)

            details_data = []
            try:
                try:
                    tree = Tree(str(n_path), format=1)
                except:
                    tree = Tree(str(n_path))

                for node in tree.traverse():
                    if node.is_leaf() and node.name:
                        orig = node.name
                        orig_clean = orig.replace(" ", "_")

                        lookup_status = None
                        for (bk_fname, bk_orig), st in status_lookup.items():
                            if bk_orig == orig_clean and n_path.name in bk_fname:
                                lookup_status = st
                                break

                        if orig_clean in nwk_corrections:
                            final_name = nwk_corrections[orig_clean]
                            node.name = final_name
                            details_data.append(
                                [
                                    orig,
                                    final_name,
                                    "SIMILAR",
                                    "Reconciliation correction applied.",
                                ]
                            )
                        else:
                            if lookup_status == "MISMATCH":
                                details_data.append(
                                    [
                                        orig,
                                        orig_clean,
                                        "MISMATCH",
                                        "No safe match found or user skipped correction.",
                                    ]
                                )
                            elif lookup_status == "SIMILAR":
                                details_data.append(
                                    [
                                        orig,
                                        orig_clean,
                                        "SIMILAR",
                                        "User ignored suggested correction.",
                                    ]
                                )
                            else:
                                details_data.append(
                                    [
                                        orig,
                                        orig_clean,
                                        "PERFECT",
                                        "Exact match verified across datasets.",
                                    ]
                                )

                tree.write(outfile=str(new_n_path), format=1)
                saved_nwks.append(new_n_path)
                try:
                    manifest_logic_tab.add_row(
                        t1_st1_logic.CURRENT_PROJECT_PATH,
                        *manifest_logic_tab.resolve_identity(
                            t1_st1_logic.CURRENT_PROJECT_PATH, n_path
                        ),
                        "",
                        "tree_rec",
                        str(new_n_path),
                        str(n_path),
                    )
                except Exception as e:
                    print("manifest write failed:", e)

                _generate_report(
                    rep_path,
                    "NWK Reconciliation",
                    n_path.name,
                    new_n_path.name,
                    details_data,
                    "NWK Details",
                )
                saved_reports.append(rep_path)
            except Exception as e:
                print(f"Error processing {nwk}: {e}")

    return saved_fastas, saved_nwks, saved_reports


def _generate_report(
    rep_path, title, orig_name, new_name, details_data, sheet_name="Details"
):
    try:
        with pd.ExcelWriter(rep_path, engine="xlsxwriter") as writer:
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
            ws_sum.set_column("A:B", 35)

            ws_sum.write("A1", f"HYphlow {title} Report", bold_fmt)
            ws_sum.write("A2", "Date & Time", bold_fmt)
            ws_sum.write("B2", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            ws_sum.write("A3", "Source File", bold_fmt)
            ws_sum.write("B3", orig_name)
            ws_sum.write("A4", "Reconciled Output", bold_fmt)
            ws_sum.write("B4", new_name)

            total_targets = len(details_data)
            perfect_cnt = sum(1 for r in details_data if r[2] == "PERFECT")
            similar_cnt = sum(1 for r in details_data if r[2] == "SIMILAR")
            mismatch_cnt = sum(1 for r in details_data if r[2] == "MISMATCH")

            ws_sum.write("A6", "--- Statistics ---", bold_fmt)
            ws_sum.write("A7", "Total Target Taxa", bold_fmt)
            ws_sum.write("B7", total_targets)
            ws_sum.write("A8", "Perfect Matches", bold_fmt)
            ws_sum.write("B8", perfect_cnt, green_bg)
            ws_sum.write("A9", "Similar (Reconciled/Suggested)", bold_fmt)
            ws_sum.write("B9", similar_cnt, orange_bg)
            ws_sum.write("A10", "Mismatches / Unresolved", bold_fmt)
            ws_sum.write("B10", mismatch_cnt, red_bg)

            df = pd.DataFrame(
                details_data,
                columns=["Original Taxon", "Reconciled Name", "Match Status", "Note"],
            )
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            ws_det = writer.sheets[sheet_name]
            ws_det.set_column("A:D", 25)

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
                    "value": '"SIMILAR"',
                    "format": orange_bg,
                },
            )
            ws_det.conditional_format(
                row_range,
                {
                    "type": "cell",
                    "criteria": "==",
                    "value": '"MISMATCH"',
                    "format": red_bg,
                },
            )

    except Exception as e:
        print(f"Report generation failed: {e}")
