#!/usr/bin/env python3
"""
gen_helper.py — 최종 씬 이미지 배치 생성 헬퍼 (스레드 4 + --rerun)

목적
  콘티(구도) + 캐릭터시트 + 배경을 레퍼런스로 묶어, 한 시퀀스의 여러 샷
  최종 씬 이미지를 ThreadPoolExecutor 로 병렬(기본 4스레드) 배치 생성한다.
  GenConti2Img 스킬/runner 와 같은 산출물을 만들되, 스레드 병렬과 v2 재생성에
  특화된 가벼운 보조 스크립트다. (정식 서비스에서는 백엔드 기능으로 흡수)

폴더/명명 규약 (PDF 트리)
  콘티 :  Conti/{SEQ}/{SEQ}_{SHOT}/{SEQ}_{SHOT}-1_v*.png  (없으면 Conti/{SEQ}/{SEQ}_{SHOT}_v*.png)
  배경 :  Image/{SEQ}/{SEQ}_Background.png
  씬   :  Image/{SEQ}/Sceneprompt.md
  샷   :  Image/{SEQ}/{SEQ}_{SHOT}/Shotprompt.md
  시트 :  character/{이름}_Character_v*.png
  출력 :  Image/{SEQ}/{SEQ}_{SHOT}/{SEQ}_{SHOT}-1_v{N}.png

사용법
  python3 gen_helper.py S41 [0010 0020 ...] [--model gpt] [--workers 4] [--rerun] [--dry-run]
    (샷 생략 시 콘티 폴더 전체)
  --rerun   : 기존 최고 버전 +1 (v2, v3 ...)로 재생성
  --dry-run : higgsfield 호출 없이 대상 샷/경로/프롬프트 길이만 출력

의존성
  - higgsfield CLI  (이미지 생성)
  - ffmpeg 불필요
"""

import argparse
import concurrent.futures
import glob
import json
import pathlib
import re
import subprocess
import sys
import urllib.request

# ── 공통 헬퍼 (standalone) ───────────────────────────────────────────────────

def project_root() -> pathlib.Path:
    p = pathlib.Path(__file__).resolve().parent
    for cand in [p, *p.parents]:
        if (cand / "config.md").exists():
            return cand
    return p


# 모델 표는 프로젝트 루트의 models.py 가 단일 출처다.
# 이 파일은 scripts/ 아래에 놓이므로 루트를 sys.path 에 넣고 가져온다.
# models.py 가 없는 구버전 프로젝트에서도 죽지 않도록 폴백을 둔다.
sys.path.insert(0, str(project_root()))
try:
    from models import MODEL_MAP, image_flags
except ImportError:                                        # models.py 미배포 프로젝트
    MODEL_MAP = {
        "gpt": "gpt_image_2",
        "nano": "nano_banana_2",
        "cinema": "cinematic_studio_2_5",
    }

    def image_flags(model_id, quality="high", resolution="2k"):
        # gpt 만 --quality 를 받는다. 나머지는 붙이면 CLI가 거부한다.
        if model_id in ("gpt_image_2",):
            return ["--quality", quality, "--resolution", resolution]
        if model_id in ("text2image_soul_v2", "soul_cinematic", "soul_cinema_studio"):
            return ["--quality", "2k"]
        if model_id in ("seedream_v4_5",):
            return ["--quality", "high"]
        return ["--resolution", resolution]


def normalize_seq(seq_id: str) -> str:
    seq_id = seq_id.strip()
    if seq_id.isdigit():
        return f"S{int(seq_id):02d}"
    return seq_id if seq_id.upper().startswith("S") else f"S{seq_id}"


def pad_shot(shot: str) -> str:
    return f"{int(shot):04d}" if str(shot).isdigit() else str(shot)


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


# ── 입력 수집 ────────────────────────────────────────────────────────────────

def find_conti(root: pathlib.Path, seq: str, shot: str):
    """샷별 콘티 이미지 1장을 찾는다. -1 프레임 우선, 없으면 평이름."""
    shot_dir = root / "Conti" / seq / f"{seq}_{shot}"
    for pattern in (f"{seq}_{shot}-1_v*.png", f"{seq}_{shot}_v*.png"):
        matches = sorted(glob.glob(str(shot_dir / pattern)))
        if matches:
            return pathlib.Path(matches[-1])
    # 서브폴더가 없는 평면 배치도 보조 지원
    for pattern in (f"{seq}_{shot}-1_v*.png", f"{seq}_{shot}_v*.png"):
        matches = sorted(glob.glob(str(root / "Conti" / seq / pattern)))
        if matches:
            return pathlib.Path(matches[-1])
    return None


def all_shots(root: pathlib.Path, seq: str) -> list:
    seq_dir = root / "Conti" / seq
    shots = set()
    # 서브폴더형 + 평면형 둘 다 스캔
    for d in glob.glob(str(seq_dir / f"{seq}_[0-9]*")):
        m = re.search(rf"{re.escape(seq)}_(\d{{4}})", pathlib.Path(d).name)
        if m:
            shots.add(m.group(1))
    return sorted(shots)


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def char_sheets(root: pathlib.Path) -> list:
    """캐릭터 시트를 찾는다.

    GenSetup v5.2 는 `{EP}/character/char/{이름}_Character_sheet_v1.png` 에 쓴다.
    예전 평면 배치(`character/{이름}_Character_v1.png`)도 아직 쓰이므로 둘 다 본다.
    (구버전 글로브는 GenSetup 레이아웃과 어긋나 항상 빈 리스트를 돌려줬다 —
     그런데 프롬프트는 "시트 레퍼런스를 따르라"고 말하고 있었다.)
    """
    patterns = [
        root / "character" / "char" / "*_Character_*_v*.png",   # v5.2 레이아웃
        root / "*" / "character" / "char" / "*_Character_*_v*.png",  # {EP}/ 하위
        root / "character" / "*_Character_v*.png",              # 레거시 평면
    ]
    hits = []
    for pat in patterns:
        hits = sorted(glob.glob(str(pat)))
        if hits:
            break
    return [pathlib.Path(p) for p in hits]


def next_version(out_dir: pathlib.Path, seq: str, shot: str, rerun: bool) -> int:
    existing = sorted(glob.glob(str(out_dir / f"{seq}_{shot}-1_v*.png")))
    if not existing:
        return 1
    vmax = max(int(re.search(r"_v(\d+)\.png$", p).group(1)) for p in existing)
    return vmax + 1 if rerun else vmax  # rerun 아니면 최고 버전 = 이미 존재 → 스킵 신호


# ── 프롬프트 합성 ────────────────────────────────────────────────────────────

def english_lines(text: str) -> str:
    """MD에서 영문 줄만 추린다.

    Sceneprompt/Shotprompt 는 규격상 한국어다(CLAUDE.md). 그런데 최종 프롬프트는
    영문이어야 한다(Cinedance: "must be written in clear cinematic English").
    이 헬퍼는 모델 없이 도는 standalone 이라 번역을 못 하므로, 한국어를 통째로
    실어 보내는 대신 영문 줄만 남긴다. 마크다운 헤더도 뺀다
    (Lira: 생성 프롬프트에 ALL-CAPS 섹션 헤더를 쓰지 않는다).
    """
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(">") or s.startswith("|"):
            continue
        hangul = sum(1 for c in s if "가" <= c <= "힣")
        if hangul == 0:
            out.append(s)
    return "\n".join(out).strip()


def build_prompt(root: pathlib.Path, seq: str, shot: str) -> str:
    """콘티→씬 이미지 i2i 프롬프트.

    원문 규칙 적용:
      - 화면비는 **CLI 파라미터**로만 넘긴다. 프롬프트 텍스트에 `16:9`를 쓰지 않는다 (Lira)
      - 키워드 스택(`photorealistic cinematic`) 대신 자연스러운 산문으로 쓴다 (Lira)
      - 캐릭터 외형은 기술하지 않는다 — 시트 레퍼런스가 담당한다
      - 레퍼런스 계층: 콘티는 **구도만**, 외형은 시트, 색·아트스타일은 상속하지 않는다
    """
    scene = english_lines(read_text(root / "Image" / seq / "Sceneprompt.md"))
    shotp = english_lines(read_text(root / "Image" / seq / f"{seq}_{shot}" / "Shotprompt.md"))
    parts = []
    if scene:
        parts.append(scene)
    if shotp:
        parts.append(shotp)
    parts.append(
        "Recreate this storyboard frame as a photographic cinematic still. "
        "Take shot size, camera angle and composition from the storyboard only. "
        "Follow the character reference sheets exactly for face, build, hair and wardrobe. "
        "Clean plate with unmarked surfaces."
    )
    return "\n\n".join(parts)


# ── higgsfield 호출 ──────────────────────────────────────────────────────────

def build_cmd(model_id: str, prompt: str, images: list) -> list:
    cmd = ["higgsfield", "generate", "create", model_id, "--prompt", prompt]
    for img in images:
        cmd += ["--image", str(img)]
    cmd += [
        "--aspect_ratio", "16:9",
        *image_flags(model_id, quality="high", resolution="2k"),
        "--wait", "--wait-timeout", "10m",
    ]
    return cmd


def run_job(cmd: list):
    """(url, error) 반환."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=660)
    except subprocess.TimeoutExpired:
        return None, "timeout (11m)"
    except FileNotFoundError:
        return None, "higgsfield CLI를 찾을 수 없습니다 (설치/PATH 확인)"
    if r.returncode != 0:
        return None, (r.stderr.strip() or r.stdout.strip() or f"exit {r.returncode}")[:300]
    raw = r.stdout.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            data = data[0]
        url = (data.get("result_url") or data.get("output_url") or data.get("url")
               or data.get("image_url"))
        if url:
            return url, None
    except (json.JSONDecodeError, IndexError, TypeError, AttributeError):
        pass
    m = re.search(r"https://\S+\.(?:png|jpg|webp)", raw)
    return (m.group(0), None) if m else (None, "결과 URL 없음")


def download(url: str, dest: pathlib.Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, str(dest))


# ── 샷 1개 작업 (스레드 워커) ─────────────────────────────────────────────────

def process_shot(root: pathlib.Path, seq: str, shot: str, model_id: str,
                 sheets: list, rerun: bool, dry_run: bool) -> str:
    conti = find_conti(root, seq, shot)
    if conti is None:
        return f"SHOT_FAIL:{shot}:콘티 이미지 없음"

    out_dir = root / "Image" / seq / f"{seq}_{shot}"
    v = next_version(out_dir, seq, shot, rerun)
    dest = out_dir / f"{seq}_{shot}-1_v{v}.png"

    if dest.exists() and not rerun:
        return f"SHOT_SKIP:{shot}:{dest.relative_to(root)} (이미 존재, --rerun 으로 재생성)"

    background = root / "Image" / seq / f"{seq}_Background.png"
    images = []
    if background.exists():
        images.append(background)
    images.append(conti)
    images.extend(sheets)

    prompt = build_prompt(root, seq, shot)

    if dry_run:
        return (f"SHOT_DRY:{shot}:model={model_id} v{v} refs={len(images)} "
                f"prompt_len={len(prompt)} → {dest.relative_to(root)}")

    cmd = build_cmd(model_id, prompt, images)
    url, err = run_job(cmd)
    if err:
        return f"SHOT_FAIL:{shot}:{err}"
    try:
        download(url, dest)
    except Exception as e:  # noqa: BLE001
        return f"SHOT_FAIL:{shot}:다운로드 실패 {e} (url={url})"
    return f"SHOT_DONE:{shot}:{dest.relative_to(root)} ({url})"


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="gen_helper.py",
        description="최종 씬 이미지 배치 생성 (스레드 병렬 + --rerun)",
    )
    p.add_argument("seq_id", help="시퀀스 ID (예: S41)")
    p.add_argument("shots", nargs="*", help="샷 번호들 (생략 시 콘티 폴더 전체)")
    p.add_argument("--model", default="gpt", help="gpt | nano | cinema (기본 gpt)")
    p.add_argument("--workers", type=int, default=4, help="동시 스레드 수 (기본 4)")
    p.add_argument("--rerun", action="store_true", help="기존 최고 버전 +1로 재생성")
    p.add_argument("--dry-run", action="store_true", help="API 호출 없이 대상만 출력")
    args = p.parse_args()

    root = project_root()
    seq = normalize_seq(args.seq_id)
    model_id = MODEL_MAP.get(args.model, args.model)

    shots = [pad_shot(s) for s in args.shots] if args.shots else all_shots(root, seq)
    if not shots:
        die(f"{root / 'Conti' / seq} 에서 콘티 샷을 찾지 못했습니다.")

    sheets = char_sheets(root)
    print(f"대상: {seq} {len(shots)}샷 | model={model_id} | workers={args.workers} | "
          f"캐릭터시트 {len(sheets)}장 | rerun={args.rerun}", flush=True)

    success = fail = skipped = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(process_shot, root, seq, s, model_id, sheets, args.rerun, args.dry_run): s
            for s in shots
        }
        for fut in concurrent.futures.as_completed(futures):
            line = fut.result()
            print(line, flush=True)
            if line.startswith("SHOT_DONE") or line.startswith("SHOT_DRY"):
                success += 1
            elif line.startswith("SHOT_SKIP"):
                skipped += 1
            else:
                fail += 1

    print(f"BATCH_DONE:{success}:{fail}:{skipped}", flush=True)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
