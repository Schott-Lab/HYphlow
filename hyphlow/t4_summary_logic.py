import json
import re
import traceback
from pathlib import Path

import pandas as pd
from PyQt5.QtCore import QThread, pyqtSignal

from hyphlow import common_utils

# =========================================================== constants

# Shown in the report when a result carries no foreground tag, which is what a
# tree that never passed through Tab 2 looks like: every branch was tested.
UNTAGGED = "All branches"

# Analyses that test one site at a time rather than the alignment as a whole.
SITE_MODELS = ("FEL", "MEME", "FUBAR")

P_THRESHOLD = 0.05
# FUBAR reports a posterior probability instead of a p-value.
POSTERIOR_THRESHOLD = 0.9

SHEET_MASTER = "p-value summary"
SHEET_SITES = "Site_Models"

# A result file ends in the analysis that produced it, and that tail is what
# the gene scan would otherwise land on.
RESULT_TAIL_RE = re.compile(
    r"_(?:%s)(?:_run\d+)?$" % "|".join(map(re.escape, common_utils.HYPHY_MODELS)),
    re.IGNORECASE,
)
RUN_TAIL_RE = re.compile(r"_run(\d+)$", re.IGNORECASE)
# Characters a file name cannot hold on Windows.
UNSAFE_NAME_RE = re.compile(r'[\\/*?:"<>|]')


# ======================================================== file identity


def _safe_prefix(custom_name):
    clean = UNSAFE_NAME_RE.sub("", (custom_name or "").strip())
    return f"HYphlow_{clean}_" if clean else "HYphlow_"


# Tab 2 names annotated trees GENE_annotated_TAG_STEP_v1_0801.nwk and HyPhy
# appends _MODEL(_runN), so the organism and gene sit before _annotated_.
def identity_from_json_name(json_name):
    stem = Path(json_name).stem
    tag = common_utils.tag_from_tree_name(json_name) or UNTAGGED
    head = RESULT_TAIL_RE.sub("", stem.split("_annotated_")[0])

    tokens = [t for t in head.split("_") if t]
    i = common_utils.gene_token_index(tokens)
    if i >= 0:
        return "_".join(tokens[:i]), tokens[i], tag
    if tokens:
        return "_".join(tokens[:-1]), tokens[-1].upper(), tag
    return "", "", tag


# Read from the end of the name, not by searching the whole of it: the step
# name Felsenstein contains FEL, so a MEME result on a Felsenstein tree used to
# be recorded as FEL.
def model_from_json_name(json_name):
    stem = RUN_TAIL_RE.sub("", Path(json_name).stem)
    token = stem.rsplit("_", 1)[-1].upper()
    return common_utils.HYPHY_MODEL_TOKENS.get(token, "")


def model_from_analysis_info(data):
    info = (data.get("analysis", {}) or {}).get("info", "") or ""
    for token, name in common_utils.HYPHY_MODEL_TOKENS.items():
        if token in info.upper():
            return name
    return ""


def run_id_from_name(json_name):
    stem = Path(json_name).stem
    m = RUN_TAIL_RE.search(stem)
    return (RUN_TAIL_RE.sub("", stem), int(m.group(1))) if m else (stem, 1)


# ========================================================= json parsing


# None when the file carries no AIC-c at all, which is normal for FUBAR.
def _aic(data):
    fits = data.get("fits", {}) or {}
    ordered = [
        fits[n] for n in ("Unconstrained model", "RELAX alternative") if n in fits
    ]
    ordered += [v for v in fits.values() if isinstance(v, dict)]
    for fit in ordered:
        score = fit.get("AIC-c")
        if isinstance(score, (int, float)):
            return score
    return None


def _omega_3(dist):
    # The third rate class is keyed "2"; RELAX nests it under the branch set.
    if not isinstance(dist, dict):
        return ""
    target = dist.get("2")
    if not isinstance(target, dict):
        nested = dist.get("Test")
        target = nested.get("2") if isinstance(nested, dict) else None
    if not isinstance(target, dict) and dist:
        last = dist[list(dist)[-1]]
        target = last if isinstance(last, dict) else None
    if not isinstance(target, dict):
        return ""
    if "omega" not in target or "proportion" not in target:
        return ""
    return f"{target['omega']:.4f} ({target['proportion'] * 100:.2f}%)"


def _test_pvalue(data):
    results = data.get("test results", {}) or {}
    pval = results.get("p-value", results.get("P-value", ""))
    return pval if isinstance(pval, (int, float)) else ""


def _significant(pval):
    return "Significant" if pval != "" and pval < P_THRESHOLD else "Not Significant"


def _parse_busted(data, common):
    rows = []
    pval = _test_pvalue(data)
    verdict = _significant(pval)
    fits = data.get("fits", {}) or {}

    for sub_model in ("Unconstrained model", "Constrained model"):
        fit = fits.get(sub_model, {}) or {}
        dists = fit.get("Rate Distributions", {}) or {}
        by_branch = {
            "Tested": dists.get("Test", {}),
            "Background": dists.get("Background", {}),
            "Synonymous": dists.get("Synonymous", dists.get("Synonymous rates", {})),
        }
        for branch_set, dist in by_branch.items():
            row = dict(common)
            row.update(
                {
                    "Model": "BUSTED",
                    "Sub_Model": sub_model,
                    "Distribution": branch_set,
                    "Log(L)": fit.get("Log Likelihood", ""),
                    "AIC-c": fit.get("AIC-c", ""),
                    "Params": fit.get("estimated parameters", ""),
                    "p-value": pval,
                    "Significance": verdict,
                    "Omega_3": _omega_3(dist),
                }
            )
            rows.append(row)
    return rows, pval, verdict


def _parse_relax(data, common):
    rows = []
    pval = _test_pvalue(data)
    verdict = _significant(pval)
    fits = data.get("fits", {}) or {}
    k_value = (data.get("test results", {}) or {}).get(
        "relaxation or intensification parameter", ""
    )
    if isinstance(k_value, (int, float)):
        pattern = "Intensification" if k_value > 1 else "Relaxation"
    else:
        pattern = ""

    for sub_model in ("RELAX null", "RELAX alternative"):
        fit = fits.get(sub_model, {}) or {}
        dists = fit.get("Rate Distributions", {}) or {}
        for branch_set in ("Reference", "Test"):
            row = dict(common)
            row.update(
                {
                    "Model": "RELAX",
                    "Sub_Model": sub_model,
                    "Branch": branch_set,
                    "Log(L)": fit.get("Log Likelihood", ""),
                    "AIC-c": fit.get("AIC-c", ""),
                    "Params": fit.get("estimated parameters", ""),
                    "p-value": pval,
                    "Significance": verdict,
                    "K_Value": k_value,
                    "Selection": pattern,
                    "Omega_3": _omega_3(dists.get(branch_set, {})),
                }
            )
            rows.append(row)
    return rows, pval, verdict


def _parse_absrel(data, common):
    # aBSREL tests each lineage separately, so the alignment as a whole has no
    # p-value. The verdict is whether any lineage came out significant.
    results = data.get("test results", {}) or {}
    tested = results.get("tested", 0)
    positive = results.get("positive test results", 0)

    attributes = data.get("branch attributes", {}) or {}
    branches = {}
    for value in attributes.values():
        if isinstance(value, dict):
            branches = value
            break

    named = [
        node
        for node, attr in branches.items()
        if isinstance(attr, dict)
        and isinstance(attr.get("Corrected P-value"), (int, float))
        and attr["Corrected P-value"] < P_THRESHOLD
    ]

    verdict = "Significant" if named else "Not Significant"
    row = dict(common)
    row.update(
        {
            "Model": "aBSREL",
            "Tested Lineages": tested,
            "Positive Lineages": positive,
            "Significant Branches": ", ".join(sorted(named)),
            "Significance": verdict,
        }
    )
    return [row], "", verdict


def _parse_sites(data, common, model):
    # Site methods test one codon at a time, so the verdict is whether any site
    # came out significant rather than one p-value for the alignment.
    mle = data.get("MLE", {}) or {}
    headers = mle.get("headers", []) or []
    content = []
    for value in (mle.get("content", {}) or {}).values():
        if isinstance(value, list):
            content = value
            break

    column = -1
    label = ""
    for i, header in enumerate(headers):
        text = str(header[0]).lower() if header else ""
        if "p-value" in text or "posterior" in text:
            column, label = i, text
            break

    named = []
    if column >= 0:
        for i, site in enumerate(content, start=1):
            value = site[column] if column < len(site) else None
            if not isinstance(value, (int, float)):
                continue
            if "posterior" in label:
                if value >= POSTERIOR_THRESHOLD:
                    named.append(str(i))
            elif value < P_THRESHOLD:
                named.append(str(i))

    verdict = "Significant" if named else "Not Significant"
    row = dict(common)
    row.update(
        {
            "Model": model,
            "Tested Sites": len(content),
            "Significant Sites Count": len(named),
            "Significant Sites List": ", ".join(named),
            "Significance": verdict,
        }
    )
    return [row], "", verdict


def parse_result(data, common, model):
    if model == "BUSTED":
        return _parse_busted(data, common)
    if model == "RELAX":
        return _parse_relax(data, common)
    if model == "aBSREL":
        return _parse_absrel(data, common)
    if model in SITE_MODELS:
        return _parse_sites(data, common, model)
    raise ValueError(f"No reader for model {model}.")


# ========================================================= excel report

FMT_HEADER = {"bold": True, "bg_color": "#FAFAFA", "border": 1}
FMT_SIGNIFICANT = {"bg_color": "#FFFF99", "font_color": "#FF0000"}
FMT_BEST_AIC = {"bg_color": "#E5FFE5"}
FMT_FILE_BREAK = {"bottom": 2}
FMT_SUBMODEL_BREAK = {"bottom": 1}


def _write_header(worksheet, columns, fmt, width=15):
    for i, name in enumerate(columns):
        worksheet.write(0, i, name, fmt)
        worksheet.set_column(i, i, max(len(str(name)) + 5, width))


def _write_master(writer, formats, master_data):
    # reset_index: sort_values keeps the original labels, and the labels are
    # what the row numbers below would otherwise be taken from.
    frame = pd.DataFrame(master_data).sort_values(by="Model").reset_index(drop=True)
    frame.to_excel(writer, sheet_name=SHEET_MASTER, index=False)
    worksheet = writer.sheets[SHEET_MASTER]
    _write_header(worksheet, frame.columns, formats["header"])

    aic_columns = [c for c in frame.columns if c.startswith("AIC_Run")]
    for i, row in frame.iterrows():
        line = i + 1
        pval = row.get("p-value", "")
        if isinstance(pval, (int, float)) and pval < P_THRESHOLD:
            worksheet.write(
                line, frame.columns.get_loc("p-value"), pval, formats["significant"]
            )
        if row.get("Significance") == "Significant":
            worksheet.write(
                line,
                frame.columns.get_loc("Significance"),
                row["Significance"],
                formats["significant"],
            )

        values = [row[c] for c in aic_columns if isinstance(row[c], (int, float))]
        if values:
            best = min(values)
            for c in aic_columns:
                if row[c] == best:
                    worksheet.write(
                        line, frame.columns.get_loc(c), row[c], formats["best_aic"]
                    )

        if i < len(frame) - 1 and row["Model"] != frame.at[i + 1, "Model"]:
            worksheet.set_row(line, None, formats["file_break"])


def _write_model_sheet(writer, formats, sheet_name, rows):
    frame = pd.DataFrame(rows)
    frame.to_excel(writer, sheet_name=sheet_name, index=False)
    worksheet = writer.sheets[sheet_name]
    _write_header(worksheet, frame.columns, formats["header"])

    previous = (None, None)
    for i, row in frame.iterrows():
        line = i + 1
        pval = row.get("p-value", "")
        if isinstance(pval, (int, float)) and pval < P_THRESHOLD:
            if "p-value" in frame.columns:
                worksheet.write(
                    line, frame.columns.get_loc("p-value"), pval, formats["significant"]
                )
        if row.get("Significance") == "Significant" and "Significance" in frame.columns:
            worksheet.write(
                line,
                frame.columns.get_loc("Significance"),
                row["Significance"],
                formats["significant"],
            )

        current = (row.get("File Name", ""), row.get("Sub_Model", ""))
        if i > 0:
            if current[0] != previous[0]:
                worksheet.set_row(line - 1, None, formats["file_break"])
            elif current[1] != previous[1]:
                worksheet.set_row(line - 1, None, formats["submodel_break"])
        previous = current


def write_report(save_path, master_data, rows_by_model):
    with pd.ExcelWriter(save_path, engine="xlsxwriter") as writer:
        book = writer.book
        formats = {
            "header": book.add_format(FMT_HEADER),
            "significant": book.add_format(FMT_SIGNIFICANT),
            "best_aic": book.add_format(FMT_BEST_AIC),
            "file_break": book.add_format(FMT_FILE_BREAK),
            "submodel_break": book.add_format(FMT_SUBMODEL_BREAK),
        }
        _write_master(writer, formats, master_data)
        for sheet_name, rows in rows_by_model.items():
            if rows:
                _write_model_sheet(writer, formats, sheet_name, rows)


# =============================================================== worker


class SummaryExportThread(QThread):
    progress_update = pyqtSignal(int, str)
    # Not "finished": QThread has a signal of that name already.
    export_done = pyqtSignal(dict)

    def __init__(self, json_files, output_dir, custom_name=""):
        super().__init__()
        self.json_files = json_files
        self.output_dir = Path(output_dir)
        self.custom_name = custom_name

    def _report_paths(self):
        prefix = _safe_prefix(self.custom_name)
        stamp = common_utils.mmdd()
        version = 1
        while True:
            folder = self.output_dir / f"{prefix}summary_{stamp}_v{version}"
            if not folder.exists():
                folder.mkdir(parents=True)
                name = f"{prefix}result_summary_{stamp}_v{version}.xlsx"
                return folder, folder / name
            version += 1

    # Triplicate runs of one analysis differ only by seed, so the run with the
    # lowest AIC-c is the one reported; the others stay in the AIC columns.
    def _best_runs(self, errors):
        groups = {}
        for path in self.json_files:
            base, run_id = run_id_from_name(Path(path).name)
            groups.setdefault(base, {})[run_id] = path

        chosen = []
        for runs in groups.values():
            scores, best, lowest = {}, None, float("inf")
            for run_id, path in sorted(runs.items()):
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        score = _aic(json.load(fh))
                except (OSError, ValueError) as e:
                    errors.append(
                        {
                            "file": path,
                            "error": str(e),
                            "type": type(e).__name__,
                            "traceback": traceback.format_exc(),
                        }
                    )
                    continue
                if score is None:
                    continue
                scores[f"AIC_Run{run_id}"] = score
                if score < lowest:
                    lowest, best = score, run_id
            # FUBAR writes no "fits" section, so its AIC-c is never a number.
            # Falling back to the first run keeps those results in the report.
            if best is None and runs:
                best = min(runs)
            if best is not None:
                chosen.append((runs[best], best, scores))
        return chosen

    def run(self):
        errors = []
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            folder, save_path = self._report_paths()

            rows_by_model = {
                "BUSTED": [],
                "aBSREL": [],
                "RELAX": [],
                SHEET_SITES: [],
            }
            master_data = []
            processed = []

            chosen = self._best_runs(errors)
            for index, (path, best_run, scores) in enumerate(chosen):
                name = Path(path).name
                self.progress_update.emit(
                    int((index / max(1, len(chosen))) * 100), f"Reading {name}..."
                )
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)

                    if not any(k in data for k in ("fits", "MLE", "test results")):
                        raise ValueError(
                            "This file holds no HyPhy result; the analysis may "
                            "not have finished."
                        )

                    model = model_from_json_name(name) or model_from_analysis_info(data)
                    if not model:
                        raise ValueError(
                            "Could not tell which HyPhy analysis wrote this file."
                        )

                    organism, gene, tag = identity_from_json_name(name)
                    common = {
                        "File Name": name,
                        "Organism": organism,
                        "Gene Name": gene,
                        "FG Tag": tag,
                        "Sequences": (data.get("input", {}) or {}).get(
                            "number of sequences", ""
                        ),
                        "Sites": (data.get("input", {}) or {}).get(
                            "number of sites", ""
                        ),
                    }

                    rows, pval, verdict = parse_result(data, common, model)
                    sheet = SHEET_SITES if model in SITE_MODELS else model
                    rows_by_model[sheet].extend(rows)

                    master_row = {
                        "Model": model,
                        "File Name": name,
                        "Organism": organism,
                        "Gene Name": gene,
                        "FG Tag": tag,
                        "AIC_Run1": scores.get("AIC_Run1", ""),
                        "AIC_Run2": scores.get("AIC_Run2", ""),
                        "AIC_Run3": scores.get("AIC_Run3", ""),
                        "Best_Run": f"Run{best_run}",
                        "p-value": pval,
                        "Significance": verdict,
                    }
                    master_data.append(master_row)
                    processed.append(path)

                except Exception as e:
                    errors.append(
                        {
                            "file": path,
                            "error": str(e),
                            "type": type(e).__name__,
                            "traceback": traceback.format_exc(),
                        }
                    )

            if not master_data:
                self.export_done.emit(
                    {
                        "status": "error",
                        "message": "No result file could be read.",
                        "type": "NoValidData",
                        "traceback": "",
                        "errors": errors,
                        "processed": [],
                    }
                )
                return

            self.progress_update.emit(90, "Writing the report...")
            try:
                write_report(save_path, master_data, rows_by_model)
            except PermissionError as e:
                raise PermissionError(
                    "The report is open in another program. Close it and try again."
                ) from e

            self.progress_update.emit(100, "Done.")
            self.export_done.emit(
                {
                    "status": "success",
                    "path": str(save_path),
                    "folder": str(folder),
                    "errors": errors,
                    "processed": processed,
                }
            )

        except Exception as e:
            self.export_done.emit(
                {
                    "status": "error",
                    "message": str(e),
                    "type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                    "errors": errors,
                    "processed": [],
                }
            )
