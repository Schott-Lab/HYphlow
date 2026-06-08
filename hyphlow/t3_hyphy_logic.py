import os
import re
import zipfile
import subprocess
from pathlib import Path
from ete3 import Tree


def standardize_filename(filename):
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", filename)
    return re.sub(r"_+", "_", safe_name).strip("_")


def extract_base_name(filename):
    parts = filename.split("_")
    return parts[0] if parts else filename


def pre_execution_validation(fasta_path, nwk_path):
    try:
        with open(fasta_path, "r", encoding="utf-8") as f:
            fasta_ids = {
                line.strip()[1:].strip().replace("'", "").replace('"', "")
                for line in f
                if line.startswith(">")
            }

        if not fasta_ids:
            return False, False, "Empty FASTA file."

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
            return True, has_fg, "Perfect Match"

        missing_in_fasta = sorted(list(tree_tips - fasta_ids))
        missing_in_tree = sorted(list(fasta_ids - tree_tips))

        error_msg = "Mismatch:"
        if missing_in_fasta:
            error_msg += f" Tree has extra ({missing_in_fasta[0]}...). "
        if missing_in_tree:
            error_msg += f" FASTA has extra ({missing_in_tree[0]}...)."

        return False, has_fg, error_msg.strip()

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
        f_base = extract_base_name(f_stem)
        matched_trees = []

        for n_stem, nwk_path_str in nwk_dict_paths.items():
            n_base = extract_base_name(n_stem)

            if (f_stem in n_stem) or (n_stem in f_stem) or (f_base == n_base):
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


def prep_parallel_tasks(job_list, total_threads):
    min_cores_per_job = 2
    max_concurrent = max(1, total_threads // min_cores_per_job)

    tasks = []
    for i, job in enumerate(job_list):
        f_name = Path(job["fasta"]).name
        t_name = Path(job["tree"]).name
        model = job["model"]
        task_key = f"{f_name}==={t_name}==={model.upper()}==={i}"

        tasks.append(
            {
                "job": job,
                "model": model,
                "key": task_key,
                "f_name": f_name,
                "t_name": t_name,
            }
        )

    batches = [
        tasks[i : i + max_concurrent] for i in range(0, len(tasks), max_concurrent)
    ]
    allocations = {}

    for batch in batches:
        n = len(batch)
        base = total_threads // n
        rem = total_threads % n
        for i, task in enumerate(batch):
            allocations[task["key"]] = max(1, base + (1 if i < rem else 0))

    return batches, allocations


def generate_bash_script(job_list, threads):
    if not job_list:
        return ""

    batches, allocations = prep_parallel_tasks(job_list, threads)

    lines = [
        "#!/bin/bash",
        "export TOLERATE_NUMERICAL_ERRORS=1",
        'CACHE_FILE="$HOME/.hyphlow_hyphy_path.txt"',
        'HYPHY_PATH=""',
        'if [ -f "$CACHE_FILE" ]; then',
        '    CACHED_PATH=$(cat "$CACHE_FILE")',
        '    if [ -x "$CACHED_PATH" ]; then',
        '        HYPHY_PATH="$CACHED_PATH"',
        '    fi',
        'fi',
        'if [ -z "$HYPHY_PATH" ]; then',
        '    OS_TYPE=$(uname -s)',
        '    if command -v conda &> /dev/null || command -v micromamba &> /dev/null; then',
        '        [ -f ~/.bashrc ] && source ~/.bashrc 2>/dev/null',
        '        [ -f ~/.zshrc ] && source ~/.zshrc 2>/dev/null',
        '    fi',
        '    if command -v hyphy &> /dev/null; then',
        '        HYPHY_PATH=$(command -v hyphy)',
        '    else',
        '        HYPHY_PATH=$(find ~/.local/share/mamba ~/micromamba ~/miniconda3 ~/anaconda3 ~/.conda /usr/local/bin /usr/bin /opt/homebrew/bin -type f -name "hyphy" -executable 2>/dev/null | grep "/bin/hyphy" | head -n 1)',
        '    fi',
        '    if [ -n "$HYPHY_PATH" ]; then',
        '        echo "$HYPHY_PATH" > "$CACHE_FILE"',
        '    fi',
        'fi',
        'if [ -z "$HYPHY_PATH" ]; then',
        '    echo "[ERROR] HyPhy executable not found! Please ensure it is installed and accessible."',
        '    exit 1',
        'fi',
        'HYPHY_LIB="$(dirname "$(dirname "$HYPHY_PATH")")/share/hyphy"',
        'export PATH="$(dirname "$HYPHY_PATH"):$PATH"',
        'HYPHY_EXEC="hyphy"',
        'echo "Starting HyPhy Parallel pipeline..."\n',
    ]

    model_name_map = {
        "busted": "BUSTED",
        "absrel": "aBSREL",
        "fel": "FEL",
        "meme": "MEME",
        "fubar": "FUBAR",
        "relax": "RELAX"
    }

    for b_idx, batch in enumerate(batches):
        lines.append(f'echo "----------------------------------------"')
        lines.append(
            f'echo "Starting Batch {b_idx + 1}/{len(batches)} (Parallel Execution)..."'
        )

        for task in batch:
            f_name = task["f_name"]
            t_name = task["t_name"]
            model = task["model"].lower()
            model_exact = model_name_map.get(model, model.upper())
            base_name = Path(t_name).stem
            output_name = f"{base_name}_{model.upper()}.JSON"
            error_log = f"{base_name}_{model.upper()}_log.txt"
            task_cores = allocations[task["key"]]

            trace_key = task["key"]
            lines.append(f'echo "===REACTION_START==={trace_key}==="')

            cmd_a = f'"$HYPHY_PATH" LIBPATH="$HYPHY_LIB" "$HYPHY_LIB/TemplateBatchFiles/SelectionAnalyses/{model_exact}.bf" --alignment "{f_name}" --tree "{t_name}" --CPU {task_cores} --output "{output_name}"'
            cmd_b = f'"$HYPHY_EXEC" {model} --alignment "{f_name}" --tree "{t_name}" --CPU {task_cores} --output "{output_name}"'

            if task["job"].get("has_fg"):
                if model == "relax":
                    cmd_a += " --test FG"
                    cmd_b += " --test FG"
                elif model in ["busted", "absrel", "meme", "fel"]:
                    cmd_a += " --branches FG"
                    cmd_b += " --branches FG"
                if model == "busted":
                    cmd_a += " --srv Yes"
                    cmd_b += " --srv Yes"

            bash_logic = (
                f'( '
                f'{cmd_a} 2>&1 | tee "{error_log}"; '
                f'STATUS=${{PIPESTATUS[0]}}; '
                f'if [ $STATUS -ne 0 ]; then '
                f'echo "[WARNING] Plan A (Absolute Path) failed for {model.upper()}. Retrying with Plan B (Standard)..." | tee -a "{error_log}"; '
                f'{cmd_b} 2>&1 | tee -a "{error_log}"; '
                f'STATUS=${{PIPESTATUS[0]}}; '
                f'fi; '
                f'if [ $STATUS -eq 0 ]; then '
                f'echo "===REACTION_DONE==={trace_key}==="; '
                f'else echo "===REACTION_ERROR==={trace_key}==="; fi '
                f') &'
            )
            lines.append(bash_logic)

        lines.append("wait")
        lines.append(f'echo "Batch {b_idx + 1} completed."\n')

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
