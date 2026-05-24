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
| GUI フレームワーク | **tkinter**（Python 組み込み、ライセンス懸念なし） |
| 画像処理 | Pillow、OpenCV (`opencv-python`) |
| 動画処理 | OpenCV + **ffmpeg-python** |
| テスト | pytest + pytest-cov |

### セットアップコマンド

```bash
# 依存関係のインストール（開発用込み）
uv sync --dev

# アプリ起動
uv run mosaicman
# または
uv run python -m mosaicman.main

# テスト実行
uv run pytest

# カバレッジ付き
uv run pytest --cov=src/mosaicman --cov-report=term-missing
```

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
│       │   ├── detector.py      # OpenCV Haar 分類器による領域検出
│       │   └── media.py         # 画像・動画 I/O（lossless 対応）
│       ├── gui/
│       │   ├── app.py           # メインウィンドウ・ワークフロー制御
│       │   ├── preview.py       # プレビューキャンバス（領域選択・追加）
│       │   └── settings.py      # モザイク設定パネル
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

### ユーザー操作フロー

```
開く → 検出（バックグラウンドスレッド）→ プレビューで確認・調整
  → 設定パネルで種類・強さを選択 → 適用（プレビュー反映）→ 保存
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
- `RegionDetector.detect(image: np.ndarray)`: 顔（正面・横顔）検出
- `RegionDetector.detect_from_pil(image: Image.Image)`: PIL Image 版
- IoU 0.3 以上の重複検出は `_deduplicate()` で除去

### `core/media.py`

- `ImageMedia.load(path)`: パス検証後に PIL Image を返す
- `ImageMedia.save_lossless(image, path)`: PNG 形式で無劣化保存
- `ImageMedia.save(image, path, quality)`: JPEG は quality 引数使用
- `VideoMedia`: コンテキストマネージャ。`frames()` でフレームをイテレート
- `VideoMedia.save_with_mosaic(output, mosaic_fn, lossless)`:
  一時ファイル経由で保存し、成功時のみ最終パスへ移動する（破損防止）

### `gui/preview.py`

- `Region` dataclass: `x, y, width, height, label, confidence, enabled, rect_id`
- `PreviewCanvas(tk.Canvas)`:
  - クリック → 領域の有効/無効トグル（赤: 有効、グレー: 無効）
  - ドラッグ → 新規領域追加（シアン色の点線プレビュー）
  - 画像はアスペクト比維持でキャンバスにフィット表示
  - `get_enabled_regions()` で有効領域のリストを返す

### `gui/settings.py`

- `SettingsPanel(ttk.LabelFrame)`:
  - コンボボックス: モザイク種類（ピクセル化 / ぼかし / 黒帯）
  - スライダー: ブロックサイズ、ぼかし半径、黒帯本数・角度・不透明度
  - `get_config() → MosaicConfig`
  - `set_config(config)` で UI に反映可能

### `gui/app.py`

- `MosaicApp(tk.Tk)`: ワークフロー全体を管理するメインウィンドウ
- `_detect_regions()`: `threading.Thread(daemon=True)` でバックグラウンド実行
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
raise FileNotFoundError(...)

# GUI 層: ユーザーフレンドリーなダイアログを表示
except Exception as exc:
    messagebox.showerror("エラー", str(exc))
```

### スレッド安全

- tkinter の操作は必ずメインスレッドで行う
- バックグラウンドスレッドから UI を更新するときは `self.after(0, callback)` を使う

---

## セキュリティ要件

| リスク | 対策 |
|---|---|
| パストラバーサル | `validate_file_path()` で `..` と NUL バイトを拒否 |
| 不正拡張子 | `allowed_extensions` セットで許可リスト制御 |
| シンボリックリンク攻撃 | `resolve(strict=True)` で実体パスを取得 |
| 動画保存中の破損 | `.part` 一時ファイルに書き出し、成功時のみ最終パスへ `shutil.move` |
| クラウド漏洩 | ローカル完結処理。外部通信なし |

---

## テスト規約

- テストファイルは `tests/` 配下に `test_<module>.py` 形式で配置
- フィクスチャは `tests/conftest.py` に集約
- 各テストは独立して実行できること（副作用なし）
- `pragma: no cover` は GUI 例外経路など手動テストが困難な箇所のみに使用
- 新しいコア機能を追加したときは、対応するテストを必ず追加する

### テスト実行

```bash
uv run pytest                          # 全テスト
uv run pytest tests/test_mosaic.py     # 特定ファイル
uv run pytest -v                       # 詳細表示
```

---

## 依存ライブラリのライセンス（配布時の注意）

| ライブラリ | ライセンス |
|---|---|
| Python | PSF License |
| tkinter / Tcl/Tk | BSD 系 |
| Pillow | HPND 系 |
| opencv-python | Apache License 2.0 |
| NumPy | BSD 3-Clause |
| ffmpeg-python | BSD License |
| pytest / pytest-cov | MIT |
| FFmpeg バイナリ | ビルド構成により LGPL / GPL |

本リポジトリ自体は **MIT ライセンス** で運用。
再配布時は依存バイナリ同梱条件と各ライセンス文面の添付要否を確認すること。

---

## 今後の拡張ポイント

- DNN ベース高精度人物検出器への切替（`detector.py` の差し替えのみで対応可能）
- 領域ごとの個別 `MosaicConfig` 設定
- タイムライン付き動画編集 UI
- CLI / バッチモード（コア層が GUI 非依存のため容易）
- 検出モデルのプラグイン化
