from pathlib import Path

import qtawesome as qta
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QColor
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

from hyphlow import (
    manifest_logic_tab,
    t1_st1_logic,
    t1_st5_logic,
)
from hyphlow.common_ui import (
    BLUE,
    DIM,
    FLAT,
    FS_BODY,
    FS_FIELD,
    FS_SMALL,
    FS_TINY,
    GREEN,
    GREEN_DARK,
    GREEN_FILL,
    INK,
    INK_FAINT,
    INK_HOVER,
    INK_MUTED,
    LINE,
    ORANGE,
    ORANGE_FILL,
    RADIUS,
    RADIUS_SMALL,
    RED,
    RED_FILL,
    SURFACE,
    SURFACE_ALT,
    ActionButton,
    PrimaryButton,
    TableCheckBoxWidget,
    UnifiedDropZone,
    card,
)

# ============================================================ constants
ROW_H_RECON = 40
TABLE_MAX_H = 250
MAX_FILES_SHOWN = 3
RECON_JOB = "Data_Reconciliation_Job"


def _badge_style(bg, fg):
    return (
        f"background: {bg}; color: {fg}; padding: 4px 8px;"
        f" border-radius: {RADIUS_SMALL}px; font-size: {FS_TINY}px;"
        f" font-weight: bold; border: none;"
    )


def create_status_badge(text, bg_color, text_color):
    wrapper = QWidget()
    wrapper.setAttribute(Qt.WA_TranslucentBackground)
    wrapper.setStyleSheet(FLAT)
    layout = QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(
        f"background-color: {bg_color}; color: {text_color}; border-radius: 4px;"
        f" font-weight: bold; font-size: {FS_TINY}px; padding: 4px 8px;"
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
            f"font-size: {FS_BODY}px; font-weight: 700; color: {INK_MUTED};"
            f" padding-left: 5px; {FLAT}"
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
        self.corrections = [
            r
            for r in file_results
            if r[3] in (t1_st5_logic.SIMILAR, t1_st5_logic.NOT_FOUND)
        ]

        self.setStyleSheet(
            f"QFrame#Block {{ border: 1px solid {LINE};"
            f" border-radius: {RADIUS_SMALL}px; background: {DIM}; }}"
        )
        self.setObjectName("Block")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QFrame()
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setStyleSheet(FLAT)
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(15, 10, 15, 10)

        icon_lbl = QLabel()
        icon_name = "mdi.file-document-outline"
        if src in ["NWK", "FAS_NWK"]:
            icon_name = "mdi.file-tree"
        icon_lbl.setPixmap(qta.icon(icon_name, color=INK_MUTED).pixmap(18, 18))
        h_layout.addWidget(icon_lbl)

        name_lbl = QLabel(self.fname)
        name_lbl.setStyleSheet(
            f"font-size: {FS_BODY}px; font-weight: 500; color: {INK}; {FLAT}"
        )
        h_layout.addWidget(name_lbl)

        total_cnt = len(file_results)
        mismatch_cnt = len(self.corrections)
        perfect_cnt = total_cnt - mismatch_cnt

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(6)
        stats_layout.setContentsMargins(10, 0, 0, 0)

        lbl_tot = QLabel(f"Total: {total_cnt}")
        lbl_tot.setStyleSheet(_badge_style(LINE, INK_MUTED))
        lbl_perf = QLabel(f"Perfect: {perfect_cnt}")
        lbl_perf.setStyleSheet(_badge_style(GREEN_FILL, GREEN_DARK))
        lbl_mis = QLabel(f"Mismatches: {mismatch_cnt}")
        if mismatch_cnt:
            lbl_mis.setStyleSheet(_badge_style(RED_FILL, RED))
        else:
            lbl_mis.setStyleSheet(_badge_style(LINE, INK_FAINT))

        stats_layout.addWidget(lbl_tot)
        stats_layout.addWidget(lbl_perf)
        stats_layout.addWidget(lbl_mis)
        h_layout.addLayout(stats_layout)
        h_layout.addStretch()

        self.btn_apply_block = QPushButton("Apply Changes")
        self.btn_apply_block.setIcon(qta.icon("mdi.play", color=SURFACE))
        self.btn_apply_block.setStyleSheet(
            f"QPushButton {{ background-color: {INK}; color: {SURFACE};"
            f" font-weight: bold; font-size: {FS_FIELD}px; padding: 6px 14px;"
            f" border-radius: {RADIUS_SMALL}px; border: none; }}"
            f"QPushButton:hover {{ background-color: {INK_HOVER}; }}"
        )
        self.btn_apply_block.setCursor(Qt.PointingHandCursor)
        self.btn_apply_block.clicked.connect(lambda: self.apply_requested.emit(self))
        h_layout.addWidget(self.btn_apply_block)

        self.toggle_icon = QLabel()
        self.toggle_icon.setPixmap(
            qta.icon("mdi.chevron-down", color=INK).pixmap(20, 20)
        )
        self.toggle_icon.setStyleSheet(FLAT)
        h_layout.addWidget(self.toggle_icon)
        layout.addWidget(self.header)

        self.content_area = QFrame()
        self.content_area.hide()
        self.content_area.setStyleSheet(FLAT)
        c_layout = QVBoxLayout(self.content_area)
        c_layout.setContentsMargins(15, 0, 15, 15)

        if not self.corrections:
            empty_lbl = QLabel(
                "All taxa match the reference perfectly. Report generation available."
            )
            empty_lbl.setStyleSheet(
                f"color: {INK_FAINT}; font-size: {FS_SMALL}px;"
                f" font-style: italic; {FLAT}"
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
            self.table.verticalHeader().setDefaultSectionSize(ROW_H_RECON)
            self.table.setFocusPolicy(Qt.NoFocus)

            th = min(len(self.corrections) * ROW_H_RECON + 38, TABLE_MAX_H)
            self.table.setFixedHeight(th)

            self.table.setStyleSheet(
                f"QTableWidget {{ border: 1px solid {LINE};"
                f" border-radius: {RADIUS}px; background-color: {SURFACE};"
                f" outline: none; gridline-color: transparent; }}"
                f"QTableWidget::item {{ padding: 4px 8px;"
                f" border-bottom: 1px solid {SURFACE_ALT};"
                f" font-size: {FS_FIELD}px; color: {INK}; }}"
                f"QHeaderView::section {{ background-color: {DIM};"
                f" border: none; border-bottom: 1px solid {LINE};"
                f" font-size: {FS_TINY}px; font-weight: bold;"
                f" color: {INK_FAINT}; height: 32px; padding-left: 8px; }}"
            )

            for row, r_data in enumerate(self.corrections):
                orig, status, sugg = r_data[2], r_data[3], r_data[4]

                item_o = QTableWidgetItem(orig)
                item_s = QTableWidgetItem(sugg)

                if status == t1_st5_logic.NOT_FOUND:
                    item_s.setForeground(QColor(RED))
                    badge = create_status_badge("Mismatch", RED_FILL, RED)
                else:
                    item_s.setForeground(QColor(BLUE))
                    badge = create_status_badge("Similar", ORANGE_FILL, ORANGE)

                chk_w = TableCheckBoxWidget(checked=(status != t1_st5_logic.NOT_FOUND))

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
            icon = "mdi.chevron-down"
        else:
            self.content_area.show()
            icon = "mdi.chevron-up"
        self.toggle_icon.setPixmap(qta.icon(icon, color=INK).pixmap(20, 20))

    def get_selected_corrections(self):
        to_apply = {}
        if not self.corrections:
            return to_apply
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if w and w.is_checked:
                orig = self.table.item(r, 1).text()
                sugg = self.table.item(r, 2).text()
                if sugg != t1_st5_logic.NO_MATCH_LABEL:
                    to_apply[orig] = sugg
        return to_apply


class _VerifyThread(QThread):
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, csv_path, csv_col, fasta_files, nwk_files):
        super().__init__()
        self.csv_path = csv_path
        self.csv_col = csv_col
        self.fasta_files = fasta_files
        self.nwk_files = nwk_files

    def run(self):
        try:
            results = t1_st5_logic.run_smart_verification(
                self.csv_path, self.csv_col, self.fasta_files, self.nwk_files
            )
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished.emit(results)


class _ApplyThread(QThread):
    finished = pyqtSignal(list, list, list)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(
        self,
        fasta_files,
        fasta_corrections,
        nwk_files,
        nwk_corrections,
        status_lookup,
    ):
        super().__init__()
        self.fasta_files = fasta_files
        self.fasta_corrections = fasta_corrections
        self.nwk_files = nwk_files
        self.nwk_corrections = nwk_corrections
        self.status_lookup = status_lookup

    def run(self):
        try:
            fs, ns, rs = t1_st5_logic.apply_and_save_reconciled(
                self.fasta_files,
                self.fasta_corrections,
                self.nwk_files,
                self.nwk_corrections,
                self.status_lookup,
                self.progress.emit,
            )
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished.emit(fs, ns, rs)


class Subtab5ReconUI(QWidget):
    log_msg = pyqtSignal(str)
    progress_update = pyqtSignal(str, int, str)

    def __init__(self):
        super().__init__()
        self.csv_path = ""
        self.fasta_files = []
        self.nwk_files = []
        self.result_blocks = []
        self.verify_thread = None
        self.apply_thread = None
        self.applied_block = None
        self._setup_ui()

    def _setup_ui(self):
        master_layout = QVBoxLayout(self)
        master_layout.setContentsMargins(0, 0, 0, 0)

        self.global_scroll = QScrollArea()
        self.global_scroll.setWidgetResizable(True)
        self.global_scroll.setFrameShape(QFrame.NoFrame)
        self.global_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.global_scroll.setStyleSheet(f"QScrollArea {{ {FLAT} }}")

        scroll_content = QWidget()
        scroll_content.setStyleSheet(FLAT)

        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(20)

        main_card = QFrame()
        main_card.setObjectName("ReconMainCard")
        main_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        main_card.setStyleSheet(card(name="ReconMainCard"))
        card_layout = QVBoxLayout(main_card)
        card_layout.setContentsMargins(25, 25, 25, 25)
        card_layout.setSpacing(15)

        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(4)

        self.title_lbl = QLabel("Data Reconciliation")
        self.title_lbl.setObjectName("SubHeader")
        self.title_lbl.setStyleSheet(f"{FLAT} color: {INK};")
        header_vbox.addWidget(self.title_lbl)

        self.desc_lbl = QLabel(
            "Compares species labels across CSV, FASTA, and NWK files to detect mismatches."
        )
        self.desc_lbl.setObjectName("SubText")
        self.desc_lbl.setStyleSheet(f"{FLAT} color: {INK_MUTED};")
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
        self.results_scroll.setStyleSheet(f"QScrollArea {{ {FLAT} outline: none; }}")
        self.results_scroll.setMinimumHeight(200)
        self.results_scroll.setMaximumHeight(400)

        self.results_container = QWidget()
        self.results_container.setObjectName("ResContainer")
        self.results_container.setStyleSheet(
            f"QWidget#ResContainer {{ {FLAT} outline: none; }}"
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
        separator.setStyleSheet(f"color: {LINE}; margin-top: 10px; margin-bottom: 5px;")
        card_layout.addWidget(separator)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)

        self.btn_verify = PrimaryButton(" Run Verification", "mdi.play")
        self.btn_verify.clicked.connect(self.run_verification)
        btn_layout.addWidget(self.btn_verify, stretch=1)
        self.btn_apply = ActionButton(
            " Change && Save All Reconciled Files", "mdi.content-save"
        )
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.apply_changes)
        btn_layout.addWidget(self.btn_apply, stretch=1)

        card_layout.addLayout(btn_layout)

        self.notify_lbl = QLabel("")
        self.notify_lbl.setAlignment(Qt.AlignCenter)
        self.notify_lbl.setStyleSheet(
            f"font-size: {FS_SMALL}px; font-weight: bold; {FLAT}"
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

        link = f'style="color: {BLUE}; text-decoration: underline;"'
        short_text = f"Drag & drop ... <span {link}>browse</span>"
        long_text = f"Drag & drop files here, or <span {link}>click to browse</span>"

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

    def _notify(self, text, color):
        self.notify_lbl.setText(text)
        self.notify_lbl.setStyleSheet(f"color: {color}; font-weight: bold; {FLAT}")
        self.notify_lbl.show()

    def run_verification(self):
        self.log_msg.emit("[PROCESS] Initialization: Validating input files...")

        proj = t1_st1_logic.CURRENT_PROJECT_PATH
        unregistered = []
        for f in self.fasta_files + self.nwk_files:
            if not proj:
                break
            org, gene = manifest_logic_tab.identity_for_path(proj, f)
            if not (org or gene):
                unregistered.append(Path(f).name)

        if unregistered:
            shown = ", ".join(unregistered[:MAX_FILES_SHOWN])
            if len(unregistered) > MAX_FILES_SHOWN:
                shown += "..."
            self.log_msg.emit(
                f"[WARNING] {len(unregistered)} file(s) are not in the "
                f"project manifest: {shown}"
            )
            self.log_msg.emit(
                "[INFO] Proceeding anyway. Results may not be traceable to a "
                "pipeline stage."
            )

        loaded_types = sum(
            [bool(self.csv_path), len(self.fasta_files) > 0, len(self.nwk_files) > 0]
        )
        if loaded_types < 2:
            self.log_msg.emit(
                "[WARNING] Insufficient data. Requires at least TWO types of inputs (e.g., CSV+FASTA, CSV+NWK) for cross-validation."
            )
            self._notify("Missing Data. Check system log.", RED)
            return

        col = ""
        if self.csv_path and self.csv_path in self.dz_csv.item_widgets:
            col = self.dz_csv.item_widgets[self.csv_path].combo.currentText()

        self.log_msg.emit(
            f"[PROCESS] Executing Verification: Cross-referencing {len(self.fasta_files)} FASTA(s) and {len(self.nwk_files)} NWK(s) against Master CSV..."
        )

        self.cat_csv_fas.clear()
        self.cat_csv_nwk.clear()
        self.cat_fas_nwk.clear()
        self.cat_nwk_fas.clear()
        self.result_blocks = []

        self.btn_verify.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.progress_update.emit(RECON_JOB, 0, "Verifying...")

        self.verify_thread = _VerifyThread(
            self.csv_path, col, self.fasta_files, self.nwk_files
        )
        self.verify_thread.finished.connect(self.on_verify_finished)
        self.verify_thread.failed.connect(self.on_verify_failed)
        self.verify_thread.start()

    def on_verify_failed(self, error):
        self.btn_verify.setEnabled(True)
        self.progress_update.emit(RECON_JOB, 0, "Error Occurred")
        self.log_msg.emit(f"[ERROR] Verification engine failure: {error}")
        self._notify("Verification failed. Check system log.", RED)

    def on_verify_finished(self, results):
        self.btn_verify.setEnabled(True)
        self.progress_update.emit(RECON_JOB, 100, "Verification complete")

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
            self._notify("Perfect Match! No changes required.", GREEN)
        else:
            self._notify(
                f"Found {total_mismatches} mismatch(es). " f"Review and apply changes.",
                BLUE,
            )

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

        self.log_msg.emit(
            f"[PROCESS] Execution Started: Applying {len(fasta_corrections)} FASTA updates and {len(nwk_corrections)} NWK updates..."
        )

        # Widgets are read here, on the GUI thread; the worker only ever sees the plain dict this produces
        status_lookup = t1_st5_logic.build_status_lookup(
            (b.fname, b.corrections) for b in blocks_to_process
        )

        self.applied_block = specific_block
        self.btn_verify.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.progress_update.emit(RECON_JOB, 0, "Initializing rewrite protocols...")

        self.apply_thread = _ApplyThread(
            target_fasta_files,
            fasta_corrections,
            target_nwk_files,
            nwk_corrections,
            status_lookup,
        )
        self.apply_thread.progress.connect(self.on_apply_progress)
        self.apply_thread.finished.connect(self.on_apply_finished)
        self.apply_thread.failed.connect(self.on_apply_failed)
        self.apply_thread.start()

    def on_apply_progress(self, curr, tot):
        val = int((curr / tot) * 100) if tot else 0
        self.progress_update.emit(RECON_JOB, val, "Writing reconciled files...")

    def on_apply_failed(self, error):
        self.btn_verify.setEnabled(True)
        self.btn_apply.setEnabled(True)
        self.progress_update.emit(RECON_JOB, 0, "Error Occurred")
        self.log_msg.emit(f"[ERROR] File write operation failed: {error}")
        self._notify("Failed to save changes. Check system log.", RED)

    def on_apply_finished(self, fs, ns, rs):
        self.btn_verify.setEnabled(True)
        self.btn_apply.setEnabled(True)
        self.progress_update.emit(RECON_JOB, 100, "Completed")

        msg = (
            f"Reconciled files exported successfully. "
            f"[{len(fs)} FASTA | {len(ns)} NWK | {len(rs)} Reports]"
        )
        if self.applied_block:
            msg = f"Block applied: {self.applied_block.fname}. " + msg

        self.log_msg.emit(f"[SUCCESS] {msg}")
        self._notify(f"Successfully saved {len(fs) + len(ns)} reconciled files!", GREEN)
