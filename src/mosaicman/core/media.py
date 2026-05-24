"""
media.py - メディア入出力モジュール

画像・動画の読み込みと保存を担当します。
PNG 形式での無劣化保存、ffmpeg を用いた動画の無劣化処理をサポートします。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np
from PIL import Image

from ..utils.security import sanitize_output_path, validate_file_path

try:
    import ffmpeg
except ImportError:  # pragma: no cover - 依存未導入時の保険
    ffmpeg = None

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


class ImageMedia:
    """画像の読み込み・保存クラス。"""

    @staticmethod
    def load(path: str | Path) -> Image.Image:
        """画像を PIL Image として読み込む（パス検証付き）。"""
        validated = validate_file_path(path, SUPPORTED_IMAGE_EXTENSIONS)
        with Image.open(validated) as image:
            return image.copy()

    @staticmethod
    def save_lossless(image: Image.Image, path: str | Path) -> None:
        """PNG 形式で無劣化保存する。"""
        output = sanitize_output_path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, format="PNG")

    @staticmethod
    def save(image: Image.Image, path: str | Path, quality: int = 95) -> None:
        """指定パスに保存（JPEG は quality 引数を使用）。"""
        output = sanitize_output_path(path)
        suffix = output.suffix.lower()
        if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image extension: {suffix}")
        output.parent.mkdir(parents=True, exist_ok=True)

        save_kwargs: dict[str, object] = {}
        if suffix in {".jpg", ".jpeg"}:
            save_kwargs["quality"] = int(max(1, min(100, quality)))
            save_kwargs["optimize"] = True
        image.save(output, **save_kwargs)


class VideoMedia:
    """動画の読み込み・フレーム処理・保存クラス。"""

    def __init__(self, path: str | Path):
        """入力動画パスを保持する。"""
        validated = validate_file_path(path, SUPPORTED_VIDEO_EXTENSIONS)
        self._path = validated
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        """動画を開く。"""
        if self._cap is not None:
            return
        self._cap = cv2.VideoCapture(str(self._path))
        if not self._cap.isOpened():
            self._cap.release()
            self._cap = None
            raise ValueError(f"Failed to open video: {self._path}")

    def close(self) -> None:
        """動画を閉じる。"""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self) -> "VideoMedia":
        """with 文で動画を開く。"""
        self.open()
        return self

    def __exit__(self, *args) -> None:
        """with 文を抜ける際に動画を閉じる。"""
        self.close()

    @property
    def frame_count(self) -> int:
        """総フレーム数を返す。"""
        return int(self._get_prop(cv2.CAP_PROP_FRAME_COUNT))

    @property
    def fps(self) -> float:
        """FPS を返す。"""
        fps_value = float(self._get_prop(cv2.CAP_PROP_FPS))
        return fps_value if fps_value > 0 else 30.0

    @property
    def width(self) -> int:
        """動画幅を返す。"""
        return int(self._get_prop(cv2.CAP_PROP_FRAME_WIDTH))

    @property
    def height(self) -> int:
        """動画高さを返す。"""
        return int(self._get_prop(cv2.CAP_PROP_FRAME_HEIGHT))

    def frames(self) -> Iterator[tuple[int, np.ndarray]]:
        """フレームをジェネレータで返す (index, numpy_frame)。"""
        self.open()
        assert self._cap is not None
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        index = 0
        while True:
            ok, frame = self._cap.read()
            if not ok:
                break
            yield index, frame
            index += 1

    def save_with_mosaic(
        self,
        output_path: str | Path,
        mosaic_fn: Callable[[np.ndarray], np.ndarray],
        lossless: bool = True,
    ) -> None:
        """各フレームに mosaic_fn を適用して動画を保存する。"""
        output = sanitize_output_path(output_path)
        suffix = output.suffix.lower()
        if suffix not in SUPPORTED_VIDEO_EXTENSIONS:
            raise ValueError(f"Unsupported video extension: {suffix}")
        output.parent.mkdir(parents=True, exist_ok=True)

        self.open()
        assert self._cap is not None
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        codec_candidates: list[tuple[str, Path]] = []
        if lossless:
            codec_candidates.extend([
                ("FFV1", output.with_name(f"{output.stem}.part.avi")),
                ("HFYU", output.with_name(f"{output.stem}.part.avi")),
            ])
        codec_candidates.extend([
            ("mp4v", output.with_name(f"{output.stem}.part{suffix}")),
            ("XVID", output.with_name(f"{output.stem}.part.avi")),
        ])

        writer: cv2.VideoWriter | None = None
        temp_output: Path | None = None
        selected_codec = ""

        for codec_name, temp_candidate in codec_candidates:
            fourcc = cv2.VideoWriter_fourcc(*codec_name)
            candidate_writer = cv2.VideoWriter(
                str(temp_candidate),
                fourcc,
                self.fps,
                (self.width, self.height),
            )
            if candidate_writer.isOpened():
                writer = candidate_writer
                temp_output = temp_candidate
                selected_codec = codec_name
                break
            candidate_writer.release()

        if writer is None or temp_output is None:
            raise ValueError("Failed to initialize a video writer")

        if temp_output.exists():
            temp_output.unlink()
            writer.release()
            writer = cv2.VideoWriter(
                str(temp_output),
                cv2.VideoWriter_fourcc(*selected_codec),
                self.fps,
                (self.width, self.height),
            )
            if not writer.isOpened():
                raise ValueError("Failed to initialize a video writer after cleanup")

        ffmpeg_output = output.with_name(f"{output.stem}.ffmpeg{suffix}")
        try:
            for _, frame in self.frames():
                processed = mosaic_fn(frame.copy())
                if processed.shape[:2] != (self.height, self.width):
                    raise ValueError("mosaic_fn must preserve frame size")
                writer.write(processed)
        finally:
            writer.release()

        try:
            if temp_output.suffix == output.suffix:
                shutil.move(temp_output, output)
                return

            if ffmpeg is not None:
                stream = ffmpeg.input(str(temp_output))
                output_kwargs: dict[str, object] = {}
                if lossless:
                    output_kwargs = {"vcodec": "ffv1" if suffix == ".mkv" else "libx264rgb", "crf": 0}
                    if suffix != ".mkv":
                        output_kwargs["pix_fmt"] = "rgb24"
                else:
                    output_kwargs = {"vcodec": "libx264", "crf": 18, "pix_fmt": "yuv420p"}

                try:
                    probe = ffmpeg.probe(str(self._path))
                    has_audio = any(stream_info.get("codec_type") == "audio" for stream_info in probe.get("streams", []))
                except Exception:
                    has_audio = False

                if has_audio:
                    original = ffmpeg.input(str(self._path))
                    pipeline = ffmpeg.output(
                        stream.video,
                        original.audio,
                        str(ffmpeg_output),
                        shortest=None,
                        **output_kwargs,
                    )
                else:
                    pipeline = ffmpeg.output(stream.video, str(ffmpeg_output), **output_kwargs)

                ffmpeg.run(pipeline, overwrite_output=True, quiet=True)
                shutil.move(ffmpeg_output, output)
                temp_output.unlink(missing_ok=True)
                return

            shutil.move(temp_output, output)
        finally:
            if temp_output.exists():
                temp_output.unlink(missing_ok=True)
            ffmpeg_output.unlink(missing_ok=True)

    def _get_prop(self, prop_id: int) -> float:
        """OpenCV のプロパティ値を安全に取得する。"""
        self.open()
        assert self._cap is not None
        return float(self._cap.get(prop_id))
