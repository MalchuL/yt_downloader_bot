import json
import math
import os
import shutil
import subprocess
import sys
import glob
from typing import List, Optional
from pathlib import Path

from .splitter import Splitter


class FFmpegSplitter(Splitter):
    """
    Split a video into ~N MB chunks using ffmpeg's segment muxer,
    naming outputs with postfixes _0, _1, _2, ...

    Requirements:
      - ffmpeg and ffprobe must be installed and discoverable in PATH
        (or provide explicit paths via constructor).

    Caveats:
      - Splitting by exact byte size isn't supported by most muxers.
        This estimates segment_time from the overall bitrate to target ~chunk_size_mb.
      - With -c copy (no re-encode), segment boundaries align to keyframes,
        so sizes will vary. Re-encoding would allow precise GOP-aligned keyframes
        but is slower and still not exact-bytes.

    Example:
        splitter = FFMPEGSplitter(chunk_size_mb=50)
        parts = splitter.split("input.mp4")
        print(parts)
    """
    MAX_CHUNKS = 10

    def __init__(
        self,
        ffmpeg_path: str = "ffmpeg",
        ffprobe_path: str = "ffprobe",
        max_chunks: int = MAX_CHUNKS
    ):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

        for tool in (self.ffmpeg_path, self.ffprobe_path):
            if not shutil.which(tool):
                raise RuntimeError(
                    f"Required tool '{tool}' not found in PATH. "
                    f"Install FFmpeg or provide explicit path."
                )

    def split_by_size(self, input_path: str | Path, output_dir: str | Path, size_mb: int = 100) -> List[Path]:
        """
        Split input_path into approximately chunk_size_mb segments.
        Returns a list of created file paths in order.
        """
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"Input not found: {input_path}")

        # Resolve output directory and file naming
        input_path = Path(input_path).resolve()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        base_name = input_path.stem
        ext = input_path.suffix or ".mp4"  # default to .mp4 if none
        output_pattern = str(output_dir / (f"{base_name}" + "_%d" + f"{ext}"))

        # Clean any pre-existing files that match the pattern to avoid mixing runs
        self._cleanup_existing(output_dir, base_name, ext)

        # Derive target segment_time from bitrate
        bitrate_bps, duration_s, size_bytes = self._probe_bitrate_duration_size(input_path)
        if bitrate_bps is None or bitrate_bps <= 0:
            # Fallback: use file size / duration if possible
            if duration_s and duration_s > 0 and size_bytes and size_bytes > 0:
                bitrate_bps = (size_bytes * 8.0) / duration_s
            else:
                # Worst-case fallback: assume a 5 Mbps stream (arbitrary)
                bitrate_bps = 5_000_000.0

        target_bytes = size_mb * 1024.0 * 1024.0
        segment_time = (target_bytes * 8.0) / bitrate_bps

        # Build ffmpeg command
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-y",
            "-i", str(input_path),
            "-c", "copy",
            "-map", "0",
            "-fs", f"{target_bytes}",
            "-f", "segment",
            "-segment_time", f"{segment_time:.3f}",
            "-reset_timestamps", "1",
        ]

        # For MP4/MOV family, enable faststart on each segment for better playability
        if ext.lower() in (".mp4", ".mov", ".m4v"):
            cmd += ["-movflags", "+faststart"]

        cmd += [output_pattern]

        # Run ffmpeg
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            # Include a short excerpt of stderr for debugging
            stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
            snippet = "\n".join(stderr.splitlines()[-15:])
            raise RuntimeError(f"ffmpeg failed:\n{snippet}") from e

        # Collect outputs in numeric order
        parts = self._collect_outputs(output_dir, base_name, ext)
        if not parts:
            raise RuntimeError("No output segments were produced.")
        return parts

    def _probe_bitrate_duration_size(self, input_path: str | Path) -> tuple[float | None, float | None, float | None]:
        """
        Use ffprobe to get container-level bitrate (bps), duration (s), and size (bytes).
        Returns (bitrate_bps or None, duration_s or None, size_bytes or None).
        """
        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=bit_rate,duration,size",
            "-of", "json",
            str(input_path),
        ]
        try:
            proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
            fmt = data.get("format", {})
            bit_rate = fmt.get("bit_rate")
            duration = fmt.get("duration")
            size = fmt.get("size")
            bitrate_bps = float(bit_rate) if bit_rate is not None else None
            duration_s = float(duration) if duration is not None else None
            size_bytes = float(size) if size is not None else None
            return bitrate_bps, duration_s, size_bytes
        except Exception:
            return None, None, None

    def _cleanup_existing(self, output_dir: str | Path, base_name: str, ext: str) -> None:
        output_dir = Path(output_dir)
        pattern = output_dir / (f"{base_name}_" + "*" + f"{ext}")
        for path in pattern.glob("*"):
            try:
                path.unlink()
            except OSError:
                pass

    def _collect_outputs(self, output_dir: str | Path, base_name: str, ext: str) -> List[Path]:
        output_dir = Path(output_dir)
        files = list(output_dir.glob(f"{base_name}_" + "*" + f"{ext}"))
        print(files, output_dir, base_name, ext, f"{base_name}_" + "*" + f"{ext}")
        def extract_index(p: Path) -> int:
            name = p.stem
            # Expect suffix after last underscore
            try:
                return int(name.split("_")[-1])
            except ValueError:
                return sys.maxsize  # push unexpected names to the end

        files.sort(key=lambda p: extract_index(p))
        return files

