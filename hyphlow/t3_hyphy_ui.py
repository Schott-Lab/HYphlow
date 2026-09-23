import datetime
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

import qtawesome as qta
from PyQt5.QtCore import (
    Qt,
    QPoint,
    pyqtSignal,
    QPropertyAnimation,
    QProcess,
    QTimer,
)
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFrame,
    QLabel,
    QTextEdit,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QSizePolicy,
    QCheckBox,
)

from hyphlow import common_utils, t1_st1_logic, t3_hyphy_logic
from hyphlow.common_ui import (
    UnifiedDropZone,
    PrimaryButton,
    mono_font,
    pick_save,
)

# QProcess.kill() ends the shell with SIGKILL, so this code means the user
# pressed Abort, not that the analysis failed.
ABORT_EXIT_CODE = 9


class Tab3HyPhyUI(QWidget):
    log_msg = pyqtSignal(str)
    request_reconciliation = pyqtSignal()
    progress_update = pyqtSignal(str, int, str)
    wsl_msg = pyqtSignal(str)
    wsl_clear = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.fasta_files = []
        self.nwk_files = []
        self.models = list(common_utils.HYPHY_MODELS)
        self.is_generating_script = False
        self.was_valid = True
        self.local_process = None
        self.current_work_dir = None
        self.job_queue = []
        self.reaction_timer = QTimer(self)
        self.reaction_timer.timeout.connect(self.update_reaction_time)
        self.active_tasks = {}
        self.task_map = {}
        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0
        self.spinner_timer = QTimer(self)
        self.spinner_timer.timeout.connect(self.update_spinner)
        # Syntax is checked after typing pauses, not on every keystroke: the
        # check walks the whole script, which is hundreds of lines for a full
        # queue.
        self.syntax_timer = QTimer(self)
        self.syntax_timer.setSingleShot(True)
        self.syntax_timer.timeout.connect(self.check_syntax)
        self.total_jobs = 0
        self.completed_jobs = 0
        self.terminal_history = []
        self._setup_ui()
        self.update_script_preview()

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
        header_lbl = QLabel("HyPhy Execution")
        header_lbl.setObjectName("SectionHeader")
        header_lbl.setStyleSheet("border: none; background: transparent;")
        header_vbox.addWidget(header_lbl)
        desc_lbl = QLabel(
            "Runs batch HyPhy analyses with selected models, adjustable CPU cores, editable Bash scripts, and WSL support for Windows."
        )
        desc_lbl.setObjectName("SubText")
        desc_lbl.setStyleSheet("border: none; background: transparent;")
        header_vbox.addWidget(desc_lbl)
        main_layout.addLayout(header_vbox)
        self.input_card = QFrame()
        self.input_card.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 10px; }"
        )
        ic_layout = QVBoxLayout(self.input_card)
        ic_layout.setContentsMargins(15, 10, 15, 15)
        ic_layout.setSpacing(10)
        input_header = QHBoxLayout()
        lbl_input_title = QLabel("Data Input")
        lbl_input_title.setObjectName("SubHeader")
        lbl_input_title.setStyleSheet("border: none; background: transparent;")
        input_header.addWidget(lbl_input_title)
        input_header.addStretch()
        self.btn_toggle_input = QPushButton()
        self.btn_toggle_input.setIcon(qta.icon("mdi.chevron-up", color="#1D1D1F"))
        self.btn_toggle_input.setStyleSheet("border: none; background: transparent;")
        self.btn_toggle_input.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_input.clicked.connect(self.toggle_input_overview)
        input_header.addWidget(self.btn_toggle_input)
        ic_layout.addLayout(input_header)
        self.input_content_area = QFrame()
        self.input_content_area.setStyleSheet("background: transparent; border: none;")
        input_content_layout = QVBoxLayout(self.input_content_area)
        input_content_layout.setContentsMargins(0, 0, 0, 0)
        input_content_layout.setSpacing(15)
        dz_layout = QHBoxLayout()
        dz_layout.setSpacing(15)
        self.fasta_container = QWidget()
        self.fasta_container.setStyleSheet("background: transparent; border: none;")
        fc_layout = QVBoxLayout(self.fasta_container)
        fc_layout.setContentsMargins(0, 0, 0, 0)
        self.dz_fasta = UnifiedDropZone(
            [".fasta", ".fas", ".fa"],
            "Master Alignment (FASTA)",
            show_dropdown=False,
            file_type="fasta",
            show_gene_input=True,
        )
        self.dz_fasta.files_updated.connect(self.handle_fasta_files)
        fc_layout.addWidget(self.dz_fasta)
        dz_layout.addWidget(self.fasta_container, 1)
        self.nwk_container = QWidget()
        self.nwk_container.setStyleSheet("background: transparent; border: none;")
        nc_layout = QVBoxLayout(self.nwk_container)
        nc_layout.setContentsMargins(0, 0, 0, 0)
        self.dz_nwk = UnifiedDropZone(
            [".nwk", ".tre", ".tree"],
            "Target Phylogeny (NWK)",
            show_dropdown=False,
            file_type="nwk",
            show_gene_input=True,
            default_subdir=("Results", "Tree_Annotation"),
        )
        self.dz_nwk.files_updated.connect(self.handle_nwk_files)
        nc_layout.addWidget(self.dz_nwk)
        dz_layout.addWidget(self.nwk_container, 1)

        input_content_layout.addLayout(dz_layout)
        self.btn_auto_match = PrimaryButton(" Run Auto Match", "mdi.play")
        self.btn_auto_match.clicked.connect(self.process_matching)
        input_content_layout.addWidget(self.btn_auto_match)
        ic_layout.addWidget(self.input_content_area)
        main_layout.addWidget(self.input_card)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet("""
            QSplitter::handle { background-color: #E5E5EA; width: 6px; border-radius: 3px; margin: 2px; }
            QSplitter::handle:hover { background-color: #C7C7CC; }
            QSplitter::handle:pressed { background-color: #8E8E93; }
        """)
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 15, 0)
        left_layout.setSpacing(15)
        left_layout.setAlignment(Qt.AlignTop)
        match_box = QFrame()
        match_box.setObjectName("ConfigCard")
        match_box.setStyleSheet(
            "QFrame#ConfigCard { background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 10px; }"
        )
        ml_layout = QVBoxLayout(match_box)
        ml_layout.setContentsMargins(15, 15, 15, 15)
        ml_layout.setSpacing(10)
        match_header = QHBoxLayout()
        match_title = QLabel("FASTA-Tree Matching")
        match_title.setObjectName("SubHeader")
        match_title.setStyleSheet("border: none; background: transparent;")
        match_header.addWidget(match_title)
        match_header.addStretch()
        self.btn_toggle_match = QPushButton()
        self.btn_toggle_match.setIcon(qta.icon("mdi.chevron-down", color="#1D1D1F"))
        self.btn_toggle_match.setStyleSheet("border: none; background: transparent;")
        self.btn_toggle_match.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_match.clicked.connect(self.toggle_match_overview)
        match_header.addWidget(self.btn_toggle_match)
        ml_layout.addLayout(match_header)
        self.match_tree = QTreeWidget()
        self.match_tree.setHeaderLabels(["Files", "FG", "Status", "Action"])
        self.match_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.match_tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.match_tree.header().setSectionResizeMode(2, QHeaderView.Fixed)
        self.match_tree.header().setSectionResizeMode(3, QHeaderView.Fixed)
        self.match_tree.setColumnWidth(1, 50)
        self.match_tree.setColumnWidth(2, 70)
        self.match_tree.setColumnWidth(3, 100)
        self.match_tree.setIndentation(15)
        self.match_tree.setMinimumHeight(150)
        self.match_tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.match_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.match_tree.setFocusPolicy(Qt.NoFocus)
        self.match_tree.setStyleSheet("""
            QTreeWidget { background-color: #FAFAFA; border: 1px solid #E5E5EA; border-radius: 6px; font-size: 12px; color: #1D1D1F; outline: none; }
            QHeaderView::section { background-color: #FFFFFF; font-weight: bold; font-size: 11px; color: #8E8E93; border: none; border-bottom: 1px solid #E5E5EA; padding: 4px 8px; }
            QTreeView::item { min-height: 30px; border-bottom: 1px solid #F8F8F8; }
        """)
        self.match_tree.itemChanged.connect(self.update_target_combo)
        self.match_tree.hide()
        ml_layout.addWidget(self.match_tree)
        left_layout.addWidget(match_box)
        config_box = QFrame()
        config_box.setObjectName("ConfigCard")
        config_box.setStyleSheet(
            "QFrame#ConfigCard { background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 10px; }"
        )
        cl_layout = QVBoxLayout(config_box)
        cl_layout.setContentsMargins(15, 15, 15, 15)
        cl_layout.setSpacing(12)
        config_title = QLabel("Select HyPhy Model")
        config_title.setObjectName("SubHeader")
        config_title.setStyleSheet("border: none; background: transparent;")
        cl_layout.addWidget(config_title)

        self.chk_triplicate = QCheckBox("Enable Triplicate Runs (Avoid Local Optima)")
        self.chk_triplicate.setStyleSheet(
            "QCheckBox { background: transparent; padding: 0px; border: none; "
            "color: #1D1D1F; font-weight: 600; font-size: 12px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; "
            "border: 1px solid #C7C7CC; border-radius: 4px; background: white; }"
            "QCheckBox::indicator:checked { background: #1D1D1F; "
            "border: 1px solid #1D1D1F; }"
        )
        self.chk_triplicate.stateChanged.connect(self.update_script_preview)
        cl_layout.addWidget(self.chk_triplicate)

        # A table rather than pills: with 20+ jobs the pills all read the same,
        # because what distinguishes them (gene, tag) sits in the middle of a
        # filename that gets elided away.
        self.queue_table = QTableWidget(0, 6)
        self.queue_table.setHorizontalHeaderLabels(
            ["Gene", "Alignment", "Tree", "Tag", "Model", ""]
        )
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.queue_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.queue_table.setAlternatingRowColors(True)
        self.queue_table.setMinimumHeight(260)
        self.queue_table.verticalHeader().setDefaultSectionSize(30)
        self.queue_table.setStyleSheet(
            "QTableWidget { background: white; border: 1px solid #E5E5EA;"
            " border-radius: 8px; gridline-color: #F0F0F0; font-size: 12px; }"
            "QHeaderView::section { background: #FAFAFA; color: #6E6E73;"
            " border: none; border-bottom: 1px solid #E5E5EA; padding: 6px;"
            " font-weight: bold; }"
        )
        hh = self.queue_table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for col in (0, 3, 4, 5):
            hh.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        cl_layout.addWidget(self.queue_table)
        self.builder_frame = QFrame()
        self.builder_frame.setStyleSheet(
            "QFrame { background-color: #FAFAFA; border: 1px solid #E5E5EA; border-radius: 8px; }"
        )
        builder_layout = QVBoxLayout(self.builder_frame)
        builder_layout.setContentsMargins(15, 15, 15, 15)
        builder_layout.setSpacing(10)
        model_row = QHBoxLayout()
        model_row.addWidget(
            QLabel(
                "1. Model:",
                styleSheet="font-size: 12px; color: #515154; font-weight: 600; border: none; background: transparent;",
            )
        )
        self.combo_method = QComboBox()
        self.combo_method.addItems(common_utils.HYPHY_MODELS)
        self.combo_method.setStyleSheet("""
            QComboBox { border: 1px solid #D1D1D6; border-radius: 6px; padding: 4px 10px; background: #FFFFFF; font-weight: 500; font-size: 12px; color: #1D1D1F; min-width: 150px; }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #8E8E93; margin-top: 1px; }
        """)
        model_row.addWidget(self.combo_method)
        model_row.addStretch()
        builder_layout.addLayout(model_row)
        target_row = QHBoxLayout()
        target_row.addWidget(
            QLabel(
                "2. Target:",
                styleSheet="font-size: 12px; color: #515154; font-weight: 600; border: none; background: transparent;",
            )
        )
        self.combo_target = QComboBox()
        self.combo_target.setStyleSheet("""
            QComboBox { border: 1px solid #D1D1D6; border-radius: 6px; padding: 4px 10px; background: #FFFFFF; font-weight: 500; font-size: 12px; color: #1D1D1F; min-width: 150px; }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #8E8E93; margin-top: 1px; }
        """)
        self.combo_target.addItem("Apply to ALL Checked Matches", userData="ALL")
        target_row.addWidget(self.combo_target, stretch=1)
        builder_layout.addLayout(target_row)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_cancel_add = QPushButton("Cancel")
        self.btn_cancel_add.setCursor(Qt.PointingHandCursor)
        self.btn_cancel_add.setStyleSheet("""
            QPushButton { color: #8E8E93; font-size: 12px; font-weight: bold; border-radius: 6px; padding: 6px 12px; border: none; background: transparent; }
            QPushButton:hover { color: #1D1D1F; background-color: #E5E5EA; }
        """)
        self.btn_cancel_add.clicked.connect(self.hide_builder)
        btn_row.addWidget(self.btn_cancel_add)
        self.btn_confirm_add = QPushButton("Confirm")
        self.btn_confirm_add.setCursor(Qt.PointingHandCursor)
        self.btn_confirm_add.setStyleSheet("""
            QPushButton { background-color: #0071E3; color: white; font-size: 12px; font-weight: bold; border-radius: 6px; padding: 6px 16px; border: none; }
            QPushButton:hover { background-color: #005BB5; }
        """)
        self.btn_confirm_add.clicked.connect(self.add_job_to_queue)
        btn_row.addWidget(self.btn_confirm_add)
        builder_layout.addLayout(btn_row)
        cl_layout.addWidget(self.builder_frame)
        self.builder_frame.hide()
        self.btn_show_builder = QPushButton("Add New Job")
        self.btn_show_builder.setCursor(Qt.PointingHandCursor)
        self.btn_show_builder.setStyleSheet("""
            QPushButton { background-color: #F2F2F7; color: #1D1D1F; font-size: 12px; font-weight: bold; border-radius: 6px; padding: 8px 16px; border: 1px solid #E5E5EA; }
            QPushButton:hover { background-color: #E5E5EA; }
        """)
        self.btn_show_builder.clicked.connect(self.show_builder)
        cl_layout.addWidget(self.btn_show_builder)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #E5E5EA; margin-top: 10px; margin-bottom: 10px;")
        cl_layout.addWidget(line)
        cpu_layout = QVBoxLayout()
        cpu_layout.setSpacing(4)
        top_cpu = QHBoxLayout()
        top_cpu.addWidget(
            QLabel(
                "CPU Threads:",
                styleSheet="font-size: 13px; color: #1D1D1F; font-weight: bold; border: none; background: transparent;",
            )
        )
        max_cores = os.cpu_count() or 4
        rec_cores = max(1, max_cores - 1)
        self.combo_cpu = QComboBox()
        self.combo_cpu.setStyleSheet("""
            QComboBox { border: 1px solid #D1D1D6; border-radius: 6px; padding: 4px 10px; background: white; color: #1D1D1F; font-size: 13px; font-weight: bold; }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #8E8E93; margin-top: 1px; }
        """)
        self.combo_cpu.addItems([str(i) for i in range(1, max_cores + 1)])
        self.combo_cpu.setCurrentText(str(rec_cores))
        self.combo_cpu.currentTextChanged.connect(self.update_script_preview)
        top_cpu.addWidget(self.combo_cpu)
        top_cpu.addStretch()
        cpu_layout.addLayout(top_cpu)

        min_cpu_row = QHBoxLayout()
        min_cpu_row.addWidget(
            QLabel(
                "Min CPU per task:",
                styleSheet="font-size: 13px; color: #1D1D1F; font-weight: bold; border: none; background: transparent;",
            )
        )
        self.combo_min_cpu = QComboBox()
        self.combo_min_cpu.setStyleSheet(self.combo_cpu.styleSheet())
        self.combo_min_cpu.addItems([str(i) for i in range(1, 5)])
        self.combo_min_cpu.setCurrentText("2")
        self.combo_min_cpu.currentTextChanged.connect(self.update_script_preview)
        min_cpu_row.addWidget(self.combo_min_cpu)
        min_cpu_row.addStretch()
        cpu_layout.addLayout(min_cpu_row)

        self.cpu_desc_lbl = QLabel(f"Recommended max CPU: {rec_cores}")
        self.cpu_desc_lbl.setStyleSheet(
            "color: #8E8E93; font-size: 11px; border: none; background: transparent; padding-left: 2px;"
        )
        self.cpu_desc_lbl.setWordWrap(True)
        cpu_layout.addWidget(self.cpu_desc_lbl)
        cl_layout.addLayout(cpu_layout)
        left_layout.addWidget(config_box)
        left_layout.addStretch()
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(15)
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.setStyleSheet("""
            QSplitter::handle { background-color: #E5E5EA; height: 6px; border-radius: 3px; margin: 2px; }
            QSplitter::handle:hover { background-color: #C7C7CC; }
        """)
        editor_card = QFrame()
        editor_card.setObjectName("EditorCard")
        editor_card.setStyleSheet(
            "QFrame#EditorCard { background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 10px; }"
        )
        ed_layout = QVBoxLayout(editor_card)
        ed_layout.setContentsMargins(15, 15, 15, 15)
        ed_layout.setSpacing(8)
        ed_header = QHBoxLayout()
        editor_title = QLabel("Editable Bash Script")
        editor_title.setObjectName("SubHeader")
        editor_title.setStyleSheet("border: none; background: transparent;")
        ed_header.addWidget(editor_title)
        ed_header.addStretch()
        self.btn_run_hyphy = PrimaryButton(" Run HyPhy Execution", "mdi.play")
        self.btn_run_hyphy.setFixedHeight(30)
        self.btn_run_hyphy.setEnabled(False)
        self.btn_run_hyphy.clicked.connect(self.run_hyphy_process)
        ed_header.addWidget(self.btn_run_hyphy)
        ed_layout.addLayout(ed_header)
        self.script_editor = QTextEdit()
        self.script_editor.setMinimumHeight(350)
        self.script_editor.setFont(mono_font(10))
        self.script_editor.setStyleSheet(
            "QTextEdit { background-color: #2D2D30; color: #D4D4D4; border: 1px solid #D1D1D6; border-radius: 8px; padding: 10px; }"
        )
        self.script_editor.setAcceptRichText(False)
        self.script_editor.textChanged.connect(lambda: self.syntax_timer.start(300))
        ed_layout.addWidget(self.script_editor)
        right_splitter.addWidget(editor_card)
        progress_card = QFrame()
        progress_card.setObjectName("ProgressCard")
        progress_card.setStyleSheet(
            "QFrame#ProgressCard { background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 10px; }"
        )
        br_layout = QVBoxLayout(progress_card)
        br_layout.setContentsMargins(15, 15, 15, 15)
        br_layout.setSpacing(10)
        table_header = QHBoxLayout()
        progress_title = QLabel("HyPhy Execution Progress")
        progress_title.setObjectName("SubHeader")
        progress_title.setStyleSheet("border: none; background: transparent;")
        table_header.addWidget(progress_title)
        table_header.addStretch()
        self.btn_abort = QPushButton("Abort")
        self.btn_abort.setCursor(Qt.PointingHandCursor)
        self.btn_abort.setStyleSheet("""
            QPushButton { background-color: #FFECEB; color: #FF3B30; font-size: 11px; font-weight: bold; border-radius: 6px; padding: 5px 12px; border: none; }
            QPushButton:hover { background-color: #FFD1CE; }
            QPushButton:disabled { background-color: #E5E5EA; color: #8E8E93; }
        """)
        self.btn_abort.clicked.connect(self.abort_process)
        self.btn_abort.setEnabled(False)
        table_header.addWidget(self.btn_abort)
        export_style = """
            QPushButton { background-color: #0071E3; color: white; font-size: 11px; font-weight: bold; border-radius: 6px; padding: 5px 12px; border: none; }
            QPushButton:hover { background-color: #005BB5; }
            QPushButton:disabled { background-color: #E5E5EA; color: #8E8E93; }
        """
        self.btn_export_zip = QPushButton("Export")
        self.btn_export_zip.setStyleSheet(export_style)
        self.btn_export_zip.clicked.connect(self.export_zip)
        self.btn_export_zip.setEnabled(False)
        table_header.addWidget(self.btn_export_zip)

        self.btn_export_slurm = QPushButton("Export SLURM")
        self.btn_export_slurm.setStyleSheet(export_style)
        self.btn_export_slurm.clicked.connect(self.export_slurm)
        self.btn_export_slurm.setEnabled(False)
        table_header.addWidget(self.btn_export_slurm)
        br_layout.addLayout(table_header)
        self.progress_table = QTableWidget(0, 8)
        self.progress_table.setMinimumHeight(250)
        self.progress_table.setHorizontalHeaderLabels(
            ["FASTA", "NWK", "Model", "CPUs", "Start", "End", "Duration", "Status"]
        )
        header = self.progress_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.progress_table.setColumnWidth(0, 150)
        self.progress_table.setColumnWidth(1, 150)
        self.progress_table.verticalHeader().setVisible(False)
        self.progress_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.progress_table.setFocusPolicy(Qt.NoFocus)
        self.progress_table.setStyleSheet("""
            QTableWidget { background-color: #FFFFFF; border: 1px solid #D1D1D6; border-radius: 8px; font-size: 11px; color: #1D1D1F; gridline-color: transparent; outline: none;}
            QHeaderView::section { background-color: #FAFAFA; font-weight: bold; color: #8E8E93; border: none; padding: 6px; border-bottom: 1px solid #E5E5EA; font-size: 11px;}
        """)
        br_layout.addWidget(self.progress_table)
        right_splitter.addWidget(progress_card)
        right_splitter.setStretchFactor(0, 5)
        right_splitter.setStretchFactor(1, 5)
        right_layout.addWidget(right_splitter)
        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(right_panel)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 6)
        self.splitter.setSizes([450, 650])
        main_layout.addWidget(self.splitter)
        self.global_scroll.setWidget(scroll_content)
        master_layout.addWidget(self.global_scroll)

    def format_display_names(self, fasta_name, nwk_name):
        gene = (
            fasta_name.split("_")[0] if "_" in fasta_name else fasta_name.split(".")[0]
        )
        if "tagged_" in nwk_name or "annotated_" in nwk_name:
            split_word = "annotated_" if "annotated_" in nwk_name else "tagged_"
            parts = nwk_name.split(split_word)
            if len(parts) > 1:
                tag = parts[1].split("_")[0]
                t_display = f"{gene} ({tag})"
            else:
                t_display = f"{gene} (All)"
        else:
            t_display = f"{gene} (All)"
        return gene, t_display

    def show_builder(self):
        self.btn_show_builder.hide()
        self.builder_frame.show()

    def hide_builder(self):
        self.builder_frame.hide()
        self.btn_show_builder.show()

    def toggle_input_overview(self):
        if self.input_content_area.isVisible():
            self.input_content_area.hide()
            self.btn_toggle_input.setIcon(qta.icon("mdi.chevron-down", color="#1D1D1F"))
        else:
            self.input_content_area.show()
            self.btn_toggle_input.setIcon(qta.icon("mdi.chevron-up", color="#1D1D1F"))

    def toggle_match_overview(self):
        if self.match_tree.isVisible():
            self.match_tree.hide()
            self.btn_toggle_match.setIcon(qta.icon("mdi.chevron-down", color="#1D1D1F"))
        else:
            self.match_tree.show()
            self.btn_toggle_match.setIcon(qta.icon("mdi.chevron-up", color="#1D1D1F"))

    def create_status_badge(self, text, bg_color, text_color):
        wrapper = QWidget()
        wrapper.setAttribute(Qt.WA_TranslucentBackground)
        wrapper.setStyleSheet("background: transparent; border: none; outline: none;")
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f"background-color: {bg_color}; color: {text_color}; border-radius: 4px; font-weight: bold; font-size: 10px; padding: 2px 6px; border: none;"
        )
        layout.addWidget(lbl)
        layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return wrapper

    def handle_fasta_files(self, files):
        self.fasta_files = files

    def handle_nwk_files(self, files):
        self.nwk_files = files

    def get_selected_pairs_from_tree(self):
        selected_pairs = []
        root = self.match_tree.invisibleRootItem()
        if not root:
            return selected_pairs
        for i in range(root.childCount()):
            fasta_node = root.child(i)
            for j in range(fasta_node.childCount()):
                tree_node = fasta_node.child(j)
                if tree_node.checkState(0) == Qt.Checked:
                    selected_pairs.append(tree_node.data(0, Qt.UserRole))
        return selected_pairs

    def update_target_combo(self):
        pairs = self.get_selected_pairs_from_tree()
        self.combo_target.clear()
        self.combo_target.addItem("Apply to ALL Checked Matches", userData="ALL")
        if pairs:
            self.combo_target.addItem("--- Specific Pairs ---", userData="SEP")
            model = self.combo_target.model()
            item = model.item(1)
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            for p in pairs:
                t_name = Path(p["tree"]).name
                f_name = Path(p["fasta"]).name
                disp_f, disp_t = self.format_display_names(f_name, t_name)
                self.combo_target.addItem(f"[{disp_f}] {disp_t}", userData=p)

    def process_matching(self):
        fasta_ids = self.dz_fasta.get_all_identities()
        tree_ids = self.dz_nwk.get_all_identities()
        if not fasta_ids or not tree_ids:
            return

        self.match_tree.blockSignals(True)
        self.match_tree.clear()
        matched, unpaired = t3_hyphy_logic.get_matched_pairs(fasta_ids, tree_ids)

        for data in matched.values():
            fasta_item = QTreeWidgetItem(self.match_tree)
            fasta_item.setText(0, f" {Path(data['fasta_path']).name}")
            for tree_data in data["trees"]:
                tree_item = QTreeWidgetItem(fasta_item)
                tree_item.setFlags(tree_item.flags() | Qt.ItemIsUserCheckable)
                tree_item.setText(0, f" {Path(tree_data['nwk_path']).name}")

                if tree_data["is_valid"]:
                    tree_item.setCheckState(0, Qt.Checked)
                    badge = self.create_status_badge("Matched", "#EBF9EE", "#34C759")
                else:
                    tree_item.setCheckState(0, Qt.Unchecked)
                    badge = self.create_status_badge("Mismatch", "#FFF9E5", "#FF9500")
                # The badge says only pass or fail; which taxa differ is in the
                # tooltip so it does not crowd the row.
                badge.setToolTip(tree_data["error_msg"])
                self.match_tree.setItemWidget(tree_item, 2, badge)

                if tree_data["has_fg"]:
                    fg_badge = self.create_status_badge("FG", "#F2F2F7", "#1D1D1F")
                    self.match_tree.setItemWidget(tree_item, 1, fg_badge)
                else:
                    tree_item.setText(1, "")

                tree_item.setData(
                    0,
                    Qt.UserRole,
                    {
                        "fasta": data["fasta_path"],
                        "tree": tree_data["nwk_path"],
                        "has_fg": tree_data["has_fg"],
                    },
                )
            fasta_item.setExpanded(True)

        self.match_tree.blockSignals(False)
        self.update_target_combo()

        # A file that paired with nothing is named here rather than left out of
        # the tree, where its absence reads as "nothing was dropped".
        for path, reason in unpaired:
            self.log_msg.emit(f"[WARNING] {Path(path).name}: {reason}")
        if matched:
            self.input_content_area.hide()
            self.btn_toggle_input.setIcon(qta.icon("mdi.chevron-down", color="#1D1D1F"))
        self.match_tree.show()
        self.btn_toggle_match.setIcon(qta.icon("mdi.chevron-up", color="#1D1D1F"))

    def add_job_to_queue(self):
        sel_model = self.combo_method.currentText()
        t_data = self.combo_target.currentData()
        if not t_data or t_data == "SEP":
            return
        pairs_to_add = []
        if t_data == "ALL":
            pairs_to_add = self.get_selected_pairs_from_tree()
        else:
            pairs_to_add = [t_data]
        if not pairs_to_add:
            self.log_msg.emit(
                "[WARNING] No matched trees selected. Please check your selections in the FASTA-Tree Matching table."
            )
            return
        added_count = 0
        for p in pairs_to_add:
            job_id = f"{p['fasta']}|{p['tree']}|{sel_model}"
            is_dup = any(job.get("job_id") == job_id for job in self.job_queue)
            if not is_dup:
                new_job = {
                    "job_id": job_id,
                    "fasta": p["fasta"],
                    "tree": p["tree"],
                    "model": sel_model,
                    "has_fg": p["has_fg"],
                }
                self.job_queue.append(new_job)
                added_count += 1
        if added_count > 0:
            self.refresh_queue_table()
            self.update_script_preview()
            self.hide_builder()

    def refresh_queue_table(self):
        self.queue_table.setRowCount(0)
        for job in self.job_queue:
            row = self.queue_table.rowCount()
            self.queue_table.insertRow(row)

            gene = t3_hyphy_logic._gene_from_stem(Path(job["tree"]).stem) or "?"
            tag = common_utils.tag_from_tree_name(job["tree"]) or "—"
            values = [
                gene,
                Path(job["fasta"]).stem,
                Path(job["tree"]).stem,
                tag,
                job["model"].upper(),
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.queue_table.setItem(row, col, item)

            btn_del = QPushButton("Remove")
            btn_del.setFixedHeight(24)
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet(
                "QPushButton { border: 1px solid #FFB3AD; border-radius: 6px;"
                " background: #FFF5F4; color: #C1543A; font-size: 11px;"
                " font-weight: bold; padding: 2px 10px; }"
                "QPushButton:hover { background: #FF3B30; color: white;"
                " border: 1px solid #FF3B30; }"
            )
            btn_del.clicked.connect(
                lambda _, jid=job["job_id"]: self.remove_job_from_queue(jid)
            )
            self.queue_table.setCellWidget(row, 5, btn_del)

    def remove_job_from_queue(self, job_id):
        before = len(self.job_queue)
        self.job_queue = [j for j in self.job_queue if j["job_id"] != job_id]
        self.refresh_queue_table()
        self.update_script_preview()
        if len(self.job_queue) < before:
            self.log_msg.emit(
                "[INFO] Removed 1 job. %d remaining in queue." % len(self.job_queue)
            )

    def update_cpu_desc(self):
        """Show how the two CPU settings translate into a run plan."""
        try:
            threads = int(self.combo_cpu.currentText())
            min_cpu = int(self.combo_min_cpu.currentText())
        except (ValueError, AttributeError):
            return

        n_tasks = len(self.job_queue) * (3 if self.chk_triplicate.isChecked() else 1)
        if n_tasks == 0:
            self.cpu_desc_lbl.setText(
                "%d cores available. Add a job to see the run plan." % threads
            )
            return

        cores_each = min(max(min_cpu, threads // max(1, n_tasks)), 4)
        concurrent = max(1, threads // cores_each)
        waves = -(-n_tasks // concurrent)

        text = "%d task(s): %d at a time, %d CPU each  (%d round%s)" % (
            n_tasks,
            concurrent,
            cores_each,
            waves,
            "" if waves == 1 else "s",
        )
        # Extra cores inside one HyPhy run scale poorly (2 CPU = 65% efficient,
        # 4 CPU = 51%), while running separate jobs side by side does not, so
        # fewer rounds finishes the batch sooner.
        if waves > 1 and cores_each > 1:
            best_conc = max(1, threads)
            best_waves = -(-n_tasks // best_conc)
            if best_waves < waves:
                text += (
                    "\nFewer rounds finish sooner. 1 CPU each would be %d round%s."
                    % (best_waves, "" if best_waves == 1 else "s")
                )
        self.cpu_desc_lbl.setText(text)

    def update_script_preview(self):
        self.update_cpu_desc()
        self.is_generating_script = True
        threads = int(self.combo_cpu.currentText())
        min_cpu = int(self.combo_min_cpu.currentText())
        script_content = t3_hyphy_logic.generate_bash_script(
            self.job_queue,
            threads,
            self.chk_triplicate.isChecked(),
            min_cores=min_cpu,
        )
        self.script_editor.setText(script_content)
        self.is_generating_script = False
        self.check_syntax()

    def reset_run_button(self):
        self.spinner_timer.stop()
        self.btn_abort.setEnabled(False)
        self.check_syntax()

    def update_spinner(self):
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_frames)
        self.btn_run_hyphy.setText(
            f" {self.spinner_frames[self.spinner_idx]} Running..."
        )

    def check_syntax(self):
        if self.is_generating_script:
            return
        text = self.script_editor.toPlainText()
        text_lower = text.lower()
        errors = []
        if not self.job_queue:
            errors.append("Batch Queue is empty.")
        missing = [
            kw for kw in ["hyphy", "--alignment", "--tree"] if kw not in text_lower
        ]
        if missing and self.job_queue:
            errors.append(f"Missing flags: {', '.join(missing)}")
        if text.count('"') % 2 != 0:
            errors.append('Unbalanced double quotes (")')
        if text.count("'") % 2 != 0:
            errors.append("Unbalanced single quotes (')")
        if text.count("(") != text.count(")"):
            errors.append("Unbalanced parentheses ()")
        if text.count("{") != text.count("}"):
            errors.append("Unbalanced curly braces {}")

        if errors:
            self.btn_run_hyphy.set_state("error", " Syntax Error", "mdi.alert")
            self.btn_run_hyphy.setToolTip(f"Error: {errors[0]}")
            self.btn_export_zip.setEnabled(False)
            self.btn_export_slurm.setEnabled(False)
            self.btn_run_hyphy.setEnabled(False)
            if self.was_valid and self.job_queue:
                self.trigger_shake_animation()
                self.was_valid = False
        else:
            self.btn_run_hyphy.set_state("run", " Run HyPhy Execution", "mdi.play")
            self.btn_run_hyphy.setToolTip("")
            self.btn_export_zip.setEnabled(True)
            self.btn_export_slurm.setEnabled(True)
            self.btn_run_hyphy.setEnabled(True)
            self.was_valid = True

    def trigger_shake_animation(self):
        self.shake_anim = QPropertyAnimation(self.script_editor, b"pos")
        self.shake_anim.setDuration(350)
        original_pos = self.script_editor.pos()
        self.shake_anim.setKeyValueAt(0.0, original_pos)
        self.shake_anim.setKeyValueAt(0.2, original_pos + QPoint(-6, 0))
        self.shake_anim.setKeyValueAt(0.4, original_pos + QPoint(6, 0))
        self.shake_anim.setKeyValueAt(0.6, original_pos + QPoint(-6, 0))
        self.shake_anim.setKeyValueAt(0.8, original_pos + QPoint(6, 0))
        self.shake_anim.setKeyValueAt(1.0, original_pos)
        self.shake_anim.start()

    def run_hyphy_process(self):
        self.progress_table.setRowCount(0)
        self.task_map = {}
        self.active_tasks.clear()
        self.terminal_history = []

        if not self.job_queue:
            self.log_msg.emit(
                "[WARNING] Batch Queue is empty. Please add at least one job before running."
            )
            return

        exec_root = common_utils.get_hyphy_path(t1_st1_logic.CURRENT_PROJECT_PATH)
        if not exec_root:
            self.log_msg.emit(
                "[ERROR] No workspace selected.\nSolution: Please set a project workspace in the Dashboard first."
            )
            return

        threads = int(self.combo_cpu.currentText())
        min_cpu = int(self.combo_min_cpu.currentText())
        batches, allocations = t3_hyphy_logic.prep_parallel_tasks(
            self.job_queue,
            threads,
            self.chk_triplicate.isChecked(),
            min_cores=min_cpu,
        )

        row = 0
        for batch in batches:
            for task in batch:
                self.progress_table.insertRow(row)
                disp_f, disp_t = self.format_display_names(
                    task["f_name"], task["t_name"]
                )

                disp_model = task["model"]
                if task["run_suffix"]:
                    disp_model += f" (Run {task['run_suffix'].replace('_run', '')})"

                self.progress_table.setItem(row, 0, QTableWidgetItem(disp_f))
                self.progress_table.setItem(row, 1, QTableWidgetItem(disp_t))
                self.progress_table.setItem(row, 2, QTableWidgetItem(disp_model))
                self.progress_table.setItem(
                    row, 3, QTableWidgetItem(str(allocations[task["key"]]))
                )
                self.progress_table.setItem(row, 4, QTableWidgetItem("-"))
                self.progress_table.setItem(row, 5, QTableWidgetItem("-"))
                self.progress_table.setItem(row, 6, QTableWidgetItem("00:00"))
                badge = self.create_status_badge("Pending", "#F2F2F7", "#8E8E93")
                self.progress_table.setCellWidget(row, 7, badge)
                self.progress_table.item(row, 0).setData(
                    Qt.UserRole, badge.layout().itemAt(0).widget()
                )
                self.task_map[task["key"]] = row
                row += 1

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        work_dir = exec_root / f"Run_{timestamp}"
        work_dir.mkdir(parents=True, exist_ok=True)

        # The script refers to files by name, so two files with one name would
        # collapse into one here and both tasks would run on whichever landed
        # first. A missing file is named now rather than at HyPhy's error.
        copied = {}
        for job in self.job_queue:
            for f in [job["fasta"], job["tree"]]:
                src = Path(f)
                if not src.exists():
                    self.log_msg.emit(f"[ERROR] File not found: {f}")
                    return
                if copied.get(src.name, f) != f:
                    self.log_msg.emit(
                        f"[ERROR] Two different files are both named {src.name}. "
                        "Rename one of them before running."
                    )
                    return
                copied[src.name] = f

        for name, source in copied.items():
            shutil.copy2(source, work_dir / name)

        script_path = work_dir / "run_hyphy_local.sh"
        with open(script_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(self.script_editor.toPlainText())

        try:
            if sys.platform == "win32":
                wsl_script = t3_hyphy_logic.to_wsl_path(str(script_path))
                wsl_dir = t3_hyphy_logic.to_wsl_path(str(work_dir))
                cmd = ["wsl", "bash", "-c", f"cd '{wsl_dir}' && bash '{wsl_script}'"]
            else:
                os.chmod(script_path, 0o755)
                cmd = ["bash", str(script_path)]

            self.total_jobs = sum(len(b) for b in batches)
            self.completed_jobs = 0
            self.progress_update.emit("Batch Execution", 0, "Initializing...")

            self.local_process = QProcess(self)
            self.local_process.setWorkingDirectory(str(work_dir))
            self.current_work_dir = str(work_dir)
            self.local_process.readyReadStandardOutput.connect(self.handle_stdout)
            self.local_process.readyReadStandardError.connect(self.handle_stderr)
            self.local_process.finished.connect(self.handle_finished)
            self.local_process.start(cmd[0], cmd[1:])

            self.wsl_clear.emit()
            self.wsl_msg.emit("[SYSTEM] Initializing HyPhy Execution...")
            self.log_msg.emit(
                f"[PROCESS] HyPhy Parallel Execution Started ({self.total_jobs} tasks pending)..."
            )

            self.btn_run_hyphy.setEnabled(False)
            self.spinner_idx = 0
            self.spinner_timer.start(100)
            self.btn_abort.setEnabled(True)

        except Exception as e:
            err_tb = traceback.format_exc()
            self.log_msg.emit(f"[ERROR] Process failed to start: {str(e)}\n{err_tb}")
            self.wsl_msg.emit(f"[ERROR] Process failed to start: {str(e)}")
            if t1_st1_logic.CURRENT_PROJECT_PATH:
                common_utils.log_error_to_file(
                    str(t1_st1_logic.CURRENT_PROJECT_PATH),
                    "Tab 3",
                    f"Process Start Error:\n{err_tb}",
                )

    def abort_process(self):
        if (
            self.local_process
            and self.local_process.state() == QProcess.ProcessState.Running
        ):
            self.local_process.kill()
            self.wsl_msg.emit("\n[SYSTEM] Process aborted by user.")
            self.terminal_history.append("[SYSTEM] Process aborted by user.")
            self.reset_run_button()

            for row in range(self.progress_table.rowCount()):
                lbl = self.progress_table.item(row, 0).data(Qt.UserRole)
                if lbl and lbl.text() in ["Pending", "Running"]:
                    self.update_badge(row, "Aborted", "#FFECEB", "#FF3B30")

    def handle_stdout(self):
        data = (
            self.local_process.readAllStandardOutput()
            .data()
            .decode("utf-8", errors="replace")
        )
        for line in data.splitlines():
            ls = line.strip()
            if not ls:
                continue

            self.wsl_msg.emit(ls)
            self.terminal_history.append(ls)

            parts = ls.split("===")
            if len(parts) < 7 or not parts[1].startswith("REACTION_"):
                continue
            row = self.task_map.get(
                f"{parts[2]}==={parts[3]}==={parts[4]}==={parts[5]}"
            )
            if row is None:
                continue

            if parts[1] == "REACTION_START":
                self.active_tasks[row] = time.time()
                if not self.reaction_timer.isActive():
                    self.reaction_timer.start(1000)
                self.progress_table.item(row, 4).setText(self._now())
                self.update_badge(row, "Running", "#FFF9E5", "#FF9500")
                continue

            self.active_tasks.pop(row, None)
            if not self.active_tasks:
                self.reaction_timer.stop()
            self.progress_table.item(row, 5).setText(self._now())
            self.completed_jobs += 1
            pct = int((self.completed_jobs / max(1, self.total_jobs)) * 100)
            self.progress_update.emit("Batch Execution", pct, "Running...")

            if parts[1] == "REACTION_DONE":
                self.update_badge(row, "Completed", "#E5F0FF", "#0071E3")
            else:
                self.update_badge(row, "Failed", "#FFECEB", "#FF3B30")
                msg = (
                    f"[ERROR] Task execution failed for {parts[2]} "
                    f"(Model: {parts[4]})."
                )
                self.log_msg.emit(
                    msg + (self._error_log_tail() or " Please check the terminal logs.")
                )

    def update_badge(self, row, status, bg, fg):
        lbl = self.progress_table.item(row, 0).data(Qt.UserRole)
        if lbl:
            lbl.setText(status)
            lbl.setStyleSheet(
                f"background-color: {bg}; color: {fg}; border-radius: 4px; font-weight: 800; font-size: 10px; padding: 2px 6px; border: none;"
            )

    def _now(self):
        return datetime.datetime.now().strftime("%H:%M:%S")

    # The same errors.log is read when one task fails and when the whole run
    # fails, so both paths report the same text.
    def _error_log_tail(self):
        if not self.current_work_dir:
            return ""
        err_log = Path(self.current_work_dir) / "errors.log"
        try:
            content = err_log.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        return f"\n[EXTRACTED ERRORS.LOG]\n{content}" if content else ""

    def update_reaction_time(self):
        for row, st in list(self.active_tasks.items()):
            el = int(time.time() - st)
            m, s = divmod(el, 60)
            self.progress_table.item(row, 6).setText(f"{m:02d}:{s:02d}")

    def handle_stderr(self):
        data = (
            self.local_process.readAllStandardError()
            .data()
            .decode("utf-8", errors="replace")
        )
        if data.strip():
            for line in data.splitlines():
                if line.strip():
                    self.wsl_msg.emit(f"[ERROR] {line.strip()}")
                    self.terminal_history.append(f"[STDERR] {line.strip()}")

    def handle_finished(self, code, status):
        self.reset_run_button()
        if code == 0:
            self.wsl_msg.emit("\n[SYSTEM] All HyPhy jobs finished successfully!")
            self.progress_update.emit("Batch Execution", 100, "Completed")
            self.log_msg.emit("[SUCCESS] HyPhy Analysis Completed successfully!")
            if self.current_work_dir:
                self.log_msg.emit(f"[INFO] Results saved to: {self.current_work_dir}")
            self._write_run_log()

        elif code != ABORT_EXIT_CODE:
            self.wsl_msg.emit(f"\n[SYSTEM] Job failed with exit code {code}")
            self.progress_update.emit("Batch Execution", 0, "Failed")

            err_summary = (
                f"[ERROR] Bash Execution Failed (Exit Code: {code})\n"
                f"[TRACEBACK] Last output before crash:\n"
                f">>>\n{chr(10).join(self.terminal_history[-20:])}\n<<<\n"
            )
            err_summary += self._error_log_tail() or (
                "[HINT] The process might be waiting for user input. "
                "Check your script for missing arguments."
            )
            self.log_msg.emit(err_summary)

            saved = common_utils.log_error_to_file(
                t1_st1_logic.CURRENT_PROJECT_PATH,
                "Tab 3",
                err_summary
                + "\n\n=== FULL TERMINAL LOG ===\n"
                + "\n".join(self.terminal_history),
            )
            if saved:
                self.log_msg.emit(f"[INFO] Full crash log saved to: {saved}")

    def _write_run_log(self):
        if not t1_st1_logic.CURRENT_PROJECT_PATH:
            return
        log_dir = (
            Path(t1_st1_logic.CURRENT_PROJECT_PATH)
            / common_utils.REPORTS
            / "System_Logs"
        )
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(
                log_dir / f"log_report_{common_utils.mmdd()}.txt",
                "a",
                encoding="utf-8",
            ) as f:
                f.write(f"\n{'=' * 50}\n")
                f.write(f"[HYPHY EXECUTION FULL LOG] {common_utils.timestamp()}\n")
                f.write(f"{'=' * 50}\n")
                f.write("\n".join(self.terminal_history) + "\n\n")
        except OSError as e:
            self.log_msg.emit(f"[ERROR] Failed to embed terminal log: {e}")

    def export_zip(self):
        save_path = pick_save(
            self, "Save Export Package", "HyPhy_Job.zip", "ZIP Files (*.zip)"
        )
        if not save_path:
            return
        ok, message = t3_hyphy_logic.export_job_to_zip(
            self.job_queue, self.script_editor.toPlainText(), save_path
        )
        self.log_msg.emit(f"[{'SUCCESS' if ok else 'ERROR'}] {message}")

    def export_slurm(self):
        save_path = pick_save(
            self, "Save SLURM Script", "hyphlow_slurm.sh", "Shell Scripts (*.sh)"
        )
        if not save_path:
            return

        # Built from the queue, not from the editor: the local script manages
        # its own worker pool, which would fight the scheduler on a cluster.
        script = t3_hyphy_logic.generate_slurm_script(
            self.job_queue,
            self.chk_triplicate.isChecked(),
            cpus_per_task=int(self.combo_min_cpu.currentText()),
        )
        if not script:
            self.log_msg.emit(
                "[ERROR] No task in the queue can run: check the FG tags on the "
                "trees you selected."
            )
            return

        try:
            with open(save_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(script)
        except OSError as e:
            self.log_msg.emit(f"[ERROR] Could not save the SLURM script: {e}")
            return

        self.log_msg.emit(f"[SUCCESS] SLURM array script saved to: {save_path}")
        self.log_msg.emit(
            "[INFO] Open the script and edit the lines marked TODO before "
            "submitting: wall time, memory, and how HyPhy is loaded on your "
            "cluster. Then submit it with: sbatch <script>"
        )
