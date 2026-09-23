import concurrent.futures
import re
from pathlib import Path

import pandas as pd


from hyphlow import (
    common_utils,
    bio_io,
    manifest_logic_tab,
    report_builder,
    t1_st1_logic,
)

# ============================================================ constants
UNCHANGED = "UNCHANGED"
MODIFIED = "MODIFIED"
GENE_TAG_NOT_FOUND = "GENE_TAG_NOT_FOUND"

# ete3 writes branch support values into internal node names, so a label that is only a number is not a taxon name.

NUMERIC_LABEL = re.compile(r"^-?\d+(?:\.\d+)?$")

COLOR_BY_STATUS = {
    UNCHANGED: "green",
    MODIFIED: "orange",
    GENE_TAG_NOT_FOUND: "red",
}

# ============================================================= parsing


def is_accession_junk(token):
    t = token.upper()
    return (
        t in common_utils.NCBI_PREFIXES
        or token.isdigit()
        or bool(common_utils.ACCESSION_LIKE.match(t))
    )


def _gene_pattern(gene_name):
    if not gene_name:
        return None
    tokens = [t for t in re.split(r"[\s_]+", gene_name.strip()) if t]
    if not tokens or tokens[0].upper() == "UNKNOWN":
        return None
    body = "_".join(re.escape(t) for t in tokens)
    return re.compile(rf"(?:^|_){body}(?:_|$)", re.IGNORECASE)


def clean_species_label(text, gene_name, *, report=None):
    text = text.strip()

    # The gene name marks where the taxon ends. Taking the leading segment
    # assumes the species name comes first; labels that put the accession first
    # are left for manual correction.

    pat = _gene_pattern(gene_name)
    if pat:
        segs = [s.strip("_") for s in pat.split(text)]
        if len(segs) > 1:
            text = segs[0] or segs[1] or text
        elif report is not None:
            report["gene_tag_missing"] = True

    parts = [p for p in text.split("_") if p and not is_accession_junk(p)]
    if len(parts) < 2:
        return "_".join(parts)

    # Binomial nomenclature: genus then species. A thrid part counts as a
    # subspecific epithet only when it is entirely lowercase, following the
    # convention that subspecific names are not capitalized.
    species = parts[:2]
    if len(parts) >= 3 and parts[2].islower() and parts[2].isalpha():
        species.append(parts[2])
    return "_".join(species)


def clean_header_text(header, gene_name, *, report=None):
    result = clean_species_label(header.lstrip(">"), gene_name, report=report)
    return f">{result}" if header.startswith(">") else result


# =============================================================== paths


def get_results_path(kind="FASTA"):
    return common_utils.get_pipeline_path(
        t1_st1_logic.CURRENT_PROJECT_PATH, common_utils.RESULTS, kind
    )


def get_reports_path(kind="FASTA"):
    return common_utils.get_pipeline_path(
        t1_st1_logic.CURRENT_PROJECT_PATH, common_utils.REPORTS, kind
    )


# ============================================================= report


def _format_report(res_dict, rep_path, title, count_label, columns):
    mod = res_dict.get("modified_count", 0)
    miss = res_dict.get("tag_missing_count", 0)

    report_builder.build_report(
        rep_path,
        title=title,
        source=res_dict.get("file", "Unknown"),
        output=res_dict.get("out_name", "Unknown"),
        stats=[
            (count_label, res_dict.get("total", 0)),
            ("Unchanged Labels", res_dict.get("unchanged_count", 0), "green"),
            ("Modified Labels", mod, "orange" if mod else None),
            ("Gene Tag Not Found", miss, "red" if miss else None),
        ],
        rows=res_dict.get("details_data", []),
        columns=columns,
        color_column="Status",
        color_map=COLOR_BY_STATUS,
        widths={"A:C": 40},
    )


def generate_fasta_format_report(res_dict, rep_path):
    _format_report(
        res_dict,
        rep_path,
        title="FASTA Formatting",
        count_label="Total Sequences",
        columns=["Original Header", "Formatted Header", "Status"],
    )


def generate_nwk_format_report(res_dict, rep_path):
    _format_report(
        res_dict,
        rep_path,
        title="NWK Tree Formatting",
        count_label="Total Taxa in Tree",
        columns=["Original Taxon", "Formatted Taxon", "Status"],
    )


def process_fasta_worker(args):
    file_path, out_dir, rep_dir, base_name, gene_only = args
    path = Path(file_path)
    out_path, rep_path = _output_paths(base_name, "FASTA", ".fasta", out_dir, rep_dir)

    try:
        total = modified_count = unchanged_count = tag_missing_count = 0
        details_data = []
        lines = []

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.startswith(">"):
                    lines.append(line)
                    continue

                total += 1
                orig = line.strip().lstrip(">")

                info = {}
                new_line = clean_header_text(line, gene_only, report=info)
                new_head = new_line.strip().lstrip(">")
                lines.append(new_line + "\n")

                if info.get("gene_tag_missing"):
                    tag_missing_count += 1
                    status = GENE_TAG_NOT_FOUND
                elif orig != new_head:
                    modified_count += 1
                    status = MODIFIED
                else:
                    unchanged_count += 1
                    status = UNCHANGED
                details_data.append([orig, new_head, status])

        with open(out_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return {
            "file": path.name,
            "success": True,
            "out_name": out_path.name,
            "out_path": str(out_path),
            "src_path": str(path),
            "total": total,
            "modified_count": modified_count,
            "unchanged_count": unchanged_count,
            "tag_missing_count": tag_missing_count,
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
        tree, tree_format = bio_io.load_tree(path)

        total = modified_count = unchanged_count = tag_missing_count = 0
        details_data = []

        for node in tree.traverse():
            if not node.name or NUMERIC_LABEL.fullmatch(node.name):
                continue

            orig = node.name
            if node.is_leaf():
                total += 1

            info = {}
            new_head = clean_species_label(orig, gene_only, report=info)

            if info.get("gene_tag_missing"):
                tag_missing_count += 1
                status = GENE_TAG_NOT_FOUND
            elif orig != new_head:
                modified_count += 1
                status = MODIFIED
            else:
                unchanged_count += 1
                status = UNCHANGED

            node.name = new_head
            details_data.append([orig, new_head, status])

        # Write back in the format the file was read in, so internal node labels survive if they were there to begin with.
        tree.write(outfile=str(out_path), format=tree_format)

        return {
            "file": path.name,
            "success": True,
            "out_name": out_path.name,
            "out_path": str(out_path),
            "src_path": str(path),
            "total": total,
            "modified_count": modified_count,
            "unchanged_count": unchanged_count,
            "tag_missing_count": tag_missing_count,
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


def _run_pipeline(
    files, identity_dict, kind, worker, report_fn, stage, progress_cb=None
):
    out_dir = get_results_path(kind)
    rep_dir = get_reports_path(kind)
    if not out_dir or not rep_dir:
        return [], ""

    identity_dict = identity_dict or {}
    proj = t1_st1_logic.CURRENT_PROJECT_PATH

    tasks = []
    resolved = {}
    for fp in files:
        org, gene = manifest_logic_tab.resolve_identity(proj, fp, identity_dict.get(fp))
        # keyed by the same string the worker reports back as src_path
        resolved[str(Path(fp))] = (org, gene)
        tasks.append(
            (fp, out_dir, rep_dir, common_utils.make_base_name(org, gene), gene)
        )
    results = []
    last_rep_path = ""
    done = 0

    with concurrent.futures.ThreadPoolExecutor() as executor:
        for result in executor.map(worker, tasks):
            if result.get("success") and result.get("rep_path"):
                rep_path = result.pop("rep_path")
                report_fn(result, rep_path)
                last_rep_path = rep_path

            if result.get("success") and result.get("out_path"):
                src = result.get("src_path", "")
                org, gene = resolved.get(src, ("", ""))
                manifest_logic_tab.add_row(
                    proj, org, gene, "", stage, result["out_path"], src
                )
            results.append(result)
            done += 1
            if progress_cb:
                progress_cb(done, len(tasks))

    return results, str(last_rep_path)


def run_fasta_pipeline(
    fasta_files, gene_dict=None, identity_dict=None, progress_cb=None
):
    return _run_pipeline(
        fasta_files,
        identity_dict,
        "FASTA",
        process_fasta_worker,
        generate_fasta_format_report,
        "aln_fmt",
        progress_cb,
    )


def run_nwk_pipeline(file_paths, gene_dict=None, identity_dict=None, progress_cb=None):
    return _run_pipeline(
        file_paths,
        identity_dict,
        "NWK",
        process_nwk_worker,
        generate_nwk_format_report,
        "tree_fmt",
        progress_cb,
    )
