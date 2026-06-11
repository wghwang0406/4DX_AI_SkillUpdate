#!/usr/bin/env python3
"""
extract_motion_frames.py — 모션 분석용 다중 프레임 샘플 추출

목적
  하나의 mp4에서 일정 간격(기본 0.15초)으로 프레임을 다수 추출한다.
  GenVideo 등에서 "이 영상이 어떻게 움직이는가"를 Vision으로 분석하기 위한
  입력 프레임 세트를 만든다. (첫/끝 1프레임만 뽑는 GenSetup 과 달리, 동작
  궤적을 보기 위해 촘촘히 샘플링)

사용법
  python3 extract_motion_frames.py <mp4경로> [--interval 0.15] [--out <디렉터리>]
    --interval : 프레임 간격(초). 기본 0.15
    --out      : 출력 디렉터리. 기본 /tmp/{영상이름}_motion/

출력
  <out>/frame_001.png, frame_002.png ...
  stdout 으로 출력 디렉터리와 추출 프레임 개수/목록을 보고한다.

의존성
  - ffmpeg  (brew install ffmpeg / apt install ffmpeg)
"""

import argparse
import glob
import pathlib
import shutil
import subprocess
import sys


def require_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print(
            "필요한 외부 의존성이 없어 실행할 수 없습니다.\n\n"
            "  • ffmpeg 가 없습니다.  설치:  brew install ffmpeg  (또는 apt install ffmpeg)\n\n"
            "설치한 뒤 다시 실행하세요.",
            file=sys.stderr,
        )
        sys.exit(2)


def main():
    p = argparse.ArgumentParser(
        prog="extract_motion_frames.py",
        description="mp4에서 일정 간격(기본 0.15s) 프레임 다중 추출 (모션 분석용)",
    )
    p.add_argument("video", help="mp4 파일 경로")
    p.add_argument("--interval", type=float, default=0.15, help="프레임 간격(초), 기본 0.15")
    p.add_argument("--out", default="", help="출력 디렉터리 (기본 /tmp/{이름}_motion/)")
    args = p.parse_args()

    require_ffmpeg()

    video = pathlib.Path(args.video).expanduser()
    if not video.exists():
        print(f"ERROR: 영상 파일을 찾을 수 없습니다: {video}", file=sys.stderr)
        return 1
    if args.interval <= 0:
        print("ERROR: --interval 은 0보다 커야 합니다.", file=sys.stderr)
        return 1

    out_dir = pathlib.Path(args.out) if args.out else pathlib.Path("/tmp") / f"{video.stem}_motion"
    out_dir.mkdir(parents=True, exist_ok=True)
    # 기존 프레임 정리 (이전 실행 잔여물 제거)
    for old in glob.glob(str(out_dir / "frame_*.png")):
        pathlib.Path(old).unlink()

    fps = 1.0 / args.interval  # 0.15초 간격 ≈ 6.67fps
    cmd = [
        "ffmpeg", "-i", str(video),
        "-vf", f"fps={fps:.6f}",
        str(out_dir / "frame_%03d.png"), "-y",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR: ffmpeg 실패\n{r.stderr.strip()[:500]}", file=sys.stderr)
        return 1

    frames = sorted(glob.glob(str(out_dir / "frame_*.png")))
    print(f"OUT_DIR:{out_dir}", flush=True)
    print(f"FRAMES:{len(frames)} (interval={args.interval}s, fps={fps:.2f})", flush=True)
    for f in frames:
        print(f"  {pathlib.Path(f).name}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
