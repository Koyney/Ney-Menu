"""NEY-MENU — Lance CO-FLIX (optionnel) et NEY-TUBE.

Les scripts sont stockés dans le dossier Koyney/Ney-Menu et téléchargés/mis à
jour automatiquement depuis GitHub. Ney-Menu.py lui-même peut aussi se
mettre à jour via le menu Mise à jour.

Compatibilité :
    - Windows (PC)           : navigation clavier + chemins AppData
    - Linux / macOS (PC)     : navigation clavier + chemins XDG
    - Termux / Android       : saisie numérique + chemins HOME
"""
# pylint: disable=import-outside-toplevel  # stdlib léger importé localement
from __future__ import annotations

import os
import sys
import time
import signal
import traceback

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


# ── Version ───────────────────────────────────────────────────────────────────
VERSION = "2.2"

# ── URLs de téléchargement ────────────────────────────────────────────────────
URL_NEYMENU = (
    "https://raw.githubusercontent.com/Koyney/Ney-Menu"
    "/refs/heads/main/Ney-Menu.py"
)
URL_COTUBE = (
    "https://raw.githubusercontent.com/Koyney/Ney-Tube"
    "/refs/heads/main/Ney-Tube.py"
)

# ── Noms des scripts enfants ──────────────────────────────────────────────────
COFLIX_FILE = "Co-flix.py"
COTUBE_FILE = "Ney-tube.py"

# ── Cache réseau (url -> (taille_octets, timestamp)) ─────────────────────────
_NET_CACHE: dict[str, tuple[int, float]] = {}
_CACHE_TTL = 300  # 5 minutes

# ── Statut des scripts (peuplé par _refresh_status) ──────────────────────────
# Chaque entrée : (label_affiché, badge_texte_brut, code_couleur_ANSI)
_SCRIPT_STATUSES: list[tuple[str, str, str]] = []


# ── Détection plateforme ──────────────────────────────────────────────────────
def _is_termux() -> bool:
    """Retourne True si l'exécution se fait dans Termux (Android)."""
    return os.name != "nt" and (
        "ANDROID_STORAGE" in os.environ
        or "com.termux" in os.environ.get("PREFIX", "")
    )



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
        directory = os.path.join(local, "Koyney", "Ney-Menu")
    elif _is_termux():
        directory = os.path.join(
            os.path.expanduser("~"), ".local", "Koyney", "Ney-Menu"
        )
    else:
        directory = os.path.join(
            os.path.expanduser("~"), ".local", "share", "Koyney", "Ney-Menu"
        )
    os.makedirs(directory, exist_ok=True)
    return directory


# ══════════════════════════════════════════════════════════════════════════════
#  ConsoleUI — bannière, menus, navigation, messages
# ══════════════════════════════════════════════════════════════════════════════
class ConsoleUI:
    """Interface console colorée : navigation PC (fleches) et Termux (numeros)."""

    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[31m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    CYAN   = "\033[36m"

    MAX_VISIBLE = 6  # lignes d'options visibles simultanement

    # ── ANSI Windows ──────────────────────────────────────────────────────────
    @staticmethod
    def enable_ansi() -> None:
        """Active les sequences ANSI dans la console Windows si possible."""
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
        """Retourne la largeur visuelle d'une chaine (emoji/CJK comptent double)."""
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

    # ── Banniere ASCII ────────────────────────────────────────────────────────
    @staticmethod
    def print_banner() -> None:
        """Affiche la banniere NEY-MENU."""
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
        """Affiche le panneau ETAT DES SCRIPTS (2 entrees par ligne) sous la banniere."""
        if not _SCRIPT_STATUSES:
            return

        C     = ConsoleUI
        inner = box_w - 2   # 60 chars entre les bords
        half  = inner // 2  # 30 par colonne

        # En-tete
        hdr      = " ETAT DES SCRIPTS "
        hdr_vlen = C.display_len(hdr)
        eq_left  = (inner - hdr_vlen) // 2
        eq_right = inner - hdr_vlen - eq_left
        print(
            f"  {C.CYAN}╔{'═' * eq_left}"
            f"{C.BOLD}{hdr}{C.RESET}"
            f"{C.CYAN}{'═' * eq_right}╗{C.RESET}"
        )

        # Lignes de donnees (2 entrees par ligne)
        entries = list(_SCRIPT_STATUSES)
        if len(entries) % 2:
            entries.append(None)  # type: ignore[arg-type]

        for i in range(0, len(entries), 2):
            left  = ConsoleUI._fmt_status_cell(entries[i],     half)
            right = ConsoleUI._fmt_status_cell(entries[i + 1], half)
            print(f"  {C.CYAN}║{C.RESET}{left}{right}{C.CYAN}║{C.RESET}")

        # Pied
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

    # ── Menu PC (boite + curseur visuel) ──────────────────────────────────────
    @staticmethod
    def show_menu(
        options: list[str],
        title: str = "MENU",
        selected_index: int = 0,
        subtitle: str = "",
        show_status: bool = False,
    ) -> None:
        """Affiche le menu interactif PC avec boite et curseur visuel."""
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

        # Indicateur de defilement haut
        if top > 0:
            arrow_up = f"^  {top} element(s) plus haut"
            pad_r    = " " * max(0, box_w - 2 - ConsoleUI.display_len(arrow_up))
            print(f"  |  {ConsoleUI.CYAN}{arrow_up}{ConsoleUI.RESET}{pad_r}|")
        else:
            print(f"  |{' ' * box_w}|")

        # Options
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

        # Indicateur de defilement bas
        remaining = len(options) - top - visible
        if remaining > 0:
            arrow_dn = f"v  {remaining} element(s) plus bas"
            pad_r    = " " * max(0, box_w - 2 - ConsoleUI.display_len(arrow_dn))
            print(f"  |  {ConsoleUI.CYAN}{arrow_dn}{ConsoleUI.RESET}{pad_r}|")
        else:
            print(f"  |{' ' * box_w}|")

        # Pied de boite + barre de navigation
        print(f"  +{h_line}+")
        nav     = "haut/bas: Naviguer   Entree: Valider   Echap: Quitter"
        nav_pad = " " * max(0, box_w - 2 - ConsoleUI.display_len(nav))
        print(f"  |  {ConsoleUI.YELLOW}{nav}{ConsoleUI.RESET}{nav_pad}|")
        print(f"  +{h_line}+")

        # Version alignee a droite
        ver_str = f"v{VERSION}"
        ver_pad = " " * max(0, box_w + 2 - ConsoleUI.display_len(ver_str))
        print(f"  {ConsoleUI.DIM}{ver_pad}{ver_str}{ConsoleUI.RESET}")

    # ── Menu Termux (liste numerotee) ─────────────────────────────────────────
    @staticmethod
    def show_menu_termux(
        options: list[str],
        title: str = "MENU",
        subtitle: str = "",
        show_status: bool = False,
    ) -> None:
        """Affiche le menu Termux (liste numerotee, saisie clavier standard)."""
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

    # ── Navigation unifiee PC / Termux ────────────────────────────────────────
    @staticmethod
    def navigate(
        options: list[str],
        title: str = "MENU",
        subtitle: str = "",
        show_status: bool = False,
    ) -> int:
        """Navigation interactive. Retourne l'index selectionne ou -1 (Echap/0)."""
        if not options:
            return -1

        if _is_termux():
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
        """Affiche un succes (vert)."""
        print(f"  {ConsoleUI.GREEN}ok {ConsoleUI.RESET}{msg}")


# ══════════════════════════════════════════════════════════════════════════════
#  Reseau — taille distante avec cache + telechargement avec barre
# ══════════════════════════════════════════════════════════════════════════════
def _get_remote_size(url: str) -> int:
    """Retourne la taille distante en octets (0 si inconnue) avec cache TTL 5 min."""
    import urllib.request

    now    = time.time()
    cached = _NET_CACHE.get(url)
    if cached is not None:
        size, ts = cached
        if now - ts < _CACHE_TTL:
            return size

    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": "curl/termux"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            size = int(resp.headers.get("Content-Length", 0) or 0)
    except Exception:  # pylint: disable=broad-except
        size = 0

    _NET_CACHE[url] = (size, now)
    return size


def _invalidate_cache(url: str) -> None:
    """Supprime l'entree de cache pour forcer un rechargement."""
    _NET_CACHE.pop(url, None)


def _download_file(
    url: str, dest: str, label: str, force: bool = False
) -> bool:
    """Telecharge *url* vers *dest* avec barre de progression.

    Skip si taille locale == taille distante (+-1 o) et force=False.
    Retourne True si le fichier est a jour ou telecharge avec succes.
    """
    import urllib.request

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


# ══════════════════════════════════════════════════════════════════════════════
#  Statut des scripts (panneau inline dans le menu)
# ══════════════════════════════════════════════════════════════════════════════
def _compute_one_status(
    label: str, path: str, url: str | None
) -> tuple[str, str, str]:
    """Calcule le statut d'un script et retourne (label, badge, couleur)."""
    C = ConsoleUI

    # Co-flix : pas d'URL, on vérifie seulement la présence (appelé uniquement si présent)
    if url is None:
        return (label, "* Present ", C.GREEN)

    # Scripts avec URL
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
    """Recalcule les statuts de tous les scripts et met a jour _SCRIPT_STATUSES.

    Affiche un ecran de chargement si *silent* est False (premier appel).
    """
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
        ("Ney-tube.py", os.path.join(py, COTUBE_FILE), URL_COTUBE),
    ]

    # Co-flix : uniquement si le fichier est présent
    coflix_path = os.path.join(py, COFLIX_FILE)
    if os.path.isfile(coflix_path):
        scripts.append(("Co-flix.py", coflix_path, None))

    _SCRIPT_STATUSES = [
        _compute_one_status(lbl, path, url) for lbl, path, url in scripts
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  Gestion des scripts enfants
# ══════════════════════════════════════════════════════════════════════════════
def _rename_if_needed(folder: str, src_name: str, dst_name: str) -> None:
    """Renomme src_name vers dst_name dans *folder* si src existe et dst absent."""
    src = os.path.join(folder, src_name)
    dst = os.path.join(folder, dst_name)
    if os.path.isfile(src) and not os.path.isfile(dst):
        os.rename(src, dst)
        ConsoleUI.info(f"Renomme : {src_name} -> {dst_name}")


def _ensure_scripts() -> bool:
    """Verifie la presence des scripts ; les installe si absents.

    Co-flix n'a pas d'URL et n'est jamais telecharge automatiquement.
    Retourne True si tous les scripts telechargeables sont presents.
    """
    py = _py_dir()

    for alias in ("cotube.py", "youtube_downloader.py"):
        _rename_if_needed(py, alias, COTUBE_FILE)
    for alias in ("coflix.py", "get.php"):
        _rename_if_needed(py, alias, COFLIX_FILE)

    downloadable = [
        ("Ney-tube", os.path.join(py, COTUBE_FILE)),
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
    """Telecharge la derniere version des scripts (Co-flix exclu)."""
    py = _py_dir()

    updatable = [
        ("Ney-tube",   URL_COTUBE, os.path.join(py, COTUBE_FILE)),
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
        "Ney-Menu.py se met a jour automatiquement au demarrage."
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

    # Recalcule le statut apres mise a jour (cache invalide pendant _download_file)
    _refresh_status(silent=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Auto-mise à jour de Ney-Menu.py au démarrage
# ══════════════════════════════════════════════════════════════════════════════
def _self_update() -> None:
    """Télécharge TOUJOURS le contenu de Ney-Menu.py depuis GitHub au démarrage.

    Compare le contenu distant (hash SHA-256) avec le fichier local.
    Si identiques : on continue. Si différents : on écrase et on relance.
    En cas d'échec réseau : on démarre quand même sans bloquer.

    Note : utilise subprocess + sys.exit pour le relancement afin d'éviter
    les problèmes de os.execv avec des chemins contenant des espaces (Windows).
    """
    import urllib.request
    import urllib.error
    import hashlib
    import subprocess

    current_path = os.path.abspath(__file__)

    ConsoleUI.clear()
    ConsoleUI.print_banner()
    print(
        f"\n  {ConsoleUI.CYAN}i  {ConsoleUI.RESET}"
        "Vérification de Ney-Menu.py depuis GitHub...\n"
    )

    # ── Téléchargement complet du fichier distant ─────────────────────────────
    try:
        # Paramètre aléatoire pour contourner le cache CDN de GitHub
        import random
        cache_bust = random.randint(100000, 999999)
        url_nocache = f"{URL_NEYMENU}?cb={cache_bust}"  # FIX: ? au lieu de &
        req = urllib.request.Request(
            url_nocache,
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

    # Sanity-check : le fichier doit faire au moins 5 Ko (protection anti-page HTML)
    if len(remote_content) < 5000:
        ConsoleUI.warn(
            f"Réponse suspecte ({len(remote_content)} o) — mise à jour annulée."
        )
        ConsoleUI.info("Démarrage avec la version locale.")
        time.sleep(1)
        return

    # ── Comparaison par hash SHA-256 ──────────────────────────────────────────
    remote_hash = hashlib.sha256(remote_content).hexdigest()

    if os.path.isfile(current_path):
        with open(current_path, "rb") as fh:
            local_hash = hashlib.sha256(fh.read()).hexdigest()
    else:
        local_hash = ""

    if remote_hash == local_hash:
        ConsoleUI.success(
            f"Ney-Menu.py est à jour  "
            f"{ConsoleUI.DIM}({len(remote_content)} o){ConsoleUI.RESET}"
        )
        time.sleep(0.8)
        return

    # ── Contenu différent : on écrase et on relance ───────────────────────────
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
        "Ney-Menu.py mis à jour — relancement automatique...\n"
    )
    time.sleep(1)

    # Relance via subprocess (compatible chemins avec espaces sur Windows)
    subprocess.Popen([sys.executable, current_path] + sys.argv[1:])
    sys.exit(0)


# ══════════════════════════════════════════════════════════════════════════════
#  Lancement des scripts enfants
# ══════════════════════════════════════════════════════════════════════════════
def _cleanup_pycache() -> None:
    """Supprime le dossier __pycache__ du dossier py."""
    import shutil

    cache = os.path.join(_py_dir(), "__pycache__")
    try:
        if os.path.isdir(cache):
            shutil.rmtree(cache, ignore_errors=True)
    except Exception:  # pylint: disable=broad-except
        pass


def _launch(filename: str, module_name: str) -> None:
    """Charge et execute le main() d'un script Python dans _py_dir()."""
    import importlib.util

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
    """Lance Co-flix."""
    _launch(COFLIX_FILE, "coflix")
    _cleanup_pycache()


def launch_cotube() -> None:
    """Lance Ney-tube."""
    _launch(COTUBE_FILE, "neytube")
    _cleanup_pycache()


# ══════════════════════════════════════════════════════════════════════════════
#  Sortie propre
# ══════════════════════════════════════════════════════════════════════════════
def _goodbye() -> None:
    """Nettoie et quitte proprement."""
    _cleanup_pycache()
    ConsoleUI.clear()
    print(ConsoleUI.CYAN + "\n  " + "=" * 58 + ConsoleUI.RESET)
    print(f"  {ConsoleUI.CYAN}  Merci d'avoir utilise NEY-MENU !{ConsoleUI.RESET}")
    print("     A bientot !")
    print(ConsoleUI.CYAN + "  " + "=" * 58 + ConsoleUI.RESET + "\n")
    time.sleep(1)
    os._exit(0)  # pylint: disable=protected-access


def _signal_handler(_sig: int, _frame: object) -> None:
    """Gestionnaire SIGINT / SIGTERM / SIGHUP."""
    _goodbye()


# ══════════════════════════════════════════════════════════════════════════════
#  Point d'entree
# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    """Point d'entree principal de NEY-MENU."""
    ConsoleUI.enable_ansi()

    if os.name == "nt":
        os.system("title NEY-MENU")
    elif _is_termux():
        sys.stdout.write("\033]0;NEY-MENU\007")
        sys.stdout.flush()

    # 0. Auto-mise à jour de Ney-Menu.py (se relance si nouvelle version trouvée)
    _self_update()

    # 1. Installation des scripts manquants
    _ensure_scripts()

    # 2. Verification des statuts (requetes HEAD — ecran de chargement une seule fois)
    _refresh_status(silent=False)

    # 3. Menu principal (boucle)
    while True:
        # Construction dynamique du menu selon la presence de Co-flix
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

        # Resolution de l'index selon la presence de Co-flix
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


if __name__ == "__main__":
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