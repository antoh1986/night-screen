#!/usr/bin/python3
"""Значок Night Screen в трее. Запускается самим окном (night_screen.py).

Левая кнопка — показать окно, правая — меню: пресеты, «Открыть», «Выход». Сам значок
ничего не считает: он шлёт команды окну через ipc (оно одно и держит все настройки).
Если окна больше нет, значок сам исчезает.

Нужен системный питон: gi и XApp есть только в нём (у conda их нет), поэтому шебанг —
/usr/bin/python3. Первый аргумент — JSON с подписями меню уже на нужном языке:
{"open": ..., "quit": ..., "presets": [названия пресетов по порядку]}.
"""

import json
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("XApp", "1.0")
from gi.repository import GLib, Gtk, XApp  # noqa: E402

import ipc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def tell(command):
    """Команда окну; если его уже нет — значок тоже уходит."""
    if not ipc.send(command):
        Gtk.main_quit()


def menu_item(label, command):
    item = Gtk.MenuItem(label=label)
    item.connect("activate", lambda _w: tell(command))
    return item


def build_menu(labels):
    menu = Gtk.Menu()
    menu.append(menu_item(labels["open"], "show"))
    menu.append(Gtk.SeparatorMenuItem())
    for i, name in enumerate(labels["presets"]):
        menu.append(menu_item(name, "preset %d" % i))
    menu.append(Gtk.SeparatorMenuItem())
    menu.append(menu_item(labels["quit"], "quit"))
    menu.show_all()
    return menu


def main():
    labels = {"open": "Open", "quit": "Quit", "presets": []}
    if len(sys.argv) > 1:
        labels.update(json.loads(sys.argv[1]))
    parent = os.getppid()

    GLib.set_prgname("night-screen")     # от него имя значка на шине; «tray.py» слишком общее
    icon = XApp.StatusIcon()
    icon.set_name("night-screen")
    icon.set_icon_name(os.path.join(HERE, "icon.png"))
    icon.set_tooltip_text("Night Screen")
    icon.set_secondary_menu(build_menu(labels))
    icon.connect("activate", lambda _icon, _button, _time: tell("show"))

    def parent_alive():
        if os.getppid() != parent:       # окно закрыто аварийно — значок осиротел
            Gtk.main_quit()
            return False
        return True

    GLib.timeout_add_seconds(2, parent_alive)
    Gtk.main()


if __name__ == "__main__":
    main()
