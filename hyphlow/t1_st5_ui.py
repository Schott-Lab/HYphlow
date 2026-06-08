import os
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QScrollArea,
    QPushButton,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
import qtawesome as qta

from hyphlow import t1_st5_logic
from hyphlow import t1_st1_logic
from hyphlow import common_utils
from hyphlow.common_ui import (
    UnifiedDropZone,
    TableCheckBoxWidget,
    PrimaryButton,
    ActionButton,
)

def create_status_badge(text, bg_color, text_color):
    wrapper = QWidget()
    wrapper.setAttribute(Qt.WA_TranslucentBackground)
    wrapper.setStyleSheet("background: transparent; border: none;")
    layout = QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(
        f"background-color: {bg_color}; color: {text_color}; border-radius: 4px; font-weight: bold; font-size: 11px; padding: 4px 8px;"
    )
    layout.addWidget(lbl)
    layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    return wrapper


class CategorySection(QWidget):
    def __init__(self, title):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #515154; padding-left: 5px; border: none; background: transparent;"
        )
        layout.addWidget(self.title_lbl)

        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(10)
        layout.addLayout(self.content_layout)
        self.hide()

    def add_block(self, block):
        self.content_layout.addWidget(block)
        self.show()

    def clear(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.hide()


class ReconResultBlock(QFrame):
    apply_requested = pyqtSignal(object)

    def __init__(self, src, fname, file_results):
        super().__init__()
        self.src = src
        self.fname = fname
        self.corrections = [r for r in file_results if r[3] in ["SIMILAR", "NOT_FOUND"]]

        self.setStyleSheet(
            "QFrame#Block { border: 1px solid #E5E5EA; border-radius: 6px; background: #FAFAFA; }"
        )
        self.setObjectName("Block")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QFrame()
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setStyleSheet("background: transparent; border: none;")
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(15, 10, 15, 10)

        icon_lbl = QLabel()
        icon_name = "mdi.file-document-outline"
        if src in ["NWK", "FAS_NWK"]:
            icon_name = "mdi.file-tree"
        icon_lbl.setPixmap(qta.icon(icon_name, color="#515154").pixmap(18, 18))
        h_layout.addWidget(icon_lbl)

        name_lbl = QLabel(self.fname)
        name_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 500; color: #1D1D1F; border: none; background: transparent;"
        )
        h_layout.addWidget(name_lbl)

        total_cnt = len(file_results)
        mismatch_cnt = len(self.corrections)
        perfect_cnt = total_cnt - mismatch_cnt

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(6)
        stats_layout.setContentsMargins(10, 0, 0, 0)

        lbl_tot = QLabel(f"Total: {total_cnt}")
        lbl_tot.setStyleSheet(
            "background: #E5E5EA; color: #515154; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: bold; border: none;"
        )
        lbl_perf = QLabel(f"Perfect: {perfect_cnt}")
        lbl_perf.setStyleSheet(
            "background: #EBF9EE; color: #16A34A; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: bold; border: none;"
        )
        lbl_mis = QLabel(f"Mismatches: {mismatch_cnt}")
        mis_bg = "#FFECEB" if mismatch_cnt > 0 else "#E5E5EA"
        mis_fg = "#FF3B30" if mismatch_cnt > 0 else "#8E8E93"
        lbl_mis.setStyleSheet(
            f"background: {mis_bg}; color: {mis_fg}; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: bold; border: none;"
        )

        stats_layout.addWidget(lbl_tot)
        stats_layout.addWidget(lbl_perf)
        stats_layout.addWidget(lbl_mis)
        h_layout.addLayout(stats_layout)
        h_layout.addStretch()

        self.btn_apply_block = QPushButton("Apply Changes")
        self.btn_apply_block.setIcon(qta.icon("mdi.play", color="white"))
        self.btn_apply_block.setStyleSheet("""
            QPushButton { background-color: #1D1D1F; color: white; font-weight: bold; font-size: 12px; padding: 6px 14px; border-radius: 6px; border: none; }
            QPushButton:hover { background-color: #333333; }
        """)
        self.btn_apply_block.setCursor(Qt.PointingHandCursor)
        self.btn_apply_block.clicked.connect(lambda: self.apply_requested.emit(self))
        h_layout.addWidget(self.btn_apply_block)

        self.toggle_icon = QLabel()
        self.toggle_icon.setPixmap(
            qta.icon("mdi.chevron-down", color="#1D1D1F").pixmap(20, 20)
        )
        self.toggle_icon.setStyleSheet("border: none; background: transparent;")
        h_layout.addWidget(self.toggle_icon)
        layout.addWidget(self.header)

        self.content_area = QFrame()
        self.content_area.hide()
        self.content_area.setStyleSheet("border: none; background: transparent;")
        c_layout = QVBoxLayout(self.content_area)
        c_layout.setContentsMargins(15, 0, 15, 15)

        if not self.corrections:
            empty_lbl = QLabel(
                "All taxa match the reference perfectly. Report generation available."
            )
            empty_lbl.setStyleSheet(
                "color: #8E8E93; font-size: 13px; font-style: italic; border: none; background: transparent;"
            )
            c_layout.addWidget(empty_lbl)
        else:
            self.table = QTableWidget(len(self.corrections), 4)
            self.table.setHorizontalHeaderLabels(
                ["Apply", "Original Name", "Suggested", "Status"]
            )
            header = self.table.horizontalHeader()

            header.setSectionResizeMode(0, QHeaderView.Fixed)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.Stretch)
            header.setSectionResizeMode(3, QHeaderView.Fixed)

            self.table.setColumnWidth(0, 50)
            self.table.setColumnWidth(3, 120)

            self.table.verticalHeader().setVisible(False)
            self.table.verticalHeader().setDefaultSectionSize(40)
            self.table.setFocusPolicy(Qt.NoFocus)

            th = min(len(self.corrections) * 40 + 38, 250)
            self.table.setFixedHeight(th)

            self.table.setStyleSheet("""
                QTableWidget { border: 1px solid #E5E5EA; border-radius: 8px; background-color: #FFFFFF; outline: none; gridline-color: transparent; }
                QTableWidget::item { padding: 4px 8px; border-bottom: 1px solid #F2F2F7; font-size: 12px; color: #1D1D1F; }
                QHeaderView::section { background-color: #FAFAFA; border: none; border-bottom: 1px solid #E5E5EA; font-size: 11px; font-weight: bold; color: #8E8E93; height: 32px; padding-left: 8px;}
            """)

            for row, r_data in enumerate(self.corrections):
                orig, status, sugg, score = r_data[2], r_data[3], r_data[4], r_data[5]

                item_o = QTableWidgetItem(orig)
                item_s = QTableWidgetItem(sugg)

                if status == "NOT_FOUND":
                    item_s.setForeground(QColor("#FF3B30"))
                    badge = create_status_badge("Mismatch", "#FFECEB", "#FF3B30")
                else:
                    item_s.setForeground(QColor("#0071E3"))
                    badge = create_status_badge("Similar", "#FFF9E5", "#FF9500")

                chk_w = TableCheckBoxWidget(checked=(status != "NOT_FOUND"))

                self.table.setCellWidget(row, 0, chk_w)
                self.table.setItem(row, 1, item_o)
                self.table.setItem(row, 2, item_s)
                self.table.setCellWidget(row, 3, badge)

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
                if sugg != "No safe match":
                    to_apply[orig] = sugg
        return to_apply


class Subtab5ReconUI(QWidget):
    log_msg = pyqtSignal(str)
    progress_update = pyqtSignal(str, int, str)

    def __init__(self):
        super().__init__()
        self.csv_path = ""
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
        self.global_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.global_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")

        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(20)

        main_card = QFrame()
        main_card.setObjectName("ReconMainCard")
        main_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        main_card.setStyleSheet(
            "QFrame#ReconMainCard { background-color: #ffffff; border: 1px solid #e5e5ea; border-radius: 16px; }"
        )
        card_layout = QVBoxLayout(main_card)
        card_layout.setContentsMargins(25, 25, 25, 25)
        card_layout.setSpacing(15)

        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(4)

        self.title_lbl = QLabel("Data Reconciliation")
        self.title_lbl.setObjectName("SubHeader")
        self.title_lbl.setStyleSheet(
            "border: none; background: transparent; color: #1D1D1F;"
        )
        header_vbox.addWidget(self.title_lbl)

        self.desc_lbl = QLabel(
            "Compares species labels across CSV, FASTA, and NWK files to detect mismatches."
        )
        self.desc_lbl.setObjectName("SubText")
        self.desc_lbl.setStyleSheet(
            "border: none; background: transparent; color: #515154;"
        )
        header_vbox.addWidget(self.desc_lbl)

        card_layout.addLayout(header_vbox)

        drop_layout = QHBoxLayout()
        drop_layout.setContentsMargins(0, 0, 0, 0)
        drop_layout.setSpacing(15)

        self.dz_csv = UnifiedDropZone(
            [".csv"], "Master CSV", show_dropdown=True, file_type="csv"
        )
        self.dz_csv.files_updated.connect(self.handle_csv)

        self.dz_fasta = UnifiedDropZone(
            [".fasta", ".fas", ".fa"],
            "Target FASTA",
            show_dropdown=False,
            file_type="fasta",
            show_gene_input=False,
        )
        self.dz_fasta.files_updated.connect(self.handle_fasta)

        self.dz_nwk = UnifiedDropZone(
            [".nwk", ".tre", ".tree"],
            "Target NWK",
            show_dropdown=False,
            file_type="nwk",
            show_gene_input=False,
        )
        self.dz_nwk.files_updated.connect(self.handle_nwk)

        for dz in [self.dz_csv, self.dz_fasta, self.dz_nwk]:
            dz.setMinimumWidth(100)
            dz.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)

        drop_layout.addWidget(self.dz_csv, stretch=1)
        drop_layout.addWidget(self.dz_fasta, stretch=1)
        drop_layout.addWidget(self.dz_nwk, stretch=1)

        card_layout.addLayout(drop_layout)

        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setFrameShape(QFrame.NoFrame)
        self.results_scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: transparent; outline: none; }"
        )
        self.results_scroll.setMinimumHeight(200)
        self.results_scroll.setMaximumHeight(400)

        self.results_container = QWidget()
        self.results_container.setObjectName("ResContainer")
        self.results_container.setStyleSheet(
            "QWidget#ResContainer { background: transparent; border: none; outline: none; }"
        )
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(10)
        self.results_layout.setAlignment(Qt.AlignTop)

        self.cat_csv_fas = CategorySection(
            "1. Master CSV vs Target FASTA (Update FASTA)"
        )
        self.cat_csv_nwk = CategorySection("2. Master CSV vs Target NWK (Update NWK)")
        self.cat_fas_nwk = CategorySection(
            "3. Reference FASTA vs Target NWK (Update NWK)"
        )
        self.cat_nwk_fas = CategorySection(
            "4. Reference NWK vs Target FASTA (Update FASTA)"
        )

        self.results_layout.addWidget(self.cat_csv_fas)
        self.results_layout.addWidget(self.cat_csv_nwk)
        self.results_layout.addWidget(self.cat_fas_nwk)
        self.results_layout.addWidget(self.cat_nwk_fas)

        self.results_scroll.setWidget(self.results_container)
        self.results_scroll.hide()
        card_layout.addWidget(self.results_scroll)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #E5E5EA; margin-top: 10px; margin-bottom: 5px;")
        card_layout.addWidget(separator)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)

        self.btn_verify = ActionButton(" Run Verification", "mdi.play")
        self.btn_verify.clicked.connect(self.run_verification)
        btn_layout.addWidget(self.btn_verify, stretch=1)
        self.btn_apply = PrimaryButton(
            " Change && Save All Reconciled Files", "mdi.play"
        )
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.apply_changes)
        btn_layout.addWidget(self.btn_apply, stretch=1)

        card_layout.addLayout(btn_layout)

        self.notify_lbl = QLabel("")
        self.notify_lbl.setAlignment(Qt.AlignCenter)
        self.notify_lbl.setStyleSheet(
            "font-size: 13px; font-weight: bold; border:none; background: transparent;"
        )
        self.notify_lbl.hide()
        card_layout.addWidget(self.notify_lbl)

        main_layout.addWidget(main_card, 0, Qt.AlignTop)
        main_layout.addStretch(1)

        self.global_scroll.setWidget(scroll_content)
        master_layout.addWidget(self.global_scroll)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()

        short_text = 'Drag & drop... <span style="color: #0071E3; text-decoration: underline;">browse</span>'
        long_text = 'Drag & drop files here, or <span style="color: #0071E3; text-decoration: underline;">click to browse</span>'

        for dz in [self.dz_csv, self.dz_fasta, self.dz_nwk]:
            if hasattr(dz, "main_text"):
                if w < 1000:
                    dz.main_text.setText(short_text)
                else:
                    dz.main_text.setText(long_text)

    def handle_csv(self, files):
        if files:
            path = files[0]
            self.csv_path = path
            headers = t1_st1_logic.load_csv_headers(path)
            if path in self.dz_csv.item_widgets:
                self.dz_csv.item_widgets[path].set_headers(headers)
            self.log_msg.emit(f"[INFO] Master CSV Loaded: {Path(path).name}")
        else:
            self.csv_path = ""

    def handle_fasta(self, files):
        self.fasta_files = files
        if files:
            self.log_msg.emit(f"[INFO] Loaded {len(files)} FASTA file(s).")

    def handle_nwk(self, files):
        self.nwk_files = files
        if files:
            self.log_msg.emit(f"[INFO] Loaded {len(files)} NWK file(s).")

    def run_verification(self):
        self.log_msg.emit("[PROCESS] Initialization: Validating input files...")
        for f in self.fasta_files + self.nwk_files:
            stem_lower = Path(f).stem.lower()
            if not any(tag in stem_lower for tag in ["_fmt", "_rec", "_tagged"]):
                self.log_msg.emit(
                    f"[WARNING] File format error: '{Path(f).name}' lacks required formatting tags ('_fmt', '_rec', or '_tagged')."
                )
                self.notify_lbl.setText("Format required. Check system log.")
                self.notify_lbl.setStyleSheet(
                    "color: #FF3B30; font-weight: bold; border:none; background: transparent;"
                )
                self.notify_lbl.show()
                return

        loaded_types = sum(
            [bool(self.csv_path), len(self.fasta_files) > 0, len(self.nwk_files) > 0]
        )
        if loaded_types < 2:
            self.log_msg.emit(
                "[WARNING] Insufficient data. Requires at least TWO types of inputs (e.g., CSV+FASTA, CSV+NWK) for cross-validation."
            )
            self.notify_lbl.setText("Missing Data. Check system log.")
            self.notify_lbl.setStyleSheet(
                "color: #FF3B30; font-weight: bold; border:none; background: transparent;"
            )
            self.notify_lbl.show()
            return

        col = ""
        if self.csv_path and self.csv_path in self.dz_csv.item_widgets:
            col = self.dz_csv.item_widgets[self.csv_path].combo.currentText()

        self.log_msg.emit(
            f"[PROCESS] Executing Verification: Cross-referencing {len(self.fasta_files)} FASTA(s) and {len(self.nwk_files)} NWK(s) against Master CSV..."
        )

        try:
            self.cat_csv_fas.clear()
            self.cat_csv_nwk.clear()
            self.cat_fas_nwk.clear()
            self.cat_nwk_fas.clear()
            self.result_blocks = []

            results = t1_st5_logic.run_smart_verification(
                self.csv_path,
                col,
                self.fasta_files,
                self.nwk_files,
            )

            total_mismatches = 0

            def _build_blocks(res_list, category_section):
                nonlocal total_mismatches
                grouped = {}
                for r in res_list:
                    key = (r[0], r[1])
                    grouped.setdefault(key, []).append(r)
                for (src, fname), file_results in grouped.items():
                    block = ReconResultBlock(src, fname, file_results)
                    total_mismatches += len(block.corrections)
                    block.apply_requested.connect(self.apply_specific_block)
                    category_section.add_block(block)
                    self.result_blocks.append(block)

            _build_blocks(results["CSV_FAS"], self.cat_csv_fas)
            _build_blocks(results["CSV_NWK"], self.cat_csv_nwk)
            _build_blocks(results["FAS_NWK"], self.cat_fas_nwk)
            _build_blocks(results["NWK_FAS"], self.cat_nwk_fas)

            self.results_scroll.show()
            self.btn_apply.setEnabled(True)

            self.log_msg.emit(
                f"[SUCCESS] Verification Complete: Identified {total_mismatches} total discrepancies across all file pairs."
            )

            if total_mismatches == 0:
                self.notify_lbl.setText("Perfect Match! No changes required.")
                self.notify_lbl.setStyleSheet(
                    "color: #34C759; font-weight: bold; border:none; background: transparent;"
                )
            else:
                self.notify_lbl.setText(
                    f"Found {total_mismatches} mismatch(es). Review and apply changes."
                )
                self.notify_lbl.setStyleSheet(
                    "color: #0071E3; font-weight: bold; border:none; background: transparent;"
                )
            self.notify_lbl.show()

        except Exception as e:
            self.log_msg.emit(f"[ERROR] Verification engine failure: {e}")
            self.notify_lbl.setText("Verification failed. Check system log.")
            self.notify_lbl.setStyleSheet(
                "color: #FF3B30; font-weight: bold; border:none; background: transparent;"
            )
            self.notify_lbl.show()

    def apply_specific_block(self, block):
        self.apply_changes(specific_block=block)

    def apply_changes(self, specific_block=None):
        if isinstance(specific_block, bool):
            specific_block = None

        blocks_to_process = [specific_block] if specific_block else self.result_blocks

        fasta_corrections = {}
        nwk_corrections = {}

        target_fasta_files = []
        target_nwk_files = []

        self.log_msg.emit("[PROCESS] Compiling selected corrections from UI...")

        for block in blocks_to_process:
            selected = block.get_selected_corrections()

            if block.src in ["FASTA", "NWK_FAS"]:
                fasta_corrections.update(selected)
                target_name = (
                    block.fname
                    if block.src == "FASTA"
                    else block.fname.split(" vs ")[1]
                )
                for f in self.fasta_files:
                    if Path(f).name == target_name and f not in target_fasta_files:
                        target_fasta_files.append(f)

            elif block.src in ["NWK", "FAS_NWK"]:
                nwk_corrections.update(selected)
                target_name = (
                    block.fname if block.src == "NWK" else block.fname.split(" vs ")[1]
                )
                for f in self.nwk_files:
                    if Path(f).name == target_name and f not in target_nwk_files:
                        target_nwk_files.append(f)

        if not target_fasta_files and not target_nwk_files:
            self.log_msg.emit(
                "[WARNING] No target files selected or available for correction."
            )
            return

        try:
            self.log_msg.emit(
                f"[PROCESS] Execution Started: Applying {len(fasta_corrections)} FASTA updates and {len(nwk_corrections)} NWK updates..."
            )
            self.progress_update.emit(
                "Data_Reconciliation_Job", 10, "Initializing rewrite protocols..."
            )

            fs, ns, rs = t1_st5_logic.apply_and_save_reconciled(
                target_fasta_files,
                fasta_corrections,
                target_nwk_files,
                nwk_corrections,
                blocks_to_process,
            )

            self.progress_update.emit("Data_Reconciliation_Job", 100, "Completed")

            msg = f"Reconciled files exported successfully. [{len(fs)} FASTA | {len(ns)} NWK | {len(rs)} Reports]"
            if specific_block:
                msg = f"Block applied: {specific_block.fname}. " + msg

            self.log_msg.emit(f"[SUCCESS] {msg}")
            self.notify_lbl.setText(
                f"Successfully saved {len(fs)+len(ns)} reconciled files!"
            )
            self.notify_lbl.setStyleSheet(
                "color: #34C759; font-weight: bold; border:none; background: transparent;"
            )
            self.notify_lbl.show()

        except Exception as e:
            self.progress_update.emit("Data_Reconciliation_Job", 0, "Error Occurred")
            self.log_msg.emit(f"[ERROR] File write operation failed: {e}")
            self.notify_lbl.setText("Failed to save changes. Check system log.")
            self.notify_lbl.setStyleSheet(
                "color: #FF3B30; font-weight: bold; border:none; background: transparent;"
            )
            self.notify_lbl.show()
