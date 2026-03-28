# CO-MENU · v2.2

> Lanceur central de la suite **CoTEAM** — accédez à CO-FLIX, CO-CHAN, CO-SAMA et CO-TUBE depuis un seul menu interactif.

```
╔══════════════════════════════════════════════════════════════════╗
║    ██████╗ ██████╗       ███╗   ███╗███████╗███╗   ██╗██╗   ██╗  ║
║   ██╔════╝██╔═══██╗      ████╗ ████║██╔════╝████╗  ██║██║   ██║  ║
║   ██║     ██║   ██║█████╗██╔████╔██║█████╗  ██╔██╗ ██║██║   ██║  ║
║   ██║     ██║   ██║╚════╝██║╚██╔╝██║██╔══╝  ██║╚██╗██║██║   ██║  ║
║   ╚██████╗╚██████╔╝      ██║ ╚═╝ ██║███████╗██║ ╚████║╚██████╔╝  ║
║    ╚═════╝ ╚═════╝       ╚═╝     ╚═╝╚══════╝╚═╝  ╚═══╝ ╚═════╝   ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## Contenu du menu

| Option | Script | Description |
|---|---|---|
| 🎬 Films / Séries | `Co-flix.py` | Téléchargeur de films et séries |
| 🌸 Anime | `Co-chan.py` | Téléchargeur d'animés (VOSTFR) |
| 📖 Scan / Manga | `Co-sama.py` | Téléchargeur de scans et mangas |
| 🔴 YouTube | `Co-tube.py` | Téléchargeur de vidéos YouTube |
| ⬇️ Mise à jour | — | Met à jour Co-chan, Co-sama et Co-tube |
| ❌ Quitter | — | Ferme CO-MENU proprement |

---

## Compatibilité

| Plateforme | Navigation | Chemin d'installation |
|---|---|---|
| Windows | Flèches ↑↓ + Entrée | `%LOCALAPPDATA%\CoTEAM\` |
| Linux / macOS | Flèches ↑↓ + Entrée | `~/.local/share/CoTEAM/` |
| Android (Termux) | Saisie numérique `[1]…[n]` | `~/.local/share/CoTEAM/` |

---

## Prérequis

- **Python 3.8+**
- Aucune dépendance externe — CO-MENU n'utilise que la bibliothèque standard Python.

---

## Installation

### Windows

```bat
curl -o Co-Menu.py https://raw.githubusercontent.com/Bicode-dev/Co-Menu/refs/heads/main/Co-Menu.py
python Co-Menu.py
```

### Linux / macOS

```bash
curl -o Co-Menu.py https://raw.githubusercontent.com/Bicode-dev/Co-Menu/refs/heads/main/Co-Menu.py
python3 Co-Menu.py
```

### Android (Termux)

```bash
pkg install python
curl -o Co-Menu.py https://raw.githubusercontent.com/Bicode-dev/Co-Menu/refs/heads/main/Co-Menu.py
python Co-Menu.py
```

---

## Utilisation

Lancez simplement le script :

```bash
python Co-Menu.py      # Windows
python3 Co-Menu.py     # Linux / macOS / Termux
```

Au démarrage, CO-MENU effectue automatiquement les opérations suivantes :

1. **Auto-mise à jour** — compare le fichier local avec la version GitHub via hash SHA-256. Si une nouvelle version est détectée, le script se met à jour et se relance tout seul.
2. **Vérification des scripts** — signale les scripts manquants et invite à les installer via le menu *Mise à jour*.
3. **Panneau de statut** — affiche l'état de chaque script directement dans le menu (à jour, mise à jour disponible, absent, etc.).

### Navigation PC (Windows / Linux / macOS)

| Touche | Action |
|---|---|
| `↑` / `↓` | Déplacer le curseur |
| `Entrée` | Valider le choix |
| `Échap` | Quitter |

### Navigation Termux (Android)

Entrez le numéro correspondant à l'option souhaitée, puis validez avec `Entrée`. Tapez `0` pour quitter.

---

## Mise à jour des scripts enfants

Depuis le menu, sélectionnez **⬇️ Mise à jour des scripts** pour télécharger ou mettre à jour Co-chan, Co-sama et Co-tube.

> **Co-flix.py** n'est **pas** téléchargé automatiquement. Placez-le manuellement dans le dossier CoTEAM (voir ci-dessous).

---

## Structure des fichiers

```
# Windows
%LOCALAPPDATA%\CoTEAM\
├── Co-Menu.py       ← lanceur principal (auto-mis à jour)
└── Co-Menu\
    ├── Co-chan.py
    ├── Co-sama.py
    ├── Co-tube.py
    └── Co-flix.py   ← à placer manuellement

# Linux / macOS / Termux
~/.local/share/CoTEAM/
├── Co-Menu.py
└── Co-Menu/
    ├── Co-chan.py
    ├── Co-sama.py
    ├── Co-tube.py
    └── Co-flix.py
```

---

## Panneau de statut

Le menu affiche un panneau **ETAT DES SCRIPTS** résumant la situation de chaque script :

| Badge | Signification |
|---|---|
| `✔ A jour` | Le script local correspond à la version GitHub |
| `^ MaJ (+Xo)` | Une mise à jour est disponible |
| `✘ Manquant` | Le script n'est pas encore téléchargé |
| `* Manuel` | Le script est présent mais géré manuellement (Co-flix) |
| `? Inconnu` | Taille distante non disponible (réseau inaccessible) |

Le statut est mis en cache **5 minutes** pour éviter des requêtes réseau répétées.

---

## Dépôts liés

| Script | Dépôt |
|---|---|
| Co-Menu | [Bicode-dev/Co-Menu](https://github.com/Bicode-dev/Co-Menu) |
| Co-Chan | [Bicode-dev/anime_Co-Chan_download](https://github.com/Bicode-dev/anime_Co-Chan_download) |
| Co-Sama | [Bicode-dev/Scan_Co-Sama_download](https://github.com/Bicode-dev/Scan_Co-Sama_download) |
| Co-Tube | [Bicode-dev/Co-tube](https://github.com/Bicode-dev/Co-tube) |

---

## Licence

Voir le fichier `LICENSE` du dépôt.
