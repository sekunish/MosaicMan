"""
detector.py - 領域検出モジュール

モザイク適用が推奨される領域を自動検出します。
以下の検出器を提供しており、用途に合わせて切り替えられます。

- HaarCascadeDetector : OpenCV Haar 分類器（ライセンス: Apache 2.0）。
                        オフライン・追加インストール不要で動作します。
- OllamaDetector      : ローカルで動作する LLM（llava / moondream など）。
                        ollama パッケージ（MIT）が必要です。
- OpenAIDetector      : OpenAI の Vision API（gpt-4o など）。
                        openai パッケージ（Apache 2.0）と API キーが必要です。

すべての検出器は BaseDetector を実装しており、 create_detector() で
文字列指定するだけで切り替えられます。

LLM 検出器では DetectionTarget で検出対象を選択できます。
"""

from __future__ import annotations

import base64
import enum
import io
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from PIL import Image

# ロガーはモジュール単位で取得する（GUI 側でハンドラを設定する）
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  オプション依存のガード付きインポート
#  uv add --optional ollama   または  uv add --optional openai  でインストール
# --------------------------------------------------------------------------- #
try:
    import ollama as _ollama_lib  # type: ignore[import-untyped]
    _OLLAMA_AVAILABLE = True
except ImportError:
    _OLLAMA_AVAILABLE = False

try:
    from openai import OpenAI as _OpenAI  # type: ignore[import-untyped]
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

# --------------------------------------------------------------------------- #
#  検出対象の種別
# --------------------------------------------------------------------------- #

class DetectionTarget(enum.Enum):
    """LLM 検出器で指定できる検出対象の種別。"""

    FACE = "face"
    """顔（正面・横顔・後頭部を含む）。"""

    PERSONAL_INFO = "personal_info"
    """個人を特定できる情報（名前・住所・電話番号・メールアドレスなど）。"""

    SENSITIVE = "sensitive"
    """センシティブな部位（身体の露出部位・医療情報など）。"""


#: 全検出対象のデフォルトセット
ALL_TARGETS: frozenset[DetectionTarget] = frozenset(DetectionTarget)

#: 各検出対象を日本語で説明する辞書（プロンプト生成に使用）
_TARGET_DESCRIPTIONS: dict[DetectionTarget, str] = {
    DetectionTarget.FACE: "顔",
    DetectionTarget.PERSONAL_INFO: "個人を特定できる情報（名前・住所・電話番号など）",
    DetectionTarget.SENSITIVE: "センシティブな部位",
}


# --------------------------------------------------------------------------- #
#  LLM へ送るプロンプト生成（日本語で記述し、JSON のみを要求する）
# --------------------------------------------------------------------------- #

def _build_detection_prompt(
    targets: frozenset[DetectionTarget] | None = None,
) -> str:
    """
    指定された検出対象に応じた LLM 用プロンプトを生成する。

    Parameters
    ----------
    targets:
        検出対象のセット。``None``（デフォルト指定）の場合、または空セットの場合は
        すべての対象を検出する。
    """
    if targets is None or not targets:
        targets = ALL_TARGETS

    # 定義順（enum 宣言順）で並べる
    descriptions = [
        _TARGET_DESCRIPTIONS[t] for t in DetectionTarget if t in targets
    ]
    target_str = "、".join(descriptions)

    return (
        f"この画像を分析し、モザイク処理が推奨される領域（{target_str}など）を"
        "すべて特定してください。\n"
        "検出した各領域を以下の JSON 形式のみで返してください。"
        "座標は画像の左上を原点(0,0)とするピクセル値です。説明文は不要です。\n"
        '[{"x": <左端X>, "y": <上端Y>, "width": <幅>, "height": <高さ>, '
        '"label": "<内容>", "confidence": <0.0〜1.0>}]\n'
        "領域が検出されない場合は空配列 [] を返してください。"
    )


# --------------------------------------------------------------------------- #
#  データクラス
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class DetectedRegion:
    """検出された推奨領域。"""

    x: int
    y: int
    width: int
    height: int
    label: str
    confidence: float


# --------------------------------------------------------------------------- #
#  共通ユーティリティ
# --------------------------------------------------------------------------- #

def _iou(left: DetectedRegion, right: DetectedRegion) -> float:
    """2 領域の Intersection over Union を計算する。"""
    x1 = max(left.x, right.x)
    y1 = max(left.y, right.y)
    x2 = min(left.x + left.width, right.x + right.width)
    y2 = min(left.y + left.height, right.y + right.height)
    if x1 >= x2 or y1 >= y2:
        return 0.0
    intersection = (x2 - x1) * (y2 - y1)
    union = left.width * left.height + right.width * right.height - intersection
    return intersection / union if union else 0.0


def _deduplicate(regions: list[DetectedRegion]) -> list[DetectedRegion]:
    """IoU が 0.3 を超える重複領域を除去する。"""
    unique: list[DetectedRegion] = []
    for region in regions:
        if any(_iou(region, existing) > 0.3 for existing in unique):
            continue
        unique.append(region)
    return unique


def _image_to_base64_png(image: np.ndarray) -> str:
    """RGB NumPy 配列を PNG の Base64 文字列に変換する。"""
    pil_image = Image.fromarray(image)
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _parse_llm_response(
    text: str,
    image_width: int,
    image_height: int,
) -> list[DetectedRegion]:
    """
    LLM のテキスト応答から DetectedRegion のリストを抽出する。

    LLM は必ずしも純粋な JSON だけを返すとは限らないため、
    1. テキスト全体を JSON としてパース
    2. 失敗した場合は正規表現で JSON 配列を検索
    という 2 段階フォールバックを行う。
    """
    candidates: list[Any] = []

    # まず全体を JSON としてパースを試みる
    try:
        parsed = json.loads(text.strip())
        if isinstance(parsed, list):
            candidates = parsed
    except json.JSONDecodeError:
        pass

    # パースできなかった場合は "[...]" 形式のブロックを探す
    if not candidates:
        match = re.search(r"\[.*?\]", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    candidates = parsed
            except json.JSONDecodeError:
                logger.warning("LLM 応答から JSON 配列を抽出できませんでした: %s", text[:200])

    regions: list[DetectedRegion] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        try:
            x = int(item.get("x", 0))
            y = int(item.get("y", 0))
            width = int(item.get("width", 0))
            height = int(item.get("height", 0))
            label = str(item.get("label", "detected"))
            confidence = float(item.get("confidence", 0.8))
            # 画像サイズの範囲内にクランプ
            x = max(0, min(x, image_width - 1))
            y = max(0, min(y, image_height - 1))
            width = max(1, min(width, image_width - x))
            height = max(1, min(height, image_height - y))
            confidence = max(0.0, min(1.0, confidence))
            regions.append(DetectedRegion(
                x=x,
                y=y,
                width=width,
                height=height,
                label=label,
                confidence=confidence,
            ))
        except (TypeError, ValueError) as exc:
            logger.debug("領域のパースに失敗しました: %s (%s)", item, exc)

    return regions


# --------------------------------------------------------------------------- #
#  抽象基底クラス
# --------------------------------------------------------------------------- #

class BaseDetector(ABC):
    """
    すべての検出器が実装すべき抽象基底クラス。

    detect() だけを実装すれば detect_from_pil() は自動的に動作します。
    """

    @abstractmethod
    def detect(self, image: np.ndarray) -> list[DetectedRegion]:
        """
        RGB NumPy 配列から推奨モザイク領域を返す。

        Parameters
        ----------
        image:
            H×W×3 の RGB 配列（dtype: uint8）。
        """

    def detect_from_pil(self, image: Image.Image) -> list[DetectedRegion]:
        """PIL Image から検出する（テンプレートメソッド）。"""
        return self.detect(np.array(image.convert("RGB")))


# --------------------------------------------------------------------------- #
#  Haar 分類器実装（ローカル・追加インストール不要）
# --------------------------------------------------------------------------- #

class HaarCascadeDetector(BaseDetector):
    """
    OpenCV の事前学習済み Haar 分類器を使用する検出器。

    ライセンス: Apache License 2.0（opencv-python パッケージ）。
    追加インストールは不要で、完全オフラインで動作します。
    正面顔・横顔の 2 種類を同時に検出します。
    """

    def __init__(self) -> None:
        """Haar 分類器ファイルを OpenCV バンドルからロードする。"""
        self._face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self._profile_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_profileface.xml"
        )

    def detect(self, image: np.ndarray) -> list[DetectedRegion]:
        """顔（正面・横顔）の検出領域リストを返す。"""
        if image.ndim == 2:
            gray = image
        elif image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            raise ValueError("image must be a 2D or 3D numpy array")

        regions: list[DetectedRegion] = []
        cascade_configs = [
            (self._face_cascade, "face", 0.9),
            (self._profile_cascade, "profile_face", 0.75),
        ]

        for cascade, label, confidence in cascade_configs:
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
                        x=int(x), y=int(y),
                        width=int(width), height=int(height),
                        label=label, confidence=float(confidence),
                    )
                )

        return _deduplicate(regions)


# --------------------------------------------------------------------------- #
#  Ollama 検出器（ローカル LLM）
# --------------------------------------------------------------------------- #

class OllamaDetector(BaseDetector):
    """
    ローカルで動作する Ollama の Vision モデルを使用する検出器。

    ライセンス: ollama Python パッケージは MIT License。
    事前に Ollama サーバーと Vision 対応モデル（llava, moondream など）の
    インストールが必要です。

    依存: uv add "mosaicman[llm]"  または  uv add ollama

    プライバシー: 画像データは指定したホスト上の Ollama にのみ送信されます。
    デフォルトはローカルホスト（http://localhost:11434）です。
    """

    def __init__(
        self,
        model: str = "llava",
        host: str = "http://localhost:11434",
        targets: frozenset[DetectionTarget] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        model:
            使用する Ollama モデル名（例: "llava", "moondream", "llava-phi3"）。
        host:
            Ollama サーバーの URL。
        targets:
            検出対象のセット。``None`` の場合はすべての対象（顔・個人情報・センシティブ）を検出する。
        """
        self._model = model
        self._host = host
        self._prompt = _build_detection_prompt(targets)

    def detect(self, image: np.ndarray) -> list[DetectedRegion]:
        """Ollama Vision モデルで推奨領域を検出する。"""
        if not _OLLAMA_AVAILABLE:
            raise ImportError(
                "ollama パッケージがインストールされていません。\n"
                "uv add 'mosaicman[llm]'  または  uv add ollama  を実行してください。"
            )

        image_height, image_width = image.shape[:2]
        image_b64 = _image_to_base64_png(image)

        logger.debug("Ollama 検出開始 (model=%s, host=%s)", self._model, self._host)
        client = _ollama_lib.Client(host=self._host)
        response = client.chat(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": self._prompt,
                    # ollama SDK は Base64 文字列を images フィールドで受け取る
                    "images": [image_b64],
                }
            ],
        )
        raw_text: str = response["message"]["content"]
        logger.debug("Ollama 応答: %s", raw_text[:300])

        regions = _parse_llm_response(raw_text, image_width, image_height)
        return _deduplicate(regions)


# --------------------------------------------------------------------------- #
#  OpenAI 検出器（クラウド LLM）
# --------------------------------------------------------------------------- #

class OpenAIDetector(BaseDetector):
    """
    OpenAI の Vision API を使用する検出器。

    ライセンス: openai Python パッケージは Apache License 2.0。
    API キーと通信環境が必要です。

    依存: uv add "mosaicman[llm]"  または  uv add openai

    プライバシー: 画像データが OpenAI のサーバーへ送信されます。
    機密性の高い素材を扱う場合は OllamaDetector の利用を検討してください。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        targets: frozenset[DetectionTarget] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        api_key:
            OpenAI API キー（sk-... 形式）。コード内やログに残さないこと。
        model:
            使用するモデル名（例: "gpt-4o", "gpt-4o-mini"）。
        targets:
            検出対象のセット。``None`` の場合はすべての対象（顔・個人情報・センシティブ）を検出する。
        """
        if not api_key:
            raise ValueError("OpenAI API キーが設定されていません。")
        self._api_key = api_key
        self._model = model
        self._prompt = _build_detection_prompt(targets)

    def detect(self, image: np.ndarray) -> list[DetectedRegion]:
        """OpenAI Vision API で推奨領域を検出する。"""
        if not _OPENAI_AVAILABLE:
            raise ImportError(
                "openai パッケージがインストールされていません。\n"
                "uv add 'mosaicman[llm]'  または  uv add openai  を実行してください。"
            )

        image_height, image_width = image.shape[:2]
        image_b64 = _image_to_base64_png(image)

        logger.debug("OpenAI 検出開始 (model=%s)", self._model)
        # API キーはログに出力しない
        client = _OpenAI(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            max_tokens=1024,
        )
        raw_text: str = response.choices[0].message.content or ""
        logger.debug("OpenAI 応答: %s", raw_text[:300])

        regions = _parse_llm_response(raw_text, image_width, image_height)
        return _deduplicate(regions)


# --------------------------------------------------------------------------- #
#  ファクトリ関数
# --------------------------------------------------------------------------- #

def create_detector(
    detector_type: str = "haar",
    *,
    targets: frozenset[DetectionTarget] | None = None,
    ollama_host: str = "http://localhost:11434",
    ollama_model: str = "llava",
    openai_api_key: str = "",
    openai_model: str = "gpt-4o",
) -> BaseDetector:
    """
    検出器を文字列指定で生成するファクトリ関数。

    Parameters
    ----------
    detector_type:
        "haar" | "ollama" | "openai"
    targets:
        LLM 検出器で使用する検出対象のセット。``None`` の場合はすべての対象を検出する。
        Haar 分類器では無視される。
    ollama_host:
        Ollama サーバーの URL（detector_type="ollama" 時に使用）。
    ollama_model:
        Ollama モデル名（detector_type="ollama" 時に使用）。
    openai_api_key:
        OpenAI API キー（detector_type="openai" 時に使用）。
    openai_model:
        OpenAI モデル名（detector_type="openai" 時に使用）。
    """
    if detector_type == "haar":
        return HaarCascadeDetector()
    if detector_type == "ollama":
        return OllamaDetector(model=ollama_model, host=ollama_host, targets=targets)
    if detector_type == "openai":
        return OpenAIDetector(api_key=openai_api_key, model=openai_model, targets=targets)
    raise ValueError(f"不明な検出器タイプです: {detector_type!r}。'haar' / 'ollama' / 'openai' から選択してください。")


# --------------------------------------------------------------------------- #
#  後方互換エイリアス
# --------------------------------------------------------------------------- #

#: v0.1.0 との後方互換性のためのエイリアス。新規コードでは HaarCascadeDetector を使ってください。
RegionDetector = HaarCascadeDetector
