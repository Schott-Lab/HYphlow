import os
import re
import sys
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
    QComboBox,
    QTableWidget,
    QHeaderView,
    QTextBrowser,
    QLineEdit,
    QSplitter,
    QLayout,
    QMessageBox,
)
from PyQt5.QtCore import (
    Qt,
    pyqtSignal,
    QTimer,
    QPropertyAnimation,
    QPoint,
    QRect,
    QSize,
    QTime,
    QUrl,
)
from PyQt5.QtGui import (
    QColor,
    QPainter,
    QPen,
    QTextCursor,
    QFont,
    QPalette,
    QDesktopServices,
)
import qtawesome as qta
from hyphlow import common_utils
from hyphlow import organism_names
from hyphlow import manifest_logic_tab
from hyphlow import t1_st1_logic

DOT_GREEN = "#34C759"
DOT_ORANGE = "#FF9500"

# --- design tokens: the only place these values are defined ---
INK, INK_MUTED, INK_FAINT = "#1D1D1F", "#515154", "#8E8E93"
BLUE, GREEN, RED, ORANGE = "#0071E3", "#34C759", "#FF3B30", "#FF9500"
LINE, SURFACE, SURFACE_ALT = "#E5E5EA", "#FFFFFF", "#F2F2F7"

FONT_FAMILY = "-apple-system, 'Segoe UI', Roboto, sans-serif"
# Same stack for QFont.setFamilies, which Qt resolves against installed fonts.
# Consolas is Windows-only, Menlo macOS-only, DejaVu Sans Mono ships on Linux.
FONT_STACK = ["Segoe UI", "Roboto", "DejaVu Sans", "sans-serif"]
MONO_FAMILY = "Consolas, Menlo, 'DejaVu Sans Mono', 'Courier New', monospace"
MONO_STACK = ["Consolas", "Menlo", "DejaVu Sans Mono", "Courier New", "monospace"]


FS_TITLE, FS_BODY, FS_SMALL, FS_TINY = 16, 14, 13, 11
RADIUS, RADIUS_CARD = 8, 16
BTN_HEIGHT = 44


def mono_font(size=10):
    f = QFont()
    f.setFamilies(MONO_STACK)
    f.setPointSize(size)
    f.setStyleHint(QFont.Monospace)
    return f


# state -> (background, foreground, hover). Used by PrimaryButton.set_state.
BUTTON_STATES = {
    "run": (INK, "#FFFFFF", "#333333"),
    "accent": (BLUE, "#FFFFFF", "#005BB5"),
    "stop": (RED, "#FFFFFF", "#D70015"),
    "busy": (ORANGE, "#FFFFFF", "#E08600"),
    "error": ("#FFECEB", RED, "#FFD1CE"),
}


def open_path(path):
    """Open a file or folder in the OS file manager. Qt handles every platform."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


# Every role Qt reads. Any role left unset falls through to the desktop theme,
# which is how dialogs went dark on dark-mode machines.
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
    "BrightText": "#FFFFFF",
    "Highlight": BLUE,
    "HighlightedText": "#FFFFFF",
    "PlaceholderText": INK_FAINT,
    "Link": BLUE,
    "LinkVisited": "#5856D6",
    "Light": "#FFFFFF",
    "Midlight": "#FAFAFA",
    "Mid": LINE,
    "Dark": "#D1D1D6",
    "Shadow": "#C7C7CC",
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
QMainWindow, QDialog, QFileDialog, QMessageBox, QInputDialog {{
    background-color: {SURFACE};
    color: {INK};
}}
/* Qt does not inherit color into child widgets, so name them explicitly. */
QMessageBox QLabel, QInputDialog QLabel {{ color: {INK}; background: transparent; }}
QMessageBox QPushButton, QInputDialog QPushButton {{
    background-color: {SURFACE_ALT}; color: {INK};
    border: 1px solid #D1D1D6; border-radius: 6px; padding: 6px 16px; min-width: 72px;
}}
QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {{ background-color: #E5E5EA; }}
QMessageBox QPushButton:default, QInputDialog QPushButton:default {{
    background-color: {INK}; color: #FFFFFF; border: none;
}}
QToolTip {{ background-color: {SURFACE}; color: {INK}; border: 1px solid {LINE}; padding: 4px; }}
QMenu {{ background-color: {SURFACE}; color: {INK}; border: 1px solid {LINE}; }}
QMenu::item:selected {{ background-color: {SURFACE_ALT}; color: {INK}; }}
QComboBox QAbstractItemView {{
    background-color: {SURFACE}; color: {INK};
    selection-background-color: {SURFACE_ALT}; selection-color: {INK};
}}
QFileDialog, QFileDialog * {{ background-color: {SURFACE}; color: {INK}; }}
QFileDialog QTreeView, QFileDialog QListView, QFileDialog QTableView {{
    background-color: {SURFACE}; color: {INK};
    selection-background-color: {BLUE}; selection-color: #FFFFFF;
}}
QFileDialog QHeaderView::section {{
    background-color: {SURFACE_ALT}; color: {INK}; border: none;
    border-right: 1px solid #D1D1D6; border-bottom: 1px solid #D1D1D6; padding: 4px;
}}
QFileDialog QComboBox, QFileDialog QLineEdit {{
    background-color: #F5F5F7; color: {INK};
    border: 1px solid #D1D1D6; border-radius: 4px; padding: 3px 6px;
}}
/* without padding Qt sizes these to the raw text width and the label touches the border */
QFileDialog QPushButton {{
    background-color: #F5F5F7; color: {INK};
    border: 1px solid #D1D1D6; border-radius: 4px;
    padding: 5px 14px; min-width: 64px;
}}
QFileDialog QPushButton:hover {{ background-color: #E5E5EA; }}
QLabel#MainTitle {{ font-size: 24px; font-weight: 800; color: {INK}; background: transparent; border: none; }}
QLabel#SectionHeader {{ font-size: 20px; font-weight: 700; color: {INK}; background: transparent; border: none; }}
QLabel#SubHeader {{ font-size: 18px; font-weight: 500; color: {INK}; background: transparent; border: none; }}
QLabel#SubText {{ font-size: {FS_BODY}px; font-weight: 400; color: {INK_FAINT}; background: transparent; border: none; }}
QScrollBar:vertical {{ border: none; background: transparent; width: 8px; margin: 0px; }}
QScrollBar::handle:vertical {{ background-color: #D1D1D6; border-radius: 4px; min-height: 20px; }}
QScrollBar::handle:vertical:hover {{ background-color: {INK_FAINT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ border: none; background: none; height: 0px; }}
QScrollBar:horizontal {{ border: none; background: transparent; height: 8px; margin: 0px; }}
QScrollBar::handle:horizontal {{ background-color: #D1D1D6; border-radius: 4px; min-width: 20px; }}
QScrollBar::handle:horizontal:hover {{ background-color: {INK_FAINT}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ border: none; background: none; width: 0px; }}
"""


# Native Win/macOS file dialogs follow the OS theme and ignore our palette, so
# every picker asks for Qt's own dialog.
#
# The dialog is parented into the app, so Qt merges the ANCESTOR widget
# stylesheets into it - and several app widgets say "background: transparent",
# which paints the file list black. Ancestor sheets also outrank the application
# sheet, so GLOBAL_STYLESHEET cannot fix it. A stylesheet on the dialog itself
# outranks every ancestor, so that is where the colours have to go.
FILE_DIALOG_STYLESHEET = f"""
QWidget {{ background-color: {SURFACE}; color: {INK}; }}
QAbstractItemView {{
    background-color: {SURFACE}; color: {INK};
    alternate-background-color: {SURFACE_ALT}; outline: none;
}}
QAbstractItemView::item:selected {{ background-color: {BLUE}; color: #FFFFFF; }}
QHeaderView::section {{
    background-color: {SURFACE_ALT}; color: {INK}; border: none;
    border-right: 1px solid #D1D1D6; border-bottom: 1px solid #D1D1D6; padding: 4px;
}}
QPushButton {{
    background-color: #F5F5F7; color: {INK}; border: 1px solid #D1D1D6;
    border-radius: 4px; padding: 5px 14px; min-width: 64px;
}}
QPushButton:hover {{ background-color: {LINE}; }}
QLineEdit, QComboBox {{
    background-color: #F5F5F7; color: {INK};
    border: 1px solid #D1D1D6; border-radius: 4px; padding: 3px 6px;
}}
QComboBox QAbstractItemView {{ background-color: {SURFACE}; color: {INK}; }}
QToolButton {{ background: transparent; border: none; padding: 2px; }}
QToolButton:hover {{ background-color: {SURFACE_ALT}; border-radius: 4px; }}
"""
# Same reason as FILE_DIALOG_STYLESHEET: ancestor stylesheets outrank the
# application sheet, so the QMessageBox rules in GLOBAL_STYLESHEET never
# reach a box that is parented into the app.
MESSAGE_BOX_STYLESHEET = f"""
QMessageBox {{ background-color: {SURFACE}; }}
QMessageBox QLabel {{ background: transparent; color: {INK}; }}
QMessageBox QPushButton {{
    background-color: #F5F5F7; color: {INK}; border: 1px solid #D1D1D6;
    border-radius: 6px; padding: 6px 18px; min-width: 72px;
}}
QMessageBox QPushButton:hover {{ background-color: {LINE}; }}
QMessageBox QPushButton:default {{
    background-color: {INK}; color: #FFFFFF; border: none; font-weight: bold;
}}
"""


def message_box(parent, icon, title, text):
    """QMessageBox with the colours set on the dialog itself."""
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStyleSheet(MESSAGE_BOX_STYLESHEET)
    return box


def _file_dialog(parent, caption, directory, filter_str=""):
    d = QFileDialog(parent, caption, str(directory or ""), filter_str)
    d.setOption(QFileDialog.DontUseNativeDialog, True)
    d.setStyleSheet(FILE_DIALOG_STYLESHEET)
    return d


def pick_files(parent, caption, directory, filter_str):
    d = _file_dialog(parent, caption, directory, filter_str)
    d.setFileMode(QFileDialog.ExistingFiles)
    return d.selectedFiles() if d.exec_() else []


def pick_save(parent, caption, directory, filter_str):
    d = _file_dialog(parent, caption, directory, filter_str)
    d.setAcceptMode(QFileDialog.AcceptSave)
    picked = d.selectedFiles() if d.exec_() else []
    return picked[0] if picked else ""


def pick_dir(parent, caption, directory=""):
    d = _file_dialog(parent, caption, directory)
    d.setFileMode(QFileDialog.Directory)
    d.setOption(QFileDialog.ShowDirsOnly, True)
    picked = d.selectedFiles() if d.exec_() else []
    return picked[0] if picked else ""


def force_light_env():
    """Neutralise OS theme hooks. MUST run before QApplication is constructed.

    Qt reads these at startup, so setting them later has no effect:
      QT_STYLE_OVERRIDE     e.g. Adwaita-Dark, applied before our setStyle runs
      QT_QPA_PLATFORMTHEME  gtk3/kde plugins hand Qt the desktop's dark palette
      windows:darkmode      Qt >=5.15 paints dark title bars and frames
    """
    os.environ.pop("QT_STYLE_OVERRIDE", None)
    os.environ.pop("QT_QPA_PLATFORMTHEME", None)
    if sys.platform == "win32" and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=0"


def apply_light_theme(app):
    """Force light mode regardless of the OS theme.

    Fusion is used because the native Windows/macOS styles paint from the system
    theme and ignore a custom palette.
    """
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


class PrimaryButton(QPushButton):
    """The one primary action button. Tabs change state via set_state, never CSS."""

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
    """Secondary action. Same geometry and type scale as PrimaryButton, blue fill."""

    def __init__(self, text, icon_name, is_danger=False):
        super().__init__(text, icon_name)
        self.set_state("stop" if is_danger else "accent")


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
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(9, 9)
        top_layout.addWidget(self.status_dot)
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
            LABEL_CSS = (
                "font-size: 11px; font-weight: 800; color: #0071E3; border: none;"
            )
            FIELD_CSS = """
                QLineEdit { border: 1px solid #0071E3; border-radius: 6px; padding: 2px 8px; font-size: 12px; font-weight: bold; background: white; color: #1D1D1F; }
                QLineEdit:focus { border: 2px solid #005BB5; }
            """

            self.org_lbl = QLabel("ORG")
            self.org_lbl.setStyleSheet(LABEL_CSS)
            top_layout.addWidget(self.org_lbl)

            self.org_input = QLineEdit()
            self.org_input.setFixedHeight(28)
            self.org_input.setFixedWidth(95)
            self.org_input.setPlaceholderText("organism")
            self.org_input.setStyleSheet(FIELD_CSS)
            self.org_input.setText(self._guess_organism())
            top_layout.addWidget(self.org_input)

            self.gene_lbl = QLabel("GENE")
            self.gene_lbl.setStyleSheet(LABEL_CSS)
            top_layout.addWidget(self.gene_lbl)

            self.gene_input = QLineEdit()
            self.gene_input.setFixedHeight(28)
            self.gene_input.setFixedWidth(80)
            self.gene_input.setPlaceholderText("gene")
            self.gene_input.setStyleSheet(FIELD_CSS)
            self.gene_input.setText(self._guess_gene())
            top_layout.addWidget(self.gene_input)
            self.org_input.textChanged.connect(self._refresh_dot)
            self.gene_input.textChanged.connect(self._refresh_dot)

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
        self._refresh_dot()

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

    def _name_tokens(self):
        stem = os.path.splitext(self.filename)[0]
        return [p for p in re.split(r"[^A-Za-z0-9]+", stem) if p]

    def _guess_organism(self):

        known = set()
        try:
            proj = t1_st1_logic.CURRENT_PROJECT_PATH
            if proj:
                known = manifest_logic_tab.known_values(proj, "organism")
        except Exception:
            pass

        for token in self._name_tokens():
            if token.lower() in known:
                return token
            if organism_names.looks_like_organism(token):
                return token
        return ""

    def _guess_gene(self):
        if self.strict_gene_parse:
            return common_utils.detect_gene_from_file(self.file_path)
        parts = self._name_tokens()
        return parts[1].upper() if len(parts) > 1 else ""

    def get_organism(self):
        if hasattr(self, "org_input"):
            return self.org_input.text().strip()
        return ""

    def get_identity(self):
        return self.get_organism(), self.get_gene_name()

    def is_complete(self):
        if not hasattr(self, "gene_input"):
            return True
        return bool(self.get_organism()) and bool(self.get_gene_name())

    def _refresh_dot(self):
        if not hasattr(self, "status_dot"):
            return
        if not hasattr(self, "gene_input"):
            self.status_dot.hide()
            return
        ok = self.is_complete()
        self.status_dot.setStyleSheet(
            "background-color: %s; border-radius: 4px; border: none;"
            % (DOT_GREEN if ok else DOT_ORANGE)
        )
        self.status_dot.setToolTip("ready" if ok else "organism or gene is missing")

    def get_gene_name(self):
        if hasattr(self, "gene_input"):
            return self.gene_input.text().strip()
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
        default_subdir=None,
    ):
        super().__init__()
        self.supported_exts = [ext.lower() for ext in supported_exts]
        self.show_dropdown = show_dropdown
        self.file_type = file_type
        self.show_gene_input = show_gene_input
        self.open_in_base_dir = open_in_base_dir
        self.strict_gene_parse = strict_gene_parse
        # path parts under the project root to open the browser in, e.g.
        # ("Results", "Tree_Annotation"). Falls back to the file_type pipeline dir.
        self.default_subdir = default_subdir
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
            proj = getattr(t1_st1_logic, "CURRENT_PROJECT_PATH", None)
            if proj:
                default_dir = str(proj)
                if self.default_subdir:
                    p = Path(proj).joinpath(*self.default_subdir)
                    if p.exists():
                        default_dir = str(p)
                elif not self.open_in_base_dir:
                    p = common_utils.get_pipeline_path(proj, "Results", self.file_type)
                    if p and p.exists():
                        default_dir = str(p)
        except Exception:
            default_dir = ""

        filter_str = " ".join([f"*{ext}" for ext in self.supported_exts])
        files = pick_files(
            self, "Select Files", default_dir, f"Supported Files ({filter_str})"
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

    def get_all_identities(self):
        return {f: w.get_identity() for f, w in self.item_widgets.items()}

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
        wsl_title = QLabel("TERMINAL OUTPUT")
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
        self.wsl_browser.setFont(mono_font(10))
        self.wsl_browser.setStyleSheet(
            "QTextBrowser { background-color: #000000; color: #34C759; border: 1px solid #D1D1D6; border-radius: 8px; padding: 8px; outline: none; }"
        )
        self.wsl_browser.setText("[SYSTEM] Terminal ready. Waiting for execution...")
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
        self.wsl_browser.append("[SYSTEM] Terminal ready. Waiting for execution...")

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
        <div style="font-family: {MONO_FAMILY}; font-size: 12px; margin-bottom: 3px;">
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


def _demo():
    """Light mode must survive a dark desktop. Run: python -m hyphlow.common_ui"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["QT_STYLE_OVERRIDE"] = "Adwaita-Dark"
    os.environ["QT_QPA_PLATFORMTHEME"] = "gtk3"
    force_light_env()
    assert "QT_STYLE_OVERRIDE" not in os.environ
    assert "QT_QPA_PLATFORMTHEME" not in os.environ

    from PyQt5.QtWidgets import QApplication, QMessageBox

    app = QApplication([])
    dark = QPalette()  # what a dark desktop hands Qt
    for role in _LIGHT_ROLES:
        dark.setColor(getattr(QPalette, role), QColor("#1E1E1E"))
    app.setPalette(dark)

    apply_light_theme(app)

    for role, want in _LIGHT_ROLES.items():
        got = app.palette().color(getattr(QPalette, role)).name().lower()
        assert got == want.lower(), f"{role}: {got} != {want}"
    for role, want in _DISABLED_ROLES.items():
        got = app.palette().color(QPalette.Disabled, getattr(QPalette, role)).name()
        assert got.lower() == want.lower(), f"disabled {role}: {got} != {want}"

    def luma(c):
        return 0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()

    for role in ("Window", "Base", "Button", "Light"):
        assert luma(app.palette().color(getattr(QPalette, role))) > 200, role
    for role in ("WindowText", "Text", "ButtonText"):
        assert luma(app.palette().color(getattr(QPalette, role))) < 120, role

    box = QMessageBox(QMessageBox.Warning, "t", "m")
    box.show()
    app.processEvents()
    px = box.grab().toImage().pixelColor(3, 3)
    assert luma(px) > 200, f"popup rendered dark: {px.name()}"
    print("ok")


if __name__ == "__main__":
    _demo()
