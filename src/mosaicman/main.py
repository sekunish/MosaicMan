"""
main.py - エントリーポイント

MosaicMan アプリケーションの起動スクリプト。
"""

from .gui.app import MosaicApp


def main() -> None:
    """アプリケーションを起動する。"""
    app = MosaicApp()
    app.mainloop()


if __name__ == "__main__":
    main()
