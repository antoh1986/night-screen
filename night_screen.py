#!/usr/bin/env python3
"""Экран: температура, яркость и контраст — GUI для гамма-таблицы видеокарты.

Таблицу выставляет модуль gamma (XRandR, как это делает `xsct`). Подсветку
монитора не трогаем, меняется только картинка, которую выводит видеокарта.
"""

import json
import math
import os
import re
import shutil
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk

import gamma

# --- пределы ---------------------------------------------------------------
TEMP_MIN, TEMP_MAX, TEMP_STEP = 1000, 10000, 50
TEMP_DEFAULT = 6500                 # «нейтральный» белый
BRIGHT_MIN, BRIGHT_MAX = 10, 100    # проценты; ниже 10 % экран почти не видно
BRIGHT_DEFAULT = 100
CONTRAST_MIN, CONTRAST_MAX = 30, 150  # проценты; выше 100 крайние тона обрезаются
CONTRAST_DEFAULT = 100
PIVOT_MIN, PIVOT_MAX = 0, 100       # ползунок «Центр контраста»: вправо — больше светлеет
PIVOT_DEFAULT = 50
STATE_FILE = os.path.expanduser("~/.config/night-screen/state.json")

# (название, температура K, яркость %)
PRESETS = [
    ("День", 6500, 100),
    ("Вечер", 5000, 80),
    ("Ночь", 4500, 60),
    ("Глубокая ночь", 3500, 40),
]

# --- палитра: тёмная и неяркая, чтобы само окно не слепило ночью ------------
BG = "#17171b"
PANEL = "#1f1f25"
FG = "#b9b9c2"
FG_DIM = "#7c7c88"
ACCENT = "#d9822b"
FIELD = "#101014"
BORDER = "#34343d"


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
    светлела (центр опускается), а влево — темнела, как и цвет дорожки."""
    return (PIVOT_MAX - slider_value) / 100


def save_state(temp, bright, contrast, pivot):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"temp": temp, "bright": bright, "contrast": contrast,
                       "pivot": pivot}, f)
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
            if isinstance(color, tuple):          # (верхняя половина, нижняя половина)
                self.create_line(x0 + i, y0, x0 + i, cy, fill=color[0])
                self.create_line(x0 + i, cy, x0 + i, y1, fill=color[1])
            else:
                self.create_line(x0 + i, y0, x0 + i, y1, fill=color)
        self.create_rectangle(x0, y0, x1, y1, outline=BORDER)
        x = self._x_of(self.value)
        ring = ACCENT if self.focus_get() is self else FG
        self.create_oval(x - self.THUMB_R, cy - self.THUMB_R, x + self.THUMB_R,
                         cy + self.THUMB_R, fill=BG, outline=ring, width=2)

    def set(self, value):
        """Выставить значение программно (команду не вызывает)."""
        self.value = max(self.lo, min(self.hi, value))
        self.redraw()

    def _emit(self, value):
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
        self.focus_set()
        self._emit(self._from_x(e.x))

    def _drag(self, e):
        self._emit(self._from_x(e.x))

    def _nudge(self, direction):
        self._emit(self.value + direction * self.step)
        return "break"


# --- само окно --------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.screen = gamma.Screen()
        self.error = None
        self._save_job = None
        self.temp, self.bright, self.contrast, self.pivot = self._initial_values()

        root.title("Экран: температура и яркость")
        root.configure(bg=BG)
        root.minsize(440, 0)
        root.resizable(True, False)
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
        try:
            root.iconphoto(True, tk.PhotoImage(file=icon_path))
        except tk.TclError:
            pass

        self._style()
        outer = tk.Frame(root, bg=BG, padx=16, pady=14)
        outer.pack(fill="both", expand=True)

        self.temp_var = tk.StringVar(value=str(self.temp))
        self.bright_var = tk.StringVar(value=str(self.bright))
        self.contrast_var = tk.StringVar(value=str(self.contrast))
        self.pivot_var = tk.StringVar(value=str(self.pivot))

        self.temp_slider = self._section(
            outer, "Цветовая температура", "K", self.temp_var,
            TEMP_MIN, TEMP_MAX, TEMP_STEP, self.temp,
            self._temp_from_slider, self._temp_from_entry,
            lambda f: rgb_hex(kelvin_to_rgb(TEMP_MIN + f * (TEMP_MAX - TEMP_MIN))),
            ("теплее", "холоднее"))
        self.bright_slider = self._section(
            outer, "Яркость", "%", self.bright_var,
            BRIGHT_MIN, BRIGHT_MAX, 1, self.bright,
            self._bright_from_slider, self._bright_from_entry,
            lambda f: rgb_hex(kelvin_to_rgb(self.temp), 0.08 + 0.92 * f),
            ("темнее", "ярче"))
        self.contrast_slider = self._section(
            outer, "Контрастность", "%", self.contrast_var,
            CONTRAST_MIN, CONTRAST_MAX, 1, self.contrast,
            self._contrast_from_slider, self._contrast_from_entry,
            self._contrast_track, ("слабее", "сильнее"),
            reset=lambda: self.apply_contrast(CONTRAST_DEFAULT))
        self.pivot_slider = self._section(
            outer, "Центр контраста", "%", self.pivot_var,
            PIVOT_MIN, PIVOT_MAX, 1, self.pivot,
            self._pivot_from_slider, self._pivot_from_entry,
            lambda f: rgb_hex((255, 255, 255), f), ("темнеет больше", "светлеет больше"),
            reset=lambda: self.apply_pivot(PIVOT_DEFAULT),
            hint="При контрасте > 100 %: вправо — больше тонов светлеет, влево — темнеет.\n"
                 "Тусклые рамки ярче: ≈ 80–90 %. При контрасте 100 % не действует.")

        presets = tk.Frame(outer, bg=BG)
        presets.pack(fill="x", pady=(14, 0))
        for i, (name, t, b) in enumerate(PRESETS):
            presets.columnconfigure(i, weight=1, uniform="p")
            self._button(presets, "%s\n%d K · %d %%" % (name, t, b),
                         lambda t=t, b=b: self.apply_values(t, b)
                         ).grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))

        bottom = tk.Frame(outer, bg=BG)
        bottom.pack(fill="x", pady=(12, 0))
        self.status = tk.Label(bottom, bg=BG, fg=FG_DIM, anchor="w", font=("TkDefaultFont", 9))
        self.status.pack(side="left", fill="x", expand=True)
        self._button(bottom, "Сбросить всё", self.reset_all,
                     pad=(14, 4)).pack(side="right")

        root.protocol("WM_DELETE_WINDOW", self._close)
        self._refresh_status()

    def _initial_values(self):
        """Сохранённые значения, если экран сейчас именно такой; иначе — то, что видит xsct."""
        saved = load_state()
        if saved:
            t, b, c, p = saved
            if (TEMP_MIN <= t <= TEMP_MAX and BRIGHT_MIN <= b <= BRIGHT_MAX
                    and CONTRAST_MIN <= c <= CONTRAST_MAX and PIVOT_MIN <= p <= PIVOT_MAX
                    and self.screen.matches(t, b / 100, c / 100, pivot_level(p))):
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
               lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)])

    def _button(self, parent, text, command, pad=(8, 6)):
        btn = tk.Button(parent, text=text, command=command, bg=PANEL, fg=FG,
                        activebackground=BORDER, activeforeground=FG,
                        relief="flat", bd=0, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=ACCENT,
                        padx=pad[0], pady=pad[1], cursor="hand2",
                        font=("TkDefaultFont", 9))
        btn.bind("<Enter>", lambda e: btn.configure(bg=BORDER))
        btn.bind("<Leave>", lambda e: btn.configure(bg=PANEL))
        return btn

    def _section(self, parent, title, unit, var, lo, hi, step, value,
                 slider_cmd, entry_cmd, track_color, ends, reset=None, hint=None):
        box = tk.Frame(parent, bg=PANEL, padx=14, pady=10)
        box.pack(fill="x", pady=(0, 10))

        head = tk.Frame(box, bg=PANEL)
        head.pack(fill="x")
        tk.Label(head, text=title, bg=PANEL, fg=FG,
                 font=("TkDefaultFont", 11, "bold")).pack(side="left")
        tk.Label(head, text=unit, bg=PANEL, fg=FG_DIM).pack(side="right", padx=(4, 0))
        spin = ttk.Spinbox(head, from_=lo, to=hi, increment=step if unit == "K" else 1,
                           textvariable=var, width=7, justify="right",
                           style="Warm.TSpinbox", command=entry_cmd)
        spin.pack(side="right")
        if reset:
            self._button(head, "Сбросить", reset, pad=(8, 1)).pack(side="right", padx=(0, 10))
        for ev in ("<Return>", "<KP_Enter>", "<FocusOut>"):
            spin.bind(ev, lambda e, cmd=entry_cmd: cmd())

        slider = Slider(box, lo, hi, step, value, slider_cmd, track_color)
        slider.pack(fill="x", pady=(6, 0))

        legend = tk.Frame(box, bg=PANEL)
        legend.pack(fill="x")
        tk.Label(legend, text="◀ %s  %d" % (ends[0], lo), bg=PANEL, fg=FG_DIM,
                 font=("TkDefaultFont", 8)).pack(side="left")
        tk.Label(legend, text="%d  %s ▶" % (hi, ends[1]), bg=PANEL, fg=FG_DIM,
                 font=("TkDefaultFont", 8)).pack(side="right")
        if hint:
            tk.Label(box, text=hint, bg=PANEL, fg=FG_DIM, justify="left", anchor="w",
                     font=("TkDefaultFont", 8)).pack(fill="x", pady=(6, 0))
        return slider

    # --- изменение значений ---
    def _commit(self):
        try:
            self.screen.set(self.temp, self.bright / 100, self.contrast / 100,
                            pivot_level(self.pivot))
            self.error = None
        except gamma.GammaError as exc:
            self.error = str(exc)
        self._refresh_status()
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, self._save)

    def _save(self):
        self._save_job = None
        save_state(self.temp, self.bright, self.contrast, self.pivot)

    def _close(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save()
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
        self.temp = self._parse(self.temp_var.get(), TEMP_MIN, TEMP_MAX, self.temp)
        self.temp_var.set(str(self.temp))
        self.temp_slider.set(self.temp)
        self.bright_slider.redraw()
        self._commit()

    def _bright_from_entry(self):
        self.bright = self._parse(self.bright_var.get(), BRIGHT_MIN, BRIGHT_MAX, self.bright)
        self.bright_var.set(str(self.bright))
        self.bright_slider.set(self.bright)
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
        self.contrast, self.pivot = CONTRAST_DEFAULT, PIVOT_DEFAULT
        self.contrast_var.set(str(self.contrast))
        self.pivot_var.set(str(self.pivot))
        self.contrast_slider.set(self.contrast)
        self.pivot_slider.set(self.pivot)
        self.apply_values(TEMP_DEFAULT, BRIGHT_DEFAULT)

    def apply_values(self, temp, bright):
        self.temp, self.bright = temp, bright
        self.temp_var.set(str(temp))
        self.bright_var.set(str(bright))
        self.temp_slider.set(temp)
        self.bright_slider.set(bright)
        self._commit()

    # --- статус ---
    def _refresh_status(self):
        if self.error:
            self.status.configure(text="Ошибка: " + self.error, fg="#d2604f")
        else:
            self.status.configure(
                text="Сейчас: %d K · %d %% · контраст %d %% · центр %d %%"
                     % (self.temp, self.bright, self.contrast, self.pivot), fg=FG_DIM)


def main():
    root = tk.Tk(className="NightScreen")
    try:
        App(root)
    except gamma.GammaError as exc:
        root.withdraw()
        messagebox.showerror("Не удалось управлять экраном", str(exc))
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
