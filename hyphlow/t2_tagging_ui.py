import os
import traceback
from pathlib import Path

import pandas as pd

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFrame,
    QLabel,
    QComboBox,
    QTextBrowser,
    QSizePolicy,
    QSplitter,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QScrollArea,
    QMessageBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap
import qtawesome as qta

from hyphlow import common_utils, t1_st1_logic, t2_tagging_logic
from hyphlow.common_ui import (
    UnifiedDropZone,
    PrimaryButton,
    FlowLayout,
    FlowContainer,
    open_path,
    message_box,
)

# ================================================================= shared styles

# Qt stylesheets are CSS, so their braces collide with f-strings and str.format.
# Styles are therefore assembled by concatenation. Only the ones this file reuses
# are named here; a colour or style that appears once stays where it is used,
# since naming it would add a lookup without removing a decision.
#
# The colours are not shared with t2_tagging_logic, which defines its own for the
# figures. A button and a branch are free to diverge, and one constant for both
# would make that impossible to express.

COLOR_BORDER = "#D1D1D6"
COLOR_FILL = "#F2F2F7"
COLOR_INACTIVE = "#E5E5EA"
COLOR_SURFACE = "#FFFFFF"
COLOR_TEXT = "#1D1D1F"
COLOR_TEXT_DISABLED = "#A2A2A6"
COLOR_WARNING = "#FF3B30"
COLOR_WARNING_FILL = "#FFECEB"

# An icon button that should read as a bare glyph. Twelve call sites.
STYLE_FLAT = "border: none; background: transparent;"
STYLE_TRANSPARENT = "background-color: transparent;"

# A small bordered button, used across the viewer toolbar.
STYLE_SMALL_BUTTON = (
    "QPushButton { background-color: "
    + COLOR_SURFACE
    + "; color: "
    + COLOR_TEXT
    + "; font-weight: bold; font-size: 11px; border-radius: 6px; "
    "border: 1px solid " + COLOR_BORDER + "; padding: 6px 10px; } "
    "QPushButton:hover { background-color: " + COLOR_FILL + "; } "
    "QPushButton:disabled { color: "
    + COLOR_TEXT_DISABLED
    + "; border-color: "
    + COLOR_INACTIVE
    + "; }"
)

# The pill that reports a failed step.
STYLE_ERROR_PILL = (
    "background-color: " + COLOR_WARNING_FILL + "; color: " + COLOR_WARNING + "; "
    "border-radius: 6px; font-weight: 800; font-size: 11px; padding: 4px 8px;"
)


class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ImagePopupDialog(QDialog):
    def __init__(self, parent=None, frames=[], current_step=0):
        super().__init__(parent)
        self.setStyleSheet("QDialog { background-color: #FFFFFF; }")
        self.frames = frames
        self.current_step = current_step
        self.parent_ui = parent
        self.setWindowTitle("Zoomed Evolutionary Tree")
        self.resize(1100, 800)
        layout = QVBoxLayout(self)
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.img_label, stretch=1)

        nav_layout = QHBoxLayout()
        self.btn_prev = QPushButton(" Prev Step")
        self.btn_prev.setIcon(qta.icon("mdi.chevron-left", color="#1D1D1F"))
        self.btn_prev.setStyleSheet(
            "QPushButton { "
            "background-color: #E5E5EA; font-weight: bold; font-size: 13px; "
            "color: #1D1D1F; padding: 10px 20px; border-radius: 8px; border: none; "
            "} "
            "QPushButton:disabled { color: #A2A2A6; }"
        )
        self.btn_prev.clicked.connect(lambda: self.change_step(-1))

        self.lbl_step = QLabel()
        self.lbl_step.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1D1D1F;"
        )
        self.lbl_step.setAlignment(Qt.AlignCenter)

        self.btn_next = QPushButton("Next Step ")
        self.btn_next.setIcon(qta.icon("mdi.chevron-right", color="#1D1D1F"))
        self.btn_next.setLayoutDirection(Qt.RightToLeft)
        self.btn_next.setStyleSheet(
            "QPushButton { "
            "background-color: #E5E5EA; font-weight: bold; font-size: 13px; "
            "color: #1D1D1F; padding: 10px 20px; border-radius: 8px; border: none; "
            "} "
            "QPushButton:disabled { color: #A2A2A6; }"
        )
        self.btn_next.clicked.connect(lambda: self.change_step(1))

        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.lbl_step, stretch=1)
        nav_layout.addWidget(self.btn_next)
        layout.addLayout(nav_layout)
        self.update_ui()

    def change_step(self, delta):
        self.current_step += delta
        self.update_ui()
        if self.parent_ui:
            self.parent_ui.set_step_absolute(self.current_step)

    def update_ui(self):
        self.btn_prev.setEnabled(self.current_step > 0)
        self.btn_next.setEnabled(self.current_step < t2_tagging_logic.N_STEPS - 1)
        labels = [
            "Step 1: Fitch",
            "Step 2: ML",
            "Step 3: Consensus",
        ]
        self.lbl_step.setText(labels[self.current_step])
        if self.frames and os.path.exists(self.frames[self.current_step]):
            pixmap = QPixmap(self.frames[self.current_step])
            self.img_label.setPixmap(
                pixmap.scaled(
                    self.img_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )

    def resizeEvent(self, event):
        self.update_ui()
        super().resizeEvent(event)


class AlgoSettingsDialog(QDialog):
    def __init__(self, parent=None, current_params=None):
        super().__init__(parent)
        self.setWindowTitle("Algorithm Parameters")
        self.setMinimumWidth(420)
        self.setFixedSize(300, 200)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; }
            QLabel { color: #1D1D1F; border: none; background: transparent; }
            QDoubleSpinBox {
                background-color: #FFFFFF; color: #1D1D1F; border: 1px solid #D1D1D6;
                border-radius: 4px; padding: 4px;
            }
        """)
        self.params = (
            current_params
            if current_params
            else dict(t2_tagging_logic.DEFAULT_ALGO_PARAMS)
        )
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.setSpacing(15)

        self.spin_mu = QDoubleSpinBox()
        self.spin_mu.setRange(0.1, 100.0)
        self.spin_mu.setSingleStep(0.1)
        cur = self.params["felsenstein_mu"]
        is_auto = str(cur).lower() == "auto"
        self.spin_mu.setValue(1.0 if is_auto else float(cur))
        self.spin_mu.setEnabled(not is_auto)

        self.chk_mu_auto = QCheckBox("Estimate from data (recommended)")
        self.chk_mu_auto.setChecked(is_auto)
        self.chk_mu_auto.toggled.connect(lambda on: self.spin_mu.setEnabled(not on))
        self.chk_mu_auto.setStyleSheet(
            "QCheckBox { background: transparent; padding: 0px; border: none; "
            "color: #515154; font-weight: 600; font-size: 12px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; "
            "border: 1px solid #C7C7CC; border-radius: 4px; background: white; }"
            "QCheckBox::indicator:checked { background: #1D1D1F; "
            "border: 1px solid #1D1D1F; }"
        )
        form_layout.addRow(
            QLabel("Felsenstein μ:", styleSheet="font-weight: 600; color: #515154;"),
            self.spin_mu,
        )
        form_layout.addRow(QLabel(""), self.chk_mu_auto)
        layout.addLayout(form_layout)
        btn_layout = QHBoxLayout()
        save_btn = QPushButton(" Save Settings")
        save_btn.setIcon(qta.icon("mdi.check", color="white"))
        save_btn.setStyleSheet(
            "QPushButton { "
            "background-color: #1D1D1F; color: white; padding: 8px 16px; "
            "border-radius: 8px; font-weight: bold; border: none; "
            "} "
            "QPushButton:hover { background-color: #333333; }"
        )
        save_btn.clicked.connect(self.save_and_close)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def save_and_close(self):
        self.params["felsenstein_mu"] = (
            "auto" if self.chk_mu_auto.isChecked() else self.spin_mu.value()
        )
        self.accept()


class TaggingThread(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, csv_file, nwk_files, tagged_data, target_vars_str, algo_params):
        super().__init__()
        self.csv_file = csv_file
        self.nwk_files = nwk_files
        self.tagged_data = tagged_data
        self.target_vars_str = target_vars_str
        self.algo_params = algo_params

    def run(self):
        try:
            results = {}
            for nwk in self.nwk_files:
                res = t2_tagging_logic.run_consensus_tagging(
                    nwk, self.tagged_data, self.target_vars_str, self.algo_params
                )
                res["original_nwk"] = nwk
                if res.get("status") == "success":
                    results[res["session_name"]] = res
                else:
                    results[nwk] = res
            self.finished.emit({"status": "success", "results": results})
        except Exception as e:
            self.finished.emit(
                {
                    "status": "error",
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                }
            )


class TraitRowWidget(QWidget):
    def __init__(self, csv_file, delete_callback, change_callback):
        super().__init__()
        self.csv_file = csv_file
        self.delete_callback = delete_callback
        self.change_callback = change_callback
        self.pills = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 5)

        top_bar = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #D1D1D6; border-radius: 6px; padding: 4px 10px;
                background: #FFFFFF; font-weight: 500; font-size: 13px; color: #1D1D1F;
                min-width: 150px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #FFFFFF; selection-background-color: #E5E5EA;
                selection-color: #1D1D1F;
            }
        """)
        self.combo.addItems(t2_tagging_logic.get_csv_headers(self.csv_file))
        self.combo.currentIndexChanged.connect(self.load_pills)
        top_bar.addWidget(self.combo)

        btn_del = QPushButton()
        btn_del.setIcon(qta.icon("mdi.close", color="#8E8E93"))
        btn_del.setFixedSize(26, 26)
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setStyleSheet(
            "QPushButton { "
            "border: none; background: transparent; border-radius: 13px; "
            "} "
            "QPushButton:hover { background: #FFECEB; }"
        )
        btn_del.clicked.connect(lambda: self.delete_callback(self))
        top_bar.addWidget(btn_del)
        layout.addLayout(top_bar)

        self.pill_container = FlowContainer()
        self.pill_container.setStyleSheet("background: transparent; margin-top: 5px;")

        self.pill_layout = FlowLayout(self.pill_container, margin=0, spacing=8)
        layout.addWidget(self.pill_container)
        self.load_pills()

    def load_pills(self):
        while self.pill_layout.count():
            item = self.pill_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self.pills.clear()

        vals = t2_tagging_logic.get_unique_values(
            self.csv_file, self.combo.currentText()
        )
        for val in vals:
            chk = QCheckBox(str(val))
            chk.setStyleSheet("""
                QCheckBox {
                    background: #F2F2F7; padding: 6px 14px; border-radius: 14px;
                    color: #515154; font-weight: 600; font-size: 12px;
                    border: 1px solid #E5E5EA;
                }
                QCheckBox::indicator { width: 0px; height: 0px; }
                QCheckBox:checked {
                    background: #1D1D1F; color: #FFFFFF; border: 1px solid #1D1D1F;
                }
                QCheckBox:hover:!checked { background: #E5E5EA; }
            """)
            chk.toggled.connect(lambda _, c=chk: self.change_callback())
            self.pills.append(chk)
            self.pill_layout.addItem(self.pill_layout.addWidget(chk))

        self.change_callback()

        if self.pill_container.layout():
            h = self.pill_container.layout().heightForWidth(self.pill_container.width())
            self.pill_container.setMinimumHeight(h)

    def get_selected(self):
        return self.combo.currentText(), [p.text() for p in self.pills if p.isChecked()]


class Tab2TaggingUI(QWidget):
    log_msg = pyqtSignal(str)
    progress_update = pyqtSignal(str, int, str)

    def __init__(self):
        super().__init__()
        self.csv_file = None
        self.nwk_files = []
        # Read from the logic module rather than restated here. The two had
        # already drifted: n_simulations was 1000 in this copy and 5000 there,
        # so every GUI run used the value the stability test rejected.
        self.algo_params = dict(t2_tagging_logic.DEFAULT_ALGO_PARAMS)
        self.batch_results = {}
        self.current_step = t2_tagging_logic.N_STEPS - 1
        self.trait_rows = []
        self.current_batch_labels = {}
        self._setup_ui()

    def _setup_ui(self):
        master_layout = QVBoxLayout(self)
        master_layout.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet(STYLE_TRANSPARENT)

        self.global_scroll = QScrollArea()
        self.global_scroll.setWidgetResizable(True)
        self.global_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        scroll_content = QWidget()
        scroll_content.setStyleSheet(STYLE_TRANSPARENT)
        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(20)

        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(4)
        header_lbl = QLabel("Tree Annotation")
        header_lbl.setObjectName("SectionHeader")
        header_lbl.setStyleSheet(STYLE_FLAT)
        header_vbox.addWidget(header_lbl)

        desc_lbl = QLabel(
            "Performs automatic foreground branch annotation by identifying\n"
            "consensus internal branches using CSV trait data."
        )
        desc_lbl.setObjectName("SubText")
        desc_lbl.setStyleSheet(STYLE_FLAT)
        header_vbox.addWidget(desc_lbl)
        main_layout.addLayout(header_vbox)

        self.input_card = QFrame()
        self.input_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.input_card.setStyleSheet(
            "QFrame { "
            "background-color: #FFFFFF; border: 1px solid #E5E5EA; "
            "border-radius: 10px; "
            "}"
        )
        ic_layout = QVBoxLayout(self.input_card)
        ic_layout.setContentsMargins(15, 10, 15, 15)
        ic_layout.setSpacing(10)

        input_header = QHBoxLayout()
        lbl_input_title = QLabel("Data Input")
        lbl_input_title.setObjectName("SubHeader")
        lbl_input_title.setStyleSheet(STYLE_FLAT)
        input_header.addWidget(lbl_input_title)

        input_header.addStretch()
        self.btn_toggle_input = QPushButton()
        self.btn_toggle_input.setIcon(qta.icon("mdi.chevron-up", color="#1D1D1F"))
        self.btn_toggle_input.setStyleSheet(STYLE_FLAT)
        self.btn_toggle_input.setCursor(Qt.PointingHandCursor)
        input_header.addWidget(self.btn_toggle_input)
        ic_layout.addLayout(input_header)

        self.input_content_area = QFrame()
        self.input_content_area.setStyleSheet("background: transparent; border: none;")
        input_content_layout = QVBoxLayout(self.input_content_area)
        input_content_layout.setContentsMargins(0, 0, 0, 0)

        upload_layout = QHBoxLayout()
        upload_layout.setSpacing(15)

        self.dz_csv = UnifiedDropZone(
            [".csv"],
            "Master Alignment (CSV)",
            show_dropdown=True,
            file_type="csv",
            show_gene_input=False,
        )
        self.dz_csv.files_updated.connect(self.handle_csv_drop)
        if hasattr(self.dz_csv, "scroll_area"):
            self.dz_csv.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.dz_csv.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.dz_csv.scroll_area.setWidgetResizable(True)
            self.dz_csv.scroll_area.setMaximumHeight(130)

        upload_layout.addWidget(self.dz_csv, stretch=1)

        self.dz_nwk = UnifiedDropZone(
            [".nwk", ".tre", ".tree"],
            "Target Phylogeny (NWK)",
            show_dropdown=False,
            file_type="nwk",
            show_gene_input=False,
        )
        self.dz_nwk.files_updated.connect(self.handle_nwk_drop)

        if hasattr(self.dz_nwk, "scroll_area"):
            self.dz_nwk.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.dz_nwk.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.dz_nwk.scroll_area.setWidgetResizable(True)
            self.dz_nwk.scroll_area.setMaximumHeight(130)

        upload_layout.addWidget(self.dz_nwk, stretch=1)

        input_content_layout.addLayout(upload_layout)
        ic_layout.addWidget(self.input_content_area)

        self.btn_toggle_input.clicked.connect(
            lambda: self.toggle_card(self.input_content_area, self.btn_toggle_input)
        )

        main_layout.addWidget(self.input_card)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet(
            "QSplitter::handle { background-color: #F2F2F7; width: 2px; }"
        )

        left_container = QFrame()
        left_container.setStyleSheet(STYLE_FLAT)
        left_panel = QVBoxLayout(left_container)
        left_panel.setContentsMargins(0, 10, 20, 0)
        left_panel.setSpacing(20)

        target_box = QFrame()
        target_box.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 10px;"
        )
        self.tb_layout = QVBoxLayout(target_box)
        lbl_target_traits = QLabel("Set Target Traits")
        lbl_target_traits.setObjectName("SubHeader")
        lbl_target_traits.setStyleSheet(STYLE_FLAT)
        self.tb_layout.addWidget(lbl_target_traits)

        self.trait_container = QVBoxLayout()
        self.tb_layout.addLayout(self.trait_container)

        self.btn_add_trait = QPushButton(" Add Trait Category")
        self.btn_add_trait.setIcon(qta.icon("mdi.plus", color="#0071E3"))
        self.btn_add_trait.setCursor(Qt.PointingHandCursor)
        self.btn_add_trait.setStyleSheet(
            "QPushButton { "
            "background-color: transparent; color: #0071E3; font-weight: bold; "
            "font-size: 13px; border: none; padding: 8px; text-align: left; "
            "} "
            "QPushButton:hover { color: #005BB5; }"
        )
        self.btn_add_trait.clicked.connect(self.add_trait_row)
        self.btn_add_trait.hide()
        self.tb_layout.addWidget(self.btn_add_trait)
        left_panel.addWidget(target_box)

        algo_box = QFrame()
        algo_box.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 10px;"
        )
        ab_layout = QVBoxLayout(algo_box)
        algo_header_layout = QHBoxLayout()
        lbl_algo_params = QLabel("Algorithm Parameters")
        lbl_algo_params.setObjectName("SubHeader")
        lbl_algo_params.setStyleSheet(STYLE_FLAT)
        algo_header_layout.addWidget(lbl_algo_params)
        algo_header_layout.addStretch()

        self.btn_settings = QPushButton(" Setup")
        self.btn_settings.setIcon(qta.icon("mdi.cog", color="#515154"))
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setStyleSheet(
            "QPushButton { "
            "background-color: #FFFFFF; border: 1px solid #D1D1D6; "
            "border-radius: 6px; padding: 4px 10px; font-size: 12px; "
            "font-weight: bold; color: #515154; "
            "} "
            "QPushButton:hover { background-color: #F2F2F7; }"
        )
        self.btn_settings.clicked.connect(self.open_settings)
        algo_header_layout.addWidget(self.btn_settings)
        ab_layout.addLayout(algo_header_layout)

        self.lbl_algo_desc = QLabel()
        self.lbl_algo_desc.setStyleSheet(
            "color: #515154; font-size: 12px; font-weight: 500; border: none;"
            "background: transparent; line-height: 1.5;"
        )
        self.update_algo_desc()
        ab_layout.addWidget(self.lbl_algo_desc)
        left_panel.addWidget(algo_box)

        self.run_btn = PrimaryButton(" Run Auto-Consensus Annotation", "mdi.play")
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.start_tagging)
        left_panel.addWidget(self.run_btn)

        progress_card = QFrame()
        progress_card.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 10px;"
        )
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(15, 15, 15, 15)
        progress_layout.setSpacing(10)

        table_title_lbl = QLabel("Annotation Status")
        table_title_lbl.setObjectName("SubHeader")
        table_title_lbl.setStyleSheet(STYLE_FLAT)
        progress_layout.addWidget(table_title_lbl)

        self.status_table = QTableWidget(0, 3)
        self.status_table.setHorizontalHeaderLabels(
            ["File Name", "Target Trait", "Status"]
        )

        header = self.status_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.status_table.setColumnWidth(2, 90)

        self.status_table.verticalHeader().setVisible(False)
        self.status_table.verticalHeader().setDefaultSectionSize(36)
        self.status_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.status_table.setFocusPolicy(Qt.NoFocus)
        self.status_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #E5E5EA; border-radius: 8px;
                background-color: #FFFFFF; outline: none; gridline-color: transparent;
            }
            QTableWidget::item {
                padding: 4px; border-bottom: 1px solid #F2F2F7; font-size: 11px;
                color: #1D1D1F;
            }
            QHeaderView::section {
                background-color: #FAFAFA; border: none;
                border-bottom: 1px solid #E5E5EA; font-size: 11px; font-weight: bold;
                color: #8E8E93; height: 28px; padding-left: 5px;
            }
        """)
        progress_layout.addWidget(self.status_table, stretch=1)
        left_panel.addWidget(progress_card, stretch=1)

        self.splitter.addWidget(left_container)

        right_panel = QFrame()
        right_panel.setStyleSheet(STYLE_FLAT)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 0, 0)
        right_layout.setSpacing(20)

        top_left_card = QFrame()
        top_left_card.setStyleSheet(
            "QFrame { "
            "background-color: #FFFFFF; border: 1px solid #E5E5EA; "
            "border-radius: 10px; "
            "}"
        )
        top_left_vbox = QVBoxLayout(top_left_card)
        top_left_vbox.setContentsMargins(15, 15, 15, 15)
        top_left_vbox.setSpacing(12)

        viewer_header = QHBoxLayout()
        lbl_viewing_session = QLabel("Preview:")
        lbl_viewing_session.setObjectName("SubHeader")
        lbl_viewing_session.setStyleSheet(STYLE_FLAT)
        viewer_header.addWidget(lbl_viewing_session)
        self.combo_viewer = QComboBox()
        self.combo_viewer.setStyleSheet("""
            QComboBox {
                border: 1px solid #D1D1D6; border-radius: 6px; padding: 6px 12px;
                background: #FFFFFF; font-weight: 500; font-size: 13px; color: #1D1D1F;
                min-width: 150px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding; subcontrol-position: top right;
                width: 30px; border-left: 1px solid #E5E5EA;
                background-color: transparent;
            }
            QComboBox::down-arrow {
                width: 0; height: 0; border-left: 4px solid transparent;
                border-right: 4px solid transparent; border-top: 5px solid #8E8E93;
                margin-top: 1px;
            }
            QComboBox QAbstractItemView {
                background: #FFFFFF; border: 1px solid #E5E5EA;
                selection-background-color: #F2F2F7; selection-color: #1D1D1F;
                outline: none;
            }
        """)
        self.combo_viewer.currentIndexChanged.connect(self.update_viewer)
        self.combo_viewer.setEnabled(False)
        viewer_header.addWidget(self.combo_viewer)

        self.btn_open_img_folder = QPushButton(" Open Folder")
        self.btn_open_img_folder.setIcon(
            qta.icon("mdi.folder-open-outline", color="#0071E3")
        )
        self.btn_open_img_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_img_folder.setStyleSheet(
            "QPushButton { "
            "color: #0071E3; font-weight: bold; font-size: 11px; border: none; "
            "background: transparent; "
            "} "
            "QPushButton:hover { color: #005BB5; }"
        )
        self.btn_open_img_folder.setEnabled(False)
        self.btn_open_img_folder.clicked.connect(
            lambda: hasattr(self, "current_res")
            and open_path(self.current_res["session_dir"])
        )
        viewer_header.addWidget(self.btn_open_img_folder)
        viewer_header.addStretch()
        top_left_vbox.addLayout(viewer_header)

        self.nav_widget = QWidget()
        self.nav_widget.setStyleSheet(STYLE_FLAT)
        nav_layout = QHBoxLayout(self.nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_prev = QPushButton(" Prev Step")
        self.btn_prev.setIcon(qta.icon("mdi.chevron-left", color="#1D1D1F"))
        self.btn_prev.setCursor(Qt.PointingHandCursor)
        self.btn_prev.setStyleSheet(
            "QPushButton { "
            "background-color: #F2F2F7; font-weight: bold; font-size: 12px; "
            "color: #1D1D1F; border-radius: 8px; padding: 8px 15px; border: none; "
            "} "
            "QPushButton:hover { background-color: #E5E5EA; } "
            "QPushButton:disabled { color: #A2A2A6; }"
        )
        self.btn_prev.clicked.connect(lambda: self.change_step(-1))
        self.btn_prev.setEnabled(False)

        self.lbl_step_title = QLabel("Step 5: Final Strict Consensus")
        self.lbl_step_title.setStyleSheet(
            "font-weight: 800; color: #A2A2A6; font-size: 13px; border: none;"
            "background: transparent;"
        )
        self.lbl_step_title.setAlignment(Qt.AlignCenter)

        self.btn_next = QPushButton("Next Step ")
        self.btn_next.setIcon(qta.icon("mdi.chevron-right", color="#1D1D1F"))
        self.btn_next.setLayoutDirection(Qt.RightToLeft)
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.setStyleSheet(
            "QPushButton { "
            "background-color: #F2F2F7; font-weight: bold; font-size: 12px; "
            "color: #1D1D1F; border-radius: 8px; padding: 8px 15px; border: none; "
            "} "
            "QPushButton:hover { background-color: #E5E5EA; } "
            "QPushButton:disabled { color: #A2A2A6; }"
        )
        self.btn_next.clicked.connect(lambda: self.change_step(1))
        self.btn_next.setEnabled(False)

        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.lbl_step_title, stretch=1)
        nav_layout.addWidget(self.btn_next)
        top_left_vbox.addWidget(self.nav_widget)

        self.img_preview = ClickableLabel("Click the box to zoom in.")
        self.img_preview.setAlignment(Qt.AlignCenter)
        self.img_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.img_preview.setStyleSheet(
            "background-color: #FAFAFA; border: 2px dashed #D1D1D6;"
            "border-radius: 10px; color: #8E8E93; font-weight: bold; font-size: 13px;"
        )
        self.img_preview.setMinimumHeight(240)
        self.img_preview.setCursor(Qt.PointingHandCursor)
        self.img_preview.clicked.connect(self.open_zoomed_popup)
        top_left_vbox.addWidget(self.img_preview, stretch=1)

        action_layout = QHBoxLayout()
        btn_style = STYLE_SMALL_BUTTON

        self.btn_open_report = QPushButton(" Report CSV")
        self.btn_open_report.setIcon(
            qta.icon("mdi.file-document-outline", color="#1D1D1F")
        )
        self.btn_open_report.setCursor(Qt.PointingHandCursor)
        self.btn_open_report.setStyleSheet(btn_style)
        self.btn_open_report.setEnabled(False)
        self.btn_open_report.clicked.connect(
            lambda: hasattr(self, "current_res")
            and open_path(self.current_res["out_report_csv"])
        )
        action_layout.addWidget(self.btn_open_report)

        self.btn_open_svg = QPushButton(" Get SVG")
        self.btn_open_svg.setIcon(qta.icon("mdi.image-outline", color="#1D1D1F"))
        self.btn_open_svg.setCursor(Qt.PointingHandCursor)
        self.btn_open_svg.setStyleSheet(btn_style)
        self.btn_open_svg.setEnabled(False)
        self.btn_open_svg.clicked.connect(
            lambda: hasattr(self, "current_svg") and open_path(self.current_svg)
        )
        action_layout.addWidget(self.btn_open_svg)

        action_layout.addStretch()
        top_left_vbox.addLayout(action_layout)
        right_layout.addWidget(top_left_card, stretch=6)

        bottom_card = QFrame()
        bottom_card.setStyleSheet(
            "QFrame { "
            "background-color: #FFFFFF; border: 1px solid #E5E5EA; "
            "border-radius: 10px; "
            "}"
        )
        bottom_half_layout = QVBoxLayout(bottom_card)
        bottom_half_layout.setContentsMargins(15, 15, 15, 15)
        bottom_half_layout.setSpacing(8)

        nwk_header = QHBoxLayout()
        nwk_title_lbl = QLabel("NWK Text Output")
        nwk_title_lbl.setObjectName("SubHeader")
        nwk_title_lbl.setStyleSheet(STYLE_FLAT)
        nwk_header.addWidget(nwk_title_lbl)

        self.btn_open_nwk_folder = QPushButton(" Open NWK Folder")
        self.btn_open_nwk_folder.setIcon(
            qta.icon("mdi.folder-open-outline", color="#0071E3")
        )
        self.btn_open_nwk_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_nwk_folder.setStyleSheet(
            "QPushButton { "
            "color: #0071E3; font-weight: bold; font-size: 11px; border: none; "
            "background: transparent; "
            "} "
            "QPushButton:hover { color: #005BB5; } "
            "QPushButton:disabled { color: #A2A2A6; }"
        )
        self.btn_open_nwk_folder.setEnabled(False)
        self.btn_open_nwk_folder.clicked.connect(
            lambda: hasattr(self, "current_res")
            and open_path(self.current_res["session_dir"])
        )
        nwk_header.addWidget(self.btn_open_nwk_folder)
        nwk_header.addStretch()
        bottom_half_layout.addLayout(nwk_header)

        self.txt_preview = QTextBrowser()
        self.txt_preview.setStyleSheet(
            "border: 1px solid #E5E5EA; border-radius: 8px; background: #FAFAFA;"
            "color: #1D1D1F;"
            "font-family: Consolas, Menlo, 'DejaVu Sans Mono', monospace;"
            "font-size: 11px; padding: 10px; font-weight: normal; outline: none;"
        )
        bottom_half_layout.addWidget(self.txt_preview, stretch=1)

        right_layout.addWidget(bottom_card, stretch=4)

        self.splitter.addWidget(right_panel)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([500, 500])

        main_layout.addWidget(self.splitter, stretch=1)

        self.global_scroll.setWidget(scroll_content)
        master_layout.addWidget(self.global_scroll)

    def toggle_card(self, content_area, toggle_btn):
        if content_area.isVisible():
            content_area.hide()
            toggle_btn.setIcon(qta.icon("mdi.chevron-down", color="#1D1D1F"))
        else:
            content_area.show()
            toggle_btn.setIcon(qta.icon("mdi.chevron-up", color="#1D1D1F"))

    def reset_viewer(self):
        if self.nwk_files:
            self.run_btn.set_state("run", " Run New Annotation Session", "mdi.play")

    def add_trait_row(self):
        if not self.csv_file:
            return
        row = TraitRowWidget(self.csv_file, self.remove_trait_row, self.reset_viewer)
        self.trait_rows.append(row)
        self.trait_container.addWidget(row)

    def remove_trait_row(self, row_widget):
        if len(self.trait_rows) > 1:
            self.trait_rows.remove(row_widget)
            row_widget.setParent(None)
            self.reset_viewer()

    def update_algo_desc(self):
        desc = (
            "• Fitch Parsimony\n"
            f"• Felsenstein ML (μ: {self.algo_params['felsenstein_mu']})"
        )
        self.lbl_algo_desc.setText(desc)

    def open_settings(self):
        dialog = AlgoSettingsDialog(self, self.algo_params)
        if dialog.exec():
            self.algo_params = dialog.params
            self.update_algo_desc()
            self.reset_viewer()
            self.log_msg.emit("[INFO] Algorithm parameters updated.")

    def open_zoomed_popup(self):
        if not hasattr(self, "current_frames"):
            return
        popup = ImagePopupDialog(self, self.current_frames, self.current_step)
        popup.exec()

    def handle_csv_drop(self, files):
        if files:
            fname = files[0]
            self.csv_file = fname
            headers = t2_tagging_logic.get_csv_headers(fname)
            if fname in self.dz_csv.item_widgets:
                self.dz_csv.item_widgets[fname].set_headers(headers)
                self.dz_csv.item_widgets[fname].combo.currentIndexChanged.connect(
                    self.reset_viewer
                )
            for row in self.trait_rows:
                row.setParent(None)
            self.trait_rows.clear()
            self.btn_add_trait.show()
            self.add_trait_row()
            self.log_msg.emit(f"[INFO] Loaded Master CSV: {Path(fname).name}")
            if self.csv_file and self.nwk_files:
                self.run_btn.setEnabled(True)
                self.run_btn.set_state("run", "Run Auto-Consensus Tagging")
        else:
            self.csv_file = None
            self.run_btn.setEnabled(False)

    def handle_nwk_drop(self, files):
        self.nwk_files = files
        self.status_table.setRowCount(0)

        if files:
            self.log_msg.emit(f"[INFO] Loaded {len(files)} NWK file(s).")
            self.status_table.setRowCount(len(files))
            for i, f in enumerate(files):
                base_name = os.path.basename(f)
                gene_name = (
                    base_name.split("_")[0]
                    if "_" in base_name
                    else base_name.split(".")[0]
                )

                self.status_table.setItem(i, 0, QTableWidgetItem(gene_name))
                self.status_table.setItem(i, 1, QTableWidgetItem("Waiting..."))

                wrapper, lbl = self.create_status_badge("Ready", "#F2F2F7", "#8E8E93")
                self.status_table.setCellWidget(i, 2, wrapper)

            if self.csv_file:
                self.run_btn.setEnabled(True)
                self.run_btn.set_state("run", "Run Auto-Consensus Tagging")
        else:
            self.run_btn.setEnabled(False)

    def create_status_badge(self, text, bg_color, text_color):
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(4, 2, 4, 2)
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f"background-color: {bg_color}; color: {text_color}; "
            "border-radius: 6px; font-weight: 800; font-size: 11px; "
            "padding: 4px 8px;"
        )
        layout.addWidget(lbl)
        return wrapper, lbl

    def _collect_selections(self) -> dict:
        """Trait column to selected states, read off the pill widgets.

        A column can appear in more than one row, since each row picks its own
        column, so the states accumulate under it rather than replacing.
        """
        selections = {}
        for row in self.trait_rows:
            column, values = row.get_selected()
            if not values:
                continue
            selections.setdefault(column, []).extend(str(v).strip() for v in values)
        return selections

    def start_tagging(self):
        selections = self._collect_selections()
        if not selections:
            message_box(
                self,
                QMessageBox.Warning,
                "Missing Info",
                "Please select at least one Target Trait Pill.",
            ).exec_()
            return

        target_vars_str = t2_tagging_logic.trait_label(selections)

        df = pd.read_csv(self.csv_file)
        name_col = self.dz_csv.item_widgets[self.csv_file].combo.currentText()
        try:
            tagged_data = t2_tagging_logic.build_tagged_data(df, name_col, selections)
        except KeyError as exc:
            self.log_msg.emit(f"[ERROR] {exc}")
            return

        self.run_btn.setEnabled(False)
        self.run_btn.set_state("busy", "Processing...")

        self.current_batch_labels = {}
        for nwk in self.nwk_files:
            self.status_table.insertRow(0)

            base_name = os.path.basename(nwk)
            gene_name = (
                base_name.split("_")[0] if "_" in base_name else base_name.split(".")[0]
            )

            item_name = QTableWidgetItem(gene_name)
            item_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.status_table.setItem(0, 0, item_name)

            item_tag = QTableWidgetItem(target_vars_str)
            item_tag.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.status_table.setItem(0, 1, item_tag)

            wrapper, lbl = self.create_status_badge("Processing", "#FFF9E5", "#FF9500")
            self.status_table.setCellWidget(0, 2, wrapper)
            self.current_batch_labels[nwk] = lbl

        first_nwk_name = (
            os.path.basename(self.nwk_files[0]) if self.nwk_files else "Annotation_Job"
        )
        self.progress_update.emit(first_nwk_name, 10, "Running Batch Annotation...")

        self.thread = TaggingThread(
            self.csv_file,
            self.nwk_files,
            tagged_data,
            target_vars_str,
            self.algo_params,
        )
        self.thread.finished.connect(self.on_finished)
        self.thread.start()

    def on_finished(self, res):
        self.run_btn.setEnabled(True)
        self.run_btn.set_state("run", "Run Auto-Consensus Annotation")

        first_nwk_name = (
            os.path.basename(self.nwk_files[0]) if self.nwk_files else "Tagging_Job"
        )

        if res.get("status") == "success":
            new_results = res["results"]
            for key, r in new_results.items():
                if r.get("status") != "success":
                    continue
                n_un = len(r.get("unmatched_leaves", []))
                if n_un:
                    names = ", ".join(r["unmatched_leaves"][:5])
                    self.log_msg.emit(
                        "[WARNING] %s: %d of %d tree leaves had no trait entry and "
                        "were treated as background: %s%s"
                        % (
                            os.path.basename(r.get("original_nwk", key)),
                            n_un,
                            r.get("n_leaves", 0),
                            names,
                            " ..." if n_un > 5 else "",
                        )
                    )
                else:
                    self.log_msg.emit(
                        "[INFO] %s: all %d tree leaves matched the trait table."
                        % (
                            os.path.basename(r.get("original_nwk", key)),
                            r.get("n_leaves", 0),
                        )
                    )
                for w in r.get("mu_warnings", []):
                    self.log_msg.emit(
                        "[WARNING] %s: %s"
                        % (os.path.basename(r.get("original_nwk", key)), w)
                    )
                for item in r.get("tree_cleanup_notes", []):
                    detail = ""
                    if item["taxa"]:
                        detail = " — %d taxa below: %s" % (
                            item["taxa_count"],
                            item["taxa"],
                        )
                    self.log_msg.emit(
                        "[INFO] %s: %s%s"
                        % (
                            os.path.basename(r.get("original_nwk", key)),
                            item["note"],
                            detail,
                        )
                    )
                if r.get("mu_estimated"):
                    self.log_msg.emit(
                        "[INFO] %s: estimated transition rate mu = %.3f"
                        % (
                            os.path.basename(r.get("original_nwk", key)),
                            r.get("mu_used", 0.0),
                        )
                    )

            self.batch_results.update(new_results)

            self.combo_viewer.clear()
            self.combo_viewer.addItems(list(self.batch_results.keys()))
            self.combo_viewer.setCurrentIndex(self.combo_viewer.count() - 1)

            self.combo_viewer.setEnabled(True)
            self.btn_prev.setEnabled(True)
            self.btn_next.setEnabled(True)
            self.lbl_step_title.setStyleSheet(
                "font-weight: 800; color: #1D1D1F; font-size: 13px; border: none;"
                "background: transparent;"
            )

            self.btn_open_img_folder.setEnabled(True)
            self.btn_open_nwk_folder.setEnabled(True)
            self.btn_open_report.setEnabled(True)
            self.btn_open_svg.setEnabled(True)

            for key, data in new_results.items():
                orig_nwk = data.get("original_nwk")
                if orig_nwk and orig_nwk in self.current_batch_labels:
                    lbl = self.current_batch_labels[orig_nwk]
                    if data.get("status") == "success":
                        lbl.setText("Completed")
                        lbl.setStyleSheet(
                            "background-color: #E5F0FF; color: #0071E3;"
                            "border-radius: 6px; font-weight: 800; font-size: 11px;"
                            "padding: 4px 8px;"
                        )
                    else:
                        lbl.setText("Error")
                        lbl.setStyleSheet(STYLE_ERROR_PILL)

            self.log_msg.emit(
                f"[SUCCESS] Batch Annotation Complete! "
                f"{len(new_results)} session(s) saved."
            )
            self.progress_update.emit(first_nwk_name, 100, "Completed")

        else:
            tb = res.get("traceback", "")
            err_msg = res.get("message", "Unknown Error")
            full_err = f"{err_msg}\n{tb}" if tb else err_msg

            for lbl in self.current_batch_labels.values():
                lbl.setText("Error")
                lbl.setStyleSheet(STYLE_ERROR_PILL)
            self.log_msg.emit(f"[ERROR] {full_err}")
            self.progress_update.emit(first_nwk_name, 0, "Error Occurred")
            common_utils.log_error_to_file(
                t1_st1_logic.CURRENT_PROJECT_PATH, t2_tagging_logic.TAB_NAME, full_err
            )

    def update_viewer(self):
        idx = self.combo_viewer.currentIndex()
        if idx == -1:
            return

        session_name = list(self.batch_results.keys())[idx]
        self.current_res = self.batch_results[session_name]

        if self.current_res.get("status") != "success":
            self.txt_preview.setText(
                f"Error on this tree: {self.current_res.get('message')}"
            )
            return

        base = self.current_res["out_fig_base"]
        first_img = f"{base}_step0.svg"

        # This result's own tree, not the first of the batch. Drawing another
        # gene's topology matches the tips, whose names are shared, but not the
        # internal clades, so the scores are silently dropped for most internal
        # nodes and those branches come out inactive however they were tagged.
        #
        # The collapsed tree when one was written. The algorithms and the scores
        # file both refer to it, so drawing the uncollapsed tree leaves every
        # collapsed node without a score for the same reason.
        nwk_path = self.current_res.get("cleaned_tree_path") or self.current_res.get(
            "original_nwk"
        )
        if nwk_path and not os.path.exists(first_img):
            t2_tagging_logic.render_all_steps(
                nwk_path,
                base,
                self.current_res["tagged_data"],
                no_signal=self.current_res.get("no_signal", False),
            )

        steps = range(t2_tagging_logic.N_STEPS)
        self.current_frames = [f"{base}_step{i}.svg" for i in steps]
        self.current_svgs = [f"{base}_step{i}.svg" for i in steps]
        self.current_nwks = self.current_res["nwk_steps"]
        self.set_step_absolute(t2_tagging_logic.N_STEPS - 1)

    def show_image(self, path):
        if os.path.exists(path):
            pixmap = QPixmap(path)
            self.img_preview.setPixmap(
                pixmap.scaled(
                    self.img_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
            self.img_preview.setStyleSheet(
                "border: none; background: #FAFAFA; border-radius: 10px;"
            )

    def change_step(self, delta):
        self.set_step_absolute(self.current_step + delta)

    def set_step_absolute(self, idx):
        self.current_step = max(0, min(idx, t2_tagging_logic.N_STEPS - 1))
        self.btn_prev.setEnabled(self.current_step > 0)
        labels = [
            "Step 1: Fitch Parsimony",
            "Step 2: Felsenstein ML",
            "Step 3: Consensus",
        ]
        self.lbl_step_title.setText(labels[self.current_step])
        if hasattr(self, "current_frames"):
            self.show_image(self.current_frames[self.current_step])
            self.current_svg = self.current_svgs[self.current_step]
            self.txt_preview.setText(self.current_nwks[self.current_step])
