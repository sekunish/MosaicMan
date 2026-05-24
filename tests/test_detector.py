"""領域検出モジュールのテスト。"""

from __future__ import annotations

import numpy as np

from mosaicman.core.detector import DetectedRegion, RegionDetector



def test_detect_returns_list(sample_image_rgb) -> None:
    detector = RegionDetector()
    detected = detector.detect(sample_image_rgb)
    assert isinstance(detected, list)



def test_detect_no_face() -> None:
    detector = RegionDetector()
    blank = np.zeros((200, 200, 3), dtype=np.uint8)
    detected = detector.detect(blank)
    assert isinstance(detected, list)
    assert all(isinstance(item, DetectedRegion) for item in detected)



def test_detected_region_fields() -> None:
    region = DetectedRegion(x=1, y=2, width=3, height=4, label="face", confidence=0.9)
    assert (region.x, region.y, region.width, region.height) == (1, 2, 3, 4)
    assert region.label == "face"
    assert region.confidence == 0.9



def test_detect_from_pil(sample_pil_image) -> None:
    detector = RegionDetector()
    detected = detector.detect_from_pil(sample_pil_image)
    assert isinstance(detected, list)
