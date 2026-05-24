"""
settings.py - モザイク設定パネル / 検出器設定パネル

モザイクの種類・ブロックサイズ・ぼかし半径・黒帯設定などを
tkinter ウィジェットで設定するパネル（SettingsPanel）と、
検出器の種類・接続先・API キーを設定するパネル（DetectorSettingsPanel）を提供します。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..core.detector import BaseDetector, create_detector
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


# --------------------------------------------------------------------------- #
#  検出器設定パネル
# --------------------------------------------------------------------------- #

#: 表示名 → create_detector() に渡す detector_type 文字列
_DETECTOR_DISPLAY_NAMES: dict[str, str] = {
    "Haar分類器 (ローカル・追加不要)": "haar",
    "Ollama LLM (ローカル)": "ollama",
    "OpenAI API (クラウド)": "openai",
}


class DetectorSettingsPanel(ttk.LabelFrame):
    """
    検出器の種類と接続設定をまとめたパネルウィジェット。

    get_detector() で現在の設定に応じた BaseDetector インスタンスを返します。
    OpenAI API キーは画面上ではマスク表示し、ログへ出力しません。
    """

    def __init__(self, parent: tk.Misc, **kwargs: object) -> None:
        """設定用変数と UI を初期化する。"""
        super().__init__(parent, text="検出器設定", **kwargs)
        self._detector_var = tk.StringVar(value=list(_DETECTOR_DISPLAY_NAMES.keys())[0])
        self._ollama_host_var = tk.StringVar(value="http://localhost:11434")
        self._ollama_model_var = tk.StringVar(value="llava")
        self._openai_key_var = tk.StringVar(value="")
        self._openai_model_var = tk.StringVar(value="gpt-4o")
        # 各検出器固有設定を格納するフレームの参照（show/hide 用）
        self._ollama_frame: ttk.Frame | None = None
        self._openai_frame: ttk.Frame | None = None
        self._build_ui()
        self._on_detector_changed()

    def _build_ui(self) -> None:
        """検出器種別コンボと、種別ごとの設定フレームを構築する。"""
        self.columnconfigure(1, weight=1)

        # --- 検出器種別 ---
        ttk.Label(self, text="検出器").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        detector_cb = ttk.Combobox(
            self,
            textvariable=self._detector_var,
            values=list(_DETECTOR_DISPLAY_NAMES.keys()),
            state="readonly",
            width=28,
        )
        detector_cb.grid(row=0, column=1, sticky="ew", padx=8, pady=6)
        detector_cb.bind("<<ComboboxSelected>>", lambda _e: self._on_detector_changed())

        # --- Ollama 固有設定 ---
        self._ollama_frame = ttk.Frame(self)
        self._ollama_frame.columnconfigure(1, weight=1)
        ttk.Label(self._ollama_frame, text="Ollamaホスト").grid(
            row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(self._ollama_frame, textvariable=self._ollama_host_var).grid(
            row=0, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(self._ollama_frame, text="モデル名").grid(
            row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(self._ollama_frame, textvariable=self._ollama_model_var).grid(
            row=1, column=1, sticky="ew", padx=8, pady=4)

        # --- OpenAI 固有設定 ---
        self._openai_frame = ttk.Frame(self)
        self._openai_frame.columnconfigure(1, weight=1)
        ttk.Label(self._openai_frame, text="APIキー").grid(
            row=0, column=0, sticky="w", padx=8, pady=4)
        # API キーはマスク表示（show="*"）してスクリーンショット等に残さない
        ttk.Entry(self._openai_frame, textvariable=self._openai_key_var, show="*").grid(
            row=0, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(self._openai_frame, text="モデル名").grid(
            row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(self._openai_frame, textvariable=self._openai_model_var).grid(
            row=1, column=1, sticky="ew", padx=8, pady=4)

    def _on_detector_changed(self) -> None:
        """検出器種別の変更に応じて固有設定フレームを表示/非表示にする。"""
        assert self._ollama_frame is not None
        assert self._openai_frame is not None
        selected = _DETECTOR_DISPLAY_NAMES.get(self._detector_var.get(), "haar")

        if selected == "ollama":
            self._openai_frame.grid_remove()
            self._ollama_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        elif selected == "openai":
            self._ollama_frame.grid_remove()
            self._openai_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        else:
            self._ollama_frame.grid_remove()
            self._openai_frame.grid_remove()

    def get_detector(self) -> BaseDetector:
        """現在の設定から BaseDetector インスタンスを生成して返す。"""
        detector_type = _DETECTOR_DISPLAY_NAMES.get(self._detector_var.get(), "haar")
        return create_detector(
            detector_type,
            ollama_host=self._ollama_host_var.get(),
            ollama_model=self._ollama_model_var.get(),
            openai_api_key=self._openai_key_var.get(),
            openai_model=self._openai_model_var.get(),
        )
