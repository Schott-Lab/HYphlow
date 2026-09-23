import concurrent.futures
from pathlib import Path


from hyphlow import (
    bio_io,
    common_utils,
    manifest_logic_tab,
    t1_st1_logic,
    report_builder,
)

# ============================================================ constants
RETAINED = "RETAINED"
PRUNED = "PRUNED"

# Not ERROR. t1_st1_logic.ERROR means the run failed; this means the master
# tree does not cover the taxon, which is a normal outcome.
MISSING_IN_TREE = "MISSING_IN_TREE"

COLOR_BY_STATUS = {
    RETAINED: "green",
    PRUNED: "orange",
    MISSING_IN_TREE: "red",
}

MIN_TAXA = 3


def get_results_path():
    return common_utils.get_pipeline_path(
        t1_st1_logic.CURRENT_PROJECT_PATH, common_utils.RESULTS, "NWK"
    )


def get_reports_path():
    return common_utils.get_pipeline_path(
        t1_st1_logic.CURRENT_PROJECT_PATH, common_utils.REPORTS, "NWK"
    )


def generate_pruning_report(res_dict, rep_path):
    retained = res_dict.get("retained_count", 0)
    pruned = res_dict.get("pruned_count", 0)
    missing = res_dict.get("missing_count", 0)
    try:
        report_builder.build_report(
            rep_path,
            title="Tree Pruning",
            source=res_dict.get("fasta_name", "Unknown"),
            output=res_dict.get("out_name", "Unknown"),
            stats=[
                ("Retained Taxa", retained, "green" if retained else None),
                ("Pruned (Not in FASTA)", pruned, "orange" if pruned else None),
                ("Missing (Not in Tree)", missing, "red" if missing else None),
            ],
            rows=res_dict.get("details_data", []),
            columns=["Taxon", "Action", "Status"],
            color_column="Status",
            color_map=COLOR_BY_STATUS,
            widths={"A:C": 30},
        )
    except Exception as e:
        raise RuntimeError(
            f"Report generation failed (Check if file is open): {e}"
        ) from e


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
        tree, orig_format = bio_io.load_tree(n_path)
        fasta_taxa = bio_io.read_fasta_taxa(f_path)

        tree_taxa_map = {
            common_utils.to_label(leaf.name): leaf.name for leaf in tree.get_leaves()
        }
        tree_taxa = set(tree_taxa_map.keys())

        common_taxa = fasta_taxa.intersection(tree_taxa)
        missing_in_fasta = tree_taxa - fasta_taxa
        missing_in_tree = fasta_taxa - tree_taxa

        details_data = []
        for t in common_taxa:
            details_data.append([t, "Retained", RETAINED])
        for t in missing_in_fasta:
            details_data.append([t, "Pruned (Not in FASTA)", PRUNED])
        for t in missing_in_tree:
            details_data.append([t, "Missing (Not in Tree)", MISSING_IN_TREE])

        if len(common_taxa) < MIN_TAXA:
            return {
                "file": f_path.name,
                "success": False,
                "error": (
                    f"Insufficient overlapping taxa ({len(common_taxa)}). "
                    f"Minimum {MIN_TAXA} required to form a tree."
                ),
                "rep_path": rep_path,
                "fasta_name": f_path.name,
                "out_name": "Failed",
                "retained_count": len(common_taxa),
                "pruned_count": len(missing_in_fasta),
                "missing_count": len(missing_in_tree),
                "details_data": details_data,
                "has_mismatch": True,
            }

        prune_targets = [tree_taxa_map[t] for t in common_taxa]
        tree.prune(prune_targets, preserve_branch_length=True)
        tree.write(outfile=str(out_path), format=orig_format)

        return {
            "file": f_path.name,
            "success": True,
            "has_mismatch": bool(missing_in_tree),
            "out_name": out_path.name,
            "out_path": str(out_path),
            "src_path": str(f_path),
            "fasta_name": f_path.name,
            "retained_count": len(common_taxa),
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


def run_pruning_pipeline(fasta_files, nwk_files, identity_dict=None, progress_cb=None):
    out_dir = get_results_path()
    rep_dir = get_reports_path()
    if not out_dir or not rep_dir or not nwk_files:
        return [], ""

    results = []
    last_rep_path = ""
    done = 0

    nwk_target = nwk_files[0]
    identity_dict = identity_dict or {}
    proj = t1_st1_logic.CURRENT_PROJECT_PATH
    tasks = []
    resolved = {}
    for fp in fasta_files:
        typed = identity_dict.get(fp)
        org, gene = manifest_logic_tab.resolve_identity(proj, fp, typed)
        # keyed by the same string the worker reports back as src_path
        resolved[str(Path(fp))] = (org, gene)
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
                manifest_logic_tab.add_row(
                    proj, org, gene, "", "prn", result["out_path"], src
                )
            results.append(result)
            done += 1
            if progress_cb:
                progress_cb(done, len(tasks))

    return results, str(last_rep_path)
