import os
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidgetItem,
    QProgressBar,
    QScrollArea,
    QFrame,
    QHeaderView,
    QPushButton,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QColor
import qtawesome as qta

from common_ui import (
    Popup,
    UnifiedDropZone,
    StandardTable,
    TableCheckBoxWidget,
    PrimaryButton,
    ActionButton,
)

import t1_st1_logic
import t1_st2_logic
import t1_st3_logic


class ValidationThread(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(dict)

    def __init__(self, file_col_pairs):
        super().__init__()
        self.file_col_pairs = file_col_pairs
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            file_results = {}
            tot_files = len(self.file_col_pairs)

            for idx, (path, col) in enumerate(self.file_col_pairs):
                if self.is_cancelled:
                    return

                def prog(curr, tot):
                    if self.is_cancelled:
                        raise InterruptedError()
                    overall = int(((idx + curr / tot) / tot_files) * 100)
                    self.progress.emit(overall, 100)

                res = t1_st1_logic.run_validation_pipeline(path, col, prog)
                file_results[path] = res

            if not self.is_cancelled:
                self.finished.emit(file_results)
        except InterruptedError:
            pass


class FastaFormatThread(QThread):
    finished = pyqtSignal(list, str, int)
    progress = pyqtSignal(int, int)

    def __init__(self, file_paths, gene_dict):
        super().__init__()
        self.file_paths = file_paths
        self.gene_dict = gene_dict
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def _progress_callback(self, curr, tot):
        if self.is_cancelled:
            raise InterruptedError("USER_ABORTED")
        self.progress.emit(curr, tot)

    def run(self):
        try:
            if self.is_cancelled:
                return
            results, rep_path = t1_st2_logic.run_fasta_pipeline(
                self.file_paths, self.gene_dict
            )
            if not self.is_cancelled:
                self.finished.emit(results, str(rep_path), 0)
        except InterruptedError:
            pass


class NwkFormatThread(QThread):
    finished = pyqtSignal(list, str, int)
    progress = pyqtSignal(int, int)

    def __init__(self, file_paths, gene_dict):
        super().__init__()
        self.file_paths = file_paths
        self.gene_dict = gene_dict
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def _progress_callback(self, curr, tot):
        if self.is_cancelled:
            raise InterruptedError("USER_ABORTED")
        self.progress.emit(curr, tot)

    def run(self):
        try:
            if self.is_cancelled:
                return
            results, rep_path = t1_st3_logic.run_nwk_pipeline(
                self.file_paths, self.gene_dict
            )
            if not self.is_cancelled:
                self.finished.emit(results, str(rep_path), 0)
        except InterruptedError:
            pass


class ResultFileBlock(QFrame):
    def __init__(self, file_path, results):
        super().__init__()
        self.file_path = file_path
        self.results = results
        self.corrections = [r for r in results if r[1] in ["SIMILAR", "SUBS_NOT_FOUND"]]
        self.filename = os.path.basename(file_path)

        self.setStyleSheet(
            "QFrame#Block { border: 1px solid #E5E5EA; border-radius: 8px; background: #FFFFFF; }"
        )
        self.setObjectName("Block")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QFrame()
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setStyleSheet("background: transparent; border: none;")
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(15, 12, 15, 12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(
            qta.icon("mdi.file-document-outline", color="#0071E3").pixmap(20, 20)
        )
        h_layout.addWidget(icon_lbl)

        name_lbl = QLabel(self.filename)
        name_lbl.setStyleSheet("font-size: 14px; font-weight: 600; color: #1D1D1F;")
        h_layout.addWidget(name_lbl)

        if self.corrections:
            badge = QLabel(f"{len(self.corrections)} items")
            badge.setStyleSheet(
                "background: #FFF0F0; color: #FF3B30; padding: 3px 8px; border-radius: 6px; font-size: 12px; font-weight: bold;"
            )
            h_layout.addWidget(badge)
        else:
            badge = QLabel("Perfect Match")
            badge.setStyleSheet(
                "background: #F0FDF4; color: #16A34A; padding: 3px 8px; border-radius: 6px; font-size: 12px; font-weight: bold;"
            )
            h_layout.addWidget(badge)

        h_layout.addStretch()

        self.toggle_icon = QLabel()
        self.toggle_icon.setPixmap(
            qta.icon("mdi.chevron-down", color="#1D1D1F").pixmap(20, 20)
        )
        h_layout.addWidget(self.toggle_icon)

        layout.addWidget(self.header)

        self.content_area = QFrame()
        self.content_area.hide()
        c_layout = QVBoxLayout(self.content_area)
        c_layout.setContentsMargins(15, 0, 15, 15)

        if not self.corrections:
            empty_lbl = QLabel(
                "No corrections needed. All species labels are 100% accurate."
            )
            empty_lbl.setStyleSheet(
                "color: #8E8E93; font-size: 13px; font-style: italic;"
            )
            c_layout.addWidget(empty_lbl)
        else:
            self.table = StandardTable(["Apply", "Original Name", "Suggested", "Score"])
            self.table.setRowCount(len(self.corrections))

            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Fixed)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.Stretch)
            header.setSectionResizeMode(3, QHeaderView.Fixed)

            self.table.setColumnWidth(0, 50)
            self.table.setColumnWidth(3, 120)

            th = min(len(self.corrections) * 44 + 38, 250)
            self.table.setFixedHeight(th)

            for row, (orig, status, sugg, score, err) in enumerate(self.corrections):
                item_o = QTableWidgetItem(orig)
                item_s = QTableWidgetItem(sugg)
                item_c = QTableWidgetItem(f"{score:.1f}%")

                item_c.setTextAlignment(Qt.AlignCenter)

                if status == "SUBS_NOT_FOUND":
                    item_s.setForeground(QColor("#9333EA"))
                    item_c.setForeground(QColor("#9333EA"))
                else:
                    item_s.setForeground(QColor("#0071E3"))
                    item_c.setForeground(QColor("#8E8E93"))

                chk_w = TableCheckBoxWidget(checked=True)

                self.table.setCellWidget(row, 0, chk_w)
                self.table.setItem(row, 1, item_o)
                self.table.setItem(row, 2, item_s)
                self.table.setItem(row, 3, item_c)

            c_layout.addWidget(self.table)

        layout.addWidget(self.content_area)
        self.header.mousePressEvent = self.toggle

    def toggle(self, event):
        if self.content_area.isVisible():
            self.content_area.hide()
            self.toggle_icon.setPixmap(
                qta.icon("mdi.chevron-down", color="#1D1D1F").pixmap(20, 20)
            )
        else:
            self.content_area.show()
            self.toggle_icon.setPixmap(
                qta.icon("mdi.chevron-up", color="#1D1D1F").pixmap(20, 20)
            )

    def get_selected_corrections(self):
        to_apply = {}
        if not self.corrections:
            return to_apply
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if w and w.is_checked:
                orig = self.table.item(r, 1).text()
                sugg = self.table.item(r, 2).text()
                to_apply[orig] = sugg
        return to_apply


class StandardizationPage(QWidget):
    applied = pyqtSignal(str, int)
    log_msg = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    file_progress_update = pyqtSignal(str, int, str)

    def __init__(self):
        super().__init__()
        self.csv_files = []
        self.applied_corrections = {}
        self.current_report_version = None
        self.fasta_files = []
        self.nwk_files = []
        self.result_blocks = []

        self._setup_ui()

    def _setup_ui(self):
        master_layout = QVBoxLayout(self)
        master_layout.setContentsMargins(0, 0, 0, 0)

        self.global_scroll = QScrollArea()
        self.global_scroll.setWidgetResizable(True)
        self.global_scroll.setFrameShape(QFrame.NoFrame)
        self.global_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")

        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(20)

        self.card_csv = QFrame()
        self.card_csv.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.card_csv.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 10px; }"
        )
        csv_card_layout = QVBoxLayout(self.card_csv)
        csv_card_layout.setContentsMargins(15, 15, 15, 15)
        csv_card_layout.setSpacing(10)

        csv_header = QHBoxLayout()
        csv_title_vbox = QVBoxLayout()
        lbl_csv_title = QLabel("CSV Species Label Validation")
        lbl_csv_title.setObjectName("SubHeader")
        lbl_csv_title.setStyleSheet("border: none; background: transparent;")
        lbl_csv_desc = QLabel(
            "Checks and corrects CSV species labels using the NCBI taxonomy database."
        )
        lbl_csv_desc.setObjectName("SubText")
        lbl_csv_desc.setStyleSheet("border: none; background: transparent;")
        csv_title_vbox.addWidget(lbl_csv_title)
        csv_title_vbox.addWidget(lbl_csv_desc)
        csv_header.addLayout(csv_title_vbox)

        csv_header.addStretch()
        self.btn_toggle_csv = QPushButton()
        self.btn_toggle_csv.setIcon(qta.icon("mdi.chevron-up", color="#1D1D1F"))
        self.btn_toggle_csv.setStyleSheet("border: none; background: transparent;")
        self.btn_toggle_csv.setCursor(Qt.PointingHandCursor)
        csv_header.addWidget(self.btn_toggle_csv)
        csv_card_layout.addLayout(csv_header)

        self.csv_content_area = QFrame()
        self.csv_content_area.setStyleSheet("background: transparent; border: none;")
        csv_content_layout = QVBoxLayout(self.csv_content_area)
        csv_content_layout.setContentsMargins(0, 10, 0, 0)
        self._build_csv_ui(csv_content_layout)
        csv_card_layout.addWidget(self.csv_content_area)

        self.btn_toggle_csv.clicked.connect(
            lambda: self.toggle_card(self.csv_content_area, self.btn_toggle_csv)
        )

        main_layout.addWidget(self.card_csv)

        self.card_format = QFrame()
        self.card_format.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.card_format.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 10px; }"
        )
        fmt_card_layout = QVBoxLayout(self.card_format)
        fmt_card_layout.setContentsMargins(15, 15, 15, 15)
        fmt_card_layout.setSpacing(10)

        fmt_header = QHBoxLayout()
        fmt_title_vbox = QVBoxLayout()
        lbl_fmt_title = QLabel("FASTA/NWK Label Standardization")
        lbl_fmt_title.setObjectName("SubHeader")
        lbl_fmt_title.setStyleSheet("border: none; background: transparent;")
        lbl_fmt_desc = QLabel(
            "Standardizes FASTA headers and NWK leaf names into species-level labels."
        )
        lbl_fmt_desc.setObjectName("SubText")
        lbl_fmt_desc.setStyleSheet("border: none; background: transparent;")
        fmt_title_vbox.addWidget(lbl_fmt_title)
        fmt_title_vbox.addWidget(lbl_fmt_desc)
        fmt_header.addLayout(fmt_title_vbox)

        fmt_header.addStretch()
        self.btn_toggle_fmt = QPushButton()
        self.btn_toggle_fmt.setIcon(qta.icon("mdi.chevron-down", color="#1D1D1F"))
        self.btn_toggle_fmt.setStyleSheet("border: none; background: transparent;")
        self.btn_toggle_fmt.setCursor(Qt.PointingHandCursor)
        fmt_header.addWidget(self.btn_toggle_fmt)
        fmt_card_layout.addLayout(fmt_header)

        self.fmt_content_area = QFrame()
        self.fmt_content_area.setStyleSheet("background: transparent; border: none;")
        fmt_content_layout = QVBoxLayout(self.fmt_content_area)
        fmt_content_layout.setContentsMargins(0, 10, 0, 0)
        self._build_format_ui(fmt_content_layout)
        fmt_card_layout.addWidget(self.fmt_content_area)
        self.fmt_content_area.hide()

        self.btn_toggle_fmt.clicked.connect(
            lambda: self.toggle_card(self.fmt_content_area, self.btn_toggle_fmt)
        )

        main_layout.addWidget(self.card_format)
        main_layout.addStretch()

        self.global_scroll.setWidget(scroll_content)
        master_layout.addWidget(self.global_scroll)

    def toggle_card(self, content_area, toggle_btn):
        if content_area.isVisible():
            content_area.hide()
            toggle_btn.setIcon(qta.icon("mdi.chevron-down", color="#1D1D1F"))
        else:
            content_area.show()
            toggle_btn.setIcon(qta.icon("mdi.chevron-up", color="#1D1D1F"))

    def _build_csv_ui(self, layout):
        self.csv_drop_zone = UnifiedDropZone(
            [".csv"],
            "Supported formats: CSV",
            show_dropdown=True,
            file_type="csv",
            open_in_base_dir=True,
        )
        self.csv_drop_zone.files_updated.connect(self.handle_csv_files)

        if hasattr(self.csv_drop_zone, "scroll_area"):
            self.csv_drop_zone.scroll_area.setHorizontalScrollBarPolicy(
                Qt.ScrollBarAsNeeded
            )
            self.csv_drop_zone.scroll_area.setVerticalScrollBarPolicy(
                Qt.ScrollBarAsNeeded
            )
            self.csv_drop_zone.scroll_area.setWidgetResizable(True)
            self.csv_drop_zone.scroll_area.setMaximumHeight(150)

        layout.addWidget(self.csv_drop_zone)

        self.csv_pbar = QProgressBar()
        self.csv_pbar.setFixedHeight(6)
        self.csv_pbar.setTextVisible(False)
        self.csv_pbar.setStyleSheet(
            "QProgressBar { background-color: #F2F2F7; border-radius: 3px; border: none; margin-top: 10px; margin-bottom: 2px;} QProgressBar::chunk { background-color: #34C759; border-radius: 3px; }"
        )
        self.csv_pbar.hide()
        layout.addWidget(self.csv_pbar)

        self.csv_run_btn = ActionButton(" Run Validation", "mdi.play", is_danger=False)
        self.is_csv_running = False
        self.csv_run_btn.clicked.connect(self.toggle_csv_validation)
        layout.addWidget(self.csv_run_btn)
        self.set_csv_run_state("run")

        self.results_container = QFrame()
        self.results_container.setStyleSheet(
            "QFrame#ResContainer { border: 1px solid #E5E5EA; border-radius: 8px; background: #FAFAFA; }"
        )
        self.results_container.setObjectName("ResContainer")
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(10, 10, 10, 10)
        self.results_layout.setSpacing(10)
        self.results_container.hide()
        layout.addWidget(self.results_container)

        self.apply_container = QWidget()
        act_layout = QVBoxLayout(self.apply_container)
        act_layout.setContentsMargins(0, 5, 0, 0)
        act_layout.setSpacing(8)

        self.csv_notify_lbl = QLabel("")
        self.csv_notify_lbl.setStyleSheet(
            "font-size: 13px; font-weight: bold; border:none; color: #34C759;"
        )
        self.csv_notify_lbl.setAlignment(Qt.AlignCenter)
        act_layout.addWidget(self.csv_notify_lbl)

        self.csv_apply_btn = PrimaryButton(" Apply Corrections")
        self.csv_apply_btn.setFixedHeight(44)
        self.csv_apply_btn.clicked.connect(self.apply_csv_corrections)
        act_layout.addWidget(self.csv_apply_btn)

        self.apply_container.hide()
        layout.addWidget(self.apply_container)

    def _build_format_ui(self, layout):
        sub_layout = QHBoxLayout()
        sub_layout.setSpacing(20)

        fasta_vbox = QVBoxLayout()
        self.fasta_drop = UnifiedDropZone(
            [".fas", ".fasta", ".fa"],
            "Supported formats: FASTA",
            file_type="fasta",
            open_in_base_dir=True,
        )
        self.fasta_drop.files_updated.connect(self.handle_fasta_files)

        if hasattr(self.fasta_drop, "scroll_area"):
            self.fasta_drop.scroll_area.setHorizontalScrollBarPolicy(
                Qt.ScrollBarAsNeeded
            )
            self.fasta_drop.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.fasta_drop.scroll_area.setWidgetResizable(True)
            self.fasta_drop.scroll_area.setMaximumHeight(130)

        fasta_vbox.addWidget(self.fasta_drop)

        fasta_vbox.addStretch(1)

        self.fasta_pbar = QProgressBar()
        self.fasta_pbar.setFixedHeight(6)
        self.fasta_pbar.setTextVisible(False)
        self.fasta_pbar.setStyleSheet(
            "QProgressBar { background-color: #F2F2F7; border-radius: 3px; border: none; margin-top: 10px; margin-bottom: 2px;} QProgressBar::chunk { background-color: #34C759; border-radius: 3px; }"
        )
        self.fasta_pbar.hide()
        fasta_vbox.addWidget(self.fasta_pbar)

        self.fasta_run_btn = ActionButton(
            " Run FASTA Formatting", "mdi.play", is_danger=False
        )
        self.is_fasta_running = False
        self.fasta_run_btn.clicked.connect(self.toggle_fasta_formatting)
        fasta_vbox.addWidget(self.fasta_run_btn)
        self.set_fasta_run_state("run")

        nwk_vbox = QVBoxLayout()
        self.nwk_drop = UnifiedDropZone(
            [".nwk", ".tree", ".tre"],
            "Supported formats: NWK",
            file_type="nwk",
            open_in_base_dir=True,
        )
        self.nwk_drop.files_updated.connect(self.handle_nwk_files)

        if hasattr(self.nwk_drop, "scroll_area"):
            self.nwk_drop.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.nwk_drop.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.nwk_drop.scroll_area.setWidgetResizable(True)
            self.nwk_drop.scroll_area.setMaximumHeight(130)

        nwk_vbox.addWidget(self.nwk_drop)

        nwk_vbox.addStretch(1)

        self.nwk_pbar = QProgressBar()
        self.nwk_pbar.setFixedHeight(6)
        self.nwk_pbar.setTextVisible(False)
        self.nwk_pbar.setStyleSheet(
            "QProgressBar { background-color: #F2F2F7; border-radius: 3px; border: none; margin-top: 10px; margin-bottom: 2px;} QProgressBar::chunk { background-color: #34C759; border-radius: 3px; }"
        )
        self.nwk_pbar.hide()
        nwk_vbox.addWidget(self.nwk_pbar)

        self.nwk_run_btn = ActionButton(
            " Run NWK Formatting", "mdi.play", is_danger=False
        )
        self.is_nwk_running = False
        self.nwk_run_btn.clicked.connect(self.toggle_nwk_formatting)
        nwk_vbox.addWidget(self.nwk_run_btn)
        self.set_nwk_run_state("run")

        sub_layout.addLayout(fasta_vbox, stretch=1)
        sub_layout.addLayout(nwk_vbox, stretch=1)
        layout.addLayout(sub_layout)

    def handle_csv_files(self, files):
        self.csv_files = files
        if not files:
            while self.results_layout.count():
                item = self.results_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.result_blocks = []

            self.results_container.hide()
            self.apply_container.hide()
            self.csv_pbar.hide()

            if getattr(self, "is_csv_running", False):
                self.abort_csv_validation()
            return

        self.log_msg.emit(f"[INFO] Loaded {len(files)} CSV file(s) for validation.")

        for fname in files:
            widget = self.csv_drop_zone.item_widgets.get(fname)
            if widget and widget.combo.count() == 0:
                headers = t1_st1_logic.load_csv_headers(fname)
                widget.set_headers(headers)

    def set_csv_run_state(self, state):
        if state == "run":
            self.csv_run_btn.setText(" Run Validation")
            self.csv_run_btn.setIcon(qta.icon("mdi.play", color="white"))
            self.csv_run_btn.setStyleSheet(
                "QPushButton { background-color: #1D1D1F; color: white; font-size: 14px; font-weight: bold; border-radius: 8px; border: none; padding: 0 16px; } QPushButton:hover { background-color: #333333; }"
            )
            self.is_csv_running = False
        else:
            self.csv_run_btn.setText(" Stop / Abort")
            self.csv_run_btn.setIcon(qta.icon("mdi.stop", color="white"))
            self.csv_run_btn.setStyleSheet(
                "QPushButton { background-color: #FF3B30; color: white; font-size: 14px; font-weight: bold; border-radius: 8px; border: none; padding: 0 16px; } QPushButton:hover { background-color: #D70015; }"
            )
            self.is_csv_running = True

    def toggle_csv_validation(self):
        if not self.is_csv_running:
            self.start_csv_validation()
        else:
            self.abort_csv_validation()

    def start_csv_validation(self):
        if not self.csv_files:
            return

        file_col_pairs = []
        for f in self.csv_files:
            widget = self.csv_drop_zone.item_widgets.get(f)
            col = widget.combo.currentText()
            if not col:
                self.log_msg.emit(
                    f"[ERROR] Please select a column for {os.path.basename(f)}"
                )
                return
            file_col_pairs.append((f, col))

        self.set_csv_run_state("stop")

        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.result_blocks = []

        self.csv_pbar.show()
        self.csv_pbar.setRange(0, 0)
        self.results_container.hide()
        self.apply_container.hide()

        for f in self.csv_files:
            self.file_progress_update.emit(os.path.basename(f), 0, "Validating CSV...")

        self.log_msg.emit(
            f"[PROCESS] Started validation pipeline for {len(self.csv_files)} file(s)."
        )

        self.csv_thread = ValidationThread(file_col_pairs)
        self.csv_thread.progress.connect(self.update_csv_progress)
        self.csv_thread.finished.connect(self.on_csv_finished)
        self.csv_thread.start()

    def abort_csv_validation(self):
        if hasattr(self, "csv_thread") and self.csv_thread.isRunning():
            self.csv_thread.cancel()
            self.csv_thread.wait()
        self.set_csv_run_state("run")
        self.csv_pbar.hide()
        self.log_msg.emit("[WARNING] CSV validation aborted by user.")

    def update_csv_progress(self, curr, tot):
        if self.csv_pbar.maximum() == 0:
            self.csv_pbar.setRange(0, 100)
        val = int((curr / tot) * 100)
        self.csv_pbar.setValue(val)
        self.progress_update.emit(val)
        for f in self.csv_files:
            self.file_progress_update.emit(
                os.path.basename(f), val, "Validating CSV..."
            )

    def on_csv_finished(self, file_results):
        self.set_csv_run_state("run")
        self.csv_pbar.setRange(0, 100)
        self.csv_pbar.setValue(100)

        for f in self.csv_files:
            self.file_progress_update.emit(
                os.path.basename(f), 100, "Validation Complete"
            )

        total_corrections = 0
        for path, results in file_results.items():
            block = ResultFileBlock(path, results)
            self.results_layout.addWidget(block)
            self.result_blocks.append(block)
            total_corrections += len(block.corrections)

        self.results_container.show()
        self.apply_container.show()

        if total_corrections == 0:
            self.log_msg.emit(
                "[SUCCESS] All files are perfect matches. Auto-generating reports..."
            )
            self.apply_csv_corrections()
        else:
            self.log_msg.emit("[SUCCESS] Validation complete. Ready for review.")

    def apply_csv_corrections(self):
        if not hasattr(self, "result_blocks") or not self.result_blocks:
            return

        total_applied = 0
        try:
            for block in self.result_blocks:
                to_apply = block.get_selected_corrections()
                widget = self.csv_drop_zone.item_widgets.get(block.file_path)
                col = widget.combo.currentText() if widget else None

                if col:
                    res = t1_st1_logic.apply_and_save_corrections(
                        block.file_path,
                        col,
                        to_apply,
                        block.results,
                        target_version=self.current_report_version,
                    )
                    if res and res[0]:
                        total_applied += res[2]
                        self.applied.emit(os.path.basename(res[0]), res[2])

            self.csv_notify_lbl.setText(
                f"Saved for all files! ({total_applied} applied)"
            )
            self.log_msg.emit(
                f"[SUCCESS] Process completed and saved to Results folder."
            )

        except Exception as e:
            self.log_msg.emit(f"[ERROR] Error saving files: {str(e)}")

    def handle_fasta_files(self, files):
        self.fasta_files = files
        if not files:
            self.fasta_pbar.hide()
            return
        self.log_msg.emit(f"[INFO] Loaded {len(files)} FASTA file(s) for formatting.")

    def set_fasta_run_state(self, state):
        if state == "run":
            self.fasta_run_btn.setText(" Run FASTA Formatting")
            self.fasta_run_btn.setIcon(qta.icon("mdi.play", color="white"))
            self.fasta_run_btn.setStyleSheet(
                "QPushButton { background-color: #1D1D1F; color: white; font-size: 14px; font-weight: bold; border-radius: 8px; border: none; padding: 0 16px; } QPushButton:hover { background-color: #333333; }"
            )
            self.is_fasta_running = False
        else:
            self.fasta_run_btn.setText(" Stop / Abort")
            self.fasta_run_btn.setIcon(qta.icon("mdi.stop", color="white"))
            self.fasta_run_btn.setStyleSheet(
                "QPushButton { background-color: #FF3B30; color: white; font-size: 14px; font-weight: bold; border-radius: 8px; border: none; padding: 0 16px; } QPushButton:hover { background-color: #D70015; }"
            )
            self.is_fasta_running = True

    def toggle_fasta_formatting(self):
        if not self.is_fasta_running:
            self.run_fasta_formatting()
        else:
            self.abort_fasta_formatting()

    def abort_fasta_formatting(self):
        if hasattr(self, "fasta_thread") and self.fasta_thread.isRunning():
            self.fasta_thread.cancel()
            self.fasta_thread.wait()
        self.set_fasta_run_state("run")
        self.fasta_pbar.hide()
        if self.fasta_files:
            self.fasta_drop.update_file_progress(self.fasta_files[-1], 0)
        self.log_msg.emit("[WARNING] FASTA Formatting aborted by user.")

    def run_fasta_formatting(self):
        if not self.fasta_files:
            return
        self.set_fasta_run_state("stop")
        self.fasta_pbar.show()
        self.fasta_pbar.setRange(0, 0)

        for f in self.fasta_files:
            self.file_progress_update.emit(
                os.path.basename(f), 0, "Formatting FASTA..."
            )

        self.log_msg.emit(
            f"[PROCESS] Started FASTA formatting pipeline for {len(self.fasta_files)} file(s)."
        )

        gene_dict = self.fasta_drop.get_all_genes()
        self.fasta_thread = FastaFormatThread(self.fasta_files, gene_dict)
        self.fasta_thread.progress.connect(self.update_fasta_progress)
        self.fasta_thread.finished.connect(self.on_fasta_finished)
        self.fasta_thread.start()

    def update_fasta_progress(self, curr, tot):
        if self.fasta_pbar.maximum() == 0:
            self.fasta_pbar.setRange(0, 100)
        val = int((curr / tot) * 100) if tot > 0 else 0
        self.fasta_pbar.setValue(val)
        for f in self.fasta_files:
            self.file_progress_update.emit(
                os.path.basename(f), val, "Formatting FASTA..."
            )

    def on_fasta_finished(self, results, rep_path, version):
        self.set_fasta_run_state("run")
        self.fasta_pbar.setRange(0, 100)
        self.fasta_pbar.setValue(100)
        success_count = sum(1 for r in results if r.get("success", False))

        for f in self.fasta_files:
            self.file_progress_update.emit(
                os.path.basename(f), 100, "Formatting Complete"
            )

        self.log_msg.emit(
            f"[SUCCESS] FASTA formatting completed successfully: {success_count}/{len(results)} files. Report: {os.path.basename(rep_path)}"
        )

    def handle_nwk_files(self, files):
        self.nwk_files = files
        if not files:
            self.nwk_pbar.hide()
            return
        self.log_msg.emit(f"[INFO] Loaded {len(files)} NWK file(s) for formatting.")

    def set_nwk_run_state(self, state):
        if state == "run":
            self.nwk_run_btn.setText(" Run NWK Formatting")
            self.nwk_run_btn.setIcon(qta.icon("mdi.play", color="white"))
            self.nwk_run_btn.setStyleSheet(
                "QPushButton { background-color: #1D1D1F; color: white; font-size: 14px; font-weight: bold; border-radius: 8px; border: none; padding: 0 16px; } QPushButton:hover { background-color: #333333; }"
            )
            self.is_nwk_running = False
        else:
            self.nwk_run_btn.setText(" Stop / Abort")
            self.nwk_run_btn.setIcon(qta.icon("mdi.stop", color="white"))
            self.nwk_run_btn.setStyleSheet(
                "QPushButton { background-color: #FF3B30; color: white; font-size: 14px; font-weight: bold; border-radius: 8px; border: none; padding: 0 16px; } QPushButton:hover { background-color: #D70015; }"
            )
            self.is_nwk_running = True

    def toggle_nwk_formatting(self):
        if not self.is_nwk_running:
            self.run_nwk_formatting()
        else:
            self.abort_nwk_formatting()

    def abort_nwk_formatting(self):
        if hasattr(self, "nwk_thread") and self.nwk_thread.isRunning():
            self.nwk_thread.cancel()
            self.nwk_thread.wait()
        self.set_nwk_run_state("run")
        self.nwk_pbar.hide()
        if self.nwk_files:
            self.nwk_drop.update_file_progress(self.nwk_files[-1], 0)
        self.log_msg.emit("[WARNING] NWK Formatting aborted by user.")

    def run_nwk_formatting(self):
        if not self.nwk_files:
            return
        self.set_nwk_run_state("stop")
        self.nwk_pbar.show()
        self.nwk_pbar.setRange(0, 0)

        for f in self.nwk_files:
            self.file_progress_update.emit(os.path.basename(f), 0, "Formatting NWK...")

        self.log_msg.emit(
            f"[PROCESS] Started NWK formatting pipeline for {len(self.nwk_files)} file(s)."
        )

        gene_dict = self.nwk_drop.get_all_genes()
        self.nwk_thread = NwkFormatThread(self.nwk_files, gene_dict)
        self.nwk_thread.progress.connect(self.update_nwk_progress)
        self.nwk_thread.finished.connect(self.on_nwk_finished)
        self.nwk_thread.start()

    def update_nwk_progress(self, curr, tot):
        if self.nwk_pbar.maximum() == 0:
            self.nwk_pbar.setRange(0, 100)
        val = int((curr / tot) * 100) if tot > 0 else 0
        self.nwk_pbar.setValue(val)
        for f in self.nwk_files:
            self.file_progress_update.emit(
                os.path.basename(f), val, "Formatting NWK..."
            )

    def on_nwk_finished(self, results, rep_path, version):
        self.set_nwk_run_state("run")
        self.nwk_pbar.setRange(0, 100)
        self.nwk_pbar.setValue(100)
        success_count = sum(1 for r in results if r.get("success", False))

        for f in self.nwk_files:
            self.file_progress_update.emit(
                os.path.basename(f), 100, "Formatting Complete"
            )

        self.log_msg.emit(
            f"[SUCCESS] NWK formatting completed successfully: {success_count}/{len(results)} files. Report: {os.path.basename(rep_path)}"
        )
