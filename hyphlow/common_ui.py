import html
import os
import re
import sys
from pathlib import Path

import qtawesome as qta
from PyQt5.QtCore import (
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTime,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QPainter,
    QPalette,
    QPen,
    QTextCursor,
)
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from hyphlow import common_utils, manifest_logic_tab, t1_st1_logic

# ======================================================= design tokens
INK, INK_MUTED, INK_FAINT = "#1D1D1F", "#515154", "#8E8E93"
BLUE, GREEN, RED, ORANGE = "#0071E3", "#34C759", "#FF3B30", "#FF9500"
LINE, SURFACE, SURFACE_ALT = "#E5E5EA", "#FFFFFF", "#F2F2F7"

RED_FILL, GREEN_FILL, ORANGE_FILL = "#FFECEB", "#EBF9EE", "#FFF9E5"
BLUE_FILL = "#E5F0FF"

# Text on GREEN_FILL. GREEN(#34C759) is the iOS accent and fails contrast
# on that background.
GREEN_DARK = "#16A34A"

INK_HOVER, BLUE_HOVER, RED_HOVER = "#333333", "#005BB5", "#D70015"
ORANGE_HOVER, RED_FILL_HOVER = "#E08600", "#FFD1CE"

FIELD_BG, FIELD_LINE = "#F5F5F7", "#D1D1D6"
DIM = "#FAFAFA"
PURPLE = "#5856D6"
SHADOW = "#C7C7CC"
YELLOW = "#FFCC00"
TERMINAL_BG, LOG_TIME = "#000000", "#AEAEB2"
DROP_H_EMPTY, DROP_H_FILLED, LIST_MAX_H = 120, 60, 180
CONSOLE_H, CONSOLE_H_WSL = 140, 180

FLAT = "background: transparent; border: none;"

FONT_FAMILY = "-apple-system, 'Segoe UI', Roboto, sans-serif"
FONT_STACK = ["Segoe UI", "Roboto", "DejaVu Sans", "sans-serif"]
MONO_FAMILY = "Consolas, Menlo, 'DejaVu Sans Mono', 'Courier New', monospace"
MONO_STACK = ["Consolas", "Menlo", "DejaVu Sans Mono", "Courier New", "monospace"]

FS_TITLE, FS_BODY, FS_SMALL, FS_TINY = 16, 14, 13, 11
FS_H1, FS_H2, FS_H3 = 24, 20, 18
RADIUS_SMALL, RADIUS, RADIUS_CARD = 6, 8, 16
BTN_HEIGHT, ROW_H = 44, 44
FS_FIELD = 12
# Width a file name is elided to in a drop-zone row.
FILENAME_MAX_W = 200
ITEM_H, FIELD_H = 42, 28


def card(radius=RADIUS_CARD, name=None):
    sel = f"QFrame#{name}" if name else "QFrame"
    return (
        f"{sel} {{ background-color: {SURFACE}; border: 1px solid {LINE};"
        f" border-radius: {radius}px; }}"
    )


BUTTON_STATES = {
    "run": (INK, SURFACE, INK_HOVER),
    "accent": (BLUE, SURFACE, BLUE_HOVER),
    "stop": (RED, SURFACE, RED_HOVER),
    "busy": (ORANGE, SURFACE, ORANGE_HOVER),
    "error": (RED_FILL, RED, RED_FILL_HOVER),
}


def mono_font(size=10):
    f = QFont()
    f.setFamilies(MONO_STACK)
    f.setPointSize(size)
    f.setStyleHint(QFont.Monospace)
    return f


def open_path(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def link_button(text, icon_name=None, color=BLUE, hover=None):
    b = QPushButton(text)
    if icon_name:
        b.setIcon(qta.icon(icon_name, color=color))
    b.setCursor(Qt.PointingHandCursor)
    sheet = (
        f"QPushButton {{ font-size: {FS_SMALL}px; font-weight: bold;"
        f" color: {color}; {FLAT} }}"
    )
    if hover:
        sheet += f"QPushButton:hover {{ color: {hover}; }}"
    b.setStyleSheet(sheet)
    return b


def caption(text, color=INK_FAINT):
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: {FS_TINY}px; font-weight: 800; color: {color}; border: none;"
    )
    return lbl


TERMINAL_READY = "[SYSTEM] Terminal ready. Waiting for execution..."

LOG_COLORS = {
    "info": INK_FAINT,
    "process": BLUE,
    "success": GREEN,
    "warning": YELLOW,
    "error": RED,
}

# Prefixes people actually type in log messages, mapped onto the five levels.
LOG_ALIASES = (
    (("success", "completed"), "success"),
    (("error", "fail"), "error"),
    (("warn",), "warning"),
    (("process", "start"), "process"),
)


def _drop_hint(more=False):
    what = "more files" if more else "files here"
    return (
        f'Drag & drop {what}, or <span style="color: {BLUE};'
        ' text-decoration: underline;">click to browse</span>'
    )


def _drop_text_css(color=INK):
    return f"font-size: {FS_BODY}px; font-weight: 600; color: {color}; {FLAT}"


_LIGHT_ROLES = {
    "Window": SURFACE,
    "WindowText": INK,
    "Base": SURFACE,
    "AlternateBase": SURFACE_ALT,
    "ToolTipBase": SURFACE,
    "ToolTipText": INK,
    "Text": INK,
    "Button": SURFACE_ALT,
    "ButtonText": INK,
    "BrightText": SURFACE,
    "Highlight": BLUE,
    "HighlightedText": SURFACE,
    "PlaceholderText": INK_FAINT,
    "Link": BLUE,
    "LinkVisited": PURPLE,
    "Light": SURFACE,
    "Midlight": DIM,
    "Mid": LINE,
    "Dark": FIELD_LINE,
    "Shadow": SHADOW,
}


_DISABLED_ROLES = {
    "WindowText": INK_FAINT,
    "Text": INK_FAINT,
    "ButtonText": INK_FAINT,
    "Base": SURFACE_ALT,
    "Button": SURFACE_ALT,
    "Window": SURFACE,
    "Highlight": LINE,
    "HighlightedText": INK_FAINT,
}

GLOBAL_STYLESHEET = f"""
QMainWindow, QDialog, QFileDialog, QMessageBox {{
    background-color: {SURFACE};
    color: {INK};
}}
/* Unparented boxes get no ancestor sheet, so these are their only defence.
   Same values as MESSAGE_BOX_STYLESHEET: a box must not look different for
   having been built one way rather than the other. */
QMessageBox QLabel {{ color: {INK}; background: transparent; }}
QMessageBox QPushButton {{
    background-color: {FIELD_BG}; color: {INK};
    border: 1px solid {FIELD_LINE}; border-radius: 6px;
    padding: 6px 18px; min-width: 72px;
}}
QMessageBox QPushButton:hover {{ background-color: {LINE}; }}
QMessageBox QPushButton:default {{
    background-color: {INK}; color: {SURFACE}; border: none; font-weight: bold;
}}
QToolTip {{ background-color: {SURFACE}; color: {INK}; border: 1px solid {LINE}; padding: 4px; }}
QMenu {{ background-color: {SURFACE}; color: {INK}; border: 1px solid {LINE}; }}
QMenu::item:selected {{ background-color: {SURFACE_ALT}; color: {INK}; }}
QComboBox QAbstractItemView{{
    background-color: {SURFACE}; color: {INK};
    selection-background-color: {SURFACE_ALT}; selection-color: {INK};
}}
QLabel#MainTitle {{ font-size: {FS_H1}px; font-weight: 800; color: {INK}; {FLAT} }}
QLabel#SectionHeader {{ font-size: {FS_H2}px; font-weight: 700; color: {INK}; {FLAT} }}
QLabel#SubHeader {{ font-size: {FS_H3}px; font-weight: 500; color: {INK}; {FLAT} }}
QLabel#SubText {{ font-size: {FS_BODY}px; font-weight: 400; color: {INK_FAINT}; {FLAT} }}
QScrollBar:vertical {{ {FLAT} width: 8px; margin: 0px; }}
QScrollBar::handle:vertical {{ background-color: {FIELD_LINE}; border-radius: 4px; min-height: 20px; }}
QScrollBar::handle:vertical:hover {{ background-color: {INK_FAINT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ {FLAT} height: 0px; }}
QScrollBar:horizontal {{ {FLAT} height: 8px; margin: 0px; }}
QScrollBar::handle:horizontal {{ background-color: {FIELD_LINE}; border-radius: 4px; min-width: 20px; }}
QScrollBar::handle:horizontal:hover {{ background-color: {INK_FAINT}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ {FLAT} width: 0px; }}
"""

FILE_DIALOG_STYLESHEET = f"""
QWidget {{ background-color: {SURFACE}; color: {INK}; }}
QAbstractItemView {{
    background-color: {SURFACE}; color: {INK};
    alternate-background-color: {SURFACE_ALT}; outline: none;
}}
QAbstractItemView::item:selected {{ background-color: {BLUE}; color: {SURFACE}; }}
QHeaderView::section {{
    background-color: {SURFACE_ALT}; color: {INK}; border: none;
    border-right: 1px solid {FIELD_LINE}; border-bottom: 1px solid {FIELD_LINE};
    padding: 4px;
}}
QPushButton {{
    background-color: {FIELD_BG}; color: {INK}; border: 1px solid {FIELD_LINE};
    border-radius: 4px; padding: 5px 14px; min-width: 64px;
}}
QPushButton:hover {{ background-color: {LINE}; }}
QLineEdit, QComboBox {{
    background-color: {FIELD_BG}; color: {INK};
    border: 1px solid {FIELD_LINE}; border-radius: 4px; padding: 3px 6px;
}}
QComboBox QAbstractItemView {{ background-color: {SURFACE}; color: {INK}; }}
QToolButton {{ {FLAT} padding: 2px; }}
QToolButton:hover {{ background-color: {SURFACE_ALT}; border-radius: 4px; }}
"""

MESSAGE_BOX_STYLESHEET = f"""
QMessageBox {{ background-color: {SURFACE}; }}
QMessageBox QLabel {{ background: transparent; color: {INK}; }}
QMessageBox QPushButton {{
    background-color: {FIELD_BG}; color: {INK}; border: 1px solid {FIELD_LINE};
    border-radius: 6px; padding: 6px 18px; min-width: 72px;
}}
QMessageBox QPushButton:hover {{ background-color: {LINE}; }}
QMessageBox QPushButton:default {{
    background-color: {INK}; color: {SURFACE}; border: none; font-weight: bold;
}}
"""


def message_box(parent, icon, title, text):
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStyleSheet(MESSAGE_BOX_STYLESHEET)
    return box


def _file_dialog(parent, title, directory, filter_str=""):
    d = QFileDialog(parent, title, str(directory or ""), filter_str)
    d.setOption(QFileDialog.DontUseNativeDialog, True)
    d.setStyleSheet(FILE_DIALOG_STYLESHEET)
    return d


def _pick_one(d):
    picked = d.selectedFiles() if d.exec_() else []
    return picked[0] if picked else ""


def pick_files(parent, title, directory, filter_str):
    d = _file_dialog(parent, title, directory, filter_str)
    d.setFileMode(QFileDialog.ExistingFiles)
    return d.selectedFiles() if d.exec_() else []


def pick_save(parent, title, directory, filter_str):
    d = _file_dialog(parent, title, directory, filter_str)
    d.setAcceptMode(QFileDialog.AcceptSave)
    return _pick_one(d)


def pick_dir(parent, title, directory=""):
    d = _file_dialog(parent, title, directory)
    d.setFileMode(QFileDialog.Directory)
    d.setOption(QFileDialog.ShowDirsOnly, True)
    return _pick_one(d)


def force_light_env():
    # MUST run before QApplication is constructed - Qt reads these at startup,
    # so setting them later has no effect.
    os.environ.pop("QT_STYLE_OVERRIDE", None)
    os.environ.pop("QT_QPA_PLATFORMTHEME", None)
    if sys.platform == "win32" and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=0"


def apply_light_theme(app):
    # Fusion: native Win/macOS styles ignore a custom palette.
    app.setStyle("Fusion")
    base_font = QFont()
    base_font.setFamilies(FONT_STACK)
    base_font.setPixelSize(FS_BODY)
    app.setFont(base_font)

    pal = QPalette()
    for role, color in _LIGHT_ROLES.items():
        pal.setColor(getattr(QPalette, role), QColor(color))
    for role, color in _DISABLED_ROLES.items():
        pal.setColor(QPalette.Disabled, getattr(QPalette, role), QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(GLOBAL_STYLESHEET)
    return app


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

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


class PrimaryButton(QPushButton):
    def __init__(self, text, icon_name=None):
        super().__init__(text)
        self.setFixedHeight(BTN_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self._icon_name = icon_name
        self.set_state("run")

    def set_state(self, state="run", text=None, icon_name=None):
        bg, fg, hover = BUTTON_STATES[state]
        border = f"1px solid {fg}" if state == "error" else "none"
        # An error button is usually disabled too - it must stay red, not grey out.
        off_bg, off_fg = (bg, fg) if state == "error" else (LINE, INK_FAINT)
        self.setStyleSheet(f"""
            QPushButton {{ background-color: {bg}; color: {fg}; font-family: {FONT_FAMILY};
                font-size: {FS_BODY}px; font-weight: bold; border-radius: {RADIUS}px;
                border: {border}; padding: 0 16px; }}
            QPushButton:hover {{ background-color: {hover}; }}
            QPushButton:disabled {{ background-color: {off_bg}; color: {off_fg}; border: {border}; }}
        """)
        if text is not None:
            self.setText(text)
        if icon_name is not None:
            self._icon_name = icon_name
        if self._icon_name:
            self.setIcon(qta.icon(self._icon_name, color=fg))


class ActionButton(PrimaryButton):
    def __init__(self, text, icon_name, is_danger=False):
        super().__init__(text, icon_name)
        self.set_state("stop" if is_danger else "accent")


class StandardTable(QTableWidget):
    def __init__(self, headers):
        super().__init__(0, len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(ROW_H)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(f"""
            QTableWidget {{ border: 1px solid {LINE}; border-radius: {RADIUS}px;
                background-color: {SURFACE}; outline: none; }}
            QTableWidget::item {{ padding: 8px; border-bottom: 1px solid {SURFACE_ALT};
                font-size: {FS_BODY}px; color: {INK}; }}
            QHeaderView::section {{ background-color: {DIM}; border: none;
                border-bottom: 1px solid {LINE}; font-size: {FS_SMALL}px;
                font-weight: bold; color: {INK_FAINT}; height: 36px; }}
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
        if not self.isEnabled():
            # INK_FAINT, not LINE: a tick in LINE on SURFACE_ALT is the same
            # grey as its background, so a disabled-but-checked box reads as
            # unchecked.
            fill, edge, tick = SURFACE_ALT, LINE, INK_FAINT
        elif self.is_checked:
            fill, edge, tick = BLUE, BLUE, SURFACE
        else:
            fill, edge, tick = SURFACE, INK_FAINT, None

        self.setStyleSheet(
            f"background-color: {fill}; border-radius: 4px; border: 2px solid {edge};"
        )
        if tick and self.is_checked:
            self.setPixmap(qta.icon("mdi.check", color=tick).pixmap(14, 14))
        else:
            self.clear()

    def changeEvent(self, event):
        super().changeEvent(event)
        # PyQt6 moves this to QEvent.Type.EnabledChange.
        if event.type() == event.EnabledChange:
            self.update_state()

    def mousePressEvent(self, event):
        if self.isEnabled() and event.button() == Qt.LeftButton:
            self.is_checked = not self.is_checked
            self.update_state()
            self.toggled.emit(self.is_checked)


class TableCheckBoxWidget(QWidget):
    def __init__(self, checked=True):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(FLAT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        self.checkbox = CustomTableCheckBox(checked)
        layout.addWidget(self.checkbox)

    @property
    def is_checked(self):
        return self.checkbox.is_checked


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
        self.filename = Path(file_path).name
        self.file_type = file_type.lower()
        self.strict_gene_parse = strict_gene_parse
        self.setStyleSheet(
            f"QFrame {{ background-color: {FIELD_BG}; border: none;"
            f" border-radius: 6px; }}"
        )
        self.setFixedHeight(ITEM_H)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(4)

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setAlignment(Qt.AlignVCenter)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(9, 9)
        top_layout.addWidget(self.status_dot)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(
            qta.icon("mdi.file-document-outline", color=INK_MUTED).pixmap(18, 18)
        )
        top_layout.addWidget(icon_lbl)

        name_lbl = QLabel(self.filename)
        name_lbl.setStyleSheet(
            f"font-size: {FS_SMALL}px; font-weight: 500; color: {INK};"
            " padding-right: 10px; border: none;"
        )
        name_lbl.setText(
            name_lbl.fontMetrics().elidedText(
                self.filename, Qt.ElideMiddle, FILENAME_MAX_W
            )
        )
        top_layout.addWidget(name_lbl)
        top_layout.addStretch()

        if self.file_type == "csv":
            self._build_column_picker(top_layout, show_dropdown)
        elif show_gene_input:
            self._build_identity_inputs(top_layout)

        del_btn = QPushButton()
        del_btn.setIcon(qta.icon("mdi.close", color=INK_FAINT))
        del_btn.setFixedSize(26, 26)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(
            f"QPushButton {{ border: none; border-radius: 13px;"
            f" background: transparent; }}"
            f"QPushButton:hover {{ background-color: {LINE}; }}"
        )
        del_btn.clicked.connect(lambda: self.remove_requested.emit(self.file_path))
        top_layout.addWidget(del_btn)

        layout.addLayout(top_layout)

        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(4)
        self.pbar.setTextVisible(False)
        self.pbar.setStyleSheet(
            f"QProgressBar {{ {FLAT} }}"
            f"QProgressBar::chunk {{ background-color: {GREEN};"
            f" border-radius: 2px; }}"
        )
        self.pbar.hide()
        layout.addWidget(self.pbar)
        self._refresh_dot()

    def _build_column_picker(self, row, visible):
        self.combo_lbl = QLabel("Species column:")
        self.combo_lbl.setStyleSheet(
            f"font-size: {FS_FIELD}px; font-weight: 600; color: {INK_MUTED};"
            " border: none;"
        )
        self.combo_lbl.setVisible(visible)
        row.addWidget(self.combo_lbl)

        self.combo = QComboBox()
        self.combo.setFixedHeight(FIELD_H)
        self.combo.setMinimumWidth(130)
        self.combo.setStyleSheet(
            f"QComboBox {{ border: 1px solid {FIELD_LINE}; border-radius: 6px;"
            f" padding: 2px 10px; font-size: {FS_FIELD}px;"
            f" background: {SURFACE}; color: {INK}; }}"
            f"QComboBox::drop-down {{ border:none; }}"
        )
        self.combo.setVisible(visible)
        row.addWidget(self.combo)

    def _build_identity_inputs(self, row):
        label_css = (
            f"font-size: {FS_TINY}px; font-weight: 800; color: {BLUE}; border: none;"
        )
        field_css = (
            f"QLineEdit {{ border: 1px solid {BLUE}; border-radius: 6px;"
            f" padding: 2px 8px; font-size: {FS_FIELD}px; font-weight: bold;"
            f" background: {SURFACE}; color: {INK}; }}"
            f"QLineEdit:focus {{ border: 2px solid {BLUE_HOVER}; }}"
        )

        org, gene = self._guess_identity()
        for attr, text, width, placeholder, value in (
            ("org", "ORG", 95, "organism", org),
            ("gene", "GENE", 80, "gene", gene),
        ):
            lbl = QLabel(text)
            lbl.setStyleSheet(label_css)
            row.addWidget(lbl)
            setattr(self, f"{attr}_lbl", lbl)

            field = QLineEdit()
            field.setFixedHeight(FIELD_H)
            field.setFixedWidth(width)
            field.setPlaceholderText(placeholder)
            field.setStyleSheet(field_css)
            field.setText(value)
            field.textChanged.connect(self._refresh_dot)
            row.addWidget(field)
            setattr(self, f"{attr}_input", field)

    def set_headers(self, headers):
        if not hasattr(self, "combo"):
            return
        current = self.combo.currentText()
        self.combo.clear()
        self.combo.addItems(headers)
        for h in headers:
            if "species" in h.lower() or "taxon" in h.lower():
                self.combo.setCurrentText(h)
                return
        if current in headers:
            self.combo.setCurrentText(current)

    def _name_tokens(self):
        return [p for p in re.split(r"[^A-Za-z0-9]+", Path(self.filename).stem) if p]

    # The manifest already holds what Tab 1 and Tab 2 recorded for a file, so
    # ask it first and fall back to the name only when it has nothing.
    def _guess_identity(self):
        org, gene = manifest_logic_tab.resolve_identity(
            t1_st1_logic.CURRENT_PROJECT_PATH, self.file_path
        )
        if not self.strict_gene_parse:
            # Pruning reads raw sequence files, where the headers carry
            # identifiers that outnumber the gene symbol. The name the user
            # typed is the more reliable source there.
            parts = self._name_tokens()
            gene = parts[1].upper() if len(parts) > 1 else ""
        return org, gene

    def get_organism(self):
        return self.org_input.text().strip() if hasattr(self, "org_input") else ""

    def get_gene_name(self):
        return self.gene_input.text().strip() if hasattr(self, "gene_input") else ""

    def get_identity(self):
        return self.get_organism(), self.get_gene_name()

    def is_complete(self):
        if not hasattr(self, "gene_input"):
            return True
        return bool(self.get_organism()) and bool(self.get_gene_name())

    def _refresh_dot(self):
        if not hasattr(self, "gene_input"):
            self.status_dot.hide()
            return
        ok = self.is_complete()
        self.status_dot.setStyleSheet(
            f"background-color: {GREEN if ok else ORANGE};"
            " border-radius: 4px; border: none;"
        )
        self.status_dot.setToolTip("ready" if ok else "organism or gene is missing")

    # val 0 means the step has started but cannot say how far along it is.
    def update_progress(self, val):
        self.pbar.show()
        if val == 0:
            self.pbar.setRange(0, 0)
        else:
            self.pbar.setRange(0, 100)
            self.pbar.setValue(val)

    def finish_progress(self):
        self.pbar.setRange(0, 100)
        self.pbar.hide()


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
        default_subdir=None,
    ):
        super().__init__()
        self.supported_exts = [ext.lower() for ext in supported_exts]
        self.show_dropdown = show_dropdown
        self.file_type = file_type
        self.show_gene_input = show_gene_input
        self.open_in_base_dir = open_in_base_dir
        self.strict_gene_parse = strict_gene_parse
        # path parts under the project root to open the browser in e.g.
        # ("Results", "Tree_Annotation"). Falls back to the file_type pipeline dir.
        self.default_subdir = default_subdir
        self.current_files = []
        self.item_widgets = {}
        self.is_drag_hover = False
        self.is_error = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._build_drop_area(format_text))
        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._build_list())

    def _build_drop_area(self, format_text):
        self.drop_area = QFrame()
        self.drop_area.setAcceptDrops(True)
        self.drop_area.setCursor(Qt.PointingHandCursor)
        self.drop_area.setFixedHeight(DROP_H_EMPTY)
        self.drop_area.setStyleSheet(f"QFrame {{ {FLAT} }}")

        col = QVBoxLayout(self.drop_area)
        col.setAlignment(Qt.AlignCenter)
        col.setSpacing(8)

        self.upload_icon = QLabel()
        self.upload_icon.setPixmap(
            qta.icon("fa5s.upload", color=INK_FAINT).pixmap(26, 26)
        )
        self.upload_icon.setAlignment(Qt.AlignCenter)
        self.upload_icon.setStyleSheet(FLAT)
        col.addWidget(self.upload_icon)

        self.main_text = QLabel(_drop_hint())
        self.main_text.setStyleSheet(_drop_text_css())
        self.main_text.setAlignment(Qt.AlignCenter)
        col.addWidget(self.main_text)

        self.sub_text = QLabel(format_text)
        self.sub_text.setStyleSheet(
            f"font-size: {FS_SMALL}px; color: {INK_FAINT}; {FLAT}"
        )
        self.sub_text.setAlignment(Qt.AlignCenter)
        col.addWidget(self.sub_text)

        self.drop_area.paintEvent = self._paint_drop_area
        self.drop_area.dragEnterEvent = self._drag_enter
        self.drop_area.dragLeaveEvent = self._drag_leave
        self.drop_area.dropEvent = self._drop
        self.drop_area.mousePressEvent = self._mouse_press
        return self.drop_area

    def _build_toolbar(self):
        self.list_toolbar = QFrame()
        self.list_toolbar.setStyleSheet(f"QFrame {{ {FLAT} }}")
        self.list_toolbar.hide()

        row = QHBoxLayout(self.list_toolbar)
        row.setContentsMargins(4, 0, 4, 0)

        self.file_count_lbl = QLabel()
        self.file_count_lbl.setStyleSheet(
            f"font-size: {FS_SMALL}px; font-weight: bold; color: {INK_MUTED}; {FLAT}"
        )
        row.addWidget(self.file_count_lbl)
        row.addStretch()

        self.add_more_btn = link_button(" Add files", "mdi.plus")
        self.add_more_btn.clicked.connect(self._open_file_dialog)
        row.addWidget(self.add_more_btn)

        self.clear_all_btn = link_button(" Clear all", "mdi.delete-outline", RED)
        self.clear_all_btn.clicked.connect(self.clear_all)
        row.addWidget(self.clear_all_btn)
        return self.list_toolbar

    def _build_list(self):
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"QScrollArea {{ {FLAT} }}")
        self.scroll_area.hide()

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.list_container)
        return self.scroll_area

    def _paint_drop_area(self, event):
        painter = QPainter(self.drop_area)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.is_error:
            pen, fill = QPen(QColor(RED), 2, Qt.DashLine), QColor(RED_FILL)
        elif self.is_drag_hover:
            pen, fill = QPen(QColor(BLUE), 2, Qt.SolidLine), QColor(BLUE_FILL)
        elif self.current_files:
            pen, fill = QPen(Qt.NoPen), QColor(DIM)
        else:
            pen, fill = QPen(QColor(FIELD_LINE), 2, Qt.DashLine), QColor(DIM)
        painter.setPen(pen)
        painter.setBrush(fill)
        painter.drawRoundedRect(self.drop_area.rect().adjusted(2, 2, -2, -2), 10, 10)

    def _drag_enter(self, event):
        if event.mimeData().hasUrls():
            self.is_drag_hover = True
            self.drop_area.update()
            event.accept()
        else:
            event.ignore()

    def _drag_leave(self, event):
        self.is_drag_hover = False
        self.drop_area.update()

    def _drop(self, event):
        self.is_drag_hover = False
        self.drop_area.update()
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        valid = [
            f
            for f in files
            if any(f.lower().endswith(ext) for ext in self.supported_exts)
        ]
        if len(valid) != len(files):
            self._trigger_error()
        if valid:
            self.add_files(valid)

    def _mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._open_file_dialog()

    def _open_file_dialog(self):
        default_dir = ""
        proj = t1_st1_logic.CURRENT_PROJECT_PATH
        if proj:
            default_dir = str(proj)
            try:
                if self.default_subdir:
                    p = Path(proj).joinpath(*self.default_subdir)
                elif self.open_in_base_dir:
                    p = None
                else:
                    p = common_utils.get_pipeline_path(
                        proj, common_utils.RESULTS, self.file_type
                    )
                if p and p.exists():
                    default_dir = str(p)
            except OSError:
                # An unreachable folder just means the dialog opens at the
                # project root instead.
                pass

        filter_str = " ".join(f"*{ext}" for ext in self.supported_exts)
        files = pick_files(
            self, "Select Files", default_dir, f"Supported Files ({filter_str})"
        )
        if files:
            self.add_files(files)

    def _trigger_error(self):
        self.is_error = True
        self.main_text.setText("Unsupported file format!")
        self.main_text.setStyleSheet(_drop_text_css(RED))
        self.drop_area.update()

        self.shake_anim = QPropertyAnimation(self.drop_area, b"pos")
        self.shake_anim.setDuration(400)
        origin = self.drop_area.pos()
        for at, dx in ((0.0, 0), (0.2, 4), (0.4, -4), (0.6, 2), (0.8, -2), (1.0, 0)):
            self.shake_anim.setKeyValueAt(at, origin + QPoint(dx, 0))
        self.shake_anim.start()
        QTimer.singleShot(1500, self._reset_error_state)

    def _reset_error_state(self):
        self.is_error = False
        self.main_text.setStyleSheet(_drop_text_css())
        # Only the wording and the border go back: the file list never changed,
        # so listeners must not be told it did.
        self.main_text.setText(_drop_hint(more=bool(self.current_files)))
        self.drop_area.update()

    def add_files(self, new_files):
        for f in new_files:
            if f in self.current_files:
                continue
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

    def get_all_identities(self):
        return {f: w.get_identity() for f, w in self.item_widgets.items()}

    def remove_file(self, file_path):
        if file_path not in self.current_files:
            return
        self.current_files.remove(file_path)
        item = self.item_widgets.pop(file_path)
        self.list_layout.removeWidget(item)
        item.deleteLater()
        self._update_ui_state()

    def clear_all(self):
        # One pass, one update: remove_file per file would rebuild every
        # listening tab's table once per file.
        for item in self.item_widgets.values():
            self.list_layout.removeWidget(item)
            item.deleteLater()
        self.current_files.clear()
        self.item_widgets.clear()
        self._update_ui_state()

    def update_file_progress(self, file_path, val):
        if file_path in self.item_widgets:
            self.item_widgets[file_path].update_progress(val)

    def finish_file_progress(self, file_path=None):
        targets = (
            self.item_widgets.values()
            if file_path is None
            else (
                [self.item_widgets[file_path]] if file_path in self.item_widgets else []
            )
        )
        for item in targets:
            item.finish_progress()

    def _update_ui_state(self):
        filled = bool(self.current_files)
        self.drop_area.setFixedHeight(DROP_H_FILLED if filled else DROP_H_EMPTY)
        self.upload_icon.setVisible(not filled)
        self.sub_text.setVisible(not filled)
        self.main_text.setText(_drop_hint(more=filled))
        self.list_toolbar.setVisible(filled)
        self.scroll_area.setVisible(filled)

        if filled:
            self.file_count_lbl.setText(f"{len(self.current_files)} File(s) added")
            row_h = ITEM_H + self.list_layout.spacing()
            self.scroll_area.setFixedHeight(
                min(row_h * len(self.current_files), LIST_MAX_H)
            )

        self.drop_area.update()
        # A copy, not the list itself: receivers keep what they are handed, and
        # a worker thread reading it must not see Clear all empty it mid-run.
        self.files_updated.emit(list(self.current_files))


class LogConsole(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogConsole")
        self.setFixedHeight(CONSOLE_H)
        self.master_logs = []

        self.setStyleSheet(
            f"QFrame#LogConsole {{ background-color: {FIELD_BG};"
            f" border: 1px solid {LINE}; border-radius: 10px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {LINE}; width: 2px; }}"
        )

        self.sys_widget, self.browser, clear_sys = self._panel("SYSTEM LOG CONSOLE")
        clear_sys.clicked.connect(self.browser.clear)

        self.wsl_widget, self.wsl_browser, clear_wsl = self._panel(
            "TERMINAL OUTPUT", mono=True
        )

        self.wsl_browser.setText(TERMINAL_READY)
        clear_wsl.clicked.connect(self.clear_wsl_log)

        self.splitter.addWidget(self.sys_widget)
        self.splitter.addWidget(self.wsl_widget)
        self.wsl_widget.hide()
        layout.addWidget(self.splitter)

    def _panel(self, title, mono=False):
        panel = QWidget()
        panel.setStyleSheet(FLAT)
        col = QVBoxLayout(panel)
        col.setContentsMargins(5, 5, 5, 5)

        head = QHBoxLayout()
        head.addWidget(caption(title))
        head.addStretch()
        clear_btn = link_button("Clear", color=INK_FAINT, hover=RED)
        head.addWidget(clear_btn)
        col.addLayout(head)

        browser = QTextBrowser()
        if mono:
            browser.setFont(mono_font(10))
            browser.setStyleSheet(
                f"QTextBrowser {{ background-color: {TERMINAL_BG}; color: {GREEN};"
                f" border: 1px solid {FIELD_LINE}; border-radius: {RADIUS}px;"
                f" padding: 8px; outline: none; }}"
            )
        else:
            browser.setStyleSheet(f"QTextBrowser {{ {FLAT} outline: none; }}")
        col.addWidget(browser)

        return panel, browser, clear_btn

    def set_wsl_mode(self, enabled):
        self.wsl_widget.setVisible(enabled)
        self.setFixedHeight(CONSOLE_H_WSL if enabled else CONSOLE_H)
        if enabled:
            self.splitter.setSizes([500, 500])

    def append_wsl_log(self, text):
        # Plain, not append(): HyPhy output holding a "<" would otherwise be
        # read as markup and vanish from the terminal panel.
        self.wsl_browser.moveCursor(QTextCursor.MoveOperation.End)
        self.wsl_browser.insertPlainText(text + "\n")
        self.wsl_browser.moveCursor(QTextCursor.MoveOperation.End)

    def clear_wsl_log(self):
        self.wsl_browser.clear()
        self.wsl_browser.insertPlainText(TERMINAL_READY + "\n")

    def append_log(self, text, default_type="info"):
        level = default_type.lower()
        body = text
        prefix = default_type.upper()

        # DOTALL: a message that explains itself over several lines must not
        # lose everything after the first.
        match = (
            re.match(r"^\[(.*?)\]\s*(.*)", text, re.DOTALL)
            if text.startswith("[")
            else None
        )
        if match:
            tag = match.group(1).lower()
            body = match.group(2)
            prefix = tag.upper()
            if tag in LOG_COLORS:
                level = tag
            else:
                for needles, mapped in LOG_ALIASES:
                    if any(n in tag for n in needles):
                        level, prefix = mapped, mapped.upper()
                        break

        color = LOG_COLORS.get(level, INK_FAINT)
        clock = QTime.currentTime().toString("hh:mm:ss")
        # escape, not a character filter: the filter dropped "/" and turned
        # every path in a message into one word.
        shown = html.escape(body).replace("\n", "<br>")
        self.browser.append(
            f'<div style="font-family: {MONO_FAMILY}; font-size: {FS_FIELD}px;'
            f' margin-bottom: 3px;">'
            f'<span style="color: {LOG_TIME};">[{clock}]</span> '
            f'<span style="color: {color}; font-weight: bold;">[{prefix}]</span> '
            f'<span style="color: {INK};">{shown}</span></div>'
        )
        self.browser.moveCursor(QTextCursor.MoveOperation.End)
        self.master_logs.append(f"[{common_utils.timestamp()}] [{prefix}] {body}")

    def export_master_log(self, project_path):
        if not self.master_logs or not project_path:
            return
        try:
            report_dir = Path(project_path) / common_utils.REPORTS / "System_Logs"
            report_dir.mkdir(parents=True, exist_ok=True)
            log_file = report_dir / f"log_report_{common_utils.mmdd()}.txt"

            bar = "=" * 50
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(
                    f"\n{bar}\nHYphlow Session Ended: {common_utils.timestamp()}\n"
                    f"{bar}\n"
                )
                f.write("\n".join(self.master_logs) + "\n\n")

            self.master_logs.clear()
        except OSError:
            # Losing the session log must not stop the app from closing.
            pass
