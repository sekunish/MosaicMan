"""
main.py - エントリーポイント

MosaicMan アプリケーションの起動スクリプト。
PySide6 の QApplication を初期化してからメインウィンドウを起動します。
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .gui.app import MosaicApp


def main() -> None:
    """アプリケーションを起動する。"""
    app = QApplication(sys.argv)
    app.setApplicationName("MosaicMan")
    app.setApplicationVersion("0.1.0")
    window = MosaicApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
