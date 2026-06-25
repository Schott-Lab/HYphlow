import re
from pathlib import Path
from collections import Counter
from datetime import datetime


def get_pipeline_path(project_path, category="Results", file_type="CSV"):

    if not project_path:
        return None

    ft_upper = file_type.upper()

    if ft_upper == "JSON":
        path = Path(project_path) / "Results" / "HyPhy_Execution"
    elif ft_upper == "SUMMARY":
        path = Path(project_path) / "Results" / "Results_Summary"
    else:
        if ft_upper in ["FAS", "FASTA", "FA"]:
            ft_dir = "FASTA"
        elif ft_upper in ["NWK", "TREE", "TRE"]:
            ft_dir = "NWK"
        else:
            ft_dir = "CSV"

        path = Path(project_path) / category / "Data_Preparation" / ft_dir

    path.mkdir(parents=True, exist_ok=True)
    return path


def detect_gene_from_file(file_path):

    candidates = []
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
        "UNKNOWN",
        "PREDICTED",
        "ISOLATE",
    }
    ncbi_prefixes = {"XM", "NM", "NP", "XP", "NC", "NG", "XR", "NR"}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read(4096)

        tokens = re.split(r"[^a-zA-Z0-9]", content)
        for token in tokens:
            t_upper = token.upper()
            if (
                3 <= len(t_upper) <= 10
                and not token.isdigit()
                and t_upper not in ignore_words
            ):
                if t_upper[:2] not in ncbi_prefixes:
                    if re.match(r"^[A-Z][A-Z0-9]{2,}$", t_upper):
                        candidates.append(t_upper)

        if candidates:
            most_common = Counter(candidates).most_common(1)
            return most_common[0][0]
    except Exception:
        pass

    name = Path(file_path).name.upper()
    tokens = re.split(r"[^A-Z0-9]", name)
    for t in tokens:
        if (
            3 <= len(t) <= 10
            and not t.isdigit()
            and t not in ignore_words
            and t[:2] not in ncbi_prefixes
        ):
            if re.match(r"^[A-Z][A-Z0-9]{2,}$", t):
                return t

    return "UNKNOWN"


def generate_smart_filename(base_name, file_type, out_dir, ext, is_report=False):

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    mmdd = datetime.now().strftime("%m%d")

    ft_upper = file_type.upper()

    if "REC" in ft_upper:
        if any(x in ft_upper for x in ["FAS", "FASTA", "FA"]):
            middle_tag = "_aln_rec"
        elif any(x in ft_upper for x in ["NWK", "TREE", "TRE"]):
            middle_tag = "_tree_rec"
        else:
            middle_tag = "_rec"
    elif ft_upper == "SUMMARY":
        middle_tag = ""
    else:
        if ft_upper in ["FAS", "FASTA", "FA"]:
            middle_tag = "_aln_fmt"
        elif ft_upper in ["NWK", "TREE", "TRE"]:
            middle_tag = "_tree_fmt"
        else:
            middle_tag = "_fmt"

    prefix = "Rpt_" if is_report else ""

    v = 1
    while True:
        new_name = f"{prefix}{base_name}{middle_tag}_v{v}_{mmdd}{ext}"
        full_path = out_path / new_name

        if not full_path.exists():
            return str(full_path), v
        v += 1


def log_error_to_file(project_path, tab_name, error_msg):

    if not project_path:
        return None

    mmdd = datetime.now().strftime("%m%d")
    timestamp = datetime.now().strftime("%H:%M:%S")

    err_dir = Path(project_path) / "Reports" / "Error_Reports"
    err_dir.mkdir(parents=True, exist_ok=True)

    err_file = err_dir / f"HYphlow_Error_Report_{mmdd}.txt"

    with open(err_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{tab_name}] {error_msg}\n")

    return str(err_dir)
