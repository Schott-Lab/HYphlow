import re
import concurrent.futures
from pathlib import Path
from ete3 import Tree
import pandas as pd
import datetime

from hyphlow import common_utils
from hyphlow import t1_st1_logic
from hyphlow import manifest_logic_tab

_NUMERIC_LABEL = re.compile(r"^-?\d+(?:\.\d+)?$")


def is_accession_junk(token: str) -> bool:
    t = token.upper()
    return (
        t in common_utils.NCBI_PREFIXES
        or token.isdigit()
        or bool(common_utils.ACCESSION_LIKE.match(t))
    )


def _gene_pattern(gene_name: str):

    if not gene_name:
        return None
    tokens = [t for t in re.split(r"[\s_]+", gene_name.strip()) if t]
    if not tokens or tokens[0].upper() == "UNKNOWN":
        return None
    body = "_".join(re.escape(t) for t in tokens)
    return re.compile(rf"(?:^|_){body}(?:_|$)", re.IGNORECASE)


def extract_valid_tokens(text: str) -> list[str]:
    return [p for p in text.split("_") if p and not is_accession_junk(p)]


def clean_species_label(text: str, gene_name: str, *, report=None) -> str:
    text = text.strip()

    pat = _gene_pattern(gene_name)
    if pat:
        segs = [s.strip("_") for s in pat.split(text)]
        if len(segs) > 1:
            text = segs[0] or segs[1] or text
        elif report is not None:
            report["gene_tag_missing"] = True

    parts = extract_valid_tokens(text)
    if len(parts) < 2:
        return "_".join(parts)

    species = parts[:2]
    if len(parts) >= 3 and parts[2].islower() and parts[2].isalpha():
        species.append(parts[2])
    return "_".join(species)


def clean_header_text(header: str, gene_name: str, *, report=None) -> str:
    result = clean_species_label(header.lstrip(">"), gene_name, report=report)
    return f">{result}" if header.startswith(">") else result


def clean_node_name(node_name: str, gene_name: str, *, report=None) -> str:
    return clean_species_label(node_name, gene_name, report=report)


def get_results_path(kind="FASTA"):
    return common_utils.get_pipeline_path(
        t1_st1_logic.CURRENT_PROJECT_PATH, "Results", kind
    )


def get_reports_path(kind="FASTA"):
    return common_utils.get_pipeline_path(
        t1_st1_logic.CURRENT_PROJECT_PATH, "Reports", kind
    )


def generate_fasta_format_report(res_dict, rep_path):
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
            red_bg = workbook.add_format(
                {"bg_color": "#FFECEB", "font_color": "#FF3B30", "bold": True}
            )

            ws_sum = workbook.add_worksheet("Summary")
            ws_sum.set_column("A:B", 30)

            ws_sum.write("A1", "HYphlow FASTA Formatting Report", bold_fmt)
            ws_sum.write("A2", "Date & Time", bold_fmt)
            ws_sum.write("B2", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            ws_sum.write("A3", "Original File", bold_fmt)
            ws_sum.write("B3", res_dict.get("file", "Unknown"))
            ws_sum.write("A4", "Formatted Output", bold_fmt)
            ws_sum.write("B4", res_dict.get("out_name", "Unknown"))

            ws_sum.write("A6", "--- Statistics ---", bold_fmt)
            ws_sum.write("A7", "Total Sequences", bold_fmt)
            ws_sum.write("B7", res_dict.get("total_seqs", 0))
            ws_sum.write("A8", "Perfect Matches", bold_fmt)
            ws_sum.write("B8", res_dict.get("perfect_count", 0), green_bg)
            ws_sum.write("A9", "Modified Headers", bold_fmt)
            mod_count = res_dict.get("modified_count", 0)
            ws_sum.write("B9", mod_count, orange_bg if mod_count > 0 else None)
            ws_sum.write("A10", "Gene Tag Not Found", bold_fmt)
            miss = res_dict.get("tag_missing_count", 0)
            ws_sum.write("B10", miss, red_bg if miss > 0 else None)

            details_data = res_dict.get("details_data", [])
            df = pd.DataFrame(
                details_data, columns=["Original Header", "Formatted Header", "Status"]
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
            ws_det.conditional_format(
                row_range,
                {
                    "type": "cell",
                    "criteria": "==",
                    "value": '"GENE_TAG_NOT_FOUND"',
                    "format": red_bg,
                },
            )

    except Exception as e:
        print(f"Report generation failed: {e}")


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
            ws_sum.write("A10", "Gene Tag Not Found", bold_fmt)
            miss = res_dict.get("tag_missing_count", 0)
            ws_sum.write("B10", miss, red_bg if miss > 0 else None)

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


def process_fasta_worker(args):
    file_path, out_dir, rep_dir, base_name, gene_only = args
    path = Path(file_path)

    out_path, rep_path = _output_paths(base_name, "FASTA", ".fasta", out_dir, rep_dir)

    try:
        total_seqs = modified_count = perfect_count = tag_missing_count = 0
        details_data = []
        lines = []

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.startswith(">"):
                    lines.append(line)
                    continue

                total_seqs += 1
                orig = line.strip().lstrip(">")

                info = {}
                new_line = clean_header_text(line, gene_only, report=info)
                new_head = new_line.strip().lstrip(">")
                lines.append(new_line + "\n")

                if info.get("gene_tag_missing"):
                    tag_missing_count += 1
                    status = "GENE_TAG_NOT_FOUND"
                elif orig != new_head:
                    modified_count += 1
                    status = "MODIFIED"
                else:
                    perfect_count += 1
                    status = "PERFECT"
                details_data.append([orig, new_head, status])

        with open(out_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return {
            "file": path.name,
            "success": True,
            "out_name": out_path.name,
            "out_path": str(out_path),
            "src_path": str(path),
            "total_seqs": total_seqs,
            "modified_count": modified_count,
            "perfect_count": perfect_count,
            "details_data": details_data,
            "rep_path": rep_path,
        }
    except Exception as e:
        return {"file": path.name, "success": False, "error": str(e), "rep_path": None}


def process_nwk_worker(args):
    file_path, out_dir, rep_dir, base_name, gene_only = args
    path = Path(file_path)

    out_path, rep_path = _output_paths(base_name, "NWK", ".nwk", out_dir, rep_dir)

    try:
        try:
            tree = Tree(str(path), format=1)
        except Exception:
            tree = Tree(str(path))

        total_taxa = modified_count = perfect_count = 0
        details_data = []

        for node in tree.traverse():
            if not node.name:
                continue

            orig = node.name
            if _NUMERIC_LABEL.fullmatch(orig):
                continue

            if node.is_leaf():
                total_taxa += 1

            new_head = clean_node_name(orig, gene_only)
            if orig != new_head:
                node.name = new_head
                modified_count += 1
                details_data.append([orig, new_head, "MODIFIED"])
            else:
                perfect_count += 1
                details_data.append([orig, new_head, "PERFECT"])

        tree.write(outfile=str(out_path), format=1)

        return {
            "file": path.name,
            "success": True,
            "out_name": out_path.name,
            "out_path": str(out_path),
            "src_path": str(path),
            "total_taxa": total_taxa,
            "modified_count": modified_count,
            "perfect_count": perfect_count,
            "details_data": details_data,
            "rep_path": rep_path,
        }
    except Exception as e:
        return {"file": path.name, "success": False, "error": str(e), "rep_path": None}


def _output_paths(base_name, kind, ext, out_dir, rep_dir):
    out_name, _ = common_utils.generate_smart_filename(
        base_name, kind, out_dir, ext, is_report=False
    )
    rep_name, _ = common_utils.generate_smart_filename(
        base_name, kind, rep_dir, ".xlsx", is_report=True
    )
    return Path(out_name), Path(rep_name)


def _run_pipeline(files, identity_dict, kind, worker, report_fn, stage):
    out_dir = get_results_path(kind)
    rep_dir = get_reports_path(kind)
    if not out_dir or not rep_dir:
        return [], ""

    results = []
    last_rep_path = ""

    identity_dict = identity_dict or {}
    proj = t1_st1_logic.CURRENT_PROJECT_PATH

    def _norm(p):
        return str(Path(p))

    typed = {_norm(k): v for k, v in identity_dict.items()}

    tasks = []
    resolved = {}
    for fp in files:
        org, gene = manifest_logic_tab.resolve_identity(proj, fp, identity_dict.get(fp))
        resolved[_norm(fp)] = (org, gene)
        tasks.append(
            (fp, out_dir, rep_dir, common_utils.make_base_name(org, gene), gene)
        )

    with concurrent.futures.ThreadPoolExecutor() as executor:
        for result in executor.map(worker, tasks):
            if result.get("success") and result.get("rep_path"):
                rep_path = result.pop("rep_path")
                report_fn(result, rep_path)
                last_rep_path = rep_path
            if result.get("success") and result.get("out_path"):
                src = result.get("src_path", "")
                org, gene = typed.get(src) or resolved.get(src, ("", ""))
                try:
                    manifest_logic_tab.add_row(
                        proj, org, gene, "", stage, result["out_path"], src
                    )
                except Exception as e:
                    print("manifest write failed:", e)
            results.append(result)

    return results, str(last_rep_path)


def run_fasta_pipeline(fasta_files, gene_dict=None, identity_dict=None):
    return _run_pipeline(
        fasta_files,
        identity_dict,
        "FASTA",
        process_fasta_worker,
        generate_fasta_format_report,
        "aln_fmt",
    )


def run_nwk_pipeline(file_paths, gene_dict=None, identity_dict=None):
    return _run_pipeline(
        file_paths,
        identity_dict,
        "NWK",
        process_nwk_worker,
        generate_nwk_format_report,
        "tree_fmt",
    )


if __name__ == "__main__":
    assert (
        clean_species_label("Homo_sapiens_XM_123456_BRCA1", "BRCA1") == "Homo_sapiens"
    )
    assert clean_species_label("Canis_lupus_familiaris", "") == "Canis_lupus_familiaris"
    assert clean_species_label("Canis_lupus_Familiaris", "") == "Canis_lupus"
    assert clean_header_text(">Mus_musculus_NM_9999", "") == ">Mus_musculus"
    assert clean_node_name("Mus_musculus_NM_9999", "") == "Mus_musculus"
    assert (
        is_accession_junk("XM")
        and is_accession_junk("123")
        and is_accession_junk("AB1234")
    )
    assert not is_accession_junk("sapiens")
    print("ok")
