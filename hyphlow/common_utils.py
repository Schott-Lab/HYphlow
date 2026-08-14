import re
import threading
from pathlib import Path
from collections import Counter
from datetime import datetime
from hyphlow import organism_names

_NAME_LOCK = threading.Lock()


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


IGNORE_WORDS = {
    "FMT",
    "FAS",
    "FASTA",
    "NWK",
    "TREE",
    "TRE",
    "ALIGN",
    "ALN",
    "OUTPUT",
    "REC",
    "PRN",
    "PR",
    "MASTER",
    "CSV",
    "UNKNOWN",
    "PREDICTED",
    "ISOLATE",
    "SEQ",
    "CDS",
    "FA",
    "V1",
    "V2",
}
NCBI_PREFIXES = {"XM", "NM", "NP", "XP", "NC", "NG", "XR", "NR"}


GENE_LIKE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
SEQUENCE_LIKE = re.compile(r"^[ACGTUN]{6,}$")
ACCESSION_LIKE = re.compile(r"^[A-Z]{1,2}\d{4,}$")


def _is_gene_like(token):
    if not GENE_LIKE.match(token):
        return False
    if token in IGNORE_WORDS or token[:2] in NCBI_PREFIXES:
        return False
    if ACCESSION_LIKE.match(token):
        return False
    if SEQUENCE_LIKE.match(token):
        return False
    if organism_names.looks_like_organism(token):
        return False
    return True


def detect_gene_from_file(file_path):

    stem = Path(file_path).stem
    for token in re.split(r"[^A-Za-z0-9]+", stem):
        if _is_gene_like(token):
            return token

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read(8192).splitlines()
        if any(l.startswith(">") for l in lines):
            text = " ".join(l for l in lines if l.startswith(">"))
        else:
            text = " ".join(lines)
        hits = [t for t in re.split(r"[^A-Za-z0-9]+", text) if _is_gene_like(t)]
        if hits:
            token, count = Counter(hits).most_common(1)[0]
            if count >= 2:
                return token
    except OSError:
        pass

    return ""


def make_base_name(organism, gene):

    parts = [p.strip() for p in (organism, gene) if p and p.strip()]
    return "_".join(parts) if parts else "UNKNOWN"


def generate_smart_filename(base_name, file_type, out_dir, ext, is_report=False):

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    mmdd = datetime.now().strftime("%m%d")

    ft_upper = file_type.upper()
    if "PRN" in ft_upper:
        middle_tag = "_prn"
    elif "REC" in ft_upper:
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

    with _NAME_LOCK:
        v = 1
        while True:
            new_name = f"{prefix}{base_name}{middle_tag}_v{v}_{mmdd}{ext}"
            full_path = out_path / new_name
            try:
                full_path.touch(exist_ok=False)
                return str(full_path), v
            except FileExistsError:
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
