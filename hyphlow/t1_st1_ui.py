from pathlib import Path

import qtawesome as qta
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hyphlow import common_ui, t1_st1_logic, t1_st2_logic
from hyphlow.common_ui import (
    PrimaryButton,
    StandardTable,
    TableCheckBoxWidget,
    UnifiedDropZone,
)

BADGE = (
    "padding: 3px 8px; border-radius: 6px;"
    f" font-size: {common_ui.FS_FIELD}px; font-weight: bold;"
)
BADGE_REVIEW = f"background: {common_ui.RED_FILL}; color: {common_ui.RED}; {BADGE}"
BADGE_UNMATCHED = (
    f"background: {common_ui.ORANGE_FILL}; color: {common_ui.ORANGE}; {BADGE}"
)
BADGE_CLEAN = f"background: {common_ui.GREEN_FILL}; color: {common_ui.GREEN}; {BADGE}"

BLOCK_FRAME = (
    f"QFrame#Block {{ border: 1px solid {common_ui.LINE};"
    f" border-radius: {common_ui.RADIUS}px; background: {common_ui.SURFACE}; }}"
)

SUBSPECIES = "#9333EA"
TABLE_CHROME_H, TABLE_MAX_H = 38, 300

CARD_FRAME = (
    f"QFrame {{ background-color: {common_ui.SURFACE};"
    f" border: 1px solid {common_ui.LINE}; border-radius: 10px; }}"
)
HEADER_FRAME = (
    f"QFrame {{ {common_ui.FLAT} border-radius: {common_ui.RADIUS}px; }}"
    f"QFrame:hover {{ background-color: {common_ui.DIM}; }}"
)
PAGE_MARGINS = (40, 30, 40, 30)

PBAR_CSS = (
    f"QProgressBar {{ background-color: {common_ui.SURFACE_ALT};"
    f" border-radius: 3px; border: none;"
    f" margin-top: 10px; margin-bottom: 2px; }}"
    f"QProgressBar::chunk {{ background-color: {common_ui.GREEN};"
    f" border-radius: 3px; }}"
)
RES_CONTAINER = (
    f"QFrame#ResContainer {{ border: 1px solid {common_ui.LINE};"
    f" border-radius: {common_ui.RADIUS}px; background: {common_ui.DIM}; }}"
)

PBAR_H = 6
DROP_MAX_H_CSV, DROP_MAX_H_SEQ = 150, 130


class ValidationThread(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(dict)

    def __init__(self, file_col_pairs):
        super().__init__()
        self.file_col_pairs = file_col_pairs
        self.is_cancelled = False
        self._last_pct = -1

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        self._last_pct = -1
        file_results = {}
        tot_files = len(self.file_col_pairs)

        for idx, (path, col) in enumerate(self.file_col_pairs):
            if self.is_cancelled:
                return

            def prog(curr, tot, idx=idx):
                if self.is_cancelled:
                    raise t1_st1_logic.ValidationCancelled()
                # The bar has 100 steps, so re-emitting the same integer only
                # floods the event loop.

                overall = int(((idx + curr / tot) / tot_files) * 100)
                if overall != self._last_pct:
                    self._last_pct = overall
                    self.progress.emit(overall, 100)

            try:
                file_results[path] = t1_st1_logic.run_validation_pipeline(
                    path, col, prog
                )
            except t1_st1_logic.ValidationCancelled:
                return
        if not self.is_cancelled:
            self.finished.emit(file_results)


class _FormatThread(QThread):
    finished = pyqtSignal(list, str, int)
    progress = pyqtSignal(int, int)
    pipeline = None

    def __init__(self, file_paths, identity_dict=None):
        super().__init__()
        self.file_paths = file_paths
        self.identity_dict = identity_dict or {}
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def _progress_callback(self, curr, tot):
        if self.is_cancelled:
            raise t1_st1_logic.ValidationCancelled()
        self.progress.emit(curr, tot)

    def run(self):
        if self.is_cancelled:
            return
        try:
            # None is the gene_dict slot; t1_st2_logic still declares it
            results, rep_path = self.pipeline(
                self.file_paths,
                None,
                self.identity_dict,
                self._progress_callback,
            )
        except t1_st1_logic.ValidationCancelled:
            return
        if not self.is_cancelled:
            self.finished.emit(results, str(rep_path), 0)


class FastaFormatThread(_FormatThread):
    pipeline = staticmethod(t1_st2_logic.run_fasta_pipeline)


class NwkFormatThread(_FormatThread):
    pipeline = staticmethod(t1_st2_logic.run_nwk_pipeline)


class ResultFileBlock(QFrame):
    def __init__(self, file_path, results):
        super().__init__()
        self.file_path = file_path
        self.results = results
        self.corrections = [r for r in results if r.status in t1_st1_logic.NEEDS_REVIEW]
        self.unmatched = [
            r
            for r in results
            if r.status in (t1_st1_logic.NOT_FOUND, t1_st1_logic.ERROR)
        ]
        self.filename = Path(file_path).name

        self.setStyleSheet(BLOCK_FRAME)
        self.setObjectName("Block")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QFrame()
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setStyleSheet(common_ui.FLAT)
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(15, 12, 15, 12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(
            qta.icon("mdi.file-document-outline", color=common_ui.BLUE).pixmap(20, 20)
        )
        h_layout.addWidget(icon_lbl)

        name_lbl = QLabel(self.filename)
        name_lbl.setStyleSheet(
            f"font-size: {common_ui.FS_BODY}px; font-weight: 600;"
            f" color: {common_ui.INK};"
        )
        h_layout.addWidget(name_lbl)

        h_layout.addWidget(self._badge())
        h_layout.addStretch()

        self.toggle_icon = QLabel()
        h_layout.addWidget(self.toggle_icon)
        self._set_chevron("down")

        layout.addWidget(self.header)

        self.content_area = QFrame()
        self.content_area.hide()
        c_layout = QVBoxLayout(self.content_area)
        c_layout.setContentsMargins(15, 0, 15, 15)
        c_layout.addWidget(self._build_table() if self.corrections else self._empty())

        layout.addWidget(self.content_area)
        self.header.mousePressEvent = self.toggle

    def _badge(self):
        if self.corrections:
            text, style = f"{len(self.corrections)} to review", BADGE_REVIEW
        elif self.unmatched:
            text, style = f"{len(self.unmatched)} unmatched", BADGE_UNMATCHED
        else:
            text, style = "All matched", BADGE_CLEAN
        badge = QLabel(text)
        badge.setStyleSheet(style)
        return badge

    def _empty(self):
        # corrections only holds NEEDS_REVIEW, so an empty list does not mean
        # every name matched; unmatched ones are counted separately.
        if self.unmatched:
            text = (
                f"{len(self.unmatched)} name(s) could not be matched and were kept "
                "unchanged. See the report for details."
            )
        else:
            text = "No corrections needed. Every name matched NCBI taxonomy."
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {common_ui.INK_FAINT}; font-size: {common_ui.FS_SMALL}px;"
            " font-style: italic;"
        )
        return lbl

    def _build_table(self):
        self.table = StandardTable(
            ["Apply", "Original Name", "Suggested", "Score", "Detail"]
        )
        self.table.setRowCount(len(self.corrections))

        header = self.table.horizontalHeader()
        for col, mode in enumerate(
            (
                QHeaderView.Fixed,
                QHeaderView.Stretch,
                QHeaderView.Stretch,
                QHeaderView.Fixed,
                QHeaderView.Stretch,
            )
        ):
            header.setSectionResizeMode(col, mode)

        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(3, 90)
        self.table.setFixedHeight(
            min(
                len(self.corrections) * common_ui.ROW_H + TABLE_CHROME_H,
                TABLE_MAX_H,
            )
        )

        tints = {
            t1_st1_logic.SUBS_NOT_FOUND: SUBSPECIES,
            t1_st1_logic.MULTIPLE_HITS: common_ui.ORANGE,
            t1_st1_logic.ABOVE_SPECIES: common_ui.ORANGE,
            t1_st1_logic.OPEN_NOMENCLATURE: common_ui.ORANGE,
        }

        for row, r in enumerate(self.corrections):
            # Only SIMILAR carries a name to apply; for the others the suggestion
            # equals the original, so accepting one would change nothing.
            applicable = r.status == t1_st1_logic.SIMILAR
            tint = QColor(tints.get(r.status, common_ui.BLUE))

            item_o = QTableWidgetItem(r.original)
            item_s = QTableWidgetItem(r.suggested)
            item_s.setForeground(tint)

            # No single score exists when several taxa share one name.

            item_c = QTableWidgetItem(
                "—" if r.status == t1_st1_logic.MULTIPLE_HITS else f"{r.score:.1f}%"
            )
            item_c.setTextAlignment(Qt.AlignCenter)
            item_c.setForeground(QColor(common_ui.INK_FAINT) if applicable else tint)

            item_d = QTableWidgetItem(r.note)
            item_d.setToolTip(r.note)

            chk_w = TableCheckBoxWidget(checked=applicable)
            chk_w.setEnabled(applicable)

            self.table.setCellWidget(row, 0, chk_w)
            for col, item in enumerate((item_o, item_s, item_c, item_d), start=1):
                self.table.setItem(row, col, item)

        return self.table

    def _set_chevron(self, direction):
        self.toggle_icon.setPixmap(
            qta.icon(f"mdi.chevron-{direction}", color=common_ui.INK).pixmap(20, 20)
        )

    def toggle(self, event):
        visible = self.content_area.isVisible()
        self.content_area.setVisible(not visible)
        self._set_chevron("down" if visible else "up")

    def get_selected_corrections(self):
        to_apply = {}
        for row, r in enumerate(self.corrections):
            w = self.table.cellWidget(row, 0)
            if w and w.is_checked and r.status == t1_st1_logic.SIMILAR:
                to_apply[r.original] = r.suggested
        return to_apply


class StandardizationPage(QWidget):
    applied = pyqtSignal(str, int)
    log_msg = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    file_progress_update = pyqtSignal(str, int, str)

    def __init__(self):
        super().__init__()
        self.csv_files = []
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
        self.global_scroll.setStyleSheet(f"QScrollArea {{ {common_ui.FLAT} }}")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")

        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(*PAGE_MARGINS)
        main_layout.setSpacing(20)

        self.card_csv, self.csv_content_area, self.btn_toggle_csv = self._card(
            "CSV Species Label Validation",
            "Checks and corrects CSV species labels using the NCBI taxonomy database.",
            self._build_csv_ui,
            expanded=True,
        )
        main_layout.addWidget(self.card_csv)

        self.card_format, self.fmt_content_area, self.btn_toggle_fmt = self._card(
            "FASTA/NWK Label Standardization",
            "Standardizes FASTA headers and NWK leaf names into species-level labels.",
            self._build_format_ui,
            expanded=False,
        )
        main_layout.addWidget(self.card_format)
        main_layout.addStretch()

        self.global_scroll.setWidget(scroll_content)
        master_layout.addWidget(self.global_scroll)

    def _card(self, title, desc, build, expanded):
        card = QFrame()
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        card.setStyleSheet(CARD_FRAME)
        col = QVBoxLayout(card)
        col.setContentsMargins(15, 15, 15, 15)
        col.setSpacing(10)

        content = QFrame()
        content.setStyleSheet(common_ui.FLAT)
        inner = QVBoxLayout(content)
        inner.setContentsMargins(0, 10, 0, 0)
        build(inner)
        content.setVisible(expanded)

        toggle_btn = QPushButton()
        toggle_btn.setStyleSheet(common_ui.FLAT)
        toggle_btn.setCursor(Qt.PointingHandCursor)
        toggle_btn.clicked.connect(lambda: self.toggle_card(content, toggle_btn))
        self._set_card_chevron(toggle_btn, expanded)

        col.addWidget(self._header(title, desc, toggle_btn, content))
        col.addWidget(content)
        return card, content, toggle_btn

    def _header(self, title, desc, toggle_btn, content):
        # The whole header is clickable, not just the chevron.
        frame = QFrame()
        frame.setStyleSheet(HEADER_FRAME)
        frame.setCursor(Qt.PointingHandCursor)
        frame.mousePressEvent = lambda e: self.toggle_card(content, toggle_btn)

        wrap = QVBoxLayout(frame)
        wrap.setContentsMargins(4, 4, 4, 4)

        row = QHBoxLayout()
        titles = QVBoxLayout()
        for text, name in ((title, "SubHeader"), (desc, "SubText")):
            lbl = QLabel(text)
            lbl.setObjectName(name)
            titles.addWidget(lbl)
        row.addLayout(titles)
        row.addStretch()
        row.addWidget(toggle_btn)
        wrap.addLayout(row)
        return frame

    @staticmethod
    def _set_card_chevron(btn, expanded):
        arrow = "up" if expanded else "down"
        btn.setIcon(qta.icon(f"mdi.chevron-{arrow}", color=common_ui.INK))

    def toggle_card(self, content_area, toggle_btn):
        expanded = not content_area.isVisible()
        content_area.setVisible(expanded)
        self._set_card_chevron(toggle_btn, expanded)

    @staticmethod
    def _progress_bar():
        bar = QProgressBar()
        bar.setFixedHeight(PBAR_H)
        bar.setTextVisible(False)
        bar.setStyleSheet(PBAR_CSS)
        bar.hide()
        return bar

    @staticmethod
    def _cap_drop_height(drop, max_h):
        # UnifiedDropZone builds its own scroll area; cap it so the card does
        # not grow past the fold.
        if not hasattr(drop, "scroll_area"):
            return
        drop.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        drop.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        drop.scroll_area.setWidgetResizable(True)
        drop.scroll_area.setMaximumHeight(max_h)

    def _build_csv_ui(self, layout):
        self.csv_drop_zone = UnifiedDropZone(
            [".csv"],
            "Supported formats: CSV",
            show_dropdown=True,
            file_type="csv",
            open_in_base_dir=True,
        )
        self.csv_drop_zone.files_updated.connect(self.handle_csv_files)
        self._cap_drop_height(self.csv_drop_zone, DROP_MAX_H_CSV)
        layout.addWidget(self.csv_drop_zone)

        self.csv_pbar = self._progress_bar()
        layout.addWidget(self.csv_pbar)

        self.csv_run_btn = PrimaryButton(" Run Validation", "mdi.play")
        self.is_csv_running = False
        self.csv_run_btn.clicked.connect(self.toggle_csv_validation)
        layout.addWidget(self.csv_run_btn)
        self.set_csv_run_state("run")

        self.results_container = QFrame()
        self.results_container.setObjectName("ResContainer")
        self.results_container.setStyleSheet(RES_CONTAINER)
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(10, 10, 10, 10)
        self.results_layout.setSpacing(10)
        self.results_container.hide()
        layout.addWidget(self.results_container)

        self.apply_container = QWidget()
        act = QVBoxLayout(self.apply_container)
        act.setContentsMargins(0, 5, 0, 0)
        act.setSpacing(8)

        self.csv_notify_lbl = QLabel("")
        self.csv_notify_lbl.setStyleSheet(
            f"font-size: {common_ui.FS_SMALL}px; font-weight: bold;"
            f" border: none; color: {common_ui.GREEN};"
        )
        self.csv_notify_lbl.setAlignment(Qt.AlignCenter)
        act.addWidget(self.csv_notify_lbl)

        self.csv_apply_btn = PrimaryButton(" Apply Corrections")
        self.csv_apply_btn.clicked.connect(self.apply_csv_corrections)
        act.addWidget(self.csv_apply_btn)

        self.apply_container.hide()
        layout.addWidget(self.apply_container)

    def _build_format_ui(self, layout):
        row = QHBoxLayout()
        row.setSpacing(20)
        row.addLayout(
            self._format_column(
                "fasta",
                [".fas", ".fasta", ".fa"],
                "Supported formats: FASTA",
                " Run FASTA Formatting",
                self.handle_fasta_files,
                self.toggle_fasta_formatting,
                self.set_fasta_run_state,
            ),
            stretch=1,
        )
        row.addLayout(
            self._format_column(
                "nwk",
                [".nwk", ".tree", ".tre", ".newick"],
                "Supported formats: NWK",
                " Run NWK Formatting",
                self.handle_nwk_files,
                self.toggle_nwk_formatting,
                self.set_nwk_run_state,
            ),
            stretch=1,
        )
        layout.addLayout(row)

    def _format_column(
        self, kind, exts, format_text, run_text, on_files, on_click, set_state
    ):
        col = QVBoxLayout()

        drop = UnifiedDropZone(exts, format_text, file_type=kind, open_in_base_dir=True)
        drop.files_updated.connect(on_files)
        self._cap_drop_height(drop, DROP_MAX_H_SEQ)
        col.addWidget(drop)
        col.addStretch(1)

        bar = self._progress_bar()
        col.addWidget(bar)

        btn = PrimaryButton(run_text, "mdi.play")
        btn.clicked.connect(on_click)
        col.addWidget(btn)

        setattr(self, f"{kind}_drop", drop)
        setattr(self, f"{kind}_pbar", bar)
        setattr(self, f"{kind}_run_btn", btn)
        setattr(self, f"is_{kind}_running", False)
        set_state("run")
        return col

    def handle_csv_files(self, files):
        self.csv_files = files
        if not files:
            self._clear_results()
            self.results_container.hide()
            self.apply_container.hide()
            self.csv_pbar.hide()
            if self.is_csv_running:
                self.abort_csv_validation()
            return

        self.log_msg.emit(f"[INFO] Loaded {len(files)} CSV file(s) for validation.")
        for fname in files:
            widget = self.csv_drop_zone.item_widgets.get(fname)
            if widget and widget.combo.count() == 0:
                widget.set_headers(t1_st1_logic.load_csv_headers(fname))

    def _clear_results(self):
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.result_blocks = []

    def _emit_file_progress(self, files, val, label):
        for f in files:
            self.file_progress_update.emit(Path(f).name, val, label)

    @staticmethod
    def _apply_run_state(btn, state, run_text):
        if state == "run":
            btn.set_state("run", run_text, "mdi.play")
        else:
            btn.set_state("stop", "Stop / Abort", "mdi.stop")
        return state != "run"

    def set_csv_run_state(self, state):
        self.is_csv_running = self._apply_run_state(
            self.csv_run_btn, state, " Run Validation"
        )

    def toggle_csv_validation(self):
        if self.is_csv_running:
            self.abort_csv_validation()
        else:
            self.start_csv_validation()

    def start_csv_validation(self):
        if not self.csv_files:
            return

        file_col_pairs = []
        for f in self.csv_files:
            widget = self.csv_drop_zone.item_widgets.get(f)
            col = widget.combo.currentText() if widget else ""
            if not col:
                self.log_msg.emit(f"[ERROR] Please select a column for {Path(f).name}")
                return
            file_col_pairs.append((f, col))

        self.set_csv_run_state("stop")
        self._clear_results()

        self.csv_pbar.show()
        self.csv_pbar.setRange(0, 0)
        self.results_container.hide()
        self.apply_container.hide()
        self._emit_file_progress(self.csv_files, 0, "Validating CSV...")

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
        val = int((curr / tot) * 100) if tot else 0
        self.csv_pbar.setValue(val)
        self.progress_update.emit(val)
        self._emit_file_progress(self.csv_files, val, "Validating CSV...")

    def on_csv_finished(self, file_results):
        self.set_csv_run_state("run")
        self.csv_pbar.setRange(0, 100)
        self.csv_pbar.setValue(100)
        self._emit_file_progress(self.csv_files, 100, "Validation Complete")

        total_corrections = 0
        for path, results in file_results.items():
            block = ResultFileBlock(path, results)
            self.results_layout.addWidget(block)
            self.result_blocks.append(block)
            total_corrections += len(block.corrections)

        self.results_container.show()
        self.apply_container.show()

        if total_corrections:
            self.log_msg.emit("[SUCCESS] Validation complete. Ready for review.")
        else:
            self.log_msg.emit(
                "[SUCCESS] Nothing needs review. Auto-generating reports..."
            )
            self.apply_csv_corrections()

    def apply_csv_corrections(self):
        if not self.result_blocks:
            return

        total_applied = 0
        try:
            for block in self.result_blocks:
                widget = self.csv_drop_zone.item_widgets.get(block.file_path)
                col = widget.combo.currentText() if widget else ""
                if not col:
                    continue

                res = t1_st1_logic.apply_and_save_corrections(
                    block.file_path,
                    col,
                    block.get_selected_corrections(),
                    block.results,
                )
                if res and res[0]:
                    total_applied += res[2]
                    self.applied.emit(Path(res[0]).name, res[2])
            self.csv_notify_lbl.setText(
                f"Saved for all files! ({total_applied} applied)"
            )
            self.log_msg.emit(
                "[SUCCESS] Process completed and saved to Results folder."
            )
        except Exception as e:
            self.log_msg.emit(f"[ERROR] Error saving files: {e}")

    # FASTA and NWK share one implementation; kind is "fasta" or "nwk"

    def _fmt(self, kind, name):
        return getattr(self, f"{kind}_{name}")

    def handle_format_files(self, kind, files):
        setattr(self, f"{kind}_files", files)
        if not files:
            self._fmt(kind, "pbar").hide()
            return
        self.log_msg.emit(
            f"[INFO] Loaded {len(files)} {kind.upper()} file(s) for formatting."
        )

    def set_format_run_state(self, kind, state):
        setattr(
            self,
            f"is_{kind}_running",
            self._apply_run_state(
                self._fmt(kind, "run_btn"), state, f" Run {kind.upper()} Formatting"
            ),
        )

    def toggle_format(self, kind):
        if getattr(self, f"is_{kind}_running"):
            self.abort_format(kind)
        else:
            self.run_format(kind)

    def abort_format(self, kind):
        thread = getattr(self, f"{kind}_thread", None)
        if thread and thread.isRunning():
            thread.cancel()
            thread.wait()
        self.set_format_run_state(kind, "run")
        self._fmt(kind, "pbar").hide()

        files = getattr(self, f"{kind}_files")
        if files:
            self._fmt(kind, "drop").update_file_progress(files[-1], 0)
        self.log_msg.emit(f"[WARNING] {kind.upper()} formatting aborted by user.")

    def run_format(self, kind):
        files = getattr(self, f"{kind}_files")
        if not files:
            return

        self.set_format_run_state(kind, "stop")
        bar = self._fmt(kind, "pbar")
        bar.show()
        bar.setRange(0, 0)
        self._emit_file_progress(files, 0, f"Formatting {kind.upper()}...")

        self.log_msg.emit(
            f"[PROCESS] Started {kind.upper()} formatting pipeline for "
            f"{len(files)} file(s)."
        )

        drop = self._fmt(kind, "drop")
        cls = FastaFormatThread if kind == "fasta" else NwkFormatThread
        thread = cls(files, drop.get_all_identities())
        thread.progress.connect(
            lambda c, t, k=kind: self.update_format_progress(k, c, t)
        )
        thread.finished.connect(
            lambda res, rep, ver, k=kind: self.on_format_finished(k, res, rep)
        )
        setattr(self, f"{kind}_thread", thread)
        thread.start()

    def update_format_progress(self, kind, curr, tot):
        bar = self._fmt(kind, "pbar")
        if bar.maximum() == 0:
            bar.setRange(0, 100)
        val = int((curr / tot) * 100) if tot else 0
        bar.setValue(val)
        self._emit_file_progress(
            getattr(self, f"{kind}_files"), val, f"Formatting {kind.upper()}..."
        )

    def on_format_finished(self, kind, results, rep_path):
        self.set_format_run_state(kind, "run")
        bar = self._fmt(kind, "pbar")
        bar.setRange(0, 100)
        bar.setValue(100)
        # The thin bar on each dropped file is started in toggle_format and
        # has nothing else to switch it off.
        self._fmt(kind, "drop").finish_file_progress()

        files = getattr(self, f"{kind}_files")
        self._emit_file_progress(files, 100, "Formatting Complete")

        ok = sum(1 for r in results if r.get("success"))
        self.log_msg.emit(
            f"[SUCCESS] {kind.upper()} formatting completed: {ok}/{len(results)} "
            f"files. Report: {Path(rep_path).name}"
        )

    def handle_fasta_files(self, files):
        self.handle_format_files("fasta", files)

    def handle_nwk_files(self, files):
        self.handle_format_files("nwk", files)

    def set_fasta_run_state(self, state):
        self.set_format_run_state("fasta", state)

    def set_nwk_run_state(self, state):
        self.set_format_run_state("nwk", state)

    def toggle_fasta_formatting(self):
        self.toggle_format("fasta")

    def toggle_nwk_formatting(self):
        self.toggle_format("nwk")
