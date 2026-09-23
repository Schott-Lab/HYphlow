import re
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path

from hyphlow import organism_names

# =========================================================== constants

FASTA_TYPES = frozenset({"FAS", "FASTA", "FA"})
TREE_TYPES = frozenset({"NWK", "TREE", "TRE"})


RESULTS = "Results"
REPORTS = "Reports"


# File extensions (like 'fasta' or 'nwk') are never used as gene names.
# We just reuse the existing extension lists here so we don't have to
# type them out again.
IGNORE_WORDS = (
    FASTA_TYPES
    | TREE_TYPES
    | frozenset(
        {
            "FMT",
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
        }
    )
)


NCBI_PREFIXES = frozenset({"XM", "NM", "NP", "XP", "NC", "NG", "XR", "NR", "NW"})


# HyPhy models that HYphlow runs.
# This renames the model from the filename into the proper display
# format for the report (e.g., "absrel"->"aBSREL").
# See t3_hyphy_logic.MODEL_SPECS for how each model is executed.
HYPHY_MODELS = ("BUSTED", "aBSREL", "RELAX", "FEL", "MEME", "FUBAR")
HYPHY_MODEL_TOKENS = {name.upper(): name for name in HYPHY_MODELS}


# Ancestral-state steps.
# Kept here so both Tab 2 (to name files) and Tab 4 (to read those
# files) can share it.
# Since these become folder/file names, keep the names simple and safe
# (no special characters).
ANNOTATION_STEPS = ("Fitch", "Felsenstein", "Consensus")


# Tab 2 writes GENE_annotated_TAG_STEP_v1_0801.nwk. The tag can contain
# underscores, so it is read as a span up to the step name, not as one token.
TREE_TAG_RE = re.compile(
    r"_annotated_(.+?)_(?:%s)" % "|".join(map(re.escape, ANNOTATION_STEPS))
)

# Token shapes checked by is_gene_like.
GENE_LIKE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
SEQUENCE_LIKE = re.compile(r"^[ACGTUN]{6,}$")
ACCESSION_LIKE = re.compile(r"^[A-Z]{1,2}\d{4,}$")
# Uppercase version numbers (V1,V2,V3...) label samples or file
# revisions, not genes. A pattern rather than a word list.
VERSION_LIKE = re.compile(r"^V\d+$")


# ============================================================= helpers


def mmdd():
    return datetime.now().strftime("%m%d")


def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def to_label(name):
    return (name or "").strip().replace(" ", "_")


def _ensure(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_kind(file_type):
    ft = (file_type or "").upper()
    if ft in FASTA_TYPES:
        return "FASTA"
    if ft in TREE_TYPES:
        return "NWK"
    return "CSV"


# =============================================================== paths


def get_pipeline_path(project_path, category=RESULTS, file_type="CSV"):
    if not project_path:
        return None
    return _ensure(
        Path(project_path) / category / "Data_Preparation" / file_kind(file_type)
    )


def get_hyphy_path(project_path):
    if not project_path:
        return None
    return _ensure(Path(project_path) / RESULTS / "HyPhy_Execution")


def get_summary_path(project_path):
    if not project_path:
        return None
    return _ensure(Path(project_path) / RESULTS / "Results_Summary")


# ===================================================== gene detection


def _is_gene_like(token):
    if not GENE_LIKE.match(token):
        return False
    if token in IGNORE_WORDS:
        return False
    # Model names pass the shape test: BUSTED, RELAX and FEL all read
    # as gene symbols. Exact tokens only, so SLAC1 and FELB still get
    # through.
    if token in HYPHY_MODEL_TOKENS:
        return False
    if token[:2] in NCBI_PREFIXES:
        return False
    if ACCESSION_LIKE.match(token):
        return False
    if SEQUENCE_LIKE.match(token):
        return False
    if VERSION_LIKE.match(token):
        return False
    if organism_names.looks_like_organism(token):
        return False
    return True


# Callers need the position, not just the token: Tab 4 splits the
# organism from the gene at this index.
def gene_token_index(tokens):
    for i, token in enumerate(tokens):
        if _is_gene_like(token):
            return i
    return -1


def detect_gene_from_file(file_path):
    tokens = re.split(r"[^A-Za-z0-9]+", Path(file_path).stem)
    i = gene_token_index(tokens)
    if i >= 0:
        return tokens[i]

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read(8192).splitlines()
        if any(line.startswith(">") for line in lines):
            text = " ".join(line for line in lines if line.startswith(">"))
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


# =========================================================== filenames


# Guards the touch-and-retry loop below: 2 threads asking for the next
# version must not both get the same one.
_FILENAME_LOCK = threading.Lock()


def tag_from_tree_name(tree_path):
    m = TREE_TAG_RE.search(Path(tree_path).stem)
    return m.group(1) if m else ""


def make_base_name(organism, gene):
    parts = [p.strip() for p in (organism, gene) if p and p.strip()]
    return "_".join(parts) if parts else "UNKNOWN"


def _middle_tag(file_type):
    ft = (file_type or "").upper()
    if "PRN" in ft:
        return "_prn"
    if "REC" in ft:
        if any(x in ft for x in FASTA_TYPES):
            return "_aln_rec"
        if any(x in ft for x in TREE_TYPES):
            return "_tree_rec"
        return "_rec"
    if ft == "SUMMARY":
        return ""
    kind = file_kind(ft)
    if kind == "FASTA":
        return "_aln_fmt"
    if kind == "NWK":
        return "_tree_fmt"
    return "_fmt"


def generate_smart_filename(base_name, file_type, out_dir, ext, is_report=False):
    out_path = _ensure(Path(out_dir))
    prefix = "Rpt_" if is_report else ""
    tag = _middle_tag(file_type)
    stamp = mmdd()

    with _FILENAME_LOCK:
        v = 1
        while True:
            full_path = out_path / f"{prefix}{base_name}{tag}_v{v}_{stamp}{ext}"
            try:
                # touch, not exist(): creating the file is what reserves
                # the name. A check-then-create leaves a gap for
                # another writer.
                # Cost: a caller that fails after this leaves a 0-byte
                # file, and that file consumes the version number.
                full_path.touch(exist_ok=False)
                return str(full_path), v
            except FileExistsError:
                v += 1


# ========================================================== error logs


def log_error_to_file(project_path, tab_name, error_msg):
    if not project_path:
        return None

    # Called from except blocks. A logging failure must not replace the
    # error that is already being handled.
    try:
        err_dir = _ensure(Path(project_path) / REPORTS / "Error_Reports")
        err_file = err_dir / f"HYphlow_Error_Report_{mmdd()}.txt"
        with open(err_file, "a", encoding="utf-8") as f:
            f.write(
                f"[{datetime.now().strftime('%H:%M:%S')}] [{tab_name}] {error_msg}\n"
            )
    except OSError:
        return None

    return str(err_file)
