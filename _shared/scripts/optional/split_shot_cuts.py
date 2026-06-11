#!/usr/bin/env python3
"""
split_shot_cuts.py — 멀티컷 스토리보드 영상 컷 분할 + 자식 샷 ID 부여 + 프레임 추출

⚠️ 소스가 PDF·콘티이미지가 아니라 "여러 컷이 든 영상"으로 들어올 때만 사용
   소스가 PDF/콘티이미지인 한 샷 = 한 컷 구조 프로젝트에서는 멀티컷 분할이
   필요 없어 사용하지 않는다.
   이 스크립트는 기술개발서(PDF) 04절 "헬퍼 스크립트 5종" 명세와 코드를
   일치시키고, "한 영상에 여러 컷이 붙은" 스토리보드 영상을 소스로 다룰 때
   쓰도록 동작하는 범용 툴로 제공한다.

목적
  한 개의 부모 샷 영상(예: S41_0010_v1.mp4) 안에 여러 컷이 들어있을 때,
  PySceneDetect(ContentDetector)로 컷 경계를 탐지하여
    1) 컷마다 자식 샷 ID를 부여하고
    2) 컷 시작 프레임을 ffmpeg로 추출하며
    3) 각 자식 샷의 Shotprompt.md 항목을 만들어 준다.
  결과는 .cut_split_cache.json 에 캐시해, 입력 영상이 바뀌지 않으면 재탐지를 건너뛴다.

자식 샷 ID 규약
  부모 0010 이 N개 컷으로 나뉘면:
    첫 컷  → 0010 (부모 번호 유지)
    이후    → 0011, 0012, ... (4자리, +10 간격의 빈 자리를 채움)
  컷이 9개를 넘으면 다음 십의 자리를 침범하므로 경고만 출력한다.

폴더/명명 규약 (PDF 트리)
  입력 :  Conti/{SEQ}/{SEQ}_{SHOT}/{SEQ}_{SHOT}_v{N}.mp4
  프레임:  Conti/{SEQ}/{SEQ}_{CHILD}/{SEQ}_{CHILD}-1_v1.png
  프롬프트: Image/{SEQ}/{SEQ}_{CHILD}/Shotprompt.md

사용법
  python3 split_shot_cuts.py S41 0010 [--threshold 27.0] [--force]
  python3 split_shot_cuts.py S41 all  [--threshold 27.0] [--force]

의존성
  - scenedetect  (pip install scenedetect)
  - ffmpeg       (brew install ffmpeg / apt install ffmpeg)
"""

import argparse
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

CACHE_FILE_NAME = ".cut_split_cache.json"


# ── 공통 헬퍼 (standalone) ───────────────────────────────────────────────────

def project_root() -> pathlib.Path:
    """config.md 가 있는 상위 디렉터리를 프로젝트 루트로 본다."""
    p = pathlib.Path(__file__).resolve().parent
    for cand in [p, *p.parents]:
        if (cand / "config.md").exists():
            return cand
    return p


def normalize_seq(seq_id: str) -> str:
    seq_id = seq_id.strip()
    if seq_id.isdigit():
        return f"S{int(seq_id):02d}"
    return seq_id if seq_id.upper().startswith("S") else f"S{seq_id}"


def pad_shot(shot: str) -> str:
    return f"{int(shot):04d}" if str(shot).isdigit() else str(shot)


def file_sig(path: pathlib.Path):
    """파일 변경 감지용 서명 (mtime:size). cache.file_sig 와 동일 규약."""
    if not path.exists():
        return None
    st = path.stat()
    return f"{st.st_mtime:.1f}:{st.st_size}"


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def require_dependencies():
    """scenedetect / ffmpeg 미설치 시 친절한 안내 후 종료."""
    missing = []
    try:
        import scenedetect  # noqa: F401
    except ImportError:
        missing.append(
            "• PySceneDetect 가 없습니다.  설치:  pip install scenedetect"
        )
    if shutil.which("ffmpeg") is None:
        missing.append(
            "• ffmpeg 가 없습니다.        설치:  brew install ffmpeg  (또는 apt install ffmpeg)"
        )
    if missing:
        print("필요한 외부 의존성이 없어 실행할 수 없습니다.\n", file=sys.stderr)
        for m in missing:
            print("  " + m, file=sys.stderr)
        print(
            "\n위 의존성을 설치한 뒤 다시 실행하세요.\n"
            "(split_shot_cuts.py 는 멀티컷 영상 분할 전용 — PDF/콘티이미지 입력 프로젝트에선 사용하지 않습니다.)",
            file=sys.stderr,
        )
        sys.exit(2)


# ── 캐시 ─────────────────────────────────────────────────────────────────────

class CutSplitCache:
    def __init__(self, root: pathlib.Path):
        self.path = root / CACHE_FILE_NAME
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        return {"_schema": "cut-split-v1", "_updated_at": 0.0, "videos": {}}

    def save(self):
        self.data["_updated_at"] = time.time()
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, key: str, sig: str):
        rec = self.data["videos"].get(key)
        if rec and rec.get("video_sig") == sig:
            return rec
        return None

    def set(self, key: str, sig: str, cuts: list, children: list):
        self.data["videos"][key] = {
            "video_sig": sig,
            "cuts": cuts,
            "children": children,
            "split_at": time.time(),
        }
        self.save()


# ── 컷 탐지 ──────────────────────────────────────────────────────────────────

def detect_cuts(video_path: pathlib.Path, threshold: float) -> list:
    """PySceneDetect로 컷 경계 탐지. (start_sec, end_sec) 리스트 반환."""
    from scenedetect import detect, ContentDetector

    scenes = detect(str(video_path), ContentDetector(threshold=threshold))
    if not scenes:
        # 컷이 하나도 안 잡히면 영상 전체를 한 컷으로 본다.
        return [(0.0, None)]
    return [(s.get_seconds(), e.get_seconds()) for s, e in scenes]


def child_shot_ids(parent: str, n: int) -> list:
    """부모 샷 번호에서 N개의 자식 샷 ID 생성. 0010 → [0010, 0011, ...]."""
    base = int(parent)
    ids = [f"{base + i:04d}" for i in range(n)]
    if n > 10:
        print(
            f"  ⚠️ 컷이 {n}개라 자식 샷 ID가 다음 샷 번호({base + 10:04d})를 침범할 수 있습니다.",
            flush=True,
        )
    return ids


def extract_frame(video_path: pathlib.Path, at_sec: float, out_path: pathlib.Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-ss", f"{at_sec:.3f}", "-i", str(video_path),
        "-vframes", "1", str(out_path), "-y",
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=False)


# ── Shotprompt 작성 ──────────────────────────────────────────────────────────

def write_child_shotprompt(root: pathlib.Path, seq: str, child: str, cut_idx: int, parent: str):
    sp_dir = root / "Image" / seq / f"{seq}_{child}"
    sp_dir.mkdir(parents=True, exist_ok=True)
    sp = sp_dir / "Shotprompt.md"
    if sp.exists() and sp.read_text(encoding="utf-8").strip():
        return  # 이미 내용 있으면 덮지 않음 (GenSetup 규칙과 동일)
    content = (
        f"# {seq}_{child} Shotprompt\n\n"
        f"- 부모 샷: {seq}_{parent} (멀티컷 분할 cut #{cut_idx + 1})\n"
        f"- 단일 프레임 모드 (start image only)\n"
        f"- 레퍼런스 프레임: {seq}_{child}-1_v1.png\n\n"
        f"(연출 의도를 한국어로 작성 → GenConti2Img/GenVideo가 영문 변환·합성)\n"
    )
    sp.write_text(content, encoding="utf-8")


# ── 단일 부모 샷 처리 ─────────────────────────────────────────────────────────

def split_one(root: pathlib.Path, seq: str, parent: str, threshold: float,
              cache: CutSplitCache, force: bool) -> bool:
    shot_dir = root / "Conti" / seq / f"{seq}_{parent}"
    videos = sorted(glob.glob(str(shot_dir / f"{seq}_{parent}_v*.mp4")))
    if not videos:
        print(f"SHOT_SKIP:{parent}:영상 없음 ({shot_dir}/{seq}_{parent}_v*.mp4)", flush=True)
        return False
    video_path = pathlib.Path(videos[-1])  # 최신 버전 사용
    sig = file_sig(video_path)
    cache_key = f"{seq}/{parent}"

    print(f"SHOT_START:{parent}", flush=True)

    cached = cache.get(cache_key, sig) if not force else None
    if cached:
        children = cached["children"]
        print(f"SHOT_CACHED:{parent}:{len(children)}컷 → {','.join(children)}", flush=True)
        return True

    cuts = detect_cuts(video_path, threshold)
    children = child_shot_ids(parent, len(cuts))

    for idx, ((start_sec, _end), child) in enumerate(zip(cuts, children)):
        frame_path = root / "Conti" / seq / f"{seq}_{child}" / f"{seq}_{child}-1_v1.png"
        extract_frame(video_path, start_sec, frame_path)
        write_child_shotprompt(root, seq, child, idx, parent)
        print(f"  CUT:{child}:@{start_sec:.2f}s → {frame_path.relative_to(root)}", flush=True)

    cache.set(cache_key, sig, [list(c) for c in cuts], children)
    print(f"SHOT_DONE:{parent}:{len(cuts)}컷 → {','.join(children)}", flush=True)
    return True


def all_parent_shots(root: pathlib.Path, seq: str) -> list:
    seq_dir = root / "Conti" / seq
    shots = set()
    for d in glob.glob(str(seq_dir / f"{seq}_[0-9]*")):
        m = re.match(rf"{re.escape(seq)}_(\d{{4}})$", pathlib.Path(d).name)
        if m:
            shots.add(m.group(1))
    return sorted(shots)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="split_shot_cuts.py",
        description="멀티컷 스토리보드 영상 컷 분할 + 자식 샷 + 프레임 추출 (소스가 영상일 때만 사용)",
    )
    p.add_argument("seq_id", help="시퀀스 ID (예: S41)")
    p.add_argument("shot", help="부모 샷 번호 (예: 0010) 또는 all")
    p.add_argument("--threshold", type=float, default=27.0, help="ContentDetector 임계값 (기본 27.0)")
    p.add_argument("--force", action="store_true", help="캐시 무시하고 재탐지")
    args = p.parse_args()

    require_dependencies()

    root = project_root()
    seq = normalize_seq(args.seq_id)
    cache = CutSplitCache(root)

    if args.shot == "all":
        parents = all_parent_shots(root, seq)
        if not parents:
            die(f"{root / 'Conti' / seq} 에서 부모 샷 폴더를 찾지 못했습니다.")
    else:
        parents = [pad_shot(args.shot)]

    ok = 0
    for parent in parents:
        if split_one(root, seq, parent, args.threshold, cache, args.force):
            ok += 1

    print(f"BATCH_DONE:{ok}:{len(parents) - ok}:0", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
