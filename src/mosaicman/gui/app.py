"""
app.py - メインアプリケーションウィンドウ

MosaicMan のメインウィンドウ。
ファイルの読み込み・検出・プレビュー・適用・保存の
ワークフロー全体を管理します。
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image

from ..core.detector import BaseDetector
from ..core.media import ImageMedia, VideoMedia, SUPPORTED_IMAGE_EXTENSIONS, SUPPORTED_VIDEO_EXTENSIONS
from ..core.mosaic import MosaicConfig, MosaicEngine
from .preview import PreviewCanvas
from .settings import DetectorSettingsPanel, SettingsPanel


class MosaicApp(tk.Tk):
    """
    メインアプリケーションウィンドウ。

    ワークフロー:
    1. ファイルを開く
    2. 「検出」ボタンで AI による領域推薦
    3. プレビューで領域を確認・調整
    4. 「適用」ボタンでモザイクを適用
    5. 「保存」ボタンで出力
    """

    def __init__(self) -> None:
        """アプリケーションの主要コンポーネントを初期化する。"""
        super().__init__()
        self.title("MosaicMan - モザイク自動付与ツール")
        self.geometry("1200x800")
        self._engine = MosaicEngine()
        self._current_image: Image.Image | None = None
        self._current_path: Path | None = None
        self._applied_image: Image.Image | None = None
        self._is_video: bool = False
        self._status_var = tk.StringVar(value="準備完了")
        self._preview_canvas: PreviewCanvas | None = None
        self._settings_panel: SettingsPanel | None = None
        self._detector_panel: DetectorSettingsPanel | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """ツールバー、プレビュー、設定パネル、ステータスバーを構築する。"""
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        toolbar = ttk.Frame(self, padding=8)
        toolbar.grid(row=0, column=0, sticky="ew")
        for text, command in [
            ("開く", self._open_file),
            ("検出", self._detect_regions),
            ("適用", self._apply_mosaic),
            ("保存", self._save_file),
        ]:
            ttk.Button(toolbar, text=text, command=command).pack(side=tk.LEFT, padx=4)

        content = ttk.Frame(self, padding=(8, 0, 8, 8))
        content.grid(row=1, column=0, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        self._preview_canvas = PreviewCanvas(content)
        self._preview_canvas.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right_panel = ttk.Frame(content)
        right_panel.grid(row=0, column=1, sticky="ns")

        self._detector_panel = DetectorSettingsPanel(right_panel, padding=8)
        self._detector_panel.pack(fill=tk.X, pady=(0, 8))

        self._settings_panel = SettingsPanel(right_panel, padding=8)
        self._settings_panel.pack(fill=tk.X)

        status_bar = ttk.Label(self, textvariable=self._status_var, anchor=tk.W, padding=8)
        status_bar.grid(row=2, column=0, sticky="ew")

    def _open_file(self) -> None:
        """画像または動画を開いてプレビューに表示する。"""
        file_path = filedialog.askopenfilename(
            title="ファイルを開く",
            filetypes=[
                ("対応ファイル", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.mp4 *.mov *.avi *.mkv"),
                ("画像", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"),
                ("動画", "*.mp4 *.mov *.avi *.mkv"),
            ],
        )
        if not file_path:
            return

        try:
            path = Path(file_path)
            suffix = path.suffix.lower()
            self._current_path = path
            self._applied_image = None
            if suffix in SUPPORTED_IMAGE_EXTENSIONS:
                self._current_image = ImageMedia.load(path)
                self._is_video = False
            elif suffix in SUPPORTED_VIDEO_EXTENSIONS:
                with VideoMedia(path) as video:
                    first_frame = next(video.frames(), None)
                if first_frame is None:
                    raise ValueError("動画からフレームを取得できませんでした")
                _, frame = first_frame
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self._current_image = Image.fromarray(rgb_frame)
                self._is_video = True
            else:
                raise ValueError("未対応のファイル形式です")

            assert self._preview_canvas is not None
            self._preview_canvas.set_image(self._current_image)
            self._preview_canvas.set_regions([])
            self._update_status(f"ファイルを読み込みました: {path.name}")
        except Exception as exc:  # pragma: no cover - GUI 例外経路
            messagebox.showerror("読み込みエラー", str(exc))
            self._update_status("読み込みに失敗しました")

    def _detect_regions(self) -> None:
        """現在画像に対して推薦領域検出をバックグラウンド実行する。

        DetectorSettingsPanel の設定に基づいて検出器インスタンスを生成するため、
        「検出」を押すたびに最新の設定が反映されます。
        """
        if self._current_image is None:
            messagebox.showinfo("情報", "先にファイルを開いてください。")
            return

        assert self._detector_panel is not None
        try:
            detector = self._detector_panel.get_detector()
        except Exception as exc:  # pragma: no cover - GUI 例外経路
            messagebox.showerror("検出器設定エラー", str(exc))
            return

        def worker() -> None:
            try:
                self._update_status("領域を検出しています...")
                detected = detector.detect_from_pil(self._current_image)
                self.after(0, lambda: self._apply_detected_regions(detected))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("検出エラー", str(exc)))
                self.after(0, lambda: self._update_status("領域検出に失敗しました"))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_mosaic(self) -> None:
        """現在の設定と有効領域を使ってプレビューへモザイクを適用する。"""
        if self._current_image is None:
            messagebox.showinfo("情報", "先にファイルを開いてください。")
            return

        assert self._preview_canvas is not None
        assert self._settings_panel is not None
        config = self._settings_panel.get_config()
        enabled_regions = self._preview_canvas.get_enabled_regions()

        if not enabled_regions:
            messagebox.showinfo("情報", "適用対象の領域がありません。")
            return

        try:
            self._applied_image = self._apply_to_pil_image(self._current_image, enabled_regions, config)
            self._preview_canvas.set_image(self._applied_image)
            if self._is_video:
                self._update_status("プレビューにモザイクを適用しました。保存時に動画全体へ反映されます。")
            else:
                self._update_status("画像へモザイクを適用しました。")
        except Exception as exc:  # pragma: no cover - GUI 例外経路
            messagebox.showerror("適用エラー", str(exc))
            self._update_status("モザイク適用に失敗しました")

    def _save_file(self) -> None:
        """画像または動画を保存する。"""
        if self._current_path is None or self._current_image is None:
            messagebox.showinfo("情報", "先にファイルを開いてください。")
            return

        if self._is_video:
            if not messagebox.askyesno("確認", "動画全体へモザイクを適用して保存します。時間がかかる場合があります。続行しますか？"):
                return
            self._save_video()
            return

        default_name = f"{self._current_path.stem}_mosaic.png"
        output = filedialog.asksaveasfilename(
            title="画像を保存",
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg *.jpeg"), ("BMP", "*.bmp"), ("TIFF", "*.tiff")],
        )
        if not output:
            return

        try:
            image_to_save = self._applied_image or self._apply_to_pil_image(
                self._current_image,
                self._preview_canvas.get_enabled_regions(),
                self._settings_panel.get_config(),
            )
            suffix = Path(output).suffix.lower()
            if suffix == ".png":
                ImageMedia.save_lossless(image_to_save, output)
            else:
                ImageMedia.save(image_to_save, output)
            self._update_status(f"保存しました: {Path(output).name}")
        except Exception as exc:  # pragma: no cover - GUI 例外経路
            messagebox.showerror("保存エラー", str(exc))
            self._update_status("保存に失敗しました")

    def _update_status(self, msg: str) -> None:
        """ステータスバー文字列を更新する。"""
        if threading.current_thread() is threading.main_thread():
            self._status_var.set(msg)
        else:
            self.after(0, lambda: self._status_var.set(msg))

    def _apply_detected_regions(self, detected) -> None:
        """検出結果をプレビューへ反映する。"""
        assert self._preview_canvas is not None
        self._preview_canvas.set_regions(detected)
        self._update_status(f"{len(detected)} 件の領域を検出しました")

    def _apply_to_pil_image(self, image: Image.Image, regions, config: MosaicConfig) -> Image.Image:
        """PIL Image に複数領域のモザイクを順次適用する。"""
        array = np.array(image.convert("RGB"))
        for region in regions:
            array = self._engine.apply(array, (region.x, region.y, region.width, region.height), config)
        return Image.fromarray(array)

    def _save_video(self) -> None:
        """動画へフレーム単位でモザイクを適用して保存する。"""
        assert self._preview_canvas is not None
        assert self._settings_panel is not None
        regions = self._preview_canvas.get_enabled_regions()
        if not regions:
            messagebox.showinfo("情報", "適用対象の領域がありません。")
            return

        default_name = f"{self._current_path.stem}_mosaic{self._current_path.suffix}"
        output = filedialog.asksaveasfilename(
            title="動画を保存",
            initialfile=default_name,
            defaultextension=self._current_path.suffix,
            filetypes=[("動画", "*.mp4 *.mov *.avi *.mkv")],
        )
        if not output:
            return

        config = self._settings_panel.get_config()

        def worker() -> None:
            try:
                self._update_status("動画へモザイクを適用して保存しています...")
                with VideoMedia(self._current_path) as video:
                    video.save_with_mosaic(output, lambda frame: self._apply_to_frame(frame, regions, config), lossless=True)
                self.after(0, lambda: self._update_status(f"保存しました: {Path(output).name}"))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("保存エラー", str(exc)))
                self.after(0, lambda: self._update_status("動画保存に失敗しました"))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_to_frame(self, frame: np.ndarray, regions, config: MosaicConfig) -> np.ndarray:
        """動画フレームへモザイクを適用する。"""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        for region in regions:
            rgb = self._engine.apply(rgb, (region.x, region.y, region.width, region.height), config)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
