"""CO-MENU — Lance CO-FLIX (films/séries), CO-CHAN (anime) ou CO-TUBE (YouTube).
Les scripts sont stockés dans le sous-dossier ./py/ et téléchargés automatiquement si absents."""
import os
import sys
import time
import signal
import traceback

try:
    import ctypes
except ImportError:
    ctypes = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    import tty
    import termios
    import select
except ImportError:
    tty = termios = select = None


VERSION = "1.3"

# ── Noms de fichiers et URLs ──────────────────────────────────────────────────
COFLIX_FILE = "Co-flix.py"
COCHAN_FILE = "Co-chan.py"
COTUBE_FILE = "Co-tube.py"

COFLIX_URL  = None
COCHAN_URL  = "https://raw.githubusercontent.com/Bicode-dev/anime_Co-Chan_download/main/Co-chan.py"
COTUBE_URL  = "https://raw.githubusercontent.com/Bicode-dev/Co-tube/main/Co-tube.py"


# ── Détection Termux ──────────────────────────────────────────────────────────
def _is_termux():
    return (os.name != "nt" and (
        "ANDROID_STORAGE" in os.environ
        or "com.termux" in os.environ.get("PREFIX", "")
    ))


# ── Chemins ───────────────────────────────────────────────────────────────────
def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _py_dir():
    """Dossier de stockage des scripts :
    Windows : %LOCALAPPDATA%/CoTEAM/Co-Menu
    Linux/macOS/Termux : ~/.local/share/CoTEAM/Co-Menu"""
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        d = os.path.join(local, "CoTEAM", "Co-Menu")
    else:
        d = os.path.join(os.path.expanduser("~"), ".local", "share", "CoTEAM", "Co-Menu")
    os.makedirs(d, exist_ok=True)
    return d


# ── ConsoleUI ─────────────────────────────────────────────────────────────────
class ConsoleUI:
    RESET  = '\033[0m'
    BOLD   = '\033[1m'
    DIM    = '\033[2m'
    RED    = '\033[31m'
    GREEN  = '\033[32m'
    YELLOW = '\033[33m'
    CYAN   = '\033[36m'

    @staticmethod
    def enable_ansi():
        if os.name == 'nt':
            try:
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except Exception:
                pass

    @staticmethod
    def clear():
        os.system('cls' if os.name == 'nt' else 'clear')

    MAX_VISIBLE = 8

    @staticmethod
    def display_len(s):
        count = 0
        for ch in s:
            cp = ord(ch)
            if cp in (0xFE0E, 0xFE0F, 0x200D, 0x20E3):
                continue
            if 0x0300 <= cp <= 0x036F:
                continue
            is_emoji = (0x1F000 <= cp <= 0x1FFFF or 0x2600 <= cp <= 0x27BF
                        or 0x2B00 <= cp <= 0x2BFF)
            is_cjk   = (0xFE30 <= cp <= 0xFE4F or 0x2E80 <= cp <= 0x2EFF
                        or 0x3000 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF)
            is_hangul = 0xAC00 <= cp <= 0xD7AF
            if is_emoji or is_cjk or is_hangul:
                count += 2
            else:
                count += 1
        return count

    @staticmethod
    def _print_banner():
        print(ConsoleUI.CYAN + r"""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║    ██████╗ ██████╗       ███╗   ███╗███████╗███╗   ██╗██╗   ██╗  ║
║   ██╔════╝██╔═══██╗      ████╗ ████║██╔════╝████╗  ██║██║   ██║  ║
║   ██║     ██║   ██║█████╗██╔████╔██║█████╗  ██╔██╗ ██║██║   ██║  ║
║   ██║     ██║   ██║╚════╝██║╚██╔╝██║██╔══╝  ██║╚██╗██║██║   ██║  ║
║   ╚██████╗╚██████╔╝      ██║ ╚═╝ ██║███████╗██║ ╚████║╚██████╔╝  ║
║    ╚═════╝ ╚═════╝       ╚═╝     ╚═╝╚══════╝╚═╝  ╚═══╝ ╚═════╝   ║
║                                                                  ║
║              🎬  CO-MENU  DOWNLOADER  🎌                         ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝""" + ConsoleUI.RESET)

    @staticmethod
    def show_menu(options, title="MENU", selected_index=0, subtitle=""):
        box_w = 62
        ConsoleUI.clear()
        ConsoleUI._print_banner()

        if subtitle:
            print(f"\n  {ConsoleUI.DIM}{subtitle}{ConsoleUI.RESET}")
        else:
            print()

        visible = min(len(options), ConsoleUI.MAX_VISIBLE)
        half    = visible // 2
        top     = selected_index - half
        top     = max(0, min(top, len(options) - visible))

        h_line      = "=" * box_w
        title_vlen  = ConsoleUI.display_len(title)
        title_pad_l = max(0, (box_w - title_vlen) // 2)
        title_pad_r = max(0, box_w - title_vlen - title_pad_l)
        print(f"  +{h_line}+")
        print(f"  |{' ' * title_pad_l}{ConsoleUI.BOLD}{ConsoleUI.CYAN}{title}{ConsoleUI.RESET}{' ' * title_pad_r}|")
        print(f"  +{h_line}+")

        if top > 0:
            arrow_up = f"^  {top} resultat(s) plus haut"
            pad_r = " " * max(0, box_w - 2 - ConsoleUI.display_len(arrow_up))
            print(f"  |  {ConsoleUI.CYAN}{arrow_up}{ConsoleUI.RESET}{pad_r}|")
        else:
            print(f"  |{' ' * box_w}|")

        inner    = box_w - 4
        max_text = inner - 3

        for i in range(top, top + visible):
            raw = options[i]
            if ConsoleUI.display_len(raw) > max_text:
                accum, width = [], 0
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
                print(f"  |  {ConsoleUI.CYAN}{ConsoleUI.BOLD}{visible_text}{ConsoleUI.RESET}{pad_r}  |")
            else:
                print(f"  |  {visible_text}{pad_r}  |")

        remaining = len(options) - top - visible
        if remaining > 0:
            arrow_dn = f"v  {remaining} resultat(s) plus bas"
            pad_r = " " * max(0, box_w - 2 - ConsoleUI.display_len(arrow_dn))
            print(f"  |  {ConsoleUI.CYAN}{arrow_dn}{ConsoleUI.RESET}{pad_r}|")
        else:
            print(f"  |{' ' * box_w}|")

        print(f"  +{h_line}+")
        nav     = "haut/bas: Naviguer   Entree: Valider   Echap: Quitter"
        nav_pad = " " * max(0, box_w - 2 - ConsoleUI.display_len(nav))
        print(f"  |  {ConsoleUI.YELLOW}{nav}{ConsoleUI.RESET}{nav_pad}|")
        print(f"  +{h_line}+")

    @staticmethod
    def show_menu_termux(options, title="MENU", subtitle=""):
        ConsoleUI.clear()
        print(f"{ConsoleUI.CYAN}\n  {'='*54}{ConsoleUI.RESET}")
        print(f"  {ConsoleUI.BOLD}{ConsoleUI.CYAN}CO-MENU  --  {title}{ConsoleUI.RESET}")
        if subtitle:
            print(f"  {ConsoleUI.DIM}{subtitle}{ConsoleUI.RESET}")
        print(f"{ConsoleUI.CYAN}  {'='*54}{ConsoleUI.RESET}\n")
        for i, opt in enumerate(options, 1):
            print(f"  {ConsoleUI.CYAN}{ConsoleUI.BOLD}[{i}]{ConsoleUI.RESET}  {opt}")
        print(f"  {ConsoleUI.CYAN}{ConsoleUI.BOLD}[0]{ConsoleUI.RESET}  {ConsoleUI.DIM}Quitter{ConsoleUI.RESET}")
        print(f"\n{ConsoleUI.CYAN}  {'-'*54}{ConsoleUI.RESET}")

    @staticmethod
    def get_key():
        if os.name == 'nt':
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'\xe0':
                    key = msvcrt.getch()
                    if key == b'H':
                        return 'UP'
                    if key == b'P':
                        return 'DOWN'
                elif key == b'\r':
                    return 'ENTER'
                elif key == b'\x1b':
                    return 'ESC'
        else:
            fd = sys.stdin.fileno()
            try:
                old_attr = termios.tcgetattr(fd)
            except Exception:
                return None
            try:
                tty.setraw(fd)
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    ch = sys.stdin.read(1)
                    if ch == '\x1b':
                        if select.select([sys.stdin], [], [], 0.05)[0]:
                            more = sys.stdin.read(2)
                            if more == '[A':
                                return 'UP'
                            if more == '[B':
                                return 'DOWN'
                        return 'ESC'
                    if ch in ('\r', '\n'):
                        return 'ENTER'
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)
        return None

    @staticmethod
    def navigate(options, title="MENU", subtitle=""):
        if not options:
            return -1

        if _is_termux():
            while True:
                ConsoleUI.show_menu_termux(options, title, subtitle)
                try:
                    raw = input(f"  {ConsoleUI.YELLOW}>  {ConsoleUI.RESET}Choix : ").strip()
                except (EOFError, OSError):
                    return -1
                if raw == "0" or raw == "":
                    return -1
                if raw.isdigit():
                    idx = int(raw) - 1
                    if 0 <= idx < len(options):
                        return idx
                print(f"  {ConsoleUI.YELLOW}!  Choix invalide -- entrez un nombre entre 1 et {len(options)}{ConsoleUI.RESET}")
                time.sleep(0.8)
        else:
            selected = 0
            while True:
                ConsoleUI.show_menu(options, title, selected, subtitle)
                while True:
                    key = ConsoleUI.get_key()
                    if key:
                        break
                    time.sleep(0.03)
                if key == 'UP':
                    selected = (selected - 1) % len(options)
                elif key == 'DOWN':
                    selected = (selected + 1) % len(options)
                elif key == 'ENTER':
                    return selected
                elif key == 'ESC':
                    return -1

    @staticmethod
    def warn(msg):
        print(f"  {ConsoleUI.YELLOW}!  {ConsoleUI.RESET}{msg}")

    @staticmethod
    def info(msg):
        print(f"  {ConsoleUI.CYAN}i  {ConsoleUI.RESET}{msg}")

    @staticmethod
    def success(msg):
        print(f"  {ConsoleUI.GREEN}ok {ConsoleUI.RESET}{msg}")


# ── Téléchargement ────────────────────────────────────────────────────────────
def _download_file(url, dest, label):
    """Telecharge un fichier avec barre de progression."""
    import urllib.request  # pylint: disable=import-outside-toplevel
    print(f"\n  {ConsoleUI.CYAN}i  {ConsoleUI.RESET}Telechargement de {label}...")
    try:
        headers = {"User-Agent": "curl/termux"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            total      = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                while True:
                    buf = resp.read(8192)
                    if not buf:
                        break
                    f.write(buf)
                    downloaded += len(buf)
                    if total > 0:
                        pct = min(int(downloaded * 100 / total), 100)
                        bar = "#" * (pct // 5) + "." * (20 - pct // 5)
                        print(f"\r  [{ConsoleUI.CYAN}{bar}{ConsoleUI.RESET}] {pct:3d}%",
                              end="", flush=True)
        print()
        ConsoleUI.success(f"{label} telecharge.")
        return True
    except Exception as e:  # pylint: disable=broad-except
        print()
        ConsoleUI.warn(f"Impossible de telecharger {label} : {e}")
        return False


def _rename_if_needed(folder, src_name, dst_name):
    """Renomme src_name en dst_name dans folder si src existe et dst n'existe pas."""
    src = os.path.join(folder, src_name)
    dst = os.path.join(folder, dst_name)
    if os.path.isfile(src) and not os.path.isfile(dst):
        os.rename(src, dst)
        ConsoleUI.info(f"Renomme : {src_name} -> {dst_name}")


def _ensure_scripts():
    """Verifie la presence des scripts dans ./py/ ; telecharge et renomme si necessaire.
    Les scripts sans URL (ex: Co-flix) sont signales comme manquants mais pas telecharges."""
    py = _py_dir()

    # Renommages preventifs (fichiers deja presents sous un autre nom)
    for alias in ("Anime-dowload.py", "Anime-download.py", "cochan.py"):
        _rename_if_needed(py, alias, COCHAN_FILE)
    for alias in ("coflix.py", "get.php"):
        _rename_if_needed(py, alias, COFLIX_FILE)
    for alias in ("cotube.py", "youtube_downloader.py"):
        _rename_if_needed(py, alias, COTUBE_FILE)

    coflix_path = os.path.join(py, COFLIX_FILE)
    cochan_path = os.path.join(py, COCHAN_FILE)
    cotube_path = os.path.join(py, COTUBE_FILE)

    # Scripts manquants avec une URL de telechargement disponible
    missing = []
    if not os.path.isfile(cochan_path):
        missing.append(("Co-chan", COCHAN_URL, cochan_path))
    if not os.path.isfile(cotube_path):
        missing.append(("Co-tube", COTUBE_URL, cotube_path))

    if not missing:
        return True

    # Ecran de telechargement pour les scripts avec URL
    ConsoleUI.clear()
    ConsoleUI._print_banner()
    print(ConsoleUI.CYAN + "\n  " + "="*58 + ConsoleUI.RESET)
    print(f"  {ConsoleUI.BOLD}  Scripts manquants -- telechargement automatique{ConsoleUI.RESET}")
    print(ConsoleUI.CYAN + "  " + "="*58 + ConsoleUI.RESET)

    all_ok = True
    for label, url, dest in missing:
        ok = _download_file(url, dest, label)
        if not ok:
            all_ok = False

    # Renommage post-telechargement
    for alias in ("Anime-dowload.py", "Anime-download.py"):
        _rename_if_needed(py, alias, COCHAN_FILE)

    if not all_ok:
        ConsoleUI.warn("Certains fichiers n'ont pas pu etre telecharges.")
        try:
            input(f"\n  {ConsoleUI.DIM}Appuyez sur Entree pour continuer...{ConsoleUI.RESET}")
        except (EOFError, OSError):
            pass

    return all_ok


def _update_scripts():
    """Telecharge la derniere version des scripts mis a jour (ceux ayant une URL).
    Co-flix est exclu car il n'a pas d'URL de telechargement."""
    py = _py_dir()

    # Liste des scripts pouvant etre mis a jour automatiquement
    updatable = [
        ("Co-chan", COCHAN_URL, os.path.join(py, COCHAN_FILE)),
        ("Co-tube", COTUBE_URL, os.path.join(py, COTUBE_FILE)),
    ]

    ConsoleUI.clear()
    ConsoleUI._print_banner()
    print(ConsoleUI.CYAN + "\n  " + "="*58 + ConsoleUI.RESET)
    print(f"  {ConsoleUI.BOLD}  Mise a jour des scripts{ConsoleUI.RESET}")
    print(ConsoleUI.CYAN + "  " + "="*58 + ConsoleUI.RESET)
    print(f"\n  {ConsoleUI.DIM}Co-flix.py doit etre mis a jour manuellement.{ConsoleUI.RESET}\n")

    all_ok = True
    for label, url, dest in updatable:
        ok = _download_file(url, dest, label)
        if not ok:
            all_ok = False

    if all_ok:
        print(f"\n  {ConsoleUI.GREEN}ok  Mise a jour terminee avec succes !{ConsoleUI.RESET}")
    else:
        ConsoleUI.warn("Certains fichiers n'ont pas pu etre mis a jour.")

    try:
        input(f"\n  {ConsoleUI.DIM}Appuyez sur Entree pour continuer...{ConsoleUI.RESET}")
    except (EOFError, OSError):
        pass


# ── Lancement des scripts ─────────────────────────────────────────────────────
def _launch(filename, module_name):
    """Charge et execute le main() d'un script dans ./py/."""
    import importlib.util  # pylint: disable=import-outside-toplevel
    path = os.path.join(_py_dir(), filename)
    if not os.path.isfile(path):
        ConsoleUI.warn(f"{filename} introuvable dans : {_py_dir()}")
        time.sleep(2)
        return
    spec   = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


def launch_coflix():
    _launch(COFLIX_FILE, "coflix")
    _cleanup_pycache()


def launch_cochan():
    _launch(COCHAN_FILE, "cochan")
    _cleanup_pycache()


def launch_cotube():
    _launch(COTUBE_FILE, "cotube")
    _cleanup_pycache()


# ── Point d'entree ────────────────────────────────────────────────────────────
def _cleanup_pycache():
    """Supprime le dossier __pycache__ dans ./py/ s'il existe."""
    import shutil  # pylint: disable=import-outside-toplevel
    cache = os.path.join(_py_dir(), "__pycache__")
    try:
        if os.path.isdir(cache):
            shutil.rmtree(cache, ignore_errors=True)
    except Exception:  # pylint: disable=broad-except
        pass


def _goodbye():
    _cleanup_pycache()
    ConsoleUI.clear()
    print(ConsoleUI.CYAN + "\n  " + "="*58 + ConsoleUI.RESET)
    print(f"  {ConsoleUI.CYAN}  Merci d'avoir utilise CO-MENU !{ConsoleUI.RESET}")
    print("     A bientot !")
    print(ConsoleUI.CYAN + "  " + "="*58 + ConsoleUI.RESET + "\n")
    time.sleep(1)
    os._exit(0)


def _signal_handler(_sig, _frame):
    _goodbye()


def main():
    ConsoleUI.enable_ansi()

    if os.name == 'nt':
        os.system('title CO-MENU DOWNLOADER')
    elif _is_termux():
        sys.stdout.write("\033]0;CO-MENU\007")
        sys.stdout.flush()

    # Verification / telechargement des scripts au demarrage
    _ensure_scripts()

    # Proposition de mise a jour
    if _is_termux():
        ConsoleUI.clear()
        ConsoleUI._print_banner()
        print(f"\n  {ConsoleUI.CYAN}i  {ConsoleUI.RESET}Voulez-vous mettre a jour les scripts ?")
        print(f"  {ConsoleUI.DIM}(Co-chan et Co-tube — Co-flix est exclu){ConsoleUI.RESET}")
        print(f"\n  {ConsoleUI.CYAN}{ConsoleUI.BOLD}[1]{ConsoleUI.RESET}  Oui, mettre a jour")
        print(f"  {ConsoleUI.CYAN}{ConsoleUI.BOLD}[0]{ConsoleUI.RESET}  Non, continuer\n")
        try:
            raw = input(f"  {ConsoleUI.YELLOW}>  {ConsoleUI.RESET}Choix : ").strip()
            if raw == "1":
                _update_scripts()
        except (EOFError, OSError):
            pass
    else:
        upd = ConsoleUI.navigate(
            ["⬇️   Oui, mettre a jour Co-chan et Co-tube",
             "▶   Non, continuer"],
            "MISE A JOUR",
            subtitle="Co-flix doit etre mis a jour manuellement",
        )
        if upd == 0:
            _update_scripts()

    while True:
        choice = ConsoleUI.navigate([
            "\U0001f3ac  Films / Series  (CO-FLIX)",
            "\U0001f338  Anime           (CO-CHAN)",
            "\U0001f534  YouTube         (CO-TUBE)",
            "\u274c  Quitter",
        ], "QUE VOULEZ-VOUS TELECHARGER ?", f"v{VERSION}")

        if choice == 0:
            launch_coflix()
        elif choice == 1:
            launch_cochan()
        elif choice == 2:
            launch_cotube()
        elif choice in (3, -1):
            _goodbye()


if __name__ == "__main__":
    signal.signal(signal.SIGINT,  _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, _signal_handler)

    try:
        main()
    except KeyboardInterrupt:
        _goodbye()
    except Exception as e:  # pylint: disable=broad-except
        ConsoleUI.clear()
        print(ConsoleUI.RED + "\n\n  ERREUR CRITIQUE\n" + ConsoleUI.RESET)
        print(f"  {e}\n")
        traceback.print_exc()
        try:
            input("\n  Appuyez sur Entree pour quitter...")
        except (EOFError, OSError):
            pass
        _goodbye()