import csv
import re
import threading
from pathlib import Path

COLUMNS = ["organism", "gene", "tag", "stage", "path", "source"]
_LOCK = threading.Lock()

OK, WARN, ERROR = "ok", "warn", "error"

from hyphlow import common_utils, organism_names


def manifest_path(project_path):
    folder = Path(project_path) / "Reports" / "Manifest"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "project_manifest.tsv"


def _ensure_header(path):
    if path.exists():
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh, delimiter="\t").writerow(COLUMNS)


def add_row(project_path, organism, gene, tag, stage, file_path, source=""):

    path = manifest_path(project_path)
    with _LOCK:
        _ensure_header(path)
        with open(path, "a", newline="", encoding="utf-8") as fh:
            csv.writer(fh, delimiter="\t").writerow(
                [
                    organism,
                    gene,
                    tag,
                    stage,
                    _relative(project_path, file_path),
                    _relative(project_path, source) if source else "",
                ]
            )


def read_rows(project_path):
    path = manifest_path(project_path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


_known_cache = {}


def known_values(project_path, column):

    path = manifest_path(project_path)
    stamp = path.stat().st_mtime_ns if path.exists() else 0
    key = (str(path), column, stamp)
    if key in _known_cache:
        return _known_cache[key]
    out = set()
    for row in read_rows(project_path):
        v = (row.get(column) or "").strip()
        if v:
            out.add(v.lower())
    _known_cache.clear()
    _known_cache[key] = out
    return out


def identity_for_path(project_path, file_path):

    target = _relative(project_path, file_path)
    for row in reversed(read_rows(project_path)):
        if _key(row.get("path")) == _key(target):
            return (row.get("organism") or ""), (row.get("gene") or "")
    return "", ""


def resolve_identity(project_path, file_path, typed=None):

    typed_org = (typed[0] or "").strip() if typed else ""
    typed_gene = (typed[1] or "").strip() if typed else ""
    if typed_org and typed_gene:
        return typed_org, typed_gene

    org, gene = "", ""
    if project_path:
        org, gene = identity_for_path(project_path, file_path)

    org = typed_org or org
    gene = typed_gene or gene
    if org and gene:
        return org, gene

    tokens = [p for p in re.split(r"[^A-Za-z0-9]+", Path(file_path).stem) if p]
    if not org:
        for t in tokens:
            if organism_names.looks_like_organism(t) or (
                project_path and t.lower() in known_values(project_path, "organism")
            ):
                org = t
                break
    if not gene:
        gene = common_utils.detect_gene_from_file(file_path) or ""
    return org, gene


def _relative(project_path, file_path):

    p, base = Path(file_path), Path(project_path)
    try:
        return p.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def _key(value):
    return (value or "").strip().lower()


def group_by_gene(rows):
    groups = {}
    for row in rows:
        groups.setdefault((_key(row["organism"]), _key(row["gene"])), []).append(row)
    return groups


def latest_rows(rows):

    keep = {}
    for row in rows:
        source = _key(row.get("source")) or _key(row.get("path"))
        keep[(source, _key(row.get("stage")))] = row
    return list(keep.values())


def check_rows(project_path, rows):
    base = Path(project_path)
    results = []
    for row in rows:
        problems = []
        for col in ("organism", "gene", "path"):
            if not (row.get(col) or "").strip():
                problems.append((ERROR, f"{col} is empty"))
        rel = (row.get("path") or "").strip()
        if rel and not (base / rel).exists():
            problems.append((ERROR, "file not found"))
        if not (row.get("stage") or "").strip():
            problems.append((WARN, "stage is empty"))
        status = (
            ERROR
            if any(s == ERROR for s, _ in problems)
            else (WARN if problems else OK)
        )
        results.append({"row": row, "status": status, "problems": problems})
    return results
