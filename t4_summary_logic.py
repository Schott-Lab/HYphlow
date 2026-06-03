import json
import pandas as pd
import traceback
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal


class SummaryExportThread(QThread):
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, json_files, save_path):
        super().__init__()
        self.json_files = json_files
        self.save_path = save_path

    def run(self):
        errors = []
        try:
            results_by_model = {
                "BUSTED": [],
                "aBSREL": [],
                "RELAX": [],
                "Site_Models": [],
            }

            total_files = len(self.json_files)

            for idx, file_path in enumerate(self.json_files):
                self.progress_update.emit(
                    int((idx / total_files) * 100), f"Parsing {Path(file_path).name}..."
                )

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    model_info = data.get("analysis", {}).get("info", "")
                    base_name = Path(file_path).name
                    gene_name = (
                        base_name.split("_")[0]
                        if "_" in base_name
                        else base_name.split(".")[0]
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

                    common_data = {
                        "File Name": base_name,
                        "Gene Name": gene_name,
                        "Sequences": data.get("input", {}).get(
                            "number of sequences", ""
                        ),
                        "Sites": data.get("input", {}).get("number of sites", ""),
                    }

                    if detected_model == "BUSTED":
                        row = common_data.copy()
                        row["Model"] = "BUSTED"
                        row["LRT"] = data.get("test results", {}).get("LRT", "")

                        pval = data.get("test results", {}).get("p-value", "")
                        row["P-value"] = pval

                        if isinstance(pval, (int, float)):
                            row["Significance"] = (
                                "Significant" if pval < 0.05 else "Not Significant"
                            )
                        else:
                            row["Significance"] = "Not Significant"

                        omega_prop = ""
                        rate_dists = (
                            data.get("fits", {})
                            .get("Unconstrained model", {})
                            .get("Rate Distributions", {})
                        )
                        if "Test" in rate_dists:
                            for rate_class, values in rate_dists["Test"].items():
                                if values.get("omega", 0) > 1:
                                    omega_prop = values.get("proportion", "")
                                    break
                        row["Omega > 1 Proportion"] = omega_prop
                        results_by_model["BUSTED"].append(row)

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
                        results_by_model["aBSREL"].append(row)

                    elif detected_model == "RELAX":
                        row = common_data.copy()
                        row["Model"] = "RELAX"
                        row["LRT"] = data.get("test results", {}).get("LRT", "")

                        pval = data.get("test results", {}).get("p-value", "")
                        row["P-value"] = pval

                        if isinstance(pval, (int, float)):
                            row["Significance"] = (
                                "Significant" if pval < 0.05 else "Not Significant"
                            )
                        else:
                            row["Significance"] = "Not Significant"

                        k_val = data.get("test results", {}).get(
                            "relaxation or intensification parameter", ""
                        )
                        row["K Value"] = k_val

                        if isinstance(k_val, (int, float)):
                            if k_val > 1:
                                row["Selection Pattern"] = "Intensification"
                            elif k_val < 1:
                                row["Selection Pattern"] = "Relaxation"
                            else:
                                row["Selection Pattern"] = "Neutral"
                        else:
                            row["Selection Pattern"] = ""

                        results_by_model["RELAX"].append(row)

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

            if all(len(rows) == 0 for rows in results_by_model.values()):
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
                with pd.ExcelWriter(self.save_path, engine="xlsxwriter") as writer:
                    workbook = writer.book
                    yellow_format = workbook.add_format(
                        {"bg_color": "#FFF2CC", "font_color": "#1D1D1F"}
                    )

                    for sheet_name, rows in results_by_model.items():
                        if not rows:
                            continue

                        df = pd.DataFrame(rows)
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                        worksheet = writer.sheets[sheet_name]

                        for col_num, col_name in enumerate(df.columns):
                            worksheet.set_column(
                                col_num, col_num, max(len(col_name) + 5, 15)
                            )

                            if col_name == "P-value" or col_name == "Corrected P-value":
                                col_letter = chr(65 + col_num)
                                cell_range = (
                                    f"{col_letter}2:{col_letter}{len(rows) + 1}"
                                )
                                worksheet.conditional_format(
                                    cell_range,
                                    {
                                        "type": "cell",
                                        "criteria": "<",
                                        "value": 0.05,
                                        "format": yellow_format,
                                    },
                                )

                            elif col_name == "Significance":
                                col_letter = chr(65 + col_num)
                                cell_range = (
                                    f"{col_letter}2:{col_letter}{len(rows) + 1}"
                                )
                                worksheet.conditional_format(
                                    cell_range,
                                    {
                                        "type": "cell",
                                        "criteria": "==",
                                        "value": '"Significant"',
                                        "format": yellow_format,
                                    },
                                )
            except PermissionError:
                raise PermissionError(
                    "The Excel file is currently open. Please close it and try again."
                )

            self.progress_update.emit(100, "Done!")
            self.finished.emit(
                {"status": "success", "path": self.save_path, "errors": errors}
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
