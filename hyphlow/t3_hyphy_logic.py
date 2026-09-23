import random
import re
import shlex
import subprocess
import zipfile
from collections import Counter
from pathlib import Path

from hyphlow import bio_io, common_utils

# =========================================================== constants


# Zero-length branches carry no substitution, so HyPhy collapses them
# before testing rather than counting them as branches the data cannot
# tell apart.
KILL_ZERO_LENGTHS = "Yes"

# Validation messages list at most this many taxa per problem, then a
# count.
NAMES_SHOWN = 5


# ========================================================== file names


def standardize_filename(filename):
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", filename)
    return re.sub(r"_+", "_", safe_name).strip("_")


# Same rule as common_utils.detect_gene_from_file, but the name only:
# this never opens the file.
def _gene_from_stem(stem):
    tokens = re.split(r"[^A-Za-z0-9]+", stem)
    i = common_utils.gene_token_index(tokens)
    return tokens[i] if i >= 0 else ""


# ====================================================== model settings


# Every option is written out, even ones that match the HyPhy default,
# so a HyPhy version change cannot silently alter results.
MODEL_SPECS = {
    "busted": {
        "subcommand": "busted",
        "requires_tags": False,
        "fixed": {
            "code": "Universal",
            "srv": "Yes",
            "error-sink": "No",
            "multiple-hits": "None",
            "kill-zero-lengths": KILL_ZERO_LENGTHS,
        },
        "tag_args": {"branches": "FG"},
    },
    "relax": {
        "subcommand": "relax",
        "requires_tags": True,
        "fixed": {
            "code": "Universal",
            "srv": "No",
            "models": "All",
            "multiple-hits": "None",
            "kill-zero-lengths": KILL_ZERO_LENGTHS,
        },
        # RELAX picks the reference set automatically from
        # unlabelled branches when only --test is given.
        "tag_args": {"test": "FG"},
    },
    "absrel": {
        "subcommand": "absrel",
        "requires_tags": False,
        "fixed": {
            "code": "Universal",
            "srv": "No",
            "multiple-hits": "None",
            "kill-zero-lengths": KILL_ZERO_LENGTHS,
        },
        "tag_args": {"branches": "FG"},
    },
    "fel": {
        "subcommand": "fel",
        "requires_tags": False,
        "fixed": {
            "code": "Universal",
            "srv": "Yes",
            "multiple-hits": "None",
            "pvalue": "0.1",
            "ci": "No",
            "resample": "0",
            "kill-zero-lengths": KILL_ZERO_LENGTHS,
        },
        "tag_args": {"branches": "FG"},
    },
    "meme": {
        "subcommand": "meme",
        "requires_tags": False,
        "fixed": {
            "code": "Universal",
            "rates": "2",
            "multiple-hits": "None",
            "impute-states": "No",
            "pvalue": "0.1",
            "resample": "0",
            "kill-zero-lengths": KILL_ZERO_LENGTHS,
        },
        "tag_args": {"branches": "FG"},
    },
    # FUBAR has no --branches option, so a tagged tree cannot narrow it;
    # it is a whole-alignment site-wise method and always runs globally.
    # chains and chain-length are MCMC-only and the default inference
    # method is variational Bayes, so neither is set here.
    "fubar": {
        "subcommand": "fubar",
        "requires_tags": False,
        "cache_arg": "cache",
        "fixed": {
            "code": "Universal",
            "grid": "20",
            "concentration_parameter": "0.5",
            "kill-zero-lengths": KILL_ZERO_LENGTHS,
        },
        "tag_args": {},
    },
}


# ======================================================= hyphy command


# ENV= must come after the subcommand: HyPhy reads the first positional
# argument as the analysis name, so putting ENV= first makes it treat
# the analysis name as a batch file path.
def build_command(model, fasta, tree, output, cores, has_fg, seed=None, tolerant=False):
    spec = MODEL_SPECS.get(model)
    if spec is None:
        return None

    parts = ['"$HYPHY_EXEC"', spec["subcommand"]]
    if tolerant:
        parts.append("ENV=TOLERATE_NUMERICAL_ERRORS=1")
    # shlex.quote, not "...": user file names are copied in
    # unchanged, and a $ or " inside double quotes would break or
    # rewrite the command.
    parts += [f"--alignment {shlex.quote(fasta)}", f"--tree {shlex.quote(tree)}"]

    for key, value in spec["fixed"].items():
        parts.append(f"--{key} {value}")
    if has_fg:
        for key, value in spec["tag_args"].items():
            parts.append(f"--{key} {value}")

    parts.append(f"--CPU {cores}")
    if seed:
        parts.append(f"--seed {seed}")
    # FUBAR caches its grid next to the alignment by default, so
    # parallel jobs sharing one alignment would race on the same file.
    # Key it to the output.
    if spec.get("cache_arg"):
        parts.append(f"--{spec['cache_arg']} {shlex.quote(output + '.cache')}")
    parts.append(f"--output {shlex.quote(output)}")
    return " ".join(parts)


# One task, from the HyPhy call to the marker the run log is read by. Shared
# with any other launcher: the caller decides how it is run, so no & here.
def _task_body(model, f_name, t_name, cores, has_fg, seed, run_suffix, trace_key):
    run_stem = f"{Path(t_name).stem}_{model.upper()}{run_suffix}"
    output_name = f"{run_stem}.JSON"
    q_out = shlex.quote(output_name)
    q_log = shlex.quote(f"{run_stem}_log.txt")
    q_done = shlex.quote(f".hyphlow_done/{output_name}")
    q_tol = shlex.quote(f".hyphlow_done/{output_name}.tolerated")
    # The key holds user file names; quoting keeps a $ in one from being
    # expanded away before the UI can match the line to a task.
    q_done_msg = shlex.quote(f"===REACTION_DONE==={trace_key}===")
    q_err_msg = shlex.quote(f"===REACTION_ERROR==={trace_key}===")

    args = (model, f_name, t_name, output_name, cores, has_fg)
    cmd_strict = build_command(*args, seed=seed, tolerant=False)
    cmd_tolerant = build_command(*args, seed=seed, tolerant=True)

    return (
        f"{cmd_strict} < /dev/null 2>&1 | tee {q_log}; "
        f"STATUS=${{PIPESTATUS[0]}}; "
        f"if [ $STATUS -ne 0 ] || [ ! -s {q_out} ]; then "
        f'echo "[WARNING] {model.upper()} failed; retrying with '
        f"TOLERATE_NUMERICAL_ERRORS=1. Results from this pass ignore "
        f'numerical warnings." | tee -a {q_log}; '
        f"{cmd_tolerant} < /dev/null 2>&1 | tee -a {q_log}; "
        f"STATUS=${{PIPESTATUS[0]}}; "
        f"if [ $STATUS -eq 0 ] && [ -s {q_out} ]; then "
        f"touch {q_tol}; fi; "
        f"fi; "
        f"if [ $STATUS -eq 0 ] && [ -s {q_out} ]; then "
        f"touch {q_done}; "
        f"echo {q_done_msg}; "
        f"else echo {q_err_msg}; fi"
    )


# ======================================================== input checks


# Names are read the way HyPhy reads them. A name that appears twice is
# returned separately rather than letting the later sequence overwrite
# the earlier one, which would hide the repeat from every check
# downstream.
def _read_fasta(path):
    seqs, repeated, name = {}, [], None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith(">"):
                name = line.strip()[1:].strip().replace("'", "").replace('"', "")
                if name in seqs:
                    repeated.append(name)
                seqs[name] = []
            elif name is not None:
                seqs[name].append(line.strip())
    return {k: "".join(v).upper() for k, v in seqs.items()}, repeated


# HyPhy warns about identical sequences and carries on. They add no
# information and force the branch between them to zero length, which is
# where numerical trouble starts.
def _duplicate_groups(seqs):
    by_seq = {}
    for name, s in seqs.items():
        if s:
            by_seq.setdefault(s, []).append(name)
    return [sorted(g) for g in by_seq.values() if len(g) > 1]


# Messages are read by people choosing which pairs to run, so each
# problem names the taxa involved rather than only saying that one exists.
def _name_list(names):
    names = list(names)
    shown = ", ".join(names[:NAMES_SHOWN])
    extra = len(names) - NAMES_SHOWN
    return f"{shown} and {extra} more" if extra > 0 else shown


def pre_execution_validation(fasta_path, nwk_path):
    try:
        seqs, repeated = _read_fasta(fasta_path)
        if not seqs:
            return False, False, "Empty FASTA file."

        try:
            tree, _ = bio_io.load_tree(nwk_path)
        except Exception as e:
            return False, False, f"Tree parsing error\n     {e}"

        # The tree is read even when the FASTA already fails: a pair
        # left unchecked can still be ticked by hand, and has_fg decides
        # whether the tagged branches reach HyPhy.
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

        problems, warnings = [], []

        if repeated:
            counts = Counter(repeated)
            named = _name_list(f"{n} (x{c + 1})" for n, c in counts.items())
            problems.append(
                f"Name used more than once in FASTA ({len(counts)}): {named}. "
                "HyPhy stops on this before writing any results."
            )

        fasta_ids = set(seqs)
        in_tree_only = sorted(tree_tips - fasta_ids)
        in_fasta_only = sorted(fasta_ids - tree_tips)
        if in_tree_only:
            problems.append(
                f"In tree, not in FASTA ({len(in_tree_only)}): "
                f"{_name_list(in_tree_only)}"
            )
        if in_fasta_only:
            problems.append(
                f"In FASTA, not in tree ({len(in_fasta_only)}): "
                f"{_name_list(in_fasta_only)}"
            )

        dups = _duplicate_groups(seqs)
        if dups:
            shown = " / ".join(", ".join(g) for g in dups[:NAMES_SHOWN])
            extra = len(dups) - NAMES_SHOWN
            more = f" and {extra} more" if extra > 0 else ""
            warnings.append(
                f"Identical sequences ({len(dups)} group(s)): {shown}{more}. "
                "HyPhy runs, but the branch between them has zero length."
            )

        if repeated:
            status = "Name repeated"
        elif problems:
            status = "Mismatch"
        elif warnings:
            status = "Warning"
        else:
            status = "Perfect Match"

        lines = [status] + [f"  {p}" for p in problems]
        if problems and warnings:
            lines.append("Warning")
        lines += [f"    {w}" for w in warnings]
        return not problems, has_fg, "\n".join(lines)

    except Exception as e:
        return False, False, f"Error\n  {e}"


# ============================================================== pairing


def _identity_key(identity):
    org, gene = ((s or "").strip().lower() for s in identity)
    return (org, gene) if org and gene else None


# Pairing follows the ORG/GENE the user can see and edit. Whether a pair
# really belongs together is left to pre_execution_validation, which
# compares taxa.
def get_matched_pairs(fasta_ids, tree_ids):
    unpaired = []
    trees_by_key = {}
    for path, identity in tree_ids.items():
        key = _identity_key(identity)
        if key is None:
            unpaired.append((str(path), "ORG or GENE is empty"))
        else:
            trees_by_key.setdefault(key, []).append(str(path))

    matched_dict = {}
    used_keys = set()
    for path, identity in fasta_ids.items():
        fasta_path = str(path)
        key = _identity_key(identity)
        if key is None:
            unpaired.append((fasta_path, "ORG or GENE is empty"))
            continue
        tree_paths = trees_by_key.get(key)
        if not tree_paths:
            unpaired.append((fasta_path, "no tree with the same ORG/GENE"))
            continue

        used_keys.add(key)
        matched_trees = []
        for tree_path in tree_paths:
            is_valid, has_fg, error_msg = pre_execution_validation(
                fasta_path, tree_path
            )
            matched_trees.append(
                {
                    "nwk_path": tree_path,
                    "nwk_name": Path(tree_path).stem,
                    "is_valid": is_valid,
                    "has_fg": has_fg,
                    "error_msg": error_msg,
                }
            )
        matched_dict[fasta_path] = {"fasta_path": fasta_path, "trees": matched_trees}

    for key, tree_paths in trees_by_key.items():
        if key not in used_keys:
            unpaired += [(p, "no FASTA with the same ORG/GENE") for p in tree_paths]

    return matched_dict, unpaired


def prep_parallel_tasks(job_list, total_threads, enable_triplicate=False, min_cores=2):
    tasks = []

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

    # Measured on a 30-taxon, 354 codon BUSTED run: 1 CPU 636s, 2 CPU
    # 490s (65% efficient), 4 CPU 311s(51%). Extra cores per task buy
    # much less than running more tasks side by side, so cores are
    # spread thin and only concentrated when there are fewer tasks than
    # cores.
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
        # conda installs put hyphy on PATH only after the shell rc file runs,
        # and a script started from the app does not read it.
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
        'HYPHY_EXEC="$HYPHY_PATH"',
        'echo "Using HyPhy: $HYPHY_EXEC"',
        '"$HYPHY_EXEC" --version 2>/dev/null | head -n1',
        "mkdir -p .hyphlow_done",
        'echo "Starting HyPhy Dynamic Queue Execution..."\n',
    ]

    # Every task now gets the same number of cores, so the budget is exact.
    cores_each = next(iter(allocations.values()), 1)
    max_concurrent = max(1, threads // cores_each)
    lines.append(f"MAX_JOBS={max_concurrent}")
    lines.append("RUNNING=0")
    lines.append(
        f'echo "Running up to {max_concurrent} task(s) at once, '
        f'{cores_each} CPU each ({threads} available)."\n'
    )

    for batch in batches:
        lines.append('echo "----------------------------------------"')
        lines.append(f'echo "Queuing {len(batch)} tasks into Dynamic Worker Pool..."')

        for task in batch:
            model = task["model"].lower()
            trace_key = task["key"]
            has_fg = bool(task["job"].get("has_fg"))
            spec = MODEL_SPECS.get(model)
            q_err = shlex.quote(f"===REACTION_ERROR==={trace_key}===")

            # Skipped tasks return before the queue counter moves: a task that
            # never starts must not hold one of the MAX_JOBS slots.
            if spec is None:
                lines.append(
                    f'echo "[ERROR] No specification for model {model}; skipped."'
                )
                lines.append(f"echo {q_err}")
                continue

            if spec.get("requires_tags") and not has_fg:
                lines.append(
                    f'echo "[ERROR] {model.upper()} needs a tagged tree '
                    f'({{FG}} labels); skipped."'
                )
                lines.append(f"echo {q_err}")
                continue

            # -gt, not -ge. RUNNING is incremented before the task is launched,
            # so at -ge the queue waits when it is one short of the limit and
            # never reaches it: a run capped at three kept two going and left a
            # third of the cores idle throughout. The body always ends on an
            # echo, so a failed analysis still exits 0 and wait -n does not
            # fall through to the full wait.
            lines.append("RUNNING=$((RUNNING+1))")
            lines.append("if [ $RUNNING -gt $MAX_JOBS ]; then")
            lines.append("    wait -n 2>/dev/null || wait")
            lines.append("    RUNNING=$((RUNNING-1))")
            lines.append("fi")

            lines.append(f"echo {shlex.quote(f'===REACTION_START==={trace_key}===')}")
            body = _task_body(
                model,
                task["f_name"],
                task["t_name"],
                allocations[task["key"]],
                has_fg,
                task["seed"],
                task["run_suffix"],
                trace_key,
            )
            lines.append(f"( {body} ) &")

        lines.append("wait")
        lines.append('echo "All dynamic queue tasks completed."\n')

    lines.append('echo "All tasks completed successfully!"\n')
    return "\n".join(lines)


# The header is a starting point, not a guess at the cluster. Partition, time
# and memory differ everywhere, and so does the way HyPhy is reached, so each
# of those is left for the user to set before submitting.
SLURM_HEADER = """#!/bin/bash
#SBATCH --job-name=hyphlow
#SBATCH --array=0-{last}
#SBATCH --cpus-per-task={cpus}
#SBATCH --output=slurm_%A_%a.out

# TODO: set a wall time and memory that fit your alignments. Memory scales
# with alignment size rather than with run time.
#SBATCH --time=24:00:00
#SBATCH --mem=8G

# TODO: uncomment if your cluster requires them.
# #SBATCH --partition=<PARTITION>
# #SBATCH --account=<ACCOUNT>

# TODO: uncomment the line that matches your cluster.
# module load hyphy
# module load StdEnv/2020 hyphy
# source ~/miniconda3/etc/profile.d/conda.sh && conda activate hyphy

# Add %N to --array above to cap how many run at once, e.g. --array=0-{last}%4.
# Without it the scheduler decides, which is usually what you want.

HYPHY_EXEC=$(command -v hyphy)
if [ -z "$HYPHY_EXEC" ]; then
    echo "[ERROR] hyphy not found. Load it above before submitting."
    exit 1
fi
echo "Using HyPhy: $HYPHY_EXEC"

mkdir -p .hyphlow_done

case "$SLURM_ARRAY_TASK_ID" in"""


def generate_slurm_script(job_list, enable_triplicate=False, cpus_per_task=2):
    if not job_list:
        return ""

    # Only the task list is taken from here; how many run at once is the
    # scheduler's decision on a cluster, not a thread count on this machine.
    batches, _ = prep_parallel_tasks(
        job_list, cpus_per_task, enable_triplicate, cpus_per_task
    )

    runnable, skipped = [], []
    for task in batches[0]:
        model = task["model"].lower()
        spec = MODEL_SPECS.get(model)
        if spec is None:
            skipped.append(f"{task['key']}: no specification for model {model}")
        elif spec.get("requires_tags") and not task["job"].get("has_fg"):
            skipped.append(f"{task['key']}: {model.upper()} needs a tagged tree")
        else:
            runnable.append(task)

    if not runnable:
        return ""

    lines = [
        SLURM_HEADER.format(last=len(runnable) - 1, cpus=cpus_per_task),
    ]

    for index, task in enumerate(runnable):
        body = _task_body(
            task["model"].lower(),
            task["f_name"],
            task["t_name"],
            "$SLURM_CPUS_PER_TASK",
            bool(task["job"].get("has_fg")),
            task["seed"],
            task["run_suffix"],
            task["key"],
        )
        lines.append(f"{index})")
        lines.append(f"    {body}")
        lines.append("    ;;")

    lines.append("*)")
    lines.append('    echo "[ERROR] No task for index $SLURM_ARRAY_TASK_ID"')
    lines.append("    exit 1")
    lines.append("    ;;")
    lines.append("esac")

    for note in skipped:
        lines.append(f"# skipped -- {note}")

    return "\n".join(lines) + "\n"


# ======================================================= export & wsl


def export_job_to_zip(job_list, script_content, save_path):
    # The script refers to files by name, so two files with one name cannot
    # both travel in the package. Checked before anything is written.
    sources = {}
    for job in job_list:
        for path in (job["fasta"], job["tree"]):
            name = Path(path).name
            if sources.get(name, path) != path:
                return (
                    False,
                    f"Two different files are both named {name}. "
                    "Rename one of them before exporting.",
                )
            sources[name] = path

    path = Path(save_path)
    zip_path = (
        path if path.suffix.lower() == ".zip" else path.with_name(path.name + ".zip")
    )

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            info = zipfile.ZipInfo("run_hyphy.sh")
            info.external_attr = 0o755 << 16
            zipf.writestr(info, script_content)
            for name, source in sources.items():
                zipf.write(source, name)
    except OSError as e:
        return False, f"Export failed: {e}"

    return True, "Export Package ZIP has been created successfully!"


def to_wsl_path(win_path):
    try:
        out = subprocess.check_output(
            ["wsl", "wslpath", "-a", "-u", win_path.replace("\\", "/")],
            text=True,
            timeout=15,
            # A console window would flash over the app on every call.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return out.strip()
    except (OSError, subprocess.SubprocessError):
        # No WSL, no distribution, or it did not answer. The Windows path is
        # returned unchanged so the caller fails on the path it was given.
        return win_path
