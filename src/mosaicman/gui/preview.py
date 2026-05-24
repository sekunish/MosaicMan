"""
preview.py - プレビューキャンバスウィジェット

画像のプレビュー表示と、モザイク適用領域の選択・追加・削除を
インタラクティブに行うための tkinter キャンバスウィジェット。
"""

from __future__ import annotations

import copy
import tkinter as tk
from dataclasses import dataclass

from PIL import Image, ImageTk


@dataclass(slots=True)
class Region:
    """モザイク適用領域。"""

    x: int
    y: int
    width: int
    height: int
    label: str = "custom"
    confidence: float = 1.0
    enabled: bool = True
    rect_id: int = -1


class PreviewCanvas(tk.Canvas):
    """
    画像プレビューとモザイク領域の選択を行うキャンバス。
    - 領域をクリックして有効/無効を切り替え
    - ドラッグで新しい領域を追加
    - 画像はアスペクト比を維持してリサイズ
    """

    def __init__(self, parent: tk.Misc, **kwargs: object) -> None:
        """キャンバス内部状態を初期化する。"""
        super().__init__(parent, highlightthickness=0, background="#1e1e1e", **kwargs)
        self._image: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._regions: list[Region] = []
        self._scale_x: float = 1.0
        self._scale_y: float = 1.0
        self._offset_x: int = 0
        self._offset_y: int = 0
        self._drag_start: tuple[int, int] | None = None
        self._drag_rect_id: int | None = None
        self._on_regions_changed = None
        self._bind_events()

    def set_image(self, image: Image.Image) -> None:
        """表示対象画像を設定する。"""
        self._image = image.copy()
        self._redraw()

    def set_regions(self, regions: list) -> None:
        """DetectedRegion 相当のリストを Region に変換して設定する。"""
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
        self._redraw()
        self._notify_regions_changed()

    def get_enabled_regions(self) -> list[Region]:
        """有効化されている領域のみ返す。"""
        return [copy.deepcopy(region) for region in self._regions if region.enabled]

    def set_on_regions_changed(self, callback) -> None:
        """領域更新時のコールバックを設定する。"""
        self._on_regions_changed = callback

    def _bind_events(self) -> None:
        """マウス操作とリサイズイベントを関連付ける。"""
        self.bind("<ButtonPress-1>", self._on_drag_start)
        self.bind("<B1-Motion>", self._on_drag_move)
        self.bind("<ButtonRelease-1>", self._on_drag_end)
        self.bind("<Configure>", lambda _event: self._redraw())

    def _on_click(self, event) -> None:
        """クリック位置の領域を有効/無効トグルする。"""
        image_coords = self._canvas_to_image_coords(event.x, event.y)
        if image_coords is None:
            return
        ix, iy = image_coords
        for region in reversed(self._regions):
            if region.x <= ix <= region.x + region.width and region.y <= iy <= region.y + region.height:
                region.enabled = not region.enabled
                self._redraw()
                self._notify_regions_changed()
                return

    def _on_drag_start(self, event) -> None:
        """ドラッグ開始座標を記録する。"""
        if self._image is None:
            return
        self._drag_start = (event.x, event.y)
        self._drag_rect_id = None

    def _on_drag_move(self, event) -> None:
        """ドラッグ中の仮領域を描画する。"""
        if self._image is None or self._drag_start is None:
            return
        start_x, start_y = self._drag_start
        if abs(event.x - start_x) < 4 and abs(event.y - start_y) < 4:
            return
        if self._drag_rect_id is None:
            self._drag_rect_id = self.create_rectangle(
                start_x,
                start_y,
                event.x,
                event.y,
                outline="#00ffff",
                dash=(4, 2),
                width=2,
            )
        else:
            self.coords(self._drag_rect_id, start_x, start_y, event.x, event.y)

    def _on_drag_end(self, event) -> None:
        """クリックまたは新規領域確定を処理する。"""
        if self._image is None or self._drag_start is None:
            return

        start_x, start_y = self._drag_start
        dragged = self._drag_rect_id is not None
        if dragged:
            start_image = self._canvas_to_image_coords(start_x, start_y)
            end_image = self._canvas_to_image_coords(event.x, event.y)
            if start_image and end_image:
                x1, y1 = start_image
                x2, y2 = end_image
                width = abs(x2 - x1)
                height = abs(y2 - y1)
                if width >= 3 and height >= 3:
                    self._regions.append(
                        Region(
                            x=min(x1, x2),
                            y=min(y1, y2),
                            width=width,
                            height=height,
                            label="custom",
                            confidence=1.0,
                            enabled=True,
                        )
                    )
                    self._notify_regions_changed()
        else:
            self._on_click(event)

        if self._drag_rect_id is not None:
            self.delete(self._drag_rect_id)
        self._drag_start = None
        self._drag_rect_id = None
        self._redraw()

    def _redraw(self) -> None:
        """画像と領域オーバーレイを再描画する。"""
        self.delete("all")
        if self._image is None:
            return

        canvas_width = max(1, self.winfo_width())
        canvas_height = max(1, self.winfo_height())
        image_width, image_height = self._image.size
        scale = min(canvas_width / image_width, canvas_height / image_height)
        scale = max(scale, 0.01)
        display_width = max(1, int(image_width * scale))
        display_height = max(1, int(image_height * scale))

        self._scale_x = image_width / display_width
        self._scale_y = image_height / display_height
        self._offset_x = (canvas_width - display_width) // 2
        self._offset_y = (canvas_height - display_height) // 2

        display_image = self._image.resize((display_width, display_height), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(display_image)
        self.create_image(self._offset_x, self._offset_y, anchor=tk.NW, image=self._photo)
        self._draw_regions()

    def _canvas_to_image_coords(self, cx: int, cy: int) -> tuple[int, int] | None:
        """キャンバス座標を元画像座標へ変換する。"""
        if self._image is None:
            return None
        ix = int((cx - self._offset_x) * self._scale_x)
        iy = int((cy - self._offset_y) * self._scale_y)
        width, height = self._image.size
        if not (0 <= ix < width and 0 <= iy < height):
            return None
        return ix, iy

    def _image_to_canvas_coords(self, ix: int, iy: int) -> tuple[int, int]:
        """元画像座標をキャンバス座標へ変換する。"""
        return int(ix / self._scale_x) + self._offset_x, int(iy / self._scale_y) + self._offset_y

    def _draw_regions(self) -> None:
        """領域枠とラベルを描画する。"""
        for region in self._regions:
            x1, y1 = self._image_to_canvas_coords(region.x, region.y)
            x2, y2 = self._image_to_canvas_coords(region.x + region.width, region.y + region.height)
            color = "#ff4d4d" if region.enabled else "#9e9e9e"
            region.rect_id = int(
                self.create_rectangle(x1, y1, x2, y2, outline=color, width=2)
            )
            self.create_text(
                x1 + 4,
                max(12, y1 + 12),
                anchor=tk.W,
                fill=color,
                text=f"{region.label} ({region.confidence:.2f})",
            )

    def _notify_regions_changed(self) -> None:
        """登録済みコールバックへ変更通知を行う。"""
        if self._on_regions_changed is not None:
            self._on_regions_changed([copy.deepcopy(region) for region in self._regions])
