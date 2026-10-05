#!/usr/bin/env python3
"""Night Screen: температура, яркость и контраст — GUI для гамма-таблицы видеокарты.

Таблицу выставляет модуль gamma (XRandR, как это делает `xsct`). Подсветку
монитора не трогаем, меняется только картинка, которую выводит видеокарта.
"""

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import gamma
import i18n
import ipc
from i18n import t

# --- пределы ---------------------------------------------------------------
TEMP_MIN, TEMP_MAX, TEMP_STEP = 1000, 10000, 50
TEMP_DEFAULT = 6500                 # «нейтральный» белый
BRIGHT_MIN, BRIGHT_MAX = 10, 100    # проценты; ниже 10 % экран почти не видно
BRIGHT_DEFAULT = 100
CONTRAST_MIN, CONTRAST_MAX = 30, 300  # проценты; выше 100 крайние тона обрезаются
CONTRAST_DEFAULT = 100
PIVOT_MIN, PIVOT_MAX = 0, 150       # ползунок «Центр контраста»: вправо — больше светлеет;
                                    # правее 100 центр уходит ниже чёрного
PIVOT_DEFAULT = 50
HERE = os.path.dirname(os.path.abspath(__file__))
POLL_MS = 100                       # как часто смотрим команды от значка в трее
WATCH_MS = 500                      # как часто проверяем, не переписал ли кто-то гамму
STATE_FILE = os.path.expanduser("~/.config/night-screen/state.json")
PRESETS_FILE = os.path.expanduser("~/.config/night-screen/presets.json")
SETTINGS_FILE = os.path.expanduser("~/.config/night-screen/settings.json")
FLAGS_DIR = os.path.join(HERE, "flags")

# (ключ в presets.json, id для перевода, температура K, яркость %) — по умолчанию пресеты
# не трогают контраст; через «Сохранить» в пресет записываются все четыре значения.
# Ключ остаётся русским, как был, чтобы старые presets.json читались; подпись — по id.
PRESETS = [
    ("День", "day", 6500, 100),
    ("Вечер", "evening", 5000, 80),
    ("Ночь", "night", 4500, 60),
    ("Глубокая ночь", "deep", 3500, 40),
]

# --- палитра: тёмная и неяркая, чтобы само окно не слепило ночью ------------
BG = "#17171b"
PANEL = "#1f1f25"
FG = "#b9b9c2"
FG_DIM = "#7c7c88"
ACCENT = "#d9822b"
FIELD = "#101014"
BORDER = "#34343d"
FG_OFF = "#4a4a54"      # текст неактивного интерфейса (режим сохранения)
HILITE = "#4a3017"      # подсветка пресетов в режиме сохранения
HILITE_HOVER = "#664220"
FG_HI = "#f2c896"


def kelvin_to_rgb(kelvin):
    """Приближённый цвет чёрного тела (формула Tanner Helland) для подсветки дорожки."""
    t = max(1000, min(40000, kelvin)) / 100.0
    if t <= 66:
        r = 255
        g = 99.4708025861 * math.log(t) - 161.1195681661
    else:
        r = 329.698727446 * (t - 60) ** -0.1332047592
        g = 288.1221695283 * (t - 60) ** -0.0755148492
    if t >= 66:
        b = 255
    elif t <= 19:
        b = 0
    else:
        b = 138.5177312231 * math.log(t - 10) - 305.0447927307
    clamp = lambda v: int(max(0, min(255, v)))
    return clamp(r), clamp(g), clamp(b)


def rgb_hex(rgb, factor=1.0):
    return "#%02x%02x%02x" % tuple(int(c * factor) for c in rgb)


def fade(color, k=0.3):
    """Цвет (или пара цветов), приглушённый к фону панели — для неактивного интерфейса."""
    if isinstance(color, tuple):
        return tuple(fade(c, k) for c in color)
    c = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    p = [int(PANEL[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(b + (a - b) * k) for a, b in zip(c, p))


def in_range(temp, bright, contrast, pivot):
    return (TEMP_MIN <= temp <= TEMP_MAX and BRIGHT_MIN <= bright <= BRIGHT_MAX
            and CONTRAST_MIN <= contrast <= CONTRAST_MAX and PIVOT_MIN <= pivot <= PIVOT_MAX)


# --- сохранённое состояние -------------------------------------------------
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return (int(d["temp"]), int(d["bright"]), int(d["contrast"]),
                int(d.get("pivot", PIVOT_DEFAULT)))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def pivot_level(slider_value):
    """Уровень серого 0..1 для gamma: ползунок инвертирован, чтобы вправо картинка
    светлела (центр опускается), а влево — темнела, как и цвет дорожки. На 100 центр
    у чёрного (0), правее он отрицательный: тёмное тянется вверх и сильнее светлеет."""
    return (100 - slider_value) / 100


def save_state(temp, bright, contrast, pivot):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"temp": temp, "bright": bright, "contrast": contrast,
                       "pivot": pivot}, f)
    except OSError:
        pass


def load_presets():
    """Пресеты по умолчанию, поверх — сохранённые через «Сохранить» (по названию).
    У несохранённых contrast и pivot = None: такой пресет меняет только температуру
    и яркость."""
    presets = [{"name": n, "id": i, "temp": temp, "bright": b, "contrast": None,
                "pivot": None} for n, i, temp, b in PRESETS]
    try:
        with open(PRESETS_FILE, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return presets
    for p in presets:
        try:
            s = saved[p["name"]]
            values = [int(s[k]) for k in ("temp", "bright", "contrast", "pivot")]
        except (KeyError, TypeError, ValueError):
            continue
        if in_range(*values):
            p.update(zip(("temp", "bright", "contrast", "pivot"), values))
    return presets


def save_presets(presets):
    try:
        os.makedirs(os.path.dirname(PRESETS_FILE), exist_ok=True)
        data = {p["name"]: {k: p[k] for k in ("temp", "bright", "contrast", "pivot")}
                for p in presets if p["contrast"] is not None}
        with open(PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def load_language():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)["lang"]
    except (OSError, ValueError, KeyError, TypeError):
        return i18n.DEFAULT


def save_language(code):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({"lang": code}, f)
    except OSError:
        pass


def read_current():
    """Температура и яркость по текущей таблице экрана, спросив `xsct`, если он есть
    (вывод вида: «Screen 0: temperature ~ 6500 1.000000»)."""
    if not shutil.which("xsct"):
        return TEMP_DEFAULT, BRIGHT_MAX
    try:
        out = subprocess.run(["xsct"], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"temperature ~ (\d+)\s+([\d.]+)", out)
        if m:
            temp = int(m.group(1))
            bright = round(float(m.group(2)) * 100)
            return (max(TEMP_MIN, min(TEMP_MAX, temp)),
                    max(BRIGHT_MIN, min(BRIGHT_MAX, bright)))
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return TEMP_DEFAULT, BRIGHT_MAX


# --- свой ползунок с цветной дорожкой --------------------------------------
class Slider(tk.Canvas):
    TRACK_H = 10
    THUMB_R = 11
    PAD = 14

    def __init__(self, master, lo, hi, step, value, command, track_color):
        super().__init__(master, height=2 * self.THUMB_R + 8, bg=PANEL,
                         highlightthickness=0, takefocus=True, cursor="hand2")
        self.lo, self.hi, self.step = lo, hi, step
        self.value = value
        self.enabled = True
        self.command = command
        self.track_color = track_color  # функция: доля 0..1 -> цвет
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<Left>", lambda e: self._nudge(-1))
        self.bind("<Right>", lambda e: self._nudge(1))
        self.bind("<Down>", lambda e: self._nudge(-1))
        self.bind("<Up>", lambda e: self._nudge(1))
        self.bind("<Prior>", lambda e: self._nudge(10))
        self.bind("<Next>", lambda e: self._nudge(-10))
        self.bind("<MouseWheel>", lambda e: self._nudge(1 if e.delta > 0 else -1))
        self.bind("<Button-4>", lambda e: self._nudge(1))   # колесо в X11
        self.bind("<Button-5>", lambda e: self._nudge(-1))
        self.bind("<FocusIn>", lambda e: self.redraw())
        self.bind("<FocusOut>", lambda e: self.redraw())

    def _x_of(self, value):
        w = self.winfo_width()
        frac = (value - self.lo) / (self.hi - self.lo)
        return self.PAD + frac * max(1, w - 2 * self.PAD)

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2 * self.PAD + 2:
            return
        cy = h / 2
        x0, x1 = self.PAD, w - self.PAD
        y0, y1 = cy - self.TRACK_H / 2, cy + self.TRACK_H / 2
        n = int(x1 - x0)
        for i in range(n + 1):
            color = self.track_color(i / n)
            if not self.enabled:
                color = fade(color)
            if isinstance(color, tuple):          # (верхняя половина, нижняя половина)
                self.create_line(x0 + i, y0, x0 + i, cy, fill=color[0])
                self.create_line(x0 + i, cy, x0 + i, y1, fill=color[1])
            else:
                self.create_line(x0 + i, y0, x0 + i, y1, fill=color)
        self.create_rectangle(x0, y0, x1, y1, outline=BORDER)
        x = self._x_of(self.value)
        if not self.enabled:
            ring = FG_OFF
        else:
            ring = ACCENT if self.focus_get() is self else FG
        self.create_oval(x - self.THUMB_R, cy - self.THUMB_R, x + self.THUMB_R,
                         cy + self.THUMB_R, fill=BG, outline=ring, width=2)

    def set(self, value):
        """Выставить значение программно (команду не вызывает)."""
        self.value = max(self.lo, min(self.hi, value))
        self.redraw()

    def set_enabled(self, on):
        """Неактивный ползунок блёклый и не реагирует на мышь и клавиши."""
        self.enabled = on
        self.configure(takefocus=on, cursor="hand2" if on else "")
        self.redraw()

    def _emit(self, value):
        if not self.enabled:
            return
        value = round(value / self.step) * self.step
        value = max(self.lo, min(self.hi, value))
        if value != self.value:
            self.value = value
            self.redraw()
            self.command(value)

    def _from_x(self, x):
        w = self.winfo_width()
        frac = (x - self.PAD) / max(1, w - 2 * self.PAD)
        return self.lo + max(0.0, min(1.0, frac)) * (self.hi - self.lo)

    def _press(self, e):
        if not self.enabled:
            return
        self.focus_set()
        self._emit(self._from_x(e.x))

    def _drag(self, e):
        self._emit(self._from_x(e.x))

    def _nudge(self, direction):
        self._emit(self.value + direction * self.step)
        return "break"


# --- само окно --------------------------------------------------------------
class App:
    def __init__(self, root, server):
        self.root = root
        self.server = server         # команды от значка в трее и от повторного запуска
        self.screen = gamma.Screen()
        self.error = None
        self._save_job = None
        self._blink_job = None
        self._flash_job = None
        self.saving = False          # режим «Сохранить»: ждём клика по пресету
        self.tray = None             # процесс значка в трее
        self._closed = False
        self.presets = load_presets()
        self.temp, self.bright, self.contrast, self.pivot = self._initial_values()
        self._flags = {}             # код языка -> картинка флага (ссылку надо держать)

        root.configure(bg=BG)
        root.minsize(440, 0)
        root.resizable(True, False)
        icon_path = os.path.join(HERE, "icon.png")
        try:
            root.iconphoto(True, tk.PhotoImage(file=icon_path))
        except tk.TclError:
            pass

        self._style()
        self.outer = None
        self._build()
        root.bind("<Escape>", lambda e: self.cancel_save_mode())
        root.protocol("WM_DELETE_WINDOW", self._close)
        self._start_tray()
        root.after(POLL_MS, self._poll_ipc)
        root.after(WATCH_MS, self._watch_gamma)

    def _build(self):
        """Всё содержимое окна на текущем языке. Смена языка просто строит его заново:
        значения лежат в self.temp / bright / contrast / pivot и не теряются."""
        root = self.root
        if self.outer:
            self.outer.destroy()
        self._dimmable = []          # что блекнет и отключается в режиме «Сохранить»
        self._entry_cmds = {}        # поле ввода -> его команда применения
        root.title(t("title"))
        outer = self.outer = tk.Frame(root, bg=BG, padx=16, pady=14)
        outer.pack(fill="both", expand=True)

        self._language_bar(outer)

        self.temp_var = tk.StringVar(value=str(self.temp))
        self.bright_var = tk.StringVar(value=str(self.bright))
        self.contrast_var = tk.StringVar(value=str(self.contrast))
        self.pivot_var = tk.StringVar(value=str(self.pivot))

        self.temp_slider = self._section(
            outer, t("temp"), "K", self.temp_var,
            TEMP_MIN, TEMP_MAX, TEMP_STEP, self.temp,
            self._temp_from_slider, self._temp_from_entry,
            lambda f: rgb_hex(kelvin_to_rgb(TEMP_MIN + f * (TEMP_MAX - TEMP_MIN))),
            t("temp.ends"),
            reset=lambda: self.apply_temp(TEMP_DEFAULT))
        self.bright_slider = self._section(
            outer, t("bright"), "%", self.bright_var,
            BRIGHT_MIN, BRIGHT_MAX, 1, self.bright,
            self._bright_from_slider, self._bright_from_entry,
            lambda f: rgb_hex(kelvin_to_rgb(self.temp), 0.08 + 0.92 * f),
            t("bright.ends"),
            reset=lambda: self.apply_bright(BRIGHT_DEFAULT))
        self.contrast_slider = self._section(
            outer, t("contrast"), "%", self.contrast_var,
            CONTRAST_MIN, CONTRAST_MAX, 1, self.contrast,
            self._contrast_from_slider, self._contrast_from_entry,
            self._contrast_track, t("contrast.ends"),
            reset=lambda: self.apply_contrast(CONTRAST_DEFAULT))
        self.pivot_slider = self._section(
            outer, t("pivot"), "%", self.pivot_var,
            PIVOT_MIN, PIVOT_MAX, 1, self.pivot,
            self._pivot_from_slider, self._pivot_from_entry,
            lambda f: rgb_hex((255, 255, 255), min(1.0, f * PIVOT_MAX / 100)),
            t("pivot.ends"),
            reset=lambda: self.apply_pivot(PIVOT_DEFAULT),
            hint=t("pivot.hint"))

        presets = tk.Frame(outer, bg=BG)
        presets.pack(fill="x", pady=(14, 0))
        self.preset_buttons = []
        for i, p in enumerate(self.presets):
            presets.columnconfigure(i, weight=1, uniform="p")
            btn = self._button(presets, self._preset_text(p),
                               lambda i=i: self._preset_click(i))
            btn.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))
            self.preset_buttons.append(btn)

        bottom = tk.Frame(outer, bg=BG)
        bottom.pack(fill="x", pady=(12, 0))
        self.status = tk.Label(bottom, bg=BG, fg=FG_DIM, anchor="w", font=("TkDefaultFont", 9))
        self.status.pack(fill="x")
        buttons = tk.Frame(bottom, bg=BG)
        buttons.pack(fill="x", pady=(8, 0))
        reset_btn = self._button(buttons, t("reset_all"), self.reset_all, pad=(14, 4))
        reset_btn.pack(side="right")
        self._dimmable.append(reset_btn)
        self.save_btn = self._button(buttons, t("save"), self.toggle_save_mode, pad=(14, 4))
        self.save_btn.pack(side="right", padx=(0, 8))
        self._refresh_status()

    def _flag(self, code):
        if code not in self._flags:
            try:
                self._flags[code] = tk.PhotoImage(file=os.path.join(FLAGS_DIR, code + ".png"))
            except tk.TclError:
                self._flags[code] = None      # без картинки останется просто название
        return self._flags[code]

    def _language_bar(self, parent):
        """Ряд кнопок «флаг + название языка» в правом верхнем углу; выбранный подсвечен."""
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", pady=(0, 10))
        for code, name in reversed(i18n.LANGUAGES):
            btn = self._button(bar, name, lambda c=code: self.set_language(c), pad=(8, 3))
            flag = self._flag(code)
            if flag:
                btn.configure(image=flag, compound="left")
            btn.pack(side="right", padx=(6, 0))
            if code == i18n.language():
                self._light(btn, True)

    def set_language(self, code):
        if code == i18n.language():
            return
        self.cancel_save_mode()
        i18n.set_language(code)
        save_language(code)
        self._build()
        self._restart_tray()      # подписи в меню значка тоже меняются

    def _initial_values(self):
        """Сохранённые значения, если экран сейчас именно такой; иначе — то, что видит xsct."""
        saved = load_state()
        if saved:
            t, b, c, p = saved
            if in_range(t, b, c, p) and self.screen.matches(t, b / 100, c / 100,
                                                            pivot_level(p)):
                return t, b, c, p
        t, b = read_current()
        return t, b, CONTRAST_DEFAULT, PIVOT_DEFAULT

    @staticmethod
    def _contrast_track(f):
        """Дорожка-клин: слева обе половины серые (контраста нет), справа — белое над чёрным."""
        top, bottom = int(255 * (0.5 + 0.45 * f)), int(255 * (0.5 - 0.45 * f))
        return "#%02x%02x%02x" % (top, top, top), "#%02x%02x%02x" % (bottom, bottom, bottom)

    # --- оформление ---
    def _style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("Warm.TSpinbox", fieldbackground=FIELD, background=PANEL,
                     foreground=FG, bordercolor=BORDER, lightcolor=BORDER,
                     darkcolor=BORDER, arrowcolor=FG, insertcolor=FG,
                     selectbackground=ACCENT, selectforeground=BG, padding=4)
        st.map("Warm.TSpinbox", bordercolor=[("focus", ACCENT)],
               lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)],
               foreground=[("disabled", FG_OFF)], arrowcolor=[("disabled", FG_OFF)],
               fieldbackground=[("disabled", PANEL)])

    def _button(self, parent, text, command, pad=(8, 6)):
        btn = tk.Button(parent, text=text, command=command, bg=PANEL, fg=FG,
                        activebackground=BORDER, activeforeground=FG,
                        disabledforeground=FG_OFF,
                        relief="flat", bd=0, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=ACCENT,
                        padx=pad[0], pady=pad[1], cursor="hand2",
                        font=("TkDefaultFont", 9))
        btn.idle_bg, btn.hover_bg = PANEL, BORDER

        def enter(e):
            if btn.cget("state") != "disabled":
                btn.configure(bg=btn.hover_bg)
        btn.bind("<Enter>", enter)
        btn.bind("<Leave>", lambda e: btn.configure(bg=btn.idle_bg))
        return btn

    @staticmethod
    def _light(btn, on):
        """Подсветить кнопку (пресеты и «Отмена» в режиме сохранения) или вернуть как было."""
        btn.idle_bg, btn.hover_bg = (HILITE, HILITE_HOVER) if on else (PANEL, BORDER)
        btn.configure(bg=btn.idle_bg, fg=FG_HI if on else FG,
                      activebackground=btn.hover_bg,
                      highlightbackground=ACCENT if on else BORDER)

    @staticmethod
    def _preset_label(p):
        return t("preset." + p["id"])

    def _preset_text(self, p):
        text = "%s\n%d K · %d %%" % (self._preset_label(p), p["temp"], p["bright"])
        if p["contrast"] is not None:
            text += "\n" + t("preset.extra", p["contrast"], p["pivot"])
        return text

    def _section(self, parent, title, unit, var, lo, hi, step, value,
                 slider_cmd, entry_cmd, track_color, ends, reset=None, hint=None):
        box = tk.Frame(parent, bg=PANEL, padx=14, pady=10)
        box.pack(fill="x", pady=(0, 10))
        widgets = []

        head = tk.Frame(box, bg=PANEL)
        head.pack(fill="x")
        widgets.append(tk.Label(head, text=title, bg=PANEL, fg=FG,
                                font=("TkDefaultFont", 11, "bold")))
        widgets[-1].pack(side="left")
        widgets.append(tk.Label(head, text=unit, bg=PANEL, fg=FG_DIM))
        widgets[-1].pack(side="right", padx=(4, 0))
        spin = ttk.Spinbox(head, from_=lo, to=hi, increment=step if unit == "K" else 1,
                           textvariable=var, width=7, justify="right",
                           style="Warm.TSpinbox", command=entry_cmd)
        spin.pack(side="right")
        widgets.append(spin)
        self._entry_cmds[spin] = entry_cmd
        if reset:
            widgets.append(self._button(head, t("reset"), reset, pad=(8, 1)))
            widgets[-1].pack(side="right", padx=(0, 10))
        for ev in ("<Return>", "<KP_Enter>", "<FocusOut>"):
            spin.bind(ev, lambda e, cmd=entry_cmd: cmd())

        slider = Slider(box, lo, hi, step, value, slider_cmd, track_color)
        slider.pack(fill="x", pady=(6, 0))
        widgets.append(slider)

        legend = tk.Frame(box, bg=PANEL)
        legend.pack(fill="x")
        widgets.append(tk.Label(legend, text="◀ %s  %d" % (ends[0], lo), bg=PANEL,
                                fg=FG_DIM, font=("TkDefaultFont", 8)))
        widgets[-1].pack(side="left")
        widgets.append(tk.Label(legend, text="%d  %s ▶" % (hi, ends[1]), bg=PANEL,
                                fg=FG_DIM, font=("TkDefaultFont", 8)))
        widgets[-1].pack(side="right")
        if hint:
            widgets.append(tk.Label(box, text=hint, bg=PANEL, fg=FG_DIM, justify="left",
                                    anchor="w", font=("TkDefaultFont", 8)))
            widgets[-1].pack(fill="x", pady=(6, 0))
        self._dimmable.extend(widgets)
        return slider

    # --- изменение значений ---
    def _commit(self):
        self._apply()
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, self._save)

    def _apply(self):
        try:
            self.screen.set(self.temp, self.bright / 100, self.contrast / 100,
                            pivot_level(self.pivot))
            self.error = None
        except gamma.GammaError as exc:
            self.error = t("err." + str(exc))
        self._refresh_status()

    def _watch_gamma(self):
        """Если гамму переписал кто-то другой (например, ночной режим Cinnamon при
        своих пересчётах), записываем свою заново."""
        try:
            if self.screen.changed():
                self._apply()
        except gamma.GammaError:
            pass
        if not self._closed:
            self.root.after(WATCH_MS, self._watch_gamma)

    def _save(self):
        self._save_job = None
        save_state(self.temp, self.bright, self.contrast, self.pivot)

    # --- трей и команды извне ---
    def _start_tray(self):
        """Значок получает уже переведённые подписи меню (сам он языков не знает)."""
        labels = {"open": t("tray.open"), "quit": t("tray.quit"),
                  "presets": [self._preset_label(p) for p in self.presets]}
        try:
            self.tray = subprocess.Popen(
                ["/usr/bin/python3", os.path.join(HERE, "tray.py"), json.dumps(labels)])
        except OSError:
            self.tray = None

    def _restart_tray(self):
        """Новый язык — новое меню: проще перезапустить значок, чем менять его на лету."""
        if self._tray_alive():
            self.tray.terminate()
            try:
                self.tray.wait(2)
            except subprocess.TimeoutExpired:
                self.tray.kill()
            self._start_tray()

    def _tray_alive(self):
        return self.tray is not None and self.tray.poll() is None

    def _poll_ipc(self):
        for command in self.server.poll():
            self._command(command)
        if not self._closed:
            self.root.after(POLL_MS, self._poll_ipc)

    def _command(self, command):
        name, _, arg = command.partition(" ")
        if name == "show":
            self.show()
        elif name == "preset" and arg.isdigit() and int(arg) < len(self.presets):
            self.cancel_save_mode()
            self.apply_preset(int(arg))
        elif name == "quit":
            self.quit()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _close(self):
        """Крестик: окно прячется в трей, а без трея закрывает приложение."""
        if self._tray_alive():
            self.cancel_save_mode()
            self._save()
            self.root.withdraw()
        else:
            self.quit()

    def quit(self):
        self._closed = True
        for job in (self._save_job, self._blink_job, self._flash_job):
            if job:
                self.root.after_cancel(job)
        self._save()
        if self._tray_alive():
            self.tray.terminate()
        self.server.close()
        self.screen.close()
        self.root.destroy()

    def _temp_from_slider(self, value):
        self.temp = int(value)
        self.temp_var.set(str(self.temp))
        self.bright_slider.redraw()      # цвет дорожки яркости зависит от температуры
        self._commit()

    def _bright_from_slider(self, value):
        self.bright = int(value)
        self.bright_var.set(str(self.bright))
        self._commit()

    def _contrast_from_slider(self, value):
        self.contrast = int(value)
        self.contrast_var.set(str(self.contrast))
        self._commit()

    def _pivot_from_slider(self, value):
        self.pivot = int(value)
        self.pivot_var.set(str(self.pivot))
        self._commit()

    @staticmethod
    def _parse(text, lo, hi, fallback):
        try:
            return max(lo, min(hi, round(float(text.strip().replace(",", ".")))))
        except ValueError:
            return fallback

    def _temp_from_entry(self):
        self.apply_temp(self._parse(self.temp_var.get(), TEMP_MIN, TEMP_MAX, self.temp))

    def apply_temp(self, temp):
        self.temp = temp
        self.temp_var.set(str(temp))
        self.temp_slider.set(temp)
        self.bright_slider.redraw()
        self._commit()

    def _bright_from_entry(self):
        self.apply_bright(self._parse(self.bright_var.get(), BRIGHT_MIN, BRIGHT_MAX,
                                      self.bright))

    def apply_bright(self, bright):
        self.bright = bright
        self.bright_var.set(str(bright))
        self.bright_slider.set(bright)
        self._commit()

    def _contrast_from_entry(self):
        self.apply_contrast(self._parse(self.contrast_var.get(), CONTRAST_MIN,
                                        CONTRAST_MAX, self.contrast))

    def apply_contrast(self, contrast):
        self.contrast = contrast
        self.contrast_var.set(str(contrast))
        self.contrast_slider.set(contrast)
        self._commit()

    def _pivot_from_entry(self):
        self.apply_pivot(self._parse(self.pivot_var.get(), PIVOT_MIN, PIVOT_MAX, self.pivot))

    def apply_pivot(self, pivot):
        self.pivot = pivot
        self.pivot_var.set(str(pivot))
        self.pivot_slider.set(pivot)
        self._commit()

    def reset_all(self):
        """Всё к нейтральному виду одним применением."""
        self.apply_all(TEMP_DEFAULT, BRIGHT_DEFAULT, CONTRAST_DEFAULT, PIVOT_DEFAULT)

    def apply_all(self, temp, bright, contrast, pivot):
        self.contrast, self.pivot = contrast, pivot
        self.contrast_var.set(str(contrast))
        self.pivot_var.set(str(pivot))
        self.contrast_slider.set(contrast)
        self.pivot_slider.set(pivot)
        self.apply_values(temp, bright)

    def apply_values(self, temp, bright):
        self.temp, self.bright = temp, bright
        self.temp_var.set(str(temp))
        self.bright_var.set(str(bright))
        self.temp_slider.set(temp)
        self.bright_slider.set(bright)
        self._commit()

    # --- пресеты и режим «Сохранить» ---
    def _preset_click(self, i):
        p = self.presets[i]
        if self.saving:
            p.update(temp=self.temp, bright=self.bright, contrast=self.contrast,
                     pivot=self.pivot)
            self.preset_buttons[i].configure(text=self._preset_text(p))
            save_presets(self.presets)
            self.cancel_save_mode()
            self._flash(t("saved", self._preset_label(p)))
        else:
            self.apply_preset(i)

    def apply_preset(self, i):
        p = self.presets[i]
        if p["contrast"] is None:
            self.apply_values(p["temp"], p["bright"])
        else:
            self.apply_all(p["temp"], p["bright"], p["contrast"], p["pivot"])

    def toggle_save_mode(self):
        if self.saving:
            self.cancel_save_mode()
            return
        focused = self.root.focus_get()
        if focused in self._entry_cmds:      # число введено, но Enter ещё не нажат
            self._entry_cmds[focused]()
        self.root.focus_set()
        self.saving = True
        self._set_dimmed(True)
        self.save_btn.configure(text=t("cancel"))
        self._light(self.save_btn, True)
        self.status.configure(text=t("pick_preset"), fg=ACCENT)
        self._blink(8)

    def cancel_save_mode(self):
        if not self.saving:
            return
        self.saving = False
        if self._blink_job:
            self.root.after_cancel(self._blink_job)
            self._blink_job = None
        for btn in self.preset_buttons:
            self._light(btn, False)
        self.save_btn.configure(text=t("save"))
        self._light(self.save_btn, False)
        self._set_dimmed(False)
        self._refresh_status()

    def _blink(self, left):
        """Пресеты мигают около секунды, потом остаются подсвеченными."""
        for btn in self.preset_buttons:
            self._light(btn, left % 2 == 0)
        self._blink_job = self.root.after(120, self._blink, left - 1) if left > 0 else None

    def _set_dimmed(self, on):
        """Всё, кроме пресетов и «Сохранить/Отмена», блекнет и не реагирует."""
        for w in self._dimmable:
            if isinstance(w, Slider):
                w.set_enabled(not on)
            elif isinstance(w, ttk.Spinbox):
                w.state(["disabled"] if on else ["!disabled"])
            elif isinstance(w, tk.Button):
                w.configure(state="disabled" if on else "normal",
                            cursor="" if on else "hand2")
            elif on:
                w.normal_fg = w.cget("fg")
                w.configure(fg=FG_OFF)
            else:
                w.configure(fg=w.normal_fg)

    def _flash(self, text):
        """Короткое сообщение в строке статуса, потом снова текущие значения."""
        self.status.configure(text=text, fg=ACCENT)
        if self._flash_job:
            self.root.after_cancel(self._flash_job)
        self._flash_job = self.root.after(2500, self._refresh_status)

    # --- статус ---
    def _refresh_status(self):
        if self.saving:
            return
        if self.error:
            self.status.configure(text=t("error") + self.error, fg="#d2604f")
        else:
            self.status.configure(
                text=t("now", self.temp, self.bright, self.contrast, self.pivot), fg=FG_DIM)


def main():
    in_tray = "--tray" in sys.argv[1:]     # автозапуск: окно не показывать, только значок
    i18n.set_language(load_language())
    try:
        server = ipc.Server()
    except OSError:                         # уже запущено: просто показать то окно
        if not in_tray:
            ipc.send("show")
        return 0
    root = tk.Tk(className="NightScreen")
    try:
        App(root, server)
    except gamma.GammaError as exc:
        root.withdraw()
        messagebox.showerror(t("err.title"), t("err." + str(exc)))
        return 1
    if in_tray:
        root.withdraw()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
