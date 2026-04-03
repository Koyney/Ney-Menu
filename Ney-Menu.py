#!/usr/bin/env python3
"""NEY-MENU — Lance CO-FLIX (optionnel) et NEY-TUBE.

Interface TUI Textual — fonctionne sur PC (Windows / Linux / macOS)
et sur Termux / Android sans aucune dépendance graphique.

Dépendances :
    pip install textual
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import random
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
from typing import Callable

# ── Détection plateforme ──────────────────────────────────────────────────────
def _is_termux() -> bool:
    """Retourne True si l'exécution se fait dans Termux (Android)."""
    return os.name != "nt" and (
        "ANDROID_STORAGE" in os.environ
        or "com.termux" in os.environ.get("PREFIX", "")
    )

_TERMUX = _is_termux()

# ── Version ────────────────────────────────────────────────────────────────────
VERSION = "3.0"

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
COTUBE_FILE = "Ney-Tube.pyw"

_NET_CACHE: dict[str, tuple[int, float]] = {}
_CACHE_TTL = 300  # secondes


# ══════════════════════════════════════════════════════════════════════════════
#  Fonctions utilitaires (communes à toutes les plateformes)
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
        d = os.path.join(os.path.expanduser("~"), ".local", "Koyney", "Ney-Menu")
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
    _NET_CACHE.pop(url, None)


def _cleanup_pycache() -> None:
    cache = os.path.join(_py_dir(), "__pycache__")
    try:
        if os.path.isdir(cache):
            shutil.rmtree(cache, ignore_errors=True)
    except Exception:
        pass


def _open_in_terminal(script_path: str) -> None:
    """Lance un script Python dans un nouveau terminal (PC uniquement)."""
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


def _download_file(
    url: str,
    dest: str,
    label: str,
    progress_cb: Callable[[int], None] | None = None,
) -> bool:
    """Télécharge *url* vers *dest*.

    Si progress_cb est fourni, il est appelé avec un pourcentage (0-100)
    à chaque bloc reçu. Retourne True si le téléchargement a réussi.
    """
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/termux"})
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
                if total > 0 and progress_cb is not None:
                    progress_cb(min(int(downloaded * 100 / total), 100))
        with open(dest, "wb") as f:
            for c in chunks:
                f.write(c)
        _invalidate_cache(url)
        return True
    except Exception:
        return False


def _compute_one_status(
    label: str, path: str, url: str | None
) -> tuple[str, str, str]:
    """Calcule le statut d'un script.

    Retourne (label, badge_texte, status_key).
    status_key : "ok" | "update" | "missing" | "unknown"
    """
    if url is None:
        return (label, "✓ Présent", "ok")
    if not os.path.isfile(path):
        return (label, "✗ Manquant", "missing")
    local_size  = os.path.getsize(path)
    remote_size = _get_remote_size(url)
    if remote_size <= 0:
        return (label, "? Inconnu", "unknown")
    if abs(remote_size - local_size) <= 1:
        return (label, "✓ À jour", "ok")
    delta = remote_size - local_size
    sign  = "+" if delta > 0 else ""
    return (label, f"↑ MàJ ({sign}{delta}o)", "update")


def _rename_if_needed(folder: str, src_name: str, dst_name: str) -> None:
    src = os.path.join(folder, src_name)
    dst = os.path.join(folder, dst_name)
    if os.path.isfile(src) and not os.path.isfile(dst):
        try:
            os.rename(src, dst)
        except OSError:
            pass


def _launch(filename: str, module_name: str) -> None:
    """Charge et exécute le main() d'un script Python dans _py_dir() (Termux)."""
    import importlib.machinery

    path = os.path.join(_py_dir(), filename)
    if not os.path.isfile(path):
        return
    loader = importlib.machinery.SourceFileLoader(module_name, path)
    spec   = importlib.util.spec_from_loader(module_name, loader, origin=path)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    module.main()


def launch_coflix() -> None:
    _launch(COFLIX_FILE, "coflix")
    _cleanup_pycache()


def launch_cotube() -> None:
    _launch(COTUBE_FILE, "neytube")
    _cleanup_pycache()


# ══════════════════════════════════════════════════════════════════════════════
#  Interface Textual — PC + Termux / Android
# ══════════════════════════════════════════════════════════════════════════════
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, ProgressBar, Static, Rule
from textual import on, work


# ── Palette Void + Volt ───────────────────────────────────────────────────────
_CSS = f"""
/* ── Fond global ── */
Screen {{
    background: #09090b;
    align: center top;
}}

/* ── Conteneur principal ── */
#main {{
    width: 64;
    height: auto;
    background: #09090b;
    padding: 1 0;
}}

/* ── En-tête ── */
#header {{
    background: #111116;
    border: tall #1f1f2e;
    padding: 1 3;
    width: 100%;
    height: auto;
    margin-bottom: 1;
}}
#brand-title {{
    text-align: center;
    color: #c6f135;
    text-style: bold;
    width: 100%;
}}
#brand-subtitle {{
    text-align: center;
    color: #5a5a6e;
    width: 100%;
}}
#brand-version {{
    text-align: center;
    color: #2e2e42;
    width: 100%;
}}

/* ── Carte de statuts ── */
#status-bar {{
    background: #111116;
    border: tall #1f1f2e;
    padding: 0 2;
    width: 100%;
    height: 3;
    margin-bottom: 1;
}}
#scripts-label {{
    color: #3a3a52;
    text-style: bold;
    width: auto;
    content-align: left middle;
}}
#chip-neytube {{
    width: auto;
    content-align: right middle;
    color: #5a5a6e;
    margin-left: 2;
}}
#chip-coflix {{
    width: auto;
    content-align: right middle;
    color: #5a5a6e;
    margin-left: 2;
    display: none;
}}
.chip-ok      {{ color: #4cd97b; }}
.chip-update  {{ color: #f5a623; }}
.chip-missing {{ color: #f53c3c; }}
.chip-unknown {{ color: #5a5a6e; }}

/* ── Séparateur Volt ── */
Rule {{
    color: #c6f135;
    margin: 0 0 1 0;
}}

/* ── Section titre ── */
#section-label {{
    color: #3a3a52;
    text-style: bold;
    width: 100%;
    margin-bottom: 1;
}}

/* ── Boutons principaux ── */
Button {{
    background: #111116;
    color: #eaeaea;
    border: tall #1f1f2e;
    width: 1fr;
    height: 3;
    margin-bottom: 1;
    text-align: left;
}}
Button:hover {{
    background: #1c1c24;
    border: tall #2e2e42;
    color: #ffffff;
}}
Button:focus {{
    border: tall #2e2e42;
}}
Button:disabled {{
    background: #0d0d10;
    color: #2a2a38;
    border: tall #151520;
}}

/* ── Accent (Volt) ── */
Button.accent {{
    color: #c6f135;
    border: tall #2e2e42;
}}
Button.accent:hover {{
    background: #2a3a00;
    border: tall #c6f135;
    color: #d8ff55;
}}
Button.accent:disabled {{
    color: #3a4a1a;
    background: #0d0d10;
    border: tall #151520;
}}

/* ── Danger (Quitter) ── */
Button.danger {{
    color: #5a5a6e;
}}
Button.danger:hover {{
    background: #1a0a0a;
    border: tall #f53c3c;
    color: #f53c3c;
}}

/* ── Bouton MàJ inline (petit) ── */
#btn-upd-neytube {{
    width: 10;
    color: #5a5a6e;
    text-align: center;
}}
#btn-upd-neytube:hover {{
    background: #2a3a00;
    border: tall #c6f135;
    color: #c6f135;
}}

/* ── Ligne Ney-Tube (bouton + inline update) ── */
#row-neytube {{
    width: 100%;
    height: 3;
    margin-bottom: 1;
}}

/* ── Ligne Co-flix (masquée par défaut) ── */
#row-coflix {{
    width: 100%;
    height: 3;
    margin-bottom: 1;
    display: none;
}}
#row-coflix.shown {{
    display: block;
}}

/* ── Barre de progression ── */
#progress {{
    width: 100%;
    margin-bottom: 1;
    display: none;
}}
#progress.shown {{
    display: block;
}}
#progress > .bar--bar {{
    color: #c6f135;
    background: #1f1f2e;
}}
#progress > .bar--complete {{
    color: #c6f135;
}}
#progress > .bar--indeterminate {{
    color: #c6f135;
}}

/* ── Pied de page (log) ── */
#footer {{
    width: 100%;
    height: 1;
    margin-top: 0;
}}
#log-dot {{
    width: 2;
    color: #5a5a6e;
    content-align: left middle;
}}
#log-msg {{
    width: 1fr;
    color: #5a5a6e;
    content-align: left middle;
}}
#log-ver {{
    width: auto;
    color: #2e2e42;
    content-align: right middle;
}}
"""


class NeyMenuApp(App):
    """Application Textual NEY-MENU — PC et Termux/Android."""

    TITLE   = "NEY-MENU"
    CSS     = _CSS
    BINDINGS = [("ctrl+c", "quit_app", "Quitter")]

    def __init__(self) -> None:
        super().__init__()
        self._coflix_present = False

    # ── Construction de l'interface ───────────────────────────────────────────
    def compose(self) -> ComposeResult:
        with Container(id="main"):

            # En-tête
            with Container(id="header"):
                yield Static(
                    "NEY  ─  MENU",
                    id="brand-title",
                )
                yield Static("K O Y N E Y   S U I T E", id="brand-subtitle")
                yield Static(f"v{VERSION}", id="brand-version")

            # Statuts scripts
            with Horizontal(id="status-bar"):
                yield Static("SCRIPTS", id="scripts-label")
                yield Static("NEY-TUBE   …", id="chip-neytube")
                yield Static("CO-FLIX   …", id="chip-coflix")

            # Séparateur Volt
            yield Rule()

            # Titre section
            yield Static("QUE VOULEZ-VOUS FAIRE ?", id="section-label")

            # Bouton Co-flix (caché si absent)
            with Container(id="row-coflix"):
                yield Button(
                    "🎬   Films / Séries  ·  CO-FLIX   ›",
                    id="btn-coflix",
                    classes="accent",
                )

            # Bouton Ney-Tube + MàJ inline
            with Horizontal(id="row-neytube"):
                yield Button(
                    "▶   YouTube  ·  NEY-TUBE   ›",
                    id="btn-neytube",
                    classes="accent",
                )
                yield Button("↓  MàJ", id="btn-upd-neytube")

            # Bouton Quitter
            yield Button("✕   Quitter", id="btn-quit", classes="danger")

            # Barre de progression (masquée par défaut)
            yield ProgressBar(total=100, show_eta=False, id="progress")

            # Log bar
            with Horizontal(id="footer"):
                yield Static("●", id="log-dot")
                yield Static("  Initialisation…", id="log-msg")
                yield Static(f"v{VERSION}", id="log-ver")

    # ── Démarrage ─────────────────────────────────────────────────────────────
    def on_mount(self) -> None:
        self._set_buttons_enabled(False)
        self._worker_self_update()

    # ── Helpers UI ────────────────────────────────────────────────────────────
    def _log(self, msg: str, level: str = "info") -> None:
        """Met à jour la barre de log (thread principal uniquement)."""
        colors = {
            "info": "#5a5a6e",
            "ok":   "#4cd97b",
            "warn": "#f5a623",
            "err":  "#f53c3c",
        }
        color = colors.get(level, "#5a5a6e")
        self.query_one("#log-dot", Static).styles.color = color
        msg_w = self.query_one("#log-msg", Static)
        msg_w.styles.color = color
        msg_w.update(f"  {msg}")

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for btn_id in ("btn-coflix", "btn-neytube", "btn-upd-neytube", "btn-quit"):
            try:
                self.query_one(f"#{btn_id}", Button).disabled = not enabled
            except Exception:
                pass

    def _update_chip(self, chip_id: str, badge: str, key: str) -> None:
        chip = self.query_one(f"#{chip_id}", Static)
        chip.remove_class("chip-ok", "chip-update", "chip-missing", "chip-unknown")
        chip.add_class(f"chip-{key}")
        chip.update(f"{badge}")

    def _show_coflix(self, visible: bool) -> None:
        row  = self.query_one("#row-coflix")
        chip = self.query_one("#chip-coflix", Static)
        if visible:
            row.add_class("shown")
            chip.styles.display = "block"
        else:
            row.remove_class("shown")
            chip.styles.display = "none"

    def _show_progress(self, visible: bool) -> None:
        pb = self.query_one("#progress")
        if visible:
            pb.add_class("shown")
        else:
            pb.remove_class("shown")

    def _set_progress(self, pct: int) -> None:
        pb = self.query_one(ProgressBar)
        pb.progress = float(pct)

    # ── Workers (threads en arrière-plan) ────────────────────────────────────

    @work(thread=True, name="self-update")
    def _worker_self_update(self) -> None:
        """Vérifie et applique la mise à jour de Ney-Menu lui-même."""
        current_path = os.path.abspath(__file__)
        self.call_from_thread(self._log, "Vérification de Ney-Menu depuis GitHub…", "info")
        try:
            cb  = random.randint(100000, 999999)
            url = f"{URL_NEYMENU}?cb={cb}"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent":    "curl/termux",
                    "Cache-Control": "no-cache, no-store",
                    "Pragma":        "no-cache",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    raise ValueError(f"HTTP {resp.status}")
                remote = resp.read()
        except Exception as exc:
            self.call_from_thread(
                self._log, f"Réseau indisponible — {exc}", "warn"
            )
            self.call_from_thread(self._start_check_statuses)
            return

        if len(remote) < 5000:
            self.call_from_thread(self._log, "Réponse suspecte — MàJ ignorée.", "warn")
            self.call_from_thread(self._start_check_statuses)
            return

        remote_hash = hashlib.sha256(remote).hexdigest()
        local_hash  = ""
        if os.path.isfile(current_path):
            with open(current_path, "rb") as f:
                local_hash = hashlib.sha256(f.read()).hexdigest()

        if remote_hash == local_hash:
            self.call_from_thread(self._log, "Ney-Menu est à jour.", "ok")
            self.call_from_thread(self._start_check_statuses)
            return

        self.call_from_thread(
            self._log, "Nouvelle version détectée — mise à jour…", "info"
        )
        try:
            parent = os.path.dirname(current_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(current_path, "wb") as f:
                f.write(remote)
        except Exception as exc:
            self.call_from_thread(self._log, f"Écriture échouée : {exc}", "warn")
            self.call_from_thread(self._start_check_statuses)
            return

        # Relancer avec la nouvelle version
        self.call_from_thread(
            self._log, "Relancement avec la nouvelle version…", "ok"
        )
        time.sleep(1.2)
        subprocess.Popen([sys.executable, current_path] + sys.argv[1:])
        self.call_from_thread(self.exit)

    def _start_check_statuses(self) -> None:
        """Démarre le worker de vérification des statuts (thread principal)."""
        self._worker_check_statuses()

    @work(thread=True, name="check-statuses")
    def _worker_check_statuses(self) -> None:
        """Vérifie la présence et la version de chaque script."""
        self.call_from_thread(self._log, "Vérification des statuts…", "info")

        py = _py_dir()

        # Renommages éventuels
        for alias in ("cotube.pyw", "youtube_downloader.py"):
            _rename_if_needed(py, alias, COTUBE_FILE)
        for alias in ("coflix.py", "get.php"):
            _rename_if_needed(py, alias, COFLIX_FILE)

        # Ney-Tube
        nt_label, nt_badge, nt_key = _compute_one_status(
            "NEY-TUBE", os.path.join(py, COTUBE_FILE), URL_COTUBE
        )
        self.call_from_thread(self._update_chip, "chip-neytube", nt_badge, nt_key)

        # Co-flix
        coflix_path    = os.path.join(py, COFLIX_FILE)
        coflix_present = os.path.isfile(coflix_path)
        if coflix_present:
            _, cf_badge, cf_key = _compute_one_status("CO-FLIX", coflix_path, None)
            self.call_from_thread(self._update_chip, "chip-coflix", cf_badge, cf_key)
        self.call_from_thread(self._show_coflix, coflix_present)
        self._coflix_present = coflix_present

        self.call_from_thread(self._set_buttons_enabled, True)
        self.call_from_thread(self._log, "Prêt.", "ok")

    @work(thread=True, name="update-scripts")
    def _worker_update_scripts(self) -> None:
        """Télécharge la dernière version de Ney-Tube."""
        self.call_from_thread(self._set_buttons_enabled, False)
        self.call_from_thread(self._show_progress, True)
        self.call_from_thread(self._set_progress, 0)

        py   = _py_dir()
        dest = os.path.join(py, COTUBE_FILE)
        self.call_from_thread(self._log, "Téléchargement de Ney-Tube…", "info")

        ok = _download_file(
            URL_COTUBE,
            dest,
            "Ney-Tube",
            progress_cb=lambda pct: self.call_from_thread(self._set_progress, pct),
        )

        self.call_from_thread(self._show_progress, False)
        if ok:
            self.call_from_thread(
                self._log, "Ney-Tube mis à jour avec succès.", "ok"
            )
        else:
            self.call_from_thread(
                self._log, "Erreur lors de la mise à jour.", "warn"
            )
        self.call_from_thread(self._start_check_statuses)

    # ── Actions boutons ───────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-coflix")
    def _action_coflix(self) -> None:
        path = os.path.join(_py_dir(), COFLIX_FILE)
        if not os.path.isfile(path):
            self._log("Co-flix introuvable.", "warn")
            return
        self._log("Lancement de Co-flix…", "info")
        if _TERMUX:
            # Suspend Textual, exécute le script inline, puis reprend
            with self.suspend():
                launch_coflix()
        else:
            _open_in_terminal(path)

    @on(Button.Pressed, "#btn-neytube")
    def _action_neytube(self) -> None:
        path = os.path.join(_py_dir(), COTUBE_FILE)
        if not os.path.isfile(path):
            self._log("Ney-Tube introuvable — faites une mise à jour.", "warn")
            return
        self._log("Lancement de Ney-Tube…", "info")
        if _TERMUX:
            with self.suspend():
                launch_cotube()
        else:
            _open_in_terminal(path)

    @on(Button.Pressed, "#btn-upd-neytube")
    def _action_update(self) -> None:
        self._worker_update_scripts()

    @on(Button.Pressed, "#btn-quit")
    def _action_quit(self) -> None:
        _cleanup_pycache()
        self.exit()

    def action_quit_app(self) -> None:
        _cleanup_pycache()
        self.exit()


# ══════════════════════════════════════════════════════════════════════════════
#  Point d'entrée
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Point d'entrée principal de NEY-MENU."""
    app = NeyMenuApp()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as _err:
        print(f"\nERREUR CRITIQUE : {_err}\n")
        traceback.print_exc()
        sys.exit(1)