from ete3 import Tree

from hyphlow import common_utils


def read_fasta_taxa(path):
    taxa = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith(">"):
                taxa.add(common_utils.to_label(line.strip().lstrip(">")))
    return taxa


def load_tree(path):
    try:
        return Tree(str(path), format=1), 1
    except Exception:
        return Tree(str(path)), 0


def read_tree_taxa(path):
    tree, _ = load_tree(path)
    return {common_utils.to_label(leaf.name) for leaf in tree.get_leaves()}
