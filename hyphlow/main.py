import sys
import os
import re
import platform
import subprocess
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QFrame,
    QLabel,
    QStackedWidget,
    QTextBrowser,
    QProgressBar,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QGraphicsDropShadowEffect,
    QDialog,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
)
from PyQt5.QtGui import QFont, QColor, QPixmap, QIcon, QPainter, QTextCursor, QPalette
from PyQt5.QtCore import Qt, QSettings, pyqtSignal, QTimer, QTime
import qtawesome as qta

from hyphlow import t1_st1_logic
from hyphlow.t1_st1_ui import StandardizationPage
from hyphlow.t1_st4_ui import Subtab4PruningUI
from hyphlow.t1_st5_ui import Subtab5ReconUI
from hyphlow.t2_tagging_ui import Tab2TaggingUI
from hyphlow.t3_hyphy_ui import Tab3HyPhyUI
from hyphlow.t4_summary_ui import Tab4SummaryUI
from hyphlow.common_ui import LogConsole


def get_logo_path():
    try:
        base = Path(sys._MEIPASS)
        return base / "assets" / "logo.png"
    except Exception:
        return Path(__file__).resolve().parent / "assets" / "logo.png"

class SpinnerLabel(QLabel):
    def __init__(self, size=16, color="#0071E3"):
        super().__init__()
        self.icon_size = size
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.idx = 0
        self.color = color
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(size + 10, size + 10)
        self.setStyleSheet(
            f"color: {self.color}; font-weight: 900; font-size: {size + 4}px; font-family: 'Consolas', monospace;"
        )
        self.setText(self.frames[0])

    def start(self):
        self.timer.start(80)

    def stop(self, completed=True):
        self.timer.stop()
        if completed:
            self.setText("")
            self.setPixmap(
                qta.icon("mdi.check-circle-outline", color="#34C759").pixmap(
                    self.icon_size, self.icon_size
                )
            )

    def update_frame(self):
        self.idx = (self.idx + 1) % len(self.frames)
        self.setText(self.frames[self.idx])


class StartupDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Welcome to HYphlow")
        self.setFixedSize(500, 320)
        self.settings = QSettings("HYphlow_Team", "HYphlow_App")
        logo_path = get_logo_path()
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(str(logo_path)))
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; }
            QLabel, QLineEdit, QPushButton { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
            QLabel { color: #1D1D1F; font-size: 14px; }
            QLabel#Title { font-size: 19px; font-weight: 800; letter-spacing: -0.5px; }
            QLineEdit { border: 1px solid #D2D2D7; border-radius: 8px; padding: 6px 10px; font-size: 13px; background-color: #F5F5F7; }
            QPushButton { background-color: #1D1D1F; color: white; border-radius: 15px; padding: 8px 20px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: #333333; }
            QPushButton#ExitBtn { background-color: #F5F5F7; color: #1D1D1F; border: 1px solid #D2D2D7; }
            QPushButton#ExitBtn:hover { background-color: #E8E8ED; }
            QPushButton#BrowseBtn { background-color: #E8E8ED; color: #1D1D1F; border-radius: 8px; border: none; }
            QPushButton#BrowseBtn:hover { background-color: #D2D2D7; }
            """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        top_layout = QHBoxLayout()
        self.logo_label = QLabel()
        if os.path.exists(logo_path):
            pixmap = QPixmap(str(logo_path)).scaled(
                80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.logo_label.setPixmap(pixmap)
        else:
            self.logo_label.setText("HYphlow\nLOGO")
            self.logo_label.setAlignment(Qt.AlignCenter)
            self.logo_label.setStyleSheet(
                "border: 1px dashed #D2D2D7; border-radius: 10px;"
            )
            self.logo_label.setFixedSize(80, 80)
        top_layout.addWidget(self.logo_label)
        welcome_label = QLabel(
            "Welcome to HYphlow!\nPlease set up your project\nworkspace to begin."
        )
        welcome_label.setObjectName("Title")
        welcome_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        top_layout.addSpacing(20)
        top_layout.addWidget(welcome_label, stretch=1)
        layout.addLayout(top_layout)
        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)
        last_project_name = self.settings.value("last_project_name", "")
        last_workspace = self.settings.value("last_workspace_path", "")
        label_width = 100
        name_layout = QHBoxLayout()
        name_label = QLabel("Project Name:")
        name_label.setFixedWidth(label_width)
        name_layout.addWidget(name_label)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Schott Lab Project")
        if last_project_name:
            self.name_input.setText(last_project_name)
        name_layout.addWidget(self.name_input)
        form_layout.addLayout(name_layout)
        path_layout = QHBoxLayout()
        path_label = QLabel("Workspace:")
        path_label.setFixedWidth(label_width)
        path_layout.addWidget(path_label)
        self.path_input = QLineEdit()
        self.path_input.setReadOnly(True)
        self.path_input.setPlaceholderText("Select a folder...")
        if last_workspace:
            self.path_input.setText(last_workspace)
        path_layout.addWidget(self.path_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("BrowseBtn")
        browse_btn.setFixedWidth(100)
        browse_btn.clicked.connect(self.browse_folder)
        path_layout.addWidget(browse_btn)
        form_layout.addLayout(path_layout)
        layout.addLayout(form_layout)
        layout.addStretch()
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        exit_btn = QPushButton("Exit")
        exit_btn.setObjectName("ExitBtn")
        exit_btn.clicked.connect(self.reject)
        btn_layout.addWidget(exit_btn)
        btn_text = "Continue Project" if last_workspace else "Create Project"
        start_btn = QPushButton(btn_text)
        start_btn.clicked.connect(self.start_project)
        btn_layout.addWidget(start_btn)
        layout.addLayout(btn_layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Project Workspace"
        )
        if folder:
            self.path_input.setText(folder)

    def start_project(self):
        if not self.path_input.text():
            QMessageBox.warning(
                self, "Warning", "Please select a Workspace folder to continue."
            )
            return
        proj_name = self.name_input.text()
        self.settings.setValue("last_project_name", proj_name)
        self.settings.setValue("last_workspace_path", self.path_input.text())
        if proj_name:
            t1_st1_logic.set_project_name(proj_name)
        t1_st1_logic.set_project_path(self.path_input.text())
        self.accept()


class WorkflowBlock(QFrame):
    teleport_requested = pyqtSignal(int, str, int)

    def __init__(self, title, main_idx, main_name, sub_idx=0):
        super().__init__()
        self.setStyleSheet(
            "QFrame { background-color: #F8F8F8; border: 1px solid #E5E5EA; border-radius: 10px; }"
        )
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(6)
        self.header_layout = QHBoxLayout()
        self.title_btn = QPushButton(f" {title}")
        self.title_btn.setIcon(qta.icon("mdi.link-variant", color="#8E8E93"))
        self.title_btn.setStyleSheet(
            "QPushButton { font-weight: bold; font-size: 13px; color: #1D1D1F; border: none; text-align: left; padding: 4px 8px; border-radius: 6px; } QPushButton:hover { background-color: #E5E5EA; }"
        )
        self.title_btn.setCursor(Qt.PointingHandCursor)
        self.title_btn.clicked.connect(
            lambda: self.teleport_requested.emit(main_idx, main_name, sub_idx)
        )
        self.header_layout.addWidget(self.title_btn)
        self.header_layout.addStretch()
        self.folder_btn = QPushButton(" Open Folder")
        self.folder_btn.setIcon(qta.icon("mdi.folder-open-outline", color="#8E8E93"))
        self.folder_btn.setStyleSheet(
            "QPushButton { color: #8E8E93; font-size: 11px; font-weight: bold; border: none; background: transparent; } QPushButton:hover { color: #1D1D1F; }"
        )
        self.header_layout.addWidget(self.folder_btn)
        self.toggle_btn = QPushButton()
        self.toggle_btn.setIcon(qta.icon("mdi.chevron-down", color="#1D1D1F"))
        self.toggle_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; } QPushButton:hover { background: #E5E5EA; border-radius: 4px; }"
        )
        self.toggle_btn.setFixedSize(24, 24)
        self.is_expanded = False
        self.toggle_btn.clicked.connect(self.toggle_collapse)
        self.header_layout.addWidget(self.toggle_btn)
        self.layout.addLayout(self.header_layout)
        self.global_bar = QProgressBar()
        self.global_bar.setRange(0, 100)
        self.global_bar.setValue(0)
        self.global_bar.setTextVisible(False)
        self.global_bar.setFixedHeight(6)
        self.global_bar.setStyleSheet(
            "QProgressBar { background-color: #E5E5EA; border-radius: 3px; border: none; margin-top: 2px; } QProgressBar::chunk { background-color: #1D1D1F; border-radius: 3px; }"
        )
        self.layout.addWidget(self.global_bar)
        self.status_lbl = QLabel("Status: Idle")
        self.status_lbl.setStyleSheet(
            "color: #515154; font-size: 12px; border: none; margin-top: 2px;"
        )
        self.layout.addWidget(self.status_lbl)
        self.file_trackers = {}
        self.content_area = QFrame()
        self.content_area.setStyleSheet("background-color: transparent; border: none;")
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 10, 0, 0)
        self.content_layout.setSpacing(8)
        self.layout.addWidget(self.content_area)
        self.content_area.hide()

    def toggle_collapse(self, force_open=False):
        if force_open:
            self.is_expanded = False
        if self.is_expanded:
            self.content_area.hide()
            self.toggle_btn.setIcon(qta.icon("mdi.chevron-down", color="#1D1D1F"))
        else:
            self.content_area.show()
            self.toggle_btn.setIcon(qta.icon("mdi.chevron-up", color="#1D1D1F"))
        self.is_expanded = not self.is_expanded

    def update_file_progress(self, filename, progress, status_text):
        self.global_bar.setValue(progress)
        self.status_lbl.setText(f"Status: {status_text} ({progress}%)")
        self.status_lbl.setStyleSheet(
            "color: #0071E3; font-size: 12px; font-weight: bold; border: none; margin-top: 2px;"
        )

        if filename not in self.file_trackers:
            item_frame = QFrame()
            item_frame.setStyleSheet(
                "background-color: transparent; border: none; padding: 4px;"
            )
            item_layout = QHBoxLayout(item_frame)
            item_layout.setContentsMargins(8, 4, 8, 4)
            spinner = SpinnerLabel(16)
            spinner.start()
            item_layout.addWidget(spinner)
            name_lbl = QLabel(filename)
            name_lbl.setStyleSheet(
                "color: #1D1D1F; font-size: 12px; font-weight: 500; border: none;"
            )
            item_layout.addWidget(name_lbl)
            item_layout.addStretch()
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(progress)
            bar.setTextVisible(False)
            bar.setFixedSize(60, 4)
            bar.setStyleSheet(
                "QProgressBar { background-color: #F2F2F7; border-radius: 2px; border: none; } QProgressBar::chunk { background-color: #0071E3; border-radius: 2px; }"
            )
            item_layout.addWidget(bar)
            self.content_layout.addWidget(item_frame)
            self.file_trackers[filename] = {
                "bar": bar,
                "frame": item_frame,
                "spinner": spinner,
            }
            self.toggle_collapse(force_open=True)
        else:
            self.file_trackers[filename]["bar"].setValue(progress)

        if progress >= 100:
            self.status_lbl.setText("Status: Completed")
            self.status_lbl.setStyleSheet(
                "color: #34C759; font-size: 12px; font-weight: bold; border: none; margin-top: 2px;"
            )
            self.file_trackers[filename]["bar"].setStyleSheet(
                "QProgressBar { background-color: #F2F2F7; border-radius: 2px; border: none; } QProgressBar::chunk { background-color: #34C759; border-radius: 2px; }"
            )
            self.file_trackers[filename]["spinner"].stop(completed=True)


class HyphlowMain(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HYphlow v1")
        self.resize(1200, 850)
        logo_path = get_logo_path()
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(str(logo_path)))
        QApplication.setFont(QFont("Segoe UI", 10))
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(240)
        self.sidebar.setStyleSheet(
            "background-color: #F2F2F7; border-right: 1px solid #E5E5EA;"
        )
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_top_layout = QHBoxLayout()
        sidebar_top_layout.setContentsMargins(20, 25, 20, 15)
        sidebar_top_layout.setSpacing(10)
        sidebar_logo_label = QLabel()
        if os.path.exists(logo_path):
            pixmap = QPixmap(str(logo_path)).scaled(
                32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            sidebar_logo_label.setPixmap(pixmap)
        sidebar_logo_label.setStyleSheet("border: none; background: transparent;")
        sidebar_top_layout.addWidget(sidebar_logo_label)

        sidebar_title_label = QLabel("HYphlow")
        sidebar_title_label.setObjectName("MainTitle")
        sidebar_title_label.setStyleSheet("border: none; background: transparent;")
        sidebar_top_layout.addWidget(sidebar_title_label)

        sidebar_top_layout.addStretch()
        sidebar_layout.addLayout(sidebar_top_layout)
        nav_layout = QVBoxLayout()
        nav_layout.setContentsMargins(10, 0, 10, 0)
        nav_layout.setSpacing(5)
        self.nav_buttons = {}

        self.icon_map = {
            "Dashboard": "mdi.view-dashboard-outline",
            "Data Preparation": "mdi.database-outline",
            "Tree Annotation": "mdi.graph-outline",
            "HyPhy Execution": "mdi.console",
            "Results Summary": "mdi.chart-box-outline",
        }
        for name, icon_code in self.icon_map.items():
            btn = QPushButton(" " + name)
            btn.setIcon(qta.icon(icon_code, color="#515154"))
            btn.setFlat(True)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 10px 15px; font-size: 14px; font-weight: 600; color: #1D1D1F; border-radius: 8px; border: none; background: transparent; } QPushButton:hover { background-color: #E5E5EA; }"
            )
            nav_layout.addWidget(btn)
            self.nav_buttons[name.strip()] = btn
        nav_layout.addStretch()
        sidebar_layout.addLayout(nav_layout)
        main_layout.addWidget(self.sidebar)
        right_area = QWidget()
        right_layout = QVBoxLayout(right_area)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.header_frame = QFrame()
        self.header_frame.setStyleSheet(
            "background-color: #FFFFFF; border-bottom: 1px solid #E5E5EA;"
        )
        self.header_frame.setFixedHeight(68)
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(40, 0, 40, 0)
        header_layout.setSpacing(15)
        self.main_tab_icon = QLabel()
        self.main_tab_icon.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(self.main_tab_icon)

        self.main_tab_title = QLabel("")
        self.main_tab_title.setObjectName("SectionHeader")
        self.main_tab_title.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(self.main_tab_title)

        header_layout.addStretch()
        right_layout.addWidget(self.header_frame)
        self.subnav_frame = QFrame()
        self.subnav_frame.setStyleSheet("background-color: #FFFFFF; border: none;")
        self.subnav_frame.setFixedHeight(50)
        self.subnav_layout = QVBoxLayout(self.subnav_frame)
        self.subnav_layout.setContentsMargins(40, 0, 40, 0)
        self.subnav_layout.setSpacing(0)
        self.segmented_scroll = QScrollArea()
        self.segmented_scroll.setWidgetResizable(True)
        self.segmented_scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: transparent; }"
        )
        self.segmented_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.segmented_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_wrapper = QWidget()
        self.scroll_wrapper.setStyleSheet("background-color: transparent;")
        self.scroll_wrapper_layout = QHBoxLayout(self.scroll_wrapper)
        self.scroll_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_wrapper_layout.setSpacing(0)
        self.segmented_container = QFrame()
        self.segmented_container.setFixedHeight(50)
        self.segmented_container.setStyleSheet(
            "QFrame { background-color: transparent; border: none; }"
        )
        self.segmented_layout = QHBoxLayout(self.segmented_container)
        self.segmented_layout.setContentsMargins(0, 0, 0, 0)
        self.segmented_layout.setSpacing(10)
        self.scroll_wrapper_layout.addWidget(self.segmented_container)
        self.scroll_wrapper_layout.addStretch()
        self.segmented_scroll.setWidget(self.scroll_wrapper)
        self.subnav_layout.addWidget(self.segmented_scroll)
        right_layout.addWidget(self.subnav_frame)
        self.content_stack = QStackedWidget()

        def apply_shadow(widget):
            s = QGraphicsDropShadowEffect()
            s.setBlurRadius(30)
            s.setColor(QColor(0, 0, 0, 10))
            s.setOffset(0, 6)
            widget.setGraphicsEffect(s)

        self.dash_scroll = QScrollArea()
        self.dash_scroll.setWidgetResizable(True)
        self.dash_scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: #FFFFFF; }"
        )
        self.page_dashboard = QWidget()
        self.page_dashboard.setObjectName("DashboardPage")
        self.page_dashboard.setStyleSheet("""
            QWidget#DashboardPage { background-color: #FFFFFF; }
            QLabel { border: none; background: transparent; } 
            QFrame#DashCard { background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 16px; }
        """)
        dash_main_layout = QVBoxLayout(self.page_dashboard)
        dash_main_layout.setContentsMargins(40, 30, 40, 20)
        dash_main_layout.setSpacing(20)
        proj_name = t1_st1_logic.get_project_name()

        self.welcome_lbl = QLabel(f"Welcome, {proj_name}!")
        self.welcome_lbl.setObjectName("MainTitle")
        dash_main_layout.addWidget(self.welcome_lbl)

        dash_grid = QHBoxLayout()
        dash_grid.setSpacing(25)
        col1_layout = QVBoxLayout()
        col1_layout.setSpacing(20)
        self.ws_card = QFrame()
        self.ws_card.setObjectName("DashCard")
        apply_shadow(self.ws_card)
        ws_vbox = QVBoxLayout(self.ws_card)
        ws_vbox.setContentsMargins(25, 25, 25, 25)
        ws_header = QHBoxLayout()
        ws_header.addWidget(
            QLabel(
                "Project Workspace",
                styleSheet="font-size: 16px; font-weight: bold; color: #1D1D1F;",
            )
        )
        ws_header.addStretch()
        self.set_ws_btn = QPushButton(" Set Workspace")
        self.set_ws_btn.setIcon(qta.icon("mdi.folder-cog-outline", color="#515154"))
        self.set_ws_btn.setStyleSheet(
            "QPushButton { color: #515154; font-weight: bold; border: none; background: transparent; padding: 6px 10px; border-radius: 6px; font-size: 13px; } QPushButton:hover { background-color: #F2F2F7; color: #1D1D1F; }"
        )
        self.set_ws_btn.clicked.connect(self.set_workspace)
        ws_header.addWidget(self.set_ws_btn)
        ws_vbox.addLayout(ws_header)
        initial_path = (
            str(t1_st1_logic.CURRENT_PROJECT_PATH)
            if t1_st1_logic.CURRENT_PROJECT_PATH
            else "No workspace selected."
        )
        self.path_label = QLabel(initial_path)
        if t1_st1_logic.CURRENT_PROJECT_PATH:
            self.path_label.setStyleSheet(
                "font-size: 13px; color: #1D1D1F; font-weight: 600; padding: 12px; background: #F5F5F7; border-radius: 8px; border: 1px solid #D1D1D6;"
            )
        else:
            self.path_label.setStyleSheet(
                "font-size: 13px; color: #8E8E93; padding: 12px; background: #FAFAFA; border-radius: 8px; border: 1px dashed #D1D1D6;"
            )
        self.path_label.setWordWrap(True)
        ws_vbox.addWidget(self.path_label)
        col1_layout.addWidget(self.ws_card)
        self.prog_card = QFrame()
        self.prog_card.setObjectName("DashCard")
        apply_shadow(self.prog_card)
        prog_vbox = QVBoxLayout(self.prog_card)
        prog_vbox.setContentsMargins(25, 25, 25, 25)
        prog_vbox.setSpacing(15)
        prog_vbox.addWidget(
            QLabel(
                "Active Workflows",
                styleSheet="font-size: 16px; font-weight: bold; color: #1D1D1F;",
            )
        )
        self.wf_blocks = {}
        data_prep_block = WorkflowBlock("Data Preparation", 1, "Data Preparation", 0)
        data_prep_block.teleport_requested.connect(self.teleport_from_dashboard)
        prog_vbox.addWidget(data_prep_block)
        self.wf_blocks["data_prep"] = data_prep_block
        tag_block = WorkflowBlock("Tree Annotation", 4, "Tree Annotation", -1)
        tag_block.teleport_requested.connect(self.teleport_from_dashboard)
        prog_vbox.addWidget(tag_block)
        self.wf_blocks["tagging"] = tag_block
        hyphy_block = WorkflowBlock("HyPhy Execution", 5, "HyPhy Execution", -1)
        hyphy_block.teleport_requested.connect(self.teleport_from_dashboard)
        prog_vbox.addWidget(hyphy_block)
        self.wf_blocks["hyphy"] = hyphy_block
        col1_layout.addWidget(self.prog_card)
        col1_layout.addStretch()
        col2_layout = QVBoxLayout()
        col2_layout.setSpacing(20)
        self.res_card = QFrame()
        self.res_card.setObjectName("DashCard")
        apply_shadow(self.res_card)
        res_vbox = QVBoxLayout(self.res_card)
        res_vbox.setContentsMargins(25, 25, 25, 25)
        res_vbox.setSpacing(15)
        res_header = QHBoxLayout()
        res_header.addWidget(
            QLabel(
                "Recent Outputs",
                styleSheet="font-size: 16px; font-weight: bold; color: #1D1D1F;",
            )
        )
        res_header.addStretch()
        self.open_res_btn = QPushButton()
        self.open_res_btn.setIcon(qta.icon("mdi.open-in-new", color="#8E8E93"))
        self.open_res_btn.setToolTip("Open Folder")
        self.open_res_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; padding: 4px; } QPushButton:hover { background: #F2F2F7; border-radius: 4px; }"
        )
        self.open_res_btn.clicked.connect(self._open_results_folder)
        res_header.addWidget(self.open_res_btn)
        res_vbox.addLayout(res_header)
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget { border: none; font-size: 13px; color: #1D1D1F; background: transparent; outline: none; } 
            QListWidget::item { padding: 10px; border-bottom: 1px solid #F5F5F7; }
            QListWidget::item:selected { background-color: #F2F2F7; color: #1D1D1F; font-weight: bold; border-radius: 6px; }
        """)
        self.file_list.itemDoubleClicked.connect(self.open_file)
        res_vbox.addWidget(self.file_list)
        col2_layout.addWidget(self.res_card)
        dash_grid.addLayout(col1_layout, stretch=6)
        dash_grid.addLayout(col2_layout, stretch=4)
        dash_main_layout.addLayout(dash_grid)
        self.dash_scroll.setWidget(self.page_dashboard)
        self.content_stack.addWidget(self.dash_scroll)

        self.page_dataload = StandardizationPage()
        self.page_dataload.applied.connect(self.refresh_dashboard_files)
        self.page_dataload.log_msg.connect(self.add_log)
        if hasattr(self.page_dataload, "file_progress_update"):
            self.page_dataload.file_progress_update.connect(
                self.update_dataprep_progress
            )
        self.scroll_dataload = QScrollArea()
        self.scroll_dataload.setWidgetResizable(True)
        self.scroll_dataload.setStyleSheet(
            "QScrollArea { border: none; background-color: #FFFFFF; }"
        )
        self.scroll_dataload.setWidget(self.page_dataload)
        self.content_stack.addWidget(self.scroll_dataload)

        self.page_pruning = Subtab4PruningUI()
        self.page_pruning.log_msg.connect(self.add_log)
        if hasattr(self.page_pruning, "file_progress_update"):
            self.page_pruning.file_progress_update.connect(
                self.update_dataprep_progress
            )
        self.scroll_pruning = QScrollArea()
        self.scroll_pruning.setWidgetResizable(True)
        self.scroll_pruning.setStyleSheet(
            "QScrollArea { border: none; background-color: #FFFFFF; }"
        )
        self.scroll_pruning.setWidget(self.page_pruning)
        self.content_stack.addWidget(self.scroll_pruning)

        self.page_recon = Subtab5ReconUI()
        self.page_recon.log_msg.connect(self.add_log)
        if hasattr(self.page_recon, "progress_update"):
            self.page_recon.progress_update.connect(self.update_recon_progress)
        self.scroll_recon = QScrollArea()
        self.scroll_recon.setWidgetResizable(True)
        self.scroll_recon.setStyleSheet(
            "QScrollArea { border: none; background-color: #FFFFFF; }"
        )
        self.scroll_recon.setWidget(self.page_recon)
        self.content_stack.addWidget(self.scroll_recon)

        self.page_tagging = Tab2TaggingUI()
        self.page_tagging.log_msg.connect(self.add_log)
        if hasattr(self.page_tagging, "progress_update"):
            self.page_tagging.progress_update.connect(self.update_tagging_progress)
        self.scroll_tagging = QScrollArea()
        self.scroll_tagging.setWidgetResizable(True)
        self.scroll_tagging.setStyleSheet(
            "QScrollArea { border: none; background-color: #FFFFFF; }"
        )
        self.scroll_tagging.setWidget(self.page_tagging)
        self.content_stack.addWidget(self.scroll_tagging)

        self.page_hyphy = Tab3HyPhyUI()
        self.page_hyphy.log_msg.connect(self.add_log)
        self.page_hyphy.request_reconciliation.connect(self.teleport_to_reconciliation)
        if hasattr(self.page_hyphy, "progress_update"):
            self.page_hyphy.progress_update.connect(self.update_hyphy_progress)
        self.scroll_hyphy = QScrollArea()
        self.scroll_hyphy.setWidgetResizable(True)
        self.scroll_hyphy.setStyleSheet(
            "QScrollArea { border: none; background-color: #FFFFFF; }"
        )
        self.scroll_hyphy.setWidget(self.page_hyphy)
        self.content_stack.addWidget(self.scroll_hyphy)

        self.page_summary = Tab4SummaryUI()
        self.page_summary.log_msg.connect(self.add_log)
        self.scroll_summary = QScrollArea()
        self.scroll_summary.setWidgetResizable(True)
        self.scroll_summary.setStyleSheet(
            "QScrollArea { border: none; background-color: #FFFFFF; }"
        )
        self.scroll_summary.setWidget(self.page_summary)
        self.content_stack.addWidget(self.scroll_summary)

        right_layout.addWidget(self.content_stack, stretch=5)

        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(40, 0, 40, 20)

        self.log_console = LogConsole()
        log_layout.addWidget(self.log_console)
        right_layout.addWidget(log_container, stretch=1)
        main_layout.addWidget(right_area)

        self.page_hyphy.wsl_msg.connect(self.log_console.append_wsl_log)
        self.page_hyphy.wsl_clear.connect(self.log_console.clear_wsl_log)

        self.nav_buttons["Dashboard"].clicked.connect(
            lambda: self.switch_page(0, "Dashboard")
        )
        self.nav_buttons["Data Preparation"].clicked.connect(
            lambda: self.switch_page(1, "Data Preparation")
        )
        self.nav_buttons["Tree Annotation"].clicked.connect(
            lambda: self.switch_page(4, "Tree Annotation")
        )
        self.nav_buttons["HyPhy Execution"].clicked.connect(
            lambda: self.switch_page(5, "HyPhy Execution")
        )
        self.nav_buttons["Results Summary"].clicked.connect(
            lambda: self.switch_page(6, "Results Summary")
        )

        self.switch_page(0, "Dashboard")

    def teleport_from_dashboard(self, main_idx, main_name, sub_idx):
        self.switch_page(main_idx, main_name)
        if sub_idx >= 0:
            self.switch_subtab(sub_idx)

    def teleport_to_reconciliation(self):
        self.add_log(
            "[Process] Teleporting to Data Preparation tab to fix mismatches..."
        )
        self.switch_page(1, "Data Preparation")
        self.switch_subtab(2)

    def set_workspace(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Project Workspace"
        )
        if folder:
            self.path_label.setText(folder)
            self.path_label.setStyleSheet(
                "font-size: 13px; color: #1D1D1F; font-weight: 600; padding: 12px; background: #F5F5F7; border-radius: 8px; border: 1px solid #D1D1D6;"
            )
            t1_st1_logic.set_project_path(folder)
            self.add_log(f"[Success] Workspace set to: {folder}")
            self.refresh_dashboard_files()

    def refresh_dashboard_files(self):
        self.file_list.clear()

        if not t1_st1_logic.CURRENT_PROJECT_PATH:
            return

        res_path = t1_st1_logic.CURRENT_PROJECT_PATH / "Results"
        rep_path = t1_st1_logic.CURRENT_PROJECT_PATH / "Reports"

        all_files = []
        for p in [res_path, rep_path]:
            if p and p.exists():
                for root, dirs, files in os.walk(p):
                    for f in files:
                        if not f.startswith("~$") and not f.endswith(".json"):
                            try:
                                full_path = Path(root) / f
                                mtime = os.path.getmtime(full_path)
                                all_files.append((mtime, Path(root), f))
                            except Exception:
                                continue

        all_files.sort(key=lambda x: x[0], reverse=True)

        for _, path, name in all_files:
            name_lower = name.lower()
            if name_lower.endswith(".csv"):
                icon = "mdi.file-delimited-outline"
            elif name_lower.endswith((".nwk", ".tre", ".tree")):
                icon = "mdi.file-tree"
            elif name_lower.endswith((".fas", ".fasta", ".fa")):
                icon = "mdi.file-document-outline"
            else:
                icon = "mdi.file-table-outline"

            item = QListWidgetItem(qta.icon(icon, color="#8E8E93"), name)
            item.setData(Qt.UserRole, str(path / name))
            self.file_list.addItem(item)

        if self.file_list.count() == 0:
            self.file_list.addItem(
                QListWidgetItem("No outputs yet. Run a pipeline to see results here!")
            )

    def _open_results_folder(self):
        res_path = t1_st1_logic.get_results_path()
        if res_path and os.path.exists(res_path):
            self._open_path_cross_platform(str(res_path))

    def open_file(self, item):
        file_path = item.data(Qt.UserRole)
        if file_path and os.path.exists(file_path):
            self._open_path_cross_platform(file_path)

    def _open_path_cross_platform(self, path):
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.call(["open", path])
            else:
                subprocess.call(["xdg-open", path])
        except Exception as e:
            self.add_log(f"[Error] Failed to open path: {str(e)}")

    def update_dataprep_progress(self, filename, percent, status_text):
        self.wf_blocks["data_prep"].update_file_progress(filename, percent, status_text)

    def update_recon_progress(self, filename, percent, status_text):
        self.wf_blocks["data_prep"].update_file_progress(filename, percent, status_text)

    def update_tagging_progress(self, filename, percent, status_text):
        self.wf_blocks["tagging"].update_file_progress(filename, percent, status_text)

    def update_hyphy_progress(self, filename, percent, status_text):
        self.wf_blocks["hyphy"].update_file_progress(filename, percent, status_text)

    def switch_page(self, index, name):
        if index == 0:
            self.content_stack.setCurrentIndex(0)
            self.refresh_dashboard_files()
            self.update_subtabs(name, active_idx=0, show_subtabs=False)
        elif index == 1:
            self.content_stack.setCurrentIndex(1)
            self.update_subtabs(name, active_idx=0, show_subtabs=True)
        elif index == 4:
            self.content_stack.setCurrentIndex(4)
            self.update_subtabs(name, active_idx=0, show_subtabs=False)
        elif index == 5:
            self.content_stack.setCurrentIndex(5)
            self.update_subtabs(name, active_idx=0, show_subtabs=False)
        elif index == 6:
            self.content_stack.setCurrentIndex(6)
            self.update_subtabs(name, active_idx=0, show_subtabs=False)

        self.log_console.set_wsl_mode(index == 5)

        for btn_name, btn in self.nav_buttons.items():
            clean_name = btn_name.strip()
            if clean_name == name.strip():
                btn.setStyleSheet(
                    "QPushButton { text-align: left; padding: 10px 15px; font-size: 14px; font-weight: bold; color: #FFFFFF; background-color: #1D1D1F; border-radius: 8px; border: none; }"
                )
                btn.setIcon(qta.icon(self.icon_map[clean_name], color="#FFFFFF"))
            else:
                btn.setStyleSheet(
                    "QPushButton { text-align: left; padding: 10px 15px; font-size: 14px; font-weight: 600; color: #1D1D1F; background-color: transparent; border-radius: 8px; border: none; } QPushButton:hover { background-color: #E5E5EA; }"
                )
                btn.setIcon(qta.icon(self.icon_map[clean_name], color="#515154"))

    def update_subtabs(self, main_tab_name, active_idx=0, show_subtabs=True):
        clean_name = main_tab_name.strip()
        self.main_tab_title.setText(clean_name)
        icon_name = self.icon_map.get(clean_name, "mdi.graph-outline")
        self.main_tab_icon.setPixmap(
            qta.icon(icon_name, color="#1D1D1F").pixmap(18, 18)
        )
        while self.segmented_layout.count():
            item = self.segmented_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.spacerItem():
                pass
        if not show_subtabs:
            self.subnav_frame.hide()
        else:
            self.subnav_frame.show()
            tabs = [
                "Species Label Standardization",
                "Tree Pruning",
                "Data Reconciliation",
            ]
            for i, sub in enumerate(tabs):
                btn = QPushButton(sub)
                btn.setFixedHeight(50)
                btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
                if i == active_idx:
                    style = """
                        QPushButton { background-color: transparent; color: #1D1D1F; font-weight: 800; font-size: 14px; border: none; border-bottom: 3px solid #1D1D1F; border-radius: 0px; padding: 10px 15px 7px 15px; }
                    """
                else:
                    style = """
                        QPushButton { background-color: transparent; color: #8E8E93; font-weight: 600; font-size: 14px; border: none; border-radius: 0px; padding: 10px 15px; } 
                        QPushButton:hover { color: #1D1D1F; background-color: #FAFAFA; }
                    """
                btn.setStyleSheet(style)
                btn.clicked.connect(
                    lambda checked=False, idx=i: self.switch_subtab(idx)
                )
                self.segmented_layout.addWidget(btn)
            self.segmented_layout.addStretch()

    def switch_subtab(self, index):
        self.content_stack.setCurrentIndex(index + 1)
        for i in range(self.segmented_layout.count()):
            btn = self.segmented_layout.itemAt(i).widget()
            if btn:
                if i == index:
                    style = """
                        QPushButton { background-color: transparent; color: #1D1D1F; font-weight: 800; font-size: 14px; border: none; border-bottom: 3px solid #1D1D1F; border-radius: 0px; padding: 10px 15px 7px 15px; }
                    """
                else:
                    style = """
                        QPushButton { background-color: transparent; color: #8E8E93; font-weight: 600; font-size: 14px; border: none; border-radius: 0px; padding: 10px 15px; } 
                        QPushButton:hover { color: #1D1D1F; background-color: #FAFAFA; }
                    """
                btn.setStyleSheet(style)

    def add_log(self, msg):
        self.log_console.append_log(msg)

    def closeEvent(self, event):
        if t1_st1_logic.CURRENT_PROJECT_PATH:
            self.log_console.export_master_log(t1_st1_logic.CURRENT_PROJECT_PATH)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    light_palette = QPalette()
    light_palette.setColor(QPalette.Window, QColor("#FFFFFF"))
    light_palette.setColor(QPalette.WindowText, QColor("#1D1D1F"))
    light_palette.setColor(QPalette.Base, QColor("#FFFFFF"))
    light_palette.setColor(QPalette.AlternateBase, QColor("#F2F2F7"))
    light_palette.setColor(QPalette.ToolTipBase, QColor("#FFFFFF"))
    light_palette.setColor(QPalette.ToolTipText, QColor("#1D1D1F"))
    light_palette.setColor(QPalette.Text, QColor("#1D1D1F"))
    light_palette.setColor(QPalette.Button, QColor("#F2F2F7"))
    light_palette.setColor(QPalette.ButtonText, QColor("#1D1D1F"))
    light_palette.setColor(QPalette.BrightText, QColor("#FFFFFF"))
    light_palette.setColor(QPalette.Highlight, QColor("#0071E3"))
    light_palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(light_palette)

    global_stylesheet = """
    QMainWindow, QDialog, QFileDialog, QMessageBox { 
        background-color: #FFFFFF; 
        font-family: 'Roboto', -apple-system, 'Segoe UI', sans-serif;
        color: #1D1D1F;
    }
    QFileDialog, QFileDialog * {
        background-color: #FFFFFF;
        color: #1D1D1F;
    }
    QFileDialog QTreeView, QFileDialog QListView, QFileDialog QTableView {
        background-color: #FFFFFF;
        color: #1D1D1F;
        selection-background-color: #0071E3;
        selection-color: #FFFFFF;
    }
    QFileDialog QHeaderView::section {
        background-color: #F2F2F7;
        color: #1D1D1F;
        border: none;
        border-right: 1px solid #D1D1D6;
        border-bottom: 1px solid #D1D1D6;
        padding: 4px;
    }
    QFileDialog QPushButton, QFileDialog QComboBox, QFileDialog QLineEdit {
        background-color: #F5F5F7;
        color: #1D1D1F;
        border: 1px solid #D1D1D6;
        border-radius: 4px;
    }
    QLabel#MainTitle { font-size: 24px; font-weight: 800; color: #1D1D1F; background: transparent; border: none; }
    QLabel#SectionHeader { font-size: 20px; font-weight: 700; color: #1D1D1F; background: transparent; border: none; }
    QLabel#SubHeader { font-size: 18px; font-weight: 500; color: #1D1D1F; background: transparent; border: none; }
    QLabel#SubText { font-size: 14px; font-weight: 400; color: #8E8E93; background: transparent; border: none; }
    QScrollBar:vertical { border: none; background: transparent; width: 8px; margin: 0px; }
    QScrollBar::handle:vertical { background-color: #D1D1D6; border-radius: 4px; min-height: 20px; }
    QScrollBar::handle:vertical:hover { background-color: #8E8E93; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { border: none; background: none; height: 0px; }
    QScrollBar:horizontal { border: none; background: transparent; height: 8px; margin: 0px; }
    QScrollBar::handle:horizontal { background-color: #D1D1D6; border-radius: 4px; min-width: 20px; }
    QScrollBar::handle:horizontal:hover { background-color: #8E8E93; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { border: none; background: none; width: 0px; }
    """
    app.setStyleSheet(global_stylesheet)

    startup_dialog = StartupDialog()
    if startup_dialog.exec() == QDialog.Accepted:
        window = HyphlowMain()
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
