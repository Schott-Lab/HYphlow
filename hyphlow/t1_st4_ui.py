from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QSizePolicy,
    QScrollArea,
)

from hyphlow import t1_st1_logic, t1_st4_logic
from hyphlow.common_ui import (
    FLAT,
    INK,
    INK_MUTED,
    LINE,
    RADIUS_CARD,
    SURFACE,
    PrimaryButton,
    UnifiedDropZone,
)

# ============================================================ constants
MAX_TAXA_SHOWN = 6


class _PruningThread(QThread):
    finished = pyqtSignal(list, str)
    progress = pyqtSignal(int, int)

    def __init__(self, fasta_files, nwk_files, identity_dict=None):
        super().__init__()
        self.fasta_files = fasta_files
        self.nwk_files = nwk_files
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
            results, rep_path = t1_st4_logic.run_pruning_pipeline(
                self.fasta_files,
                self.nwk_files,
                self.identity_dict,
                self._progress_callback,
            )
        except t1_st1_logic.ValidationCancelled:
            return
        if not self.is_cancelled:
            self.finished.emit(results, str(rep_path))


class Subtab4PruningUI(QWidget):
    log_msg = pyqtSignal(str)
    file_progress_update = pyqtSignal(str, int, str)

    def __init__(self):
        super().__init__()
        self.fasta_files = []
        self.nwk_files = []
        self.prune_thread = None
        self.is_running = False
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
        main_layout.setContentsMargins(40, 30, 40, 40)
        main_layout.setSpacing(20)

        main_card = QFrame()
        main_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        main_card.setStyleSheet(
            f"QFrame {{ background-color: {SURFACE}; border: 1px solid {LINE};"
            f" border-radius: {RADIUS_CARD}px; }}"
        )
        card_layout = QVBoxLayout(main_card)
        card_layout.setContentsMargins(25, 25, 25, 25)
        card_layout.setSpacing(15)

        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(4)

        title_lbl = QLabel("Tree Pruning Engine")
        title_lbl.setObjectName("SubHeader")
        title_lbl.setStyleSheet(f"{FLAT} color: {INK};")
        header_vbox.addWidget(title_lbl)

        desc_lbl = QLabel(
            "Automatically prunes a master NWK tree to strictly match the taxa present in target FASTA alignments."
        )
        desc_lbl.setObjectName("SubText")
        desc_lbl.setStyleSheet(f"{FLAT} color: {INK_MUTED};")
        desc_lbl.setWordWrap(True)
        header_vbox.addWidget(desc_lbl)

        card_layout.addLayout(header_vbox)

        drop_layout = QHBoxLayout()
        drop_layout.setSpacing(20)

        nwk_vbox = QVBoxLayout()
        self.dz_nwk = UnifiedDropZone(
            [".nwk", ".tre", ".tree"],
            "Master Tree (NWK)",
            show_dropdown=False,
            file_type="nwk",
            show_gene_input=False,
        )
        self.dz_nwk.files_updated.connect(self.handle_nwk)
        nwk_vbox.addWidget(self.dz_nwk)
        nwk_vbox.addStretch(1)
        drop_layout.addLayout(nwk_vbox, stretch=1)

        fasta_vbox = QVBoxLayout()
        self.dz_fasta = UnifiedDropZone(
            [".fas", ".fasta", ".fa"],
            "Target Alignments (FASTA)",
            show_dropdown=False,
            file_type="fasta",
            show_gene_input=True,
            strict_gene_parse=False,
        )
        self.dz_fasta.files_updated.connect(self.handle_fasta)
        fasta_vbox.addWidget(self.dz_fasta)
        fasta_vbox.addStretch(1)
        drop_layout.addLayout(fasta_vbox, stretch=1)

        card_layout.addLayout(drop_layout)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(f"color: {LINE}; margin-top: 10px; margin-bottom: 5px;")
        card_layout.addWidget(separator)

        btn_layout = QHBoxLayout()
        self.btn_run = PrimaryButton(" Run Tree Pruning", "mdi.play")
        self.btn_run.clicked.connect(self.toggle_pruning)
        btn_layout.addWidget(self.btn_run, stretch=1)

        card_layout.addLayout(btn_layout)

        main_layout.addWidget(main_card, 0, Qt.AlignTop)
        main_layout.addStretch(1)

        self.global_scroll.setWidget(scroll_content)
        master_layout.addWidget(self.global_scroll)

    def handle_fasta(self, files):
        self.fasta_files = files
        if files:
            self.log_msg.emit(f"[INFO] Loaded {len(files)} FASTA file(s).")

    def handle_nwk(self, files):
        if len(files) > 1:
            self.log_msg.emit("[ERROR] Please upload only ONE Master Tree.")
            self.dz_nwk.clear_all()
            return
        self.nwk_files = files
        if files:
            self.log_msg.emit(f"[INFO] Loaded Master Tree: {Path(files[0]).name}")

    def _emit_file_progress(self, val, label):
        for f in self.fasta_files:
            self.file_progress_update.emit(Path(f).name, val, label)

    def set_run_state(self, state):
        if state == "run":
            self.btn_run.set_state("run", " Run Tree Pruning", "mdi.play")
        else:
            self.btn_run.set_state("stop", " Stop / Abort", "mdi.stop")
        self.is_running = state != "run"

    def toggle_pruning(self):
        if self.is_running:
            self.abort_pruning()
        else:
            self.run_pruning()

    def abort_pruning(self):
        if self.prune_thread and self.prune_thread.isRunning():
            self.prune_thread.cancel()
            self.prune_thread.wait()
        self.set_run_state("run")
        self._emit_file_progress(0, "Cancelled")
        self.log_msg.emit("[WARNING] Tree pruning aborted by user.")

    def run_pruning(self):
        if not self.fasta_files or not self.nwk_files:
            self.log_msg.emit(
                "[WARNING] Please load both Target FASTA files and a Master NWK tree."
            )
            return

        self.set_run_state("stop")
        self._emit_file_progress(0, "Pruning Tree...")
        self.log_msg.emit(
            f"[PROCESS] Starting tree pruning for {len(self.fasta_files)} FASTA file(s)."
        )

        self.prune_thread = _PruningThread(
            self.fasta_files, self.nwk_files, self.dz_fasta.get_all_identities()
        )
        self.prune_thread.progress.connect(self.update_pruning_progress)
        self.prune_thread.finished.connect(self.on_pruning_finished)
        self.prune_thread.start()

    def update_pruning_progress(self, curr, tot):
        val = int((curr / tot) * 100) if tot else 0
        self._emit_file_progress(val, "Pruning Tree...")

    def on_pruning_finished(self, results, last_rep):
        self.set_run_state("run")
        self._emit_file_progress(100, "Pruning Complete")

        success_count = sum(1 for r in results if r.get("success", False))
        mismatch_found = any(r.get("has_mismatch", False) for r in results)

        for r in results:
            missing = [
                row[0]
                for row in r.get("details_data", [])
                if row[2] == t1_st4_logic.MISSING_IN_TREE
            ]
            if not missing:
                continue
            shown = ", ".join(missing[:MAX_TAXA_SHOWN])
            if len(missing) > MAX_TAXA_SHOWN:
                shown += f", +{len(missing) - MAX_TAXA_SHOWN} more"
            self.log_msg.emit(
                f"[WARNING] {r.get('fasta_name', r.get('file', '?'))}: "
                f"{len(missing)} taxon(s) in the alignment are missing from the "
                f"master tree and were dropped: {shown}"
            )
        if mismatch_found:
            self.log_msg.emit(
                "[WARNING] Some taxa in the Target FASTA could not be found in the "
                "Master NWK tree. The tree was pruned to the matching taxa only; "
                "please review the report."
            )
            self.log_msg.emit(
                f"[PROCESS] Pruning finished with missing taxa. "
                f"{success_count}/{len(results)} trees generated."
            )
            if last_rep and Path(last_rep).exists():
                self.log_msg.emit(f"[INFO] Report saved to: {last_rep}")

        else:
            self.log_msg.emit(
                f"[SUCCESS] Pruning complete: {success_count}/{len(results)} "
                f"successful. Perfect taxon match across all files."
            )
