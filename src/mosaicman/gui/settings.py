"""
settings.py - モザイク設定パネル / 検出器設定パネル（PySide6 版）

モザイクの種類・ブロックサイズ・ぼかし半径・黒帯設定などを
PySide6 ウィジェットで設定するパネル（SettingsPanel）と、
検出器の種類・接続先・API キー・検出対象を設定するパネル（DetectorSettingsPanel）を提供します。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..core.detector import ALL_TARGETS, BaseDetector, DetectionTarget, create_detector
from ..core.mosaic import MosaicConfig, MosaicType


class _LabeledSlider(QWidget):
    """スライダーと現在値ラベルを横並びにした複合ウィジェット。"""

    def __init__(self, min_val: int, max_val: int, step: int = 1, parent=None) -> None:
        super().__init__(parent)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(min_val, max_val)
        self._slider.setSingleStep(step)
        self._slider.setPageStep(step)
        self._slider.setTickInterval(step)
        self._label = QLabel()
        self._slider.valueChanged.connect(lambda value: self._label.setText(str(value)))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._slider)
        layout.addWidget(self._label)
        self._label.setFixedWidth(40)
        self._label.setText(str(self._slider.value()))

    def value(self) -> int:
        return self._slider.value()

    def setValue(self, value: int) -> None:
        self._slider.setValue(value)

    def valueChanged(self):
        return self._slider.valueChanged


class SettingsPanel(QGroupBox):
    """
    モザイク設定をまとめたパネルウィジェット。
    get_config() で現在の設定を MosaicConfig として取得できます。
    """

    _TYPE_MAP = {
        "ピクセル化": MosaicType.PIXELATE,
        "ぼかし": MosaicType.BLUR,
        "黒帯": MosaicType.BLACK_BARS,
    }
    _REVERSE_TYPE_MAP = {value: key for key, value in _TYPE_MAP.items()}

    def __init__(self, parent=None) -> None:
        super().__init__("モザイク設定", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        form = QFormLayout(self)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        self._type_cb = QComboBox()
        self._type_cb.addItems(list(self._TYPE_MAP.keys()))
        form.addRow("種類", self._type_cb)

        self._block_size = _LabeledSlider(5, 100)
        self._block_size.setValue(15)
        form.addRow("ブロックサイズ", self._block_size)

        self._blur_radius = _LabeledSlider(3, 101, step=2)
        self._blur_radius.setValue(21)
        form.addRow("ぼかし半径", self._blur_radius)

        self._bar_count = _LabeledSlider(1, 20)
        self._bar_count.setValue(5)
        form.addRow("黒帯本数", self._bar_count)

        self._bar_angle = _LabeledSlider(0, 180)
        self._bar_angle.setValue(0)
        form.addRow("黒帯角度", self._bar_angle)

        self._bar_opacity = _LabeledSlider(0, 100)
        self._bar_opacity.setValue(100)
        form.addRow("黒帯不透明度 (%)", self._bar_opacity)

    def get_config(self) -> MosaicConfig:
        """現在の UI 状態を MosaicConfig に変換する。"""
        blur = self._blur_radius.value()
        if blur % 2 == 0:
            blur += 1
        return MosaicConfig(
            mosaic_type=self._TYPE_MAP[self._type_cb.currentText()],
            block_size=self._block_size.value(),
            blur_radius=blur,
            bar_count=self._bar_count.value(),
            bar_angle=float(self._bar_angle.value()),
            bar_opacity=self._bar_opacity.value() / 100.0,
        )

    def set_config(self, config: MosaicConfig) -> None:
        """MosaicConfig の内容を UI へ反映する。"""
        self._type_cb.setCurrentText(self._REVERSE_TYPE_MAP[config.mosaic_type])
        self._block_size.setValue(config.block_size)
        self._blur_radius.setValue(config.blur_radius)
        self._bar_count.setValue(config.bar_count)
        self._bar_angle.setValue(int(config.bar_angle))
        self._bar_opacity.setValue(int(config.bar_opacity * 100))


_DETECTOR_DISPLAY_NAMES: dict[str, str] = {
    "Haar分類器 (ローカル・追加不要)": "haar",
    "Ollama LLM (ローカル)": "ollama",
    "OpenAI API (クラウド)": "openai",
}

#: 検出対象の表示名と DetectionTarget の対応
_TARGET_DISPLAY: list[tuple[str, DetectionTarget]] = [
    ("顔", DetectionTarget.FACE),
    ("個人情報", DetectionTarget.PERSONAL_INFO),
    ("センシティブな部位", DetectionTarget.SENSITIVE),
]


class DetectorSettingsPanel(QGroupBox):
    """
    検出器の種類と接続設定をまとめたパネルウィジェット。
    get_detector() で現在の設定に応じた BaseDetector インスタンスを返します。
    OpenAI API キーは画面上ではマスク表示します。
    LLM 検出器選択時には検出対象（顔・個人情報・センシティブ）を個別に選択できます。
    """

    def __init__(self, parent=None) -> None:
        super().__init__("検出器設定", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form_top = QFormLayout()
        self._detector_cb = QComboBox()
        self._detector_cb.addItems(list(_DETECTOR_DISPLAY_NAMES.keys()))
        self._detector_cb.currentIndexChanged.connect(self._on_detector_changed)
        form_top.addRow("検出器", self._detector_cb)
        layout.addLayout(form_top)

        self._ollama_group = QGroupBox("Ollama 設定")
        ollama_form = QFormLayout(self._ollama_group)
        self._ollama_host = QLineEdit("http://localhost:11434")
        self._ollama_model = QLineEdit("llava")
        ollama_form.addRow("ホスト", self._ollama_host)
        ollama_form.addRow("モデル名", self._ollama_model)
        layout.addWidget(self._ollama_group)

        self._openai_group = QGroupBox("OpenAI 設定")
        openai_form = QFormLayout(self._openai_group)
        self._openai_key = QLineEdit()
        self._openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_key.setPlaceholderText("sk-...")
        self._openai_model = QLineEdit("gpt-4o")
        openai_form.addRow("APIキー", self._openai_key)
        openai_form.addRow("モデル名", self._openai_model)
        layout.addWidget(self._openai_group)

        # 検出対象選択（LLM 検出器選択時のみ表示）
        self._target_group = QGroupBox("検出対象")
        target_layout = QVBoxLayout(self._target_group)
        self._target_checkboxes: dict[DetectionTarget, QCheckBox] = {}
        for label, target in _TARGET_DISPLAY:
            cb = QCheckBox(label)
            cb.setChecked(True)  # デフォルトは全選択
            target_layout.addWidget(cb)
            self._target_checkboxes[target] = cb
        layout.addWidget(self._target_group)

        self._on_detector_changed()

    def _on_detector_changed(self) -> None:
        """検出器種別に応じて固有設定グループを表示/非表示にする。"""
        selected = _DETECTOR_DISPLAY_NAMES.get(self._detector_cb.currentText(), "haar")
        self._ollama_group.setVisible(selected == "ollama")
        self._openai_group.setVisible(selected == "openai")
        # LLM 検出器のときだけ検出対象を表示
        self._target_group.setVisible(selected in ("ollama", "openai"))

    def _get_selected_targets(self) -> frozenset[DetectionTarget]:
        """チェックボックスの状態から選択された検出対象セットを返す。"""
        selected = frozenset(
            target
            for target, cb in self._target_checkboxes.items()
            if cb.isChecked()
        )
        # 何も選択されていない場合は全対象にフォールバック
        return selected if selected else ALL_TARGETS

    def get_detector(self) -> BaseDetector:
        """現在の設定から BaseDetector インスタンスを生成して返す。"""
        detector_type = _DETECTOR_DISPLAY_NAMES.get(self._detector_cb.currentText(), "haar")
        targets = self._get_selected_targets() if detector_type in ("ollama", "openai") else None
        return create_detector(
            detector_type,
            targets=targets,
            ollama_host=self._ollama_host.text(),
            ollama_model=self._ollama_model.text(),
            openai_api_key=self._openai_key.text(),
            openai_model=self._openai_model.text(),
        )
