import os
import sys
import json
import subprocess
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFrame,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QScrollArea,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal
import qtawesome as qta

from common_ui import UnifiedDropZone
import common_utils
import t1_st1_logic
import t4_summary_logic


class Tab4SummaryUI(QWidget):
    log_msg = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.json_files = []
        self.file_status_labels = {}
        self._setup_ui()

    def _setup_ui(self):
        master_layout = QVBoxLayout(self)
        master_layout.setContentsMargins(0, 0, 0, 0)

        self.global_scroll = QScrollArea()
        self.global_scroll.setWidgetResizable(True)
        self.global_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")
        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(20)

        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(4)

        header_lbl = QLabel("Results Summary")
        header_lbl.setObjectName("SectionHeader")
        header_lbl.setStyleSheet("border: none; background: transparent;")
        header_vbox.addWidget(header_lbl)

        desc_lbl = QLabel(
            "Extracts key results from HyPhy analysis outputs and compiles them into a single Excel summary file."
        )
        desc_lbl.setObjectName("SubText")
        desc_lbl.setStyleSheet("border: none; background: transparent;")
        header_vbox.addWidget(desc_lbl)

        main_layout.addLayout(header_vbox)

        self.input_card = QFrame()
        self.input_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.input_card.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 10px; }"
        )
        ic_layout = QVBoxLayout(self.input_card)
        ic_layout.setContentsMargins(15, 10, 15, 15)
        ic_layout.setSpacing(10)

        input_header = QHBoxLayout()
        lbl_input_title = QLabel("JSON File Input")
        lbl_input_title.setObjectName("SubHeader")
        lbl_input_title.setStyleSheet("border: none; background: transparent;")
        input_header.addWidget(lbl_input_title)
        input_header.addStretch()
        ic_layout.addLayout(input_header)

        self.dz_json = UnifiedDropZone(
            [".json"],
            "HyPhy JSON Results",
            show_dropdown=False,
            file_type="json",
            show_gene_input=False,
        )
        self.dz_json.files_updated.connect(self.handle_json_drop)
        if hasattr(self.dz_json, "scroll_area"):
            self.dz_json.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.dz_json.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.dz_json.scroll_area.setWidgetResizable(True)
            self.dz_json.scroll_area.setMaximumHeight(200)

        ic_layout.addWidget(self.dz_json)
        main_layout.addWidget(self.input_card)

        table_card = QFrame()
        table_card.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 10px; }"
        )
        tc_layout = QVBoxLayout(table_card)
        tc_layout.setContentsMargins(15, 15, 15, 15)
        tc_layout.setSpacing(10)

        tc_header = QHBoxLayout()
        overview_lbl = QLabel("Loaded Results Overview")
        overview_lbl.setObjectName("SubHeader")
        overview_lbl.setStyleSheet("border: none; background: transparent;")
        tc_header.addWidget(overview_lbl)
        tc_header.addStretch()
        tc_layout.addLayout(tc_header)

        self.status_table = QTableWidget(0, 4)
        self.status_table.setHorizontalHeaderLabels(
            ["File Name", "Gene", "Detected Model", "Status"]
        )
        header = self.status_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.status_table.setColumnWidth(3, 120)

        self.status_table.verticalHeader().setVisible(False)
        self.status_table.verticalHeader().setDefaultSectionSize(36)
        self.status_table.setFocusPolicy(Qt.NoFocus)
        self.status_table.setMinimumHeight(200)
        self.status_table.setStyleSheet("""
            QTableWidget { border: 1px solid #E5E5EA; border-radius: 8px; background-color: #FFFFFF; outline: none; gridline-color: transparent; }
            QTableWidget::item { padding: 4px; border-bottom: 1px solid #F2F2F7; }
            QHeaderView::section { background-color: #FAFAFA; border: none; border-bottom: 1px solid #E5E5EA; height: 28px; padding-left: 5px; }
        """)
        tc_layout.addWidget(self.status_table)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_export = QPushButton(" Export to Excel")
        self.btn_export.setIcon(qta.icon("mdi.file-excel", color="#FFFFFF"))
        self.btn_export.setFixedHeight(44)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setStyleSheet("""
            QPushButton { background-color: #1D1D1F; color: white; border-radius: 8px; border: none; padding: 0 20px;}
            QPushButton:hover { background-color: #333333; }
            QPushButton:disabled { background-color: #E5E5EA; color: #8E8E93; }
        """)
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.export_to_excel)
        btn_layout.addWidget(self.btn_export)

        tc_layout.addLayout(btn_layout)
        main_layout.addWidget(table_card, stretch=1)

        self.global_scroll.setWidget(scroll_content)
        master_layout.addWidget(self.global_scroll)

    def create_status_badge(self, text, bg_color, text_color):
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(4, 2, 4, 2)
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f"background-color: {bg_color}; color: {text_color}; border-radius: 6px; font-weight: 800; font-size: 11px; padding: 4px 8px;"
        )
        layout.addWidget(lbl)
        return wrapper, lbl

    def handle_json_drop(self, files):
        self.json_files = files
        self.status_table.setRowCount(0)
        self.file_status_labels.clear()

        if files:
            self.log_msg.emit(f"[INFO] Loaded {len(files)} JSON result file(s).")
            self.status_table.setRowCount(len(files))

            known_models = ["BUSTED", "aBSREL", "RELAX", "FEL", "MEME", "FUBAR", "SLAC"]

            for i, f in enumerate(files):
                base_name = Path(f).name
                gene_name = (
                    base_name.split("_")[0]
                    if "_" in base_name
                    else base_name.split(".")[0]
                )

                model_name = "Unknown"
                name_upper = base_name.upper()

                for m in known_models:
                    if m.upper() in name_upper:
                        model_name = m if m != "aBSREL" else "aBSREL"
                        break

                if model_name == "Unknown":
                    try:
                        with open(f, "r", encoding="utf-8") as json_f:
                            data = json.load(json_f)
                            model_info = data.get("analysis", {}).get("info", "")
                            if model_info:
                                for m in known_models:
                                    if m.upper() in model_info.upper():
                                        model_name = m if m != "aBSREL" else "aBSREL"
                                        break
                    except Exception:
                        pass

                self.status_table.setItem(i, 0, QTableWidgetItem(base_name))
                self.status_table.setItem(i, 1, QTableWidgetItem(gene_name))
                self.status_table.setItem(i, 2, QTableWidgetItem(model_name))

                wrapper, lbl = self.create_status_badge("Ready", "#F2F2F7", "#8E8E93")
                self.status_table.setCellWidget(i, 3, wrapper)
                self.file_status_labels[f] = lbl

            self.btn_export.setEnabled(True)
        else:
            self.btn_export.setEnabled(False)

    def export_to_excel(self):
        if not self.json_files:
            return

        if not t1_st1_logic.CURRENT_PROJECT_PATH:
            self.log_msg.emit(
                "[ERROR] No workspace selected.\nSolution: Please set a project workspace in the Dashboard first."
            )
            return

        out_dir = common_utils.get_pipeline_path(
            t1_st1_logic.CURRENT_PROJECT_PATH, "Results", "SUMMARY"
        )

        save_path, _ = common_utils.generate_smart_filename(
            "HyPhy_Summary_Report", "SUMMARY", out_dir, ".xlsx", is_report=False
        )

        self.btn_export.setEnabled(False)
        self.btn_export.setText(" Processing...")

        for lbl in self.file_status_labels.values():
            lbl.setText("Processing")
            lbl.setStyleSheet(
                "background-color: #FFF9E5; color: #FF9500; border-radius: 6px; font-weight: 800; font-size: 11px; padding: 4px 8px;"
            )

        self.thread = t4_summary_logic.SummaryExportThread(self.json_files, save_path)
        self.thread.progress_update.connect(self.on_export_progress)
        self.thread.finished.connect(self.on_export_finished)
        self.thread.start()

    def on_export_progress(self, percent, text):
        self.log_msg.emit(f"[PROCESS] {text}")

    def on_export_finished(self, res):
        self.btn_export.setEnabled(True)
        self.btn_export.setText(" Export to Excel")

        errors = res.get("errors", [])
        status = res.get("status")
        main_msg = res.get("message", "")
        main_type = res.get("type", "")
        main_tb = res.get("traceback", "")

        def get_solution(err_type):
            if err_type == "PermissionError":
                return "Solution: Please close the Excel file and click export again."
            elif err_type == "ValueError":
                return "Solution: Double-check that you are only uploading the final JSON result files generated by HyPhy."
            elif err_type in ["KeyError", "IndexError", "TypeError"]:
                return "Solution: Re-run the analysis in HyPhy to generate a fresh, complete file."
            elif err_type == "NoValidData":
                return "Solution: Make sure your analysis actually finished properly before uploading the files."
            return "Solution: Please check the detailed error report."

        for f_path, lbl in self.file_status_labels.items():
            if any(e["file"] == f_path for e in errors):
                lbl.setText("Error")
                lbl.setStyleSheet(
                    "background-color: #FFECEB; color: #FF3B30; border-radius: 6px; font-weight: 800; font-size: 11px; padding: 4px 8px;"
                )
            else:
                lbl.setText("Completed")
                lbl.setStyleSheet(
                    "background-color: #E5F0FF; color: #0071E3; border-radius: 6px; font-weight: 800; font-size: 11px; padding: 4px 8px;"
                )

        if errors and t1_st1_logic.CURRENT_PROJECT_PATH:
            for err in errors:
                e_type = err.get("type", "")
                e_msg = err.get("error", "")
                e_tb = err.get("traceback", "")
                solution = get_solution(e_type)

                console_msg = f"Failed to parse {Path(err['file']).name} | [{e_type}] {e_msg}\n{solution}\nTraceback:\n{e_tb}"
                self.log_msg.emit(f"[ERROR] {console_msg}")
                common_utils.log_error_to_file(
                    t1_st1_logic.CURRENT_PROJECT_PATH, "Tab 4: Summary", console_msg
                )

        if status == "success":
            if errors:
                self.log_msg.emit(
                    f"[WARNING] Exported with {len(errors)} error(s). Please check the logs."
                )
            else:
                self.log_msg.emit(f"[SUCCESS] Excel report exported to: {res['path']}")
                try:
                    if sys.platform == "win32":
                        os.startfile(res["path"])
                    elif sys.platform == "darwin":
                        subprocess.call(["open", res["path"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        try:
                            r = subprocess.call(["explorer.exe", res["path"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if r != 0:
                                raise OSError()
                        except Exception:
                            r2 = subprocess.call(["xdg-open", res["path"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if r2 != 0:
                                raise OSError()
                except Exception:
                    self.log_msg.emit("[INFO] Excel report saved successfully.")
                    self.log_msg.emit("[INFO] Unable to automatically open the file due to missing GUI display components in the current environment.")
                    self.log_msg.emit(f"[INFO] Please manually open: {res['path']}")
        else:
            solution = get_solution(main_type)
            console_msg = f"Failed to export Excel | [{main_type}] {main_msg}\n{solution}\nTraceback:\n{main_tb}"
            self.log_msg.emit(f"[ERROR] {console_msg}")

            if t1_st1_logic.CURRENT_PROJECT_PATH:
                common_utils.log_error_to_file(
                    t1_st1_logic.CURRENT_PROJECT_PATH, "Tab 4: Summary", console_msg
                )
