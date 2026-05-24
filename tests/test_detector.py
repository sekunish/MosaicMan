"""領域検出モジュールのテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from mosaicman.core.detector import (
    BaseDetector,
    DetectedRegion,
    HaarCascadeDetector,
    OllamaDetector,
    OpenAIDetector,
    RegionDetector,
    _deduplicate,
    _iou,
    _parse_llm_response,
    create_detector,
)


# --------------------------------------------------------------------------- #
#  DetectedRegion / 基本ユーティリティ
# --------------------------------------------------------------------------- #

def test_detected_region_fields() -> None:
    region = DetectedRegion(x=1, y=2, width=3, height=4, label="face", confidence=0.9)
    assert (region.x, region.y, region.width, region.height) == (1, 2, 3, 4)
    assert region.label == "face"
    assert region.confidence == 0.9


def test_iou_no_overlap() -> None:
    a = DetectedRegion(0, 0, 10, 10, "a", 1.0)
    b = DetectedRegion(20, 20, 10, 10, "b", 1.0)
    assert _iou(a, b) == 0.0


def test_iou_full_overlap() -> None:
    a = DetectedRegion(0, 0, 10, 10, "a", 1.0)
    assert _iou(a, a) == 1.0


def test_deduplicate_removes_high_iou() -> None:
    a = DetectedRegion(0, 0, 100, 100, "a", 1.0)
    b = DetectedRegion(1, 1, 100, 100, "b", 0.9)  # ほぼ同じ領域
    result = _deduplicate([a, b])
    assert len(result) == 1


# --------------------------------------------------------------------------- #
#  LLM 応答パーサー
# --------------------------------------------------------------------------- #

def test_parse_llm_response_valid_json() -> None:
    text = '[{"x": 10, "y": 20, "width": 50, "height": 60, "label": "face", "confidence": 0.9}]'
    regions = _parse_llm_response(text, 200, 200)
    assert len(regions) == 1
    assert regions[0].x == 10
    assert regions[0].label == "face"


def test_parse_llm_response_embedded_json() -> None:
    """LLM が説明文とともに JSON を返した場合でも抽出できる。"""
    text = '以下の領域を検出しました。\n[{"x": 5, "y": 5, "width": 30, "height": 30, "label": "face", "confidence": 0.8}]\n以上です。'
    regions = _parse_llm_response(text, 100, 100)
    assert len(regions) == 1


def test_parse_llm_response_empty_array() -> None:
    regions = _parse_llm_response("[]", 100, 100)
    assert regions == []


def test_parse_llm_response_out_of_bounds_clamped() -> None:
    """画像サイズを超えた座標はクランプされる。"""
    text = '[{"x": -10, "y": -5, "width": 500, "height": 500, "label": "body", "confidence": 0.7}]'
    regions = _parse_llm_response(text, 100, 100)
    assert len(regions) == 1
    assert regions[0].x == 0
    assert regions[0].y == 0
    assert regions[0].width <= 100
    assert regions[0].height <= 100


def test_parse_llm_response_invalid_text() -> None:
    """JSON がまったく含まれない場合は空リストを返す。"""
    regions = _parse_llm_response("申し訳ありません、検出できませんでした。", 100, 100)
    assert regions == []


# --------------------------------------------------------------------------- #
#  HaarCascadeDetector（旧 RegionDetector エイリアス含む）
# --------------------------------------------------------------------------- #

def test_haar_detect_returns_list(sample_image_rgb) -> None:
    detector = HaarCascadeDetector()
    detected = detector.detect(sample_image_rgb)
    assert isinstance(detected, list)


def test_haar_detect_no_face() -> None:
    detector = HaarCascadeDetector()
    blank = np.zeros((200, 200, 3), dtype=np.uint8)
    detected = detector.detect(blank)
    assert isinstance(detected, list)
    assert all(isinstance(item, DetectedRegion) for item in detected)


def test_haar_detect_from_pil(sample_pil_image) -> None:
    detector = HaarCascadeDetector()
    detected = detector.detect_from_pil(sample_pil_image)
    assert isinstance(detected, list)


def test_region_detector_alias(sample_image_rgb) -> None:
    """RegionDetector が HaarCascadeDetector の後方互換エイリアスであることを確認する。"""
    assert RegionDetector is HaarCascadeDetector
    detector = RegionDetector()
    assert isinstance(detector, BaseDetector)
    detected = detector.detect(sample_image_rgb)
    assert isinstance(detected, list)


# --------------------------------------------------------------------------- #
#  create_detector ファクトリ
# --------------------------------------------------------------------------- #

def test_create_detector_haar() -> None:
    detector = create_detector("haar")
    assert isinstance(detector, HaarCascadeDetector)


def test_create_detector_unknown_raises() -> None:
    import pytest
    with pytest.raises(ValueError, match="不明な検出器タイプ"):
        create_detector("unknown_type")


def test_create_detector_ollama_instance() -> None:
    """ollama パッケージ未インストールでも OllamaDetector インスタンスは生成できる。"""
    detector = create_detector("ollama", ollama_model="llava", ollama_host="http://localhost:11434")
    assert isinstance(detector, OllamaDetector)


def test_create_detector_openai_raises_without_key() -> None:
    """API キーなしで OpenAIDetector を生成しようとすると ValueError が発生する。"""
    import pytest
    with pytest.raises(ValueError, match="API キー"):
        create_detector("openai", openai_api_key="")


# --------------------------------------------------------------------------- #
#  OllamaDetector（モック）
# --------------------------------------------------------------------------- #

def test_ollama_detector_not_installed_raises(sample_image_rgb) -> None:
    """ollama パッケージが存在しない環境では ImportError が発生する。"""
    import mosaicman.core.detector as det_mod
    original = det_mod._OLLAMA_AVAILABLE
    try:
        det_mod._OLLAMA_AVAILABLE = False
        detector = OllamaDetector(model="llava")
        import pytest
        with pytest.raises(ImportError, match="ollama"):
            detector.detect(sample_image_rgb)
    finally:
        det_mod._OLLAMA_AVAILABLE = original


def test_ollama_detector_with_mock(sample_image_rgb) -> None:
    """Ollama サーバーのレスポンスをモックして OllamaDetector の動作を検証する。"""
    import mosaicman.core.detector as det_mod
    original = det_mod._OLLAMA_AVAILABLE
    mock_lib = MagicMock()
    mock_client = MagicMock()
    mock_lib.Client.return_value = mock_client
    mock_client.chat.return_value = {
        "message": {
            "content": '[{"x": 10, "y": 10, "width": 40, "height": 40, "label": "face", "confidence": 0.85}]'
        }
    }
    try:
        det_mod._OLLAMA_AVAILABLE = True
        det_mod._ollama_lib = mock_lib
        detector = OllamaDetector(model="llava")
        regions = detector.detect(sample_image_rgb)
        assert isinstance(regions, list)
        assert len(regions) == 1
        assert regions[0].label == "face"
    finally:
        det_mod._OLLAMA_AVAILABLE = original


# --------------------------------------------------------------------------- #
#  OpenAIDetector（モック）
# --------------------------------------------------------------------------- #

def test_openai_detector_not_installed_raises(sample_image_rgb) -> None:
    """openai パッケージが存在しない環境では ImportError が発生する。"""
    import mosaicman.core.detector as det_mod
    original = det_mod._OPENAI_AVAILABLE
    try:
        det_mod._OPENAI_AVAILABLE = False
        detector = OpenAIDetector(api_key="sk-test")
        import pytest
        with pytest.raises(ImportError, match="openai"):
            detector.detect(sample_image_rgb)
    finally:
        det_mod._OPENAI_AVAILABLE = original


def test_openai_detector_with_mock(sample_image_rgb) -> None:
    """OpenAI クライアントをモックして OpenAIDetector の動作を検証する。"""
    import mosaicman.core.detector as det_mod
    original = det_mod._OPENAI_AVAILABLE
    mock_openai_cls = MagicMock()
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.choices[0].message.content = (
        '[{"x": 20, "y": 30, "width": 50, "height": 60, "label": "face", "confidence": 0.9}]'
    )
    mock_client.chat.completions.create.return_value = mock_response
    try:
        det_mod._OPENAI_AVAILABLE = True
        det_mod._OpenAI = mock_openai_cls
        detector = OpenAIDetector(api_key="sk-test", model="gpt-4o")
        regions = detector.detect(sample_image_rgb)
        assert isinstance(regions, list)
        assert len(regions) == 1
        assert regions[0].width == 50
    finally:
        det_mod._OPENAI_AVAILABLE = original
