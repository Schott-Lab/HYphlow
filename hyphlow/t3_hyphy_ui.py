import os
import sys
import time
import shutil
import datetime
import types
import traceback
import subprocess
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFrame,
    QLabel,
    QTextEdit,
    QFileDialog,
    QSplitter,
    QLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QSizePolicy,
)
from PyQt5.QtCore import (
    Qt,
    QPoint,
    QRect,
    QSize,
    pyqtSignal,
    QPropertyAnimation,
    QProcess,
    QTimer,
)
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QTextCursor
import qtawesome as qta
from hyphlow import t3_hyphy_logic
from hyphlow import common_utils
from hyphlow import t1_st1_logic
from hyphlow.common_ui import (
    UnifiedDropZone,
    PrimaryButton,
)


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        return self.itemList[index] if 0 <= index < len(self.itemList) else None

    def takeAt(self, index):
        return self.itemList.pop(index) if 0 <= index < len(self.itemList) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            if item is not None and item.widget() is not None:
                size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )
        return size

    def doLayout(self, rect, testOnly):
        x, y, lineHeight = rect.x(), rect.y(), 0
        spacing = self.spacing()
        for item in self.itemList:
            if item is None or item.widget() is None:
                continue
            nextX = x + item.sizeHint().width() + spacing
            if nextX - spacing > rect.right() and lineHeight > 0:
                x, y = rect.x(), y + lineHeight + spacing
                nextX, lineHeight = x + item.sizeHint().width() + spacing, 0
            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())
        return y + lineHeight - rect.y()


class FlowContainer(QWidget):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.layout():
            h = self.layout().heightForWidth(self.width())
            if self.minimumHeight() != h:
                self.setMinimumHeight(h)


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
        self.models = ["BUSTED", "aBSREL", "FEL", "MEME", "FUBAR", "RELAX"]
        self.is_generating_script = False
        self.was_valid = True
        self.local_process = None
        self.job_queue = []
        self.reaction_timer = QTimer(self)
        self.reaction_timer.timeout.connect(self.update_reaction_time)
        self.active_tasks = {}
        self.task_map = {}
        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0
        self.spinner_timer = QTimer(self)
        self.spinner_timer.timeout.connect(self.update_spinner)
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
            show_gene_input=False,
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
            show_gene_input=False,
        )
        self.dz_nwk.files_updated.connect(self.handle_nwk_files)
        nc_layout.addWidget(self.dz_nwk)
        dz_layout.addWidget(self.nwk_container, 1)

        def custom_fasta_browse(self_dz):
            default_dir = (
                str(
                    t1_st1_logic.CURRENT_PROJECT_PATH
                    / "Results"
                    / "Data_Preparation"
                    / "FASTA"
                )
                if t1_st1_logic.CURRENT_PROJECT_PATH
                else ""
            )
            import platform
            if platform.system() == "Linux":
                dialog = QFileDialog(self_dz, "Select FASTA Files", default_dir, "FASTA Files (*.fas *.fasta *.fa)")
                dialog.setFileMode(QFileDialog.ExistingFiles)
                dialog.setStyleSheet("""
                    QWidget { background-color: #FFFFFF; color: #1D1D1F; }
                    QTreeView, QListView, QTableView { background-color: #FFFFFF; color: #1D1D1F; alternate-background-color: #F2F2F7; outline: none; }
                    QTreeView::item:selected, QListView::item:selected { background-color: #0071E3; color: #FFFFFF; }
                    QHeaderView::section { background-color: #F2F2F7; color: #1D1D1F; border: 1px solid #D1D1D6; padding: 4px; }
                    QPushButton { background-color: #E5E5EA; color: #1D1D1F; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
                    QPushButton:hover { background-color: #D1D1D6; }
                    QLineEdit, QComboBox { background-color: #F5F5F7; color: #1D1D1F; border: 1px solid #D1D1D6; padding: 4px; }
                """)
                if dialog.exec_():
                    files = dialog.selectedFiles()
                    if files:
                        self_dz.add_files(files)
            else:
                files, _ = QFileDialog.getOpenFileNames(
                    self_dz, "Select FASTA Files", default_dir, "FASTA Files (*.fas *.fasta *.fa)"
                )
                if files:
                    self_dz.add_files(files)

        self.dz_fasta._open_file_dialog = types.MethodType(
            custom_fasta_browse, self.dz_fasta
        )

        def custom_nwk_browse(self_dz):
            default_dir = (
                str(t1_st1_logic.CURRENT_PROJECT_PATH / "Results" / "Tree_Annotation")
                if t1_st1_logic.CURRENT_PROJECT_PATH
                else ""
            )
            import platform
            if platform.system() == "Linux":
                dialog = QFileDialog(self_dz, "Select NWK Files", default_dir, "NWK Files (*.nwk *.tre *.tree)")
                dialog.setFileMode(QFileDialog.ExistingFiles)
                dialog.setStyleSheet("""
                    QWidget { background-color: #FFFFFF; color: #1D1D1F; }
                    QTreeView, QListView, QTableView { background-color: #FFFFFF; color: #1D1D1F; alternate-background-color: #F2F2F7; outline: none; }
                    QTreeView::item:selected, QListView::item:selected { background-color: #0071E3; color: #FFFFFF; }
                    QHeaderView::section { background-color: #F2F2F7; color: #1D1D1F; border: 1px solid #D1D1D6; padding: 4px; }
                    QPushButton { background-color: #E5E5EA; color: #1D1D1F; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
                    QPushButton:hover { background-color: #D1D1D6; }
                    QLineEdit, QComboBox { background-color: #F5F5F7; color: #1D1D1F; border: 1px solid #D1D1D6; padding: 4px; }
                """)
                if dialog.exec_():
                    files = dialog.selectedFiles()
                    if files:
                        self_dz.add_files(files)
            else:
                files, _ = QFileDialog.getOpenFileNames(
                    self_dz, "Select NWK Files", default_dir, "NWK Files (*.nwk *.tre *.tree)"
                )
                if files:
                    self_dz.add_files(files)

        self.dz_nwk._open_file_dialog = types.MethodType(custom_nwk_browse, self.dz_nwk)
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
        self.queue_container = FlowContainer()
        self.queue_container.setStyleSheet("background: transparent; border: none;")
        self.queue_layout = FlowLayout(self.queue_container, margin=0, spacing=8)
        cl_layout.addWidget(self.queue_container)
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
        self.combo_method.addItems(self.models)
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
        desc_lbl = QLabel(f"Recommended max CPU: {rec_cores}")
        desc_lbl.setStyleSheet(
            "color: #8E8E93; font-size: 11px; border: none; background: transparent; padding-left: 2px;"
        )
        cpu_layout.addWidget(desc_lbl)
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
        self.script_editor.setFont(QFont("Consolas", 10))
        self.script_editor.setStyleSheet(
            "QTextEdit { background-color: #2D2D30; color: #D4D4D4; border: 1px solid #D1D1D6; border-radius: 8px; padding: 10px; }"
        )
        self.script_editor.setAcceptRichText(False)
        self.script_editor.textChanged.connect(self.check_syntax)
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
        self.btn_export_zip = QPushButton("Export")
        self.btn_export_zip.setStyleSheet("""
            QPushButton { background-color: #0071E3; color: white; font-size: 11px; font-weight: bold; border-radius: 6px; padding: 5px 12px; border: none; }
            QPushButton:hover { background-color: #005BB5; }
            QPushButton:disabled { background-color: #E5E5EA; color: #8E8E93; }
        """)
        self.btn_export_zip.clicked.connect(self.export_zip)
        self.btn_export_zip.setEnabled(False)
        table_header.addWidget(self.btn_export_zip)
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
        if not self.fasta_files or not self.nwk_files:
            return
        self.match_tree.blockSignals(True)
        self.match_tree.clear()
        matched_dict = t3_hyphy_logic.get_matched_pairs(
            self.fasta_files, self.nwk_files
        )
        for fasta_stem, data in matched_dict.items():
            fasta_item = QTreeWidgetItem(self.match_tree)
            fasta_item.setText(0, f" {Path(data['fasta_path']).name}")
            for tree_data in data["trees"]:
                tree_item = QTreeWidgetItem(fasta_item)
                tree_item.setFlags(tree_item.flags() | Qt.ItemIsUserCheckable)
                is_valid = tree_data["is_valid"]
                if is_valid:
                    tree_item.setCheckState(0, Qt.Checked)
                    tree_item.setText(0, f" {Path(tree_data['nwk_path']).name}")
                    badge = self.create_status_badge("Matched", "#EBF9EE", "#34C759")
                    self.match_tree.setItemWidget(tree_item, 2, badge)
                else:
                    tree_item.setCheckState(0, Qt.Unchecked)
                    tree_item.setText(0, f" {Path(tree_data['nwk_path']).name}")
                    badge = self.create_status_badge("Mismatch", "#FFF9E5", "#FF9500")
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
                self.render_queue_pill(new_job)
                added_count += 1
        if added_count > 0:
            self.update_script_preview()
            self.hide_builder()

    def render_queue_pill(self, job):
        pill = QFrame()
        pill.setStyleSheet(
            "QFrame { background-color: #F5F5F7; border: 1px solid #D1D1D6; border-radius: 12px; }"
        )
        pill_layout = QHBoxLayout(pill)
        pill_layout.setContentsMargins(10, 4, 10, 4)
        pill_layout.setSpacing(6)
        model_lbl = QLabel(job["model"])
        model_lbl.setStyleSheet(
            "font-weight: 900; font-size: 11px; color: #0071E3; border: none; background: transparent;"
        )
        disp_f, disp_t = self.format_display_names(
            Path(job["fasta"]).name, Path(job["tree"]).name
        )
        t_lbl = QLabel(disp_t)
        t_lbl.setStyleSheet(
            "font-weight: 500; font-size: 11px; color: #1D1D1F; border: none; background: transparent;"
        )
        btn_del = QPushButton("X")
        btn_del.setFixedSize(16, 16)
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setStyleSheet("""
            QPushButton { border: none; background: transparent; font-weight: bold; color: #8E8E93; font-size: 10px; border-radius: 8px; }
            QPushButton:hover { background: #FFECEB; color: #FF3B30; }
        """)
        btn_del.clicked.connect(lambda: self.remove_job_from_queue(job["job_id"], pill))
        pill_layout.addWidget(model_lbl)
        pill_layout.addWidget(
            QLabel(
                "|", styleSheet="color: #D1D1D6; border: none; background: transparent;"
            )
        )
        pill_layout.addWidget(t_lbl)
        pill_layout.addWidget(btn_del)
        self.queue_layout.addItem(self.queue_layout.addWidget(pill))

    def remove_job_from_queue(self, job_id, pill_widget):
        self.job_queue = [j for j in self.job_queue if j["job_id"] != job_id]
        self.queue_layout.removeWidget(pill_widget)
        pill_widget.deleteLater()
        self.update_script_preview()

    def update_script_preview(self):
        self.is_generating_script = True
        threads = int(self.combo_cpu.currentText())
        script_content = t3_hyphy_logic.generate_bash_script(self.job_queue, threads)
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
            self.btn_run_hyphy.setText(" Syntax Error")
            self.btn_run_hyphy.setIcon(qta.icon("mdi.alert", color="#FF3B30"))
            self.btn_run_hyphy.setToolTip(f"Error: {errors[0]}")
            self.btn_run_hyphy.setStyleSheet("""
                QPushButton { background-color: #FFECEB; color: #FF3B30; font-size: 12px; font-weight: bold; border-radius: 6px; padding: 0 16px; border: 1px solid #FF3B30; }
            """)
            self.btn_export_zip.setEnabled(False)
            self.btn_run_hyphy.setEnabled(False)
            if self.was_valid and self.job_queue:
                self.trigger_shake_animation()
                self.was_valid = False
        else:
            self.btn_run_hyphy.setText(" Run HyPhy Execution")
            self.btn_run_hyphy.setIcon(qta.icon("mdi.play", color="white"))
            self.btn_run_hyphy.setToolTip("")
            self.btn_run_hyphy.setStyleSheet("""
                QPushButton { background-color: #1D1D1F; color: white; font-size: 12px; font-weight: bold; border-radius: 6px; padding: 0 16px; border: none; }
                QPushButton:hover { background-color: #333333; }
                QPushButton:disabled { background-color: #E5E5EA; color: #8E8E93; }
            """)
            self.btn_export_zip.setEnabled(True)
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

        threads = int(self.combo_cpu.currentText())
        batches, allocations = t3_hyphy_logic.prep_parallel_tasks(
            self.job_queue, threads
        )

        row = 0
        for batch in batches:
            for task in batch:
                self.progress_table.insertRow(row)
                disp_f, disp_t = self.format_display_names(
                    task["f_name"], task["t_name"]
                )
                self.progress_table.setItem(row, 0, QTableWidgetItem(disp_f))
                self.progress_table.setItem(row, 1, QTableWidgetItem(disp_t))
                self.progress_table.setItem(row, 2, QTableWidgetItem(task["model"]))
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
        work_dir = Path.cwd() / "Results" / "HyPhy_Execution" / f"Run_{timestamp}"
        work_dir.mkdir(parents=True, exist_ok=True)

        for job in self.job_queue:
            for f in [job["fasta"], job["tree"]]:
                src = Path(f)
                dst = work_dir / src.name
                if src.exists() and not dst.exists():
                    shutil.copy2(src, dst)

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

            self.total_jobs = len(self.job_queue)
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
                f"[PROCESS] HyPhy Parallel Execution Started ({self.total_jobs} jobs pending)..."
            )

            self.btn_run_hyphy.setEnabled(False)
            self.btn_run_hyphy.setStyleSheet("""
                QPushButton { background-color: #E5E5EA; color: #8E8E93; font-size: 12px; font-weight: bold; border-radius: 6px; padding: 0 16px; border: none; }
            """)
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

            if ls.startswith("===REACTION_START==="):
                parts = ls.split("===")
                if len(parts) >= 5:
                    key = f"{parts[2]}==={parts[3]}==={parts[4]}==={parts[5]}"
                    if key in self.task_map:
                        row = self.task_map[key]
                        self.active_tasks[row] = time.time()
                        if not self.reaction_timer.isActive():
                            self.reaction_timer.start(1000)
                        self.progress_table.item(row, 4).setText(
                            datetime.datetime.now().strftime("%H:%M:%S")
                        )
                        self.update_badge(row, "Running", "#FFF9E5", "#FF9500")

            elif ls.startswith("===REACTION_DONE==="):
                parts = ls.split("===")
                if len(parts) >= 5:
                    key = f"{parts[2]}==={parts[3]}==={parts[4]}==={parts[5]}"
                    if key in self.task_map:
                        row = self.task_map[key]
                        if row in self.active_tasks:
                            del self.active_tasks[row]
                        self.progress_table.item(row, 5).setText(
                            datetime.datetime.now().strftime("%H:%M:%S")
                        )
                        self.update_badge(row, "Completed", "#E5F0FF", "#0071E3")
                        self.completed_jobs += 1
                        pct = int((self.completed_jobs / max(1, self.total_jobs)) * 100)
                        self.progress_update.emit("Batch Execution", pct, "Running...")

            elif ls.startswith("===REACTION_ERROR==="):
                parts = ls.split("===")
                if len(parts) >= 5:
                    key = f"{parts[2]}==={parts[3]}==={parts[4]}==={parts[5]}"
                    if key in self.task_map:
                        row = self.task_map[key]
                        if row in self.active_tasks:
                            del self.active_tasks[row]
                        self.progress_table.item(row, 5).setText(
                            datetime.datetime.now().strftime("%H:%M:%S")
                        )
                        self.update_badge(row, "Failed", "#FFECEB", "#FF3B30")
                        self.completed_jobs += 1
                        pct = int((self.completed_jobs / max(1, self.total_jobs)) * 100)
                        self.progress_update.emit("Batch Execution", pct, "Running...")

                        extracted_error = ""
                        if hasattr(self, "current_work_dir"):
                            err_log = Path(self.current_work_dir) / "errors.log"
                            if err_log.exists():
                                try:
                                    with open(err_log, "r", encoding="utf-8") as f:
                                        content = f.read().strip()
                                        if content:
                                            extracted_error = (
                                                f"\n[EXTRACTED ERRORS.LOG]\n{content}"
                                            )
                                except Exception:
                                    pass

                        msg = f"[ERROR] Job execution failed for {parts[2]} (Model: {parts[4]})."
                        if extracted_error:
                            msg += extracted_error
                        else:
                            msg += " Please check the terminal logs."
                        self.log_msg.emit(msg)

    def update_badge(self, row, status, bg, fg):
        lbl = self.progress_table.item(row, 0).data(Qt.UserRole)
        if lbl:
            lbl.setText(status)
            lbl.setStyleSheet(
                f"background-color: {bg}; color: {fg}; border-radius: 4px; font-weight: 800; font-size: 10px; padding: 2px 6px; border: none;"
            )

    def update_reaction_time(self):
        for row, st in self.active_tasks.items():
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
            if hasattr(self, "current_work_dir"):
                try:
                    if sys.platform == "win32":
                        os.startfile(self.current_work_dir)
                    elif sys.platform == "darwin":
                        subprocess.call(["open", self.current_work_dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        try:
                            res = subprocess.call(["explorer.exe", self.current_work_dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if res != 0:
                                raise OSError()
                        except Exception:
                            res2 = subprocess.call(["xdg-open", self.current_work_dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if res2 != 0:
                                raise OSError()
                except Exception:
                    self.log_msg.emit("[INFO] Analysis completed successfully and all results are safely saved.")
                    self.log_msg.emit("[INFO] Unable to automatically visualize the output folder due to missing GUI display components in the current environment.")
                    self.log_msg.emit(f"[INFO] Please manually navigate to: {self.current_work_dir}")

            if t1_st1_logic.CURRENT_PROJECT_PATH:
                try:
                    full_log = (
                        "\n".join(self.terminal_history)
                        if hasattr(self, "terminal_history")
                        else ""
                    )
                    mmdd = datetime.datetime.now().strftime("%m%d")
                    log_dir = (
                        Path(t1_st1_logic.CURRENT_PROJECT_PATH)
                        / "Reports"
                        / "System_Logs"
                    )
                    log_dir.mkdir(parents=True, exist_ok=True)
                    log_file = log_dir / f"log_report_{mmdd}.txt"
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"\n{'='*50}\n")
                        f.write(
                            f"[HYPHY EXECUTION FULL LOG] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        )
                        f.write(f"{'='*50}\n")
                        f.write(full_log + "\n\n")
                except Exception as e:
                    self.log_msg.emit(f"[ERROR] Failed to embed terminal log: {str(e)}")

        elif code != 9:
            self.wsl_msg.emit(f"\n[SYSTEM] Job failed with exit code {code}")
            self.progress_update.emit("Batch Execution", 0, "Failed")

            last_words = (
                "\n".join(self.terminal_history[-20:])
                if hasattr(self, "terminal_history")
                else ""
            )

            extracted_error = ""
            if hasattr(self, "current_work_dir"):
                err_log = Path(self.current_work_dir) / "errors.log"
                if err_log.exists():
                    try:
                        with open(err_log, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                            if content:
                                extracted_error = f"\n[EXTRACTED ERRORS.LOG]\n{content}"
                    except Exception:
                        pass

            err_summary = (
                f"[ERROR] Bash Execution Failed (Exit Code: {code})\n"
                f"[TRACEBACK] Last output before crash:\n"
                f">>>\n{last_words}\n<<<\n"
            )

            if extracted_error:
                err_summary += extracted_error
            else:
                err_summary += "[HINT] The process might be waiting for user input. Check your script for missing arguments."

            self.log_msg.emit(err_summary)

            if t1_st1_logic.CURRENT_PROJECT_PATH:
                try:
                    full_log = (
                        "\n".join(self.terminal_history)
                        if hasattr(self, "terminal_history")
                        else ""
                    )
                    mmdd = datetime.datetime.now().strftime("%m%d_%H%M%S")
                    err_dir = (
                        Path(t1_st1_logic.CURRENT_PROJECT_PATH)
                        / "Reports"
                        / "Error_Reports"
                    )
                    err_dir.mkdir(parents=True, exist_ok=True)
                    crash_file = err_dir / f"HYphlow_Bash_Crash_Log_{mmdd}.txt"
                    with open(crash_file, "w", encoding="utf-8") as f:
                        f.write(
                            err_summary + "\n\n=== FULL TERMINAL LOG ===\n" + full_log
                        )
                    self.log_msg.emit(f"[INFO] Full crash log saved to: {crash_file}")
                except Exception as e:
                    self.log_msg.emit(f"[ERROR] Failed to save crash log: {str(e)}")

    def export_zip(self):
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Export Package", "HyPhy_Job.zip", "ZIP Files (*.zip)"
        )
        if save_path:
            script = self.script_editor.toPlainText()
            t3_hyphy_logic.export_job_to_zip(self.job_queue, script, save_path)
            self.log_msg.emit(
                f"[SUCCESS] Export Package ZIP created successfully at: {save_path}"
            )
