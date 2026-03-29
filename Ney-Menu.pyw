#!/usr/bin/env python3
"""NEY-MENU — Lance CO-FLIX (optionnel) et NEY-TUBE.

Sur PC (Windows / Linux / macOS) : interface graphique PyQt5.
Sur Termux / Android              : interface console colorée (saisie numérique).

Les scripts sont stockés dans le dossier Koyney/Ney-Menu et téléchargés/mis à
jour automatiquement depuis GitHub. Ney-Menu lui-même peut aussi se mettre à
jour au démarrage.

Dépendances PC :
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

try:
    import ctypes
except ImportError:
    ctypes = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore[assignment]

try:
    import tty
    import termios
    import select
except ImportError:
    tty = termios = select = None  # type: ignore[assignment]


# ── Détection plateforme ──────────────────────────────────────────────────────
def _is_termux() -> bool:
    """Retourne True si l'exécution se fait dans Termux (Android)."""
    return os.name != "nt" and (
        "ANDROID_STORAGE" in os.environ
        or "com.termux" in os.environ.get("PREFIX", "")
    )


_TERMUX = _is_termux()

# ── Imports PyQt5 (PC uniquement — ignorés sous Termux) ──────────────────────
if not _TERMUX:
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

# ── État des scripts (interface console) ──────────────────────────────────────
_SCRIPT_STATUSES: list[tuple[str, str, str]] = []

# ── Palette Void + Volt (PC) ───────────────────────────────────────────────────
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
#  Fonctions communes (PC + Termux)
# ══════════════════════════════════════════════════════════════════════════════
def _py_dir() -> str:
    """Retourne le dossier de stockage des scripts enfants (créé si absent).

    - Windows          : %LOCALAPPDATA%\\Koyney\\Ney-Menu\\
    - Termux / Android : ~/.local/Koyney/Ney-Menu/
    - Linux / macOS    : ~/.local/share/Koyney/Ney-Menu/
    """
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local"
        )
        d = os.path.join(local, "Koyney", "Ney-Menu")
    elif _TERMUX:
        d = os.path.join(
            os.path.expanduser("~"), ".local", "Koyney", "Ney-Menu"
        )
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


def _invalidate_cache(url: str) -> None:
    """Supprime l'entrée de cache pour forcer un rechargement."""
    _NET_CACHE.pop(url, None)


def _cleanup_pycache() -> None:
    cache = os.path.join(_py_dir(), "__pycache__")
    try:
        if os.path.isdir(cache):
            shutil.rmtree(cache, ignore_errors=True)
    except Exception:
        pass


def _open_in_terminal(script_path: str) -> None:
    """Lance un script Python dans un nouveau terminal selon la plateforme (PC)."""
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
#  Interface console (Termux / Android)
# ══════════════════════════════════════════════════════════════════════════════
class ConsoleUI:
    """Interface console colorée : navigation PC (flèches) et Termux (numéros)."""

    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[31m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    CYAN   = "\033[36m"

    MAX_VISIBLE = 6  # lignes d'options visibles simultanément

    # ── ANSI Windows ──────────────────────────────────────────────────────────
    @staticmethod
    def enable_ansi() -> None:
        """Active les séquences ANSI dans la console Windows si possible."""
        if os.name == "nt" and ctypes is not None:
            try:
                k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                k32.SetConsoleMode(k32.GetStdHandle(-11), 7)
            except Exception:  # pylint: disable=broad-except
                pass

    @staticmethod
    def clear() -> None:
        """Efface le terminal."""
        os.system("cls" if os.name == "nt" else "clear")

    # ── Largeur visuelle (CJK / emoji = 2 colonnes) ───────────────────────────
    @staticmethod
    def display_len(text: str) -> int:
        """Retourne la largeur visuelle d'une chaîne (emoji/CJK comptent double)."""
        count = 0
        for ch in text:
            cp = ord(ch)
            if cp in (0xFE0E, 0xFE0F, 0x200D, 0x20E3):
                continue
            if 0x0300 <= cp <= 0x036F:
                continue
            wide = (
                0x1F000 <= cp <= 0x1FFFF
                or 0x2600 <= cp <= 0x27BF
                or 0x2B00 <= cp <= 0x2BFF
                or 0xFE30 <= cp <= 0xFE4F
                or 0x2E80 <= cp <= 0x2EFF
                or 0x3000 <= cp <= 0x9FFF
                or 0xF900 <= cp <= 0xFAFF
                or 0xAC00 <= cp <= 0xD7AF
            )
            count += 2 if wide else 1
        return count

    # ── Bannière ASCII ────────────────────────────────────────────────────────
    @staticmethod
    def print_banner() -> None:
        """Affiche la bannière NEY-MENU."""
        print(
            ConsoleUI.CYAN
            + r"""
╔════════════════════════════════════════════════════════════════════════════╗
║  ███╗   ██╗███████╗██╗   ██╗      ███╗   ███╗███████╗███╗   ██╗██╗   ██╗   ║
║  ████╗  ██║██╔════╝╚██╗ ██╔╝      ████╗ ████║██╔════╝████╗  ██║██║   ██║   ║
║  ██╔██╗ ██║█████╗   ╚████╔╝ █████╗██╔████╔██║█████╗  ██╔██╗ ██║██║   ██║   ║
║  ██║╚██╗██║██╔══╝    ╚██╔╝  ╚════╝██║╚██╔╝██║██╔══╝  ██║╚██╗██║██║   ██║   ║
║  ██║ ╚████║███████╗   ██║         ██║ ╚═╝ ██║███████╗██║ ╚████║╚██████╔╝   ║
║  ╚═╝  ╚═══╝╚══════╝   ╚═╝         ╚═╝     ╚═╝╚══════╝╚═╝  ╚═══╝ ╚═════╝    ║
╚════════════════════════════════════════════════════════════════════════════╝"""
            + ConsoleUI.RESET
        )

    # ── Panneau de statut (PC) ────────────────────────────────────────────────
    @staticmethod
    def print_status_panel(box_w: int = 62) -> None:
        """Affiche le panneau ETAT DES SCRIPTS (2 entrées par ligne)."""
        if not _SCRIPT_STATUSES:
            return
        C     = ConsoleUI
        inner = box_w - 2
        half  = inner // 2
        hdr      = " ETAT DES SCRIPTS "
        hdr_vlen = C.display_len(hdr)
        eq_left  = (inner - hdr_vlen) // 2
        eq_right = inner - hdr_vlen - eq_left
        print(
            f"  {C.CYAN}╔{'═' * eq_left}"
            f"{C.BOLD}{hdr}{C.RESET}"
            f"{C.CYAN}{'═' * eq_right}╗{C.RESET}"
        )
        entries = list(_SCRIPT_STATUSES)
        if len(entries) % 2:
            entries.append(None)  # type: ignore[arg-type]
        for i in range(0, len(entries), 2):
            left  = ConsoleUI._fmt_status_cell(entries[i],     half)
            right = ConsoleUI._fmt_status_cell(entries[i + 1], half)
            print(f"  {C.CYAN}║{C.RESET}{left}{right}{C.CYAN}║{C.RESET}")
        print(f"  {C.CYAN}╚{'═' * inner}╝{C.RESET}")

    @staticmethod
    def _fmt_status_cell(
        entry: tuple[str, str, str] | None, width: int
    ) -> str:
        """Formate une cellule du panneau sur `width` colonnes visuelles."""
        if entry is None:
            return " " * width
        label, badge_plain, color = entry
        label_trunc  = label[:11]
        content_vlen = (
            2
            + ConsoleUI.display_len(label_trunc)
            + 2
            + ConsoleUI.display_len(badge_plain)
        )
        pad = " " * max(0, width - content_vlen)
        return (
            f"  {label_trunc}  "
            f"{color}{badge_plain}{ConsoleUI.RESET}"
            f"{pad}"
        )

    # ── Panneau de statut Termux (liste compacte) ─────────────────────────────
    @staticmethod
    def print_status_panel_termux() -> None:
        """Affiche le panneau de statut pour Termux (format liste verticale)."""
        if not _SCRIPT_STATUSES:
            return
        C = ConsoleUI
        print(f"  {C.DIM}{'─' * 42}{C.RESET}")
        for label, badge, color in _SCRIPT_STATUSES:
            pad = " " * max(0, 13 - C.display_len(label))
            print(f"  {label}{pad}{color}{badge}{C.RESET}")
        print(f"  {C.DIM}{'─' * 42}{C.RESET}")

    # ── Menu PC (boîte + curseur visuel) ──────────────────────────────────────
    @staticmethod
    def show_menu(
        options: list[str],
        title: str = "MENU",
        selected_index: int = 0,
        subtitle: str = "",
        show_status: bool = False,
    ) -> None:
        """Affiche le menu interactif PC avec boîte et curseur visuel."""
        box_w = 62
        ConsoleUI.clear()
        ConsoleUI.print_banner()
        if show_status:
            print()
            ConsoleUI.print_status_panel(box_w)
        elif subtitle:
            print(f"\n  {ConsoleUI.DIM}{subtitle}{ConsoleUI.RESET}")
        print()
        visible = min(len(options), ConsoleUI.MAX_VISIBLE)
        half    = visible // 2
        top     = max(0, min(selected_index - half, len(options) - visible))
        h_line      = "=" * box_w
        title_vlen  = ConsoleUI.display_len(title)
        title_pad_l = max(0, (box_w - title_vlen) // 2)
        title_pad_r = max(0, box_w - title_vlen - title_pad_l)
        print(f"  +{h_line}+")
        print(
            f"  |{' ' * title_pad_l}"
            f"{ConsoleUI.BOLD}{ConsoleUI.CYAN}{title}{ConsoleUI.RESET}"
            f"{' ' * title_pad_r}|"
        )
        print(f"  +{h_line}+")
        if top > 0:
            arrow_up = f"^  {top} element(s) plus haut"
            pad_r    = " " * max(0, box_w - 2 - ConsoleUI.display_len(arrow_up))
            print(f"  |  {ConsoleUI.CYAN}{arrow_up}{ConsoleUI.RESET}{pad_r}|")
        else:
            print(f"  |{' ' * box_w}|")
        inner    = box_w - 4
        max_text = inner - 3
        for i in range(top, top + visible):
            raw = options[i]
            if ConsoleUI.display_len(raw) > max_text:
                accum: list[str] = []
                width = 0
                for ch in raw:
                    cw = 2 if ConsoleUI.display_len(ch) == 2 else 1
                    if width + cw > max_text - 1:
                        break
                    accum.append(ch)
                    width += cw
                raw = "".join(accum) + "..."
            prefix       = ">  " if i == selected_index else "   "
            visible_text = prefix + raw
            pad_r        = " " * max(0, inner - ConsoleUI.display_len(visible_text))
            if i == selected_index:
                print(
                    f"  |  {ConsoleUI.CYAN}{ConsoleUI.BOLD}{visible_text}"
                    f"{ConsoleUI.RESET}{pad_r}  |"
                )
            else:
                print(f"  |  {visible_text}{pad_r}  |")
        remaining = len(options) - top - visible
        if remaining > 0:
            arrow_dn = f"v  {remaining} element(s) plus bas"
            pad_r    = " " * max(0, box_w - 2 - ConsoleUI.display_len(arrow_dn))
            print(f"  |  {ConsoleUI.CYAN}{arrow_dn}{ConsoleUI.RESET}{pad_r}|")
        else:
            print(f"  |{' ' * box_w}|")
        print(f"  +{h_line}+")
        nav     = "haut/bas: Naviguer   Entree: Valider   Echap: Quitter"
        nav_pad = " " * max(0, box_w - 2 - ConsoleUI.display_len(nav))
        print(f"  |  {ConsoleUI.YELLOW}{nav}{ConsoleUI.RESET}{nav_pad}|")
        print(f"  +{h_line}+")
        ver_str = f"v{VERSION}"
        ver_pad = " " * max(0, box_w + 2 - ConsoleUI.display_len(ver_str))
        print(f"  {ConsoleUI.DIM}{ver_pad}{ver_str}{ConsoleUI.RESET}")

    # ── Menu Termux (liste numérotée) ─────────────────────────────────────────
    @staticmethod
    def show_menu_termux(
        options: list[str],
        title: str = "MENU",
        subtitle: str = "",
        show_status: bool = False,
    ) -> None:
        """Affiche le menu Termux (liste numérotée, saisie clavier standard)."""
        C = ConsoleUI
        C.clear()
        print(f"{C.CYAN}\n  {'═' * 44}{C.RESET}")
        print(f"  {C.BOLD}{C.CYAN}NEY-MENU  v{VERSION}  ·  {title}{C.RESET}")
        if subtitle:
            print(f"  {C.DIM}{subtitle}{C.RESET}")
        print(f"{C.CYAN}  {'═' * 44}{C.RESET}")
        if show_status:
            C.print_status_panel_termux()
        print()
        for i, opt in enumerate(options, 1):
            print(f"  {C.CYAN}{C.BOLD}[{i}]{C.RESET}  {opt}")
        print(f"  {C.CYAN}{C.BOLD}[0]{C.RESET}  {C.DIM}Quitter{C.RESET}")
        print(f"\n{C.CYAN}  {'─' * 44}{C.RESET}")

    # ── Lecture d'une touche sans blocage (PC) ────────────────────────────────
    @staticmethod
    def get_key() -> str | None:
        """Lit une touche sans bloquer. Retourne UP, DOWN, ENTER, ESC ou None."""
        if os.name == "nt":
            if msvcrt and msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b"\xe0":
                    key = msvcrt.getch()
                    if key == b"H":
                        return "UP"
                    if key == b"P":
                        return "DOWN"
                elif key == b"\r":
                    return "ENTER"
                elif key == b"\x1b":
                    return "ESC"
        elif tty and termios and select:
            fd = sys.stdin.fileno()
            try:
                old_attr = termios.tcgetattr(fd)
            except Exception:  # pylint: disable=broad-except
                return None
            try:
                tty.setraw(fd)
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    ch = sys.stdin.read(1)
                    if ch == "\x1b":
                        if select.select([sys.stdin], [], [], 0.05)[0]:
                            more = sys.stdin.read(2)
                            if more == "[A":
                                return "UP"
                            if more == "[B":
                                return "DOWN"
                        return "ESC"
                    if ch in ("\r", "\n"):
                        return "ENTER"
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)
        return None

    # ── Navigation unifiée PC / Termux ────────────────────────────────────────
    @staticmethod
    def navigate(
        options: list[str],
        title: str = "MENU",
        subtitle: str = "",
        show_status: bool = False,
    ) -> int:
        """Navigation interactive. Retourne l'index sélectionné ou -1 (Échap/0)."""
        if not options:
            return -1
        if _TERMUX:
            while True:
                ConsoleUI.show_menu_termux(options, title, subtitle, show_status)
                try:
                    raw = input(
                        f"  {ConsoleUI.YELLOW}>  {ConsoleUI.RESET}Choix : "
                    ).strip()
                except (EOFError, OSError):
                    return -1
                if raw in ("0", ""):
                    return -1
                if raw.isdigit():
                    idx = int(raw) - 1
                    if 0 <= idx < len(options):
                        return idx
                print(
                    f"  {ConsoleUI.YELLOW}!"
                    f"  Choix invalide — entrez entre 1 et {len(options)}"
                    f"{ConsoleUI.RESET}"
                )
                time.sleep(0.8)
        else:
            selected = 0
            while True:
                ConsoleUI.show_menu(options, title, selected, subtitle, show_status)
                while True:
                    key = ConsoleUI.get_key()
                    if key:
                        break
                    time.sleep(0.03)
                if key == "UP":
                    selected = (selected - 1) % len(options)
                elif key == "DOWN":
                    selected = (selected + 1) % len(options)
                elif key == "ENTER":
                    return selected
                elif key == "ESC":
                    return -1

    # ── Messages utilitaires ──────────────────────────────────────────────────
    @staticmethod
    def warn(msg: str) -> None:
        """Affiche un avertissement (jaune)."""
        print(f"  {ConsoleUI.YELLOW}!  {ConsoleUI.RESET}{msg}")

    @staticmethod
    def info(msg: str) -> None:
        """Affiche une information (cyan)."""
        print(f"  {ConsoleUI.CYAN}i  {ConsoleUI.RESET}{msg}")

    @staticmethod
    def success(msg: str) -> None:
        """Affiche un succès (vert)."""
        print(f"  {ConsoleUI.GREEN}ok {ConsoleUI.RESET}{msg}")


# ── Téléchargement avec barre de progression (console) ────────────────────────
def _download_file(
    url: str, dest: str, label: str, force: bool = False
) -> bool:
    """Télécharge *url* vers *dest* avec barre de progression.

    Skip si taille locale == taille distante (+-1 o) et force=False.
    Retourne True si le fichier est à jour ou téléchargé avec succès.
    """
    remote_size = _get_remote_size(url)
    if not force and remote_size > 0 and os.path.isfile(dest):
        local_size = os.path.getsize(dest)
        if abs(remote_size - local_size) <= 1:
            ConsoleUI.success(
                f"{label}"
                f"  {ConsoleUI.DIM}(deja a jour, {local_size} o){ConsoleUI.RESET}"
            )
            return True
        ConsoleUI.info(
            f"{label}"
            f"  {ConsoleUI.DIM}{local_size} o -> {remote_size} o{ConsoleUI.RESET}"
        )
    elif not os.path.isfile(dest):
        ConsoleUI.info(
            f"{label}"
            f"  {ConsoleUI.DIM}— premiere installation...{ConsoleUI.RESET}"
        )
    else:
        ConsoleUI.info(
            f"{label}"
            f"  {ConsoleUI.DIM}— taille distante inconnue, mise a jour...{ConsoleUI.RESET}"
        )

    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)

    print(
        f"  {ConsoleUI.CYAN}[{'.' * 20}]{ConsoleUI.RESET}   0%",
        end="",
        flush=True,
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/termux"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total      = int(resp.headers.get("Content-Length", 0) or 0)
            downloaded = 0
            with open(dest, "wb") as fout:
                while True:
                    buf = resp.read(8192)
                    if not buf:
                        break
                    fout.write(buf)
                    downloaded += len(buf)
                    if total > 0:
                        pct = min(int(downloaded * 100 / total), 100)
                        bar = "#" * (pct // 5) + "." * (20 - pct // 5)
                        print(
                            f"\r  {ConsoleUI.CYAN}[{bar}]{ConsoleUI.RESET} {pct:3d}%",
                            end="",
                            flush=True,
                        )
        print()
        _invalidate_cache(url)
        ConsoleUI.success(
            f"{label}"
            f"  {ConsoleUI.DIM}({os.path.getsize(dest)} o){ConsoleUI.RESET}"
        )
        return True
    except Exception as exc:  # pylint: disable=broad-except
        print()
        ConsoleUI.warn(f"Impossible de telecharger {label} : {exc}")
        return False


# ── Statut des scripts (console) ───────────────────────────────────────────────
def _compute_one_status(
    label: str, path: str, url: str | None
) -> tuple[str, str, str]:
    """Calcule le statut d'un script et retourne (label, badge, couleur)."""
    C = ConsoleUI
    if url is None:
        return (label, "* Present ", C.GREEN)
    if not os.path.isfile(path):
        return (label, "x Manquant", C.RED)
    local_size  = os.path.getsize(path)
    remote_size = _get_remote_size(url)
    if remote_size <= 0:
        return (label, "? Inconnu ", C.DIM)
    diff = abs(remote_size - local_size)
    if diff <= 1:
        return (label, "v A jour  ", C.GREEN)
    delta = remote_size - local_size
    sign  = "+" if delta > 0 else ""
    badge = f"^ MaJ ({sign}{delta}o)"
    return (label, badge, C.YELLOW)


def _refresh_status(silent: bool = False) -> None:
    """Recalcule les statuts de tous les scripts et met à jour _SCRIPT_STATUSES."""
    global _SCRIPT_STATUSES  # pylint: disable=global-statement
    if not silent:
        ConsoleUI.clear()
        ConsoleUI.print_banner()
        print(
            f"\n  {ConsoleUI.CYAN}i  {ConsoleUI.RESET}"
            f"Verification des scripts...  "
            f"{ConsoleUI.DIM}(cache 5 min){ConsoleUI.RESET}\n"
        )
    py = _py_dir()
    scripts: list[tuple[str, str, str | None]] = [
        ("Ney-Tube.py", os.path.join(py, COTUBE_FILE), URL_COTUBE),
    ]
    coflix_path = os.path.join(py, COFLIX_FILE)
    if os.path.isfile(coflix_path):
        scripts.append(("Co-flix.py", coflix_path, None))
    _SCRIPT_STATUSES = [
        _compute_one_status(lbl, path, url) for lbl, path, url in scripts
    ]


# ── Gestion des scripts enfants (console) ─────────────────────────────────────
def _rename_if_needed(folder: str, src_name: str, dst_name: str) -> None:
    """Renomme src_name vers dst_name dans *folder* si src existe et dst absent."""
    src = os.path.join(folder, src_name)
    dst = os.path.join(folder, dst_name)
    if os.path.isfile(src) and not os.path.isfile(dst):
        os.rename(src, dst)
        ConsoleUI.info(f"Renomme : {src_name} -> {dst_name}")


def _ensure_scripts() -> bool:
    """Vérifie la présence des scripts ; les signale si absents."""
    py = _py_dir()
    for alias in ("cotube.py", "youtube_downloader.py"):
        _rename_if_needed(py, alias, COTUBE_FILE)
    for alias in ("coflix.py", "get.php"):
        _rename_if_needed(py, alias, COFLIX_FILE)
    downloadable = [
        ("Ney-Tube", os.path.join(py, COTUBE_FILE)),
    ]
    missing = [lbl for lbl, dst in downloadable if not os.path.isfile(dst)]
    if missing:
        for lbl in missing:
            ConsoleUI.warn(
                f"{lbl} est absent — utilisez le menu "
                f"{ConsoleUI.YELLOW}'Mise a jour'{ConsoleUI.RESET} pour l'installer."
            )
    return len(missing) == 0


def _update_scripts() -> None:
    """Télécharge la dernière version des scripts (Co-flix exclu)."""
    py = _py_dir()
    updatable = [
        ("Ney-Tube",   URL_COTUBE, os.path.join(py, COTUBE_FILE)),
    ]
    ConsoleUI.clear()
    ConsoleUI.print_banner()
    print(ConsoleUI.CYAN + "\n  " + "=" * 58 + ConsoleUI.RESET)
    print(f"  {ConsoleUI.BOLD}  Mise a jour des scripts{ConsoleUI.RESET}")
    print(
        f"  {ConsoleUI.DIM}"
        "Co-flix.py doit etre mis a jour manuellement."
        f"{ConsoleUI.RESET}"
    )
    print(
        f"  {ConsoleUI.DIM}"
        "Ney-Menu se met a jour automatiquement au demarrage."
        f"{ConsoleUI.RESET}"
    )
    print(ConsoleUI.CYAN + "  " + "=" * 58 + ConsoleUI.RESET + "\n")
    all_ok = True
    for lbl, url, dest in updatable:
        print()
        ok = _download_file(url, dest, lbl)
        if not ok:
            all_ok = False
    print()
    if all_ok:
        print(
            f"  {ConsoleUI.GREEN}ok  Mise a jour terminee avec succes !{ConsoleUI.RESET}"
        )
    else:
        ConsoleUI.warn("Certains fichiers n'ont pas pu etre mis a jour.")
    try:
        input(
            f"\n  {ConsoleUI.DIM}"
            "Appuyez sur Entree pour continuer..."
            f"{ConsoleUI.RESET}"
        )
    except (EOFError, OSError):
        pass
    _refresh_status(silent=True)


# ── Auto-mise à jour (version console) ────────────────────────────────────────
def _self_update_console() -> None:
    """Télécharge et compare Ney-Menu depuis GitHub au démarrage (console).

    Si le contenu distant diffère du fichier local, écrase et relance.
    En cas d'échec réseau, démarre quand même sans bloquer.
    """
    current_path = os.path.abspath(__file__)
    ConsoleUI.clear()
    ConsoleUI.print_banner()
    print(
        f"\n  {ConsoleUI.CYAN}i  {ConsoleUI.RESET}"
        "Vérification de Ney-Menu depuis GitHub...\n"
    )
    try:
        cb  = random.randint(100000, 999999)
        url = f"{URL_NEYMENU}?cb={cb}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "curl/termux",
                "Accept": "text/plain",
                "Cache-Control": "no-cache, no-store",
                "Pragma": "no-cache",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                raise ValueError(f"HTTP {resp.status}")
            remote_content = resp.read()
    except Exception as exc:  # pylint: disable=broad-except
        ConsoleUI.warn(f"Impossible de joindre GitHub : {exc}")
        ConsoleUI.info("Démarrage avec la version locale.")
        time.sleep(1)
        return

    if len(remote_content) < 5000:
        ConsoleUI.warn(
            f"Réponse suspecte ({len(remote_content)} o) — mise à jour annulée."
        )
        ConsoleUI.info("Démarrage avec la version locale.")
        time.sleep(1)
        return

    remote_hash = hashlib.sha256(remote_content).hexdigest()
    if os.path.isfile(current_path):
        with open(current_path, "rb") as fh:
            local_hash = hashlib.sha256(fh.read()).hexdigest()
    else:
        local_hash = ""

    if remote_hash == local_hash:
        ConsoleUI.success(
            f"Ney-Menu est à jour  "
            f"{ConsoleUI.DIM}({len(remote_content)} o){ConsoleUI.RESET}"
        )
        time.sleep(0.8)
        return

    ConsoleUI.info(
        f"Nouvelle version détectée — mise à jour en cours...  "
        f"{ConsoleUI.DIM}({len(remote_content)} o){ConsoleUI.RESET}"
    )
    try:
        parent = os.path.dirname(current_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(current_path, "wb") as fh:
            fh.write(remote_content)
    except Exception as exc:  # pylint: disable=broad-except
        ConsoleUI.warn(f"Impossible d'écrire le fichier : {exc}")
        time.sleep(2)
        return

    print(
        f"\n  {ConsoleUI.GREEN}ok  {ConsoleUI.RESET}"
        "Ney-Menu mis à jour — relancement automatique...\n"
    )
    time.sleep(1)
    subprocess.Popen([sys.executable, current_path] + sys.argv[1:])
    sys.exit(0)


# ── Lancement des scripts enfants (Termux — dans le même processus) ───────────
def _launch(filename: str, module_name: str) -> None:
    """Charge et exécute le main() d'un script Python dans _py_dir() (Termux)."""
    path = os.path.join(_py_dir(), filename)
    if not os.path.isfile(path):
        ConsoleUI.warn(f"{filename} introuvable dans : {_py_dir()}")
        time.sleep(2)
        return
    spec   = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    module.main()


def launch_coflix() -> None:
    """Lance Co-flix (console)."""
    _launch(COFLIX_FILE, "coflix")
    _cleanup_pycache()


def launch_cotube() -> None:
    """Lance Ney-Tube (console)."""
    _launch(COTUBE_FILE, "neytube")
    _cleanup_pycache()


# ── Sortie propre (console) ───────────────────────────────────────────────────
def _goodbye() -> None:
    """Nettoie et quitte proprement (console)."""
    _cleanup_pycache()
    ConsoleUI.clear()
    print(ConsoleUI.CYAN + "\n  " + "=" * 58 + ConsoleUI.RESET)
    print(f"  {ConsoleUI.CYAN}  Merci d'avoir utilise NEY-MENU !{ConsoleUI.RESET}")
    print("     A bientot !")
    print(ConsoleUI.CYAN + "  " + "=" * 58 + ConsoleUI.RESET + "\n")
    time.sleep(1)
    os._exit(0)  # pylint: disable=protected-access


def _signal_handler(_sig: int, _frame: object) -> None:
    """Gestionnaire SIGINT / SIGTERM / SIGHUP (console)."""
    _goodbye()


# ══════════════════════════════════════════════════════════════════════════════
#  Interface PyQt5 — PC uniquement (ignorée sous Termux)
# ══════════════════════════════════════════════════════════════════════════════
if not _TERMUX:

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

        # ── Construction UI ────────────────────────────────────────────────────
        def _build_ui(self) -> None:
            root = QWidget()
            root.setStyleSheet(f"background: {VOID};")
            self.setCentralWidget(root)

            outer = QVBoxLayout(root)
            outer.setContentsMargins(24, 20, 24, 16)
            outer.setSpacing(14)

            # ── En-tête ────────────────────────────────────────────────────────
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

            # ── Statuts ────────────────────────────────────────────────────────
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

            # ── Séparateur Volt ────────────────────────────────────────────────
            outer.addWidget(VoltSeparator())

            # ── Section titre ──────────────────────────────────────────────────
            section_lbl = QLabel("QUE VOULEZ-VOUS FAIRE ?")
            section_lbl.setStyleSheet(
                f"color: {TEXT_DIM}; font-size: 9px; letter-spacing: 4px; font-weight: 700;"
            )
            outer.addWidget(section_lbl)

            # ── Boutons ────────────────────────────────────────────────────────

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
            self._btn_quit.clicked.connect(self._goodbye_qt)
            outer.addWidget(self._btn_quit)

            outer.addStretch()

            # ── Barre de progression ───────────────────────────────────────────
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

            # ── Log + version ──────────────────────────────────────────────────
            foot = QHBoxLayout()
            self._logbar = LogBar()
            ver_lbl = QLabel(f"v{VERSION}")
            ver_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")

            foot.addWidget(self._logbar, 1)
            foot.addWidget(ver_lbl)
            outer.addLayout(foot)

        # ── Séquence d'init ────────────────────────────────────────────────────
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

        # ── Actions menu ───────────────────────────────────────────────────────
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

        def _goodbye_qt(self) -> None:
            _cleanup_pycache()
            self.close()

        # ── Helpers ────────────────────────────────────────────────────────────
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
    """Point d'entrée principal de NEY-MENU."""
    if _TERMUX:
        # ── Mode console (Termux / Android) ───────────────────────────────────
        ConsoleUI.enable_ansi()
        sys.stdout.write("\033]0;NEY-MENU\007")
        sys.stdout.flush()

        _self_update_console()
        _ensure_scripts()
        _refresh_status(silent=False)

        while True:
            coflix_present = os.path.isfile(os.path.join(_py_dir(), COFLIX_FILE))
            options: list[str] = []
            if coflix_present:
                options.append("\U0001f3ac  Films / Series   (CO-FLIX)")
            options.append("\U0001f534  YouTube          (NEY-TUBE)")
            options.append("\u2b07\ufe0f   Mise a jour des scripts")
            options.append("\u274c  Quitter")

            choice = ConsoleUI.navigate(
                options,
                "QUE VOULEZ-VOUS FAIRE ?",
                show_status=True,
            )

            if choice == -1:
                _goodbye()

            idx = choice
            if coflix_present:
                if idx == 0:
                    launch_coflix()
                elif idx == 1:
                    launch_cotube()
                elif idx == 2:
                    _update_scripts()
                elif idx == 3:
                    _goodbye()
            else:
                if idx == 0:
                    launch_cotube()
                elif idx == 1:
                    _update_scripts()
                elif idx == 2:
                    _goodbye()

    else:
        # ── Mode graphique PyQt5 (PC) ──────────────────────────────────────────
        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, "AA_UseHighDpiPixmaps"):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        app = QApplication(sys.argv)
        app.setApplicationName("NEY-MENU")
        app.setStyle("Fusion")

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
    if _TERMUX:
        signal.signal(signal.SIGINT,  _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, _signal_handler)
        try:
            main()
        except KeyboardInterrupt:
            _goodbye()
        except Exception as _err:  # pylint: disable=broad-except
            ConsoleUI.clear()
            print(ConsoleUI.RED + "\n\n  ERREUR CRITIQUE\n" + ConsoleUI.RESET)
            print(f"  {_err}\n")
            traceback.print_exc()
            try:
                input("\n  Appuyez sur Entree pour quitter...")
            except (EOFError, OSError):
                pass
            _goodbye()
    else:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        try:
            main()
        except Exception as _err:
            print(f"\nERREUR CRITIQUE : {_err}\n")
            traceback.print_exc()
            sys.exit(1)
