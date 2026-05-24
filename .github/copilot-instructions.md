# MosaicMan — Copilot Instructions

## プロジェクト概要

MosaicMan は、公開済みの画像・動画へ後付けでモザイクを適用するための
**ローカル完結型デスクトップアプリケーション**です。
クラウドへ素材を送信せず、クリエイターが安全に加工できることを主目的とします。

主なユースケース: fantia などで既にリリース済みの作品へ事後的にモザイクを付与する。

---

## 実行環境・パッケージ管理

| 項目 | 内容 |
|---|---|
| 言語 | Python 3.11 以上 |
| パッケージ管理 | **uv** (`pyproject.toml` で管理) |
| GUI フレームワーク | **tkinter**（Python 組み込み・BSD 系ライセンス） |
| 画像処理 | Pillow (HPND)、OpenCV `opencv-python` (Apache 2.0) |
| 動画処理 | OpenCV + **ffmpeg-python** (Apache 2.0、バイナリは LGPL/GPL) |
| LLM 検出（オプション） | **ollama** (MIT) / **openai** (Apache 2.0) |
| テスト | pytest (MIT) + pytest-cov (MIT) |

### セットアップコマンド

```bash
# 基本インストール
uv sync --dev

# LLM 検出器を使う場合（ollama + openai 両方）
uv add "mosaicman[llm]"

# ollama のみ
uv add "mosaicman[ollama]"

# OpenAI のみ
uv add "mosaicman[openai-api]"

# アプリ起動
uv run mosaicman

# テスト実行
uv run pytest

# カバレッジ付き
uv run pytest --cov=src/mosaicman --cov-report=term-missing
```

---

## ライセンス方針（重要）

すべてのコア依存ライブラリはフリーソフト配布に適したライセンスで提供されています。

| ライブラリ | ライセンス | 備考 |
|---|---|---|
| Python | PSF License | ランタイム |
| tkinter / Tcl/Tk | BSD 系 | GUI |
| Pillow | HPND 系 | 画像 I/O |
| opencv-python | Apache 2.0 | 画像処理・顔検出 |
| NumPy | BSD 3-Clause | 配列演算 |
| ffmpeg-python | Apache 2.0 | 動画ラッパー（オプション） |
| FFmpeg バイナリ | **LGPL または GPL** | ビルド構成による。同梱時は要確認 |
| ollama (オプション) | MIT | ローカル LLM |
| openai (オプション) | Apache 2.0 | クラウド LLM |
| pytest / pytest-cov | MIT | テスト |

**FFmpeg に関する注意**: `ffmpeg-python` の Python ラッパーは Apache 2.0 ですが、
実際に呼び出す FFmpeg バイナリのライセンスは LGPL または GPL です。
バイナリを同梱して配布する場合はライセンス文面の添付が必要です。
FFmpeg バイナリなしでも OpenCV コーデックのみで動作します（自動フォールバック）。

---

## ディレクトリ構成

```
MosaicMan/
├── pyproject.toml               # uv/PEP 517 プロジェクト設定
├── .gitignore
├── docs/
│   ├── design.md                # 設計書（日本語）
│   └── manual.md                # ユーザーマニュアル（日本語）
├── src/
│   └── mosaicman/
│       ├── __init__.py          # バージョン文字列のみ
│       ├── main.py              # エントリーポイント → MosaicApp().mainloop()
│       ├── core/
│       │   ├── mosaic.py        # モザイク効果エンジン（GUI非依存）
│       │   ├── detector.py      # 検出器プラグイン群（Haar / Ollama / OpenAI）
│       │   └── media.py         # 画像・動画 I/O（lossless 対応）
│       ├── gui/
│       │   ├── app.py           # メインウィンドウ・ワークフロー制御
│       │   ├── preview.py       # プレビューキャンバス（領域選択・追加）
│       │   └── settings.py      # モザイク設定パネル + 検出器設定パネル
│       └── utils/
│           └── security.py      # パス検証・サニタイズユーティリティ
└── tests/
    ├── conftest.py              # 共通フィクスチャ
    ├── test_mosaic.py
    ├── test_detector.py
    └── test_media.py
```

---

## アーキテクチャ方針

### レイヤー分離（重要）

```
GUI 層  (gui/)          ← ユーザー操作を受け取り、コア層に委譲
    ↓ 呼び出し
コア層  (core/)         ← GUI 非依存。CLI やバッチ処理からも使える
    ↓ 使用
ユーティリティ (utils/) ← セキュリティ、共通処理
```

- `core/` のモジュールは `tkinter` を import してはいけない。
- GUI 非依存にすることで、将来的な CLI / バッチモード移行を容易にする。

### 検出器プラグインアーキテクチャ

```
BaseDetector (ABC)
├── HaarCascadeDetector   ← OpenCV Haar 分類器（デフォルト、追加不要）
├── OllamaDetector        ← ローカル LLM（llava, moondream 等）  ← 要 ollama パッケージ
└── OpenAIDetector        ← OpenAI Vision API（gpt-4o 等）        ← 要 openai パッケージ
```

`create_detector(type, **kwargs)` ファクトリ関数で文字列指定して切り替えます。
`ollama` / `openai` パッケージは optional dependencies のため、未インストールでも
アプリは起動します（実行時に `ImportError` を raise）。

### ユーザー操作フロー

```
開く → 検出器選択 + 「検出」（バックグラウンドスレッド）→ プレビューで確認・調整
  → モザイク設定で種類・強さを選択 → 「適用」（プレビュー反映）→ 「保存」
```

---

## 各モジュールの責務

### `core/mosaic.py`

- `MosaicType` enum: `PIXELATE` / `BLUR` / `BLACK_BARS`
- `MosaicConfig` dataclass: `block_size`, `blur_radius`, `bar_count`, `bar_angle`, `bar_opacity`
- `MosaicEngine.apply(image, region, config)`: NumPy 配列に対してモザイク適用
- `MosaicEngine.apply_to_pil(image, region, config)`: PIL Image 版ラッパー
- 領域は常に画像サイズへクランプ（はみ出しはエラーにしない）

### `core/detector.py`

- `DetectedRegion` dataclass: `x, y, width, height, label, confidence`
- `BaseDetector(ABC)`: `detect(image)` と `detect_from_pil(image)` を定義
- `HaarCascadeDetector`: 顔（正面・横顔）検出。Apache 2.0。完全ローカル
- `OllamaDetector(model, host)`: Ollama Vision LLM。MIT。プライバシー重視時に推奨
- `OpenAIDetector(api_key, model)`: OpenAI Vision API。画像を外部送信するため注意
- `_DETECTION_PROMPT`: LLM へ JSON 形式のバウンディングボックス返却を要求するプロンプト
- `_parse_llm_response(text, w, h)`: 純 JSON パース → 埋め込み JSON 抽出の 2 段階パース
- `create_detector(type, **kwargs)`: ファクトリ関数
- `RegionDetector = HaarCascadeDetector`: 後方互換エイリアス
- IoU 0.3 以上の重複検出は `_deduplicate()` で除去

### `core/media.py`

- `ImageMedia.load(path)`: パス検証後に PIL Image を返す
- `ImageMedia.save_lossless(image, path)`: PNG 形式で無劣化保存
- `ImageMedia.save(image, path, quality)`: JPEG は quality 引数使用
- `VideoMedia`: コンテキストマネージャ。`frames()` でフレームをイテレート
- `VideoMedia.save_with_mosaic(output, mosaic_fn, lossless)`:
  一時ファイル経由で保存し、成功時のみ最終パスへ移動する（破損防止）

### `gui/settings.py`

- `SettingsPanel(ttk.LabelFrame)`:
  - コンボボックス: モザイク種類（ピクセル化 / ぼかし / 黒帯）
  - スライダー: ブロックサイズ、ぼかし半径、黒帯本数・角度・不透明度
  - `get_config() → MosaicConfig` / `set_config(config)`
- `DetectorSettingsPanel(ttk.LabelFrame)`:
  - コンボボックス: 検出器種別（Haar / Ollama / OpenAI）
  - 種別切替で固有設定フィールドを show/hide
  - OpenAI API キーは `show="*"` でマスク表示
  - `get_detector() → BaseDetector`: 設定に基づき検出器を動的生成

### `gui/preview.py`

- `Region` dataclass: `x, y, width, height, label, confidence, enabled, rect_id`
- `PreviewCanvas(tk.Canvas)`:
  - クリック → 領域の有効/無効トグル（赤: 有効、グレー: 無効）
  - ドラッグ → 新規領域追加（シアン色の点線プレビュー）
  - 画像はアスペクト比維持でキャンバスにフィット表示
  - `get_enabled_regions()` で有効領域のリストを返す

### `gui/app.py`

- `MosaicApp(tk.Tk)`: ワークフロー全体を管理するメインウィンドウ
- `_detect_regions()`: `DetectorSettingsPanel.get_detector()` で検出器を動的生成し、
  `threading.Thread(daemon=True)` でバックグラウンド実行
- `_update_status(msg)`: スレッドセーフ（`self.after(0, ...)` でメインスレッドへ）
- 動画保存も別スレッドで実行

### `utils/security.py`

- `validate_file_path(path, allowed_extensions)`:
  - `..` によるパストラバーサルを拒否
  - NUL バイトを含むパスを拒否
  - 許可拡張子以外を拒否
  - `resolve(strict=True)` でシンボリックリンクを実体化
- `sanitize_output_path(path, base_dir)`: 出力先の安全検証
- `clamp(value, min_val, max_val)`: 数値のクランプ

---

## コーディング規約

### コメント・ドキュメント

- モジュールレベルの docstring は **日本語** で記述する（既存ファイルに準拠）
- すべての public クラス・メソッドに docstring を付与する
- 複雑なロジックにはインラインコメントを付ける

### スタイル

- `from __future__ import annotations` を全 Python ファイルの先頭に記載
- `@dataclass(slots=True)` を dataclass に使用する
- 型ヒントは `str | Path` 形式（Union 型ではなく `|` 記法）
- GUI 例外は `messagebox.showerror()` で表示し、スタックトレースをユーザーに見せない

### エラー処理

```python
# コア層: 具体的な例外を raise
raise ValueError("Unsupported file extension: .xyz")
raise ImportError("ollama パッケージをインストールしてください")

# GUI 層: ユーザーフレンドリーなダイアログを表示
except Exception as exc:
    messagebox.showerror("エラー", str(exc))
```

### スレッド安全

- tkinter の操作は必ずメインスレッドで行う
- バックグラウンドスレッドから UI を更新するときは `self.after(0, callback)` を使う

### セキュリティ

- API キーは絶対にログへ出力しない（`logging.debug` 等でも不可）
- API キー入力フィールドは必ず `show="*"` を指定する
- ファイルパスは必ず `validate_file_path()` / `sanitize_output_path()` を通す

---

## テスト規約

- テストファイルは `tests/` 配下に `test_<module>.py` 形式で配置
- フィクスチャは `tests/conftest.py` に集約
- 各テストは独立して実行できること（副作用なし）
- LLM 検出器のテストは `unittest.mock.MagicMock` で外部 API をモック
- `pragma: no cover` は GUI 例外経路など手動テストが困難な箇所のみに使用
- 新しいコア機能を追加したときは、対応するテストを必ず追加する

```bash
uv run pytest                          # 全テスト（35件）
uv run pytest tests/test_detector.py  # 検出器のみ
uv run pytest -v                       # 詳細表示
```

---

## 新しい検出器を追加する方法

1. `core/detector.py` に `BaseDetector` を継承したクラスを追加
2. `detect(self, image: np.ndarray) -> list[DetectedRegion]` を実装
3. `create_detector()` に新しい `detector_type` 文字列を追加
4. `gui/settings.py` の `_DETECTOR_DISPLAY_NAMES` に表示名を追加
5. `DetectorSettingsPanel._build_ui()` に固有設定フィールドを追加（必要に応じて）
6. `tests/test_detector.py` にモックテストを追加

---

## 今後の拡張ポイント

- Anthropic Claude Vision API 対応（`BaseDetector` を継承するだけ）
- 領域ごとの個別 `MosaicConfig` 設定
- タイムライン付き動画編集 UI
- CLI / バッチモード（コア層が GUI 非依存のため容易）
- 検出モデルのプラグイン化（外部パッケージからの登録）
