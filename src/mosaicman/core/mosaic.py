"""
mosaic.py - モザイク効果エンジン

画像領域に対して各種モザイク効果を適用するモジュール。
高い再利用性を持ち、GUI・バッチ処理どちらからも利用できます。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


class MosaicType(enum.Enum):
    """サポートするモザイク表現種別。"""

    PIXELATE = "pixelate"
    BLUR = "blur"
    BLACK_BARS = "black_bars"


@dataclass(slots=True)
class MosaicConfig:
    """モザイク設定。"""

    mosaic_type: MosaicType = MosaicType.PIXELATE
    block_size: int = 15
    blur_radius: int = 21
    bar_count: int = 5
    bar_angle: float = 0.0
    bar_opacity: float = 1.0


class MosaicEngine:
    """モザイク効果を適用するエンジンクラス。"""

    def apply(
        self,
        image: np.ndarray,
        region: tuple[int, int, int, int],
        config: MosaicConfig,
    ) -> np.ndarray:
        """
        指定領域にモザイクを適用する。

        Parameters
        ----------
        image:
            入力画像。2 次元グレースケール、または 3 次元カラー配列を想定する。
        region:
            (x, y, width, height) 形式の領域。
        config:
            適用するモザイク設定。
        """
        if image.ndim not in (2, 3):
            raise ValueError("image must be a 2D or 3D numpy array")

        height, width = image.shape[:2]
        x, y, region_width, region_height = region

        # 領域は GUI 操作や自動検出により画像外にはみ出す可能性があるため、
        # ここで必ず画像サイズに合わせて安全にクランプする。
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(width, x + max(0, region_width))
        y2 = min(height, y + max(0, region_height))

        if x1 >= x2 or y1 >= y2:
            return image.copy()

        result = image.copy()
        roi = result[y1:y2, x1:x2].copy()

        if config.mosaic_type is MosaicType.PIXELATE:
            processed = self._pixelate(roi, config.block_size)
        elif config.mosaic_type is MosaicType.BLUR:
            processed = self._blur(roi, config.blur_radius)
        elif config.mosaic_type is MosaicType.BLACK_BARS:
            processed = self._black_bars(roi, config.bar_count, config.bar_angle, config.bar_opacity)
        else:
            raise ValueError(f"Unsupported mosaic type: {config.mosaic_type}")

        result[y1:y2, x1:x2] = processed
        return result

    def _pixelate(self, roi: np.ndarray, block_size: int) -> np.ndarray:
        """
        ROI をピクセル化する。

        OpenCV の縮小→拡大を使うことで、単純かつ高速にモザイク表現を作る。
        縮小時は INTER_AREA を使って情報を平均化し、拡大時は INTER_NEAREST を使って
        ブロック境界をくっきり残す。
        """
        if roi.size == 0:
            return roi.copy()

        h, w = roi.shape[:2]
        safe_block_size = max(1, int(block_size))
        reduced_w = max(1, w // safe_block_size)
        reduced_h = max(1, h // safe_block_size)

        reduced = cv2.resize(roi, (reduced_w, reduced_h), interpolation=cv2.INTER_AREA)
        return cv2.resize(reduced, (w, h), interpolation=cv2.INTER_NEAREST)

    def _blur(self, roi: np.ndarray, radius: int) -> np.ndarray:
        """ROI にガウシアンぼかしを適用する。"""
        if roi.size == 0:
            return roi.copy()

        # GaussianBlur のカーネルサイズは奇数必須のため、偶数なら 1 加算する。
        safe_radius = max(1, int(radius))
        if safe_radius % 2 == 0:
            safe_radius += 1
        return cv2.GaussianBlur(roi, (safe_radius, safe_radius), sigmaX=0)

    def _black_bars(self, roi: np.ndarray, count: int, angle: float, opacity: float) -> np.ndarray:
        """
        ROI に黒帯を重ねる。

        まず ROI 全体に対して水平な帯マスクを作り、その後で指定角度だけ回転する。
        実画像へはアルファ合成を行うため、不透明度を柔軟に調整できる。
        """
        if roi.size == 0:
            return roi.copy()

        h, w = roi.shape[:2]
        safe_count = max(1, int(count))
        safe_opacity = float(min(1.0, max(0.0, opacity)))

        bar_mask = np.zeros((h, w), dtype=np.uint8)
        spacing = h / safe_count
        thickness = max(1, int(round(spacing / 2.0)))

        for index in range(safe_count):
            center_y = int(round((index + 0.5) * spacing))
            top = max(0, center_y - thickness // 2)
            bottom = min(h, top + thickness)
            cv2.rectangle(bar_mask, (0, top), (w, max(top, bottom - 1)), color=255, thickness=-1)

        if angle % 180:
            rotation = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
            bar_mask = cv2.warpAffine(
                bar_mask,
                rotation,
                (w, h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            )

        alpha = (bar_mask.astype(np.float32) / 255.0) * safe_opacity
        if roi.ndim == 3:
            alpha = alpha[..., None]

        # 黒帯は「黒を重ねる」処理なので、元画像に (1 - alpha) を乗じるだけでよい。
        blended = roi.astype(np.float32) * (1.0 - alpha)
        return np.clip(blended, 0, 255).astype(roi.dtype)

    def apply_to_pil(
        self,
        image: Image.Image,
        region: tuple[int, int, int, int],
        config: MosaicConfig,
    ) -> Image.Image:
        """PIL Image に対して指定領域へモザイクを適用する。"""
        source = np.array(image.convert("RGB"))
        processed = self.apply(source, region, config)
        return Image.fromarray(processed)
