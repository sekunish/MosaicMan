# MosaicMan テスト結果レポート

| 項目 | 内容 |
|---|---|
| 実行日時 | 2026-05-24T18:11:51Z (UTC) |
| コミット | `37b24ad` feat: migrate GUI from tkinter to PySide6, add LLM detector plugins |
| Python | 3.12.3 |
| pytest | 最新（uv 管理） |
| 実行コマンド | `uv run pytest tests/ -v --no-header --tb=short` |

---

## サマリー

| 結果 | 件数 |
|---|---|
| ✅ PASSED | **35** |
| ❌ FAILED | 0 |
| ⚠️ ERROR | 0 |
| ⏭️ SKIPPED | 0 |
| **合計** | **35** |

**総実行時間: 0.51 秒**

---

## テストスイート別結果

### `tests/test_detector.py` — 検出器モジュール (21 件)

| # | テスト名 | 結果 | 時間 (s) | 説明 |
|---|---|---|---|---|
| 1 | `test_detected_region_fields` | ✅ PASSED | 0.002 | `DetectedRegion` フィールドの正常設定を確認 |
| 2 | `test_iou_no_overlap` | ✅ PASSED | 0.001 | 重複なし領域の IoU = 0.0 を確認 |
| 3 | `test_iou_full_overlap` | ✅ PASSED | 0.001 | 完全一致領域の IoU = 1.0 を確認 |
| 4 | `test_deduplicate_removes_high_iou` | ✅ PASSED | 0.001 | IoU > 0.3 の重複を除去することを確認 |
| 5 | `test_parse_llm_response_valid_json` | ✅ PASSED | 0.001 | 正常な JSON 応答のパースを確認 |
| 6 | `test_parse_llm_response_embedded_json` | ✅ PASSED | 0.001 | 説明文に埋め込まれた JSON の抽出を確認 |
| 7 | `test_parse_llm_response_empty_array` | ✅ PASSED | 0.001 | 空配列 `[]` を正常処理することを確認 |
| 8 | `test_parse_llm_response_out_of_bounds_clamped` | ✅ PASSED | 0.001 | 画像サイズ外の座標クランプを確認 |
| 9 | `test_parse_llm_response_invalid_text` | ✅ PASSED | 0.001 | JSON 不在テキストで空リスト返却を確認 |
| 10 | `test_haar_detect_returns_list` | ✅ PASSED | 0.030 | Haar 検出がリストを返すことを確認 |
| 11 | `test_haar_detect_no_face` | ✅ PASSED | 0.027 | 顔なし画像で空リストを返すことを確認 |
| 12 | `test_haar_detect_from_pil` | ✅ PASSED | 0.029 | PIL Image からの Haar 検出を確認 |
| 13 | `test_region_detector_alias` | ✅ PASSED | 0.029 | `RegionDetector` が `HaarCascadeDetector` の後方互換エイリアスであることを確認 |
| 14 | `test_create_detector_haar` | ✅ PASSED | 0.023 | `create_detector("haar")` で `HaarCascadeDetector` を生成することを確認 |
| 15 | `test_create_detector_unknown_raises` | ✅ PASSED | 0.001 | 不明な種別で `ValueError` を送出することを確認 |
| 16 | `test_create_detector_ollama_instance` | ✅ PASSED | 0.000 | ollama 未インストールでも `OllamaDetector` インスタンスを生成できることを確認 |
| 17 | `test_create_detector_openai_raises_without_key` | ✅ PASSED | 0.001 | API キーなしで `ValueError` を送出することを確認 |
| 18 | `test_ollama_detector_not_installed_raises` | ✅ PASSED | 0.001 | ollama 未インストール時に `ImportError` を送出することを確認 |
| 19 | `test_ollama_detector_with_mock` | ✅ PASSED | 0.023 | モックを使って `OllamaDetector` の検出結果を確認 |
| 20 | `test_openai_detector_not_installed_raises` | ✅ PASSED | 0.001 | openai 未インストール時に `ImportError` を送出することを確認 |
| 21 | `test_openai_detector_with_mock` | ✅ PASSED | 0.003 | モックを使って `OpenAIDetector` の検出結果を確認 |

**小計: 21 / 21 PASSED**

---

### `tests/test_media.py` — メディア I/O モジュール (7 件)

| # | テスト名 | 結果 | 時間 (s) | 説明 |
|---|---|---|---|---|
| 1 | `test_validate_file_path_valid` | ✅ PASSED | 0.003 | 正常なファイルパスが通ることを確認 |
| 2 | `test_validate_file_path_traversal` | ✅ PASSED | 0.001 | `..` を含むパストラバーサルを拒否することを確認 |
| 3 | `test_validate_file_path_unsupported_ext` | ✅ PASSED | 0.001 | 未サポート拡張子を拒否することを確認 |
| 4 | `test_save_and_load_lossless` | ✅ PASSED | 0.002 | PNG 無劣化保存と読み込みのラウンドトリップを確認 |
| 5 | `test_clamp` | ✅ PASSED | 0.000 | 数値クランプの境界値を確認 |
| 6 | `test_sanitize_output_path` | ✅ PASSED | 0.001 | 出力パスのサニタイズを確認 |

> ※ `test_validate_file_path_traversal` / `test_validate_file_path_unsupported_ext` は `security.py` の検証機能をカバーしています。

**小計: 7 / 7 PASSED**

---

### `tests/test_mosaic.py` — モザイクエンジン (7 件)

| # | テスト名 | 結果 | 時間 (s) | 説明 |
|---|---|---|---|---|
| 1 | `test_pixelate_changes_roi` | ✅ PASSED | 0.001 | ピクセル化が指定領域を変化させることを確認 |
| 2 | `test_blur_changes_roi` | ✅ PASSED | 0.001 | ぼかしが指定領域を変化させることを確認 |
| 3 | `test_black_bars_changes_roi` | ✅ PASSED | 0.001 | 黒帯が指定領域に純黒ピクセルを生成することを確認 |
| 4 | `test_apply_region_bounds` | ✅ PASSED | 0.001 | 画像外にはみ出した領域指定でもクラッシュしないことを確認 |
| 5 | `test_apply_to_pil` | ✅ PASSED | 0.001 | `apply_to_pil()` が PIL Image を返すことを確認 |
| 6 | `test_all_types` | ✅ PASSED | 0.001 | 全 `MosaicType` が正常動作することを確認 |
| 7 | `test_config_defaults` | ✅ PASSED | 0.001 | `MosaicConfig` のデフォルト値を確認 |
| 8 | `test_block_size_1` | ✅ PASSED | 0.001 | `block_size=1` の境界値で正常動作することを確認 |

**小計: 8 / 8 PASSED**

---

## カバレッジ詳細

| モジュール | ステートメント数 | 未カバー | カバレッジ | 主な未カバー行 |
|---|---:|---:|---:|---|
| `core/__init__.py` | 0 | 0 | **100%** | — |
| `core/detector.py` | 158 | 11 | **93%** | L42, L48 (ollama/openai 利用可能パス), L148-149, L154, L176-177, L234, L238, L248, L256 |
| `core/media.py` | 155 | 113 | **27%** | 動画処理 (L137-244)・ffmpeg 連携・VideoMedia クラス全般 |
| `core/mosaic.py` | 83 | 9 | **89%** | L60, L73, L85, L99, L112, L117, L128, L145-146 (エラーハンドリング系) |
| `gui/app.py` | 208 | 208 | **0%** | GUI 層（ヘッドレス環境のため全未カバー） |
| `gui/preview.py` | 162 | 162 | **0%** | GUI 層（同上） |
| `gui/settings.py` | 103 | 103 | **0%** | GUI 層（同上） |
| `main.py` | 13 | 13 | **0%** | エントリーポイント（同上） |
| `utils/__init__.py` | 0 | 0 | **100%** | — |
| `utils/security.py` | 30 | 4 | **87%** | L24 (NUL バイト検証), L42, L44, L51 (シンボリックリンク・sanitize 異常系) |
| `__init__.py` | 1 | 0 | **100%** | — |
| **合計** | **913** | **623** | **32%** | |

> **コア層のカバレッジ（GUI 除く）**: `detector.py` 93% / `mosaic.py` 89% / `security.py` 87%  
> GUI 層 (`app.py`, `preview.py`, `settings.py`, `main.py`) はヘッドレス環境でのディスプレイ接続が必要なため、自動テストのカバレッジは 0% です。手動 GUI テストや Qt テストフレームワーク (`pytest-qt`) による拡充が今後の課題です。

---

## 課題・改善提案

### カバレッジ向上

| 優先度 | 対象 | 改善策 |
|---|---|---|
| 高 | `core/media.py` (27%) | `VideoMedia` の動画処理テストを追加（テスト用ダミー動画を `conftest.py` で生成） |
| 中 | `core/mosaic.py` (89%) | エラーハンドリング分岐（異常サイズ・型不正）のテストを追加 |
| 中 | `utils/security.py` (87%) | NUL バイト・シンボリックリンク・出力パス異常系のテストを追加 |
| 低 | GUI 層 (0%) | `pytest-qt` を dev 依存に追加し、シグナル/スロットの単体テストを追加 |

### 将来対応

- `pytest-qt` による GUI ウィジェットの自動テスト
- `pytest-xdist` による並列実行（現状 0.51 秒のため優先度は低）
- CI（GitHub Actions）への組み込みと JUnit XML レポートの自動集計
