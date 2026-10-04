"""Переводы интерфейса: английский (по умолчанию), китайский, русский.

Только стандартная библиотека. Язык хранит само окно (night_screen.py); сюда он
приходит через set_language(). Ключ без перевода берётся из английского.
"""

DEFAULT = "en"
LANGUAGES = [            # (код, как язык называется на самом себе); картинка флага — flags/<код>.png
    ("en", "English"),
    ("zh", "中文"),
    ("ru", "Русский"),
]

STRINGS = {
    "en": {
        "title": "Screen: temperature and brightness",
        "temp": "Color temperature",
        "bright": "Brightness",
        "contrast": "Contrast",
        "pivot": "Contrast pivot",
        "temp.ends": ("warmer", "cooler"),
        "bright.ends": ("darker", "brighter"),
        "contrast.ends": ("weaker", "stronger"),
        "pivot.ends": ("darkens more", "brightens more"),
        "pivot.hint": "At contrast > 100 %: right — more tones get lighter, left — darker.\n"
                      "Dim frames brighter: ≈ 80–100 %; past 100 % black gets lighter too.",
        "reset": "Reset",
        "reset_all": "Reset all",
        "save": "Save",
        "cancel": "Cancel",
        "preset.day": "Day",
        "preset.evening": "Evening",
        "preset.night": "Night",
        "preset.deep": "Deep night",
        "preset.extra": "contr. %d · pivot %d",
        "saved": "Saved to “%s”",
        "pick_preset": "Pick a preset to save into · Esc — cancel",
        "error": "Error: ",
        "now": "Now: %d K · %d %% · contrast %d %% · pivot %d %%",
        "err.libs": "libX11 / libXrandr not found",
        "err.display": "cannot connect to the X server",
        "err.xrandr": "XRandR is not responding",
        "err.crtc": "no active screens with a gamma table",
        "err.title": "Cannot control the screen",
        "tray.open": "Open",
        "tray.quit": "Quit",
    },
    "zh": {
        "title": "屏幕：色温与亮度",
        "temp": "色温",
        "bright": "亮度",
        "contrast": "对比度",
        "pivot": "对比度中心",
        "temp.ends": ("偏暖", "偏冷"),
        "bright.ends": ("更暗", "更亮"),
        "contrast.ends": ("更弱", "更强"),
        "pivot.ends": ("更多变暗", "更多变亮"),
        "pivot.hint": "对比度 > 100 % 时：向右更多色调变亮，向左更多变暗。\n"
                      "让暗淡的边框更亮：约 80–100 %；超过 100 % 时黑色也会变亮。",
        "reset": "重置",
        "reset_all": "全部重置",
        "save": "保存",
        "cancel": "取消",
        "preset.day": "白天",
        "preset.evening": "傍晚",
        "preset.night": "夜晚",
        "preset.deep": "深夜",
        "preset.extra": "对比 %d · 中心 %d",
        "saved": "已保存到“%s”",
        "pick_preset": "选择要保存的预设 · Esc 取消",
        "error": "错误：",
        "now": "当前：%d K · %d %% · 对比度 %d %% · 中心 %d %%",
        "err.libs": "未找到 libX11 / libXrandr",
        "err.display": "无法连接到 X 服务器",
        "err.xrandr": "XRandR 没有响应",
        "err.crtc": "没有带伽马表的活动屏幕",
        "err.title": "无法控制屏幕",
        "tray.open": "打开",
        "tray.quit": "退出",
    },
    "ru": {
        "title": "Экран: температура и яркость",
        "temp": "Цветовая температура",
        "bright": "Яркость",
        "contrast": "Контрастность",
        "pivot": "Центр контраста",
        "temp.ends": ("теплее", "холоднее"),
        "bright.ends": ("темнее", "ярче"),
        "contrast.ends": ("слабее", "сильнее"),
        "pivot.ends": ("темнеет больше", "светлеет больше"),
        "pivot.hint": "При контрасте > 100 %: вправо — больше тонов светлеет, влево — темнеет.\n"
                      "Тусклые рамки ярче: ≈ 80–100 %; правее 100 % светлеет и чёрное.",
        "reset": "Сбросить",
        "reset_all": "Сбросить всё",
        "save": "Сохранить",
        "cancel": "Отмена",
        "preset.day": "День",
        "preset.evening": "Вечер",
        "preset.night": "Ночь",
        "preset.deep": "Глубокая ночь",
        "preset.extra": "контр. %d · ц. %d",
        "saved": "Сохранено в «%s»",
        "pick_preset": "Выберите пресет для сохранения · Esc — отмена",
        "error": "Ошибка: ",
        "now": "Сейчас: %d K · %d %% · контраст %d %% · центр %d %%",
        "err.libs": "не найдены libX11 / libXrandr",
        "err.display": "не удалось подключиться к X-серверу",
        "err.xrandr": "XRandR не отвечает",
        "err.crtc": "нет активных экранов с гамма-таблицей",
        "err.title": "Не удалось управлять экраном",
        "tray.open": "Открыть",
        "tray.quit": "Выход",
    },
}

_lang = DEFAULT


def set_language(code):
    """Выбрать язык; неизвестный код — английский. Возвращает принятый код."""
    global _lang
    _lang = code if code in STRINGS else DEFAULT
    return _lang


def language():
    return _lang


def t(key, *args):
    """Строка на текущем языке; с аргументами подставляет их через %."""
    text = STRINGS[_lang].get(key, STRINGS[DEFAULT].get(key, key))
    return text % args if args else text
