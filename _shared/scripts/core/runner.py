#!/usr/bin/env python3
"""
runner.py — 반복 처리 CLI 러너
순수 stdlib, Python 3.9+.

사용법:
  python3 runner.py genvideo S41 0010-0030 [--model kling3_0] [--force] [--dry-run]
  python3 runner.py genconti2img S41 [all|0010-0030] [--model gpt] [--force] [--dry-run]
  python3 runner.py status S41
  python3 runner.py cache-info S41 [--shots 0010,0020]
  python3 runner.py cache-invalidate S41 [--shots 0010,0020]

stdout 프로토콜 (Claude가 파싱):
  SHOT_START:0010
  SHOT_DONE:0010:https://...
  SHOT_SKIP:0010:https://...
  SHOT_FAIL:0010:error message
  SHOT_DRY:0010:info
  BATCH_DONE:success:fail:skipped
"""

import argparse
import glob
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

from cache import CacheManager, ShotlistUpdater

MODEL_MAP = {
    "gpt": "gpt_image_2",
    "nano": "nano_banana_2",
    "cinema": "cinematic_studio_2_5",
    "kling": "kling3_0",
    "kling3_0": "kling3_0",
    "seedance": "seedance_2_0",
    "seedance_2_0": "seedance_2_0",
}


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def die(code: int, msg: str):
    print(f"ERROR:{msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def normalize_seq(seq_id: str) -> str:
    seq_id = seq_id.strip()
    if seq_id.isdigit():
        return f"S{int(seq_id):02d}"
    return seq_id if seq_id.upper().startswith("S") else f"S{seq_id}"


def resolve_episode(config: dict, seq_id: str) -> str:
    ep = config["episode_map"].get(seq_id)
    if not ep:
        die(2, f"Episode mapping not found for {seq_id} in config.md")
    return ep


# ── config.md 파싱 ───────────────────────────────────────────────────────────

def load_config() -> dict:
    cfg = ROOT / "config.md"
    if not cfg.exists():
        die(2, "config.md를 찾을 수 없습니다. /GenSetup을 먼저 실행하세요.")
    text = cfg.read_text(encoding="utf-8")
    project_code, project_title = "", ""
    episode_map = {}
    in_table = False
    for line in text.splitlines():
        if line.startswith("project_code:"):
            project_code = line.split(":", 1)[1].strip()
        elif line.startswith("project_title:"):
            project_title = line.split(":", 1)[1].strip()
        stripped = line.strip()
        if stripped.startswith("| S") or stripped.startswith("|S"):
            parts = [p.strip() for p in stripped.strip("|").split("|")]
            if len(parts) >= 2 and parts[0].startswith("S") and parts[1].startswith("EP"):
                episode_map[parts[0]] = parts[1]
        elif "Sequence" in line and "|" in line:
            in_table = True
        elif in_table and stripped.startswith("|") and not stripped.startswith("|---"):
            parts = [p.strip() for p in stripped.strip("|").split("|")]
            if len(parts) >= 2 and parts[0] and parts[1]:
                episode_map[parts[0]] = parts[1]
    return {
        "project_code": project_code,
        "project_title": project_title,
        "episode_map": episode_map,
    }


# ── 샷 스펙 확장 ──────────────────────────────────────────────────────────────

def expand_shot_spec(spec: str, ep: str, seq: str, workflow: str) -> list:
    if workflow == "genconti2img":
        img_dir = ROOT / ep / "Conti" / seq
    else:
        img_dir = ROOT / ep / "Image" / seq

    if spec == "all":
        # 파일명은 두 형태를 다 쓴다: "0010_v1.png" 와 "{SEQ}_0010_v1.png".
        # 접두사 있는 쪽만 쓰는 프로젝트에서 all이 빈 목록을 내던 문제 때문에 둘 다 본다.
        files = glob.glob(str(img_dir / "[0-9]*.png")) + glob.glob(str(img_dir / f"{seq}_[0-9]*.png"))
        nums = set()
        for f in files:
            name = pathlib.Path(f).name
            if name.startswith(f"{seq}_"):
                name = name[len(seq) + 1:]
            m = re.match(r"(\d{4})", name)
            if m:
                nums.add(m.group(1))
        return sorted(nums)

    if "-" in spec and not spec.startswith("-"):
        parts = spec.split("-", 1)
        if parts[0].isdigit() and parts[1].isdigit():
            start, end = int(parts[0]), int(parts[1])
            return [f"{n:04d}" for n in range(start, end + 1, 10)]

    if "," in spec:
        return [f"{int(s):04d}" if s.strip().isdigit() else s.strip() for s in spec.split(",")]

    if spec.isdigit():
        return [f"{int(spec):04d}"]

    return [spec]


# ── 경로 헬퍼 ────────────────────────────────────────────────────────────────

def shotlist_path(ep: str, seq: str) -> pathlib.Path:
    return ROOT / ep / "Conti" / seq / f"shotlist_{seq}.md"


def urls_path(ep: str, seq: str) -> pathlib.Path:
    return ROOT / ep / "Conti" / seq / f"urls_{seq}.md"


def next_version(ep: str, seq: str, shot: str, ext: str) -> int:
    folder = "Video" if ext == "mp4" else "Image"
    v = 1
    while (ROOT / ep / folder / seq / f"{shot}_v{v}.{ext}").exists():
        v += 1
    return v


# ── Higgsfield 커맨드 빌더 ───────────────────────────────────────────────────

# CINEDANCE V4 최종 프롬프트 아키텍처 (섹션 순서 고정).
# (캐시 키, 출력 라벨) — 값이 빈 섹션은 출력에서 생략한다.
CINEDANCE_SECTIONS = [
    ("scene_context", "SCENE CONTEXT"),
    ("active_refs", "ACTIVE REFERENCES"),
    ("location_map", "LOCATION MAP"),
    ("first_frame", "FIRST FRAME AND SPATIAL BLOCKING"),
    ("format_mode", "FORMAT MODE"),
    ("optics", "OPTICS"),
    ("camera", "CAMERA"),
    ("action_timing", "ACTION TIMING"),
    ("physics", "PHYSICS"),
    ("lighting", "LIGHTING"),
    ("style", "STYLE"),
    ("audio", "AUDIO"),
    ("positive_constraints", "POSITIVE CONSTRAINTS"),
]


def compose_video_prompt(shot: dict, project: dict = None, sequence: dict = None) -> str:
    """캐시에서 영상 프롬프트를 CINEDANCE 12섹션 순서로 조립.

    상수는 샷에 복붙하지 않고 상위 레벨에서 끌어온다:
      - STYLE       ← 프로젝트 `style_en`        (한 곳 고치면 전 샷 반영)
      - LOCATION MAP← 시퀀스 `location_map_en`   (장면당 한 번, 모든 컷에 붙음)
    샷이 같은 이름의 값을 직접 갖고 있으면 그쪽이 우선한다.

    ACTING은 별도 섹션을 만들지 않고 CINEDANCE 구조 안에 넣는다:
      - `acting_en` → ACTION TIMING 본문 뒤에 이어붙임 (연기 = 행동 레이어)
      - `voice_en`  → AUDIO 본문 뒤에 verbatim 으로 이어붙임

    12섹션이 하나도 없으면 레거시 3슬롯(scene_en/shot_dir_en/vision_en)으로,
    그것도 없으면 레거시 단일 `prompt`로 폴백한다 (기존 캐시/genconti2img 호환).
    """
    project = project or {}
    sequence = sequence or {}

    values = {}
    for key, _label in CINEDANCE_SECTIONS:
        values[key] = (shot.get(key) or "").strip()

    # 상위 레벨 상수 주입 (샷이 직접 갖고 있으면 샷 우선)
    if not values["style"]:
        values["style"] = (project.get("style_en") or "").strip()
    if not values["location_map"]:
        values["location_map"] = (sequence.get("location_map_en") or "").strip()

    # ACTING 병합
    acting = (shot.get("acting_en") or "").strip()
    if acting:
        values["action_timing"] = "\n".join(x for x in (values["action_timing"], acting) if x)
    voice = (shot.get("voice_en") or "").strip()
    if voice:
        values["audio"] = "\n".join(x for x in (values["audio"], voice) if x)

    if any(values.values()):
        parts = []
        for key, label in CINEDANCE_SECTIONS:
            if values[key]:
                parts.append(f"{label}\n{values[key]}")
        return "\n\n".join(parts)

    # ── 레거시 폴백 ──────────────────────────────────────────────────────────
    scene = (shot.get("scene_en") or "").strip()
    shot_dir = (shot.get("shot_dir_en") or "").strip()
    vision = (shot.get("vision_en") or "").strip()

    if not (scene or shot_dir or vision):
        return (shot.get("prompt") or "").strip()

    parts = []
    if scene:
        parts.append(scene)
    if shot_dir:
        parts.append(f"Camera & motion: {shot_dir}")
    if vision:
        parts.append(f"Action: {vision}")
    return "\n".join(parts)


# 한 샷에 붙일 수 있는 이미지 총량 (Seedance 2.0 제약, start/end 포함).
# `higgsfield model get seedance_2_0` → "at most 9 image references are allowed
# (counting start_image and end_image)"
MAX_IMAGES_SEEDANCE = 9
REF_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def find_shot_media(ep: str, seq: str, shot: str) -> tuple:
    """샷의 (keyframes, refs)를 ROOT 기준 상대경로 리스트로 반환.

    keyframes — **순서 있는** 키프레임. `{SEQ}_{SHOT}-N_v*.png` 의 N이 시간 순서다.
                개수 제한 없음(-1, -2, -3 …). 하나도 없으면 `{SEQ}_{SHOT}_v*.png` 한 장.
    refs      — **순서 없는** 레퍼런스. `{SEQ}_{SHOT}_ref/` 폴더 안의 이미지 전부.
                이 폴더는 무조건 레퍼런스이며 키프레임이 되는 일이 없다.

    같은 N에 여러 버전이 있으면 `_v` 최대본을 쓴다(_newest 재사용).
    """
    d = ROOT / ep / "Image" / seq

    by_index = {}
    for f in glob.glob(str(d / f"{seq}_{shot}-*_v*.png")):
        m = re.fullmatch(rf"{re.escape(seq)}_{re.escape(shot)}-(\d+)_v(\d+)\.png",
                         pathlib.Path(f).name)
        if m:
            by_index.setdefault(int(m.group(1)), []).append(f)
    keyframes = [_newest(by_index[n]) for n in sorted(by_index)]

    if not keyframes:
        single = _newest(glob.glob(str(d / f"{seq}_{shot}_v*.png")))
        keyframes = [single] if single else []

    refs = sorted(
        p for p in glob.glob(str(d / f"{seq}_{shot}_ref" / "*"))
        if pathlib.Path(p).suffix.lower() in REF_EXTS
    )

    rel = lambda p: str(pathlib.Path(p).relative_to(ROOT))
    return [rel(k) for k in keyframes], [rel(r) for r in refs]


def build_genvideo_cmd(model: str, prompt: str, keyframes: list, refs: list) -> list:
    """키프레임(순서) + 레퍼런스(무순서)를 CLI 미디어 플래그로 조립.

    키프레임 1장  → --start-image
    키프레임 2장  → --start-image / --end-image
    키프레임 3장+ → --start-image / 중간은 --image / --end-image
    refs          → 전부 --image (키프레임 뒤에 붙음)

    Kling 3.0은 파라미터에 image_references가 없어 start/end만 받는다.
    """
    def abs_path(p):
        return str(p) if pathlib.Path(p).is_absolute() else str(ROOT / p)

    cmd = [
        "higgsfield", "generate", "create", model,
        "--prompt", prompt,
        "--aspect_ratio", "16:9",
        "--duration", "5",
        "--wait", "--wait-timeout", "20m",
    ]
    if model == "kling3_0":
        cmd += ["--mode", "pro"]

    k = [abs_path(x) for x in keyframes]
    if not k:
        return cmd

    if len(k) == 1:
        cmd += ["--start-image", k[0]]
    else:
        cmd += ["--start-image", k[0]]
        for mid in k[1:-1]:
            cmd += ["--image", mid]
        cmd += ["--end-image", k[-1]]

    for r in refs:
        cmd += ["--image", abs_path(r)]
    return cmd


def plan_shot_media(model: str, keyframes: list, refs: list, forced_model: bool = False):
    """모델 제약에 맞춰 (model, keyframes, refs, 경고목록)을 정리한다.

    - Kling은 start/end 2장만 받는다. 키프레임 3장 이상이면 Seedance로 바꾼다
      (사용자가 모델을 명시했으면 바꾸지 않고 첫/끝만 쓴다).
    - Kling은 image_references 파라미터가 없어 refs를 못 받는다.
    - Seedance는 start/end 포함 이미지 총 9장까지.
    """
    warn = []
    kf, rf = list(keyframes), list(refs)

    if model == "kling3_0" and len(kf) > 2:
        if forced_model:
            warn.append(f"키프레임 {len(kf)}장 중 첫/끝 2장만 사용됩니다 (Kling은 중간 키프레임을 받지 않음)")
            kf = [kf[0], kf[-1]]
        else:
            model = "seedance_2_0"
            warn.append(f"키프레임 {len(kf)}장 — Kling은 2장까지라 Seedance 2.0으로 전환합니다")

    if model == "kling3_0" and rf:
        warn.append(f"레퍼런스 {len(rf)}장은 Kling이 받지 않아 제외됩니다 (Seedance를 쓰세요)")
        rf = []

    total = len(kf) + len(rf)
    if total > MAX_IMAGES_SEEDANCE:
        drop = total - MAX_IMAGES_SEEDANCE
        rf = rf[: max(0, len(rf) - drop)]
        warn.append(f"이미지 총 {total}장 — 상한 {MAX_IMAGES_SEEDANCE}장이라 레퍼런스 {drop}장을 뺐습니다")

    return model, kf, rf, warn


# ── 에셋 뷰 선택 ─────────────────────────────────────────────────────────────
# 샷 사이즈에 맞는 레퍼런스 뷰를 고른다. 클로즈업에 와이드 배경을 물리면
# 공간이 안 맞고, 원경에 얼굴 클로즈업을 물리면 정체성이 흐려진다.
SHOT_SIZE_VIEWS = {
    "ews": ("wide", "front"), "els": ("wide", "front"), "ls": ("wide", "front"),
    "ws": ("wide", "front"), "establishing": ("wide", "front"),
    "mls": ("34", "front"), "mws": ("34", "front"), "ms": ("34", "front"),
    "ots": ("34", "front"), "2s": ("34", "front"), "medium": ("34", "front"),
    "cu": ("detail", "face"), "ecu": ("detail", "face"), "bcu": ("detail", "face"),
    "mcu": ("detail", "face"), "closeup": ("detail", "face"),
}
DEFAULT_VIEWS = ("wide", "front")


def views_for_shot_size(shot_size: str) -> tuple:
    """샷 사이즈 문자열 → (장소 뷰, 인물 뷰). 모르면 wide/front."""
    key = (shot_size or "").strip().lower().replace("-", "").replace(" ", "").replace(".", "")
    if key in SHOT_SIZE_VIEWS:
        return SHOT_SIZE_VIEWS[key]
    for k, v in SHOT_SIZE_VIEWS.items():          # "extreme close-up" 같은 서술형 대응
        if k in key:
            return v
    return DEFAULT_VIEWS


def _newest(paths: list) -> str:
    """_v{N} 버전이 가장 높은 파일 하나. 없으면 빈 문자열."""
    if not paths:
        return ""
    def ver(p):
        m = re.search(r"_v(\d+)\.", pathlib.Path(p).name)
        return int(m.group(1)) if m else 0
    return sorted(paths, key=lambda p: (ver(p), p))[-1]


# kind → (하위폴더, 파일 접미사, 뷰가 없을 때 쓰는 대체 뷰)
ASSET_KINDS = {
    "char": ("char", "Character", ["sheet", "front"]),
    "loc": ("loc", "Location", ["wide"]),
    "prop": ("prop", "Prop", ["top", "34"]),
}


def find_asset(ep: str, kind: str, name: str, view: str = "") -> str:
    """에셋 레퍼런스 경로를 ROOT 기준 상대경로로 반환. 없으면 빈 문자열.

    탐색 순서: 하위폴더의 요청 뷰 → 하위폴더의 대체 뷰 → 하위폴더의 아무 뷰
              → 기존 flat 경로 ({EP}/character/{name}_Character*.png)
    마지막 단계가 있어서 하위폴더로 옮기지 않은 기존 프로젝트도 그대로 동작한다.
    """
    if not name or name in ("—", "-", "", "없음"):
        return ""
    sub, suffix, fallback_views = ASSET_KINDS.get(kind, (None, None, []))
    if not sub:
        return ""
    base = ROOT / ep / "character"
    tries = []
    for v in ([view] if view else []) + fallback_views:
        if v:
            tries.append(str(base / sub / f"{name}_{suffix}_{v}_v*.png"))
    tries.append(str(base / sub / f"{name}_{suffix}*.png"))
    tries.append(str(base / f"{name}_{suffix}*.png"))     # 레거시 flat
    for pattern in tries:
        hit = _newest(glob.glob(pattern))
        if hit:
            return str(pathlib.Path(hit).relative_to(ROOT))
    return ""


def build_genconti2img_cmd(
    model: str,
    prompt: str,
    background: str,
    conti_image: str,
    char_images: list,
) -> list:
    model_id = MODEL_MAP.get(model, model)

    def abs_path(p):
        return str(p) if pathlib.Path(p).is_absolute() else str(ROOT / p)

    cmd = [
        "higgsfield", "generate", "create", model_id,
        "--prompt", prompt,
        "--image", abs_path(background),
        "--image", abs_path(conti_image),
        "--aspect_ratio", "16:9",
        "--quality", "high",
        "--resolution", "2k",
        "--wait", "--wait-timeout", "10m",
    ]
    for ci in char_images:
        cmd += ["--image", abs_path(ci)]
    return cmd


# ── API 실행 ─────────────────────────────────────────────────────────────────

def run_job(cmd: list) -> tuple:
    """Returns (result_url, job_id, error_str)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1380)
    except subprocess.TimeoutExpired:
        return None, None, "timeout (23m)"
    except FileNotFoundError:
        return None, None, "higgsfield CLI를 찾을 수 없습니다"

    if r.returncode != 0:
        stderr = r.stderr.strip()[:300]
        stdout = r.stdout.strip()[:300]
        return None, None, stderr or stdout or f"exit code {r.returncode}"

    # --wait 옵션 사용 시 완료된 결과가 바로 옴
    raw = r.stdout.strip()
    if not raw:
        return None, None, "빈 응답"

    try:
        data = json.loads(raw)
        if isinstance(data, list):
            data = data[0]
        job_id = data.get("id") or data.get("job_id")
        # result URL 키 탐색
        url = (
            data.get("result_url")
            or data.get("output_url")
            or data.get("url")
            or data.get("video_url")
            or data.get("image_url")
        )
        status = data.get("status", "")
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        # JSON이 아닌 경우 URL 직접 추출 시도
        url_match = re.search(r"https://\S+\.(?:mp4|png|jpg|webp)", raw)
        if url_match:
            return url_match.group(0), None, None
        return None, None, f"응답 파싱 오류: {e}"

    if not url:
        return None, job_id, f"결과 URL 없음 (status={status})"

    return url, job_id, None


# ── GenVideo 러너 ────────────────────────────────────────────────────────────

def run_genvideo(config: dict, ep: str, seq: str, args) -> int:
    cache = CacheManager()
    args.model_explicit = args.model is not None
    requested = args.model or "kling3_0"
    model = MODEL_MAP.get(requested, requested)
    shots = expand_shot_spec(args.shot_spec, ep, seq, "genvideo")

    if not shots:
        print(f"BATCH_DONE:0:0:0", flush=True)
        print(f"⚠️ 이미지 파일을 찾을 수 없습니다: {ep}/Image/{seq}/", flush=True)
        return 1

    success, fail, skipped = 0, 0, 0

    for shot in shots:
        print(f"SHOT_START:{shot}", flush=True)
        s = cache.get_shot(ep, seq, shot)

        if s and s.get("status") == "done" and not args.force:
            url = s.get("result_url", "")
            print(f"SHOT_SKIP:{shot}:{url}", flush=True)
            skipped += 1
            continue

        prompt = (
            compose_video_prompt(s, cache.get_project(), cache.get_sequence(ep, seq))
            if s
            else ""
        )
        if not prompt:
            print(f"SHOT_FAIL:{shot}:캐시에 프롬프트 없음 — /GenVideo로 먼저 분석 실행 필요", flush=True)
            fail += 1
            continue

        # 품질 경고 — 막지 않고 진행
        if "ACTION TIMING" in prompt:
            for label, why in (
                ("LOCATION MAP", "공간 지도 없음 — 컷이 바뀌면 인물이 순간이동할 수 있음"),
                ("FIRST FRAME AND SPATIAL BLOCKING", "첫 프레임 점유/블로킹 없음 — 빈 프레임으로 시작할 수 있음"),
                ("OPTICS", "옵틱 없음 — 렌즈가 중간값으로 흘러갈 수 있음"),
            ):
                if label not in prompt:
                    print(f"⚠️  Shot {shot}: {why}", file=sys.stderr, flush=True)
        elif not (s.get("shot_dir_en") or "").strip() and (s.get("scene_en") or s.get("vision_en")):
            # 레거시 3슬롯 경로
            print(f"⚠️  Shot {shot}: shot_dir_en(모션 디렉션) 없음 — 영상이 밋밋할 수 있음", file=sys.stderr, flush=True)

        # 디스크에서 키프레임(-N, 순서)과 레퍼런스(_ref/, 무순서)를 직접 찾는다.
        keyframes, refs = find_shot_media(ep, seq, shot)

        # 하위호환: 디스크에서 못 찾으면 기존 캐시의 image_files를 키프레임으로 쓴다.
        if not keyframes:
            keyframes = s.get("image_files", []) or []
        if not keyframes:
            print(f"SHOT_FAIL:{shot}:이미지를 찾을 수 없음 ({ep}/Image/{seq}/)", flush=True)
            fail += 1
            continue

        shot_model, keyframes, refs, warns = plan_shot_media(
            model, keyframes, refs, forced_model=args.model_explicit
        )
        for w in warns:
            print(f"⚠️  Shot {shot}: {w}", file=sys.stderr, flush=True)

        if args.dry_run:
            print(
                f"SHOT_DRY:{shot}:model={shot_model} kf={len(keyframes)} refs={len(refs)} "
                f"prompt_len={len(prompt)} files={keyframes + refs}",
                flush=True,
            )
            continue

        cmd = build_genvideo_cmd(shot_model, prompt, keyframes, refs)
        url, job_id, err = run_job(cmd)

        if err:
            print(f"SHOT_FAIL:{shot}:{err}", flush=True)
            cache.set_shot_status(ep, seq, shot, "failed")
            ShotlistUpdater.update_status(shotlist_path(ep, seq), shot, "❌")
            fail += 1
        else:
            v = next_version(ep, seq, shot, "mp4")
            local = f"{ep}/Video/{seq}/{shot}_v{v}.mp4"
            print(f"SHOT_DONE:{shot}:{url}", flush=True)
            cache.set_shot_result(ep, seq, shot, url, job_id or "", local)
            ShotlistUpdater.update_status(shotlist_path(ep, seq), shot, "✅")
            ShotlistUpdater.update_url(urls_path(ep, seq), shot, url)
            success += 1

    print(f"BATCH_DONE:{success}:{fail}:{skipped}", flush=True)
    return 0 if fail == 0 else 1


# ── GenConti2Img 러너 ────────────────────────────────────────────────────────

def run_genconti2img(config: dict, ep: str, seq: str, args) -> int:
    cache = CacheManager()
    model = args.model
    shot_spec = getattr(args, "shot_spec", "all")
    shots = expand_shot_spec(shot_spec, ep, seq, "genconti2img")

    if not shots:
        print(f"BATCH_DONE:0:0:0", flush=True)
        print(f"⚠️ 콘티 이미지를 찾을 수 없습니다: {ep}/Conti/{seq}/", flush=True)
        return 1

    success, fail, skipped = 0, 0, 0

    for shot in shots:
        print(f"SHOT_START:{shot}", flush=True)
        s = cache.get_shot(ep, seq, shot)

        if s and s.get("status") == "done" and not args.force:
            url = s.get("result_url", "")
            print(f"SHOT_SKIP:{shot}:{url}", flush=True)
            skipped += 1
            continue

        if not s or not s.get("prompt"):
            print(f"SHOT_FAIL:{shot}:캐시에 프롬프트 없음 — /GenConti2Img로 먼저 분석 실행 필요", flush=True)
            fail += 1
            continue

        conti_image = s.get("conti_image", f"{ep}/Conti/{seq}/{shot}_v1.png")
        characters = s.get("characters", [])

        # 샷 사이즈에 맞는 뷰 선택 (뒷모습 샷이면 인물 뷰를 back으로 덮어씀)
        loc_view, char_view = views_for_shot_size(s.get("shot_size", ""))
        char_view = s.get("char_view") or char_view

        # 배경: 장소 에셋의 뷰 → 없으면 기존 Background.png 경로로 폴백
        background = find_asset(ep, "loc", s.get("location", ""), loc_view)
        if not background:
            background = s.get("background_file", f"{ep}/Image/{seq}/Background.png")

        # 캐릭터 시트 파일 탐색 (샷 사이즈에 맞는 뷰 우선)
        char_images = []
        for char_name in characters:
            hit = find_asset(ep, "char", char_name, char_view)
            if hit:
                char_images.append(hit)

        # 소품 레퍼런스 (있으면)
        prop_images = []
        for prop_name in s.get("props", []):
            hit = find_asset(ep, "prop", prop_name, s.get("prop_view", ""))
            if hit:
                prop_images.append(hit)
        char_images += prop_images

        if args.dry_run:
            print(
                f"SHOT_DRY:{shot}:model={model} size={s.get('shot_size','?')} "
                f"views=loc:{loc_view}/char:{char_view} bg={background} "
                f"conti={conti_image} chars={char_images}",
                flush=True,
            )
            continue

        cmd = build_genconti2img_cmd(model, s["prompt"], background, conti_image, char_images)
        url, job_id, err = run_job(cmd)

        if err:
            print(f"SHOT_FAIL:{shot}:{err}", flush=True)
            cache.set_shot_status(ep, seq, shot, "failed")
            fail += 1
        else:
            v = next_version(ep, seq, shot, "png")
            local = f"{ep}/Image/{seq}/{shot}_v{v}.png"
            print(f"SHOT_DONE:{shot}:{url}", flush=True)
            cache.set_shot_result(ep, seq, shot, url, job_id or "", local)
            success += 1

    print(f"BATCH_DONE:{success}:{fail}:{skipped}", flush=True)
    return 0 if fail == 0 else 1


# ── 상태 / 캐시 명령 ─────────────────────────────────────────────────────────

def cmd_status(config: dict, ep: str, seq: str, args) -> int:
    cache = CacheManager()
    shots = expand_shot_spec("all", ep, seq, "genvideo")
    if not shots:
        shots = cache.all_shots(ep, seq)
    info = cache.cache_info(ep, seq, shots)
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


def cmd_cache_info(config: dict, ep: str, seq: str, args) -> int:
    cache = CacheManager()
    shots_arg = getattr(args, "shots", "")
    if shots_arg:
        shots = [f"{int(s):04d}" if s.strip().isdigit() else s.strip() for s in shots_arg.split(",")]
    else:
        shots = expand_shot_spec("all", ep, seq, "genvideo")
        if not shots:
            shots = cache.all_shots(ep, seq)
    info = cache.cache_info(ep, seq, shots)
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


def cmd_check_cache(config: dict, ep: str, seq: str, args) -> int:
    """어떤 샷이 캐시 히트/미스인지 JSON으로 출력. 스킬 Step 0에서 사용."""
    cache = CacheManager()
    shot_spec = getattr(args, "shot_spec", "all")
    workflow = getattr(args, "workflow", "genvideo")
    shots = expand_shot_spec(shot_spec, ep, seq, workflow)

    result = {"ep": ep, "seq": seq, "shots": {}, "needs_analysis": [], "cached": []}

    for shot in shots:
        vision_ok = cache.is_vision_valid(ep, seq, shot)
        prompt_ok = cache.is_prompt_valid(ep, seq, shot)
        s = cache.get_shot(ep, seq, shot)
        status = (s or {}).get("status", "unknown")

        result["shots"][shot] = {
            "vision_cached": vision_ok,
            "prompt_cached": prompt_ok,
            "status": status,
        }

        if prompt_ok and vision_ok:
            result["cached"].append(shot)
        else:
            result["needs_analysis"].append(shot)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_write_shot(config: dict, ep: str, seq: str, args) -> int:
    """stdin에서 JSON 읽어 특정 샷 캐시에 저장. 스킬 Step 7d에서 사용.

    echo '{"shot":"0010","prompt":"...","vision_text":"...","image_files":["..."],
           "image_sigs":["..."],"image_mode":"single","multi_shot":false,
           "workflow":"genvideo","characters":[]}' | python3 runner.py write-shot S41
    """
    import sys as _sys
    raw = _sys.stdin.read().strip()
    if not raw:
        die(2, "stdin이 비어 있습니다. JSON 데이터를 파이프로 전달하세요.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        die(2, f"JSON 파싱 오류: {e}")

    shot = data.pop("shot", None)
    if not shot:
        die(2, "JSON에 'shot' 필드가 없습니다.")

    shot = f"{int(shot):04d}" if str(shot).isdigit() else str(shot)

    cache = CacheManager()

    # 시퀀스 컨텍스트 sig도 함께 저장 (있으면)
    seq_sig_data = {}
    sceneprompt = ROOT / ep / "Image" / seq / "Sceneprompt.md"
    shotprompt = ROOT / ep / "Image" / seq / "Shotprompt.md"
    character = ROOT / ep / "character" / "Character.md"
    projectprompt = ROOT / "Projectprompt.md"
    cfg_file = ROOT / "config.md"

    seq_sig_data = {
        "sceneprompt_sig": cache.file_sig(sceneprompt),
        "shotprompt_sig": cache.file_sig(shotprompt),
        "character_sig": cache.file_sig(character),
    }
    # LOCATION MAP은 장면(시퀀스) 상수 — 샷마다 복붙하지 않고 여기 한 곳에 둔다.
    location_map_en = data.pop("location_map_en", "")
    if location_map_en:
        seq_sig_data["location_map_en"] = location_map_en
    cache.set_sequence(ep, seq, seq_sig_data)

    # 프로젝트 sig (없으면 스킵)
    if not cache.is_project_valid():
        proj_data = {
            "config_sig": cache.file_sig(cfg_file),
            "config_content": {},
            "projectprompt_sig": cache.file_sig(projectprompt),
            "projectprompt_text": "",
        }
        cache._data["project"] = proj_data
        cache._save()

    # 스타일 앵커는 프로젝트 상수 — 샷마다 복붙하지 않고 여기 한 곳에 둔다.
    style_en = data.pop("style_en", "")
    if style_en:
        cache._data.setdefault("project", {})["style_en"] = style_en
        cache._save()

    # 샷 데이터 저장
    workflow = data.pop("workflow", "genvideo")
    prompt = data.pop("prompt", "")
    vision_text = data.pop("vision_text", "")
    image_files = data.pop("image_files", [])
    image_sigs = data.pop("image_sigs", [])
    image_mode = data.pop("image_mode", "single")
    multi_shot = data.pop("multi_shot", False)
    characters = data.pop("characters", [])
    conti_image = data.pop("conti_image", "")
    background_file = data.pop("background_file", "")

    cache.set_shot_vision(ep, seq, shot, vision_text, image_files, image_sigs)
    extra = {"image_mode": image_mode, "multi_shot": multi_shot}
    if characters:
        extra["characters"] = characters
    if conti_image:
        extra["conti_image"] = conti_image
    if background_file:
        extra["background_file"] = background_file
    extra.update(data)  # 나머지 필드도 저장

    cache.set_shot_prompt(ep, seq, shot, prompt, workflow, **extra)

    print(f"CACHE_WRITE:{shot}:ok", flush=True)
    return 0


def cmd_cache_invalidate(config: dict, ep: str, seq: str, args) -> int:
    cache = CacheManager()
    shots_arg = getattr(args, "shots", "")
    if shots_arg:
        for s in shots_arg.split(","):
            shot = f"{int(s.strip()):04d}" if s.strip().isdigit() else s.strip()
            cache.set_shot_status(ep, seq, shot, "pending")
            # prompt_sig 제거로 재분석 강제
            shot_data = cache.get_shot(ep, seq, shot)
            if shot_data:
                shot_data.pop("prompt_sig", None)
                shot_data.pop("vision_text", None)
                shot_data.pop("image_sigs", None)
        cache._save()
        print(f"무효화 완료: {ep}/{seq} shots={shots_arg}")
    else:
        cache.invalidate_sequence(ep, seq)
        print(f"무효화 완료: {ep}/{seq} 전체 시퀀스")
    return 0


# ── argparse ────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(prog="runner.py", description="반복 처리 러너")
    sub = p.add_subparsers(dest="command", required=True)

    # genvideo
    gv = sub.add_parser("genvideo", help="영상 생성 (i2v)")
    gv.add_argument("seq_id", help="시퀀스 ID (예: S41)")
    gv.add_argument("shot_spec", help="샷 스펙 (예: 0010 | 0010-0030 | all)")
    # default=None → 사용자가 직접 지정했는지 구분한다.
    # 명시했으면 키프레임이 많아도 모델을 바꾸지 않고 지시를 따른다.
    gv.add_argument("--model", default=None, help="모델 (kling3_0 기본 | seedance_2_0)")
    gv.add_argument("--force", action="store_true", help="완료 샷도 재생성")
    gv.add_argument("--dry-run", action="store_true", help="API 호출 없이 확인만")

    # genconti2img
    gc = sub.add_parser("genconti2img", help="콘티 → 씬 이미지 생성")
    gc.add_argument("seq_id", help="시퀀스 ID")
    gc.add_argument("shot_spec", nargs="?", default="all", help="샷 스펙 (기본: all)")
    gc.add_argument("--model", default="gpt", help="모델 (gpt | nano | cinema)")
    gc.add_argument("--force", action="store_true")
    gc.add_argument("--dry-run", action="store_true")

    # status
    st = sub.add_parser("status", help="캐시 상태 조회")
    st.add_argument("seq_id")

    # cache-info
    ci = sub.add_parser("cache-info", help="캐시 상세 정보")
    ci.add_argument("seq_id")
    ci.add_argument("--shots", default="", help="쉼표 구분 샷 번호 (예: 0010,0020)")

    # cache-invalidate
    inv = sub.add_parser("cache-invalidate", help="캐시 무효화")
    inv.add_argument("seq_id")
    inv.add_argument("--shots", default="", help="특정 샷만 (비어있으면 시퀀스 전체)")

    # check-cache (스킬 Step 0에서 사용)
    cc = sub.add_parser("check-cache", help="캐시 히트/미스 확인")
    cc.add_argument("seq_id")
    cc.add_argument("shot_spec", nargs="?", default="all")
    cc.add_argument("--workflow", default="genvideo")

    # write-shot (스킬 Step 7d에서 사용, stdin으로 JSON 받음)
    ws = sub.add_parser("write-shot", help="샷 캐시 저장 (stdin JSON)")
    ws.add_argument("seq_id")

    return p.parse_args()


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    config = load_config()
    seq_id = normalize_seq(args.seq_id)
    ep = resolve_episode(config, seq_id)

    dispatch = {
        "genvideo": run_genvideo,
        "genconti2img": run_genconti2img,
        "status": cmd_status,
        "cache-info": cmd_cache_info,
        "cache-invalidate": cmd_cache_invalidate,
        "check-cache": cmd_check_cache,
        "write-shot": cmd_write_shot,
    }

    fn = dispatch.get(args.command)
    if fn:
        sys.exit(fn(config, ep, seq_id, args) or 0)
    else:
        die(2, f"알 수 없는 명령: {args.command}")


if __name__ == "__main__":
    main()
