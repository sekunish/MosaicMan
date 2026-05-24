# MosaicMan 設計書

## 1. プロジェクト概要
MosaicMan は、既に公開済みの画像・動画へ後付けでモザイクを適用するためのローカル完結型デスクトップアプリケーションです。クリエイターがクラウドへ素材を送信せずに、顔や身体などの秘匿したい領域へ安全に加工できることを主目的とします。

## 2. アーキテクチャ概要

```
[GUI 層]
  gui.app        ← ワークフロー全体の制御
  gui.preview    ← 画像プレビュー・領域の可視化と手動追加
  gui.settings   ← モザイク設定パネル / 検出器設定パネル
        ↓ 呼び出し
[コア層 ※ GUI 非依存]
  core.detector  ← 領域検出（Haar / Ollama / OpenAI の切替可能）
  core.mosaic    ← モザイク効果エンジン
  core.media     ← 画像・動画 I/O（lossless 対応）
        ↓ 使用
[ユーティリティ]
  utils.security ← パス検証・サニタイズ
```

GUI 層はユーザー操作を受け取り、コア層へ処理を委譲します。コア層は GUI 非依存にしており、将来的な CLI 化やバッチ処理への再利用を容易にしています。

## 3. モジュール設計

### `core/mosaic.py`
- `MosaicType` enum: `PIXELATE` / `BLUR` / `BLACK_BARS`
- `MosaicConfig` dataclass: 全モザイクパラメータを保持
- `MosaicEngine.apply()`: NumPy 配列に対し指定領域へモザイクを適用
- `MosaicEngine.apply_to_pil()`: PIL Image 版ラッパー
- 領域は画像サイズへ自動クランプ（はみ出しはエラーにしない）

### `core/detector.py`
検出器プラグインアーキテクチャを採用。すべての検出器が `BaseDetector` を実装します。

| クラス | 説明 | ライセンス | プライバシー |
|---|---|---|---|
| `HaarCascadeDetector` | OpenCV Haar 分類器（正面・横顔） | Apache 2.0 | 完全ローカル |
| `OllamaDetector` | ローカル LLM（llava, moondream 等） | MIT | 完全ローカル（デフォルト） |
| `OpenAIDetector` | OpenAI Vision API（gpt-4o 等） | Apache 2.0 | 画像を外部送信 |

`create_detector(type, **kwargs)` ファクトリ関数で文字列指定して切り替えられます。
LLM 検出器は `_DETECTION_PROMPT` を使い、JSON 形式でバウンディングボックスを返すよう指示します。
LLM の応答は `_parse_llm_response()` が 2 段階パース（純 JSON → 埋め込み JSON 抽出）でロバストに処理します。

`RegionDetector` は `HaarCascadeDetector` の後方互換エイリアスです。

### `core/media.py`
- `ImageMedia`: パス検証後に PIL Image を読み込み/保存（PNG 無劣化対応）
- `VideoMedia`: コンテキストマネージャ。`frames()` でフレームをイテレート
- 動画保存は `.part` 一時ファイル経由で行い、成功時のみ最終パスへ移動（破損防止）
- `ffmpeg-python` が使用可能な環境では lossless エンコードを試行

### `gui/settings.py`
- `SettingsPanel`: モザイク種類・各パラメータの設定 UI
- `DetectorSettingsPanel`: 検出器種別コンボ + 種別に応じた設定フィールドの表示/非表示
  - OpenAI API キーは `show="*"` でマスク表示

### `gui/preview.py`
- `PreviewCanvas`: 画像表示スケールと実座標の相互変換を担当
- クリック → 領域の有効/無効トグル（赤: 有効、グレー: 無効）
- ドラッグ → 新規領域追加

### `gui/app.py`
- `MosaicApp`: メインウィンドウ。「検出」押下時に `DetectorSettingsPanel.get_detector()` を呼び検出器を動的生成
- 検出・動画保存はバックグラウンドスレッドで実行し、UI はブロックしない
- `QThread` とシグナル/スロットでスレッドセーフに UI を更新する

### `utils/security.py`
- `validate_file_path()`: パストラバーサル・NUL バイト・不正拡張子を拒否
- `sanitize_output_path()`: 出力先の安全検証

## 4. データフロー

```
1. ユーザーがファイルを選択
2. media.py が安全なパス検証後に画像/動画を読み込む
3. DetectorSettingsPanel の設定で create_detector() が検出器を生成
4. detector.detect_from_pil() が推薦領域を生成（バックグラウンドスレッド）
5. PreviewCanvas が候補を表示し、ユーザーが採用・除外・追加を行う
6. SettingsPanel が UI 値を MosaicConfig に変換
7. MosaicEngine が選択領域へエフェクトを適用
8. media.py が画像または動画を保存（一時ファイル経由）
```

## 5. セキュリティ設計

| リスク | 対策 |
|---|---|
| パストラバーサル | `validate_file_path()` で `..` と NUL バイトを拒否 |
| 不正拡張子 | `allowed_extensions` セットで許可リスト制御 |
| シンボリックリンク攻撃 | `resolve(strict=True)` で実体パスを取得 |
| API キー漏洩 | `show="*"` でマスク・ログ出力なし |
| 動画保存中の破損 | `.part` 一時ファイル経由で `shutil.move` |
| クラウド漏洩 | デフォルト検出器はローカル完結。OpenAI は利用者が明示的に選択 |

## 6. 依存ライブラリと配布時の考慮事項

すべてのコア依存ライブラリはフリーソフト配布に適したライセンスです。

| ライブラリ | ライセンス | 用途 |
|---|---|---|
| Python | PSF License | ランタイム |
| PySide6 / Qt for Python | LGPL | GUI |
| Pillow | HPND 系 | 画像 I/O |
| opencv-python | Apache 2.0 | 画像処理・顔検出 |
| NumPy | BSD 3-Clause | 配列演算 |
| ffmpeg-python | Apache 2.0 | 動画高品質出力（任意） |
| ollama (オプション) | MIT | ローカル LLM 検出 |
| openai (オプション) | Apache 2.0 | クラウド LLM 検出 |
| pytest / pytest-cov | MIT | テスト |

**FFmpeg バイナリ**: `ffmpeg-python` は Python ラッパーのみ Apache 2.0。実際に使用する FFmpeg バイナリのライセンスはビルド構成により LGPL または GPL となるため、同梱する場合はライセンス文面の添付と条件確認が必要です。`ffmpeg` バイナリが不要な運用（OpenCV コーデックのみ使用）も可能です。

## 7. 今後の拡張性

- 新しい LLM プロバイダの追加: `BaseDetector` を継承するだけで対応可能
- Anthropic Claude Vision API 対応
- 領域ごとの個別 `MosaicConfig` 設定
- タイムライン付き動画編集 UI
- CLI / バッチモード（コア層が GUI 非依存のため容易）
- 検出モデルのプラグイン化

