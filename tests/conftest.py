"""テスト共通フィクスチャ。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def sample_image_rgb() -> np.ndarray:
    """テスト用 RGB 画像 (200x200)。"""
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    img[50:150, 50:150] = [255, 0, 0]
    return img


@pytest.fixture
def sample_pil_image() -> Image.Image:
    """テスト用 PIL Image。"""
    return Image.new("RGB", (200, 200), color=(128, 128, 128))
