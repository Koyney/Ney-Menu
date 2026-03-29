#!/usr/bin/env python3
"""NEY-MENU GUI — Interface PyQt5 pour PC (Windows / Linux / macOS).

Remplace la navigation clavier en console par une interface graphique moderne.
Reprend toute la logique de Ney-Menu.py (auto-MàJ, statuts, lancement des scripts).

Dépendances :
    pip install PyQt5
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import random
import shutil
import signal
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request

from PyQt5.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QSize, Qt, QThread, QTimer,
    pyqtProperty, pyqtSignal,
)
from PyQt5.QtGui import (
    QColor, QFont, QFontDatabase, QLinearGradient, QPainter, QPalette,
    QPen, QPixmap,
)
from PyQt5.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QMainWindow, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget,
)

# ── Version ────────────────────────────────────────────────────────────────────
VERSION = "2.2"

# ── URLs ───────────────────────────────────────────────────────────────────────
URL_NEYMENU = (
    "https://raw.githubusercontent.com/Koyney/Ney-Menu"
    "/refs/heads/main/Ney-Menu.pyw"
)
URL_COTUBE = (
    "https://raw.githubusercontent.com/Koyney/Ney-Tube"
    "/refs/heads/main/Ney-Tube.pyw"
)

COFLIX_FILE = "Co-flix.py"
COTUBE_FILE = "Ney-Tube.py"

_NET_CACHE: dict[str, tuple[int, float]] = {}
_CACHE_TTL = 300  # secondes

# ── Palette Void + Volt ────────────────────────────────────────────────────────
VOID      = "#09090b"
VOID_2    = "#111116"
VOID_3    = "#1c1c24"
VOLT      = "#c6f135"
VOLT_DIM  = "#8ab524"
VOLT_DARK = "#2a3a00"
TEXT_MAIN = "#eaeaea"
TEXT_DIM  = "#5a5a6e"
TEXT_WARN = "#f5a623"
TEXT_ERR  = "#f53c3c"
TEXT_OK   = "#4cd97b"
BORDER    = "#1f1f2e"
BORDER_LT = "#2e2e42"


# ══════════════════════════════════════════════════════════════════════════════
#  Logique Koyney (plateforme, réseau, scripts)
# ══════════════════════════════════════════════════════════════════════════════
def _py_dir() -> str:
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local"
        )
        d = os.path.join(local, "Koyney", "Ney-Menu")
    else:
        d = os.path.join(
            os.path.expanduser("~"), ".local", "share", "Koyney", "Ney-Menu"
        )
    os.makedirs(d, exist_ok=True)
    return d


def _get_remote_size(url: str) -> int:
    now = time.time()
    cached = _NET_CACHE.get(url)
    if cached:
        size, ts = cached
        if now - ts < _CACHE_TTL:
            return size
    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": "curl/termux"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            size = int(resp.headers.get("Content-Length", 0) or 0)
    except Exception:
        size = 0
    _NET_CACHE[url] = (size, now)
    return size


def _cleanup_pycache() -> None:
    cache = os.path.join(_py_dir(), "__pycache__")
    try:
        if os.path.isdir(cache):
            shutil.rmtree(cache, ignore_errors=True)
    except Exception:
        pass


def _open_in_terminal(script_path: str) -> None:
    """Lance un script Python dans un nouveau terminal selon la plateforme."""
    py = sys.executable
    if os.name == "nt":
        subprocess.Popen(
            ["cmd", "/c", "start", "cmd", "/k", py, script_path],
            close_fds=True,
        )
    elif sys.platform == "darwin":
        apple = (
            f'tell application "Terminal" to do script '
            f'"{py} {script_path}"'
        )
        subprocess.Popen(["osascript", "-e", apple])
    else:
        for term in ("gnome-terminal", "xterm", "konsole", "xfce4-terminal"):
            try:
                if term == "gnome-terminal":
                    subprocess.Popen([term, "--", py, script_path])
                else:
                    subprocess.Popen([term, "-e", f"{py} {script_path}"])
                return
            except FileNotFoundError:
                continue
        subprocess.Popen([py, script_path])


# ══════════════════════════════════════════════════════════════════════════════
#  Workers QThread
# ══════════════════════════════════════════════════════════════════════════════
class SelfUpdateWorker(QThread):
    log  = pyqtSignal(str, str)   # (message, niveau: "info"|"ok"|"warn")
    done = pyqtSignal(str)        # "ok" | "updated"

    def run(self) -> None:
        current_path = os.path.abspath(__file__)
        self.log.emit("Vérification de Ney-Menu depuis GitHub…", "info")
        try:
            cb  = random.randint(100000, 999999)
            url = f"{URL_NEYMENU}?cb={cb}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "curl/termux", "Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    raise ValueError(f"HTTP {resp.status}")
                remote = resp.read()
        except Exception as exc:
            self.log.emit(f"Réseau indisponible — {exc}", "warn")
            self.done.emit("ok")
            return

        if len(remote) < 5000:
            self.log.emit("Réponse suspecte — MàJ ignorée.", "warn")
            self.done.emit("ok")
            return

        remote_hash = hashlib.sha256(remote).hexdigest()
        local_hash  = ""
        if os.path.isfile(current_path):
            with open(current_path, "rb") as f:
                local_hash = hashlib.sha256(f.read()).hexdigest()

        if remote_hash == local_hash:
            self.log.emit("Ney-Menu est à jour.", "ok")
            self.done.emit("ok")
            return

        self.log.emit("Nouvelle version détectée — mise à jour…", "info")
        try:
            parent = os.path.dirname(current_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(current_path, "wb") as f:
                f.write(remote)
        except Exception as exc:
            self.log.emit(f"Écriture échouée : {exc}", "warn")
            self.done.emit("ok")
            return

        self.done.emit("updated")


class StatusWorker(QThread):
    result = pyqtSignal(list)  # list[tuple[label, badge_text, status_key]]

    def run(self) -> None:
        py       = _py_dir()
        statuses = []

        path = os.path.join(py, COTUBE_FILE)
        if not os.path.isfile(path):
            statuses.append(("Ney-Tube", "Manquant", "missing"))
        else:
            rs = _get_remote_size(URL_COTUBE)
            ls = os.path.getsize(path)
            if rs <= 0:
                statuses.append(("Ney-Tube", "Inconnu", "unknown"))
            elif abs(rs - ls) <= 1:
                statuses.append(("Ney-Tube", "À jour", "ok"))
            else:
                d = rs - ls
                statuses.append(("Ney-Tube", f"MàJ ({'+' if d > 0 else ''}{d}o)", "update"))

        coflix_path = os.path.join(py, COFLIX_FILE)
        if os.path.isfile(coflix_path):
            statuses.append(("Co-flix", "Présent", "ok"))

        self.result.emit(statuses)


class UpdateWorker(QThread):
    log      = pyqtSignal(str, str)
    progress = pyqtSignal(int)
    done     = pyqtSignal(bool)

    def run(self) -> None:
        py   = _py_dir()
        dest = os.path.join(py, COTUBE_FILE)
        self.log.emit("Téléchargement de Ney-Tube…", "info")
        try:
            req = urllib.request.Request(
                URL_COTUBE, headers={"User-Agent": "curl/termux"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                total      = int(resp.headers.get("Content-Length", 0) or 0)
                downloaded = 0
                chunks: list[bytes] = []
                while True:
                    buf = resp.read(8192)
                    if not buf:
                        break
                    chunks.append(buf)
                    downloaded += len(buf)
                    if total > 0:
                        self.progress.emit(min(int(downloaded * 100 / total), 100))
            with open(dest, "wb") as f:
                for c in chunks:
                    f.write(c)
            _NET_CACHE.pop(URL_COTUBE, None)
            self.log.emit("Ney-Tube mis à jour avec succès.", "ok")
            self.done.emit(True)
        except Exception as exc:
            self.log.emit(f"Erreur : {exc}", "warn")
            self.done.emit(False)


# ══════════════════════════════════════════════════════════════════════════════
#  Widgets personnalisés
# ══════════════════════════════════════════════════════════════════════════════

class VoltSeparator(QWidget):
    """Ligne horizontale fine, couleur Volt."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(VOID))
        grad.setColorAt(0.3, QColor(VOLT_DIM))
        grad.setColorAt(0.7, QColor(VOLT_DIM))
        grad.setColorAt(1.0, QColor(VOID))
        p.fillRect(self.rect(), grad)


class StatusChip(QWidget):
    """Badge de statut arrondi style pill."""

    _STYLES = {
        "ok":      (TEXT_OK,   "#0d2e1a", "●"),
        "update":  (TEXT_WARN, "#2e1e00", "↑"),
        "missing": (TEXT_ERR,  "#2e0d0d", "✕"),
        "unknown": (TEXT_DIM,  VOID_2,    "?"),
        "loading": (TEXT_DIM,  VOID_2,    "…"),
    }

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label = label
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._lbl_name = QLabel(label)
        self._lbl_name.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 12px; font-weight: 600;"
            " letter-spacing: 1px; background: transparent; border: none;"
        )

        self._lbl_badge = QLabel()
        self._lbl_badge.setStyleSheet(
            f"font-size: 12px; font-weight: 700; padding: 2px 10px;"
            f" border-radius: 10px; background: {VOID_2}; color: {TEXT_DIM};"
        )

        layout.addWidget(self._lbl_name)
        layout.addWidget(self._lbl_badge)
        self.set_status("loading", "")

    def set_status(self, status: str, badge: str) -> None:
        fg, bg, icon = self._STYLES.get(status, (TEXT_DIM, VOID_2, "?"))
        text = f"{icon}  {badge}" if badge else icon
        self._lbl_badge.setText(text)
        self._lbl_badge.setStyleSheet(
            f"font-size: 12px; font-weight: 700; padding: 2px 10px;"
            f" border-radius: 10px; background: {bg}; color: {fg};"
            " border: none;"
        )


class MenuButton(QFrame):
    """Bouton de menu (QFrame) — évite les artefacts de fond des QPushButton."""

    clicked = pyqtSignal()

    def __init__(
        self,
        label: str,
        sublabel: str = "",
        accent: bool = False,
        danger: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._accent  = accent
        self._danger  = danger
        self._hovered = False
        self._enabled = True

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(68)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(0)

        # Textes
        texts = QVBoxLayout()
        texts.setSpacing(3)

        self._lbl_main = QLabel(label)
        font_main = QFont()
        font_main.setPointSize(13)
        font_main.setWeight(QFont.Bold)
        self._lbl_main.setFont(font_main)
        self._lbl_main.setAttribute(Qt.WA_TransparentForMouseEvents)

        texts.addWidget(self._lbl_main)
        if sublabel:
            self._lbl_sub = QLabel(sublabel)
            self._lbl_sub.setAttribute(Qt.WA_TransparentForMouseEvents)
            texts.addWidget(self._lbl_sub)
        else:
            self._lbl_sub = None

        # Flèche droite
        self._arrow = QLabel("›")
        self._arrow.setAttribute(Qt.WA_TransparentForMouseEvents)

        layout.addLayout(texts)
        layout.addStretch()
        layout.addWidget(self._arrow)

        self._refresh_style(False)

    def _refresh_style(self, hovered: bool) -> None:
        if not self._enabled:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {VOID_2};
                    border: 1.5px solid {BORDER};
                    border-radius: 10px;
                }}
                QLabel {{
                    border: none;
                    background: transparent;
                }}
            """)
            self._lbl_main.setStyleSheet("color: #3a3a4a; border: none; background: transparent;")
            if self._lbl_sub:
                self._lbl_sub.setStyleSheet("color: #2a2a38; font-size: 11px; border: none; background: transparent;")
            self._arrow.setStyleSheet("font-size: 22px; color: #2a2a38; border: none; background: transparent;")
            return

        if self._danger:
            bg    = "#1a0a0a" if hovered else VOID_2
            fg    = TEXT_ERR
            bord  = TEXT_ERR  if hovered else BORDER
            sub   = "#7a2020" if hovered else TEXT_DIM
            arrow = TEXT_ERR  if hovered else TEXT_DIM
        elif self._accent:
            bg    = VOLT_DARK if hovered else VOID_2
            fg    = VOLT      if hovered else TEXT_MAIN
            bord  = VOLT      if hovered else BORDER_LT
            sub   = VOLT_DIM  if hovered else TEXT_DIM
            arrow = VOLT      if hovered else TEXT_DIM
        else:
            bg    = VOID_3    if hovered else VOID_2
            fg    = TEXT_MAIN
            bord  = BORDER_LT if hovered else BORDER
            sub   = TEXT_DIM
            arrow = TEXT_MAIN if hovered else TEXT_DIM

        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 1.5px solid {bord};
                border-radius: 10px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        self._lbl_main.setStyleSheet(f"color: {fg}; border: none; background: transparent;")
        if self._lbl_sub:
            self._lbl_sub.setStyleSheet(f"color: {sub}; font-size: 11px; border: none; background: transparent;")
        self._arrow.setStyleSheet(f"font-size: 22px; color: {arrow}; border: none; background: transparent;")

    def setEnabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        self._refresh_style(False)

    def isEnabled(self) -> bool:
        return self._enabled

    def enterEvent(self, e):
        if self._enabled:
            self._hovered = True
            self._refresh_style(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovered = False
        self._refresh_style(self._hovered)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if self._enabled and e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class InlineUpdateButton(QFrame):
    """Petit bouton ↓ inline pour MàJ d'un script individuel."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered = False
        self._enabled = True

        self.setFixedSize(52, 68)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._icon = QLabel("↓")
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._txt = QLabel("MàJ")
        self._txt.setAlignment(Qt.AlignCenter)
        self._txt.setAttribute(Qt.WA_TransparentForMouseEvents)

        layout.addStretch()
        layout.addWidget(self._icon)
        layout.addWidget(self._txt)
        layout.addStretch()

        self._refresh_style(False)

    def _refresh_style(self, hovered: bool) -> None:
        if not self._enabled:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {VOID_2};
                    border: 1.5px solid {BORDER};
                    border-radius: 10px;
                }}
                QLabel {{
                    border: none;
                    background: transparent;
                }}
            """)
            self._icon.setStyleSheet("font-size: 16px; color: #2a2a38; border: none; background: transparent;")
            self._txt.setStyleSheet("font-size: 9px; color: #2a2a38; letter-spacing: 1px; border: none; background: transparent;")
            return

        if hovered:
            bg   = VOLT_DARK
            bord = VOLT
            fg   = VOLT
        else:
            bg   = VOID_2
            bord = BORDER_LT
            fg   = TEXT_DIM

        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 1.5px solid {bord};
                border-radius: 10px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        self._icon.setStyleSheet(f"font-size: 16px; color: {fg}; border: none; background: transparent;")
        self._txt.setStyleSheet(
            f"font-size: 9px; color: {fg}; letter-spacing: 1px; font-weight: 700; border: none; background: transparent;"
        )

    def setEnabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        self._refresh_style(False)

    def enterEvent(self, e):
        if self._enabled:
            self._hovered = True
            self._refresh_style(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovered = False
        self._refresh_style(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if self._enabled and e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class LogBar(QWidget):
    """Barre de log en bas avec point coloré et texte glissant."""

    _COLORS = {
        "info": TEXT_DIM,
        "ok":   TEXT_OK,
        "warn": TEXT_WARN,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")

        self._msg = QLabel("Initialisation…")
        self._msg.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        self._msg.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout.addWidget(self._dot)
        layout.addWidget(self._msg)

    def push(self, msg: str, level: str = "info") -> None:
        color = self._COLORS.get(level, TEXT_DIM)
        self._dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        self._msg.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._msg.setText(msg)


# ══════════════════════════════════════════════════════════════════════════════
#  Fenêtre principale
# ══════════════════════════════════════════════════════════════════════════════
class NeyMenuWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"NEY-MENU  v{VERSION}")
        self.setMinimumSize(540, 580)
        self.resize(600, 660)
        self.setStyleSheet(f"background: {VOID};")

        self._workers: list[QThread] = []
        self._coflix_present = False

        self._build_ui()
        QTimer.singleShot(0, self._start_init)

    # ── Construction UI ────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QWidget()
        root.setStyleSheet(f"background: {VOID};")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 20, 24, 16)
        outer.setSpacing(14)

        # ── En-tête ────────────────────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background: {VOID_2};
                border: 1px solid {BORDER_LT};
                border-radius: 12px;
            }}
        """)
        hl = QVBoxLayout(header)
        hl.setContentsMargins(24, 18, 24, 18)
        hl.setSpacing(4)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(0)

        title = QLabel("NEY")
        title.setStyleSheet(
            f"color: {VOLT}; font-size: 40px; font-weight: 900;"
            " letter-spacing: 6px; background: transparent; border: none;"
        )
        dash = QLabel("─")
        dash.setStyleSheet(
            f"color: {VOLT_DIM}; font-size: 20px; background: transparent; border: none;"
        )
        menu_lbl = QLabel("MENU")
        menu_lbl.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 40px; font-weight: 900;"
            " letter-spacing: 6px; background: transparent; border: none;"
        )
        brand_row.addStretch()
        brand_row.addWidget(title)
        brand_row.addWidget(dash)
        brand_row.addWidget(menu_lbl)
        brand_row.addStretch()

        sub = QLabel("K O Y N E Y   S U I T E")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 10px; letter-spacing: 5px;"
            " background: transparent; border: none;"
        )

        hl.addLayout(brand_row)
        hl.addWidget(sub)
        outer.addWidget(header)

        # ── Statuts ────────────────────────────────────────────────────────────
        status_card = QFrame()
        status_card.setStyleSheet(f"""
            QFrame {{
                background: {VOID_2};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)
        sl = QHBoxLayout(status_card)
        sl.setContentsMargins(18, 10, 18, 10)
        sl.setSpacing(0)

        slabel = QLabel("SCRIPTS")
        slabel.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 9px; letter-spacing: 4px;"
            " font-weight: 700; background: transparent; border: none;"
        )

        self._chip_neytube = StatusChip("NEY-TUBE")
        self._chip_coflix  = StatusChip("CO-FLIX")
        self._chip_coflix.hide()

        sl.addWidget(slabel)
        sl.addStretch()
        sl.addWidget(self._chip_neytube)
        sl.addSpacing(16)
        sl.addWidget(self._chip_coflix)
        outer.addWidget(status_card)

        # ── Séparateur Volt ────────────────────────────────────────────────────
        outer.addWidget(VoltSeparator())

        # ── Section titre ──────────────────────────────────────────────────────
        section_lbl = QLabel("QUE VOULEZ-VOUS FAIRE ?")
        section_lbl.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 9px; letter-spacing: 4px; font-weight: 700;"
        )
        outer.addWidget(section_lbl)

        # ── Boutons ────────────────────────────────────────────────────────────

        # Co-flix (pas de bouton MàJ)
        self._btn_coflix = MenuButton(
            "🎬  Films / Séries",
            sublabel="CO-FLIX",
            accent=True,
        )
        self._btn_coflix.clicked.connect(self._action_coflix)
        self._row_coflix = QWidget()
        self._row_coflix.setStyleSheet("background: transparent;")
        rl_cf = QHBoxLayout(self._row_coflix)
        rl_cf.setContentsMargins(0, 0, 0, 0)
        rl_cf.setSpacing(8)
        rl_cf.addWidget(self._btn_coflix, 1)
        self._row_coflix.hide()
        outer.addWidget(self._row_coflix)

        # Ney-Tube + bouton MàJ inline
        self._btn_neytube = MenuButton(
            "▶  YouTube",
            sublabel="NEY-TUBE",
            accent=True,
        )
        self._btn_neytube.clicked.connect(self._action_neytube)

        self._btn_upd_neytube = InlineUpdateButton()
        self._btn_upd_neytube.clicked.connect(self._action_update_neytube)

        row_nt = QWidget()
        row_nt.setStyleSheet("background: transparent;")
        rl_nt = QHBoxLayout(row_nt)
        rl_nt.setContentsMargins(0, 0, 0, 0)
        rl_nt.setSpacing(8)
        rl_nt.addWidget(self._btn_neytube, 1)
        rl_nt.addWidget(self._btn_upd_neytube)
        outer.addWidget(row_nt)

        self._btn_quit = MenuButton("✕  Quitter", danger=True)
        self._btn_quit.clicked.connect(self._goodbye)
        outer.addWidget(self._btn_quit)

        outer.addStretch()

        # ── Barre de progression ───────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background: {BORDER};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {VOLT};
                border-radius: 2px;
            }}
        """)
        self._progress.hide()
        outer.addWidget(self._progress)

        # ── Log + version ──────────────────────────────────────────────────────
        foot = QHBoxLayout()
        self._logbar = LogBar()
        ver_lbl = QLabel(f"v{VERSION}")
        ver_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")

        foot.addWidget(self._logbar, 1)
        foot.addWidget(ver_lbl)
        outer.addLayout(foot)

    # ── Séquence d'init ────────────────────────────────────────────────────────
    def _start_init(self) -> None:
        self._set_menu_enabled(False)
        w = SelfUpdateWorker()
        w.log.connect(self._on_log)
        w.done.connect(self._on_self_update_done)
        self._track(w)
        w.start()

    def _on_self_update_done(self, result: str) -> None:
        if result == "updated":
            self._logbar.push("Relancement avec la nouvelle version…", "ok")
            QTimer.singleShot(1500, self._relaunch)
            return
        self._check_statuses()

    def _check_statuses(self) -> None:
        self._logbar.push("Vérification des statuts…", "info")
        w = StatusWorker()
        w.result.connect(self._on_statuses)
        self._track(w)
        w.start()

    def _on_statuses(self, statuses: list) -> None:
        coflix_present = False
        for label, badge, status in statuses:
            if label == "Ney-Tube":
                self._chip_neytube.set_status(status, badge)
            elif label == "Co-flix":
                self._chip_coflix.set_status(status, badge)
                self._chip_coflix.show()
                coflix_present = True

        self._coflix_present = coflix_present
        self._row_coflix.setVisible(coflix_present)

        self._set_menu_enabled(True)
        self._logbar.push("Prêt.", "ok")

    # ── Actions menu ───────────────────────────────────────────────────────────
    def _action_coflix(self) -> None:
        path = os.path.join(_py_dir(), COFLIX_FILE)
        if not os.path.isfile(path):
            self._logbar.push("Co-flix introuvable.", "warn")
            return
        self._logbar.push("Lancement de Co-flix…", "info")
        _open_in_terminal(path)

    def _action_neytube(self) -> None:
        path = os.path.join(_py_dir(), COTUBE_FILE)
        if not os.path.isfile(path):
            self._logbar.push("Ney-Tube introuvable — faites une mise à jour.", "warn")
            return
        self._logbar.push("Lancement de Ney-Tube…", "info")
        _open_in_terminal(path)

    def _action_update_neytube(self) -> None:
        self._action_update()

    def _action_update(self) -> None:
        self._set_menu_enabled(False)
        self._progress.setValue(0)
        self._progress.show()
        w = UpdateWorker()
        w.log.connect(self._on_log)
        w.progress.connect(self._progress.setValue)
        w.done.connect(self._on_update_done)
        self._track(w)
        w.start()

    def _on_update_done(self, _ok: bool) -> None:
        self._progress.hide()
        self._check_statuses()

    def _goodbye(self) -> None:
        _cleanup_pycache()
        self.close()

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _on_log(self, msg: str, level: str) -> None:
        self._logbar.push(msg, level)

    def _set_menu_enabled(self, enabled: bool) -> None:
        for btn in (self._btn_coflix, self._btn_neytube, self._btn_upd_neytube, self._btn_quit):
            btn.setEnabled(enabled)

    def _track(self, worker: QThread) -> None:
        self._workers.append(worker)
        worker.finished.connect(
            lambda: self._workers.remove(worker)
            if worker in self._workers
            else None
        )

    def _relaunch(self) -> None:
        subprocess.Popen([sys.executable, os.path.abspath(__file__)] + sys.argv[1:])
        QApplication.quit()

    def closeEvent(self, e):
        for w in list(self._workers):
            w.quit()
            w.wait(400)
        e.accept()


# ══════════════════════════════════════════════════════════════════════════════
#  Point d'entrée
# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    # HiDPI
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("NEY-MENU")
    app.setStyle("Fusion")

    # Palette Fusion sombre
    pal = QPalette()
    pal.setColor(QPalette.Window,          QColor(VOID))
    pal.setColor(QPalette.WindowText,      QColor(TEXT_MAIN))
    pal.setColor(QPalette.Base,            QColor(VOID_2))
    pal.setColor(QPalette.AlternateBase,   QColor(VOID_3))
    pal.setColor(QPalette.Button,          QColor(VOID_2))
    pal.setColor(QPalette.ButtonText,      QColor(TEXT_MAIN))
    pal.setColor(QPalette.Highlight,       QColor(VOLT))
    pal.setColor(QPalette.HighlightedText, QColor(VOID))
    pal.setColor(QPalette.Text,            QColor(TEXT_MAIN))
    pal.setColor(QPalette.BrightText,      QColor(VOLT))
    pal.setColor(QPalette.Link,            QColor(VOLT))
    app.setPalette(pal)

    win = NeyMenuWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        main()
    except Exception as _err:
        print(f"\nERREUR CRITIQUE : {_err}\n")
        traceback.print_exc()
        sys.exit(1)