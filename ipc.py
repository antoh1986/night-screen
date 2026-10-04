"""Один экземпляр окна и команды ему: show, preset N, quit.

Сокет живёт в абстрактном пространстве имён Linux: файла на диске нет и он исчезает
вместе с процессом, так что «зависшей» блокировки не бывает. Только стандартная
библиотека: модуль нужен и окну (питон из PATH), и значку в трее (системный питон).
"""

import os
import socket

NAME = "\0night-screen-%d" % os.getuid()


def send(command):
    """Передать команду уже запущенному окну. False — окно не запущено."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect(NAME)
        s.sendall(command.encode() + b"\n")
        return True
    except OSError:
        return False
    finally:
        s.close()


class Server:
    """Принимает команды. OSError при создании — окно уже запущено."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.bind(NAME)
        except OSError:
            self.sock.close()
            raise
        self.sock.listen(8)
        self.sock.setblocking(False)

    def poll(self):
        """Пришедшие команды (строки); не блокирует."""
        commands = []
        while True:
            try:
                conn, _ = self.sock.accept()
            except (BlockingIOError, InterruptedError):
                return commands
            with conn:
                conn.settimeout(0.2)
                try:
                    data = conn.recv(256)
                except OSError:
                    continue
            commands.append(data.decode(errors="replace").strip())

    def close(self):
        self.sock.close()
