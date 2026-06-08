import os
import sys
import re
import concurrent.futures
from pathlib import Path
from ete3 import Tree
import pandas as pd
import datetime

from hyphlow import common_utils
from hyphlow import t1_st1_logic

try:
    base = Path(sys._MEIPASS)
except Exception:
    base = Path(os.path.abspath("."))

CURRENT_PROJECT_PATH = base

NCBI_PREFIXES = {"XM", "NM", "NP", "XP", "NC", "NG", "XR", "NR"}


def is_accession_junk(token: str) -> bool:
    t_upper = token.upper()
    if t_upper in NCBI_PREFIXES or token.isdigit():
        return True
    if re.match(r"^[A-Z]{1,2}\d{4,}$", t_upper):
        return True
    return False


def extract_valid_tokens(text: str) -> list[str]:
    parts = text.split("_")
    return [p for p in parts if not is_accession_junk(p)]


def clean_node_name(node_name: str, gene_name: str) -> str:
    text = node_name.strip()

    if gene_name and gene_name != "UNKNOWN":
        pattern = re.compile(re.escape(gene_name), re.IGNORECASE)
        splits = pattern.split(text)
        if len(splits) > 1:
            text = splits[0].strip("_")

    valid_parts = extract_valid_tokens(text)

    if len(valid_parts) < 2:
        return "_".join(valid_parts)

    species_parts = [valid_parts[0], valid_parts[1]]
    if len(valid_parts) >= 3:
        third_part = valid_parts[2]
        if third_part.islower() and third_part.isalpha():
            species_parts.append(third_part)

    return "_".join(species_parts)


def get_results_path():
    return common_utils.get_pipeline_path(
        t1_st1_logic.CURRENT_PROJECT_PATH, "Results", "NWK"
    )


def get_reports_path():
    return common_utils.get_pipeline_path(
        t1_st1_logic.CURRENT_PROJECT_PATH, "Reports", "NWK"
    )


def generate_nwk_format_report(res_dict, rep_path):
    try:
        with pd.ExcelWriter(rep_path, engine="xlsxwriter") as writer:
            workbook = writer.book
            bold_fmt = workbook.add_format({"bold": True})
            green_bg = workbook.add_format(
                {"bg_color": "#EBF9EE", "font_color": "#16A34A", "bold": True}
            )
            orange_bg = workbook.add_format(
                {"bg_color": "#FFF9E5", "font_color": "#FF9500", "bold": True}
            )

            ws_sum = workbook.add_worksheet("Summary")
            ws_sum.set_column("A:B", 30)

            ws_sum.write("A1", "HYphlow NWK Tree Formatting Report", bold_fmt)
            ws_sum.write("A2", "Date & Time", bold_fmt)
            ws_sum.write("B2", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            ws_sum.write("A3", "Original File", bold_fmt)
            ws_sum.write("B3", res_dict.get("file", "Unknown"))
            ws_sum.write("A4", "Formatted Output", bold_fmt)
            ws_sum.write("B4", res_dict.get("out_name", "Unknown"))

            ws_sum.write("A6", "--- Statistics ---", bold_fmt)
            ws_sum.write("A7", "Total Taxa in Tree", bold_fmt)
            ws_sum.write("B7", res_dict.get("total_taxa", 0))
            ws_sum.write("A8", "Perfect Matches", bold_fmt)
            ws_sum.write("B8", res_dict.get("perfect_count", 0), green_bg)
            ws_sum.write("A9", "Modified Taxa Names", bold_fmt)
            mod_count = res_dict.get("modified_count", 0)
            ws_sum.write("B9", mod_count, orange_bg if mod_count > 0 else None)

            details_data = res_dict.get("details_data", [])
            df = pd.DataFrame(
                details_data, columns=["Original Taxon", "Formatted Taxon", "Status"]
            )
            df.to_excel(writer, sheet_name="Detailed Report", index=False)

            ws_det = writer.sheets["Detailed Report"]
            ws_det.set_column("A:C", 40)

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

    except Exception as e:
        print(f"Report generation failed: {e}")


def process_nwk_worker(args):
    file_path, out_dir, rep_dir, user_gene_name = args
    path = Path(file_path)

    new_nwk_name_str, _ = common_utils.generate_smart_filename(
        user_gene_name, "NWK", out_dir, ".nwk", is_report=False
    )
    new_rep_name_str, _ = common_utils.generate_smart_filename(
        user_gene_name, "NWK", rep_dir, ".xlsx", is_report=True
    )

    out_path = Path(new_nwk_name_str)
    rep_path = Path(new_rep_name_str)

    try:
        try:
            tree = Tree(str(path), format=1)
        except Exception:
            tree = Tree(str(path))

        total_taxa = 0
        modified_count = 0
        perfect_count = 0
        details_data = []

        for node in tree.traverse():
            if node.name:
                orig = node.name
                if orig.replace(".", "", 1).isdigit():
                    continue

                if node.is_leaf():
                    total_taxa += 1

                new_head = clean_node_name(orig, user_gene_name)
                if orig != new_head:
                    node.name = new_head
                    details_data.append([orig, new_head, "MODIFIED"])
                    modified_count += 1
                else:
                    perfect_count += 1
                    details_data.append([orig, new_head, "PERFECT"])

        tree.write(outfile=str(out_path), format=1)

        return {
            "file": path.name,
            "success": True,
            "out_name": out_path.name,
            "total_taxa": total_taxa,
            "modified_count": modified_count,
            "perfect_count": perfect_count,
            "details_data": details_data,
            "rep_path": rep_path,
        }
    except Exception as e:
        return {"file": path.name, "success": False, "error": str(e), "rep_path": None}


def run_nwk_pipeline(file_paths, gene_dict):
    out_dir = get_results_path()
    rep_dir = get_reports_path()
    if not out_dir or not rep_dir:
        return [], ""

    results = []
    last_rep_path = ""

    tasks = [
        (fp, out_dir, rep_dir, gene_dict.get(fp, Path(fp).stem)) for fp in file_paths
    ]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        for result in executor.map(process_nwk_worker, tasks):
            if result.get("success") and result.get("rep_path"):
                rep_path = result.pop("rep_path")
                generate_nwk_format_report(result, rep_path)
                last_rep_path = rep_path
            results.append(result)

    return results, str(last_rep_path)
