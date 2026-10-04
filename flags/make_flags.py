#!/usr/bin/env python3
"""Рисует флаги для выбора языка: en.png, zh.png, ru.png (24×16).

Нужен только Pillow и только чтобы перерисовать картинки; самому приложению он не нужен.
Рисуется в 8-кратном размере и уменьшается — края получаются сглаженными.
"""

import math
import os

from PIL import Image, ImageDraw

W, H, K = 24, 16, 8
HERE = os.path.dirname(os.path.abspath(__file__))


def uk(d, w, h):
    blue, white, red = "#012169", "#ffffff", "#c8102e"
    d.rectangle((0, 0, w, h), fill=blue)
    for width, color in ((h * 0.20, white), (h * 0.07, red)):
        d.line((0, 0, w, h), fill=color, width=round(width))
        d.line((w, 0, 0, h), fill=color, width=round(width))
    d.rectangle((w * 0.5 - h * 0.17, 0, w * 0.5 + h * 0.17, h), fill=white)
    d.rectangle((0, h * 0.5 - h * 0.17, w, h * 0.5 + h * 0.17), fill=white)
    d.rectangle((w * 0.5 - h * 0.10, 0, w * 0.5 + h * 0.10, h), fill=red)
    d.rectangle((0, h * 0.5 - h * 0.10, w, h * 0.5 + h * 0.10), fill=red)


def star(d, cx, cy, r, turn, color):
    """Пятиконечная звезда; turn — куда смотрит один из лучей (радианы)."""
    pts = []
    for i in range(10):
        a = turn + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.382
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=color)


def cn(d, w, h):
    d.rectangle((0, 0, w, h), fill="#de2910")
    u = w / 30                                   # флаг рисуют на сетке 30×20
    yellow = "#ffde00"
    star(d, 5 * u, 5 * u, 3 * u, -math.pi / 2, yellow)
    for x, y in ((10, 2), (12, 4), (12, 7), (10, 9)):   # малые звёзды смотрят на большую
        star(d, x * u, y * u, 1 * u, math.atan2(5 - y, 5 - x) + math.pi, yellow)


def ru(d, w, h):
    for i, color in enumerate(("#ffffff", "#0039a6", "#d52b1e")):
        d.rectangle((0, h * i / 3, w, h * (i + 1) / 3), fill=color)


def make(name, draw):
    img = Image.new("RGB", (W * K, H * K))
    draw(ImageDraw.Draw(img), W * K, H * K)
    img = img.resize((W, H), Image.LANCZOS)
    ImageDraw.Draw(img).rectangle((0, 0, W - 1, H - 1), outline="#5a5a66")   # рамка: белое на тёмном
    img.save(os.path.join(HERE, name + ".png"))


if __name__ == "__main__":
    make("en", uk)
    make("zh", cn)
    make("ru", ru)
