import re
import json
import datetime
import traceback
from pathlib import Path
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtCore import QThread, pyqtSignal

from hyphlow import common_utils
from hyphlow.t2_tagging_logic import STEP_NAMES


def _identity_from_json_name(json_name):
    """Recover (organism, gene, tag) from a HyPhy result filename.

    Names look like ORGANISM_GENE_annotated_TAG_Strict_Consensus_v1_0801_MODEL.
    The tag may itself contain underscores, so it is read as everything between
    _annotated_ and the consensus-step marker rather than as a single token.
    """
    stem = Path(json_name).stem

    tag = "UNPARSED"
    m = re.search(r"_annotated_(.+?)_(?:%s)" % "|".join(STEP_NAMES), stem)
    if m:
        tag = m.group(1)
        head = stem[: m.start()]
    else:
        head = re.split(r"_annotated_", stem)[0]

    # head is ORGANISM_GENE. The gene is the uppercase token; whatever comes
    # before it is the organism.
    tokens = [t for t in head.split("_") if t]
    gene, organism = "", ""
    for i, t in enumerate(tokens):
        if common_utils._is_gene_like(t):
            gene = t.upper()
            organism = "_".join(tokens[:i])
            break
    if not gene and tokens:
        gene = tokens[-1].upper()
        organism = "_".join(tokens[:-1])

    return organism, gene, tag


class SummaryExportThread(QThread):
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, json_files, output_dir, custom_name=""):
        super().__init__()
        self.json_files = json_files
        self.output_dir = Path(output_dir)
        self.custom_name = custom_name

    def _extract_omega_3(self, dist_dict):
        try:
            target = dist_dict.get("2", dist_dict.get("Test", {}).get("2", {}))
            if not target and isinstance(dist_dict, dict):
                keys = list(dist_dict.keys())
                if len(keys) >= 3:
                    target = dist_dict[keys[-1]]
                elif len(keys) > 0:
                    target = dist_dict[keys[-1]]

            if (
                isinstance(target, dict)
                and "omega" in target
                and "proportion" in target
            ):
                om = target["omega"]
                pr = target["proportion"] * 100
                return f"{om:.4f} ({pr:.2f}%)"
            return ""
        except Exception:
            return ""

    def _create_master_folder_and_excel_path(self):
        clean_custom = re.sub(r'[\\/*?:"<>|]', "", self.custom_name.strip())
        prefix = f"HYphlow_{clean_custom}_" if clean_custom else "HYphlow_"
        mmdd = datetime.datetime.now().strftime("%m%d")
        v_num = 1

        while True:
            folder_name = f"{prefix}summary_{mmdd}_v{v_num}"
            master_folder = self.output_dir / folder_name
            if not master_folder.exists():
                master_folder.mkdir(parents=True)
                excel_name = f"{prefix}result_summary_{mmdd}_v{v_num}.xlsx"
                return master_folder, master_folder / excel_name
            v_num += 1

    def run(self):
        errors = []
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            master_folder, save_path = self._create_master_folder_and_excel_path()

            results_by_model = {
                "BUSTED": [],
                "aBSREL": [],
                "RELAX": [],
                "Site_Models": [],
            }
            master_data = []

            grouped_runs = {}
            for f in self.json_files:
                fname = Path(f).name
                match = re.search(r"(.*)_run(\d+)\.JSON$", fname, re.IGNORECASE)
                if match:
                    base_key = match.group(1)
                    run_id = int(match.group(2))
                else:
                    base_key = fname.replace(".JSON", "").replace(".json", "")
                    run_id = 1

                if base_key not in grouped_runs:
                    grouped_runs[base_key] = {
                        "files": {},
                        "aics": {},
                        "best_run": None,
                        "best_file": None,
                    }

                grouped_runs[base_key]["files"][run_id] = f

            for base_key, group in grouped_runs.items():
                min_aic = float("inf")
                best_run = None
                for run_id, f_path in group["files"].items():
                    try:
                        with open(f_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        fits = data.get("fits", {})

                        aic = float("inf")
                        if "Unconstrained model" in fits:
                            aic = fits["Unconstrained model"].get("AIC-c", float("inf"))
                        elif "RELAX alternative" in fits:
                            aic = fits["RELAX alternative"].get("AIC-c", float("inf"))
                        else:
                            for k, v in fits.items():
                                if isinstance(v, dict) and "AIC-c" in v:
                                    aic = v["AIC-c"]
                                    break

                        group["aics"][f"AIC_Run{run_id}"] = aic
                        if aic < min_aic:
                            min_aic = aic
                            best_run = run_id
                            group["best_file"] = f_path
                    except Exception:
                        pass
                group["best_run"] = best_run

            best_files_to_process = [
                g["best_file"] for g in grouped_runs.values() if g["best_file"]
            ]
            total_files = len(best_files_to_process)

            for idx, file_path in enumerate(best_files_to_process):
                self.progress_update.emit(
                    int((idx / total_files) * 100), f"Parsing {Path(file_path).name}..."
                )

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    model_info = data.get("analysis", {}).get("info", "")
                    base_name = Path(file_path).name
                    organism_name, gene_name, fg_tag = _identity_from_json_name(
                        base_name
                    )

                    detected_model = "Unknown"
                    known_models = [
                        "BUSTED",
                        "aBSREL",
                        "RELAX",
                        "FEL",
                        "MEME",
                        "FUBAR",
                        "SLAC",
                    ]
                    for m in known_models:
                        if (
                            m.upper() in base_name.upper()
                            or m.upper() in model_info.upper()
                        ):
                            detected_model = m if m != "aBSREL" else "aBSREL"
                            break

                    if detected_model == "Unknown":
                        raise ValueError(
                            "Could not detect any known HyPhy model from file."
                        )

                    group_data = None
                    for k, g in grouped_runs.items():
                        if g["best_file"] == file_path:
                            group_data = g
                            break

                    pval_master = data.get("test results", {}).get(
                        "p-value", data.get("test results", {}).get("P-value", "")
                    )
                    sig_master = (
                        "Significant"
                        if isinstance(pval_master, (int, float)) and pval_master < 0.05
                        else "Not Significant"
                    )

                    master_row = {
                        "Model": detected_model,
                        "File Name": base_name,
                        "Organism": organism_name,
                        "Gene Name": gene_name,
                        "FG Tag": fg_tag,
                        "AIC_Run1": (
                            group_data["aics"].get("AIC_Run1", "") if group_data else ""
                        ),
                        "AIC_Run2": (
                            group_data["aics"].get("AIC_Run2", "") if group_data else ""
                        ),
                        "AIC_Run3": (
                            group_data["aics"].get("AIC_Run3", "") if group_data else ""
                        ),
                        "Best_Run": (
                            f"Run{group_data['best_run']}"
                            if group_data and group_data["best_run"]
                            else "Run1"
                        ),
                        "p-value": pval_master,
                        "Significance": sig_master,
                    }
                    master_data.append(master_row)

                    common_data = {
                        "File Name": base_name,
                        "Organism": organism_name,
                        "Gene Name": gene_name,
                        "FG Tag": fg_tag,
                        "Sequences": data.get("input", {}).get(
                            "number of sequences", ""
                        ),
                        "Sites": data.get("input", {}).get("number of sites", ""),
                    }

                    if detected_model == "BUSTED":
                        fits = data.get("fits", {})
                        for m_name in ["Unconstrained model", "Constrained model"]:
                            m_data = fits.get(m_name, {})
                            if not m_data:
                                for sub in ["Tested", "Background", "Synonymous"]:
                                    row = common_data.copy()
                                    row.update(
                                        {
                                            "Model": "BUSTED",
                                            "Sub_Model": m_name,
                                            "Distribution": sub,
                                        }
                                    )
                                    results_by_model["BUSTED"].append(row)
                                continue

                            logl = m_data.get("Log Likelihood", "")
                            aic = m_data.get("AIC-c", "")
                            params = m_data.get("estimated parameters", "")
                            dists = m_data.get("Rate Distributions", {})

                            dist_map = {
                                "Tested": dists.get("Test", {}),
                                "Background": dists.get("Background", {}),
                                "Synonymous": dists.get(
                                    "Synonymous", dists.get("Synonymous rates", {})
                                ),
                            }

                            for sub, d_val in dist_map.items():
                                row = common_data.copy()
                                row.update(
                                    {
                                        "Model": "BUSTED",
                                        "Sub_Model": m_name,
                                        "Distribution": sub,
                                        "Log(L)": logl,
                                        "AIC-c": aic,
                                        "Params": params,
                                        "p-value": pval_master,
                                        "Significance": sig_master,
                                        "Omega_3": (
                                            self._extract_omega_3(d_val)
                                            if d_val
                                            else ""
                                        ),
                                    }
                                )
                                results_by_model["BUSTED"].append(row)

                    elif detected_model == "RELAX":
                        fits = data.get("fits", {})
                        tr = data.get("test results", {})
                        k_val = tr.get("relaxation or intensification parameter", "")
                        sel_pat = (
                            "Intensification"
                            if isinstance(k_val, (int, float)) and k_val > 1
                            else "Relaxation" if isinstance(k_val, (int, float)) else ""
                        )

                        for m_name in ["RELAX null", "RELAX alternative"]:
                            m_data = fits.get(m_name, {})
                            if not m_data:
                                for sub in ["Reference", "Test"]:
                                    row = common_data.copy()
                                    row.update(
                                        {
                                            "Model": "RELAX",
                                            "Sub_Model": m_name,
                                            "Branch": sub,
                                            "K_Value": k_val,
                                            "Selection": sel_pat,
                                        }
                                    )
                                    results_by_model["RELAX"].append(row)
                                continue

                            logl = m_data.get("Log Likelihood", "")
                            aic = m_data.get("AIC-c", "")
                            params = m_data.get("estimated parameters", "")
                            dists = m_data.get("Rate Distributions", {})

                            for sub in ["Reference", "Test"]:
                                row = common_data.copy()
                                row.update(
                                    {
                                        "Model": "RELAX",
                                        "Sub_Model": m_name,
                                        "Branch": sub,
                                        "Log(L)": logl,
                                        "AIC-c": aic,
                                        "Params": params,
                                        "p-value": pval_master,
                                        "Significance": sig_master,
                                        "K_Value": k_val,
                                        "Selection": sel_pat,
                                        "Omega_3": self._extract_omega_3(
                                            dists.get(sub, {})
                                        ),
                                    }
                                )
                                results_by_model["RELAX"].append(row)

                    elif detected_model == "aBSREL":
                        row = common_data.copy()
                        row["Model"] = "aBSREL"
                        row["Tested Lineages"] = data.get("test results", {}).get(
                            "tested", 0
                        )
                        pos_lineages = data.get("test results", {}).get(
                            "positive test results", 0
                        )
                        row["Positive Lineages"] = pos_lineages
                        row["Significance"] = (
                            "Significant" if pos_lineages > 0 else "Not Significant"
                        )

                        sig_branches = []
                        branch_attrs = data.get("branch attributes", {})
                        branches = {}
                        if branch_attrs:
                            first_key = list(branch_attrs.keys())[0]
                            branches = branch_attrs.get(first_key, {})

                        for node, attr in branches.items():
                            if attr.get("Corrected P-value", 1) < 0.05:
                                sig_branches.append(node)
                        row["Significant Branches"] = ", ".join(sig_branches)
                        row["p-value"] = pval_master
                        results_by_model["aBSREL"].append(row)

                    elif detected_model in ["FEL", "MEME", "FUBAR", "SLAC"]:
                        row = common_data.copy()
                        row["Model"] = detected_model
                        headers = data.get("MLE", {}).get("headers", [])
                        content_dict = data.get("MLE", {}).get("content", {})
                        content = []
                        if content_dict:
                            first_key = list(content_dict.keys())[0]
                            content = content_dict.get(first_key, [])

                        pval_idx = -1
                        for i, h in enumerate(headers):
                            if "p-value" in h[0].lower() or "posterior" in h[0].lower():
                                pval_idx = i
                                break

                        sig_sites = []
                        if pval_idx != -1:
                            for i, c_row in enumerate(content):
                                val = c_row[pval_idx]
                                if (
                                    "posterior" in headers[pval_idx][0].lower()
                                    and val >= 0.9
                                ) or (
                                    "p-value" in headers[pval_idx][0].lower()
                                    and val < 0.05
                                ):
                                    sig_sites.append(str(i + 1))

                        row["Tested Sites"] = len(content)
                        row["Significant Sites Count"] = len(sig_sites)
                        row["Significance"] = (
                            "Significant" if len(sig_sites) > 0 else "Not Significant"
                        )
                        row["Significant Sites List"] = ", ".join(sig_sites)
                        row["p-value"] = pval_master
                        results_by_model["Site_Models"].append(row)

                except Exception as e:
                    errors.append(
                        {
                            "file": file_path,
                            "error": str(e),
                            "type": type(e).__name__,
                            "traceback": traceback.format_exc(),
                        }
                    )

            if not master_data:
                self.finished.emit(
                    {
                        "status": "error",
                        "message": "No valid data to export.",
                        "type": "NoValidData",
                        "traceback": "All parsed rows were empty.",
                        "errors": errors,
                    }
                )
                return

            self.progress_update.emit(90, "Writing Excel file...")

            try:
                df_master = pd.DataFrame(master_data).sort_values(by="Model")

                with pd.ExcelWriter(save_path, engine="xlsxwriter") as writer:
                    workbook = writer.book
                    fmt_header = workbook.add_format(
                        {"bold": True, "bg_color": "#FAFAFA", "border": 1}
                    )
                    fmt_sig = workbook.add_format(
                        {"bg_color": "#FFFF99", "font_color": "#FF0000"}
                    )
                    fmt_best_aic = workbook.add_format({"bg_color": "#E5FFE5"})
                    fmt_thick_bottom = workbook.add_format({"bottom": 2})
                    fmt_thin_bottom = workbook.add_format({"bottom": 1})

                    df_master.to_excel(
                        writer, sheet_name="p-value summary", index=False
                    )
                    ws_master = writer.sheets["p-value summary"]
                    for col_num, value in enumerate(df_master.columns.values):
                        ws_master.write(0, col_num, value, fmt_header)
                        ws_master.set_column(col_num, col_num, 15)

                    for row_idx, row in df_master.iterrows():
                        xls_row = row_idx + 1
                        pval = row.get("p-value", "")
                        is_sig = isinstance(pval, (int, float)) and pval < 0.05

                        if is_sig:
                            ws_master.write(
                                xls_row,
                                df_master.columns.get_loc("p-value"),
                                pval,
                                fmt_sig,
                            )
                            ws_master.write(
                                xls_row,
                                df_master.columns.get_loc("Significance"),
                                row.get("Significance", ""),
                                fmt_sig,
                            )

                        aic_cols = [
                            c for c in df_master.columns if c.startswith("AIC_Run")
                        ]
                        aic_vals = [
                            row[c] for c in aic_cols if isinstance(row[c], (int, float))
                        ]
                        if aic_vals:
                            min_aic = min(aic_vals)
                            for c in aic_cols:
                                if row[c] == min_aic:
                                    ws_master.write(
                                        xls_row,
                                        df_master.columns.get_loc(c),
                                        row[c],
                                        fmt_best_aic,
                                    )

                        if row_idx < len(df_master) - 1:
                            if (
                                df_master.iloc[row_idx]["Model"]
                                != df_master.iloc[row_idx + 1]["Model"]
                            ):
                                ws_master.set_row(xls_row, None, fmt_thick_bottom)

                    for sheet_name, rows in results_by_model.items():
                        if not rows:
                            continue

                        df = pd.DataFrame(rows)
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                        worksheet = writer.sheets[sheet_name]

                        for col_num, col_name in enumerate(df.columns):
                            worksheet.write(0, col_num, col_name, fmt_header)
                            worksheet.set_column(
                                col_num, col_num, max(len(col_name) + 5, 15)
                            )

                        prev_file = ""
                        prev_sub = ""
                        for row_idx, row in df.iterrows():
                            xls_row = row_idx + 1
                            pval = row.get("p-value", "")
                            if isinstance(pval, (int, float)) and pval < 0.05:
                                if "p-value" in df.columns:
                                    worksheet.write(
                                        xls_row,
                                        df.columns.get_loc("p-value"),
                                        pval,
                                        fmt_sig,
                                    )
                                if "Significance" in df.columns:
                                    worksheet.write(
                                        xls_row,
                                        df.columns.get_loc("Significance"),
                                        row.get("Significance", ""),
                                        fmt_sig,
                                    )

                            curr_file = row.get("File Name", "")
                            curr_sub = row.get("Sub_Model", "")

                            if row_idx > 0:
                                if curr_file != prev_file:
                                    worksheet.set_row(
                                        xls_row - 1, None, fmt_thick_bottom
                                    )
                                elif curr_sub != prev_sub:
                                    worksheet.set_row(
                                        xls_row - 1, None, fmt_thin_bottom
                                    )
                            prev_file = curr_file
                            prev_sub = curr_sub

            except PermissionError:
                raise PermissionError(
                    "The Excel file is currently open. Please close it and try again."
                )

            self.progress_update.emit(100, "Done!")
            self.finished.emit(
                {"status": "success", "path": str(save_path), "errors": errors}
            )

        except Exception as e:
            self.finished.emit(
                {
                    "status": "error",
                    "message": str(e),
                    "type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                    "errors": errors,
                }
            )


class VisualizationWorker(QThread):
    progress_update = pyqtSignal(int, str)
    finished_viz = pyqtSignal(str)
    error_viz = pyqtSignal(str)

    def __init__(self, excel_files, output_dir, custom_name=""):
        super().__init__()
        self.excel_files = excel_files
        self.custom_name = custom_name
        self.output_dir = Path(self.excel_files[0]).parent
        self.palette = [
            "#B19CD9",
            "#FFB7B2",
            "#AEC6CF",
            "#FFD1DC",
            "#CFCFC4",
            "#FDFD96",
            "#836953",
            "#77DD77",
            "#F49AC2",
            "#CB99C9",
            "#C23B22",
            "#FFD12A",
        ]

    def _generate_plot_path(self, model, plot_type, tag=""):
        clean_custom = re.sub(r'[\\/*?:"<>|]', "", self.custom_name.strip())
        prefix = f"HYphlow_{clean_custom}_" if clean_custom else "HYphlow_"
        mmdd = datetime.datetime.now().strftime("%m%d")
        v_num = 1

        tag_str = f"_{tag}" if tag else ""

        while True:
            fname = f"{prefix}{model}_{plot_type}{tag_str}_{mmdd}_v{v_num}.svg"
            full_path = self.output_dir / fname
            if not full_path.exists():
                return full_path
            v_num += 1

    def run(self):
        try:
            self.progress_update.emit(10, "Loading Excel Data...")
            dfs = []
            for f in self.excel_files:
                try:
                    df = pd.read_excel(f, sheet_name="p-value summary")
                    busted_df = (
                        pd.read_excel(f, sheet_name="BUSTED")
                        if "BUSTED" in pd.ExcelFile(f).sheet_names
                        else pd.DataFrame()
                    )
                    relax_df = (
                        pd.read_excel(f, sheet_name="RELAX")
                        if "RELAX" in pd.ExcelFile(f).sheet_names
                        else pd.DataFrame()
                    )
                    dfs.append((df, busted_df, relax_df))
                except Exception:
                    pass

            if not dfs:
                raise ValueError("No valid sheets found.")

            self.progress_update.emit(30, "Processing Model Data...")

            for df_master, df_busted, df_relax in dfs:
                busted_master = df_master[df_master["Model"] == "BUSTED"]
                relax_master = df_master[df_master["Model"] == "RELAX"]

                if not busted_master.empty and not df_busted.empty:
                    self._plot_busted(busted_master, df_busted)

                if not relax_master.empty and not df_relax.empty:
                    self._plot_relax(relax_master, df_relax)

            self.progress_update.emit(90, "Saving Source Data Excel...")
            clean_custom = re.sub(r'[\\/*?:"<>|]', "", self.custom_name.strip())
            prefix = f"HYphlow_{clean_custom}_" if clean_custom else "HYphlow_"
            mmdd = datetime.datetime.now().strftime("%m%d")

            src_path = self.output_dir / f"{prefix}plot_SourceData_{mmdd}.xlsx"

            with pd.ExcelWriter(src_path, engine="xlsxwriter") as writer:
                for df_master, df_busted, df_relax in dfs:
                    if not df_busted.empty:
                        df_busted.to_excel(
                            writer, sheet_name="BUSTED_Source", index=False
                        )
                    if not df_relax.empty:
                        df_relax.to_excel(
                            writer, sheet_name="RELAX_Source", index=False
                        )

            self.finished_viz.emit(str(self.output_dir))

        except Exception as e:
            self.error_viz.emit(str(e))

    def _plot_busted(self, master_df, sheet_df):
        plot_data = []
        fg_tags = set()

        for _, row in master_df.iterrows():
            gname = row["Gene Name"]
            fg_tag = row.get("FG Tag", "Entire Branch")
            p_val = row["p-value"]

            best_rows = sheet_df[
                (sheet_df["Gene Name"] == gname)
                & (sheet_df["Sub_Model"] == "Unconstrained model")
            ]
            bg_val = None
            fg_val = None

            for _, b_row in best_rows.iterrows():
                dist = b_row.get("Distribution", "")
                om_str = str(b_row.get("Omega_3", ""))
                if om_str and "(" in om_str:
                    val = float(om_str.split("(")[0].strip())
                    if dist == "Background":
                        bg_val = val
                    elif dist == "Tested":
                        fg_val = val

            if fg_val is not None and bg_val is not None:
                plot_data.append(
                    {
                        "Gene Name": gname,
                        "FG Tag": fg_tag,
                        "FG_Omega": fg_val,
                        "BG_Omega": bg_val,
                        "p-value": pd.to_numeric(p_val, errors="coerce"),
                    }
                )
                fg_tags.add(fg_tag)

        if not plot_data:
            return

        plot_df = pd.DataFrame(plot_data).sort_values(by=["FG Tag", "Gene Name"])
        color_map = {
            tag: self.palette[i % len(self.palette)]
            for i, tag in enumerate(sorted(list(fg_tags)))
        }

        sig_df = plot_df[plot_df["p-value"] < 0.05]
        if not sig_df.empty:
            self._draw_dumbbell(
                sig_df, color_map, "BUSTED", "FG_Omega", "BG_Omega", "ω (dN/dS)"
            )

        self._draw_factor_bars(plot_df, color_map, "BUSTED", "FG_Omega", "FG ω (dN/dS)")

    def _plot_relax(self, master_df, sheet_df):
        plot_data = []
        fg_tags = set()

        for _, row in master_df.iterrows():
            gname = row["Gene Name"]
            fg_tag = row.get("FG Tag", "Entire Branch")
            p_val = row["p-value"]

            best_rows = sheet_df[
                (sheet_df["Gene Name"] == gname)
                & (sheet_df["Sub_Model"] == "RELAX alternative")
            ]

            k_val = None
            for _, b_row in best_rows.iterrows():
                k_val_raw = b_row.get("K_Value", "")
                if isinstance(k_val_raw, (int, float)):
                    k_val = k_val_raw
                    break

            if k_val is not None:
                plot_data.append(
                    {
                        "Gene Name": gname,
                        "FG Tag": fg_tag,
                        "K_Value": k_val,
                        "Baseline": 1.0,
                        "p-value": pd.to_numeric(p_val, errors="coerce"),
                    }
                )
                fg_tags.add(fg_tag)

        if not plot_data:
            return

        plot_df = pd.DataFrame(plot_data).sort_values(by=["FG Tag", "Gene Name"])
        color_map = {
            tag: self.palette[i % len(self.palette)]
            for i, tag in enumerate(sorted(list(fg_tags)))
        }

        sig_df = plot_df[plot_df["p-value"] < 0.05]
        if not sig_df.empty:
            self._draw_dumbbell(
                sig_df,
                color_map,
                "RELAX",
                "K_Value",
                "Baseline",
                "K (Relaxation Parameter)",
            )

        self._draw_factor_bars(plot_df, color_map, "RELAX", "K_Value", "K Value")

    def _draw_dumbbell(self, df, color_map, model_name, fg_col, bg_col, x_label):
        sns.set_style("ticks")
        min_height = 6.0
        calc_height = len(df) * 0.4
        final_height = max(min_height, calc_height)

        plt.figure(figsize=(10, final_height))
        plt.xscale("log")

        y_ticks = []
        y_labels = []
        current_y = 0

        tag_groups = df.groupby("FG Tag", sort=False)

        for tag, group in tag_groups:
            start_y = current_y
            c = color_map[tag]
            for _, row in group.iterrows():
                plt.hlines(
                    y=current_y,
                    xmin=row[bg_col],
                    xmax=row[fg_col],
                    color="gray",
                    alpha=0.4,
                    linewidth=2,
                )
                plt.scatter(
                    row[bg_col],
                    current_y,
                    facecolors="none",
                    edgecolors=c,
                    s=100,
                    linewidth=2,
                    zorder=3,
                )
                plt.scatter(row[fg_col], current_y, color=c, s=100, zorder=3)

                y_ticks.append(current_y)
                y_labels.append(row["Gene Name"])
                current_y += 1

            end_y = current_y - 1
            plt.axhspan(start_y - 0.5, end_y + 0.5, facecolor=c, alpha=0.15, zorder=0)

        plt.axvline(x=1, color="red", linestyle="--", alpha=0.7, zorder=1)

        plt.yticks(y_ticks, y_labels, fontsize=11)
        plt.xlabel(x_label, fontsize=14)
        plt.ylabel("Gene names", fontsize=14)

        import matplotlib.lines as mlines

        legend_handles = [
            mlines.Line2D(
                [],
                [],
                color="black",
                marker="o",
                linestyle="None",
                markerfacecolor="none",
                markersize=10,
                label="Background / Reference",
            ),
            mlines.Line2D(
                [],
                [],
                color="black",
                marker="o",
                linestyle="None",
                markersize=10,
                label="Foreground / Test",
            ),
        ]
        for tag, c in color_map.items():
            legend_handles.append(
                mlines.Line2D(
                    [],
                    [],
                    color=c,
                    marker="s",
                    linestyle="None",
                    markersize=10,
                    label=tag,
                )
            )

        plt.legend(
            handles=legend_handles,
            title="Foreground",
            bbox_to_anchor=(1.05, 1),
            loc="upper left",
            frameon=False,
        )
        sns.despine()

        fig1_path = self._generate_plot_path(model_name, "plot_best_fit")
        plt.savefig(fig1_path, format="svg", bbox_inches="tight")
        plt.close()

    def _draw_factor_bars(self, df, color_map, model_name, val_col, x_label):
        sns.set_style("ticks")
        tag_groups = df.groupby("FG Tag", sort=False)

        for tag, group in tag_groups:
            plt.figure(figsize=(8, max(4.0, len(group) * 0.5)))

            group_sorted = group.sort_values(by=val_col, ascending=True)
            y_positions = range(len(group_sorted))
            c = color_map[tag]

            plt.barh(
                y_positions,
                group_sorted[val_col],
                color=c,
                alpha=0.8,
                height=0.5,
            )

            for y_pos, (_, row) in zip(y_positions, group_sorted.iterrows()):
                if row["p-value"] < 0.05:
                    plt.text(
                        row[val_col],
                        y_pos,
                        " *",
                        verticalalignment="center",
                        fontsize=18,
                        color="black",
                    )

            plt.yticks(y_positions, group_sorted["Gene Name"], fontsize=11)
            plt.xlabel(x_label, fontsize=14)
            plt.title(f"Foreground: {tag}", fontsize=14, fontweight="bold")
            sns.despine()

            clean_tag = "".join(x for x in tag if x.isalnum() or x in "_")
            fig2_path = self._generate_plot_path(
                model_name, "plot_across_gene", clean_tag
            )
            plt.savefig(fig2_path, format="svg", bbox_inches="tight")
            plt.close()
