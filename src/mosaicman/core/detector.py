"""
detector.py - 領域検出モジュール

OpenCV の DNN / Haar 分類器を用いて、
モザイク適用が推奨される領域を自動検出します。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass(slots=True)
class DetectedRegion:
    """検出された推奨領域。"""

    x: int
    y: int
    width: int
    height: int
    label: str
    confidence: float


class RegionDetector:
    """顔・身体領域を検出するクラス。"""

    def __init__(self) -> None:
        """OpenCV の事前学習済み Haar 分類器をロードする。"""
        self._face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self._profile_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_profileface.xml"
        )

    def detect(self, image: np.ndarray) -> list[DetectedRegion]:
        """画像から検出領域リストを返す。"""
        if image.ndim == 2:
            gray = image
        elif image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            raise ValueError("image must be a 2D or 3D numpy array")

        regions: list[DetectedRegion] = []
        detector_configs = [
            (self._face_cascade, "face", 0.9),
            (self._profile_cascade, "profile_face", 0.75),
        ]

        for cascade, label, confidence in detector_configs:
            if cascade.empty():
                continue
            detected = cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30),
            )
            for x, y, width, height in detected:
                regions.append(
                    DetectedRegion(
                        x=int(x),
                        y=int(y),
                        width=int(width),
                        height=int(height),
                        label=label,
                        confidence=float(confidence),
                    )
                )

        return self._deduplicate(regions)

    def detect_from_pil(self, image: Image.Image) -> list[DetectedRegion]:
        """PIL Image から検出する。"""
        return self.detect(np.array(image.convert("RGB")))

    def _deduplicate(self, regions: list[DetectedRegion]) -> list[DetectedRegion]:
        """重複の大きい検出結果を単純に統合する。"""
        unique: list[DetectedRegion] = []
        for region in regions:
            if any(self._iou(region, existing) > 0.3 for existing in unique):
                continue
            unique.append(region)
        return unique

    @staticmethod
    def _iou(left: DetectedRegion, right: DetectedRegion) -> float:
        """2 領域の IoU を計算する。"""
        x1 = max(left.x, right.x)
        y1 = max(left.y, right.y)
        x2 = min(left.x + left.width, right.x + right.width)
        y2 = min(left.y + left.height, right.y + right.height)
        if x1 >= x2 or y1 >= y2:
            return 0.0
        intersection = (x2 - x1) * (y2 - y1)
        left_area = left.width * left.height
        right_area = right.width * right.height
        union = left_area + right_area - intersection
        return intersection / union if union else 0.0
