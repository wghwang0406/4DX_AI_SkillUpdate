#!/usr/bin/env python3
"""
genconti2img_minimal.py — runner 없는 최소 i2i 배치 (standalone)

목적
  runner.py / 캐시 / shotlist 갱신 없이, 콘티 폴더를 순회하며 각 샷을
  콘티 + 캐릭터시트 레퍼런스로 직접 i2i 생성하는 "가장 단순한 참조 구현".
  복잡한 프롬프트 합성/캐시 검증 없이 동작 원리를 한눈에 보여주는 용도다.
  (정식 서비스에서는 백엔드 기능으로 흡수)

  ※ 의도적으로 어떤 프로젝트 모듈(runner / cache)도 import 하지 않는다.
     이 파일 하나만으로 완결되도록 모든 헬퍼를 인라인으로 둔다.

폴더/명명 규약 (PDF 트리)
  콘티 :  Conti/{SEQ}/{SEQ}_{SHOT}/{SEQ}_{SHOT}-1_v*.png  (없으면 Conti/{SEQ}/{SEQ}_{SHOT}_v*.png)
  시트 :  character/{이름}_Character_v*.png
  출력 :  Image/{SEQ}/{SEQ}_{SHOT}/{SEQ}_{SHOT}-1_v1.png

사용법
  python3 genconti2img_minimal.py S41 [--model gpt] [--dry-run]

의존성
  - higgsfield CLI
"""

import argparse
import glob
import json
import pathlib
import re
import subprocess
import sys
import urllib.request

MODEL_MAP = {
    "gpt": "gpt_image_2",
    "nano": "nano_banana_2",
    "cinema": "cinematic_studio_2_5",
}


def project_root() -> pathlib.Path:
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


def find_conti(root: pathlib.Path, seq: str, shot: str):
    shot_dir = root / "Conti" / seq / f"{seq}_{shot}"
    for base in (shot_dir, root / "Conti" / seq):
        for pattern in (f"{seq}_{shot}-1_v*.png", f"{seq}_{shot}_v*.png"):
            matches = sorted(glob.glob(str(base / pattern)))
            if matches:
                return pathlib.Path(matches[-1])
    return None


def list_shots(root: pathlib.Path, seq: str) -> list:
    shots = set()
    for d in glob.glob(str(root / "Conti" / seq / f"{seq}_[0-9]*")):
        m = re.search(rf"{re.escape(seq)}_(\d{{4}})", pathlib.Path(d).name)
        if m:
            shots.add(m.group(1))
    return sorted(shots)


def run_higgsfield(model_id: str, conti: pathlib.Path, sheets: list) -> tuple:
    prompt = (
        "Recreate this storyboard frame as a photorealistic cinematic still. "
        "Use the storyboard for composition only; match all character appearance "
        "to the provided character sheet references. 16:9."
    )
    cmd = ["higgsfield", "generate", "create", model_id, "--prompt", prompt, "--image", str(conti)]
    for s in sheets:
        cmd += ["--image", str(s)]
    cmd += ["--aspect_ratio", "16:9", "--quality", "high", "--resolution", "2k",
            "--wait", "--wait-timeout", "10m"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=660)
    except FileNotFoundError:
        return None, "higgsfield CLI를 찾을 수 없습니다 (설치/PATH 확인)"
    except subprocess.TimeoutExpired:
        return None, "timeout (11m)"
    if r.returncode != 0:
        return None, (r.stderr.strip() or r.stdout.strip() or f"exit {r.returncode}")[:300]
    raw = r.stdout.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            data = data[0]
        url = data.get("result_url") or data.get("output_url") or data.get("url") or data.get("image_url")
        if url:
            return url, None
    except (json.JSONDecodeError, IndexError, TypeError, AttributeError):
        pass
    m = re.search(r"https://\S+\.(?:png|jpg|webp)", raw)
    return (m.group(0), None) if m else (None, "결과 URL 없음")


def main():
    p = argparse.ArgumentParser(
        prog="genconti2img_minimal.py",
        description="runner 없는 최소 콘티→씬 이미지 i2i 배치 (standalone)",
    )
    p.add_argument("seq_id", help="시퀀스 ID (예: S41)")
    p.add_argument("--model", default="gpt", help="gpt | nano | cinema (기본 gpt)")
    p.add_argument("--dry-run", action="store_true", help="API 호출 없이 대상만 출력")
    args = p.parse_args()

    root = project_root()
    seq = normalize_seq(args.seq_id)
    model_id = MODEL_MAP.get(args.model, args.model)

    shots = list_shots(root, seq)
    if not shots:
        print(f"ERROR: {root / 'Conti' / seq} 에서 콘티 샷을 찾지 못했습니다.", file=sys.stderr)
        return 1

    sheets = [pathlib.Path(s) for s in sorted(glob.glob(str(root / "character" / "*_Character_v*.png")))]
    print(f"대상: {seq} {len(shots)}샷 | model={model_id} | 캐릭터시트 {len(sheets)}장", flush=True)

    success = fail = skipped = 0
    for shot in shots:
        conti = find_conti(root, seq, shot)
        if conti is None:
            print(f"SHOT_FAIL:{shot}:콘티 이미지 없음", flush=True)
            fail += 1
            continue
        dest = root / "Image" / seq / f"{seq}_{shot}" / f"{seq}_{shot}-1_v1.png"
        if dest.exists():
            print(f"SHOT_SKIP:{shot}:{dest.relative_to(root)} (이미 존재)", flush=True)
            skipped += 1
            continue
        if args.dry_run:
            print(f"SHOT_DRY:{shot}:model={model_id} conti={conti.relative_to(root)} "
                  f"sheets={len(sheets)} → {dest.relative_to(root)}", flush=True)
            success += 1
            continue
        url, err = run_higgsfield(model_id, conti, sheets)
        if err:
            print(f"SHOT_FAIL:{shot}:{err}", flush=True)
            fail += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            urllib.request.urlretrieve(url, str(dest))
        except Exception as e:  # noqa: BLE001
            print(f"SHOT_FAIL:{shot}:다운로드 실패 {e} (url={url})", flush=True)
            fail += 1
            continue
        print(f"SHOT_DONE:{shot}:{dest.relative_to(root)} ({url})", flush=True)
        success += 1

    print(f"BATCH_DONE:{success}:{fail}:{skipped}", flush=True)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
