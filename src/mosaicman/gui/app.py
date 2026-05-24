"""
app.py - メインアプリケーションウィンドウ（PySide6 版）

MosaicMan のメインウィンドウ。
ファイルの読み込み・検出・プレビュー・適用・保存の
ワークフロー全体を管理します。
PySide6 の QThread とシグナル/スロット機構を使い、
UI のブロックなしで重い処理を実行します。
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..core.detector import BaseDetector
from ..core.media import (
    ImageMedia,
    SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS,
    VideoMedia,
)
from ..core.mosaic import MosaicConfig, MosaicEngine
from .preview import PreviewCanvas
from .settings import DetectorSettingsPanel, SettingsPanel


class _DetectWorker(QThread):
    """バックグラウンドで領域検出を実行するワーカースレッド。"""

    finished = Signal(list)
    error = Signal(str)

    def __init__(self, detector: BaseDetector, image: Image.Image, parent=None) -> None:
        super().__init__(parent)
        self._detector = detector
        self._image = image.copy()

    def run(self) -> None:
        try:
            regions = self._detector.detect_from_pil(self._image)
            self.finished.emit(regions)
        except Exception as exc:  # pragma: no cover - GUI 例外経路
            self.error.emit(str(exc))


class _VideoSaveWorker(QThread):
    """バックグラウンドで動画へモザイクを適用して保存するワーカースレッド。"""

    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int)

    def __init__(self, video_path: Path, output_path: str, regions, config: MosaicConfig, parent=None) -> None:
        super().__init__(parent)
        self._video_path = video_path
        self._output_path = output_path
        self._regions = list(regions)
        self._config = config
        self._engine = MosaicEngine()

    def run(self) -> None:
        try:
            with VideoMedia(self._video_path) as video:
                total = max(1, video.frame_count)
                processed = 0

                def mosaic_fn(frame: np.ndarray) -> np.ndarray:
                    nonlocal processed
                    if self.isInterruptionRequested():
                        raise InterruptedError("動画保存がキャンセルされました")
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    for region in self._regions:
                        rgb = self._engine.apply(rgb, (region.x, region.y, region.width, region.height), self._config)
                    processed += 1
                    self.progress.emit(int(processed / total * 100))
                    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

                video.save_with_mosaic(self._output_path, mosaic_fn, lossless=True)
            self.finished.emit(self._output_path)
        except Exception as exc:  # pragma: no cover - GUI 例外経路
            self.error.emit(str(exc))


class MosaicApp(QMainWindow):
    """
    MosaicMan メインウィンドウ。

    ワークフロー:
    1. ファイルを開く
    2. 「検出」ボタンで AI による領域推薦（バックグラウンドスレッド）
    3. プレビューで領域を確認・調整
    4. 「適用」ボタンでプレビューへモザイクを反映
    5. 「保存」ボタンで出力
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MosaicMan - モザイク自動付与ツール")
        self.resize(1280, 800)
        self._engine = MosaicEngine()
        self._current_image: Image.Image | None = None
        self._current_path: Path | None = None
        self._applied_image: Image.Image | None = None
        self._is_video = False
        self._detect_worker: _DetectWorker | None = None
        self._video_worker: _VideoSaveWorker | None = None
        self._progress_dialog: QProgressDialog | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """ツールバー・プレビュー・設定パネル・ステータスバーを構築する。"""
        toolbar = QToolBar("メイン操作", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for label, slot in [
            ("開く", self._open_file),
            ("検出", self._detect_regions),
            ("適用", self._apply_mosaic),
            ("保存", self._save_file),
        ]:
            action = toolbar.addAction(label)
            action.triggered.connect(slot)

        central = QWidget()
        self.setCentralWidget(central)
        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        splitter.setChildrenCollapsible(False)

        self._preview = PreviewCanvas()
        splitter.addWidget(self._preview)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(4, 4, 4, 4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        self._detector_panel = DetectorSettingsPanel()
        self._settings_panel = SettingsPanel()
        inner_layout.addWidget(self._detector_panel)
        inner_layout.addWidget(self._settings_panel)
        inner_layout.addStretch()
        scroll.setWidget(inner)
        right_layout.addWidget(scroll)
        right_container.setMinimumWidth(280)
        right_container.setMaximumWidth(320)
        splitter.addWidget(right_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("準備完了")

    def _open_file(self) -> None:
        """画像または動画ファイルを開いてプレビューに表示する。"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "ファイルを開く",
            "",
            "対応ファイル (*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.mp4 *.mov *.avi *.mkv);;"
            "画像 (*.png *.jpg *.jpeg *.bmp *.tiff *.webp);;"
            "動画 (*.mp4 *.mov *.avi *.mkv)",
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
                self._current_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                self._is_video = True
            else:
                raise ValueError("未対応のファイル形式です")

            self._preview.set_regions([])
            self._preview.set_image(self._current_image)
            self.statusBar().showMessage(f"ファイルを読み込みました: {path.name}")
        except Exception as exc:  # pragma: no cover - GUI 例外経路
            QMessageBox.critical(self, "読み込みエラー", str(exc))
            self.statusBar().showMessage("読み込みに失敗しました")

    def _save_file(self) -> None:
        """画像または動画を保存する。"""
        if self._current_path is None or self._current_image is None:
            QMessageBox.information(self, "情報", "先にファイルを開いてください。")
            return

        if self._is_video:
            ret = QMessageBox.question(
                self,
                "確認",
                "動画全体へモザイクを適用して保存します。\n時間がかかる場合があります。続行しますか？",
            )
            if ret == QMessageBox.StandardButton.Yes:
                self._save_video()
            return

        default_name = f"{self._current_path.stem}_mosaic.png"
        output, _ = QFileDialog.getSaveFileName(
            self,
            "画像を保存",
            default_name,
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp);;TIFF (*.tiff)",
        )
        if not output:
            return

        try:
            image_to_save = self._applied_image or self._apply_to_pil_image(
                self._current_image,
                self._preview.get_enabled_regions(),
                self._settings_panel.get_config(),
            )
            suffix = Path(output).suffix.lower()
            if suffix == ".png":
                ImageMedia.save_lossless(image_to_save, output)
            else:
                ImageMedia.save(image_to_save, output)
            self.statusBar().showMessage(f"保存しました: {Path(output).name}")
        except Exception as exc:  # pragma: no cover - GUI 例外経路
            QMessageBox.critical(self, "保存エラー", str(exc))
            self.statusBar().showMessage("保存に失敗しました")

    def _detect_regions(self) -> None:
        """DetectorSettingsPanel の設定で検出器を生成し、バックグラウンドで検出する。"""
        if self._current_image is None:
            QMessageBox.information(self, "情報", "先にファイルを開いてください。")
            return

        try:
            detector = self._detector_panel.get_detector()
        except Exception as exc:  # pragma: no cover - GUI 例外経路
            QMessageBox.critical(self, "検出器設定エラー", str(exc))
            return

        self.statusBar().showMessage("領域を検出しています...")
        self._detect_worker = _DetectWorker(detector, self._current_image, self)
        self._detect_worker.finished.connect(self._on_detect_finished)
        self._detect_worker.error.connect(self._on_detect_error)
        self._detect_worker.start()

    def _on_detect_finished(self, detected: list) -> None:
        self._preview.set_regions(detected)
        self.statusBar().showMessage(f"{len(detected)} 件の領域を検出しました")
        self._detect_worker = None

    def _on_detect_error(self, msg: str) -> None:  # pragma: no cover - GUI 例外経路
        QMessageBox.critical(self, "検出エラー", msg)
        self.statusBar().showMessage("領域検出に失敗しました")
        self._detect_worker = None

    def _apply_mosaic(self) -> None:
        """現在の設定と有効領域でプレビューへモザイクを適用する。"""
        if self._current_image is None:
            QMessageBox.information(self, "情報", "先にファイルを開いてください。")
            return

        config = self._settings_panel.get_config()
        regions = self._preview.get_enabled_regions()
        if not regions:
            QMessageBox.information(self, "情報", "適用対象の領域がありません。")
            return

        try:
            self._applied_image = self._apply_to_pil_image(self._current_image, regions, config)
            self._preview.set_image(self._applied_image)
            message = (
                "プレビューにモザイクを適用しました。保存時に動画全体へ反映されます。"
                if self._is_video
                else "画像へモザイクを適用しました。"
            )
            self.statusBar().showMessage(message)
        except Exception as exc:  # pragma: no cover - GUI 例外経路
            QMessageBox.critical(self, "適用エラー", str(exc))
            self.statusBar().showMessage("モザイク適用に失敗しました")

    def _save_video(self) -> None:
        """動画へフレーム単位でモザイクを適用して保存する。"""
        regions = self._preview.get_enabled_regions()
        if not regions:
            QMessageBox.information(self, "情報", "適用対象の領域がありません。")
            return

        default_name = f"{self._current_path.stem}_mosaic{self._current_path.suffix}"
        output, _ = QFileDialog.getSaveFileName(
            self,
            "動画を保存",
            default_name,
            "動画 (*.mp4 *.mov *.avi *.mkv)",
        )
        if not output:
            return

        config = self._settings_panel.get_config()
        progress = QProgressDialog("動画へモザイクを適用中...", "キャンセル", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        progress.show()
        self._progress_dialog = progress

        self._video_worker = _VideoSaveWorker(self._current_path, output, regions, config, self)
        self._video_worker.progress.connect(progress.setValue)
        self._video_worker.finished.connect(self._on_video_save_finished)
        self._video_worker.error.connect(self._on_video_save_error)
        progress.canceled.connect(self._video_worker.requestInterruption)
        self._video_worker.start()

    def _on_video_save_finished(self, path: str) -> None:
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None
        self.statusBar().showMessage(f"保存しました: {Path(path).name}")
        self._video_worker = None

    def _on_video_save_error(self, msg: str) -> None:  # pragma: no cover - GUI 例外経路
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None
        if msg == "動画保存がキャンセルされました":
            self.statusBar().showMessage(msg)
        else:
            QMessageBox.critical(self, "保存エラー", msg)
            self.statusBar().showMessage("保存に失敗しました")
        self._video_worker = None

    def _apply_to_pil_image(self, image: Image.Image, regions, config: MosaicConfig) -> Image.Image:
        """PIL Image へ複数領域のモザイクを順次適用する。"""
        array = np.array(image.convert("RGB"))
        for region in regions:
            array = self._engine.apply(array, (region.x, region.y, region.width, region.height), config)
        return Image.fromarray(array)
