import os
import sys
import shlex
import subprocess
from pathlib import Path
from typing import Optional, List

try:
    import PySimpleGUI as sg
except Exception:
    sg = None

SCRIPT_NAME = "import_mangadex_bookmarks_to_suwayomi.py"
PACKAGED_CLI = "import_mangadex_bookmarks_to_suwayomi.exe"


def find_cli_executable() -> Optional[Path]:
    here = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    exe = here / PACKAGED_CLI
    return exe if exe.exists() else None


def python_executable() -> str:
    return sys.executable or "python"


def build_args(values: dict) -> List[str]:
    args: List[str] = []
    # Required
    base_url = values.get('-BASE-URL-','').strip()
    if base_url:
        args += ["--base-url", base_url]

    # Follows
    if values.get('-FROM-FOLLOWS-'):
        if values.get('-MD-USER-'):
            args += ["--from-follows", "--md-username", values['-MD-USER-']]
        if values.get('-MD-PASS-'):
            args += ["--md-password", values['-MD-PASS-']]
        if values.get('-FOLLOWS-JSON-'):
            args += ["--follows-json", values['-FOLLOWS-JSON-']]

    # Reading status
    if values.get('-IMPORT-STATUS-'):
        args += ["--import-reading-status"]
        if values.get('-STATUS-MAP-'):
            args += ["--status-category-map", values['-STATUS-MAP-']]

    # Read chapters
    if values.get('-IMPORT-READ-'):
        args += ["--import-read-chapters"]
        try:
            delay = float(values.get('-READ-DELAY-') or 0)
        except Exception:
            delay = 0
        if delay > 0:
            args += ["--read-sync-delay", str(delay)]

    # Category
    if values.get('-CATEGORY-ID-'):
        args += ["--category-id", str(values['-CATEGORY-ID-'])]

    # Migration
    if values.get('-MIGRATE-LIB-'):
        args += ["--migrate-library"]
        if values.get('-MIGRATE-SOURCES-'):
            args += ["--migrate-sources", values['-MIGRATE-SOURCES-']]
        if values.get('-EXCLUDE-SOURCES-'):
            args += ["--exclude-sources", values['-EXCLUDE-SOURCES-']]
        if values.get('-MIGRATE-PREF-ONLY-'):
            args += ["--migrate-preferred-only"]
        if values.get('-BEST-SOURCE-'):
            args += ["--best-source"]
        if values.get('-BEST-GLOBAL-'):
            args += ["--best-source-global"]
        if values.get('-BEST-CANON-'):
            args += ["--best-source-canonical"]
        if values.get('-PREF-LANGS-'):
            args += ["--preferred-langs", values['-PREF-LANGS-']]
        if values.get('-LANG-FALLBACK-'):
            args += ["--lang-fallback"]
        if values.get('-PREFER-SOURCES-'):
            args += ["--prefer-sources", values['-PREFER-SOURCES-']]
        try:
            boost = int(values.get('-PREFER-BOOST-', 3) or 3)
        except Exception:
            boost = 3
        if boost != 3:
            args += ["--prefer-boost", str(boost)]
        if values.get('-KEEP-BOTH-'):
            args += ["--migrate-keep-both"]
            try:
                kbmin = int(values.get('-KEEP-BOTH-MIN-', 1) or 1)
            except Exception:
                kbmin = 1
            if kbmin != 1:
                args += ["--keep-both-min-preferred", str(kbmin)]
        # Remove originals (default is enabled in script). Only add flag if unchecked -> disable.
        if not values.get('-REMOVE-ORIGINAL-'):
            args += ["--no-migrate-remove"]

    # Prune
    if values.get('-PRUNE-ZERO-'):
        args += ["--prune-zero-duplicates"]
        try:
            th = int(values.get('-PRUNE-THRESH-') or 1)
        except Exception:
            th = 1
        if th != 1:
            args += ["--prune-threshold-chapters", str(th)]
    if values.get('-PRUNE-NONPREF-'):
        args += ["--prune-nonpreferred-langs"]
        if values.get('-PREF-LANGS-'):
            args += ["--preferred-langs", values['-PREF-LANGS-']]
        try:
            lth = int(values.get('-PRUNE-LANG-THRESH-') or 1)
        except Exception:
            lth = 1
        if lth != 1:
            args += ["--prune-lang-threshold", str(lth)]
        if values.get('-PRUNE-KEEP-MOST-'):
            args += ["--prune-lang-fallback-keep-most"]
    if values.get('-PRUNE-FILTER-TITLE-'):
        args += ["--prune-filter-title", values['-PRUNE-FILTER-TITLE-']]

    # Misc
    if values.get('-FILTER-TITLE-'):
        args += ["--migrate-filter-title", values['-FILTER-TITLE-']]
    if values.get('-DRY-RUN-'):
        args += ["--dry-run"]
    if values.get('-DEBUG-'):
        args += ["--debug-library"]

    return args


def preset(values: dict, name: str) -> dict:
    v = dict(values)
    if name == 'Prefer English Migration':
        v.update({
            '-MIGRATE-LIB-': True,
            '-MIGRATE-PREF-ONLY-': True,
            '-BEST-SOURCE-': True,
            '-BEST-GLOBAL-': False,
            '-BEST-CANON-': True,
            '-PREF-LANGS-': 'en,en-us',
            '-LANG-FALLBACK-': True,
            '-REMOVE-ORIGINAL-': True,
            '-DRY-RUN-': True,
        })
    elif name == 'Cleanup Non-English':
        v.update({
            '-PRUNE-NONPREF-': True,
            '-PREF-LANGS-': 'en,en-us',
            '-DRY-RUN-': True,
        })
    elif name == 'Keep Both (Quality+Coverage)':
        v.update({
            '-MIGRATE-LIB-': True,
            '-MIGRATE-PREF-ONLY-': True,
            '-BEST-SOURCE-': True,
            '-BEST-GLOBAL-': True,
            '-BEST-CANON-': True,
            '-PREF-LANGS-': 'en,en-us',
            '-LANG-FALLBACK-': True,
            '-PREFER-SOURCES-': 'asura,flame,genz,utoons',
            '-PREFER-BOOST-': 3,
            '-KEEP-BOTH-': True,
            '-KEEP-BOTH-MIN-': 1,
            '-REMOVE-ORIGINAL-': True,
            '-DRY-RUN-': True,
        })
    return v


def _pwsh_binary() -> str:
    # Prefer PowerShell 7 (pwsh) if available, else Windows PowerShell
    for cand in ("pwsh", "powershell"):
        try:
            subprocess.run([cand, "-NoLogo", "-NoProfile", "-Command", "$PSVersionTable.PSVersion"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return cand
        except Exception:
            continue
    return "powershell"


def launch_command(cmd_list: List[str], save_log: bool, log_path: Optional[str]):
    pwsh = _pwsh_binary()
    cli_exe = find_cli_executable()
    if cli_exe is not None:
        # Run packaged console importer directly
        full_cmd = [str(cli_exe), *cmd_list]
        if save_log and log_path:
            # Use PowerShell Tee-Object to save and display
            ps_cmd = ' '.join([shlex.quote(p) for p in full_cmd]) + f" | Tee-Object -FilePath {shlex.quote(log_path)}"
            subprocess.Popen([pwsh, "-NoExit", "-Command", ps_cmd])
        else:
            subprocess.Popen(full_cmd)
        return
    # Fallback to calling python script
    py = python_executable()
    script = str(Path(__file__).parent / SCRIPT_NAME)
    full_cmd = [py, script, *cmd_list]
    if save_log and log_path:
        ps_cmd = ' '.join([shlex.quote(p) for p in full_cmd]) + f" | Tee-Object -FilePath {shlex.quote(log_path)}"
        subprocess.Popen([pwsh, "-NoExit", "-Command", ps_cmd])
    else:
        subprocess.Popen([pwsh, "-NoExit", "-Command", ' '.join([shlex.quote(p) for p in full_cmd])])


def main():
    if sg is None:
        print("PySimpleGUI is not installed. Install with: pip install PySimpleGUI")
        sys.exit(1)
    if hasattr(sg, 'theme'):
        sg.theme('SystemDefault')
    elif hasattr(sg, 'ChangeLookAndFeel'):
        sg.ChangeLookAndFeel('SystemDefault')

    presets = ["Prefer English Migration", "Cleanup Non-English", "Keep Both (Quality+Coverage)"]

    migrate_col = [
        [sg.Checkbox('Migrate library', key='-MIGRATE-LIB-')],
        [sg.Text('Preferred sources (comma)'), sg.Input(key='-MIGRATE-SOURCES-', size=(40,1))],
        [sg.Text('Exclude sources (comma)'), sg.Input(key='-EXCLUDE-SOURCES-', size=(40,1), default_text='comick,hitomi')],
        [sg.Checkbox('Preferred only', key='-MIGRATE-PREF-ONLY-'), sg.Checkbox('Best source', key='-BEST-SOURCE-'), sg.Checkbox('Global', key='-BEST-GLOBAL-'), sg.Checkbox('Canonical', key='-BEST-CANON-')],
        [sg.Text('Preferred languages'), sg.Input(key='-PREF-LANGS-', size=(30,1), default_text='en,en-us'), sg.Checkbox('Allow non-preferred fallback', key='-LANG-FALLBACK-')],
        [sg.Text('Prefer sources (quality bias)'), sg.Input(key='-PREFER-SOURCES-', size=(30,1), default_text='asura,flame,genz,utoons'), sg.Text('Boost'), sg.Input(key='-PREFER-BOOST-', size=(5,1), default_text='3')],
        [sg.Checkbox('Keep both (quality + coverage)', key='-KEEP-BOTH-'), sg.Text('Second must have >= preferred ch.'), sg.Input(key='-KEEP-BOTH-MIN-', size=(5,1), default_text='1')],
        [sg.Checkbox('Remove original after migration (default ON)', key='-REMOVE-ORIGINAL-', default=True)],
        [sg.Text('Filter title (optional)'), sg.Input(key='-FILTER-TITLE-', size=(40,1))],
    ]

    prune_col = [
        [sg.Checkbox('Prune zero/low-chapter duplicates', key='-PRUNE-ZERO-'), sg.Text('Keep threshold'), sg.Input(key='-PRUNE-THRESH-', size=(5,1), default_text='1')],
        [sg.Checkbox('Prune non-preferred language variants', key='-PRUNE-NONPREF-'), sg.Text('Preferred-lang threshold'), sg.Input(key='-PRUNE-LANG-THRESH-', size=(5,1), default_text='1')],
        [sg.Checkbox('If no preferred, keep only most chapters', key='-PRUNE-KEEP-MOST-')],
        [sg.Text('Prune filter title (optional)'), sg.Input(key='-PRUNE-FILTER-TITLE-', size=(40,1))],
    ]

    follows_col = [
        [sg.Checkbox('Fetch MangaDex follows', key='-FROM-FOLLOWS-')],
        [sg.Text('MD Username'), sg.Input(key='-MD-USER-', size=(25,1))],
        [sg.Text('MD Password'), sg.Input(key='-MD-PASS-', password_char='*', size=(25,1))],
        [sg.Text('Save follows JSON'), sg.Input(key='-FOLLOWS-JSON-', size=(35,1)), sg.FileSaveAs('Browse...', file_types=(('JSON','*.json'),))],
        [sg.Checkbox('Import reading statuses', key='-IMPORT-STATUS-')],
        [sg.Text('Status->Category map'), sg.Input(key='-STATUS-MAP-', size=(40,1), tooltip='e.g. completed=5,reading=2,on_hold=7')],
        [sg.Checkbox('Import read chapters', key='-IMPORT-READ-'), sg.Text('Delay (s)'), sg.Input(key='-READ-DELAY-', size=(6,1), default_text='1')],
        [sg.Text('Category ID (optional)'), sg.Input(key='-CATEGORY-ID-', size=(10,1))],
    ]

    misc_col = [
        [sg.Text('Suwayomi Base URL'), sg.Input(key='-BASE-URL-', size=(40,1), default_text='http://127.0.0.1:4567')],
        [sg.Checkbox('Dry run', key='-DRY-RUN-', default=True), sg.Checkbox('Debug output', key='-DEBUG-')],
        [sg.Checkbox('Save log to file', key='-SAVE-LOG-'), sg.Input(key='-LOG-PATH-', size=(35,1)), sg.FileSaveAs('Log path...', file_types=(('Log/Text','*.log;*.txt'),))],
        [sg.Text('Preset'), sg.Combo(presets, key='-PRESET-', readonly=True, size=(30,1)), sg.Button('Apply Preset')],
    ]

    layout = [
        [sg.TabGroup([[
            sg.Tab('Migrate', migrate_col),
            sg.Tab('Prune', prune_col),
            sg.Tab('Follows', follows_col),
            sg.Tab('Misc', misc_col),
        ]])],
        [sg.Button('Run Script', bind_return_key=True), sg.Button('Reset'), sg.Button('Exit')]
    ]

    win = sg.Window('MangaDex → Suwayomi Control Panel', layout)

    values = win.read(timeout=0)[1] or {}
    while True:
        ev, values = win.read()
        if ev in (sg.WIN_CLOSED, 'Exit'):
            break
        if ev == 'Apply Preset':
            name = values.get('-PRESET-')
            if name:
                values = preset(values, name)
                for k, v in values.items():
                    try:
                        win[k].update(v)
                    except Exception:
                        pass
        if ev == 'Reset':
            for k in list(values.keys()):
                try:
                    if isinstance(win[k], sg.Checkbox):
                        win[k].update(False)
                    elif isinstance(win[k], sg.Input):
                        win[k].update('')
                except Exception:
                    pass
            win['-BASE-URL-'].update('http://127.0.0.1:4567')
            win['-DRY-RUN-'].update(True)
        if ev == 'Run Script':
            if not values.get('-BASE-URL-'):
                sg.popup_error('Base URL is required')
                continue
            cmd_args = build_args(values)
            save_log = bool(values.get('-SAVE-LOG-'))
            log_path = values.get('-LOG-PATH-') or None
            try:
                launch_command(cmd_args, save_log, log_path)
                sg.popup_ok('Launched. Check the console window for output.')
            except Exception as e:
                sg.popup_error(f"Failed to launch: {e}")

    win.close()


if __name__ == '__main__':
    main()
