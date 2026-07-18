from __future__ import annotations

import logging
from typing import Callable

from PIL import Image, ImageDraw

from .i18n import tr


class TrayController:
    def __init__(self, callback: Callable[[str], None]):
        self.callback = callback
        self.icon = None

    @staticmethod
    def _image() -> Image.Image:
        image = Image.new("RGBA", (64, 64), (20, 24, 34, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((7, 13, 57, 51), radius=8, fill=(44, 169, 225, 255))
        draw.ellipse((23, 21, 43, 41), fill=(255, 255, 255, 255))
        draw.ellipse((28, 26, 38, 36), fill=(20, 24, 34, 255))
        draw.rectangle((18, 8, 32, 17), fill=(44, 169, 225, 255))
        return image

    def start(self) -> bool:
        try:
            import pystray

            def action(name: str):
                return lambda _icon, _item: self.callback(name)

            menu = pystray.Menu(
                pystray.MenuItem(tr("FlipCaptureを表示"), action("show"), default=True),
                pystray.MenuItem(tr("監視開始"), action("start")),
                pystray.MenuItem(tr("監視停止"), action("stop")),
                pystray.MenuItem(tr("保存フォルダを開く"), action("folder")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(tr("完全に終了"), action("exit")),
            )
            self.icon = pystray.Icon("FlipCapture", self._image(), "FlipCapture", menu)
            self.icon.run_detached()
            return True
        except Exception:
            logging.exception("task tray initialization failed")
            self.icon = None
            return False

    def notify(self, message: str) -> None:
        if self.icon:
            try:
                self.icon.notify(tr(message), "FlipCapture")
            except Exception:
                logging.exception("task tray notification failed")

    def stop(self) -> None:
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                logging.exception("task tray shutdown failed")
            finally:
                self.icon = None
