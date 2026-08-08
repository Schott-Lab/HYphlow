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

try:
    base = Path(sys._MEIPASS)
except Exception:
    base = Path(os.path.abspath("."))

CURRENT_PROJECT_PATH = base


def get_results_path():
    if not t1_st1_logic.CURRENT_PROJECT_PATH:
        return None
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    p = t1_st1_logic.CURRENT_PROJECT_PATH / "Results" / "Tree_Annotation" / today_str
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_reports_path():
    if not t1_st1_logic.CURRENT_PROJECT_PATH:
        return None
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    p = t1_st1_logic.CURRENT_PROJECT_PATH / "Reports" / "Tree_Annotation" / today_str
    p.mkdir(parents=True, exist_ok=True)
    return p


def format_name(name: str) -> str:
    return str(name).replace(" ", "_").strip()


def get_csv_headers(csv_path):
    try:
        return pd.read_csv(csv_path, nrows=0).columns.tolist()
    except:
        return []


def get_unique_values(csv_path, col_name):
    try:
        return [
            str(x)
            for x in pd.read_csv(csv_path, usecols=[col_name])[col_name]
            .dropna()
            .unique()
        ]
    except:
        return []


def initialize_tree(tree_path, tagged_data, algo_type):
    tree = Tree(tree_path, format=1)
    for leaf in tree.iter_leaves():
        trait_str = tagged_data.get(format_name(leaf.name), "")
        my_state = 1 if trait_str != "" else 0

        if algo_type == "fitch":
            leaf.add_feature("state_set", {my_state})
        elif algo_type == "sankoff":
            leaf.add_feature(
                "cost_array", [0, float("inf")] if my_state == 0 else [float("inf"), 0]
            )
        elif algo_type == "felsenstein":
            leaf.add_feature("likelihood", [1.0, 0.0] if my_state == 0 else [0.0, 1.0])
    return tree


def extract_gene_from_filename(filename):
    return Path(filename).name.split("_")[0].upper()


def generate_step_figure(
    tree: Tree, file_path_base: str, step_idx: int, tagged_data: dict
):
    ts = TreeStyle()
    ts.show_leaf_name = False
    ts.margin_left, ts.margin_right, ts.margin_top, ts.margin_bottom = 50, 80, 60, 80

    titles = [
        "HYphlow Step 1: Fitch Parsimony Prediction",
        "HYphlow Step 2: Sankoff Parsimony Prediction",
        "HYphlow Step 3: Felsenstein ML Prediction",
        "HYphlow Step 4: Two-Way Agreements (Majority Rule)",
        "HYphlow Step 5: Final Strict Consensus",
    ]

    title_face = TextFace(titles[step_idx], fsize=18, fgcolor="#1D1D1F", bold=True)
    title_face.margin_bottom = 20
    ts.title.add_face(title_face, column=0)

    unique_traits = sorted(list(set(val for val in tagged_data.values() if val != "")))
    palette = [
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
    ]
    trait_colors = {
        trait: palette[i % len(palette)] for i, trait in enumerate(unique_traits)
    }

    for node in tree.traverse():
        nstyle = NodeStyle()
        nstyle["shape"], nstyle["size"] = "circle", 0
        f, s, m = (
            getattr(node, "f_state", 0),
            getattr(node, "s_state", 0),
            getattr(node, "m_state", 0),
        )
        score = f + s + m
        actual_name = node.name.replace("{FG}", "")

        line_color, line_width = "#E5E5EA", 1

        if step_idx == 0 and f == 1:
            line_color, line_width = "#0071E3", 3
        elif step_idx == 1 and s == 1:
            line_color, line_width = "#34C759", 3
        elif step_idx == 2 and m == 1:
            line_color, line_width = "#AF52DE", 3
        elif step_idx == 3 and score >= 2:
            line_width = 3
            if score == 3:
                line_color, line_width = "#FF3B30", 4
            elif f == 1 and s == 1:
                line_color = "#00C7BE"
            elif f == 1 and m == 1:
                line_color = "#FF2D55"
            elif s == 1 and m == 1:
                line_color = "#E5C200"
        elif step_idx == 4 and score == 3:
            line_color, line_width = "#FF3B30", 4

        nstyle["hz_line_width"], nstyle["vt_line_width"] = line_width, line_width
        nstyle["hz_line_color"], nstyle["vt_line_color"], nstyle["fgcolor"] = (
            line_color,
            line_color,
            line_color,
        )
        node.set_style(nstyle)

        if node.is_leaf():
            node.add_face(
                CircleFace(radius=3, color=line_color, style="circle"),
                column=0,
                position="branch-right",
            )
            node.add_face(
                TextFace(
                    f" {actual_name}", fsize=12, fgcolor="#1D1D1F", fstyle="Italic"
                ),
                column=1,
                position="branch-right",
            )

            trait_str = tagged_data.get(actual_name, "")
            is_target = trait_str != ""
            box_color = (
                trait_colors.get(trait_str, "#F2F2F7") if is_target else "#F2F2F7"
            )

            trait_box = RectFace(
                width=16, height=16, fgcolor=box_color, bgcolor=box_color
            )
            trait_box.margin_left = 15
            node.add_face(trait_box, column=2, position="aligned")
        node.name = actual_name

    th_trait = TextFace("Trait Legend", fsize=12, bold=True)
    th_trait.margin_bottom = 8
    th_branch = TextFace("Branch Legend", fsize=12, bold=True)
    th_branch.margin_bottom = 8

    ts.legend.add_face(TextFace(" "), column=0)
    ts.legend.add_face(th_trait, column=1)
    ts.legend.add_face(TextFace("               "), column=2)
    ts.legend.add_face(TextFace(" "), column=3)
    ts.legend.add_face(th_branch, column=4)

    branch_items = []
    if step_idx == 0:
        branch_items.append(("#0071E3", "Fitch algorithm"))
    elif step_idx == 1:
        branch_items.append(("#34C759", "Sankoff algorithm"))
    elif step_idx == 2:
        branch_items.append(("#AF52DE", "Felsenstein algorithm"))
    elif step_idx == 3:
        branch_items.append(("#FF3B30", "Strict consensus branches"))
        branch_items.append(("#00C7BE", "Fitch + Sankoff"))
        branch_items.append(("#FF2D55", "Fitch + ML"))
        branch_items.append(("#E5C200", "Sankoff + ML"))
    elif step_idx == 4:
        branch_items.append(("#FF3B30", "Strict consensus branches"))

    trait_items = [(trait_colors[t], t) for t in unique_traits]
    if not trait_items:
        trait_items = [("#F2F2F7", "No Target Selected")]

    max_rows = max(len(trait_items), len(branch_items))
    for r in range(max_rows):
        if r < len(trait_items):
            color, text = trait_items[r]
            box = RectFace(16, 16, color, color)
            box.margin_right = 8
            box.margin_bottom = 4
            ts.legend.add_face(box, column=0)
            tf = TextFace(text, fsize=11)
            tf.margin_bottom = 4
            ts.legend.add_face(tf, column=1)
        else:
            ts.legend.add_face(TextFace(" "), column=0)
            ts.legend.add_face(TextFace(" "), column=1)

        ts.legend.add_face(TextFace(" "), column=2)

        if r < len(branch_items):
            color, text = branch_items[r]
            h = 8 if "consensus" in text.lower() else 6
            box = RectFace(16, h, color, color)
            box.margin_right = 8
            box.margin_bottom = 4
            ts.legend.add_face(box, column=3)
            tf = TextFace(text, fsize=11)
            tf.margin_bottom = 4
            ts.legend.add_face(tf, column=4)
        else:
            ts.legend.add_face(TextFace(" "), column=3)
            ts.legend.add_face(TextFace(" "), column=4)

    footer = TextFace("Target Phenotype", fsize=11, fgcolor="#1D1D1F", bold=True)
    footer.rotation = 0
    footer.margin_top = 10
    footer.margin_left = 5
    ts.aligned_foot.add_face(footer, column=2)

    tree.render(
        f"{file_path_base}_step{step_idx}.svg", w=1000, units="px", tree_style=ts
    )


def render_all_steps(nwk_file, file_base_path, tagged_data):
    score_data = []
    score_file = f"{file_base_path}_scores.json"
    if os.path.exists(score_file):
        with open(score_file, "r") as f:
            score_data = json.load(f)

    for step_idx in range(5):
        try:
            t = Tree(nwk_file, format=1)
        except:
            t = Tree(nwk_file)
        if score_data:
            for n, d in zip(t.traverse("preorder"), score_data):
                n.add_feature("consensus_score", d["score"])
                n.add_feature("f_state", d["f"])
                n.add_feature("s_state", d["s"])
                n.add_feature("m_state", d["m"])
        generate_step_figure(t, file_base_path, step_idx, tagged_data)


def run_consensus_tagging(
    nwk_file, tagged_data, target_vars_str="Traits", algo_params=None
):
    if algo_params is None:
        algo_params = {"sankoff_gain": 2.0, "sankoff_loss": 1.0, "felsenstein_mu": 1.0}

    base_res_dir = get_results_path()
    base_rep_dir = get_reports_path()

    gene_name = extract_gene_from_filename(nwk_file)
    safe_vars = "".join(
        [c if c.isalnum() or c in ["_"] else "_" for c in target_vars_str]
    )

    v_nums = []
    for p in base_rep_dir.glob(f"Rpt_{gene_name}_annotated_{safe_vars}_v*"):
        try:
            v_part = p.name.split("_v")[-1].split("_")[0]
            v_nums.append(int(v_part))
        except:
            pass
    next_v = max(v_nums) + 1 if v_nums else 1
    mmdd = datetime.datetime.now().strftime("%m%d")

    session_name = f"{gene_name}_annotated_{safe_vars}_v{next_v}_{mmdd}"

    figures_dir = base_res_dir / "Figures"
    trees_base_dir = base_res_dir / "Annotated_Trees"

    figures_dir.mkdir(parents=True, exist_ok=True)

    step_dirs = {
        0: trees_base_dir / "Fitch",
        1: trees_base_dir / "Sankoff",
        2: trees_base_dir / "Felsenstein",
        3: trees_base_dir / "Majority_Consensus",
        4: trees_base_dir / "Strict_Consensus",
    }

    for s_dir in step_dirs.values():
        s_dir.mkdir(parents=True, exist_ok=True)

    out_fig_base = (
        figures_dir / f"{gene_name}_annotated_{safe_vars}_figure_v{next_v}_{mmdd}"
    )
    out_report_csv = (
        base_rep_dir / f"Rpt_{gene_name}_annotated_{safe_vars}_v{next_v}_{mmdd}.csv"
    )

    try:
        tree_f = initialize_tree(nwk_file, tagged_data, "fitch")
        for node in tree_f.traverse("postorder"):
            if not node.is_leaf():
                inter = set.intersection(*[c.state_set for c in node.children])
                node.add_feature(
                    "state_set",
                    (
                        inter
                        if inter
                        else set.union(*[c.state_set for c in node.children])
                    ),
                )
        for node in tree_f.traverse("preorder"):
            if node.is_root():
                node.add_feature("final_state", min(node.state_set))
            else:
                p_state = getattr(node.up, "final_state", min(node.state_set))
                node.add_feature(
                    "final_state",
                    p_state if p_state in node.state_set else min(node.state_set),
                )

        tree_s = initialize_tree(nwk_file, tagged_data, "sankoff")
        s_gain, s_loss = algo_params["sankoff_gain"], algo_params["sankoff_loss"]
        for node in tree_s.traverse("postorder"):
            if not node.is_leaf():
                c_costs = [
                    getattr(c, "cost_array", [float("inf"), float("inf")])
                    for c in node.children
                ]
                node.add_feature(
                    "cost_array",
                    [
                        sum([min(c[0] + 0, c[1] + s_gain) for c in c_costs]),
                        sum([min(c[0] + s_loss, c[1] + 0) for c in c_costs]),
                    ],
                )
        for node in tree_s.traverse("preorder"):
            c0, c1 = getattr(node, "cost_array", [0, 0])
            node.add_feature("final_state", 0 if c0 <= c1 else 1)

        tree_m = initialize_tree(nwk_file, tagged_data, "felsenstein")
        mu = algo_params["felsenstein_mu"]
        for node in tree_m.traverse("postorder"):
            if not node.is_leaf():
                L_0, L_1 = 1.0, 1.0
                for c in node.children:
                    t_dist = getattr(c, "dist", 0.0) or 0.0
                    p_same, p_diff = 0.5 + 0.5 * math.exp(
                        -2 * mu * t_dist
                    ), 0.5 - 0.5 * math.exp(-2 * mu * t_dist)
                    cL0, cL1 = getattr(c, "likelihood", [0.5, 0.5])
                    L_0 *= (p_same * cL0) + (p_diff * cL1)
                    L_1 *= (p_diff * cL0) + (p_same * cL1)
                node.add_feature("likelihood", [L_0, L_1])
        for node in tree_m.traverse("preorder"):
            L_0, L_1 = getattr(node, "likelihood", [0.5, 0.5])
            node.add_feature("final_state", 1 if L_1 > L_0 else 0)

        nodes_f = list(tree_f.traverse("preorder"))
        nodes_s = list(tree_s.traverse("preorder"))
        nodes_m = list(tree_m.traverse("preorder"))

        score_data, report_rows = [], []
        node_id_counter = 1

        for i in range(len(nodes_f)):
            f, s, m = (
                nodes_f[i].final_state,
                nodes_s[i].final_state,
                nodes_m[i].final_state,
            )
            score = f + s + m
            nodes_f[i].add_feature("consensus_score", score)
            score_data.append({"score": score, "f": f, "s": s, "m": m})

            if not nodes_f[i].is_leaf():
                report_rows.append(
                    {
                        "Node_ID": f"Ancestor_Node_{node_id_counter}",
                        "Fitch": "YES" if f == 1 else "NO",
                        "Sankoff": "YES" if s == 1 else "NO",
                        "ML": "YES" if m == 1 else "NO",
                        "Score": score,
                        "Strict_Consensus": "YES" if score == 3 else "NO",
                    }
                )
                node_id_counter += 1

        with open(f"{out_fig_base}_scores.json", "w") as f:
            json.dump(score_data, f)
        pd.DataFrame(report_rows).to_csv(out_report_csv, index=False)

        step_nwks = []
        step_names = [
            "Fitch",
            "Sankoff",
            "Felsenstein",
            "Majority_Consensus",
            "Strict_Consensus",
        ]

        for step in range(5):
            t_copy = tree_f.copy()
            for node, scores in zip(t_copy.traverse("preorder"), score_data):
                f, s, m, score = scores["f"], scores["s"], scores["m"], scores["score"]
                is_fg = False
                if step == 0 and f == 1:
                    is_fg = True
                elif step == 1 and s == 1:
                    is_fg = True
                elif step == 2 and m == 1:
                    is_fg = True
                elif step == 3 and score >= 2:
                    is_fg = True
                elif step == 4 and score == 3:
                    is_fg = True

                if is_fg:
                    node.name = f"{node.name}{{FG}}" if node.name else "{FG}"

            raw_nwk = t_copy.write(format=1)
            clean_nwk = raw_nwk.replace("NoName", "")
            step_nwks.append(clean_nwk)

            out_filename = f"{gene_name}_annotated_{safe_vars}_{step_names[step]}_v{next_v}_{mmdd}.nwk"
            target_save_dir = step_dirs[step]
            with open(target_save_dir / out_filename, "w") as file:
                file.write(clean_nwk)

        return {
            "status": "success",
            "nwk_steps": step_nwks,
            "out_fig_base": str(out_fig_base),
            "out_report_csv": str(out_report_csv),
            "tagged_data": tagged_data,
            "session_dir": str(trees_base_dir),
            "session_name": session_name,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }
