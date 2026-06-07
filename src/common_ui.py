import os
import re
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QFileDialog,
    QProgressBar,
    QScrollArea,
    QDialog,
    QComboBox,
    QTableWidget,
    QHeaderView,
    QGraphicsDropShadowEffect,
    QTextBrowser,
    QLineEdit,
    QSplitter,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QPoint, QTime
from PyQt5.QtGui import QColor, QPixmap, QPainter, QPen, QIcon, QTextCursor, QFont
import qtawesome as qta
import common_utils


class Popup(QDialog):
    def __init__(
        self, title, message, popup_type="success", parent=None, custom_btn_text=None
    ):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(360, 240)
        style_map = {
            "success": ("#34C759", "#EBF9EE", "mdi.check", "Okay"),
            "error": ("#FF3B30", "#FFECEB", "mdi.close", "Retry"),
            "warning": ("#FFCC00", "#FFF9E5", "mdi.exclamation", "Cancel"),
            "info": ("#0071E3", "#E5F0FF", "mdi.information-variant", "Okay"),
        }
        color, bg_light, icon_name, default_btn = style_map.get(
            popup_type, style_map["success"]
        )

        btn_text = custom_btn_text if custom_btn_text else default_btn

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.main_bg = QFrame()
        self.main_bg.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border-radius: 16px; border: 1px solid #E5E5EA; }"
        )
        bg_layout = QVBoxLayout(self.main_bg)
        bg_layout.setContentsMargins(20, 15, 20, 25)
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.close_btn = QPushButton()
        self.close_btn.setIcon(qta.icon("mdi.close", color="#8E8E93"))
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; border-radius: 12px; } QPushButton:hover { background-color: #F2F2F7; }"
        )
        self.close_btn.clicked.connect(self.reject)
        top_bar.addWidget(self.close_btn)
        bg_layout.addLayout(top_bar)
        icon_layout = QHBoxLayout()
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(48, 48)
        self.icon_lbl.setStyleSheet(
            f"background-color: {bg_light}; border-radius: 24px; border: none;"
        )
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setPixmap(qta.icon(icon_name, color=color).pixmap(28, 28))
        icon_layout.addStretch()
        icon_layout.addWidget(self.icon_lbl)
        icon_layout.addStretch()
        bg_layout.addLayout(icon_layout)
        bg_layout.addSpacing(5)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            'font-family: -apple-system, "Segoe UI"; font-size: 18px; font-weight: 800; color: #1D1D1F; border: none; background: transparent;'
        )
        title_lbl.setAlignment(Qt.AlignCenter)
        bg_layout.addWidget(title_lbl)
        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet(
            'font-family: -apple-system, "Segoe UI"; font-size: 13px; color: #515154; border: none; background: transparent;'
        )
        msg_lbl.setAlignment(Qt.AlignCenter)
        msg_lbl.setWordWrap(True)
        bg_layout.addWidget(msg_lbl)
        bg_layout.addSpacing(10)
        self.action_btn = QPushButton(btn_text)
        self.action_btn.setFixedHeight(40)
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.setStyleSheet("""
            QPushButton { background-color: #1D1D1F; color: white; font-size: 14px; font-weight: bold; border-radius: 8px; border: none; }
            QPushButton:hover { background-color: #333333; }
        """)
        self.action_btn.clicked.connect(self.accept)
        bg_layout.addWidget(self.action_btn)
        layout.addWidget(self.main_bg)

    def exec(self):
        overlay = None
        main_win = self.parentWidget().window() if self.parentWidget() else None
        if main_win:
            overlay = QWidget(main_win)
            overlay.setStyleSheet("background-color: rgba(0, 0, 0, 120);")
            overlay.setGeometry(main_win.rect())
            overlay.show()
        res = super().exec()
        if overlay:
            overlay.deleteLater()
        return res


class PrimaryButton(QPushButton):
    def __init__(self, text, icon_name=None):
        super().__init__(text)
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)
        if icon_name:
            self.setIcon(qta.icon(icon_name, color="white"))
        self.setStyleSheet("""
            QPushButton { background-color: #1D1D1F; color: white; font-size: 14px; font-weight: bold; border-radius: 8px; border: none; padding: 0 16px; }
            QPushButton:hover { background-color: #000000; }
            QPushButton:disabled { background-color: #E5E5EA; color: #8E8E93; }
        """)


class ActionButton(QPushButton):
    def __init__(self, text, icon_name, is_danger=False):
        super().__init__(text)
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self.setIcon(qta.icon(icon_name, color="white"))
        bg_color = "#FF3B30" if is_danger else "#0071E3"
        hover_color = "#D70015" if is_danger else "#005BB5"
        self.setStyleSheet(f"""
            QPushButton {{ background-color: {bg_color}; color: white; font-size: 14px; font-weight: bold; border-radius: 8px; border: none; padding: 0 16px; }}
            QPushButton:hover {{ background-color: {hover_color}; }}
        """)


class GhostButton(QPushButton):
    def __init__(self, text, icon_name, color="#515154", hover_color="#1D1D1F"):
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setIcon(qta.icon(icon_name, color=color))
        self.setStyleSheet(f"""
            QPushButton {{ font-size: 14px; font-weight: bold; color: {color}; background: transparent; border: none; }}
            QPushButton:hover {{ color: {hover_color}; }}
        """)


class StandardComboBox(QComboBox):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(36)
        self.setMinimumWidth(220)
        self.setStyleSheet("""
            QComboBox { border: 1px solid #E5E5EA; border-radius: 8px; padding: 5px 12px; background: #ffffff; color: #1D1D1F; font-size: 14px; }
            QComboBox::drop-down { border: none; width: 30px; }
            QComboBox::down-arrow { image: url("data:image/svg+xml;base64,..."); }
        """)


class StandardTable(QTableWidget):
    def __init__(self, headers):
        super().__init__(0, len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(44)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("""
            QTableWidget { border: 1px solid #E5E5EA; border-radius: 8px; background-color: #FFFFFF; outline: none; }
            QTableWidget::item { padding: 8px; border-bottom: 1px solid #F2F2F7; font-size: 14px; color: #1D1D1F; }
            QHeaderView::section { background-color: #FAFAFA; border: none; border-bottom: 1px solid #E5E5EA; font-size: 13px; font-weight: bold; color: #8E8E93; height: 36px; }
        """)


class CustomTableCheckBox(QLabel):
    toggled = pyqtSignal(bool)

    def __init__(self, checked=True):
        super().__init__()
        self.setFixedSize(20, 20)
        self.is_checked = checked
        self.setCursor(Qt.PointingHandCursor)
        self.setAlignment(Qt.AlignCenter)
        self.update_state()

    def update_state(self):
        if self.is_checked:
            self.setStyleSheet(
                "background-color: #0071E3; border-radius: 4px; border: 2px solid #0071E3;"
            )
            self.setPixmap(qta.icon("mdi.check", color="white").pixmap(14, 14))
        else:
            self.setStyleSheet(
                "background-color: #FFFFFF; border-radius: 4px; border: 2px solid #8E8E93;"
            )
            self.clear()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_checked = not self.is_checked
            self.update_state()
            self.toggled.emit(self.is_checked)


class TableCheckBoxWidget(QWidget):
    def __init__(self, checked=True):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        self.checkbox = CustomTableCheckBox(checked)
        layout.addWidget(self.checkbox)

    @property
    def is_checked(self):
        return self.checkbox.is_checked


class CollapsibleCard(QFrame):
    def __init__(self, title, description="", start_collapsed=True):
        super().__init__()
        self.setObjectName("MainCard")
        self.setStyleSheet(
            "QFrame#MainCard { background-color: #ffffff; border: 1px solid #e5e5ea; border-radius: 16px; }"
        )
        s = QGraphicsDropShadowEffect()
        s.setBlurRadius(30)
        s.setColor(QColor(0, 0, 0, 10))
        s.setOffset(0, 6)
        self.setGraphicsEffect(s)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = QFrame()
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setStyleSheet("background: transparent; border: none;")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(25, 20, 25, 20)
        text_vbox = QVBoxLayout()
        text_vbox.setSpacing(4)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("SubHeader")
        title_lbl.setStyleSheet("border: none; background: transparent;")
        desc_lbl = QLabel(description)
        desc_lbl.setObjectName("SubText")
        desc_lbl.setStyleSheet("border: none; background: transparent;")
        text_vbox.addWidget(title_lbl)
        text_vbox.addWidget(desc_lbl)
        header_layout.addLayout(text_vbox)
        header_layout.addStretch()
        self.toggle_icon = QLabel()
        self.toggle_icon.setStyleSheet("background: transparent; border: none;")
        header_layout.addWidget(self.toggle_icon)
        layout.addWidget(self.header)
        self.content_area = QFrame()
        self.content_area.setStyleSheet("background: transparent; border: none;")
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(25, 0, 25, 25)
        self.content_layout.setSpacing(20)
        layout.addWidget(self.content_area)
        if start_collapsed:
            self.content_area.hide()
            self.toggle_icon.setPixmap(
                qta.icon("mdi.chevron-down", color="#1D1D1F").pixmap(28, 28)
            )
        else:
            self.content_area.show()
            self.toggle_icon.setPixmap(
                qta.icon("mdi.chevron-up", color="#1D1D1F").pixmap(28, 28)
            )
        self.header.mousePressEvent = self.toggle_content

    def toggle_content(self, event):
        is_visible = self.content_area.isVisible()
        self.content_area.setVisible(not is_visible)
        icon_name = "mdi.chevron-down" if is_visible else "mdi.chevron-up"
        self.toggle_icon.setPixmap(qta.icon(icon_name, color="#1D1D1F").pixmap(28, 28))


class FileItemWidget(QFrame):
    remove_requested = pyqtSignal(str)

    def __init__(
        self,
        file_path,
        show_dropdown=False,
        file_type="csv",
        show_gene_input=True,
        strict_gene_parse=True,
    ):
        super().__init__()
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.file_type = file_type.lower()
        self.strict_gene_parse = strict_gene_parse
        self.setStyleSheet(
            "QFrame { background-color: #F5F5F7; border: none; border-radius: 6px; }"
        )
        self.setFixedHeight(42)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(4)

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setAlignment(Qt.AlignVCenter)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(
            qta.icon("mdi.file-document-outline", color="#515154").pixmap(18, 18)
        )
        top_layout.addWidget(icon_lbl)

        name_lbl = QLabel(self.filename)
        name_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 500; color: #1D1D1F; padding-right: 10px; border: none;"
        )

        metrics = name_lbl.fontMetrics()
        elided = metrics.elidedText(self.filename, Qt.ElideMiddle, 200)
        name_lbl.setText(elided)
        top_layout.addWidget(name_lbl)
        top_layout.addStretch()

        if self.file_type == "csv":
            self.combo_lbl = QLabel("Species column:")
            self.combo_lbl.setStyleSheet(
                "font-size: 12px; font-weight: 600; color: #515154; border: none;"
            )
            self.combo_lbl.setVisible(show_dropdown)
            top_layout.addWidget(self.combo_lbl)

            self.combo = QComboBox()
            self.combo.setFixedHeight(28)
            self.combo.setMinimumWidth(130)
            self.combo.setStyleSheet("""
                QComboBox { border: 1px solid #D1D1D6; border-radius: 6px; padding: 2px 10px; font-size: 12px; background: white; color: #1D1D1F; }
                QComboBox::drop-down { border: none; }
            """)
            self.combo.setVisible(show_dropdown)
            top_layout.addWidget(self.combo)

        elif show_gene_input:
            self.gene_lbl = QLabel("Gene Name:")
            self.gene_lbl.setStyleSheet(
                "font-size: 12px; font-weight: 800; color: #0071E3; border: none;"
            )
            top_layout.addWidget(self.gene_lbl)

            self.gene_input = QLineEdit()
            self.gene_input.setFixedHeight(28)
            self.gene_input.setFixedWidth(100)
            self.gene_input.setStyleSheet("""
                QLineEdit { border: 1px solid #0071E3; border-radius: 6px; padding: 2px 10px; font-size: 12px; font-weight: bold; background: white; color: #1D1D1F; }
                QLineEdit:focus { border: 2px solid #005BB5; }
            """)

            if self.strict_gene_parse:
                detected_gene = common_utils.detect_gene_from_file(self.file_path)
            else:
                detected_gene = re.split(r"[_.]", self.filename)[0].upper()

            self.gene_input.setText(detected_gene)
            top_layout.addWidget(self.gene_input)

        del_btn = QPushButton()
        del_btn.setIcon(qta.icon("mdi.close", color="#8E8E93"))
        del_btn.setFixedSize(26, 26)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(
            "QPushButton { border: none; border-radius: 13px; background: transparent; } QPushButton:hover { background-color: #E5E5EA; }"
        )
        del_btn.clicked.connect(lambda: self.remove_requested.emit(self.file_path))
        top_layout.addWidget(del_btn)

        layout.addLayout(top_layout)

        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(4)
        self.pbar.setTextVisible(False)
        self.pbar.setStyleSheet(
            "QProgressBar { background-color: transparent; border: none; } QProgressBar::chunk { background-color: #34C759; border-radius: 2px; }"
        )
        self.pbar.hide()
        layout.addWidget(self.pbar)

    def set_headers(self, headers):
        if hasattr(self, "combo"):
            current = self.combo.currentText()
            self.combo.clear()
            self.combo.addItems(headers)
            for h in headers:
                if "species" in h.lower() or "taxon" in h.lower():
                    self.combo.setCurrentText(h)
                    break
            else:
                if current in headers:
                    self.combo.setCurrentText(current)

    def get_gene_name(self):
        if hasattr(self, "gene_input"):
            return self.gene_input.text().strip() or "UNKNOWN"
        return ""

    def update_progress(self, val):
        self.pbar.show()
        if self.pbar.maximum() == 0 and val == 0:
            self.pbar.setRange(0, 0)
        else:
            self.pbar.setRange(0, 100)
            self.pbar.setValue(val)


class UnifiedDropZone(QWidget):
    files_updated = pyqtSignal(list)

    def __init__(
        self,
        supported_exts,
        format_text="Supported formats",
        show_dropdown=False,
        file_type="csv",
        show_gene_input=True,
        open_in_base_dir=False,
        strict_gene_parse=True,
    ):
        super().__init__()
        self.supported_exts = [ext.lower() for ext in supported_exts]
        self.show_dropdown = show_dropdown
        self.file_type = file_type
        self.show_gene_input = show_gene_input
        self.open_in_base_dir = open_in_base_dir
        self.strict_gene_parse = strict_gene_parse
        self.current_files = []
        self.item_widgets = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.drop_area = QFrame()
        self.drop_area.setAcceptDrops(True)
        self.drop_area.setCursor(Qt.PointingHandCursor)
        self.drop_area.setFixedHeight(120)
        self.drop_area.setStyleSheet(
            "QFrame { border: none; background: transparent; }"
        )

        drop_layout = QVBoxLayout(self.drop_area)
        drop_layout.setAlignment(Qt.AlignCenter)
        drop_layout.setSpacing(8)

        self.upload_icon = QLabel()
        self.upload_icon.setPixmap(
            qta.icon("fa5s.upload", color="#98989D").pixmap(26, 26)
        )
        self.upload_icon.setAlignment(Qt.AlignCenter)
        self.upload_icon.setStyleSheet("border: none; background: transparent;")
        drop_layout.addWidget(self.upload_icon)

        self.main_text = QLabel(
            'Drag & drop files here, or <span style="color: #0071E3; text-decoration: underline;">click to browse</span>'
        )
        self.main_text.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #1D1D1F; border: none; background: transparent;"
        )
        self.main_text.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(self.main_text)

        self.sub_text = QLabel(format_text)
        self.sub_text.setStyleSheet(
            "font-size: 13px; color: #8E8E93; border: none; background: transparent;"
        )
        self.sub_text.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(self.sub_text)

        self.drop_area.paintEvent = self._paint_drop_area
        self.drop_area.dragEnterEvent = self._drag_enter
        self.drop_area.dragLeaveEvent = self._drag_leave
        self.drop_area.dropEvent = self._drop
        self.drop_area.mousePressEvent = self._mouse_press
        layout.addWidget(self.drop_area)

        self.list_toolbar = QFrame()
        self.list_toolbar.setStyleSheet(
            "QFrame { border: none; background: transparent; }"
        )
        self.list_toolbar.hide()
        toolbar_layout = QHBoxLayout(self.list_toolbar)
        toolbar_layout.setContentsMargins(4, 0, 4, 0)

        self.file_count_lbl = QLabel()
        self.file_count_lbl.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #515154; border: none; background: transparent;"
        )
        toolbar_layout.addWidget(self.file_count_lbl)
        toolbar_layout.addStretch()

        self.add_more_btn = QPushButton(" Add files")
        self.add_more_btn.setIcon(qta.icon("mdi.plus", color="#0071E3"))
        self.add_more_btn.setCursor(Qt.PointingHandCursor)
        self.add_more_btn.setStyleSheet(
            "QPushButton { font-weight: bold; color: #0071E3; border: none; background: transparent; }"
        )
        self.add_more_btn.clicked.connect(self._open_file_dialog)
        toolbar_layout.addWidget(self.add_more_btn)

        self.clear_all_btn = QPushButton(" Clear all")
        self.clear_all_btn.setIcon(qta.icon("mdi.delete-outline", color="#FF3B30"))
        self.clear_all_btn.setCursor(Qt.PointingHandCursor)
        self.clear_all_btn.setStyleSheet(
            "QPushButton { font-weight: bold; color: #FF3B30; border: none; background: transparent; }"
        )
        self.clear_all_btn.clicked.connect(self.clear_all)
        toolbar_layout.addWidget(self.clear_all_btn)

        layout.addWidget(self.list_toolbar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        self.scroll_area.hide()
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.list_container)
        layout.addWidget(self.scroll_area)

        self.is_drag_hover = False
        self.is_error = False

    def _paint_drop_area(self, event):
        painter = QPainter(self.drop_area)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.is_error:
            pen = QPen(QColor("#FF3B30"), 2, Qt.DashLine)
            bg_color = QColor("#FFF0F0")
        elif self.is_drag_hover:
            pen = QPen(QColor("#0071E3"), 2, Qt.SolidLine)
            bg_color = QColor("#E5F0FF")
        else:
            if self.current_files:
                pen = QPen(Qt.NoPen)
                bg_color = QColor("#FAFAFA")
            else:
                pen = QPen(QColor("#D1D1D6"), 2, Qt.DashLine)
                bg_color = QColor("#FAFAFA")
        painter.setPen(pen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(self.drop_area.rect().adjusted(2, 2, -2, -2), 10, 10)

    def _drag_enter(self, event):
        if event.mimeData().hasUrls():
            self.is_drag_hover = True
            self.drop_area.update()
            event.accept()
        else:
            event.ignore()

    def _drag_hover_leave(self, event):
        self.is_drag_hover = False
        self.drop_area.update()

    def _drag_leave(self, event):
        self.is_drag_hover = False
        self.drop_area.update()

    def _drop(self, event):
        self.is_drag_hover = False
        self.drop_area.update()
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        valid_files = [
            f
            for f in files
            if any(f.lower().endswith(ext) for ext in self.supported_exts)
        ]
        if len(valid_files) != len(files):
            self._trigger_error()
        if valid_files:
            self.add_files(valid_files)

    def _mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._open_file_dialog()

    def _open_file_dialog(self):
        default_dir = ""
        try:
            import t1_st1_logic

            if self.open_in_base_dir and getattr(
                t1_st1_logic, "CURRENT_PROJECT_PATH", None
            ):
                default_dir = str(t1_st1_logic.CURRENT_PROJECT_PATH)
            elif getattr(t1_st1_logic, "CURRENT_PROJECT_PATH", None):
                p = common_utils.get_pipeline_path(
                    t1_st1_logic.CURRENT_PROJECT_PATH, "Results", self.file_type
                )
                if p and p.exists():
                    default_dir = str(p)
                else:
                    default_dir = str(t1_st1_logic.CURRENT_PROJECT_PATH)
        except Exception:
            default_dir = ""

        filter_str = " ".join([f"*{ext}" for ext in self.supported_exts])
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files",
            default_dir,
            f"Supported Files ({filter_str})"
        )
        if files:
            self.add_files(files)

    def _trigger_error(self):
        self.is_error = True
        self.main_text.setText("Unsupported file format!")
        self.main_text.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #FF3B30; border: none; background: transparent;"
        )
        self.drop_area.update()
        self.shake_anim = QPropertyAnimation(self.drop_area, b"pos")
        self.shake_anim.setDuration(400)
        orig_pos = self.drop_area.pos()
        self.shake_anim.setKeyValueAt(0.0, orig_pos)
        self.shake_anim.setKeyValueAt(0.2, orig_pos + QPoint(4, 0))
        self.shake_anim.setKeyValueAt(0.4, orig_pos - QPoint(4, 0))
        self.shake_anim.setKeyValueAt(0.6, orig_pos + QPoint(2, 0))
        self.shake_anim.setKeyValueAt(0.8, orig_pos - QPoint(2, 0))
        self.shake_anim.setKeyValueAt(1.0, orig_pos)
        self.shake_anim.start()
        QTimer.singleShot(1500, self._reset_error_state)

    def _reset_error_state(self):
        self.is_error = False
        self.drop_area.update()
        self._update_ui_state()

    def add_files(self, new_files):
        for f in new_files:
            if f not in self.current_files:
                self.current_files.append(f)
                item = FileItemWidget(
                    f,
                    show_dropdown=self.show_dropdown,
                    file_type=self.file_type,
                    show_gene_input=self.show_gene_input,
                    strict_gene_parse=self.strict_gene_parse,
                )
                item.remove_requested.connect(self.remove_file)
                self.item_widgets[f] = item
                self.list_layout.addWidget(item)
        self._update_ui_state()

    def get_all_genes(self):
        return {f: widget.get_gene_name() for f, widget in self.item_widgets.items()}

    def remove_file(self, file_path):
        if file_path in self.current_files:
            self.current_files.remove(file_path)
            item = self.item_widgets.pop(file_path)
            self.list_layout.removeWidget(item)
            item.deleteLater()
            self._update_ui_state()

    def clear_all(self):
        for f in list(self.current_files):
            self.remove_file(f)

    def update_file_progress(self, file_path, val):
        if file_path in self.item_widgets:
            self.item_widgets[file_path].update_progress(val)

    def _update_ui_state(self):
        if self.current_files:
            self.drop_area.setFixedHeight(60)
            self.upload_icon.hide()
            self.sub_text.hide()
            self.main_text.setText(
                'Drag & drop more files, or <span style="color: #0071E3; text-decoration: underline;">click to browse</span>'
            )
            self.file_count_lbl.setText(f"{len(self.current_files)} File(s) added")
            self.list_toolbar.show()
            self.scroll_area.show()

            item_h = 42
            spacing = self.list_layout.spacing()
            calc_h = (item_h + spacing) * len(self.current_files)
            self.scroll_area.setFixedHeight(min(calc_h, 180))

        else:
            self.drop_area.setFixedHeight(120)
            self.upload_icon.show()
            self.sub_text.show()
            self.main_text.setText(
                'Drag & drop files here, or <span style="color: #0071E3; text-decoration: underline;">click to browse</span>'
            )
            self.list_toolbar.hide()
            self.scroll_area.hide()
        self.drop_area.update()
        self.files_updated.emit(self.current_files)


class LogConsole(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogConsole")
        self.setFixedHeight(140)
        self.master_logs = []

        self.setStyleSheet(
            "QFrame#LogConsole { background-color: #F5F5F7; border: 1px solid #E5E5EA; border-radius: 10px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet(
            "QSplitter::handle { background-color: #E5E5EA; width: 2px; }"
        )

        self.sys_widget = QWidget()
        self.sys_widget.setStyleSheet("background: transparent; border: none;")
        sys_layout = QVBoxLayout(self.sys_widget)
        sys_layout.setContentsMargins(5, 5, 5, 5)

        sys_header = QHBoxLayout()
        sys_title = QLabel("SYSTEM LOG CONSOLE")
        sys_title.setStyleSheet(
            "font-size: 11px; font-weight: 800; color: #8E8E93; border: none;"
        )
        sys_header.addWidget(sys_title)
        sys_header.addStretch()
        clear_sys_btn = QPushButton("Clear")
        clear_sys_btn.setCursor(Qt.PointingHandCursor)
        clear_sys_btn.setStyleSheet(
            "QPushButton { font-weight: 700; font-size: 11px; color: #8E8E93; border: none; background: transparent; } QPushButton:hover { color: #FF3B30; }"
        )
        sys_header.addWidget(clear_sys_btn)
        sys_layout.addLayout(sys_header)

        self.browser = QTextBrowser()
        self.browser.setStyleSheet(
            "QTextBrowser { background-color: transparent; border: none; outline: none; }"
        )
        sys_layout.addWidget(self.browser)
        clear_sys_btn.clicked.connect(self.browser.clear)

        self.wsl_widget = QWidget()
        self.wsl_widget.setStyleSheet("background: transparent; border: none;")
        wsl_layout = QVBoxLayout(self.wsl_widget)
        wsl_layout.setContentsMargins(5, 5, 5, 5)

        wsl_header = QHBoxLayout()
        wsl_title = QLabel("WSL TERMINAL MIRROR")
        wsl_title.setStyleSheet(
            "font-size: 11px; font-weight: 800; color: #8E8E93; border: none;"
        )
        wsl_header.addWidget(wsl_title)
        wsl_header.addStretch()
        clear_wsl_btn = QPushButton("Clear")
        clear_wsl_btn.setCursor(Qt.PointingHandCursor)
        clear_wsl_btn.setStyleSheet(
            "QPushButton { font-weight: 700; font-size: 11px; color: #8E8E93; border: none; background: transparent; } QPushButton:hover { color: #FF3B30; }"
        )
        wsl_header.addWidget(clear_wsl_btn)
        wsl_layout.addLayout(wsl_header)

        self.wsl_browser = QTextBrowser()
        font = QFont("Consolas", 10)
        self.wsl_browser.setFont(font)
        self.wsl_browser.setStyleSheet(
            "QTextBrowser { background-color: #000000; color: #34C759; border: 1px solid #D1D1D6; border-radius: 8px; padding: 8px; outline: none; }"
        )
        self.wsl_browser.setText("[SYSTEM] WSL Mirror Ready. Waiting for execution...")
        wsl_layout.addWidget(self.wsl_browser)
        clear_wsl_btn.clicked.connect(self.clear_wsl_log)

        self.splitter.addWidget(self.sys_widget)
        self.splitter.addWidget(self.wsl_widget)

        self.wsl_widget.hide()

        layout.addWidget(self.splitter)

    def set_wsl_mode(self, enabled):
        if enabled:
            self.wsl_widget.show()
            self.setFixedHeight(180)
            self.splitter.setSizes([500, 500])
        else:
            self.wsl_widget.hide()
            self.setFixedHeight(140)

    def append_wsl_log(self, text):
        self.wsl_browser.append(text)
        self.wsl_browser.moveCursor(QTextCursor.MoveOperation.End)

    def clear_wsl_log(self):
        self.wsl_browser.clear()
        self.wsl_browser.append("[SYSTEM] WSL Mirror Ready. Waiting for execution...")

    def append_log(self, text, default_type="info"):
        timestamp = QTime.currentTime().toString("hh:mm:ss")
        full_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        color_map = {
            "info": "#8E8E93",
            "process": "#0071E3",
            "success": "#34C759",
            "warning": "#FFCC00",
            "error": "#FF3B30",
        }

        color = color_map.get(default_type.lower(), "#8E8E93")
        prefix = default_type.upper()
        clean_text = re.sub(r'[^\w\s.,!?:;\'"()[\]{}_+\-*/<>=|&^%$#@~`\\]', "", text)

        if text.startswith("["):
            match = re.match(r"^\[(.*?)\]\s*(.*)", text)
            if match:
                parsed_prefix = match.group(1).lower()
                clean_text = match.group(2)
                prefix = parsed_prefix.upper()
                if parsed_prefix in color_map:
                    color = color_map[parsed_prefix]
                elif "success" in parsed_prefix or "complete" in parsed_prefix:
                    color, prefix = color_map["success"], "SUCCESS"
                elif "error" in parsed_prefix or "fail" in parsed_prefix:
                    color, prefix = color_map["error"], "ERROR"
                elif "warn" in parsed_prefix:
                    color, prefix = color_map["warning"], "WARNING"
                elif "process" in parsed_prefix or "start" in parsed_prefix:
                    color, prefix = color_map["process"], "PROCESS"

        html = f"""
        <div style="font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; margin-bottom: 3px;">
            <span style="color: #AEAEB2;">[{timestamp}]</span>
            <span style="color: {color}; font-weight: bold;">[{prefix}]</span>
            <span style="color: #1D1D1F;">{clean_text}</span>
        </div>
        """
        self.browser.append(html)
        self.browser.moveCursor(QTextCursor.MoveOperation.End)
        self.master_logs.append(f"[{full_timestamp}] [{prefix}] {clean_text}")

    def export_master_log(self, project_path):
        if not self.master_logs or not project_path:
            return

        try:
            mmdd = datetime.now().strftime("%m%d")
            report_dir = Path(project_path) / "Reports" / "System_Logs"
            report_dir.mkdir(parents=True, exist_ok=True)

            log_file = report_dir / f"log_report_{mmdd}.txt"

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*50}\n")
                f.write(
                    f"HYphlow Session Ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                )
                f.write(f"{'='*50}\n")
                f.write("\n".join(self.master_logs) + "\n\n")

            self.master_logs.clear()
        except Exception:
            pass
