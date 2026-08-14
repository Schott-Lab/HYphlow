import re
import zipfile
import subprocess
import random
from pathlib import Path
from ete3 import Tree
from hyphlow import common_utils


def standardize_filename(filename):
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", filename)
    return re.sub(r"_+", "_", safe_name).strip("_")


def extract_base_name(filename):
    parts = filename.split("_")
    return parts[0] if parts else filename


def _gene_from_stem(stem):
    """Pull the gene token out of a filename, or "" if none is identifiable.

    Uses the same rules as common_utils.detect_gene_from_file but looks only at
    the name, never opening the file.
    """
    for token in re.split(r"[^A-Za-z0-9]+", stem):
        if common_utils._is_gene_like(token):
            return token.upper()
    return ""


# Values below match the Datamonkey defaults for each analysis. They are stated
# explicitly, even where they equal the HyPhy default, so a HyPhy version change
# cannot silently alter results.
MODEL_SPECS = {
    "busted": {
        "subcommand": "busted",
        "cores": 2,
        "requires_tags": False,
        "fixed": {
            "code": "Universal",
            "srv": "Yes",
            "error-sink": "No",
            "multiple-hits": "None",
            "kill-zero-lengths": "No",
        },
        "tag_args": {"branches": "FG"},
    },
    "relax": {
        "subcommand": "relax",
        "cores": 2,
        "requires_tags": True,
        "fixed": {
            "code": "Universal",
            "srv": "No",
            "models": "All",
            "multiple-hits": "None",
            "kill-zero-lengths": "No",
        },
        # RELAX picks the reference set automatically from unlabelled branches
        # when only --test is given.
        "tag_args": {"test": "FG"},
    },
    "absrel": {
        "subcommand": "absrel",
        "cores": 2,
        "requires_tags": False,
        "fixed": {
            "code": "Universal",
            "srv": "No",
            "multiple-hits": "None",
            "kill-zero-lengths": "No",
        },
        "tag_args": {"branches": "FG"},
    },
    "fel": {
        "subcommand": "fel",
        "cores": 2,
        "requires_tags": False,
        "fixed": {
            "code": "Universal",
            "srv": "Yes",
            "multiple-hits": "None",
            "pvalue": "0.1",
            "ci": "No",
            "resample": "0",
            "kill-zero-lengths": "No",
        },
        "tag_args": {"branches": "FG"},
    },
    "meme": {
        "subcommand": "meme",
        "cores": 2,
        "requires_tags": False,
        "fixed": {
            "code": "Universal",
            "rates": "2",
            "multiple-hits": "None",
            "impute-states": "No",
            "pvalue": "0.1",
            "resample": "0",
            "kill-zero-lengths": "No",
        },
        "tag_args": {"branches": "FG"},
    },
    # FUBAR has no --branches option, so a tagged tree cannot narrow it; it is a
    # whole-alignment site-wise method and always runs globally. chains and
    # chain-length are MCMC-only and the default inference method is
    # variational Bayes, so neither is set here.
    "fubar": {
        "subcommand": "fubar",
        "cores": 2,
        "requires_tags": False,
        "cache_arg": "cache",
        "fixed": {
            "code": "Universal",
            "grid": "20",
            "concentration_parameter": "0.5",
            "kill-zero-lengths": "No",
        },
        "tag_args": {},
    },
}


def build_command(model, fasta, tree, output, cores, has_fg, seed=None, tolerant=False):
    """Assemble one HyPhy invocation from MODEL_SPECS.

    ENV= must come after the subcommand: HyPhy reads the first positional
    argument as the analysis name, so putting ENV= first makes it treat the
    analysis name as a batch file path.
    """
    spec = MODEL_SPECS.get(model)
    if spec is None:
        return None

    parts = ['"$HYPHY_EXEC"', spec["subcommand"]]
    if tolerant:
        parts.append("ENV=TOLERATE_NUMERICAL_ERRORS=1")
    parts += [f'--alignment "{fasta}"', f'--tree "{tree}"']

    for key, value in spec["fixed"].items():
        parts.append(f"--{key} {value}")
    if has_fg:
        for key, value in spec["tag_args"].items():
            parts.append(f"--{key} {value}")

    parts.append(f"--CPU {cores}")
    if seed:
        parts.append(f"--seed {seed}")
    # FUBAR caches its grid next to the alignment by default, so parallel jobs
    # sharing one alignment would race on the same file. Key it to the output.
    if spec.get("cache_arg"):
        parts.append(f'--{spec["cache_arg"]} "{output}.cache"')
    parts.append(f'--output "{output}"')
    return " ".join(parts)


def _read_fasta(path):
    """Return {name: sequence}. Names are read the way HyPhy reads them."""
    seqs, name = {}, None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith(">"):
                name = line.strip()[1:].strip().replace("'", "").replace('"', "")
                seqs[name] = []
            elif name is not None:
                seqs[name].append(line.strip())
    return {k: "".join(v).upper() for k, v in seqs.items()}


def _duplicate_groups(seqs):
    """Names sharing an identical sequence.

    HyPhy warns about these and carries on. Identical sequences add no
    information and force the branch between them to zero length, which is
    where numerical trouble starts.
    """
    by_seq = {}
    for name, s in seqs.items():
        if s:
            by_seq.setdefault(s, []).append(name)
    return [sorted(g) for g in by_seq.values() if len(g) > 1]


def pre_execution_validation(fasta_path, nwk_path):
    try:
        seqs = _read_fasta(fasta_path)
        fasta_ids = set(seqs)

        if not fasta_ids:
            return False, False, "Empty FASTA file."

        dups = _duplicate_groups(seqs)
        dup_note = ""
        if dups:
            shown = " / ".join(", ".join(g) for g in dups[:2])
            dup_note = " Duplicate sequence(s): %s%s." % (
                shown,
                " ..." if len(dups) > 2 else "",
            )

        try:
            tree = Tree(nwk_path, format=1)
        except:
            try:
                tree = Tree(nwk_path)
            except Exception as e:
                return False, False, f"Tree parsing error: {str(e)}"

        tree_tips = set()
        has_fg = False

        for node in tree.traverse():
            name_str = str(node.name)
            if "{FG}" in name_str:
                has_fg = True
            if node.is_leaf():
                clean_name = (
                    name_str.replace("{FG}", "")
                    .replace("'", "")
                    .replace('"', "")
                    .strip()
                )
                if clean_name:
                    tree_tips.add(clean_name)

        if fasta_ids == tree_tips:
            return True, has_fg, ("Perfect Match" + dup_note).strip()

        missing_in_fasta = sorted(list(tree_tips - fasta_ids))
        missing_in_tree = sorted(list(fasta_ids - tree_tips))

        error_msg = "Mismatch:"
        if missing_in_fasta:
            error_msg += f" Tree has extra ({missing_in_fasta[0]}...). "
        if missing_in_tree:
            error_msg += f" FASTA has extra ({missing_in_tree[0]}...)."

        return False, has_fg, (error_msg + dup_note).strip()

    except Exception as e:
        return False, False, f"Error: {str(e)}"


def get_matched_pairs(fasta_paths, nwk_paths):
    matched_dict = {}
    nwk_dict_paths = {
        standardize_filename(Path(f).stem).lower(): str(f) for f in nwk_paths
    }

    for fasta in fasta_paths:
        f_path = Path(fasta)
        if not str(f_path).lower().endswith((".fasta", ".fas", ".fa")):
            continue

        f_stem = standardize_filename(f_path.stem).lower()
        f_gene = _gene_from_stem(f_path.stem)
        matched_trees = []

        for n_stem, nwk_path_str in nwk_dict_paths.items():
            n_gene = _gene_from_stem(Path(nwk_path_str).stem)
            if f_gene and n_gene and f_gene != n_gene:
                continue
            # Same gene is the pairing rule. Fall back to filename overlap only
            # when the gene cannot be read from one of the names.
            if f_gene and n_gene:
                if f_gene != n_gene:
                    continue
            elif not ((f_stem in n_stem) or (n_stem in f_stem)):
                continue

            is_valid, has_fg, error_msg = pre_execution_validation(
                str(f_path), nwk_path_str
            )

            matched_trees.append(
                {
                    "nwk_path": nwk_path_str,
                    "nwk_name": Path(nwk_path_str).stem,
                    "is_valid": is_valid,
                    "has_fg": has_fg,
                    "error_msg": error_msg,
                }
            )

        if matched_trees:
            matched_dict[f_stem] = {"fasta_path": str(f_path), "trees": matched_trees}

    return matched_dict


def prep_parallel_tasks(job_list, total_threads, enable_triplicate=False, min_cores=2):
    tasks = []
    heavy_models = ["relax", "absrel", "busted"]

    for i, job in enumerate(job_list):
        f_name = Path(job["fasta"]).name
        t_name = Path(job["tree"]).name
        model = job["model"]
        runs = 3 if enable_triplicate else 1

        for run_idx in range(1, runs + 1):
            suffix = f"_run{run_idx}" if enable_triplicate else ""
            task_key = f"{f_name}==={t_name}==={model.upper()}==={i}{suffix}"
            seed_val = random.randint(10000, 99999) if enable_triplicate else None

            tasks.append(
                {
                    "job": job,
                    "model": model,
                    "key": task_key,
                    "f_name": f_name,
                    "t_name": t_name,
                    "run_suffix": suffix,
                    "seed": seed_val,
                }
            )

    # Measured on a 30-taxon, 354-codon BUSTED run: 1 CPU 636 s, 2 CPU 490 s
    # (65% efficient), 4 CPU 311 s (51%). Extra cores per task buy much less
    # than running more tasks side by side, so cores are spread thin and only
    # concentrated when there are fewer tasks than cores.
    n_tasks = max(1, len(tasks))
    cores_each = max(min_cores, total_threads // n_tasks)
    cores_each = min(cores_each, 4)

    allocations = {task["key"]: cores_each for task in tasks}
    return [tasks], allocations


def generate_bash_script(job_list, threads, enable_triplicate=False, min_cores=2):
    if not job_list:
        return ""

    batches, allocations = prep_parallel_tasks(
        job_list, threads, enable_triplicate, min_cores
    )

    lines = [
        "#!/bin/bash",
        'CACHE_FILE="$HOME/.hyphlow_hyphy_path.txt"',
        'HYPHY_PATH=""',
        'if [ -f "$CACHE_FILE" ]; then',
        '    CACHED_PATH=$(cat "$CACHE_FILE")',
        '    if [ -x "$CACHED_PATH" ] && "$CACHED_PATH" busted --help >/dev/null 2>&1; then',
        '        HYPHY_PATH="$CACHED_PATH"',
        "    fi",
        "fi",
        'if [ -z "$HYPHY_PATH" ]; then',
        "    OS_TYPE=$(uname -s)",
        "    if command -v conda &> /dev/null || command -v micromamba &> /dev/null; then",
        "        [ -f ~/.bashrc ] && source ~/.bashrc 2>/dev/null",
        "        [ -f ~/.zshrc ] && source ~/.zshrc 2>/dev/null",
        "    fi",
        "    if command -v hyphy &> /dev/null; then",
        "        HYPHY_PATH=$(command -v hyphy)",
        "    else",
        '        HYPHY_PATH=$(find ~/.local/share/mamba ~/micromamba ~/miniconda3 ~/anaconda3 ~/.conda /usr/local/bin /usr/bin /opt/homebrew/bin /opt/local/bin -type f -name "hyphy" -perm -111 2>/dev/null | grep "/bin/hyphy" | grep -v "/pkgs/" | head -n 1)',
        "    fi",
        '    if [ -n "$HYPHY_PATH" ]; then',
        '        echo "$HYPHY_PATH" > "$CACHE_FILE"',
        "    fi",
        "fi",
        'if [ -z "$HYPHY_PATH" ]; then',
        '    echo "[ERROR] HyPhy executable not found! Please ensure it is installed and accessible."',
        "    exit 1",
        "fi",
        # Run the executable we found by full path. Putting its folder on PATH
        # and calling "hyphy" can pick up a different install that happens to
        # come first, including conda build leftovers whose library paths are
        # still placeholders.
        'HYPHY_EXEC="$HYPHY_PATH"',
        'echo "Using HyPhy: $HYPHY_EXEC"',
        '"$HYPHY_EXEC" --version 2>/dev/null | head -n1',
        "mkdir -p .hyphlow_done",
        'echo "Starting HyPhy Dynamic Queue Execution..."\n',
    ]

    model_name_map = {
        "busted": "BUSTED",
        "absrel": "aBSREL",
        "fel": "FEL",
        "meme": "MEME",
        "fubar": "FUBAR",
        "relax": "RELAX",
    }

    # Every task now gets the same number of cores, so the budget is exact.
    cores_each = next(iter(allocations.values()), 1) if allocations else 1
    max_concurrent = max(1, threads // cores_each)
    lines.append(f"MAX_JOBS={max_concurrent}")
    lines.append("RUNNING=0")
    lines.append(
        f'echo "Running up to {max_concurrent} task(s) at once, '
        f'{cores_each} CPU each ({threads} available)."\n'
    )

    for b_idx, batch in enumerate(batches):
        lines.append('echo "----------------------------------------"')
        lines.append(f'echo "Queuing {len(batch)} tasks into Dynamic Worker Pool..."')

        for task in batch:
            f_name = task["f_name"]
            t_name = task["t_name"]
            model = task["model"].lower()
            model_exact = model_name_map.get(model, model.upper())
            base_name = Path(t_name).stem
            output_name = f"{base_name}_{model.upper()}{task['run_suffix']}.JSON"
            error_log = f"{base_name}_{model.upper()}{task['run_suffix']}_log.txt"
            task_cores = allocations[task["key"]]
            trace_key = task["key"]

            # jobs is unreliable here: a non-interactive shell has job control
            # off, so `jobs -rp` comes back empty and the throttle never fires.
            # Count launches ourselves and block on wait -n instead.
            lines.append("RUNNING=$((RUNNING+1))")
            lines.append("if [ $RUNNING -ge $MAX_JOBS ]; then")
            lines.append("    wait -n 2>/dev/null || wait")
            lines.append("    RUNNING=$((RUNNING-1))")
            lines.append("fi")

            lines.append(f'echo "===REACTION_START==={trace_key}==="')

            has_fg = bool(task["job"].get("has_fg"))
            cmd_strict = build_command(
                model,
                f_name,
                t_name,
                output_name,
                task_cores,
                has_fg,
                seed=task["seed"],
                tolerant=False,
            )
            cmd_tolerant = build_command(
                model,
                f_name,
                t_name,
                output_name,
                task_cores,
                has_fg,
                seed=task["seed"],
                tolerant=True,
            )

            if cmd_strict is None:
                lines.append(
                    f'echo "[ERROR] No specification for model {model}; skipped."'
                )
                lines.append(f'echo "===REACTION_ERROR==={trace_key}==="')
                continue

            if MODEL_SPECS[model].get("requires_tags") and not has_fg:
                lines.append(
                    f'echo "[ERROR] {model.upper()} needs a tagged tree '
                    f'({{FG}} labels); skipped."'
                )
                lines.append(f'echo "===REACTION_ERROR==={trace_key}==="')
                continue

            bash_logic = (
                f"( "
                f'{cmd_strict} < /dev/null 2>&1  | tee "{error_log}"; '
                f"STATUS=${{PIPESTATUS[0]}}; "
                f'if [ $STATUS -ne 0 ] || [ ! -s "{output_name}" ]; then '
                f'echo "[WARNING] {model.upper()} failed; retrying with '
                f"TOLERATE_NUMERICAL_ERRORS=1. Results from this pass ignore "
                f'numerical warnings." | tee -a "{error_log}"; '
                f'{cmd_tolerant} < /dev/null 2>&1  | tee -a "{error_log}"; '
                f"STATUS=${{PIPESTATUS[0]}}; "
                f'if [ $STATUS -eq 0 ] && [ -s "{output_name}" ]; then '
                f'touch ".hyphlow_done/{output_name}.tolerated"; fi; '
                f"fi; "
                f'if [ $STATUS -eq 0 ] && [ -s "{output_name}" ]; then '
                f'touch ".hyphlow_done/{output_name}"; '
                f'echo "===REACTION_DONE==={trace_key}==="; '
                f'else echo "===REACTION_ERROR==={trace_key}==="; fi '
                f") &"
            )
            lines.append(bash_logic)

        lines.append("wait")
        lines.append('echo "All dynamic queue tasks completed."\n')

    lines.append('echo "All tasks completed successfully!"\n')
    return "\n".join(lines)


def export_job_to_zip(job_list, script_content, save_path):
    try:
        zip_path = Path(save_path).with_suffix(".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            info = zipfile.ZipInfo("run_hyphy.sh")
            info.external_attr = 0o755 << 16
            zipf.writestr(info, script_content)

            added_files = set()
            for job in job_list:
                fasta, nwk = job["fasta"], job["tree"]
                if fasta not in added_files:
                    zipf.write(fasta, Path(fasta).name)
                    added_files.add(fasta)
                if nwk not in added_files:
                    zipf.write(nwk, Path(nwk).name)
                    added_files.add(nwk)

        return True, "Export Package ZIP has been created successfully!"
    except Exception as e:
        return False, f"Export Failed: {str(e)}"


def to_wsl_path(win_path):
    try:
        out = subprocess.check_output(
            ["wsl", "wslpath", "-a", "-u", win_path.replace("\\", "/")], text=True
        )
        return out.strip()
    except Exception:
        return win_path
