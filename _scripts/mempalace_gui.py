#!/usr/bin/env python3
import subprocess, os, sys, json, threading, shutil, time
from tkinter import Tk, Frame, Label, Button, Text, Scrollbar, END, RIGHT, BOTH, LEFT, TOP, BOTTOM, X, Y, NW, SUNKEN, messagebox, Toplevel
from tkinter import filedialog

# ── paths ──────────────────────────────────────────────
APP_RES = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = next((os.path.join(APP_RES, d) for d in ("scripts", "Scripts") if os.path.isdir(os.path.join(APP_RES, d))), os.path.join(APP_RES, "scripts"))
FALLBACK_DIR = os.path.join(os.path.expanduser("~"), "Documents/mempalace_bot/_scripts")

USER_DIR = os.path.join(os.path.expanduser("~"), "Library/Application Support/MemPalaceBot")
USER_CFG = os.path.join(USER_DIR, "user_scripts.json")
USER_CODE_DIR = os.path.join(USER_DIR, "user_code")

# ── process tracker ────────────────────────────────────
_processes: dict[str, list] = {}  # name -> [process, start_time, type]
_running_lock = threading.Lock()

def running_count():
    with _running_lock:
        return len(_processes)

def register_process(name, proc, ptype="bg"):
    with _running_lock:
        _processes[name] = [proc, time.time(), ptype]

def unregister_process(name):
    with _running_lock:
        _processes.pop(name, None)

def kill_all_processes():
    with _running_lock:
        for name, (proc, _, _) in list(_processes.items()):
            try:
                proc.terminate()
                proc.wait(timeout=3)
                log(f"⛔ Остановлен: {name}")
            except:
                try: proc.kill()
                except: pass
        _processes.clear()
    update_stop_btn()

# ── script registry ────────────────────────────────────
BUILTINS = [
    ("🚀  Запуск", [
        ("Ollama_Start",               False),
        ("start_bot",                  False),
        ("classify_and_mine",          True),
        ("PalaceManager_TelegrammBot", True),
        ("KillPalaceBot",              False),
        ("Switch_AI",                  True),
        ("setup_env",                  True),
        ("RestoreConfig",              True),
    ]),
    ("🧠  Память", [
        ("update_memory",                 False),
        ("update_memory_insights_research", False),
        ("update_memory_wingMode",        False),
        ("check_memory",                  False),
        ("clear_memory",                  False),
        ("Ask_Memory",                    True),
        ("Run_Extraction",                False),
    ]),
    ("🔍  Инструменты", [
        ("find_memory",              False),
        ("go_to_memory",             False),
        ("Archive_Chat",             True),
        ("Daily_Note",               True),
    ]),
    ("⚙️  Обслуживание", [
        ("Manage_Wechsel_Models", True),
        ("Ollama_Cleaner",        True),
        ("import_notes",          True),
    ]),
]

# ── helpers ─────────────────────────────────────────────
def script_path(name):
    for d in (SCRIPTS_DIR, FALLBACK_DIR):
        p = os.path.join(d, name + ".command")
        if os.path.exists(p): return p
    return None

def load_user_scripts():
    try:
        if os.path.exists(USER_CFG):
            with open(USER_CFG) as f:
                data = json.load(f)
                if not isinstance(data, list):
                    return []
                return data
    except Exception as e:
        log(f"⚠️ Файл пользовательских скриптов повреждён: {e}")
    return []

def save_user_scripts(lst):
    os.makedirs(os.path.dirname(USER_CFG), exist_ok=True)
    with open(USER_CFG, "w") as f: json.dump(lst, f, indent=2)

# ── GUI ─────────────────────────────────────────────────
BG = "#0f0f14"
CARD_BG = "#1a1a24"
CARD_HOVER = "#222233"
ACCENT = "#00d4ff"
TEXT = "#d0d0d0"
TEXT_DIM = "#555"

root = Tk()
root.title("🧠 MemPalace Bot")
root.geometry("820x620+300+200")
root.configure(bg=BG)

# ── header ──────────────────────────────────────────────
header = Frame(root, bg=BG)
header.pack(fill=X, padx=16, pady=(12, 2))
Label(header, text="🧠  MemPalace Bot", font=("Helvetica Neue", 20, "bold"),
      bg=BG, fg=ACCENT).pack(anchor="w")
Label(header, text="Кликните на скрипт · 🪟 Терминал  ·  ⚡ Фон",
      font=("Helvetica Neue", 11), bg=BG, fg=TEXT_DIM).pack(anchor="w")

# ── columns ─────────────────────────────────────────────
main = Frame(root, bg=BG)
main.pack(fill=BOTH, expand=True, padx=16, pady=(4, 6))

def make_col(parent, title, scripts):
    col = Frame(parent, bg=BG)
    col.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))
    Label(col, text=title, font=("Helvetica Neue", 9, "bold"),
          bg=BG, fg=TEXT_DIM).pack(anchor="w", pady=(0, 4))
    inner = Frame(col, bg=BG)
    inner.pack(fill=BOTH, expand=True)
    for name, needs_term in scripts:
        card = Frame(inner, bg=CARD_BG, highlightbackground="#2a2a38", highlightthickness=1)
        card.pack(fill=X, pady=2)
        lbl = Label(card, text=name, font=("Helvetica Neue", 12),
                    bg=CARD_BG, fg=TEXT, anchor="w", padx=10, pady=6)
        lbl.pack(fill=X, expand=True)
        tag = Label(card, text="🪟" if needs_term else "⚡",
                    font=("Helvetica Neue", 9), bg=CARD_BG,
                    fg=TEXT_DIM if needs_term else ACCENT)
        tag.pack(side=RIGHT, padx=(0, 8))
        _path = script_path(name)
        run = lambda n=name, nt=needs_term, p=_path: launch(n, nt, p)
        for w in (card, lbl, tag):
            w.bind("<Button-1>", lambda e, r=run: r())
            w.bind("<Enter>", lambda e, c=card, l=lbl, t=tag: (
                c.configure(bg=CARD_HOVER), l.configure(bg=CARD_HOVER), t.configure(bg=CARD_HOVER)))
            w.bind("<Leave>", lambda e, c=card, l=lbl, t=tag: (
                c.configure(bg=CARD_BG), l.configure(bg=CARD_BG), t.configure(bg=CARD_BG)))

def refresh_user_section():
    for w in cols_frame.winfo_children():
        if getattr(w, "_user_col", False):
            w.destroy()
    user = load_user_scripts()
    if user:
        col = Frame(cols_frame, bg=BG)
        col.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))
        col._user_col = True
        Label(col, text="📂  Пользовательские", font=("Helvetica Neue", 9, "bold"),
              bg=BG, fg=TEXT_DIM).pack(anchor="w", pady=(0, 4))
        inner = Frame(col, bg=BG)
        inner.pack(fill=BOTH, expand=True)
        for entry in user:
            path = entry.get("path", "") if isinstance(entry, dict) else ""
            name = entry.get("name", os.path.basename(path).replace(".command","")) if isinstance(entry, dict) else os.path.basename(path).replace(".command","")
            needs_term = entry.get("terminal", True) if isinstance(entry, dict) else True
            tag_text = "🪟" if needs_term else "⚡"
            tag_color = TEXT_DIM if needs_term else ACCENT
            card = Frame(inner, bg=CARD_BG, highlightbackground="#2a2a38", highlightthickness=1)
            card.pack(fill=X, pady=2)
            lbl = Label(card, text=f"📎 {name}", font=("Helvetica Neue", 12),
                        bg=CARD_BG, fg=TEXT, anchor="w", padx=10, pady=6)
            lbl.pack(fill=X, expand=True)
            tag = Label(card, text=tag_text, font=("Helvetica Neue", 9),
                        bg=CARD_BG, fg=tag_color)
            tag.pack(side=RIGHT, padx=(0, 8))
            run = lambda p=path, nt=needs_term: launch(os.path.basename(p), nt, p)
            for w in (card, lbl, tag):
                w.bind("<Button-1>", lambda e, r=run: r())
                w.bind("<Enter>", lambda e, c=card, l=lbl, t=tag: (
                    c.configure(bg=CARD_HOVER), l.configure(bg=CARD_HOVER),
                    t.configure(bg=CARD_HOVER)))
                w.bind("<Leave>", lambda e, c=card, l=lbl, t=tag: (
                    c.configure(bg=CARD_BG), l.configure(bg=CARD_BG),
                    t.configure(bg=CARD_BG)))
            btn_del = Button(card, text="✕", font=("Helvetica Neue", 9),
                             bg=CARD_BG, fg="#633", relief="flat", bd=0,
                             activebackground="#833", activeforeground="#fff",
                             command=lambda p=path: remove_user_script(p))
            btn_del.pack(side=RIGHT)

cols_frame = Frame(main, bg=BG)
cols_frame.pack(fill=BOTH, expand=True)

for title, scripts in BUILTINS:
    make_col(cols_frame, title, scripts)

refresh_user_section()

# ── bottom bar ─────────────────────────────────────────
bar = Frame(root, bg=BG)
bar.pack(fill=X, padx=16, pady=(0, 4))

stop_btn = None

def update_stop_btn():
    global stop_btn
    cnt = running_count()
    if stop_btn:
        if cnt > 0:
            stop_btn.pack(side=LEFT, padx=(6, 0))
        else:
            stop_btn.pack_forget()

def add_user_script():
    p = filedialog.askopenfilename(
        title="Выберите .command скрипт",
        filetypes=[("Shell scripts", "*.command *.sh"), ("Все файлы", "*")]
    )
    if not p: return
    needs_term = messagebox.askyesno("Режим", "Этот скрипт требует Терминал?\n\nДа = 🪟 откроется в Терминале\nНет = ⚡ выполнится здесь")
    lst = load_user_scripts()
    paths = [e["path"] if isinstance(e, dict) else e for e in lst]
    if p in paths:
        messagebox.showinfo("Уже есть", "Этот скрипт уже добавлен.")
        return
    lst.append({"name": os.path.basename(p).replace(".command",""), "path": p, "terminal": needs_term})
    save_user_scripts(lst)
    refresh_user_section()
    log(f"📎 Добавлен: {os.path.basename(p)} ({'🪟' if needs_term else '⚡'})")

def remove_user_script(path):
    lst = load_user_scripts()
    lst2 = [e for e in lst if (e["path"] if isinstance(e, dict) else e) != path]
    if len(lst2) < len(lst):
        save_user_scripts(lst2)
        refresh_user_section()
        log(f"🗑 Удалён: {os.path.basename(path)}")

def paste_script_code():
    dialog = Toplevel(root)
    dialog.title("📝 Вставить код скрипта")
    dialog.geometry("560x460+400+230")
    dialog.configure(bg=BG)
    dialog.transient(root)
    dialog.grab_set()

    Label(dialog, text="Название:", font=("Helvetica Neue", 11),
          bg=BG, fg=TEXT, anchor="w").pack(fill=X, padx=14, pady=(14, 2))
    name_entry = Text(dialog, font=("Helvetica Neue", 12), bg="#1a1a24", fg=TEXT,
                      relief="flat", bd=0, highlightbackground="#2a2a38",
                      highlightthickness=1, height=1, padx=8, pady=4)
    name_entry.pack(fill=X, padx=14, pady=(0, 6))

    Label(dialog, text="Код (bash):", font=("Helvetica Neue", 11),
          bg=BG, fg=TEXT, anchor="w").pack(fill=X, padx=14, pady=(0, 2))
    code = Text(dialog, font=("Menlo", 11), bg="#08080c", fg="#aaa",
                relief="flat", bd=0, highlightbackground="#2a2a38",
                highlightthickness=1, padx=10, pady=8, wrap="none")
    code.pack(fill=BOTH, expand=True, padx=14, pady=(0, 6))

    term_var = Toplevel(dialog).tk.booleanvar()
    import tkinter as _tk
    term_var = _tk.BooleanVar(value=True)
    cb = _tk.Checkbutton(dialog, text="🪟 Открывать в Терминале (сними галочку для ⚡ фонового режима)",
                         variable=term_var, bg=BG, fg=TEXT_DIM, selectcolor="#1a1a24",
                         activebackground=BG, activeforeground=TEXT,
                         font=("Helvetica Neue", 10), anchor="w", bd=0)
    cb.pack(fill=X, padx=14, pady=(0, 6))

    btn_frame = Frame(dialog, bg=BG)
    btn_frame.pack(fill=X, padx=14, pady=(0, 12))

    def do_save():
        name = name_entry.get("1.0", END).strip()
        content = code.get("1.0", END).strip()
        if not name:
            messagebox.showwarning("Ошибка", "Введите название скрипта", parent=dialog)
            return
        if not content:
            messagebox.showwarning("Ошибка", "Вставьте код скрипта", parent=dialog)
            return
        safe = "".join(c for c in name if c.isalnum() or c in " _-").strip().replace(" ","_") or "user_script"
        os.makedirs(USER_CODE_DIR, exist_ok=True)
        fpath = os.path.join(USER_CODE_DIR, safe + ".command")
        shebang = "#!/bin/bash\n" + content if not content.startswith("#!") else content
        with open(fpath, "w") as f: f.write(shebang)
        os.chmod(fpath, 0o755)
        lst = load_user_scripts()
        lst.append({"name": name, "path": fpath, "terminal": term_var.get()})
        save_user_scripts(lst)
        refresh_user_section()
        log(f"📝 Скрипт «{name}» сохранён ({'🪟' if term_var.get() else '⚡'})")
        dialog.destroy()

    def do_paste():
        try:
            code.insert(END, root.clipboard_get())
        except: pass

    Button(btn_frame, text="📋 Вставить", font=("Helvetica Neue", 11),
           bg="#1a1a24", fg=TEXT, relief="flat", bd=0, padx=12, pady=4,
           command=do_paste).pack(side=LEFT, padx=(0, 8))
    Button(btn_frame, text="✅ Сохранить", font=("Helvetica Neue", 11),
           bg=ACCENT, fg="#000", relief="flat", bd=0, padx=12, pady=4,
           command=do_save).pack(side=RIGHT)

Button(bar, text="📎 .command", font=("Helvetica Neue", 11),
       bg="#1a1a24", fg=ACCENT, relief="flat", bd=0, padx=12, pady=4,
       activebackground="#222233", activeforeground="#fff",
       cursor="hand2", command=add_user_script).pack(side=LEFT, padx=(0, 6))
Button(bar, text="📝 Вставить код", font=("Helvetica Neue", 11),
       bg="#1a1a24", fg=ACCENT, relief="flat", bd=0, padx=12, pady=4,
       activebackground="#222233", activeforeground="#fff",
       cursor="hand2", command=paste_script_code).pack(side=LEFT)

stop_btn = Button(bar, text="⏹  Стоп", font=("Helvetica Neue", 11),
                  bg="#442222", fg="#f66", relief="flat", bd=0, padx=14, pady=4,
                  activebackground="#663333", activeforeground="#f99",
                  cursor="hand2", command=kill_all_processes)
update_stop_btn()

# ── console ─────────────────────────────────────────────
console = Frame(root, bg="#08080c")
console.pack(fill=BOTH, padx=16, pady=(0, 12))

txt = Text(console, bg="#08080c", fg="#aaa", font=("Menlo", 11),
           relief="flat", bd=0, padx=10, pady=8, height=7, wrap="word",
           highlightbackground="#1a1a24", highlightthickness=0, state="disabled")
txt.pack(side=LEFT, fill=BOTH, expand=True)

scroll = Scrollbar(console, command=txt.yview, bg="#1a1a24", troughcolor="#0f0f14")
scroll.pack(side=RIGHT, fill=Y)
txt.config(yscrollcommand=scroll.set)

def log(text):
    txt.config(state="normal")
    txt.insert(END, text + "\n")
    txt.see(END)
    txt.config(state="disabled")

# ── launch logic ───────────────────────────────────────
def launch(name, needs_term, path):
    if not path or not os.path.exists(path):
        log(f"❌ {name}: файл не найден")
        return

    # prevent double-launch for bg tasks
    if not needs_term and name in [n for n, _ in list(_processes.items())]:
        log(f"⚠️ «{name}» уже выполняется")
        return

    try:
        if needs_term:
            proc = subprocess.Popen(["open", path])
            log(f"🪟 {name} → Терминал")
        else:
            log(f"⚡ {name} запущен...")
            proc = subprocess.Popen(["bash", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            register_process(name, proc, "bg")
            update_stop_btn()
            threading.Thread(target=_bg_worker, args=(name, proc), daemon=True).start()
    except Exception as e:
        log(f"❌ {name}: ошибка запуска — {e}")

def _bg_worker(name, proc):
    try:
        stdout, stderr = proc.communicate(timeout=300)
        if stdout: log(stdout.rstrip())
        if stderr: log("⚠️ " + stderr.rstrip())
        status = "✅" if proc.returncode == 0 else "❌"
        log(f"{status} {name} (код: {proc.returncode})\n")
    except subprocess.TimeoutExpired:
        proc.terminate()
        log(f"⏱ {name} превысил 5 мин, остановлен\n")
    except Exception as e:
        log(f"❌ {name}: {e}")
    finally:
        unregister_process(name)
        root.after(0, update_stop_btn)

# ── spinner animation ──────────────────────────────────
_spinner_active = False

def spinner_loop():
    global _spinner_active
    chars = "⠋⠙⠸⠴⠦⠇"
    i = 0
    _spinner_active = True
    while _spinner_active:
        cnt = running_count()
        if cnt == 0:
            _spinner_active = False
            break
        new_title = f"🧠 MemPalace Bot  [{chars[i % len(chars)]} {cnt} задач]"
        try: root.title(new_title)
        except: pass
        i += 1
        time.sleep(0.15)
    root.after(0, lambda: root.title("🧠 MemPalace Bot"))

def start_spinner():
    if not _spinner_active:
        threading.Thread(target=spinner_loop, daemon=True).start()

# patch register to start spinner
_orig_register = register_process
def register_process(name, proc, ptype="bg"):
    _orig_register(name, proc, ptype)
    start_spinner()
register_process = register_process

# ── window close handler ───────────────────────────────
def on_closing():
    kill_all_processes()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

log("🧠 MemPalace Bot — авто-режим")
log("🪟 интерактивные скрипты → Терминал")
log("⚡ фоновые → здесь, с таймаутом 5 мин")
log("⏹ Стоп — завершить все фоновые процессы")

root.mainloop()
