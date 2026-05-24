"""
security.py - セキュリティユーティリティ

ファイルパスの検証、入力値の安全なバリデーションを提供します。
フリーソフト配布時のセキュリティリスクを低減するための機能を含みます。
"""

from __future__ import annotations

from pathlib import Path


def validate_file_path(path: str | Path, allowed_extensions: set[str] | None = None) -> Path:
    """
    ファイルパスを検証する。
    - パストラバーサル攻撃を防ぐ
    - 許可された拡張子のみ受け付ける
    - シンボリックリンクを解決して検証
    Raises: ValueError for invalid paths, FileNotFoundError if not found
    """
    raw_path = Path(path).expanduser()
    raw_text = str(raw_path)
    if "\\x00" in raw_text or "\x00" in raw_text:
        raise ValueError("Path contains NUL byte")
    if any(part == ".." for part in raw_path.parts):
        raise ValueError("Path traversal is not allowed")

    resolved = raw_path.resolve(strict=True)
    if allowed_extensions is not None and resolved.suffix.lower() not in {ext.lower() for ext in allowed_extensions}:
        raise ValueError(f"Unsupported file extension: {resolved.suffix.lower()}")
    return resolved


def sanitize_output_path(path: str | Path, base_dir: str | Path | None = None) -> Path:
    """
    出力パスをサニタイズする。
    base_dir が指定された場合、その配下のみ許可する。
    """
    raw_path = Path(path).expanduser()
    raw_text = str(raw_path)
    if "\\x00" in raw_text or "\x00" in raw_text:
        raise ValueError("Path contains NUL byte")
    if any(part == ".." for part in raw_path.parts):
        raise ValueError("Path traversal is not allowed")

    if base_dir is not None:
        base = Path(base_dir).expanduser().resolve(strict=False)
        candidate = raw_path if raw_path.is_absolute() else (base / raw_path)
        candidate = candidate.resolve(strict=False)
        if not candidate.is_relative_to(base):
            raise ValueError("Output path must stay within base_dir")
        return candidate

    return raw_path.resolve(strict=False)


def clamp(value: float, min_val: float, max_val: float) -> float:
    """値を min_val〜max_val の範囲に制限する。"""
    return max(min_val, min(max_val, value))
