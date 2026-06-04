import os
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QSizePolicy,
    QScrollArea,
)
from PyQt5.QtCore import Qt, pyqtSignal

import t1_st4_logic
from common_ui import (
    UnifiedDropZone,
    PrimaryButton,
)


class Subtab4PruningUI(QWidget):
    log_msg = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    file_progress_update = pyqtSignal(str, int, str)

    def __init__(self):
        super().__init__()
        self.fasta_files = []
        self.nwk_files = []
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
        main_layout.setContentsMargins(40, 30, 40, 40)
        main_layout.setSpacing(20)

        main_card = QFrame()
        main_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        main_card.setStyleSheet(
            "QFrame { background-color: #ffffff; border: 1px solid #e5e5ea; border-radius: 16px; }"
        )
        card_layout = QVBoxLayout(main_card)
        card_layout.setContentsMargins(25, 25, 25, 25)
        card_layout.setSpacing(15)

        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(4)

        title_lbl = QLabel("Tree Pruning Engine")
        title_lbl.setObjectName("SubHeader")
        title_lbl.setStyleSheet(
            "border: none; background: transparent; color: #1D1D1F;"
        )
        header_vbox.addWidget(title_lbl)

        desc_lbl = QLabel(
            "Automatically prunes a master NWK tree to strictly match the taxa present in target FASTA alignments."
        )
        desc_lbl.setObjectName("SubText")
        desc_lbl.setStyleSheet("border: none; background: transparent; color: #515154;")
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
        separator.setStyleSheet("color: #E5E5EA; margin-top: 10px; margin-bottom: 5px;")
        card_layout.addWidget(separator)

        btn_layout = QHBoxLayout()
        self.btn_run = PrimaryButton(" Run Tree Pruning", "mdi.play")
        self.btn_run.setFixedHeight(44)
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setStyleSheet("""
            QPushButton { background-color: #1D1D1F; color: white; font-size: 14px; font-weight: bold; border-radius: 8px; border: none; padding: 0 24px; }
            QPushButton:hover { background-color: #333333; }
            QPushButton:disabled { background-color: #E5E5EA; color: #8E8E93; }
        """)
        self.btn_run.clicked.connect(self.run_pruning)
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

    def run_pruning(self):
        if not self.fasta_files or not self.nwk_files:
            self.log_msg.emit(
                "[WARNING] Please load both Target FASTA files and a Master NWK tree."
            )
            return

        self.log_msg.emit(
            f"[PROCESS] Starting tree pruning for {len(self.fasta_files)} FASTA file(s)."
        )

        for f in self.fasta_files:
            self.file_progress_update.emit(os.path.basename(f), 50, "Pruning Tree...")

        gene_dict = self.dz_fasta.get_all_genes()
        results, last_rep = t1_st4_logic.run_pruning_pipeline(
            self.fasta_files, self.nwk_files, gene_dict
        )

        success_count = sum(1 for r in results if r.get("success", False))
        mismatch_found = any(r.get("has_mismatch", False) for r in results)

        for f in self.fasta_files:
            self.file_progress_update.emit(os.path.basename(f), 100, "Pruning Complete")

        if mismatch_found:
            self.log_msg.emit("[WARNING] Taxon mismatch detected during tree pruning.")
            self.log_msg.emit(
                "[WARNING] Some taxa in the Target FASTA could not be found in the Master NWK tree."
            )
            self.log_msg.emit(
                "[INFO] The engine pruned the tree as much as possible based on matching taxa. Please review the output report carefully."
            )
            self.log_msg.emit(
                f"[PROCESS] Pruning finished with missing taxa. {success_count}/{len(results)} trees generated."
            )

            if last_rep and os.path.exists(last_rep):
                rep_dir = os.path.dirname(last_rep)
                self.log_msg.emit(
                    f"[INFO] Automatically opening report directory: {rep_dir}"
                )
                try:
                    os.startfile(rep_dir)
                except Exception as e:
                    self.log_msg.emit(f"[ERROR] Could not open directory: {e}")
        else:
            self.log_msg.emit(
                f"[SUCCESS] Pruning complete: {success_count}/{len(results)} successful. Perfect taxon match across all files."
            )
