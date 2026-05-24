"""モザイクエンジンのテスト。"""

from __future__ import annotations

import numpy as np

from mosaicman.core.mosaic import MosaicConfig, MosaicEngine, MosaicType


def _checkerboard(size: int = 64) -> np.ndarray:
    grid = np.indices((size, size)).sum(axis=0) % 2
    image = (grid * 255).astype(np.uint8)
    return np.stack([image, np.roll(image, 1, axis=0), np.roll(image, 1, axis=1)], axis=-1)



def test_pixelate_changes_roi() -> None:
    engine = MosaicEngine()
    image = _checkerboard(80)
    result = engine.apply(image, (10, 10, 50, 50), MosaicConfig(mosaic_type=MosaicType.PIXELATE, block_size=8))
    assert not np.array_equal(result[10:60, 10:60], image[10:60, 10:60])



def test_blur_changes_roi() -> None:
    engine = MosaicEngine()
    image = _checkerboard(80)
    result = engine.apply(image, (5, 5, 60, 60), MosaicConfig(mosaic_type=MosaicType.BLUR, blur_radius=9))
    assert not np.array_equal(result[5:65, 5:65], image[5:65, 5:65])



def test_black_bars_changes_roi(sample_image_rgb) -> None:
    engine = MosaicEngine()
    result = engine.apply(sample_image_rgb, (40, 40, 120, 120), MosaicConfig(mosaic_type=MosaicType.BLACK_BARS, bar_count=4, bar_opacity=1.0))
    assert np.any(np.all(result[40:160, 40:160] == 0, axis=-1))



def test_apply_region_bounds(sample_image_rgb) -> None:
    engine = MosaicEngine()
    result = engine.apply(sample_image_rgb, (-20, -10, 500, 500), MosaicConfig())
    assert result.shape == sample_image_rgb.shape



def test_apply_to_pil(sample_pil_image) -> None:
    engine = MosaicEngine()
    result = engine.apply_to_pil(sample_pil_image, (20, 20, 100, 100), MosaicConfig(mosaic_type=MosaicType.BLACK_BARS))
    assert isinstance(result.size, tuple)
    assert result.getpixel((30, 30)) != sample_pil_image.getpixel((30, 30))



def test_all_types(sample_image_rgb) -> None:
    engine = MosaicEngine()
    for mosaic_type in MosaicType:
        result = engine.apply(sample_image_rgb, (10, 10, 100, 100), MosaicConfig(mosaic_type=mosaic_type))
        assert result.shape == sample_image_rgb.shape



def test_config_defaults() -> None:
    config = MosaicConfig()
    assert config.mosaic_type is MosaicType.PIXELATE
    assert config.block_size == 15
    assert config.blur_radius == 21
    assert config.bar_count == 5
    assert config.bar_angle == 0.0
    assert config.bar_opacity == 1.0



def test_block_size_1(sample_image_rgb) -> None:
    engine = MosaicEngine()
    result = engine.apply(sample_image_rgb, (20, 20, 50, 50), MosaicConfig(block_size=1))
    assert result.shape == sample_image_rgb.shape
