import sys
import shlex
import subprocess
from pathlib import Path
import os
import webbrowser
import json
from typing import List, Optional
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import scrolledtext
import tkinter.font as tkfont

# Optional Markdown/HTML rendering support
try:
    from tkhtmlview import HTMLScrolledText  # type: ignore
    _HAS_HTML = True
except Exception:
    _HAS_HTML = False
try:
    import markdown as _md  # type: ignore
    _HAS_MD = True
except Exception:
    _HAS_MD = False

SCRIPT_NAME = "import_mangadex_bookmarks_to_suwayomi.py"
PACKAGED_CLI = "import_mangadex_bookmarks_to_suwayomi.exe"


def find_cli_executable() -> Optional[Path]:
    here = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    exe = here / PACKAGED_CLI
    return exe if exe.exists() else None


def python_executable() -> str:
    return sys.executable or "python"


def _pwsh_binary() -> str:
    for cand in ("pwsh", "powershell"):
        try:
            subprocess.run([cand, "-NoLogo", "-NoProfile", "-Command", "$PSVersionTable.PSVersion"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return cand
        except Exception:
            continue
    return "powershell"


def build_args(v: dict) -> List[str]:
    args: List[str] = []
    base_url = v['base_url'].get().strip()
    if base_url:
        args += ["--base-url", base_url]

    # Follows
    if v['from_follows'].get():
        args += ["--from-follows"]
        if v['md_user'].get().strip():
            args += ["--md-username", v['md_user'].get().strip()]
        if v['md_pass'].get().strip():
            args += ["--md-password", v['md_pass'].get().strip()]
        if v['follows_json'].get().strip():
            args += ["--follows-json", v['follows_json'].get().strip()]

    # Reading status
    if v['import_status'].get():
        args += ["--import-reading-status"]
        if v['status_map'].get().strip():
            args += ["--status-category-map", v['status_map'].get().strip()]

    # Read chapters
    if v['import_read'].get():
        args += ["--import-read-chapters"]
        delay = v['read_delay'].get().strip()
        if delay:
            args += ["--read-sync-delay", delay]

    # Category
    if v['category_id'].get().strip():
        args += ["--category-id", v['category_id'].get().strip()]

    # Migration
    if v['migrate_lib'].get():
        args += ["--migrate-library"]
        if v['migrate_sources'].get().strip():
            args += ["--migrate-sources", v['migrate_sources'].get().strip()]
        if v['exclude_sources'].get().strip():
            args += ["--exclude-sources", v['exclude_sources'].get().strip()]
        if v['migrate_pref_only'].get():
            args += ["--migrate-preferred-only"]
        if v['best_source'].get():
            args += ["--best-source"]
        if v['best_global'].get():
            args += ["--best-source-global"]
        if v['best_canon'].get():
            args += ["--best-source-canonical"]
        if v['pref_langs'].get().strip():
            args += ["--preferred-langs", v['pref_langs'].get().strip()]
        if v['lang_fallback'].get():
            args += ["--lang-fallback"]
        if v['prefer_sources'].get().strip():
            args += ["--prefer-sources", v['prefer_sources'].get().strip()]
        if v['prefer_boost'].get().strip() and v['prefer_boost'].get().strip() != '3':
            args += ["--prefer-boost", v['prefer_boost'].get().strip()]
        if v['keep_both'].get():
            args += ["--migrate-keep-both"]
            if v['keep_both_min'].get().strip() and v['keep_both_min'].get().strip() != '1':
                args += ["--keep-both-min-preferred", v['keep_both_min'].get().strip()]
        if not v['remove_original'].get():
            args += ["--no-migrate-remove"]

    # Prune
    if v['prune_zero'].get():
        args += ["--prune-zero-duplicates"]
        if v['prune_thresh'].get().strip() and v['prune_thresh'].get().strip() != '1':
            args += ["--prune-threshold-chapters", v['prune_thresh'].get().strip()]
    if v['prune_nonpref'].get():
        args += ["--prune-nonpreferred-langs"]
        if v['pref_langs'].get().strip():
            args += ["--preferred-langs", v['pref_langs'].get().strip()]
        if v['prune_lang_thresh'].get().strip() and v['prune_lang_thresh'].get().strip() != '1':
            args += ["--prune-lang-threshold", v['prune_lang_thresh'].get().strip()]
        if v['prune_keep_most'].get():
            args += ["--prune-lang-fallback-keep-most"]
    if v['prune_filter_title'].get().strip():
        args += ["--prune-filter-title", v['prune_filter_title'].get().strip()]

    # Misc
    if v['filter_title'].get().strip():
        args += ["--migrate-filter-title", v['filter_title'].get().strip()]
    if v['dry_run'].get():
        args += ["--dry-run"]
    if v['debug'].get():
        args += ["--debug-library"]

    return args


def launch_command(cmd_list: List[str], save_log: bool, log_path: Optional[str]):
    pwsh = _pwsh_binary()
    cli_exe = find_cli_executable()
    if cli_exe is not None:
        full_cmd = [str(cli_exe), *cmd_list]
        if save_log and log_path:
            ps_cmd = ' '.join([shlex.quote(p) for p in full_cmd]) + f" | Tee-Object -FilePath {shlex.quote(log_path)}"
            subprocess.Popen([pwsh, "-NoExit", "-Command", ps_cmd])
        else:
            subprocess.Popen(full_cmd)
        return
    py = python_executable()
    script = str(Path(__file__).parent / SCRIPT_NAME)
    full_cmd = [py, script, *cmd_list]
    if save_log and log_path:
        ps_cmd = ' '.join([shlex.quote(p) for p in full_cmd]) + f" | Tee-Object -FilePath {shlex.quote(log_path)}"
        subprocess.Popen([pwsh, "-NoExit", "-Command", ps_cmd])
    else:
        subprocess.Popen([pwsh, "-NoExit", "-Command", ' '.join([shlex.quote(p) for p in full_cmd])])


def apply_preset(v: dict, name: str):
    if name == 'Prefer English Migration':
        v['migrate_lib'].set(True)
        v['migrate_pref_only'].set(True)
        v['best_source'].set(True)
        v['best_global'].set(False)
        v['best_canon'].set(True)
        v['pref_langs'].set('en,en-us')
        v['lang_fallback'].set(True)
        v['remove_original'].set(True)
        v['dry_run'].set(True)
    elif name == 'Cleanup Non-English':
        v['prune_nonpref'].set(True)
        v['pref_langs'].set('en,en-us')
        v['dry_run'].set(True)
    elif name == 'Keep Both (Quality+Coverage)':
        v['migrate_lib'].set(True)
        v['migrate_pref_only'].set(True)
        v['best_source'].set(True)
        v['best_global'].set(True)
        v['best_canon'].set(True)
        v['pref_langs'].set('en,en-us')
        v['lang_fallback'].set(True)
        v['prefer_sources'].set('asura,flame,genz,utoons')
        v['prefer_boost'].set('3')
        v['keep_both'].set(True)
        v['keep_both_min'].set('1')
        v['remove_original'].set(True)
        v['dry_run'].set(True)


# ---- Config helpers ----

def _config_dir() -> Path:
    base = Path(os.getenv('APPDATA') or Path.home())
    return base / 'MangaDex_Suwayomi'


def _load_config() -> dict:
    try:
        p = _config_dir() / 'config.json'
        if p.exists():
            return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return {}


def _save_config(cfg: dict) -> None:
    try:
        d = _config_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / 'config.json').write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    except Exception:
        pass


def main():
    root = tk.Tk()
    root.title('MangaDex → Suwayomi Control Panel (Tk)')

    def open_manual():
        manual = Path(__file__).parent / 'USER_MANUAL.md'
        if manual.exists():
            try:
                if os.name == 'nt' and hasattr(os, 'startfile'):
                    os.startfile(str(manual))  # type: ignore[attr-defined]
                    return
            except Exception:
                pass
            try:
                webbrowser.open(manual.as_uri())
                return
            except Exception:
                pass
        messagebox.showinfo('Manual not found', 'USER_MANUAL.md could not be opened. Please open it from the repository root.')

    def show_manual_popup():
        manual = Path(__file__).parent / 'USER_MANUAL.md'
        if not manual.exists():
            messagebox.showinfo('Manual not found', 'USER_MANUAL.md could not be found in the repository root.')
            return
        try:
            content = manual.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to read manual: {e}')
            return

        top = tk.Toplevel(root)
        top.title('User Manual')
        top.geometry('900x700')
        try:
            _geo_cfg = _load_config()
            if isinstance(_geo_cfg.get('manual_geometry'), str):
                top.geometry(_geo_cfg['manual_geometry'])
        except Exception:
            pass

        # Toolbar
        bar = ttk.Frame(top)
        bar.pack(fill='x')

        # Preferences
        cfg = _load_config()
        default_sz = str(cfg.get('manual_font_size', 13))
        default_render = bool(cfg.get('manual_render_md', bool(_HAS_HTML and _HAS_MD)))
        default_dark = bool(cfg.get('manual_dark_mode', False))

        render_md = tk.BooleanVar(top, value=default_render)
        size_var = tk.StringVar(top, value=default_sz)
        dark_var = tk.BooleanVar(top, value=default_dark)
        find_var = tk.StringVar(top, value=str(cfg.get('manual_find_text', '')))
        case_var = tk.BooleanVar(top, value=bool(cfg.get('manual_find_case', False)))

        ttk.Label(bar, text='Font size').pack(side='left', padx=(6, 2))
        size_spin = ttk.Spinbox(bar, from_=8, to=24, width=4, textvariable=size_var)
        size_spin.pack(side='left', padx=(0, 6), pady=4)
        ttk.Button(bar, text='Apply', command=lambda: _apply_size()).pack(side='left', padx=(0, 6), pady=4)
        ttk.Checkbutton(bar, text='Rendered Markdown', variable=render_md, command=lambda: _switch_mode()).pack(side='left', padx=(6, 6))
        ttk.Checkbutton(bar, text='Dark', variable=dark_var, command=lambda: _switch_mode()).pack(side='left', padx=(0, 6))

        ttk.Label(bar, text='Find').pack(side='left')
        find_entry = ttk.Entry(bar, textvariable=find_var, width=28)
        find_entry.pack(side='left', padx=(4, 2))
        ttk.Checkbutton(bar, text='Aa', variable=case_var, command=lambda: (_rebuild_find())).pack(side='left', padx=(2, 6))
        ttk.Button(bar, text='Prev', command=lambda: _find_prev()).pack(side='left', padx=(0, 2))
        ttk.Button(bar, text='Next', command=lambda: _find_next()).pack(side='left', padx=(0, 6))

        ttk.Button(bar, text='Open Externally', command=open_manual).pack(side='right', padx=4, pady=4)
        ttk.Button(bar, text='Close', command=top.destroy).pack(side='right', padx=4, pady=4)

        # Content container
        content_frame = ttk.Frame(top)
        content_frame.pack(fill='both', expand=True)

        # State for viewer/text
        state = {'mode': 'text', 'widget': None, 'tw': None}
        text_font = tkfont.Font(family='Segoe UI', size=int(size_var.get()))

        def _apply_plain_theme(tw: tk.Text):
            try:
                if dark_var.get():
                    tw.configure(bg='#0f1115', fg='#e6edf3', insertbackground='#e6edf3',
                                 selectbackground='#264f78', selectforeground='#ffffff')
                else:
                    tw.configure(bg='#ffffff', fg='#000000', insertbackground='#000000',
                                 selectbackground='#bcdfff', selectforeground='#000000')
            except Exception:
                pass

        def _render_html():
            # Render markdown to HTML and display (selection supported via HTMLScrolledText)
            html_body = _md.markdown(content, extensions=['extra', 'fenced_code', 'sane_lists', 'tables', 'toc'])
            try:
                sz = max(8, min(36, int(size_var.get())))
            except Exception:
                sz = 13
            # Avoid <style> blocks (unsupported by tkhtmlview); use simple wrapper div
            if dark_var.get():
                html = (
                    f"<div style=\"font-family:Segoe UI, Arial, sans-serif; font-size:{sz}px; line-height:1.6; padding:10px; color:#e6edf3; background-color:#0f1115;\">{html_body}</div>"
                )
            else:
                html = f"<div style=\"font-family:Segoe UI, Arial, sans-serif; font-size:{sz}px; line-height:1.5; padding:10px;\">{html_body}</div>"
            viewer = HTMLScrolledText(content_frame, html=html)

            def _find_text_widget(w: tk.Widget):
                if isinstance(w, tk.Text):
                    return w
                for ch in w.winfo_children():
                    twx = _find_text_widget(ch)
                    if twx is not None:
                        return twx
                return None

            tw = _find_text_widget(viewer)
            if tw is not None:
                try:
                    tw.configure(state='normal', exportselection=False,
                                 selectbackground='#bcdfff', selectforeground='#000000',
                                 inactiveselectbackground='#dceeff', cursor='xterm', wrap='word')
                    tw.tag_configure('SEL_CUSTOM', background='#bcdfff', foreground='#000000')
                    tw.tag_raise('SEL_CUSTOM')
                    _apply_plain_theme(tw)

                    def _update_sel(event=None):
                        try:
                            start = tw.index('sel.first')
                            end = tw.index('sel.last')
                        except tk.TclError:
                            tw.tag_remove('SEL_CUSTOM', '1.0', 'end')
                            return
                        tw.tag_remove('SEL_CUSTOM', '1.0', 'end')
                        tw.tag_add('SEL_CUSTOM', start, end)

                    for seq in ('<<Selection>>', '<ButtonRelease-1>', '<B1-Motion>', '<KeyRelease>'):
                        tw.bind(seq, _update_sel, add='+')
                    tw.focus_set()
                except Exception:
                    pass
            viewer.pack(fill='both', expand=True)
            state['mode'] = 'html'
            state['widget'] = viewer
            state['tw'] = tw

        def _render_text():
            txt = scrolledtext.ScrolledText(content_frame, wrap='word')
            txt.pack(fill='both', expand=True)
            txt.insert('1.0', content)
            txt.configure(state='disabled', font=text_font)
            _apply_plain_theme(txt)
            state['mode'] = 'text'
            state['widget'] = txt
            state['tw'] = txt

        def _clear_content():
            for child in content_frame.winfo_children():
                child.destroy()

        def _persist():
            try:
                cur_sz = int(size_var.get())
            except Exception:
                cur_sz = 13
            cfg.update({
                'manual_font_size': cur_sz,
                'manual_render_md': bool(render_md.get()),
                'manual_dark_mode': bool(dark_var.get()),
                'manual_find_text': find_var.get(),
                'manual_find_case': bool(case_var.get()),
                'manual_geometry': top.winfo_geometry(),
            })
            _save_config(cfg)

        def _apply_size():
            # Adjust size for current mode
            try:
                new_size = int(size_var.get())
            except Exception:
                new_size = 13
            if state['mode'] == 'text':
                text_font.configure(size=new_size)
            elif state['mode'] == 'html':
                _clear_content()
                _render_html()
            _persist()
            _rebuild_find()

        def _switch_mode():
            _clear_content()
            if render_md.get() and _HAS_HTML and _HAS_MD:
                try:
                    _render_html()
                except Exception:
                    _render_text()
            else:
                _render_text()
            _persist()
            _rebuild_find()

        def _on_close():
            _persist()
            top.destroy()
        top.protocol('WM_DELETE_WINDOW', _on_close)

        # Initial render
        if render_md.get():
            try:
                _render_html()
            except Exception:
                _render_text()
        else:
            _render_text()

        # -------- Find / Search implementation --------
        def _clear_find_tags():
            tw = state.get('tw')
            if not isinstance(tw, tk.Text):
                return
            try:
                tw.tag_remove('FIND_HL', '1.0', 'end')
                tw.tag_remove('FIND_CUR', '1.0', 'end')
            except Exception:
                pass

        def _rebuild_find():
            tw = state.get('tw')
            if not isinstance(tw, tk.Text):
                return
            _clear_find_tags()
            pattern = find_var.get()
            if not pattern:
                return
            try:
                tw.tag_configure('FIND_HL', background='#fff3b0')
                tw.tag_configure('FIND_CUR', background='#ffd54f')
                start = '1.0'
                while True:
                    idx = tw.search(pattern, start, 'end', nocase=(not case_var.get()))
                    if not idx:
                        break
                    end = f"{idx}+{len(pattern)}c"
                    tw.tag_add('FIND_HL', idx, end)
                    start = end
            except Exception:
                pass

        def _goto_match(next_dir: int):
            tw = state.get('tw')
            if not isinstance(tw, tk.Text):
                return
            pattern = find_var.get()
            if not pattern:
                return
            try:
                cur = tw.index('insert')
            except Exception:
                cur = '1.0'
            found_idx = None
            if next_dir >= 0:
                idx = tw.search(pattern, cur, 'end', nocase=(not case_var.get()))
                if not idx:
                    idx = tw.search(pattern, '1.0', 'end', nocase=(not case_var.get()))
                found_idx = idx
            else:
                # Backward search emulation
                last_idx = None
                start = '1.0'
                while True:
                    idx = tw.search(pattern, start, 'end', nocase=(not case_var.get()))
                    if not idx or tw.compare(idx, '>=', cur):
                        break
                    last_idx = idx
                    start = f"{idx}+1c"
                found_idx = last_idx
            if found_idx:
                end = f"{found_idx}+{len(pattern)}c"
                try:
                    tw.tag_remove('FIND_CUR', '1.0', 'end')
                    tw.tag_add('FIND_CUR', found_idx, end)
                    tw.mark_set('insert', end)
                    tw.see(found_idx)
                    tw.focus_set()
                except Exception:
                    pass

        def _find_next():
            if not find_var.get():
                return
            _goto_match(1)

        def _find_prev():
            if not find_var.get():
                return
            _goto_match(-1)

        # Bind find entry updates
        try:
            find_entry.bind('<Return>', lambda e: (_rebuild_find(), _find_next()))
        except Exception:
            pass
        _rebuild_find()

    # GUI values
    vals = {
        # Misc
        'base_url': tk.StringVar(value='http://127.0.0.1:4567'),
        'dry_run': tk.BooleanVar(value=True),
        'debug': tk.BooleanVar(value=False),
        'save_log': tk.BooleanVar(value=False),
        'log_path': tk.StringVar(value=''),
        'preset': tk.StringVar(value=''),
        # Follows
        'from_follows': tk.BooleanVar(value=False),
        'md_user': tk.StringVar(value=''),
        'md_pass': tk.StringVar(value=''),
        'follows_json': tk.StringVar(value=''),
        'import_status': tk.BooleanVar(value=False),
        'status_map': tk.StringVar(value=''),
        'import_read': tk.BooleanVar(value=False),
        'read_delay': tk.StringVar(value='1'),
        'category_id': tk.StringVar(value=''),
        # Migrate
        'migrate_lib': tk.BooleanVar(value=False),
        'migrate_sources': tk.StringVar(value=''),
        'exclude_sources': tk.StringVar(value='comick,hitomi'),
        'migrate_pref_only': tk.BooleanVar(value=False),
        'best_source': tk.BooleanVar(value=False),
        'best_global': tk.BooleanVar(value=False),
        'best_canon': tk.BooleanVar(value=False),
        'pref_langs': tk.StringVar(value='en,en-us'),
        'lang_fallback': tk.BooleanVar(value=False),
        'prefer_sources': tk.StringVar(value='asura,flame,genz,utoons'),
        'prefer_boost': tk.StringVar(value='3'),
        'keep_both': tk.BooleanVar(value=False),
        'keep_both_min': tk.StringVar(value='1'),
        'remove_original': tk.BooleanVar(value=True),
        'filter_title': tk.StringVar(value=''),
        # Prune
        'prune_zero': tk.BooleanVar(value=False),
        'prune_thresh': tk.StringVar(value='1'),
        'prune_nonpref': tk.BooleanVar(value=False),
        'prune_lang_thresh': tk.StringVar(value='1'),
        'prune_keep_most': tk.BooleanVar(value=False),
        'prune_filter_title': tk.StringVar(value=''),
    }

    # Top bar with Help button on the right
    topbar = ttk.Frame(root)
    topbar.pack(fill='x', padx=8, pady=(8, 0))
    ttk.Button(topbar, text='?', width=3, command=show_manual_popup).pack(side='right')

    nb = ttk.Notebook(root)

    # Migrate tab
    mig = ttk.Frame(nb)
    nb.add(mig, text='Migrate')
    r = 0
    ttk.Checkbutton(mig, text='Migrate library', variable=vals['migrate_lib']).grid(row=r, column=0, sticky='w'); r+=1
    ttk.Label(mig, text='Preferred sources (comma)').grid(row=r, column=0, sticky='w'); ttk.Entry(mig, textvariable=vals['migrate_sources'], width=50).grid(row=r, column=1, sticky='we'); r+=1
    ttk.Label(mig, text='Exclude sources (comma)').grid(row=r, column=0, sticky='w'); ttk.Entry(mig, textvariable=vals['exclude_sources'], width=50).grid(row=r, column=1, sticky='we'); r+=1
    ttk.Checkbutton(mig, text='Preferred only', variable=vals['migrate_pref_only']).grid(row=r, column=0, sticky='w')
    ttk.Checkbutton(mig, text='Best source', variable=vals['best_source']).grid(row=r, column=1, sticky='w')
    ttk.Checkbutton(mig, text='Global', variable=vals['best_global']).grid(row=r, column=2, sticky='w')
    ttk.Checkbutton(mig, text='Canonical', variable=vals['best_canon']).grid(row=r, column=3, sticky='w'); r+=1
    ttk.Label(mig, text='Preferred languages').grid(row=r, column=0, sticky='w'); ttk.Entry(mig, textvariable=vals['pref_langs'], width=30).grid(row=r, column=1, sticky='w')
    ttk.Checkbutton(mig, text='Allow non-preferred fallback', variable=vals['lang_fallback']).grid(row=r, column=2, sticky='w'); r+=1
    ttk.Label(mig, text='Prefer sources (quality bias)').grid(row=r, column=0, sticky='w'); ttk.Entry(mig, textvariable=vals['prefer_sources'], width=30).grid(row=r, column=1, sticky='w')
    ttk.Label(mig, text='Boost').grid(row=r, column=2, sticky='e'); ttk.Entry(mig, textvariable=vals['prefer_boost'], width=6).grid(row=r, column=3, sticky='w'); r+=1
    ttk.Checkbutton(mig, text='Keep both (quality + coverage)', variable=vals['keep_both']).grid(row=r, column=0, sticky='w')
    ttk.Label(mig, text='Second must have >= preferred ch.').grid(row=r, column=1, sticky='e'); ttk.Entry(mig, textvariable=vals['keep_both_min'], width=6).grid(row=r, column=2, sticky='w'); r+=1
    ttk.Checkbutton(mig, text='Remove original after migration (default ON)', variable=vals['remove_original']).grid(row=r, column=0, sticky='w'); r+=1
    ttk.Label(mig, text='Filter title (optional)').grid(row=r, column=0, sticky='w'); ttk.Entry(mig, textvariable=vals['filter_title'], width=50).grid(row=r, column=1, sticky='we'); r+=1

    # Prune tab
    pr = ttk.Frame(nb)
    nb.add(pr, text='Prune')
    r = 0
    ttk.Checkbutton(pr, text='Prune zero/low-chapter duplicates', variable=vals['prune_zero']).grid(row=r, column=0, sticky='w')
    ttk.Label(pr, text='Keep threshold').grid(row=r, column=1, sticky='e'); ttk.Entry(pr, textvariable=vals['prune_thresh'], width=6).grid(row=r, column=2, sticky='w'); r+=1
    ttk.Checkbutton(pr, text='Prune non-preferred language variants', variable=vals['prune_nonpref']).grid(row=r, column=0, sticky='w')
    ttk.Label(pr, text='Preferred-lang threshold').grid(row=r, column=1, sticky='e'); ttk.Entry(pr, textvariable=vals['prune_lang_thresh'], width=6).grid(row=r, column=2, sticky='w'); r+=1
    ttk.Checkbutton(pr, text='If no preferred, keep only most chapters', variable=vals['prune_keep_most']).grid(row=r, column=0, sticky='w'); r+=1
    ttk.Label(pr, text='Prune filter title (optional)').grid(row=r, column=0, sticky='w'); ttk.Entry(pr, textvariable=vals['prune_filter_title'], width=50).grid(row=r, column=1, sticky='we'); r+=1

    # Follows tab
    fw = ttk.Frame(nb)
    nb.add(fw, text='Follows')
    r = 0
    ttk.Checkbutton(fw, text='Fetch MangaDex follows', variable=vals['from_follows']).grid(row=r, column=0, sticky='w'); r+=1
    ttk.Label(fw, text='MD Username').grid(row=r, column=0, sticky='w'); ttk.Entry(fw, textvariable=vals['md_user'], width=25).grid(row=r, column=1, sticky='w'); r+=1
    ttk.Label(fw, text='MD Password').grid(row=r, column=0, sticky='w'); ttk.Entry(fw, textvariable=vals['md_pass'], show='*', width=25).grid(row=r, column=1, sticky='w'); r+=1
    ttk.Label(fw, text='Save follows JSON').grid(row=r, column=0, sticky='w');
    ttk.Entry(fw, textvariable=vals['follows_json'], width=40).grid(row=r, column=1, sticky='w')
    ttk.Button(fw, text='Browse...', command=lambda: vals['follows_json'].set(filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON','*.json')]))).grid(row=r, column=2, sticky='w'); r+=1
    ttk.Checkbutton(fw, text='Import reading statuses', variable=vals['import_status']).grid(row=r, column=0, sticky='w'); r+=1
    ttk.Label(fw, text='Status->Category map').grid(row=r, column=0, sticky='w'); ttk.Entry(fw, textvariable=vals['status_map'], width=50).grid(row=r, column=1, sticky='we'); r+=1
    ttk.Checkbutton(fw, text='Import read chapters', variable=vals['import_read']).grid(row=r, column=0, sticky='w')
    ttk.Label(fw, text='Delay (s)').grid(row=r, column=1, sticky='e'); ttk.Entry(fw, textvariable=vals['read_delay'], width=6).grid(row=r, column=2, sticky='w'); r+=1
    ttk.Label(fw, text='Category ID (optional)').grid(row=r, column=0, sticky='w'); ttk.Entry(fw, textvariable=vals['category_id'], width=10).grid(row=r, column=1, sticky='w'); r+=1

    # Misc tab
    ms = ttk.Frame(nb)
    nb.add(ms, text='Misc')
    r = 0
    ttk.Label(ms, text='Suwayomi Base URL').grid(row=r, column=0, sticky='w'); ttk.Entry(ms, textvariable=vals['base_url'], width=50).grid(row=r, column=1, sticky='we'); r+=1
    ttk.Checkbutton(ms, text='Dry run', variable=vals['dry_run']).grid(row=r, column=0, sticky='w')
    ttk.Checkbutton(ms, text='Debug output', variable=vals['debug']).grid(row=r, column=1, sticky='w'); r+=1
    ttk.Checkbutton(ms, text='Save log to file', variable=vals['save_log']).grid(row=r, column=0, sticky='w')
    ttk.Entry(ms, textvariable=vals['log_path'], width=40).grid(row=r, column=1, sticky='w')
    ttk.Button(ms, text='Log path...', command=lambda: vals['log_path'].set(filedialog.asksaveasfilename(defaultextension='.log', filetypes=[('Log/Text','*.log;*.txt')]))).grid(row=r, column=2, sticky='w'); r+=1
    ttk.Label(ms, text='Preset').grid(row=r, column=0, sticky='w')
    preset_cb = ttk.Combobox(ms, textvariable=vals['preset'], values=['Prefer English Migration','Cleanup Non-English','Keep Both (Quality+Coverage)'], state='readonly', width=35)
    preset_cb.grid(row=r, column=1, sticky='w')
    def _apply():
        if vals['preset'].get():
            apply_preset(vals, vals['preset'].get())
    ttk.Button(ms, text='Apply Preset', command=_apply).grid(row=r, column=2, sticky='w'); r+=1

    nb.pack(fill='both', expand=True, padx=8, pady=8)

    btn_frame = ttk.Frame(root)
    btn_frame.pack(fill='x', padx=8, pady=8)
    def on_run():
        if not vals['base_url'].get().strip():
            messagebox.showerror('Error', 'Base URL is required')
            return
        args = build_args(vals)
        try:
            launch_command(args, vals['save_log'].get(), vals['log_path'].get().strip() or None)
            messagebox.showinfo('Launched', 'Launched. Check the console window for output.')
        except Exception as e:
            messagebox.showerror('Failed to launch', str(e))
    ttk.Button(btn_frame, text='Run Script', command=on_run).pack(side='left')
    def on_reset():
        for k, var in vals.items():
            if isinstance(var, tk.BooleanVar):
                var.set(False)
            else:
                var.set('')
        vals['base_url'].set('http://127.0.0.1:4567')
        vals['dry_run'].set(True)
        vals['exclude_sources'].set('comick,hitomi')
        vals['pref_langs'].set('en,en-us')
        vals['prefer_sources'].set('asura,flame,genz,utoons')
        vals['prefer_boost'].set('3')
        vals['read_delay'].set('1')
        vals['keep_both_min'].set('1')
        vals['prune_thresh'].set('1')
        vals['prune_lang_thresh'].set('1')
    ttk.Button(btn_frame, text='Reset', command=on_reset).pack(side='left', padx=6)
    ttk.Button(btn_frame, text='Exit', command=root.destroy).pack(side='right')

    root.mainloop()


if __name__ == '__main__':
    main()
