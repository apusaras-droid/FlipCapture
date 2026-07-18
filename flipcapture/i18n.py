from __future__ import annotations

import json
import logging
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any


APP_DIR = Path(__file__).resolve().parent.parent
LOCALES_DIR = APP_DIR / "locales"


@dataclass(frozen=True)
class LocaleInfo:
    code: str
    name: str
    translations: dict[str, str]


_locales: dict[str, LocaleInfo] = {}
_current = "en"
_messageboxes_wrapped = False


def load_locales() -> dict[str, LocaleInfo]:
    global _locales
    found: dict[str, LocaleInfo] = {}
    if LOCALES_DIR.exists():
        for path in sorted(LOCALES_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                code = str(data.get("code") or path.stem).strip()
                name = str(data["name"]).strip()
                translations = data.get("translations", {})
                if not code or not name or not isinstance(translations, dict):
                    raise ValueError("invalid locale metadata")
                found[code] = LocaleInfo(
                    code, name, {str(key): str(value) for key, value in translations.items()}
                )
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                logging.exception("invalid language file ignored: %s", path)
    if "en" not in found:
        found["en"] = LocaleInfo("en", "English", {})
    if "ja" not in found:
        found["ja"] = LocaleInfo("ja", "日本語", {})
    _locales = found
    return dict(found)


def set_language(code: str) -> str:
    global _current
    if not _locales:
        load_locales()
    _current = code if code in _locales else "en"
    return _current


def current_language() -> str:
    return _current


def available_locales() -> list[LocaleInfo]:
    if not _locales:
        load_locales()
    ordered = [item for code in ("en", "ja") if (item := _locales.get(code))]
    ordered.extend(item for code, item in sorted(_locales.items()) if code not in {"en", "ja"})
    return ordered


def tr(source: Any, **values: Any) -> str:
    text = str(source)
    locale = _locales.get(_current)
    translated = locale.translations.get(text, text) if locale else text
    if values:
        try:
            return translated.format(**values)
        except (KeyError, ValueError):
            logging.warning("language string format mismatch: %s / %s", _current, text)
    return translated


def translate_widget_tree(widget: object) -> None:
    """Translate static Tk widget text; safe for third-party locale files."""
    # Tk leaves event.widget as a Tcl path string when the mapped widget has
    # already disappeared before the idle callback runs.
    if not isinstance(widget, tk.Misc):
        return
    try:
        if isinstance(widget, (tk.Tk, tk.Toplevel)):
            widget.title(tr(widget.title()))
        try:
            text = widget.cget("text")
            if text:
                widget.configure(text=tr(text))
        except (AttributeError, tk.TclError, TypeError):
            pass
        if isinstance(widget, ttk.Combobox):
            values = widget.cget("values")
            if values:
                widget.configure(values=tuple(tr(value) for value in values))
        for child in widget.winfo_children():
            translate_widget_tree(child)
    except tk.TclError:
        pass


def install_tk_translation_hooks(root: tk.Misc) -> None:
    global _messageboxes_wrapped
    root.bind_all(
        "<Map>",
        lambda event: root.after_idle(lambda target=event.widget: translate_widget_tree(target)),
        add="+",
    )
    if _messageboxes_wrapped:
        return
    for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel", "askretrycancel"):
        original = getattr(messagebox, name)

        def wrapper(title: object, message: object, *args: object, _original=original, **kwargs: object):
            return _original(tr(title), tr(message), *args, **kwargs)

        setattr(messagebox, name, wrapper)
    _messageboxes_wrapped = True
