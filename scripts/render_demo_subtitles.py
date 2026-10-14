"""Render readable Chinese captions below the original recorded demo frame."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs/media"


def timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{milliseconds:03}"


def render(ffmpeg: str, font: Path) -> None:
    captions = json.loads((MEDIA / "cityclean-demo-captions.json").read_text(encoding="utf-8"))
    segments = captions["segments"]
    previous_end = 0.0
    for segment in segments:
        if segment["start"] != previous_end or segment["end"] <= segment["start"]:
            raise ValueError("Caption segments must cover the recording without gaps or overlap")
        previous_end = segment["end"]
    if previous_end != captions["duration_seconds"]:
        raise ValueError("Captions must cover the complete recording")
    font = font.resolve(strict=True)
    input_path = (MEDIA / "cityclean-demo.webm").resolve(strict=True)
    srt = "\n".join(
        f"{index}\n{timestamp(segment['start'])} --> {timestamp(segment['end'])}\n"
        f"{segment['stage']}\n{segment['text']}\n"
        for index, segment in enumerate(segments, start=1)
    )
    scratch = ROOT / "artifacts"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="demo-subtitles-", dir=scratch) as directory:
        work = Path(directory)
        shutil.copyfile(font, work / "caption-font.ttc")
        (work / "mode.txt").write_text(captions["mode_label"], encoding="utf-8")
        filters = [
            f"pad=iw:ih+{captions['caption_band_height']}:0:0:color=0x081722",
            "drawbox=x=0:y=768:w=iw:h=2:color=0x36c9b1:t=fill",
            "drawtext=fontfile=caption-font.ttc:textfile=mode.txt:fontsize=20:fontcolor=0x9dafba:x=w-tw-38:y=789",
        ]
        for index, segment in enumerate(segments):
            enabled = f"enable='gte(t,{segment['start']})*lt(t,{segment['end']})'"
            for field, size, color, y in [("stage", 22, "0x65dfc9", 787), ("text", 29, "0xf2f7fa", 825)]:
                name = f"{index}-{field}.txt"
                (work / name).write_text(segment[field], encoding="utf-8")
                filters.append(
                    f"drawtext=fontfile=caption-font.ttc:textfile={name}:expansion=none:"
                    f"fontsize={size}:fontcolor={color}:x=38:y={y}:{enabled}"
                )
        output = work / "captioned.mp4"
        subprocess.run([
            ffmpeg, "-hide_banner", "-i", str(input_path), "-vf", ",".join(filters),
            "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-an", str(output),
        ], cwd=work, check=True)
        os.replace(output, MEDIA / "cityclean-demo.mp4")
    (MEDIA / "cityclean-demo.zh-CN.srt").write_text(srt, encoding="utf-8")
    print(f"Rendered {len(segments)} caption segments: {MEDIA / 'cityclean-demo.mp4'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", default="ffmpeg", help="Path to FFmpeg with drawtext and libx264 support")
    parser.add_argument("--font", type=Path, required=True, help="Path to a font supporting Chinese glyphs")
    args = parser.parse_args()
    render(args.ffmpeg, args.font)
