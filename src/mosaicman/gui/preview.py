"""
preview.py - プレビューキャンバスウィジェット

QGraphicsView ベースの画像プレビューと、モザイク適用領域の
選択・追加・削除をインタラクティブに行うウィジェット。

tkinter 版と比べてスムーズなズームや高 DPI 対応が可能です。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Signal, Qt
from PySide6.QtGui import QColor, QBrush, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QRubberBand,
    QSizePolicy,
    QWidget,
)


@dataclass
class Region:
    """モザイク適用領域。"""

    x: int
    y: int
    width: int
    height: int
    label: str = "custom"
    confidence: float = 1.0
    enabled: bool = True
    _rect_item: object = field(default=None, repr=False, compare=False)


def _clone_region(region: Region) -> Region:
    """GUI 管理情報を除外した Region のコピーを返す。"""
    return Region(
        x=region.x,
        y=region.y,
        width=region.width,
        height=region.height,
        label=region.label,
        confidence=region.confidence,
        enabled=region.enabled,
    )


def _pil_to_qpixmap(image: Image.Image) -> QPixmap:
    """PIL Image を QPixmap へ変換する。"""
    rgb = image.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


class PreviewCanvas(QGraphicsView):
    """
    画像プレビューとモザイク領域の選択・追加を行うウィジェット。

    シグナル:
        regions_changed(list[Region]): 領域が変更されたときに発行される
    """

    regions_changed = Signal(list)

    _COLOR_ENABLED = QColor(255, 77, 77, 180)
    _COLOR_DISABLED = QColor(158, 158, 158, 120)
    _PEN_ENABLED = QPen(QColor(255, 77, 77), 2)
    _PEN_DISABLED = QPen(QColor(158, 158, 158), 2)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._image: Image.Image | None = None
        self._pixmap_item = None
        self._regions: list[Region] = []
        self._drag_origin: QPointF | None = None
        self._rubber_band: QRubberBand | None = None
        self._pressed_region: Region | None = None

        self.setRenderHints(
            self.renderHints()
            | QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: #1e1e1e;")

    def set_image(self, image: Image.Image) -> None:
        """表示対象の PIL Image を設定する。"""
        self._image = image.copy()
        self._scene.clear()
        self._pixmap_item = None
        pixmap = _pil_to_qpixmap(self._image)
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        for region in self._regions:
            region._rect_item = None
        self._draw_regions()
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_regions(self, regions: list) -> None:
        """DetectedRegion 相当のオブジェクトリストを Region に変換して設定する。"""
        converted: list[Region] = []
        for region in regions:
            converted.append(
                Region(
                    x=int(region.x),
                    y=int(region.y),
                    width=int(region.width),
                    height=int(region.height),
                    label=getattr(region, "label", "custom"),
                    confidence=float(getattr(region, "confidence", 1.0)),
                    enabled=bool(getattr(region, "enabled", True)),
                )
            )
        self._regions = converted
        self._draw_regions()
        self.regions_changed.emit([_clone_region(region) for region in self._regions])

    def get_enabled_regions(self) -> list[Region]:
        """有効化されている領域のみ返す。"""
        return [_clone_region(region) for region in self._regions if region.enabled]

    def set_on_regions_changed(self, callback: Callable) -> None:
        """後方互換: regions_changed シグナルに callback を接続する。"""
        self.regions_changed.connect(callback)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._image is None:
            super().mousePressEvent(event)
            return
        self._drag_origin = event.position()
        self._pressed_region = self._region_at_scene_pos(
            self.mapToScene(int(event.position().x()), int(event.position().y()))
        )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_origin is None or self._image is None or self._pressed_region is not None:
            super().mouseMoveEvent(event)
            return
        origin = self._drag_origin
        if (event.position() - origin).manhattanLength() > 4:
            if self._rubber_band is None:
                self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())
            rect = QRect(
                QPoint(int(origin.x()), int(origin.y())),
                QPoint(int(event.position().x()), int(event.position().y())),
            ).normalized()
            self._rubber_band.setGeometry(rect)
            self._rubber_band.show()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._drag_origin is None:
            super().mouseReleaseEvent(event)
            return

        origin = self._drag_origin
        end = event.position()
        dragged = (end - origin).manhattanLength() > 4

        if self._rubber_band is not None:
            self._rubber_band.hide()

        if dragged and self._pressed_region is None and self._image is not None:
            scene_start = self.mapToScene(int(origin.x()), int(origin.y()))
            scene_end = self.mapToScene(int(end.x()), int(end.y()))
            sx = min(scene_start.x(), scene_end.x())
            sy = min(scene_start.y(), scene_end.y())
            ex = max(scene_start.x(), scene_end.x())
            ey = max(scene_start.y(), scene_end.y())
            x1, y1, x2, y2 = self._clamp_scene_rect_to_image(sx, sy, ex, ey)
            width = x2 - x1
            height = y2 - y1
            if width >= 3 and height >= 3:
                region = Region(x=x1, y=y1, width=width, height=height, label="custom", confidence=1.0)
                self._regions.append(region)
                self._draw_region(region)
                self.regions_changed.emit([_clone_region(item) for item in self._regions])
        elif not dragged and self._pressed_region is not None:
            self._pressed_region.enabled = not self._pressed_region.enabled
            self._update_region_appearance(self._pressed_region)
            self.regions_changed.emit([_clone_region(region) for region in self._regions])

        self._drag_origin = None
        self._pressed_region = None
        self._rubber_band = None
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        """ウィンドウリサイズ時に画像をアスペクト比維持でフィットさせる。"""
        super().resizeEvent(event)
        if self._scene.sceneRect().isValid():
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _region_at_scene_pos(self, scene_pos: QPointF) -> Region | None:
        """シーン座標に存在する領域を上面から検索する。"""
        for region in reversed(self._regions):
            if (
                region.x <= scene_pos.x() <= region.x + region.width
                and region.y <= scene_pos.y() <= region.y + region.height
            ):
                return region
        return None

    def _clamp_scene_rect_to_image(self, sx: float, sy: float, ex: float, ey: float) -> tuple[int, int, int, int]:
        """シーン矩形を画像内ピクセル座標へクランプする。"""
        assert self._image is not None
        img_w, img_h = self._image.size
        x1 = max(0, min(int(sx), img_w))
        y1 = max(0, min(int(sy), img_h))
        x2 = max(0, min(int(ex), img_w))
        y2 = max(0, min(int(ey), img_h))
        return x1, y1, x2, y2

    def _draw_regions(self) -> None:
        """全領域を再描画する。"""
        for region in self._regions:
            if region._rect_item is not None:
                try:
                    self._scene.removeItem(region._rect_item)
                except RuntimeError:
                    pass
                region._rect_item = None
        for region in self._regions:
            self._draw_region(region)

    def _draw_region(self, region: Region) -> None:
        """単一領域を QGraphicsRectItem としてシーンへ追加する。"""
        if self._image is None:
            return
        pen = self._PEN_ENABLED if region.enabled else self._PEN_DISABLED
        brush_color = self._COLOR_ENABLED if region.enabled else self._COLOR_DISABLED
        item = self._scene.addRect(
            QRectF(region.x, region.y, region.width, region.height),
            pen,
            QBrush(brush_color),
        )
        item.setToolTip(f"{region.label} ({region.confidence:.2f})")
        region._rect_item = item

    def _update_region_appearance(self, region: Region) -> None:
        """既存の QGraphicsRectItem の表示状態を更新する。"""
        if region._rect_item is None:
            self._draw_region(region)
            return
        pen = self._PEN_ENABLED if region.enabled else self._PEN_DISABLED
        brush_color = self._COLOR_ENABLED if region.enabled else self._COLOR_DISABLED
        region._rect_item.setPen(pen)
        region._rect_item.setBrush(QBrush(brush_color))
