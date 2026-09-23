from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hyphlow import common_utils, t1_st1_logic, t4_summary_logic
from hyphlow.common_ui import PrimaryButton, UnifiedDropZone

# =========================================================== constants

COL_FILE, COL_GENE, COL_TAG, COL_MODEL, COL_STATUS = range(5)

BADGE_READY = ("#F2F2F7", "#8E8E93")
BADGE_BUSY = ("#FFF9E5", "#FF9500")
BADGE_DONE = ("#E5F0FF", "#0071E3")
BADGE_ERROR = ("#FFECEB", "#FF3B30")

# What each failure means for the person holding the files.
SOLUTIONS = {
    "PermissionError": "Close the report in Excel and export again.",
    "ValueError": "Check that these are the JSON files HyPhy wrote.",
    "KeyError": "Run the analysis again; this file is incomplete.",
    "IndexError": "Run the analysis again; this file is incomplete.",
    "TypeError": "Run the analysis again; this file is incomplete.",
    "NoValidData": "None of the files could be read as a HyPhy result.",
}
DEFAULT_SOLUTION = "See the error report for details."


class Tab4SummaryUI(QWidget):
    log_msg = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.json_files = []
        self.file_status_labels = {}
        self.thread = None
        self._setup_ui()

    # ============================================================== ui

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
            "Collects the HyPhy result files of a project into one spreadsheet: "
            "one row per analysis, with the branch or site level detail on its "
            "own sheet. Where an analysis was repeated, the run with the lowest "
            "AIC-c is the one reported."
        )
        desc_lbl.setObjectName("SubText")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("border: none; background: transparent;")
        header_vbox.addWidget(desc_lbl)

        main_layout.addLayout(header_vbox)

        self.input_card = QFrame()
        self.input_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.input_card.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E5E5EA;"
            " border-radius: 10px; }"
        )
        ic_layout = QVBoxLayout(self.input_card)
        ic_layout.setContentsMargins(15, 10, 15, 15)
        ic_layout.setSpacing(10)

        lbl_input_title = QLabel("HyPhy Result Files")
        lbl_input_title.setObjectName("SubHeader")
        lbl_input_title.setStyleSheet(
            "border: none; background: transparent; font-weight: bold;"
        )
        ic_layout.addWidget(lbl_input_title)

        self.dz_json = UnifiedDropZone(
            [".json"],
            "HyPhy JSON Results",
            show_dropdown=False,
            file_type="json",
            show_gene_input=False,
            # file_kind() has no JSON case and falls back to CSV, which would
            # open the browser in the Tab 1 folder.
            default_subdir=("Results", "HyPhy_Execution"),
        )
        self.dz_json.files_updated.connect(self.handle_json_drop)
        ic_layout.addWidget(self.dz_json)

        ic_layout.addWidget(self._build_status_table())
        main_layout.addWidget(self.input_card)

        self.global_scroll.setWidget(scroll_content)
        master_layout.addWidget(self.global_scroll)

    def _build_status_table(self):
        card = QFrame()
        card.setStyleSheet("QFrame { background-color: transparent; border: none; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 5, 0, 0)
        layout.setSpacing(10)

        self.status_table = QTableWidget(0, 5)
        self.status_table.setHorizontalHeaderLabels(
            ["File Name", "Gene", "Foreground", "Analysis", "Status"]
        )
        header = self.status_table.horizontalHeader()
        header.setSectionResizeMode(COL_FILE, QHeaderView.Stretch)
        for col in (COL_GENE, COL_TAG, COL_MODEL):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.Fixed)
        self.status_table.setColumnWidth(COL_STATUS, 120)

        self.status_table.verticalHeader().setVisible(False)
        self.status_table.verticalHeader().setDefaultSectionSize(36)
        self.status_table.setFocusPolicy(Qt.NoFocus)
        self.status_table.setMinimumHeight(200)
        self.status_table.setStyleSheet("""
            QTableWidget { border: 1px solid #E5E5EA; border-radius: 8px; background-color: #FFFFFF; outline: none; gridline-color: transparent; }
            QTableWidget::item { padding: 4px; border-bottom: 1px solid #F2F2F7; }
            QHeaderView::section { background-color: #FAFAFA; border: none; border-bottom: 1px solid #E5E5EA; height: 28px; padding-left: 5px; }
        """)
        layout.addWidget(self.status_table)

        btn_layout = QHBoxLayout()
        self.input_custom_name = QLineEdit()
        self.input_custom_name.setPlaceholderText("Custom Report Name (Optional)")
        self.input_custom_name.setFixedHeight(44)
        self.input_custom_name.setStyleSheet("""
            QLineEdit { border: 1px solid #D1D1D6; border-radius: 6px; padding: 8px; background: #FAFAFA; font-size: 13px; }
        """)
        btn_layout.addWidget(self.input_custom_name)

        self.btn_export = PrimaryButton(" Export to Excel", "mdi.file-excel")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.export_to_excel)
        btn_layout.addWidget(self.btn_export)

        layout.addLayout(btn_layout)
        return card

    # ========================================================== badges

    def create_status_badge(self, text, bg_color, text_color):
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(4, 2, 4, 2)
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f"background-color: {bg_color}; color: {text_color}; border-radius: 6px;"
            " font-weight: 800; font-size: 11px; padding: 4px 8px;"
        )
        layout.addWidget(lbl)
        return wrapper, lbl

    def _set_badge(self, label, text, colors, tooltip=""):
        bg, fg = colors
        label.setText(text)
        label.setToolTip(tooltip)
        label.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 6px;"
            " font-weight: 800; font-size: 11px; padding: 4px 8px;"
        )

    # =========================================================== input

    def handle_json_drop(self, files):
        self.json_files = files
        self.status_table.setRowCount(0)
        self.file_status_labels.clear()
        self.btn_export.setEnabled(bool(files))

        if not files:
            return

        self.log_msg.emit(f"[INFO] Loaded {len(files)} result file(s).")
        self.status_table.setRowCount(len(files))

        for i, path in enumerate(files):
            name = Path(path).name
            # Read from the name only. The analysis is confirmed against the
            # contents of the file during export, which runs off this thread.
            _, gene, tag = t4_summary_logic.identity_from_json_name(name)
            model = t4_summary_logic.model_from_json_name(name)

            for col, text in (
                (COL_FILE, name),
                (COL_GENE, gene or "—"),
                (COL_TAG, tag),
                (COL_MODEL, model or "read on export"),
            ):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.status_table.setItem(i, col, item)

            wrapper, lbl = self.create_status_badge("Ready", *BADGE_READY)
            self.status_table.setCellWidget(i, COL_STATUS, wrapper)
            self.file_status_labels[path] = lbl

    # ==================================================== excel export

    def export_to_excel(self):
        if not self.json_files:
            return

        if not t1_st1_logic.CURRENT_PROJECT_PATH:
            self.log_msg.emit(
                "[ERROR] No workspace selected. Set a project workspace in the "
                "Dashboard first."
            )
            return

        out_dir = common_utils.get_summary_path(t1_st1_logic.CURRENT_PROJECT_PATH)

        self.btn_export.setEnabled(False)
        self.btn_export.set_state("busy", " Processing...")
        for lbl in self.file_status_labels.values():
            self._set_badge(lbl, "Processing", BADGE_BUSY)

        self.thread = t4_summary_logic.SummaryExportThread(
            self.json_files, str(out_dir), self.input_custom_name.text().strip()
        )
        self.thread.progress_update.connect(self.on_export_progress)
        self.thread.export_done.connect(self.on_export_finished)
        self.thread.start()

    def on_export_progress(self, percent, text):
        self.log_msg.emit(f"[PROCESS] {text}")

    def on_export_finished(self, res):
        self.btn_export.setEnabled(True)
        self.btn_export.set_state("run", " Export to Excel", "mdi.file-excel")

        errors = res.get("errors", [])
        self._mark_files(errors, res.get("processed", []))
        self._report_errors(errors)

        if res.get("status") == "success":
            if errors:
                self.log_msg.emit(
                    f"[WARNING] Report written, but {len(errors)} file(s) could "
                    "not be read."
                )
            else:
                self.log_msg.emit(f"[SUCCESS] Report written to: {res['folder']}")
            return

        self._log_failure(
            "Could not write the report",
            res.get("type", ""),
            res.get("message", ""),
            res.get("traceback", ""),
        )

    def _mark_files(self, errors, processed):
        failed = {e["file"] for e in errors}
        read = set(processed)
        for path, lbl in self.file_status_labels.items():
            if path in failed:
                self._set_badge(lbl, "Error", BADGE_ERROR, "See the log for why.")
            elif path in read:
                self._set_badge(lbl, "Completed", BADGE_DONE)
            else:
                # A repeated run that lost the AIC-c comparison. Its numbers are
                # still in the AIC columns of the summary sheet.
                self._set_badge(
                    lbl,
                    "Not reported",
                    BADGE_READY,
                    "Another run of this analysis fitted better.",
                )

    def _report_errors(self, errors):
        for err in errors:
            self._log_failure(
                f"Could not read {Path(err['file']).name}",
                err.get("type", ""),
                err.get("error", ""),
                err.get("traceback", ""),
            )

    def _log_failure(self, headline, err_type, message, tb):
        solution = SOLUTIONS.get(err_type, DEFAULT_SOLUTION)
        text = f"{headline} | [{err_type}] {message}\n{solution}"
        self.log_msg.emit(f"[ERROR] {text}")
        common_utils.log_error_to_file(
            t1_st1_logic.CURRENT_PROJECT_PATH,
            "Tab 4: Summary",
            f"{text}\nTraceback:\n{tb}",
        )
