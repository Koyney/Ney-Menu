#!/usr/bin/env python3
"""NEY-MENU — Gestionnaire de la Koyney Suite (style store).

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
    return os.name != "nt" and (
        "ANDROID_STORAGE" in os.environ
        or "com.termux" in os.environ.get("PREFIX", "")
    )

_TERMUX = _is_termux()

# ── Version ───────────────────────────────────────────────────────────────────
VERSION = "3.1"

# ── URLs ──────────────────────────────────────────────────────────────────────
URL_NEYMENU = (
    "https://raw.githubusercontent.com/Koyney/Ney-Menu"
    "/refs/heads/main/Ney-Menu.py"
)
URL_COTUBE = (
    "https://raw.githubusercontent.com/Koyney/Ney-Tube"
    "/refs/heads/main/Ney-Tube.pyw"
)

COTUBE_FILE = "Ney-Tube.pyw"

_NET_CACHE: dict[str, tuple[int, float]] = {}
_CACHE_TTL = 300

# ── Registre des scripts de la suite ─────────────────────────────────────────
SCRIPTS: list[dict] = [
    {
        "id":   "neytube",
        "name": "Ney-Tube",
        "type": "Youtube",
        "icon": "▶",
        "desc": "Téléchargeur de vidéos Youtube",
        "file": COTUBE_FILE,
        "url":  URL_COTUBE,
    },
]


# ══════════════════════════════════════════════════════════════════════════════
#  Fonctions utilitaires (communes à toutes les plateformes)
# ══════════════════════════════════════════════════════════════════════════════

def _py_dir() -> str:
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
    if url is None:
        return (label, "✓ Présent", "ok")
    if not os.path.isfile(path):
        return (label, "↓ À installer", "missing")
    local_size  = os.path.getsize(path)
    remote_size = _get_remote_size(url)
    if remote_size <= 0:
        return (label, "? Inconnu", "unknown")
    if abs(remote_size - local_size) <= 1:
        return (label, "✓ À jour", "ok")
    return (label, "↑ MàJ disponible", "update")


def _rename_if_needed(folder: str, src_name: str, dst_name: str) -> None:
    src = os.path.join(folder, src_name)
    dst = os.path.join(folder, dst_name)
    if os.path.isfile(src) and not os.path.isfile(dst):
        try:
            os.rename(src, dst)
        except OSError:
            pass


def _launch(filename: str, module_name: str) -> None:
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


def launch_cotube() -> None:
    _launch(COTUBE_FILE, "neytube")
    _cleanup_pycache()


# ══════════════════════════════════════════════════════════════════════════════
#  Interface Textual — style "store"
# ══════════════════════════════════════════════════════════════════════════════

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, ProgressBar, Static, Input, ListView, ListItem
from textual import on, work

_CSS = """
/* ── Global ── */
Screen {
    background: #09090c;
}
#main {
    width: 100%;
    height: 100%;
    background: #09090c;
}

/* ── En-tête store ── */
#store-header {
    height: 3;
    background: #0f0f13;
    border-bottom: tall #1a1a26;
    padding: 0 2;
    width: 100%;
}
#header-left {
    color: #eaeaea;
    width: 1fr;
    content-align: left middle;
}
#header-brand {
    color: #c6f135;
    text-style: bold;
}
#header-pipe {
    color: #2e2e44;
}
#header-sub {
    color: #3a3a54;
}
#script-count {
    color: #3a3a54;
    width: auto;
    content-align: right middle;
    border: tall #1f1f30;
    background: #111118;
    padding: 0 2;
}

/* ── Barre d'outils ── */
#store-toolbar {
    height: 3;
    background: #0c0c10;
    border-bottom: tall #1a1a26;
    width: 100%;
}
.toolbar-btn {
    background: transparent;
    border: none;
    color: #4a4a60;
    height: 3;
    width: auto;
    padding: 0 3;
    min-width: 18;
}
.toolbar-btn:hover {
    color: #c6f135;
    background: #111118;
    border: none;
}
.toolbar-btn:focus {
    border: none;
    color: #c6f135;
}
.toolbar-btn:disabled {
    color: #222230;
    background: transparent;
    border: none;
}
#toolbar-spacer {
    width: 1fr;
    height: 3;
}
.toolbar-divider {
    width: 1;
    height: 3;
    background: #1a1a26;
}

/* ── Barre de recherche ── */
#search-bar {
    height: 3;
    border-bottom: tall #1a1a26;
    background: #111118;
    padding: 0 2;
    display: none;
}
#search-bar.shown {
    display: block;
}
#search-icon {
    color: #3a3a54;
    width: 3;
    content-align: left middle;
}
Input {
    background: transparent;
    border: none;
    color: #eaeaea;
    width: 1fr;
    padding: 0 1;
}
Input:focus {
    border: none;
}

/* ── Corps (split gauche/droite) ── */
#store-body {
    height: 1fr;
    width: 100%;
}

/* ── Liste des scripts (gauche) ── */
#script-list {
    width: 2fr;
    height: 100%;
    border-right: tall #1a1a26;
    background: #09090c;
}
ListView {
    background: #09090c;
    border: none;
    padding: 0;
    height: 100%;
}
ListView > .--highlight {
    background: #111118;
}
ListView:focus {
    border: none;
}
ListItem {
    background: #09090c;
    padding: 0;
    height: 7;
    border-bottom: tall #0f0f13;
}
ListItem:hover {
    background: #0f0f13;
}
ListItem.--highlight {
    background: #111118;
    border-left: outer #c6f135;
}

/* Carte script dans la liste */
.card-row {
    padding: 1 2;
    height: 7;
    width: 100%;
}
.card-info {
    width: 1fr;
    height: 5;
    padding: 0 1;
}
.card-name {
    color: #e0e0e0;
    text-style: bold;
    width: 100%;
}
.card-type {
    color: #3a3a54;
    width: 100%;
}
.card-chip {
    width: auto;
    content-align: right middle;
    color: #3a3a54;
    height: 5;
    padding: 0 1;
}

/* Couleurs des badges */
.chip-ok      { color: #4cd97b; }
.chip-update  { color: #f5a623; }
.chip-missing { color: #555570; }
.chip-unknown { color: #3a3a54; }

/* ── Panneau de détail (droite) ── */
#detail-panel {
    width: 3fr;
    height: 100%;
    background: #0f0f13;
}
#detail-tabs {
    height: 3;
    border-bottom: tall #1a1a26;
    background: #0c0c10;
    padding: 0 2;
}
.detail-tab {
    width: auto;
    content-align: left middle;
    color: #3a3a54;
    padding: 0 2;
    text-style: bold;
    height: 3;
}
.detail-tab.tab-active {
    color: #eaeaea;
}
#detail-content {
    padding: 3 4;
    height: 1fr;
    width: 100%;
}
#detail-empty {
    color: #252538;
    content-align: center middle;
    width: 100%;
    height: 100%;
    text-align: center;
}
#detail-name {
    color: #eaeaea;
    text-style: bold;
    width: 100%;
    margin-bottom: 0;
    display: none;
}
#detail-type {
    color: #3a3a54;
    width: 100%;
    margin-bottom: 2;
    display: none;
}
#detail-desc {
    color: #9a9ab8;
    width: 100%;
    margin-bottom: 2;
    display: none;
}
#detail-status {
    color: #3a3a54;
    width: 100%;
    margin-bottom: 3;
    display: none;
}

/* ── Conteneur fixe des boutons d'action ── */
#detail-actions {
    height: auto;
    padding: 1 4 2 4;
    background: #0f0f13;
    border-top: tall #1a1a26;
    display: none;
}
#detail-actions.shown {
    display: block;
}

/* ── Boutons d'action du panneau détail ── */
#btn-detail-download,
#btn-detail-launch {
    width: 100%;
    height: 3;
    background: #1a1a28;
    color: #eaeaea;
    border: tall #2e2e46;
    text-align: center;
    display: none;
    margin-bottom: 1;
}
#btn-detail-download:hover,
#btn-detail-launch:hover {
    background: #263800;
    border: tall #c6f135;
    color: #c6f135;
}
#btn-detail-download:disabled,
#btn-detail-launch:disabled {
    background: #0c0c10;
    color: #252538;
    border: tall #141420;
}

/* ── Barre de progression ── */
#progress {
    width: 100%;
    height: 1;
    display: none;
}
#progress.shown {
    display: block;
}
ProgressBar > .bar--bar {
    color: #c6f135;
    background: #1f1f30;
}
ProgressBar > .bar--complete {
    color: #c6f135;
}
ProgressBar > .bar--indeterminate {
    color: #c6f135;
}

/* ── Pied de page (log) ── */
#footer {
    height: 1;
    background: #0c0c10;
    border-top: tall #1a1a26;
    padding: 0 2;
    width: 100%;
}
#log-dot {
    width: 2;
    color: #4a4a60;
    content-align: left middle;
}
#log-msg {
    width: 1fr;
    color: #4a4a60;
    content-align: left middle;
}
#log-ver {
    width: auto;
    color: #252538;
    content-align: right middle;
}
"""


# ── Carte de script ───────────────────────────────────────────────────────────

class ScriptCard(ListItem):
    """Élément de la liste des scripts dans le store."""

    def __init__(self, script: dict) -> None:
        super().__init__()
        self._script = script

    def compose(self) -> ComposeResult:
        s = self._script
        with Horizontal(classes="card-row"):
            with Vertical(classes="card-info"):
                yield Static(s["name"], classes="card-name")
                yield Static(s["type"], classes="card-type")
            yield Static("  …", id=f"chip-{s['id']}", classes="card-chip")


# ── Application principale ────────────────────────────────────────────────────

class NeyMenuApp(App):
    """NEY-MENU — Interface store de la Koyney Suite."""

    TITLE    = "NEY-MENU"
    CSS      = _CSS
    BINDINGS = [
        ("ctrl+c", "quit_app",       "Quitter"),
        ("ctrl+f", "toggle_search",  "Rechercher"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._selected_id: str | None = None
        self._statuses: dict[str, tuple[str, str]] = {}  # id → (badge, key)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _script_by_id(self, sid: str) -> dict | None:
        for s in SCRIPTS:
            if s["id"] == sid:
                return s
        return None

    def _installed_count(self) -> int:
        py = _py_dir()
        return sum(1 for s in SCRIPTS if os.path.isfile(os.path.join(py, s["file"])))

    # ── Compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="main"):

            # ── Barre d'outils ──
            with Horizontal(id="store-toolbar"):
                yield Button("⟳  Actualiser", id="btn-refresh",  classes="toolbar-btn")
                yield Static("",              classes="toolbar-divider")
                yield Button("↓  Installer",  id="btn-install",  classes="toolbar-btn")
                yield Static("",              id="toolbar-spacer")
                yield Button("✕  Quitter",    id="btn-quit",     classes="toolbar-btn")

            # ── Barre de recherche (Ctrl+F) ──
            with Horizontal(id="search-bar"):
                yield Static("⊕ ", id="search-icon")
                yield Input(placeholder="Rechercher un script…", id="search-input")
                yield Button("✕", id="btn-search-close", classes="toolbar-btn")

            # ── Corps principal ──
            with Horizontal(id="store-body"):

                # Panneau gauche — liste des scripts
                with Container(id="script-list"):
                    yield ListView(
                        *[ScriptCard(s) for s in SCRIPTS],
                        id="script-listview",
                    )

                # Panneau droit — détail
                with Vertical(id="detail-panel"):
                    with Horizontal(id="detail-tabs"):
                        yield Static("DÉTAIL", id="tab-detail", classes="detail-tab tab-active")

                    with Vertical(id="detail-content"):
                        yield Static(
                            "←  Sélectionnez un script",
                            id="detail-empty",
                        )
                        yield Static("",  id="detail-name")
                        yield Static("",  id="detail-type")
                        yield Static("",  id="detail-desc")
                        yield Static("",  id="detail-status")

                    with Vertical(id="detail-actions"):
                        yield Button("↓  TÉLÉCHARGER / MÀJ", id="btn-detail-download", disabled=True)
                        yield Button("▶  LANCER",             id="btn-detail-launch",   disabled=True)

            # ── Barre de progression ──
            yield ProgressBar(total=100, show_eta=False, id="progress")

            # ── Pied de page (log) ──
            with Horizontal(id="footer"):
                yield Static("●",                  id="log-dot")
                yield Static("  Initialisation…",  id="log-msg")
                yield Static(f"v{VERSION}",         id="log-ver")

    # ── Démarrage ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._set_buttons_enabled(False)
        self._worker_self_update()
        

    # ── Sélection d'un script ─────────────────────────────────────────────────

    def _select_script(self, sid: str) -> None:
        """Affiche les détails du script sélectionné dans le panneau droit."""
        self._selected_id = sid
        s = self._script_by_id(sid)
        if s is None:
            return

        badge, key = self._statuses.get(sid, ("…", "unknown"))

        # Cacher le placeholder
        self.query_one("#detail-empty").styles.display = "none"

        # Nom
        name_w = self.query_one("#detail-name")
        name_w.update(s["name"])
        name_w.styles.display = "block"

        # Type
        type_w = self.query_one("#detail-type")
        type_w.update(s["type"])
        type_w.styles.display = "block"

        # Description
        desc_w = self.query_one("#detail-desc")
        desc_w.update(s["desc"])
        desc_w.styles.display = "block"

        # Statut masqué dans le détail (info déjà visible via le badge dans la liste)
        self.query_one("#detail-status").styles.display = "none"

        # Boutons télécharger / lancer
        self._refresh_detail_buttons(s, key)

    def _refresh_detail_buttons(self, s: dict, key: str) -> None:
        """Affiche uniquement le bouton pertinent selon le statut du script."""
        dl  = self.query_one("#btn-detail-download", Button)
        run = self.query_one("#btn-detail-launch",   Button)
        actions = self.query_one("#detail-actions")
        actions.add_class("shown")

        if key == "ok":
            # Script à jour : on peut lancer, inutile de retélécharger
            dl.styles.display  = "none"
            run.styles.display = "block"
            run.disabled = False
        elif key in ("missing", "update"):
            # Script absent ou obsolète : proposer le téléchargement uniquement
            dl.styles.display  = "block"
            dl.disabled        = not bool(s.get("url"))
            dl.label           = "↓  Installer" if key == "missing" else "↑  Mettre à Jour"
            run.styles.display = "none"
            run.disabled = True
        else:
            # Statut inconnu : afficher télécharger, masquer lancer
            dl.styles.display  = "block"
            dl.disabled        = not bool(s.get("url"))
            dl.label           = "↓  Installer"
            run.styles.display = "none"
            run.disabled = True

    # ── Événements ────────────────────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if isinstance(item, ScriptCard):
            self._select_script(item._script["id"])

    # ── Helpers UI ────────────────────────────────────────────────────────────

    def _log(self, msg: str, level: str = "info") -> None:
        colors = {
            "info": "#4a4a60",
            "ok":   "#4cd97b",
            "warn": "#f5a623",
            "err":  "#f53c3c",
        }
        color = colors.get(level, "#4a4a60")
        self.query_one("#log-dot",  Static).styles.color = color
        msg_w = self.query_one("#log-msg",  Static)
        msg_w.styles.color = color
        msg_w.update(f"  {msg}")

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for btn_id in ("btn-refresh", "btn-install", "btn-detail-download", "btn-detail-launch"):
            try:
                self.query_one(f"#{btn_id}", Button).disabled = not enabled
            except Exception:
                pass

    def _update_chip(self, chip_id: str, badge: str, key: str) -> None:
        """Met à jour le badge dans la liste et, si sélectionné, le panneau détail."""
        try:
            chip = self.query_one(f"#{chip_id}", Static)
            chip.remove_class("chip-ok", "chip-update", "chip-missing", "chip-unknown")
            chip.add_class(f"chip-{key}")
            chip.update(f"  {badge}")
        except Exception:
            pass

        script_id = chip_id.replace("chip-", "")
        self._statuses[script_id] = (badge, key)

        # Rafraîchir le panneau détail si ce script est sélectionné
        if script_id == self._selected_id:
            s = self._script_by_id(script_id)
            if s:
                try:
                    self.query_one("#detail-status", Static).update(badge)
                    self._refresh_detail_buttons(s, key)
                except Exception:
                    pass

    def _update_script_count(self) -> None:
        pass  # widget script-count supprimé

    def _show_progress(self, visible: bool) -> None:
        pb = self.query_one("#progress")
        if visible:
            pb.add_class("shown")
        else:
            pb.remove_class("shown")

    def _set_progress(self, pct: int) -> None:
        self.query_one(ProgressBar).progress = float(pct)

    # ── Action : toggle recherche ─────────────────────────────────────────────

    def action_toggle_search(self) -> None:
        bar = self.query_one("#search-bar")
        if "shown" in bar.classes:
            bar.remove_class("shown")
        else:
            bar.add_class("shown")
            try:
                self.query_one("#search-input", Input).focus()
            except Exception:
                pass

    @on(Input.Changed, "#search-input")
    def _on_search_changed(self, event: Input.Changed) -> None:
        query = event.value.strip().lower()
        for card in self.query(ScriptCard):
            name = card._script["name"].lower()
            card.styles.display = "block" if (not query or query in name) else "none"

    # ── Workers ───────────────────────────────────────────────────────────────

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
            self.call_from_thread(self._log, f"Réseau indisponible — {exc}", "warn")
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

        self.call_from_thread(self._log, "Nouvelle version détectée — mise à jour…", "info")
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

        self.call_from_thread(self._log, "Relancement avec la nouvelle version…", "ok")
        time.sleep(1.2)
        subprocess.Popen([sys.executable, current_path] + sys.argv[1:])
        self.call_from_thread(self.exit)

    def _start_check_statuses(self) -> None:
        self._worker_check_statuses()

    @work(thread=True, name="check-statuses")
    def _worker_check_statuses(self) -> None:
        """Vérifie la présence et la version de chaque script."""
        self.call_from_thread(self._log, "Vérification des statuts…", "info")
        py = _py_dir()

        # Renommages rétro-compatibles
        for alias in ("cotube.pyw", "youtube_downloader.py"):
            _rename_if_needed(py, alias, COTUBE_FILE)

        for s in SCRIPTS:
            path = os.path.join(py, s["file"])
            if s["url"]:
                _, badge, key = _compute_one_status(s["name"], path, s["url"])
            else:
                # Pas d'URL : local only
                if os.path.isfile(path):
                    badge, key = "✓ Présent", "ok"
                else:
                    badge, key = "⊙ Indisponible", "missing"
            self.call_from_thread(self._update_chip, f"chip-{s['id']}", badge, key)

        self.call_from_thread(self._update_script_count)
        self.call_from_thread(self._set_buttons_enabled, True)
        self.call_from_thread(self._log, "Prêt.", "ok")

    @work(thread=True, name="install-script")
    def _worker_install_script(self, sid: str) -> None:
        """Télécharge et installe le script demandé."""
        s = self._script_by_id(sid)
        if s is None or not s["url"]:
            return

        self.call_from_thread(self._set_buttons_enabled, False)
        self.call_from_thread(self._show_progress, True)
        self.call_from_thread(self._set_progress, 0)

        dest = os.path.join(_py_dir(), s["file"])
        self.call_from_thread(self._log, f"Téléchargement de {s['name']}…", "info")

        ok = _download_file(
            s["url"],
            dest,
            s["name"],
            progress_cb=lambda pct: self.call_from_thread(self._set_progress, pct),
        )

        self.call_from_thread(self._show_progress, False)
        if ok:
            self.call_from_thread(self._log, f"{s['name']} installé avec succès.", "ok")
        else:
            self.call_from_thread(self._log, "Erreur lors de l'installation.", "warn")

        self.call_from_thread(self._start_check_statuses)

    # ── Actions boutons ───────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-refresh")
    def _action_refresh(self) -> None:
        self._set_buttons_enabled(False)
        self._start_check_statuses()

    @on(Button.Pressed, "#btn-quit")
    def _action_quit_btn(self) -> None:
        _cleanup_pycache()
        self.exit()

    @on(Button.Pressed, "#btn-search-close")
    def _action_close_search(self) -> None:
        self.query_one("#search-bar").remove_class("shown")

    @on(Button.Pressed, "#btn-detail-download")
    def _action_detail_download(self) -> None:
        """Télécharge / met à jour le script sélectionné."""
        sid = self._selected_id
        if sid:
            self._worker_install_script(sid)

    @on(Button.Pressed, "#btn-detail-launch")
    def _action_detail_launch(self) -> None:
        """Lance le script sélectionné."""
        sid = self._selected_id
        if sid is None:
            return
        s = self._script_by_id(sid)
        if s is None:
            return
        path = os.path.join(_py_dir(), s["file"])
        if not os.path.isfile(path):
            self._log(f"{s['name']} introuvable.", "warn")
            return
        self._log(f"Lancement de {s['name']}…", "info")
        if _TERMUX:
            with self.suspend():
                launch_cotube()
        else:
            _open_in_terminal(path)

    @on(Button.Pressed, "#btn-install")
    def _action_install_btn(self) -> None:
        pass  # Comportement à définir ultérieurement

    def action_quit_app(self) -> None:
        _cleanup_pycache()
        self.exit()


# ══════════════════════════════════════════════════════════════════════════════
#  Point d'entrée
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    # Renommer le titre de la fenêtre terminal
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW("Ney-Menu")
        else:
            sys.stdout.write("\033]0;Ney-Menu\007")
            sys.stdout.flush()
    except Exception:
        pass
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