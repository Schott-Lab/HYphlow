import concurrent.futures
from pathlib import Path
from ete3 import Tree
import pandas as pd
import datetime

from hyphlow import common_utils
from hyphlow import t1_st1_logic
from hyphlow import manifest_logic_tab



def get_results_path():
    return common_utils.get_pipeline_path(
        t1_st1_logic.CURRENT_PROJECT_PATH, "Results", "NWK"
    )


def get_reports_path():
    return common_utils.get_pipeline_path(
        t1_st1_logic.CURRENT_PROJECT_PATH, "Reports", "NWK"
    )


def _get_fasta_taxa(f_path):
    taxa = set()
    try:
        with open(f_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(">"):
                    taxa.add(line.strip().lstrip(">").replace(" ", "_"))
    except Exception as e:
        raise RuntimeError(f"Failed to read FASTA file: {e}")
    return taxa


def generate_pruning_report(res_dict, rep_path):
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
            ws_sum.set_column("A:B", 30)

            ws_sum.write("A1", "HYphlow Tree Pruning Report", bold_fmt)
            ws_sum.write("A2", "Date & Time", bold_fmt)
            ws_sum.write("B2", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            ws_sum.write("A3", "Source FASTA", bold_fmt)
            ws_sum.write("B3", res_dict.get("fasta_name", "Unknown"))
            ws_sum.write("A4", "Pruned Tree Output", bold_fmt)
            ws_sum.write("B4", res_dict.get("out_name", "Unknown"))

            ws_sum.write("A6", "--- Statistics ---", bold_fmt)
            ws_sum.write("A7", "Perfectly Retained", bold_fmt)
            ws_sum.write("B7", res_dict.get("perfect_count", 0), green_bg)
            ws_sum.write("A8", "Pruned (Not in FASTA)", bold_fmt)
            ws_sum.write("B8", res_dict.get("pruned_count", 0), orange_bg)
            ws_sum.write("A9", "Missing (Not in Tree)", bold_fmt)

            missing_count = res_dict.get("missing_count", 0)
            ws_sum.write("B9", missing_count, red_bg if missing_count > 0 else None)

            details_data = res_dict.get("details_data", [])
            if details_data:
                df = pd.DataFrame(details_data, columns=["Taxon", "Action", "Status"])
                df.to_excel(writer, sheet_name="Detailed Report", index=False)

                ws_det = writer.sheets["Detailed Report"]
                ws_det.set_column("A:C", 30)

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
                        "value": '"PRUNED"',
                        "format": orange_bg,
                    },
                )
                ws_det.conditional_format(
                    row_range,
                    {
                        "type": "cell",
                        "criteria": "==",
                        "value": '"ERROR"',
                        "format": red_bg,
                    },
                )

    except Exception as e:
        raise RuntimeError(f"Report generation failed (Check if file is open): {e}")


def process_pruning_worker(args):
    fasta_path, nwk_path, out_dir, rep_dir, user_gene_name = args
    f_path = Path(fasta_path)
    n_path = Path(nwk_path)

    new_nwk_name_str, _ = common_utils.generate_smart_filename(
        user_gene_name, "PRN", out_dir, ".nwk", is_report=False
    )
    new_rep_name_str, _ = common_utils.generate_smart_filename(
        user_gene_name, "PRN", rep_dir, ".xlsx", is_report=True
    )

    out_path = Path(new_nwk_name_str)
    rep_path = Path(new_rep_name_str)

    try:
        try:
            tree = Tree(str(n_path), format=1)
            orig_format = 1
        except Exception:
            tree = Tree(str(n_path))
            orig_format = 0

        fasta_taxa = _get_fasta_taxa(f_path)

        tree_taxa_map = {
            leaf.name.replace(" ", "_"): leaf.name for leaf in tree.get_leaves()
        }
        tree_taxa = set(tree_taxa_map.keys())

        common_taxa = fasta_taxa.intersection(tree_taxa)
        missing_in_fasta = tree_taxa - fasta_taxa
        missing_in_tree = fasta_taxa - tree_taxa

        details_data = []
        for t in common_taxa:
            details_data.append([t, "Retained", "PERFECT"])
        for t in missing_in_fasta:
            details_data.append([t, "Pruned (Not in FASTA)", "PRUNED"])
        for t in missing_in_tree:
            details_data.append([t, "Missing (Not in Tree)", "ERROR"])

        has_mismatch = len(missing_in_tree) > 0
        out_name_str = "Failed (No Overlap)"

        if len(common_taxa) < 3:
            return {
                "file": f_path.name,
                "success": False,
                "error": f"Insufficient overlapping taxa ({len(common_taxa)}). Minimum 3 required to form a tree.",
                "rep_path": rep_path,
                "fasta_name": f_path.name,
                "out_name": "Failed",
                "perfect_count": len(common_taxa),
                "pruned_count": len(missing_in_fasta),
                "missing_count": len(missing_in_tree),
                "details_data": details_data,
                "has_mismatch": True,
            }

        prune_targets = [tree_taxa_map[t] for t in common_taxa]
        tree.prune(prune_targets, preserve_branch_length=True)
        tree.write(outfile=str(out_path), format=orig_format)
        out_name_str = out_path.name

        warning_msg = ""
        if missing_in_tree:
            warning_msg = f"Target FASTA contains taxa missing in Master Tree: {', '.join(list(missing_in_tree)[:3])}"
            if len(missing_in_tree) > 3:
                warning_msg += "..."

        return {
            "file": f_path.name,
            "success": True,
            "warning": warning_msg,
            "has_mismatch": has_mismatch,
            "out_name": out_name_str,
            "out_path": str(out_path),
            "src_path": str(f_path),
            "fasta_name": f_path.name,
            "perfect_count": len(common_taxa),
            "pruned_count": len(missing_in_fasta),
            "missing_count": len(missing_in_tree),
            "details_data": details_data,
            "rep_path": rep_path,
        }
    except Exception as e:
        return {
            "file": f_path.name,
            "success": False,
            "error": str(e),
            "has_mismatch": True,
            "rep_path": None,
        }


def run_pruning_pipeline(fasta_files, nwk_files, gene_dict, identity_dict=None):
    out_dir = get_results_path()
    rep_dir = get_reports_path()
    if not out_dir or not rep_dir or not nwk_files:
        return [], ""

    results = []
    last_rep_path = ""

    nwk_target = nwk_files[0]
    identity_dict = identity_dict or {}
    proj = t1_st1_logic.CURRENT_PROJECT_PATH
    tasks = []
    resolved = {}
    for fp in fasta_files:
        typed = identity_dict.get(fp)
        org, gene = manifest_logic_tab.resolve_identity(proj, fp, typed)
        resolved[fp] = (org, gene)
        tasks.append(
            (fp, nwk_target, out_dir, rep_dir, common_utils.make_base_name(org, gene))
        )

    with concurrent.futures.ThreadPoolExecutor() as executor:
        for result in executor.map(process_pruning_worker, tasks):
            if result.get("rep_path"):
                rep_path = result.pop("rep_path")
                try:
                    generate_pruning_report(result, rep_path)
                    last_rep_path = rep_path
                except Exception as e:
                    result["success"] = False
                    result["has_mismatch"] = True
                    result["error"] = str(e)
            if result.get("success") and result.get("out_path"):
                src = result.get("src_path", "")
                org, gene = resolved.get(src, ("", ""))
                try:
                    manifest_logic_tab.add_row(
                        t1_st1_logic.CURRENT_PROJECT_PATH,
                        org,
                        gene,
                        "",
                        "prn",
                        result["out_path"],
                        src,
                    )
                except Exception as e:
                    print("manifest write failed:", e)
            results.append(result)

    return results, str(last_rep_path)
