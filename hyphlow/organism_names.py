import gzip
import sys
from pathlib import Path

_names = None


def _data_dir():
    # sys._MEIPASS exists only inside a PyInstaller bundle.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / "data"


def find_list(data_dir=None):

    folder = Path(data_dir) if data_dir else _data_dir()
    files = sorted(folder.glob("organism_names_*.txt.gz"))
    return files[-1] if files else None


def load(path):

    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return {
            line.strip() for line in fh if line.strip() and not line.startswith("#")
        }


def get_names(data_dir=None):

    global _names
    if _names is None:
        found = find_list(data_dir)
        _names = load(found) if found else set()
    return _names


def looks_like_organism(word, names=None):
    names = get_names() if names is None else names
    w = (word or "").strip().lower()
    if not w:
        return False
    if w in names:
        return True
    if not w.endswith("s"):
        return (w + "s") in names or (w + "es") in names
    return False
