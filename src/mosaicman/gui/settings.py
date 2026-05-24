"""
settings.py - モザイク設定パネル

モザイクの種類・ブロックサイズ・ぼかし半径・黒帯設定などを
tkinter ウィジェットで設定するパネル。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..core.mosaic import MosaicConfig, MosaicType


class SettingsPanel(ttk.LabelFrame):
    """
    モザイク設定をまとめたパネルウィジェット。
    get_config() で現在の設定を MosaicConfig として取得できる。
    """

    def __init__(self, parent: tk.Misc, **kwargs: object) -> None:
        """設定用変数と UI を初期化する。"""
        super().__init__(parent, text="モザイク設定", **kwargs)
        self._type_var = tk.StringVar(value="ピクセル化")
        self._block_size_var = tk.IntVar(value=15)
        self._blur_radius_var = tk.IntVar(value=21)
        self._bar_count_var = tk.IntVar(value=5)
        self._bar_angle_var = tk.DoubleVar(value=0.0)
        self._bar_opacity_var = tk.DoubleVar(value=1.0)
        self._type_map = {
            "ピクセル化": MosaicType.PIXELATE,
            "ぼかし": MosaicType.BLUR,
            "黒帯": MosaicType.BLACK_BARS,
        }
        self._reverse_type_map = {value: key for key, value in self._type_map.items()}
        self._build_ui()

    def _build_ui(self) -> None:
        """各種スライダーとコンボボックスを構築する。"""
        self.columnconfigure(1, weight=1)

        controls = [
            ("種類", ttk.Combobox(self, textvariable=self._type_var, values=list(self._type_map.keys()), state="readonly")),
            ("ブロックサイズ", ttk.Scale(self, from_=5, to=100, variable=self._block_size_var, orient=tk.HORIZONTAL)),
            ("ぼかし半径", ttk.Scale(self, from_=3, to=101, variable=self._blur_radius_var, orient=tk.HORIZONTAL)),
            ("黒帯本数", ttk.Scale(self, from_=1, to=20, variable=self._bar_count_var, orient=tk.HORIZONTAL)),
            ("黒帯角度", ttk.Scale(self, from_=0, to=180, variable=self._bar_angle_var, orient=tk.HORIZONTAL)),
            ("黒帯不透明度", ttk.Scale(self, from_=0.0, to=1.0, variable=self._bar_opacity_var, orient=tk.HORIZONTAL)),
        ]

        for row, (label, widget) in enumerate(controls):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=6)
            widget.grid(row=row, column=1, sticky="ew", padx=8, pady=6)

    def get_config(self) -> MosaicConfig:
        """現在の UI 状態を MosaicConfig に変換する。"""
        blur_radius = int(round(self._blur_radius_var.get()))
        if blur_radius % 2 == 0:
            blur_radius += 1
        return MosaicConfig(
            mosaic_type=self._type_map[self._type_var.get()],
            block_size=int(round(self._block_size_var.get())),
            blur_radius=blur_radius,
            bar_count=int(round(self._bar_count_var.get())),
            bar_angle=float(self._bar_angle_var.get()),
            bar_opacity=float(self._bar_opacity_var.get()),
        )

    def set_config(self, config: MosaicConfig) -> None:
        """MosaicConfig の内容を UI へ反映する。"""
        self._type_var.set(self._reverse_type_map[config.mosaic_type])
        self._block_size_var.set(config.block_size)
        self._blur_radius_var.set(config.blur_radius)
        self._bar_count_var.set(config.bar_count)
        self._bar_angle_var.set(config.bar_angle)
        self._bar_opacity_var.set(config.bar_opacity)
