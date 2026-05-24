"""メディア入出力とセキュリティユーティリティのテスト。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mosaicman.core.media import ImageMedia
from mosaicman.utils.security import clamp, sanitize_output_path, validate_file_path



def test_validate_file_path_valid(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (10, 10), color=(10, 20, 30)).save(image_path)
    assert validate_file_path(image_path, {".png"}) == image_path.resolve()



def test_validate_file_path_traversal(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    with pytest.raises(ValueError):
        validate_file_path(nested / ".." / "sample.png", {".png"})



def test_validate_file_path_unsupported_ext(tmp_path: Path) -> None:
    text_path = tmp_path / "sample.txt"
    text_path.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError):
        validate_file_path(text_path, {".png"})



def test_save_and_load_lossless(tmp_path: Path) -> None:
    image = Image.fromarray(np.array([[[0, 10, 20], [30, 40, 50]]], dtype=np.uint8), mode="RGB")
    output = tmp_path / "out.png"
    ImageMedia.save_lossless(image, output)
    loaded = ImageMedia.load(output)
    assert np.array_equal(np.array(image), np.array(loaded))



def test_clamp() -> None:
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(99, 0, 10) == 10



def test_sanitize_output_path(tmp_path: Path) -> None:
    output = sanitize_output_path("result.png", base_dir=tmp_path)
    assert output == (tmp_path / "result.png").resolve(strict=False)
