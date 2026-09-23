import datetime
import json
import math
import os
import random
import re
import tempfile
import traceback
from pathlib import Path

import pandas as pd
from ete3 import CircleFace, NodeStyle, RectFace, TextFace, Tree, TreeStyle

from hyphlow import common_utils, manifest_logic_tab, t1_st1_logic

# ==================================================================== constants

INF = float("inf")

BACKGROUND = 0
FOREGROUND = 1

FITCH = "fitch"
FELSENSTEIN = "felsenstein"
ALGORITHMS = (FITCH, FELSENSTEIN)

# Starting value each algorithm needs at a tip, as (background, foreground).
# Copied before being attached, because these are module-level mutable objects.
_TIP_FEATURE = {
    FITCH: ("state_set", ({BACKGROUND}, {FOREGROUND})),
    FELSENSTEIN: ("likelihood", ([1.0, 0.0], [0.0, 1.0])),
}

RESULTS_DIR = "Results"
REPORTS_DIR = "Reports"
TAB_SUBDIR = "Tree_Annotation"
TAB_NAME = "Tree Annotation"
DATE_FORMAT = "%Y-%m-%d"

# The tag written into node names while a tree is being annotated, and stripped
# again before the name is drawn or looked up.
FG_TAG = "{FG}"

STEP_FITCH = 0
STEP_ML = 1
STEP_CONSENSUS = 2

STEP_TITLES = (
    "HYphlow Step 1: Fitch Parsimony Prediction",
    "HYphlow Step 2: Felsenstein ML Prediction",
    "HYphlow Step 3: Consensus",
)
N_STEPS = len(STEP_TITLES)

COLOR_TEXT = "#1D1D1F"
COLOR_INACTIVE = "#E5E5EA"
COLOR_NO_TRAIT = "#F2F2F7"
COLOR_WARNING = "#FF3B30"
COLOR_FITCH = "#0071E3"
COLOR_ML = "#AF52DE"
COLOR_CONSENSUS = "#FF3B30"

WIDTH_INACTIVE = 1
WIDTH_ACTIVE = 3
WIDTH_CONSENSUS = 4

SWATCH_WIDTH = 16
SWATCH_TRAIT = 16
SWATCH_THIN = 6
SWATCH_THICK = 8

# One legend row per (colour, label, swatch height). The colours are the same
# constants the branch styling uses, so an edit cannot leave a figure disagreeing
# with its own legend.
STEP_LEGEND = {
    STEP_FITCH: ((COLOR_FITCH, "Fitch algorithm", SWATCH_THIN),),
    STEP_ML: ((COLOR_ML, "Felsenstein algorithm", SWATCH_THIN),),
    STEP_CONSENSUS: ((COLOR_CONSENSUS, "Consensus branches", SWATCH_THICK),),
}

# Defaults for scores a saved run did not record, kept in one place so the
# figures and the loader that feeds them cannot drift apart. p_fg sits at the
# decision boundary and f_tie False means Fitch did not abstain.
DEFAULT_PROB_FG = 0.5
DEFAULT_F_TIE = False
# No default for p_smap on purpose: absent means unmeasured, which the consensus
# gate treats differently from a measured 0.5.

# Both methods have to have voted. ML never abstains, so this means a branch
# where Fitch abstains cannot be tagged at all: the abstention is a veto rather
# than a withdrawal. Conservative by design. Whether the trade is worth making,
# missed foreground against wrongly tagged foreground, is a question for the
# simulation benchmark and not for this module.
MIN_VOTES = 2

# Golden-section search, and the fraction of the search ceiling at which mu is
# treated as having run away, meaning the trait carries no phylogenetic signal.
GOLDEN_RATIO = (math.sqrt(5) - 1) / 2
MU_CEILING_FRACTION = 0.95
LOGLIK_FLOOR = float("-inf")

# Above this the trait changes so fast that ancestral states are poorly
# determined, though not so fast that the search hit its ceiling. A separate
# threshold from MU_CEILING_FRACTION: this one only softens the wording of a
# warning, it does not suppress the results.
MU_WEAK_SIGNAL = 10.0

# Flat probabilities, for a node whose likelihoods have underflowed to zero and
# where no state can therefore be preferred.
FLAT = [0.5, 0.5]

# A marginal probability this close to the boundary is reported as weak, since the
# two states are then nearly equally supported.
WEAK_SUPPORT_LOW = 0.4
WEAK_SUPPORT_HIGH = 0.6

# How many taxa a report cell names before summarising the rest as a count.
TAXA_SHOWN = 2

YES = "YES"
NO = "NO"

# Column order of the run report. Every row carries all of them, including the
# informational rows that leave most blank.
REPORT_COLUMNS = (
    "Node",
    "Taxa_Count",
    "Taxa",
    "Selected",
    "Agreed",
    "Voters",
    "Fitch",
    "ML",
    "Confidence",
    "Note",
)

# Fitch charges one for any change of state, a gain and a loss alike. Written as
# a cost table because the remainder-cost pass reads it as one.
UNIT_TRANSITION = {
    (BACKGROUND, BACKGROUND): 0,
    (BACKGROUND, FOREGROUND): 1,
    (FOREGROUND, BACKGROUND): 1,
    (FOREGROUND, FOREGROUND): 0,
}

# Defaults for run_consensus_tagging when the caller passes none.
DEFAULT_ALGO_PARAMS = {
    "felsenstein_mu": "auto",
    # 5000 rather than 1000. Under 1000 draws, about 4.5 percent of scored
    # branches changed verdict between seeds on the same data, concentrated in
    # 16-tip trees with a weak signal; 5000 halves that. See
    # test_nsim_stability.py.
    "n_simulations": 5000,
    "smap_threshold": 0.5,
}

# Directory and filename component for each step. Separate from STEP_TITLES,
# which is prose for a figure heading; these have to be safe inside a path on
# every platform.
STEP_NAMES = (
    "Fitch",
    "Felsenstein",
    "Consensus",
)
if len(STEP_NAMES) != N_STEPS:
    raise RuntimeError("STEP_NAMES and STEP_TITLES describe different step counts")

# Marks output whose transition rate ran away, so a file cannot be mistaken for a
# usable result once it has been moved out of its folder.
NO_SIGNAL_TAG = "_NO-SIGNAL"

# The phrase resolve_mu uses when the rate hit its ceiling. Matched on the text
# because the warnings themselves are what the report shows.
NO_SIGNAL_PHRASE = "upper bound"

TRAIT_PALETTE = (
    "#32ADE6",
    "#FF9500",
    "#AF52DE",
    "#FF2D55",
    "#0071E3",
    "#34C759",
    "#5AC8FA",
    "#4CD964",
    "#FFCC00",
    "#FF3B30",
    "#E5C200",
    "#00C7BE",
    "#A2845E",
    "#D5A6BD",
    "#8E8E93",
)


# ============================================================= paths and files


def _log(message: str) -> None:
    """Append one line to the shared error report, if that is possible.

    Failures here are swallowed. This is called from paths that are already
    handling a problem, and a logging failure must not replace the original one
    with something less informative.
    """
    try:
        common_utils.log_error_to_file(
            t1_st1_logic.CURRENT_PROJECT_PATH, TAB_NAME, message
        )
    except Exception:
        pass


def _dated_dir(top: str) -> Path | None:
    """Project subdirectory for today's outputs, created if absent.

    Returns None when no project is open, or when the directory cannot be
    created, in which case the reason is written to the error report. The date is
    local rather than UTC, so the folder matches the day shown on the user's own
    machine; a session crossing midnight writes to two folders.
    """
    root = t1_st1_logic.CURRENT_PROJECT_PATH
    if not root:
        return None
    path = Path(root) / top / TAB_SUBDIR / datetime.date.today().strftime(DATE_FORMAT)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _log(f"Could not create output directory {path}: {exc}")
        return None
    return path


def get_results_path() -> Path | None:
    return _dated_dir(RESULTS_DIR)


def get_reports_path() -> Path | None:
    return _dated_dir(REPORTS_DIR)


def format_name(name: str) -> str:
    """Collapse every whitespace run to one underscore and trim the ends.

    split() handles tabs and repeated spaces, which a plain replace() would turn
    into repeated underscores and so break otherwise valid matches.
    """
    return "_".join(str(name).split())


def get_csv_headers(csv_path) -> list[str]:
    """Column names of a CSV, or an empty list if it cannot be read."""
    try:
        return pd.read_csv(csv_path, nrows=0).columns.tolist()
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        _log(f"Could not read headers from {csv_path}: {exc}")
        return []


def get_unique_values(csv_path, col_name) -> list[str]:
    """Distinct non-null values in one column, or an empty list on failure."""
    try:
        column = pd.read_csv(csv_path, usecols=[col_name])[col_name]
    except (OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        _log(f"Could not read column {col_name!r} from {csv_path}: {exc}")
        return []
    return [str(x) for x in column.dropna().unique()]


# ============================================================= trait selection


def build_tagged_data(df, name_col: str, selections: dict) -> dict:
    """Map each taxon to the trait states it matched, or to an empty string.

    `selections` maps a trait column to the states designated as foreground in it.
    A taxon is foreground when it matches any selected state in any selected
    column, so states from the same or different columns combine as a logical OR.
    The matched state names are kept rather than reduced to a flag, both for the
    figure legend and so the report can say which state put a taxon there.

    Taxon names go through format_name and trait values are trimmed before
    comparison, for the same reason: a trailing space in the metadata would
    otherwise drop that taxon to background with no warning.

    A taxon absent from the table does not appear here at all, which
    initialize_tree reads as background and counts as unmatched.
    """
    if name_col not in df.columns:
        raise KeyError(f"taxon name column {name_col!r} is not in the table")
    absent = [column for column in selections if column not in df.columns]
    if absent:
        raise KeyError(
            "selected trait column(s) not in the table: %s" % ", ".join(absent)
        )

    tagged = {}
    for _, row in df.iterrows():
        taxon = format_name(row[name_col])
        matched = []
        for column, wanted in selections.items():
            value = str(row[column]).strip()
            if value in wanted:
                matched.append(value)
        tagged[taxon] = " + ".join(matched)
    return tagged


def trait_label(selections: dict, max_length: int = 40) -> str:
    """Short label naming the selected states, for filenames and figure titles.

    Values are grouped by their column, which is how selections holds them, so the
    label reads as all the states from one trait and then all from the next. The UI
    lets one column appear in several rows, so the alternative would be whatever
    order the rows happened to be added in, which carries no meaning.

    Only the label is affected. Matching uses selections directly, and that is
    keyed by column either way.

    Spaces are removed rather than replaced, since the result goes into a path.
    Falls back to "Traits" when nothing was selected, or when the label collapses
    to nothing.
    """
    label = "_".join(
        str(value).replace(" ", "")
        for wanted in selections.values()
        for value in wanted
    )[:max_length]
    return label or "Traits"


# ========================================================== tree construction


def initialize_tree(tree_path, tagged_data: dict, algo_type: str) -> Tree:
    """Read a tree and give every tip the starting value one algorithm needs.

    A tip is foreground when its normalized name maps to a non-empty trait
    string. A name present with an empty string counts as matched but stays
    background, because the taxon was found in the metadata and simply carries no
    selected state.

    n_matched is a count and unmatched_leaves is a list of names; the names are
    what makes a systematic naming mismatch diagnosable rather than merely
    visible in the run report.

    Raises ValueError on an unrecognized algo_type. Falling through silently
    would leave the tips with no feature at all and fail much later, inside
    whichever algorithm was asked for.
    """
    if algo_type not in _TIP_FEATURE:
        raise ValueError(
            f"unknown algo_type {algo_type!r}; expected one of {ALGORITHMS}"
        )
    feature, (background_value, foreground_value) = _TIP_FEATURE[algo_type]

    tree = Tree(tree_path, format=1)
    matched = 0
    unmatched = []
    for leaf in tree.iter_leaves():
        key = format_name(leaf.name)
        if key in tagged_data:
            matched += 1
            is_foreground = tagged_data[key] != ""
        else:
            unmatched.append(leaf.name)
            is_foreground = False
        value = foreground_value if is_foreground else background_value
        leaf.add_feature(feature, set(value) if isinstance(value, set) else list(value))

    tree.add_feature("n_matched", matched)
    tree.add_feature("unmatched_leaves", unmatched)
    return tree


def extract_gene_from_filename(filename) -> str:
    """Base name for output files, taken from the manifest when the file is known.

    Falls back to the first underscore-separated token of the stem, uppercased,
    so a file that was never registered still produces a usable name.
    """
    organism, gene = manifest_logic_tab.resolve_identity(
        t1_st1_logic.CURRENT_PROJECT_PATH, filename
    )
    base = common_utils.make_base_name(organism, gene)
    if base and base != "UNKNOWN":
        return base
    return Path(filename).stem.split("_")[0].upper()


# ==================================================================== figures


def _branch_style(step_idx: int, f: int, m: int, votes: list) -> tuple:
    """Colour and line width for one branch at one step.

    Kept apart from the drawing so the colours have a single definition, shared
    with STEP_LEGEND.

    The consensus step tests the vote list rather than f and m directly, so a
    branch cannot be coloured as a consensus where one of the two abstained.
    """
    if step_idx == STEP_FITCH and f == FOREGROUND:
        return COLOR_FITCH, WIDTH_ACTIVE
    if step_idx == STEP_ML and m == FOREGROUND:
        return COLOR_ML, WIDTH_ACTIVE
    if (
        step_idx == STEP_CONSENSUS
        and len(votes) >= MIN_VOTES
        and sum(votes) == len(votes)
    ):
        return COLOR_CONSENSUS, WIDTH_CONSENSUS
    return COLOR_INACTIVE, WIDTH_INACTIVE


def _add_legend_cell(ts, item, box_column: int, text_column: int) -> None:
    """A colour swatch and its label, or two blanks.

    The blanks matter: the trait and branch legends are drawn side by side and
    can have different numbers of rows, so the shorter one has to keep filling
    its columns for the rows to stay aligned.
    """
    if item is None:
        ts.legend.add_face(TextFace(" "), column=box_column)
        ts.legend.add_face(TextFace(" "), column=text_column)
        return
    color, text, height = item
    box = RectFace(SWATCH_WIDTH, height, color, color)
    box.margin_right = 8
    box.margin_bottom = 4
    ts.legend.add_face(box, column=box_column)
    label = TextFace(text, fsize=11)
    label.margin_bottom = 4
    ts.legend.add_face(label, column=text_column)


def generate_step_figure(
    tree: Tree,
    file_path_base: str,
    step_idx: int,
    tagged_data: dict,
    no_signal: bool = False,
) -> None:
    """Render one step of the consensus as an SVG.

    Trait colours are assigned by first appearance in sorted order, so the same
    trait keeps its colour across all five figures of one run.

    Tip names are looked up through format_name, the same normalization
    initialize_tree used when it assigned the states. Comparing raw names here
    would leave a tip whose label contains whitespace drawn as background while
    the algorithms had treated it as foreground.
    """
    if not 0 <= step_idx < N_STEPS:
        raise ValueError(f"step_idx must be in 0..{N_STEPS - 1}, got {step_idx}")

    ts = TreeStyle()
    ts.show_leaf_name = False
    ts.margin_left, ts.margin_right, ts.margin_top, ts.margin_bottom = 50, 80, 60, 80

    title_face = TextFace(
        STEP_TITLES[step_idx], fsize=18, fgcolor=COLOR_TEXT, bold=True
    )
    title_face.margin_bottom = 20
    ts.title.add_face(title_face, column=0)

    if no_signal:
        warn = TextFace(
            "NO PHYLOGENETIC SIGNAL - DO NOT USE THESE BRANCH ASSIGNMENTS",
            fsize=15,
            fgcolor=COLOR_WARNING,
            bold=True,
        )
        warn.margin_top = 6
        warn.margin_bottom = 14
        ts.title.add_face(warn, column=0)

    unique_traits = sorted({val for val in tagged_data.values() if val != ""})
    trait_colors = {
        trait: TRAIT_PALETTE[i % len(TRAIT_PALETTE)]
        for i, trait in enumerate(unique_traits)
    }

    for node in tree.traverse():
        f = getattr(node, "f_state", BACKGROUND)
        m = getattr(node, "m_state", BACKGROUND)
        votes = _votes(f, m, getattr(node, "f_tie", DEFAULT_F_TIE))
        line_color, line_width = _branch_style(step_idx, f, m, votes)

        nstyle = NodeStyle()
        nstyle["shape"], nstyle["size"] = "circle", 0
        nstyle["hz_line_width"], nstyle["vt_line_width"] = line_width, line_width
        nstyle["hz_line_color"] = line_color
        nstyle["vt_line_color"] = line_color
        nstyle["fgcolor"] = line_color
        node.set_style(nstyle)

        actual_name = node.name.replace(FG_TAG, "")
        if node.is_leaf():
            node.add_face(
                CircleFace(radius=3, color=line_color, style="circle"),
                column=0,
                position="branch-right",
            )
            node.add_face(
                TextFace(
                    f" {actual_name}",
                    fsize=12,
                    fgcolor=COLOR_TEXT,
                    fstyle="Italic",
                ),
                column=1,
                position="branch-right",
            )
            trait_str = tagged_data.get(format_name(actual_name), "")
            box_color = trait_colors.get(trait_str, COLOR_NO_TRAIT)
            trait_box = RectFace(
                width=SWATCH_TRAIT,
                height=SWATCH_TRAIT,
                fgcolor=box_color,
                bgcolor=box_color,
            )
            trait_box.margin_left = 15
            node.add_face(trait_box, column=2, position="aligned")
        node.name = actual_name

    header_trait = TextFace("Trait Legend", fsize=12, bold=True)
    header_trait.margin_bottom = 8
    header_branch = TextFace("Branch Legend", fsize=12, bold=True)
    header_branch.margin_bottom = 8

    ts.legend.add_face(TextFace(" "), column=0)
    ts.legend.add_face(header_trait, column=1)
    ts.legend.add_face(TextFace("               "), column=2)
    ts.legend.add_face(TextFace(" "), column=3)
    ts.legend.add_face(header_branch, column=4)

    branch_items = list(STEP_LEGEND[step_idx])
    trait_items = [(trait_colors[t], t, SWATCH_TRAIT) for t in unique_traits]
    if not trait_items:
        trait_items = [(COLOR_NO_TRAIT, "No Target Selected", SWATCH_TRAIT)]

    for row in range(max(len(trait_items), len(branch_items))):
        _add_legend_cell(ts, trait_items[row] if row < len(trait_items) else None, 0, 1)
        ts.legend.add_face(TextFace(" "), column=2)
        _add_legend_cell(
            ts, branch_items[row] if row < len(branch_items) else None, 3, 4
        )

    footer = TextFace("Target Phenotype", fsize=11, fgcolor=COLOR_TEXT, bold=True)
    footer.rotation = 0
    footer.margin_top = 10
    footer.margin_left = 5
    ts.aligned_foot.add_face(footer, column=2)

    out_svg = f"{file_path_base}_step{step_idx}.svg"
    tree.render(out_svg, w=1000, units="px", tree_style=ts)
    if no_signal:
        add_svg_watermark(out_svg)


def _read_tree(nwk_file) -> Tree:
    """Parse a Newick file, retrying without the internal-name format.

    format=1 requires internal labels to be names rather than support values;
    trees written by other tools often violate that, and the default parser
    accepts them.
    """
    try:
        return Tree(nwk_file, format=1)
    except Exception:
        return Tree(nwk_file)


def render_all_steps(nwk_file, file_base_path, tagged_data, no_signal=False) -> None:
    """Draw one figure per step for one tree.

    A fresh tree is parsed for each step, because generate_step_figure attaches
    styles and rewrites node names in place.

    Scores are optional. If the file is absent or unreadable the figures are
    still drawn, with every branch inactive, rather than failing a whole run for
    want of a legend.

    A tree whose branches do not all appear in the scores is warned about rather
    than refused, for the same reason. The warning matters because the failure is
    otherwise invisible: taxon names are shared across genes, so drawing one
    gene's tree with another's scores matches every tip and leaves most internal
    clades unscored, and the figure comes out plausible but wrong.
    """
    score_data = []
    score_file = f"{file_base_path}_scores.json"
    if os.path.exists(score_file):
        try:
            with open(score_file, "r", encoding="utf-8") as fh:
                score_data = json.load(fh)
        except (OSError, ValueError) as exc:
            _log(f"Could not read scores from {score_file}: {exc}")

    by_clade = {frozenset(d["clade"]): d for d in score_data if "clade" in d}

    if by_clade:
        keys = [_clade_key(n) for n in _read_tree(nwk_file).traverse()]
        missing = [k for k in keys if k not in by_clade]
        if missing:
            n_tips = sum(1 for k in missing if len(k) == 1)
            _log(
                "%d of %d branches have no score and will be drawn inactive "
                "whatever their tag (%d tip, %d internal). Tree: %s. When the tips "
                "all match and the internal clades do not, the figure is being "
                "drawn on the wrong tree: it has to be the tree the scores were "
                "computed on."
                % (len(missing), len(keys), n_tips, len(missing) - n_tips, nwk_file)
            )

    for step_idx in range(N_STEPS):
        tree = _read_tree(nwk_file)
        for node in tree.traverse():
            scores = by_clade.get(_clade_key(node))
            if scores is None:
                continue
            node.add_feature("consensus_score", scores["score"])
            node.add_feature("f_state", scores["f"])
            node.add_feature("m_state", scores["m"])
            node.add_feature("prob_fg", scores.get("p_fg", DEFAULT_PROB_FG))
            node.add_feature("f_tie", scores.get("f_tie", DEFAULT_F_TIE))
        generate_step_figure(tree, file_base_path, step_idx, tagged_data, no_signal)


def add_svg_watermark(
    svg_path,
    text="NO PHYLOGENETIC SIGNAL",
    sub="ancestral states not recoverable",
    color="#FF3B30",
    opacity=0.22,
):
    """Overlay a diagonal warning across a rendered SVG.

    ete3 cannot draw over the tree canvas, so the text is injected into the
    finished file. The viewBox gives the canvas size, and the element is
    appended before </svg> so it paints on top of everything.
    """
    try:
        with open(svg_path, "r", encoding="utf-8") as fh:
            svg = fh.read()
    except OSError:
        return False

    m = re.search(r'viewBox="([\d.\-\s]+)"', svg)
    if not m:
        return False
    x0, y0, w, h = [float(v) for v in m.group(1).split()]
    cx, cy = x0 + w / 2, y0 + h / 2

    # Size from the diagonal so a wide short canvas still gets large text.
    # 0.55 approximates a sans-serif character advance, giving a string that
    # spans about 80 percent of the diagonal.
    diag = (w * w + h * h) ** 0.5
    size = max(24.0, diag * 0.80 / (max(len(text), 1) * 0.55))

    band = (
        '<g pointer-events="none" opacity="%.2f" transform="rotate(-30 %.2f %.2f)">'
        '<text x="%.2f" y="%.2f" text-anchor="middle" font-family="sans-serif" '
        'font-weight="bold" font-size="%.1f" fill="%s">%s</text>'
        '<text x="%.2f" y="%.2f" text-anchor="middle" font-family="sans-serif" '
        'font-size="%.1f" fill="%s">%s</text>'
        "</g>"
        % (
            opacity,
            cx,
            cy,
            cx,
            cy,
            size,
            color,
            text,
            cx,
            cy + size * 0.75,
            size * 0.42,
            color,
            sub,
        )
    )

    i = svg.rfind("</svg>")
    if i < 0:
        return False
    with open(svg_path, "w", encoding="utf-8") as fh:
        fh.write(svg[:i] + band + svg[i:])
    return True


ZERO_LEN = 1e-10  # HyPhy kill range upper bound; shorter is effectively zero


def zero_length_leaves(tree, threshold=ZERO_LEN):
    names = []
    for leaf in tree.iter_leaves():
        d = leaf.dist if leaf.dist is not None else 0.0
        if d < threshold:
            names.append(leaf.name)
    return names


# ================================================= ancestral state algorithms


def _remainder_costs(tree, down_feature: str, out_feature: str) -> None:
    """Least cost in the rest of the tree, for each state of each node.

    The complement of a downpass. `down_feature` holds, per node and state, the
    least cost in the subtree below it; this writes the least cost everywhere
    else. Every branch is counted in exactly one of the two, so their sum is the
    least cost over the whole tree given that state at that node.

    "Everywhere else" includes the sibling subtrees, not only the ancestral side.
    A sibling lies outside the node's own subtree, so its branches would
    otherwise be counted nowhere.

    The parent's own state is not fixed, so the cheapest is taken. The root has
    nothing above it and costs zero in either state.

    Costs come from UNIT_TRANSITION, which charges one for any change. Kept
    separate from fitch_states rather than inlined: the remainder cost is a pass
    in its own right, and it is what makes Fitch combine descendant with
    remainder information.
    """
    for node in tree.traverse("preorder"):
        if node.is_root():
            node.add_feature(out_feature, [0.0, 0.0])
            continue
        parent = node.up
        # A sibling's contribution depends only on the parent's state, so it is
        # computed once per parent state rather than once per pair of states.
        sibling_cost = [
            sum(
                min(
                    getattr(child, down_feature)[cs] + UNIT_TRANSITION[(ps, cs)]
                    for cs in (0, 1)
                )
                for child in parent.children
                if child is not node
            )
            for ps in (0, 1)
        ]
        above = getattr(parent, out_feature)
        node.add_feature(
            out_feature,
            [
                min(
                    above[ps] + sibling_cost[ps] + UNIT_TRANSITION[(ps, s)]
                    for ps in (0, 1)
                )
                for s in (0, 1)
            ],
        )


def fitch_states(tree) -> None:
    """Fitch parsimony states and MPR sets, written onto the tree in place.

    Two pairs of traversals. The first pair produces one state per node: a
    postorder pass builds a state set from the children, and a preorder pass
    resolves it against the parent. The second pair produces the set of states
    that occur in at least one most parsimonious reconstruction, which is what
    decides whether a node abstains from the consensus vote.

    The first pair cannot answer that on its own. Its state set reflects only a
    node's descendants and is never narrowed afterwards, so a node whose state
    the whole tree in fact determines can still read as ambiguous there.

    Requires initialize_tree(..., FITCH) to have set state_set on every tip.
    Branch lengths are not read at any point.

    Features written:
        state_set        postorder set, before the parent is consulted
        final_state      the single state used for tagging
        f_g, f_h         fewest changes below the node, and in the rest of the
                         tree, for each of the node's two states
        mpr_set          states minimising f_g + f_h
        f_mpr_tie        mpr_set holds both states
        f_downpass_tie   state_set held both states; kept for validation only
        f_tie            what the consensus vote reads, bound to f_mpr_tie
    """
    # First postorder pass: a state set from the children, by majority rule. The
    # intersection-or-union rule of the original formulation is not used: the two
    # agree at bifurcating nodes, but with three or more children the union rule
    # ignores how many children support each state and can keep both when one is
    # more parsimonious.
    for node in tree.traverse("postorder"):
        if node.is_leaf():
            continue
        counts = {BACKGROUND: 0, FOREGROUND: 0}
        for child in node.children:
            for state in child.state_set:
                counts[state] += 1
        top = max(counts.values())
        node.add_feature("state_set", {s for s, n in counts.items() if n == top})

    # First preorder pass: one state per node, taken from the parent when the
    # parent's state is in the node's set, which introduces no change along the
    # connecting branch.
    for node in tree.traverse("preorder"):
        if node.is_root():
            node.add_feature("final_state", min(node.state_set))
        else:
            parent_state = node.up.final_state
            node.add_feature(
                "final_state",
                parent_state if parent_state in node.state_set else min(node.state_set),
            )

    # Second postorder pass: f_g[s] is the fewest changes in the subtree below the
    # node, counting the branches to its children, given that the node is in state
    # s. A tip's observed state costs nothing and the alternative is infinite,
    # since a tip state is observed rather than inferred.
    for node in tree.traverse("postorder"):
        if node.is_leaf():
            observed = min(node.state_set)
            node.add_feature("f_g", [0 if s == observed else INF for s in (0, 1)])
        else:
            node.add_feature(
                "f_g",
                [
                    sum(
                        min(child.f_g[cs] + (0 if cs == s else 1) for cs in (0, 1))
                        for child in node.children
                    )
                    for s in (0, 1)
                ],
            )

    # Second preorder pass: f_h[s] is the fewest changes everywhere else, which
    # includes the sibling subtrees as well as the ancestral side. The unit cost
    # table is what makes this Fitch rather than a weighted parsimony.
    _remainder_costs(tree, "f_g", "f_h")

    # The two costs partition the tree: every branch is counted in exactly one of
    # them, so their sum is the fewest changes over the whole tree given that
    # state at that node. The states attaining the minimum form the MPR set.
    for node in tree.traverse():
        total = [node.f_g[s] + node.f_h[s] for s in (0, 1)]
        best = min(total)
        node.add_feature("mpr_set", {s for s in (0, 1) if total[s] == best})
        node.add_feature("f_mpr_tie", len(node.mpr_set) > 1)
        node.add_feature("f_downpass_tie", len(node.state_set) > 1)
        node.add_feature("f_tie", node.f_mpr_tie)


def resolve_mu(tree, tagged_data: dict, setting) -> tuple:
    """Transition rate for the ML model, estimated from the data or taken as given.

    Returns (mu, warnings, estimated). `setting` is either the string "auto" or a
    number.

    A copy is passed, because estimate_mu leaves its own intermediate values on
    the nodes it visits.

    Warnings are returned rather than logged, because the caller puts them in the
    run report and uses the first of them to decide whether to watermark the
    figures.
    """
    estimated = str(setting).lower() == "auto"
    if not estimated:
        return float(setting), [], False

    leaf_states = {
        leaf.name: (
            FOREGROUND if tagged_data.get(format_name(leaf.name), "") else BACKGROUND
        )
        for leaf in tree.iter_leaves()
    }
    mu, hit_ceiling = estimate_mu(tree.copy(), leaf_states)

    warnings = []
    if hit_ceiling:
        warnings.append(
            "Transition rate estimate reached the upper bound (mu=%.1f). The trait "
            "appears independent of the phylogeny; ancestral states are not "
            "recoverable and the confidence values below should not be "
            "interpreted." % mu
        )
    elif mu > MU_WEAK_SIGNAL:
        warnings.append(
            "Transition rate is high (mu=%.2f). Phylogenetic signal is weak and "
            "ancestral states are poorly determined." % mu
        )
    return mu, warnings, True


def ml_states(tree, mu: float) -> None:
    """Felsenstein marginal ancestral states, written onto the tree in place.

    Three traversals under the two-state symmetric model. The postorder pass gives
    each node the likelihood of the tips below it, for each of its own states. The
    preorder pass gives the likelihood of everything else, which as in the
    parsimony methods includes the sibling subtrees. Their product, normalised, is
    the marginal probability of foreground at that node.

    Each pair is divided by its own sum at every node, which keeps a deep tree from
    underflowing. That discards the absolute likelihood and keeps the ratio, which
    is all the marginal needs; estimate_mu accumulates the discarded scale factors
    separately, for its own purpose.

    Requires initialize_tree(..., FELSENSTEIN) to have set likelihood on every tip.
    Unlike Fitch, this reads branch lengths.

    Features written:
        likelihood   probability of the tips below the node, per state
        upper        probability of everything else, per state
        prob_fg      marginal probability that the node is foreground
        final_state  foreground when prob_fg exceeds one half
    """
    missing = [
        n.name or "unnamed" for n in tree.iter_leaves() if not hasattr(n, "likelihood")
    ]
    if missing:
        raise ValueError(
            f"{len(missing)} tip(s) have no likelihood; call "
            f"initialize_tree(..., {FELSENSTEIN!r}) first (e.g. {missing[:3]})"
        )

    def transition(dist):
        decay = math.exp(-2 * mu * (dist or 0.0))
        return 0.5 + 0.5 * decay, 0.5 - 0.5 * decay

    def combine(children):
        """Product over children of the transition times that child's likelihood."""
        bg = fg = 1.0
        for child in children:
            p_same, p_diff = transition(getattr(child, "dist", 0.0))
            child_bg, child_fg = child.likelihood
            bg *= p_same * child_bg + p_diff * child_fg
            fg *= p_diff * child_bg + p_same * child_fg
        return bg, fg

    def normalise(bg, fg):
        total = bg + fg
        return [bg / total, fg / total] if total > 0 else list(FLAT)

    for node in tree.traverse("postorder"):
        if node.is_leaf():
            continue
        node.add_feature("likelihood", normalise(*combine(node.children)))

    for node in tree.traverse("preorder"):
        if node.is_root():
            node.add_feature("upper", list(FLAT))
            continue
        parent = node.up
        above_bg, above_fg = parent.upper
        sibling_bg, sibling_fg = combine(
            [child for child in parent.children if child is not node]
        )
        p_same, p_diff = transition(getattr(node, "dist", 0.0))
        node.add_feature(
            "upper",
            normalise(
                above_bg * sibling_bg * p_same + above_fg * sibling_fg * p_diff,
                above_bg * sibling_bg * p_diff + above_fg * sibling_fg * p_same,
            ),
        )

    for node in tree.traverse("preorder"):
        down_bg, down_fg = node.likelihood
        up_bg, up_fg = node.upper
        marginal_bg, marginal_fg = down_bg * up_bg, down_fg * up_fg
        total = marginal_bg + marginal_fg
        prob_fg = marginal_fg / total if total > 0 else 0.5
        node.add_feature("prob_fg", prob_fg)
        node.add_feature("final_state", FOREGROUND if prob_fg > 0.5 else BACKGROUND)


def _clade_key(node):
    return frozenset(node.get_leaf_names())


def stochastic_map(tree, mu, n_sim=1000, seed=None, root_prior=(0.5, 0.5)) -> dict:
    """Sample ancestral state scenarios n_sim times.

    Requires the Felsenstein downpass to have run, so that every node carries a
    likelihood pair. Descends from the root, where the parent state has already
    been drawn, so the probability needed at a node is the parent-to-node
    transition times that node's downpass likelihood.

    Transition probabilities depend only on mu and a node's own branch length,
    never on which simulation is running, so they are computed once per node
    rather than once per node per simulation.

    Raises ValueError if a node has no likelihood. Substituting a flat pair there
    would turn the whole sample into coin flips while still returning numbers
    that look like results.
    """
    if n_sim < 1:
        raise ValueError(f"n_sim must be at least 1, got {n_sim}")

    nodes = list(tree.traverse("preorder"))
    missing = [n.name or "unnamed" for n in nodes if not hasattr(n, "likelihood")]
    if missing:
        raise ValueError(
            f"{len(missing)} node(s) have no likelihood; run the Felsenstein "
            f"downpass first (e.g. {missing[:3]})"
        )

    # Per node: its downpass likelihood pair, and the transition probabilities on
    # the branch above it under the two-state symmetric model.
    down, same, diff = {}, {}, {}
    for node in nodes:
        down[id(node)] = tuple(node.likelihood)
        dist = getattr(node, "dist", 0.0) or 0.0
        decay = math.exp(-2 * mu * dist)
        same[id(node)] = 0.5 + 0.5 * decay
        diff[id(node)] = 0.5 - 0.5 * decay

    rng = random.Random(seed)
    fg_count = {id(n): 0 for n in nodes}
    gains, losses = [], []

    for _ in range(n_sim):
        state = {}
        n_gain = n_loss = 0
        for node in nodes:
            key = id(node)
            lik_bg, lik_fg = down[key]
            if node.is_root():
                weight_bg = root_prior[0] * lik_bg
                weight_fg = root_prior[1] * lik_fg
                parent_state = None
            else:
                parent_state = state[id(node.up)]
                if parent_state == BACKGROUND:
                    weight_bg, weight_fg = same[key] * lik_bg, diff[key] * lik_fg
                else:
                    weight_bg, weight_fg = diff[key] * lik_bg, same[key] * lik_fg

            total = weight_bg + weight_fg
            # total is zero only if both likelihoods are zero, which the check
            # above should prevent; the even split keeps one bad node from
            # aborting the whole sample.
            p_fg = weight_fg / total if total > 0 else 0.5
            drawn = FOREGROUND if rng.random() < p_fg else BACKGROUND

            state[key] = drawn
            if drawn == FOREGROUND:
                fg_count[key] += 1
            if parent_state == BACKGROUND and drawn == FOREGROUND:
                n_gain += 1
            elif parent_state == FOREGROUND and drawn == BACKGROUND:
                n_loss += 1

        gains.append(n_gain)
        losses.append(n_loss)

    for node in nodes:
        node.add_feature("p_smap", fg_count[id(node)] / n_sim)

    # mean_changes is summed before dividing, not added from the two means.
    # The three are equal in exact arithmetic but not in floating point, and this
    # number goes into the run report.
    return {
        "n_sim": n_sim,
        "mean_gains": sum(gains) / n_sim,
        "mean_losses": sum(losses) / n_sim,
        "mean_changes": sum(g + l for g, l in zip(gains, losses)) / n_sim,
    }


# ================================================================== consensus


def _votes(f: int, m: int, f_tie: bool) -> list:
    """Calls from the methods that actually reached a decision.

    A tie is an abstention, not a vote for background. Fitch abstains when its
    MPR set holds both states. ML always votes, because P_FG is continuous and
    0.5 is a principled cut.

    With two methods and MIN_VOTES at two, a Fitch abstention therefore leaves
    too few votes for any branch to be tagged.
    """
    votes = []
    if not f_tie:
        votes.append(f)
    votes.append(m)
    return votes


def _consensus_call(
    votes: list,
    p_smap: float | None,
    threshold: float,
    min_votes: int = MIN_VOTES,
) -> bool:
    """Whether the voting methods agree that a branch is foreground.

    Every voter has to have said yes, the stochastic-map probability has to exceed
    the threshold, and at least min_votes methods have to have voted rather than
    abstained. A p_smap of None means the probability was never measured, and the
    gate is then skipped.

    There is no majority variant. With two voters more than half of them is both
    of them, so requiring unanimity and requiring a majority are the same rule,
    and keeping a switch between them would only invite the two to drift apart.
    """
    if len(votes) < min_votes:
        return False
    # Rejected at the threshold, not only below it. A branch whose sampled
    # probability lands exactly on the boundary is as much background as
    # foreground, and admitting it would make the verdict depend on which side
    # sampling noise happened to fall. Excluding it is both the conservative
    # reading and the deterministic one.
    #
    # None means the stochastic map did not run. That is a different state from a
    # measured 0.5, so the gate does not apply rather than rejecting every branch.
    if p_smap is not None and p_smap <= threshold:
        return False
    return sum(votes) == len(votes)


def _tree_loglik(tree, states_by_leaf: dict, mu: float) -> float:
    """Log-likelihood of the observed tip states under transition rate mu.

    A rescaled Felsenstein pruning pass: each internal node's pair is divided by
    its own sum and that sum accumulated as a log, which keeps the product from
    underflowing on a deep tree.

    Values are stored under _lk rather than `likelihood`, so a search over mu
    cannot overwrite the downpass results stochastic_map depends on.
    """
    for leaf in tree.iter_leaves():
        state = states_by_leaf.get(leaf.name, BACKGROUND)
        leaf.add_feature("_lk", [1.0, 0.0] if state == BACKGROUND else [0.0, 1.0])

    total = 0.0
    for node in tree.traverse("postorder"):
        if node.is_leaf():
            continue
        lik_bg = lik_fg = 1.0
        for child in node.children:
            dist = getattr(child, "dist", 0.0) or 0.0
            decay = math.exp(-2 * mu * dist)
            p_same, p_diff = 0.5 + 0.5 * decay, 0.5 - 0.5 * decay
            child_bg, child_fg = child._lk
            lik_bg *= p_same * child_bg + p_diff * child_fg
            lik_fg *= p_diff * child_bg + p_same * child_fg
        scale = lik_bg + lik_fg
        if scale <= 0:
            return LOGLIK_FLOOR
        total += math.log(scale)
        node.add_feature("_lk", [lik_bg / scale, lik_fg / scale])

    root_bg, root_fg = tree._lk
    return total + math.log(0.5 * root_bg + 0.5 * root_fg)


def estimate_mu(tree, states_by_leaf: dict, lo=0.01, hi=100.0, iters=70) -> tuple:
    """Golden-section search for the mu that maximises the likelihood.

    Returns (mu, hit_ceiling). Hitting the ceiling means the trait is distributed
    independently of the tree, so ancestral states are not recoverable and the
    caller should warn rather than report confident values.

    Each iteration discards one interior point and keeps the other, so only one
    new likelihood is needed per step. Recomputing both, as a direct reading of
    the algorithm invites, doubles the tree traversals for the same answer.
    """
    a, b = lo, hi
    c = b - GOLDEN_RATIO * (b - a)
    d = a + GOLDEN_RATIO * (b - a)
    f_c = _tree_loglik(tree, states_by_leaf, c)
    f_d = _tree_loglik(tree, states_by_leaf, d)

    for _ in range(iters):
        if f_c > f_d:
            b, d, f_d = d, c, f_c
            c = b - GOLDEN_RATIO * (b - a)
            f_c = _tree_loglik(tree, states_by_leaf, c)
        else:
            a, c, f_c = c, d, f_d
            d = a + GOLDEN_RATIO * (b - a)
            f_d = _tree_loglik(tree, states_by_leaf, d)

    mu = (a + b) / 2
    return mu, mu > hi * MU_CEILING_FRACTION


# ================================================================ run report


def _name_taxa(taxa) -> str:
    """A few taxon names, with the rest summarised as a count."""
    shown = ", ".join(taxa[:TAXA_SHOWN])
    if len(taxa) > TAXA_SHOWN:
        shown += ", +%d" % (len(taxa) - TAXA_SHOWN)
    return shown


def _info_row(taxa_count, taxa: str, note: str) -> dict:
    """A report row carrying a message rather than a branch call."""
    row = {column: "" for column in REPORT_COLUMNS}
    row["Node"] = "#INFO"
    row["Taxa_Count"] = taxa_count
    row["Taxa"] = taxa
    row["Note"] = note
    return row


def zero_leaf_notes(zero_leaves):
    if not zero_leaves:
        return []
    return [
        {
            "taxa_count": len(zero_leaves),
            "taxa": _name_taxa(zero_leaves),
            "note": "Zero-length leaf branch(es) \u2014 identical sequences",
        }
    ]


def build_scores(
    tree_f,
    by_clade_m: dict,
    prob_by_clade: dict,
    smap_by_clade: dict,
    tie_by_clade: dict,
    smap_threshold: float,
    tree_notes: list,
) -> tuple:
    """Per-branch scores for the figures, and the rows of the run report.

    Returns (score_data, report_rows). score_data is written to JSON and read back
    by the figures, so everything in it has to survive that round trip: no
    infinities, and clades as sorted lists rather than sets.

    Walks tree_f because both algorithms produced the same clades, which the
    caller has already checked. consensus_score and prob_fg are also attached to
    the nodes, for a caller that keeps the tree.

    Whether a method abstained is read from the vote list rather than tested a
    second time, so the report cannot claim a method voted when it did not.
    """
    score_data = []
    report_rows = [
        _info_row(item["taxa_count"], item["taxa"], item["note"]) for item in tree_notes
    ]
    node_number = 1

    for node in tree_f.traverse("preorder"):
        key = _clade_key(node)
        f = node.final_state
        m = by_clade_m[key]
        p_fg = prob_by_clade[key]
        p_smap = smap_by_clade[key]
        f_tie = bool(tie_by_clade[key])
        score = f + m
        votes = _votes(f, m, f_tie)
        n_yes = sum(votes)

        node.add_feature("consensus_score", score)
        node.add_feature("prob_fg", p_fg)
        score_data.append(
            {
                "score": score,
                "f": f,
                "m": m,
                "p_fg": p_fg,
                "p_smap": p_smap,
                "f_tie": f_tie,
                "n_yes": n_yes,
                "n_votes": len(votes),
                "clade": sorted(key),
            }
        )

        if node.is_leaf():
            continue

        taxa = sorted(key)
        notes = []
        if f_tie:
            notes.append("Fitch abstained (ambiguous)")
        if len(votes) < MIN_VOTES:
            notes.append("too few voters to decide")
        if WEAK_SUPPORT_LOW <= p_fg <= WEAK_SUPPORT_HIGH:
            notes.append("weak support")

        report_rows.append(
            {
                "Node": f"Node_{node_number}",
                "Taxa_Count": len(taxa),
                "Taxa": _name_taxa(taxa),
                "Selected": (
                    YES if _consensus_call(votes, p_smap, smap_threshold) else NO
                ),
                "Agreed": n_yes,
                "Voters": len(votes),
                "Fitch": YES if f == FOREGROUND else NO,
                "ML": YES if m == FOREGROUND else NO,
                "Confidence": round(p_fg, 3),
                "Note": "; ".join(notes),
            }
        )
        node_number += 1

    return score_data, report_rows


# ============================================================== tagged output


def _next_version(report_dir, stem: str) -> int:
    """One past the highest version already present for this gene and trait set.

    A filename whose version does not parse is skipped rather than counted as
    zero, which would let one stray file pin every later run to the same number.
    """
    versions = []
    for path in report_dir.glob(f"Rpt_{stem}_v*"):
        part = path.name.split("_v")[-1].split("_")[0]
        try:
            versions.append(int(part))
        except ValueError:
            continue
    return max(versions) + 1 if versions else 1


def step_dirs_for(trees_base_dir) -> list:
    """One output directory per step, created if absent, indexed by step."""
    dirs = [trees_base_dir / name for name in STEP_NAMES]
    for path in dirs:
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def _is_foreground(step: int, scores: dict, smap_threshold: float) -> bool:
    """Whether one branch carries the tag at one step.

    The first two steps report a single method. The last asks the methods that
    actually voted whether they agree.
    """
    if step == STEP_FITCH:
        return scores["f"] == FOREGROUND
    if step == STEP_ML:
        return scores["m"] == FOREGROUND
    votes = _votes(
        scores["f"],
        scores["m"],
        scores.get("f_tie", DEFAULT_F_TIE),
    )
    return _consensus_call(votes, scores.get("p_smap"), smap_threshold)


def _record_in_manifest(out_path, step_name: str, source_nwk, target_vars: str) -> None:
    """Register one output file with the project manifest.

    Failures are logged rather than raised. The tree has already been written and
    is usable; losing its manifest entry is worth a line in the error report but
    not worth failing the run over.
    """
    try:
        organism, gene = manifest_logic_tab.resolve_identity(
            t1_st1_logic.CURRENT_PROJECT_PATH, source_nwk
        )
        manifest_logic_tab.add_row(
            t1_st1_logic.CURRENT_PROJECT_PATH,
            organism,
            gene,
            target_vars,
            "tagged_" + step_name.lower(),
            str(out_path),
            source_nwk,
        )
    except Exception as exc:
        _log(f"Manifest entry failed for {out_path}: {exc}")


def write_step_trees(
    tree_f,
    score_data: list,
    step_dirs: list,
    stem: str,
    version: int,
    mmdd: str,
    smap_threshold: float,
    no_signal: bool,
    source_nwk,
    target_vars: str,
) -> list:
    """Write one tagged Newick per step and return the five strings.

    A fresh copy of the tree is tagged for each step, because the tag goes into
    the node names and would otherwise accumulate.

    ete3 writes an unnamed internal node as "NoName", which HyPhy would read as a
    taxon, so that string is removed before the file is written.

    The strings are returned as well as written, so the caller can hand them to
    the GUI without reading the files back.
    """
    by_clade = {frozenset(d["clade"]): d for d in score_data}
    warn_tag = NO_SIGNAL_TAG if no_signal else ""
    written = []

    for step, step_name in enumerate(STEP_NAMES):
        tree = tree_f.copy()
        for node in tree.traverse():
            scores = by_clade.get(_clade_key(node))
            if scores is None:
                continue
            base = re.sub(r"\{[^}]*\}", "", node.name or "")
            if _is_foreground(step, scores, smap_threshold):
                node.name = f"{base}{FG_TAG}" if base else FG_TAG
            else:
                node.name = base

        newick = tree.write(format=1).replace("NoName", "")
        written.append(newick)

        filename = f"{stem}_{step_name}{warn_tag}_v{version}_{mmdd}.nwk"
        out_path = step_dirs[step] / filename
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(newick)

        _record_in_manifest(out_path, step_name, source_nwk, target_vars)

    return written


def _index_by_clade(tree_f, tree_m) -> tuple:
    """Per-clade lookups from the ML tree, checked against Fitch's.

    The two algorithms run on separate copies of one tree, so their results are
    matched by clade rather than by node identity or number.

    Raises RuntimeError when the clades are not a usable key. Two things cause
    that and the tree looks fine in both: a node with a single child shares its
    clade with its parent, and a duplicated leaf name makes two tips share one.
    The message names whichever applies, because the two need different fixes.
    """
    keys = [_clade_key(n) for n in tree_f.traverse()]
    if len(keys) != len(set(keys)):
        leaf_names = tree_f.get_leaf_names()
        duplicated = sorted({n for n in leaf_names if leaf_names.count(n) > 1})
        if duplicated:
            raise RuntimeError(
                "Duplicated leaf name(s) in the tree: %s. Clade keys are not "
                "unique, so results cannot be matched across the two algorithms."
                % ", ".join(duplicated)
            )
        raise RuntimeError(
            "Tree has a node with a single child; clades are not unique."
        )

    by_clade_m = {_clade_key(n): n.final_state for n in tree_m.traverse()}
    prob_by_clade = {_clade_key(n): n.prob_fg for n in tree_m.traverse()}
    # None rather than a substituted 0.5: the consensus gate distinguishes
    # unmeasured from a measured 0.5, and this value goes straight into the scores
    # file that the figures read back.
    smap_by_clade = {
        _clade_key(n): getattr(n, "p_smap", None) for n in tree_m.traverse()
    }

    unmatched = [k for k in keys if k not in by_clade_m]
    if unmatched:
        raise RuntimeError(
            "Tree structures differ across algorithms (%d clades unmatched)"
            % len(unmatched)
        )
    return by_clade_m, prob_by_clade, smap_by_clade


def run_consensus_tagging(
    nwk_file, tagged_data, target_vars_str="Traits", algo_params=None
) -> dict:
    """Tag one tree by consensus of the two reconstruction methods.

    Returns a dict whose "status" is "success" or "error". Errors are returned
    rather than raised, because the caller is a GUI worker that has to keep
    running, and are also logged, so a caller that ignores the dict still leaves a
    trace.

    """
    # Caller values override the defaults key by key, so a partial dict does not
    # silently reinstate an older default for the keys it left out.
    params = dict(DEFAULT_ALGO_PARAMS)
    params.update(algo_params or {})

    base_res_dir = get_results_path()
    base_rep_dir = get_reports_path()
    if base_res_dir is None or base_rep_dir is None:
        return {
            "status": "error",
            "message": "No project is open, or its output directories could not be "
            "created.",
            "traceback": "",
        }

    gene_name = extract_gene_from_filename(nwk_file)
    safe_vars = "".join(c if c.isalnum() or c == "_" else "_" for c in target_vars_str)
    stem = f"{gene_name}_annotated_{safe_vars}"
    next_v = _next_version(base_rep_dir, stem)
    mmdd = datetime.datetime.now().strftime("%m%d")
    session_name = f"{stem}_v{next_v}_{mmdd}"

    figures_dir = base_res_dir / "Figures"
    trees_base_dir = base_res_dir / "Annotated_Trees"
    figures_dir.mkdir(parents=True, exist_ok=True)
    step_dirs = step_dirs_for(trees_base_dir)

    out_fig_base = figures_dir / f"{stem}_figure_v{next_v}_{mmdd}"
    out_report_csv = base_rep_dir / f"Rpt_{stem}_v{next_v}_{mmdd}.csv"

    try:
        tree_f = initialize_tree(nwk_file, tagged_data, FITCH)
        n_leaves = len(tree_f.get_leaves())
        n_matched = tree_f.n_matched
        unmatched = list(tree_f.unmatched_leaves)
        if n_matched == 0:
            raise RuntimeError(
                "No tree leaf matched the trait table (%d leaves). Check that leaf "
                "names and the CSV species column use the same form." % n_leaves
            )
        fitch_states(tree_f)

        tree_m = initialize_tree(nwk_file, tagged_data, FELSENSTEIN)
        mu, mu_warnings, mu_estimated = resolve_mu(
            tree_m, tagged_data, params["felsenstein_mu"]
        )
        ml_states(tree_m, mu)
        # Resampling is O(n_sim x nodes). Lower n_simulations if a large tree drags,
        # at the cost of stability near the gate; see test_nsim_stability.py.
        smap_stats = stochastic_map(
            tree_m,
            mu,
            n_sim=int(params["n_simulations"]),
            seed=params.get("smap_seed"),
        )
        smap_threshold = float(params["smap_threshold"])

        by_clade_m, prob_by_clade, smap_by_clade = _index_by_clade(tree_f, tree_m)
        tie_by_clade = {_clade_key(n): n.f_mpr_tie for n in tree_f.traverse()}

        tree_notes = zero_leaf_notes(zero_length_leaves(tree_f))
        score_data, report_rows = build_scores(
            tree_f,
            by_clade_m,
            prob_by_clade,
            smap_by_clade,
            tie_by_clade,
            smap_threshold,
            tree_notes,
        )

        with open(f"{out_fig_base}_scores.json", "w", encoding="utf-8") as fh:
            json.dump(score_data, fh)
        pd.DataFrame(report_rows, columns=list(REPORT_COLUMNS)).to_csv(
            out_report_csv, index=False
        )

        no_signal = any(NO_SIGNAL_PHRASE in w for w in mu_warnings)
        step_nwks = write_step_trees(
            tree_f,
            score_data,
            step_dirs,
            stem,
            next_v,
            mmdd,
            smap_threshold,
            no_signal,
            nwk_file,
            target_vars_str,
        )

        return {
            "status": "success",
            "nwk_steps": step_nwks,
            "out_fig_base": str(out_fig_base),
            "out_report_csv": str(out_report_csv),
            "tagged_data": tagged_data,
            "session_dir": str(trees_base_dir),
            "session_name": session_name,
            "n_leaves": n_leaves,
            "n_matched": n_matched,
            "unmatched_leaves": unmatched,
            "smap_stats": smap_stats,
            "mu_used": mu,
            "mu_estimated": mu_estimated,
            "mu_warnings": mu_warnings,
            "no_signal": no_signal,
            "tree_notes": tree_notes,
            "algo_params": params,
        }
    except Exception as exc:
        _log(f"Tagging failed for {nwk_file}: {exc}\n{traceback.format_exc()}")
        return {
            "status": "error",
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }


# ====================================================================== checks


def _demo() -> None:
    """Smallest check that fails if the stochastic-map gate breaks."""
    tree = Tree("((A:0.1,B:0.1):0.1,(C:0.1,D:0.1):0.1);", format=1)
    for leaf in tree.iter_leaves():
        # A tuple, not the string "AB": `name in "AB"` is a substring test and
        # would also accept "" and "AB" itself.
        is_fg = leaf.name in ("A", "B")
        leaf.add_feature("likelihood", [0.0, 1.0] if is_fg else [1.0, 0.0])
    for node in tree.traverse():
        if not node.is_leaf():
            node.add_feature("likelihood", [0.5, 0.5])

    stats = stochastic_map(tree, 1.0, n_sim=200, seed=1)
    assert stats["n_sim"] == 200 and stats["mean_changes"] >= 0
    assert all(0.0 <= node.p_smap <= 1.0 for node in tree.traverse())
    # A tagged leaf must sample foreground every time, an untagged one never.
    p = {leaf.name: leaf.p_smap for leaf in tree.iter_leaves()}
    assert p["A"] == p["B"] == 1.0 and p["C"] == p["D"] == 0.0, p
    # Same seed, same answer.
    assert stochastic_map(tree, 1.0, n_sim=200, seed=1) == stats

    assert _consensus_call([1, 1], 0.95, 0.9)
    assert not _consensus_call([1, 1], 0.85, 0.9)  # threshold gates
    assert not _consensus_call([1, 0], 0.95, 0.9)  # one dissent
    # Exactly on the boundary is refused, and an unmeasured probability skips the
    # gate rather than failing it.
    assert not _consensus_call([1, 1], 0.5, 0.5)
    assert _consensus_call([1, 1], 0.501, 0.5)
    assert _consensus_call([1, 1], None, 0.5)

    # Abstention: a tied method does not vote for background. ML never abstains,
    # so a Fitch tie leaves one vote, which is below MIN_VOTES; the branch cannot
    # be tagged whichever way ML fell.
    assert _votes(0, 1, True) == [1]  # Fitch tied, abstains
    assert _votes(0, 1, False) == [0, 1]  # no tie, both vote
    assert _consensus_call([1, 1], 0.95, 0.5)  # 2 of 2 passes
    assert not _consensus_call([1], 0.95, 0.5)  # 1 voter is not enough
    assert not _consensus_call(_votes(1, 1, True), 0.95, 0.5)  # Fitch tie vetoes

    # initialize_tree must refuse an algorithm it does not know, rather than
    # returning a tree whose tips carry no starting value at all.
    fd, nwk = tempfile.mkstemp(suffix=".nwk")
    os.close(fd)
    try:
        with open(nwk, "w", encoding="utf-8") as fh:
            fh.write("((A,B),(C,D));\n")
        try:
            initialize_tree(nwk, {}, "fich")
        except ValueError:
            pass
        else:
            raise AssertionError("a misspelled algo_type was accepted")
        # Tips must not share one mutable starting value, in either algorithm.
        for algo, feature in ((FITCH, "state_set"), (FELSENSTEIN, "likelihood")):
            t2 = initialize_tree(nwk, {"A": "FG"}, algo)
            values = [getattr(leaf, feature) for leaf in t2.iter_leaves()]
            assert len({id(v) for v in values}) == len(values), feature
    finally:
        os.unlink(nwk)

    print("ok")


if __name__ == "__main__":
    _demo()
