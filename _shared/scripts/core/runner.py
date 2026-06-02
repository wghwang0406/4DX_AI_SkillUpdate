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
        die(2, "config.md를 찾을 수 없습니다. /GenInit을 먼저 실행하세요.")
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
        files = glob.glob(str(img_dir / "[0-9]*.png"))
        nums = set()
        for f in files:
            m = re.match(r"(\d{4})", pathlib.Path(f).name)
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

def build_genvideo_cmd(
    model: str, prompt: str, image_mode: str, image_files: list, multi_shot: bool
) -> list:
    abs_files = [
        str(f) if pathlib.Path(f).is_absolute() else str(ROOT / f)
        for f in image_files
    ]
    cmd = [
        "higgsfield", "generate", "create", model,
        "--prompt", prompt,
        "--aspect_ratio", "16:9",
        "--duration", "5",
        "--wait", "--wait-timeout", "20m",
    ]
    if model == "kling3_0":
        cmd += ["--mode", "pro"]
    if image_mode == "pair" and len(abs_files) >= 2:
        cmd += ["--start-image", abs_files[0], "--end-image", abs_files[1]]
    else:
        cmd += ["--start-image", abs_files[0]]
        if multi_shot and model != "seedance_2_0":
            cmd += ["--multi_shots", "true", "--multi_shot_mode", "auto"]
    return cmd


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
    model = MODEL_MAP.get(args.model, args.model)
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

        if not s or not s.get("prompt"):
            print(f"SHOT_FAIL:{shot}:캐시에 프롬프트 없음 — /GenVideo로 먼저 분석 실행 필요", flush=True)
            fail += 1
            continue

        image_mode = s.get("image_mode", "single")
        image_files = s.get("image_files", [])
        multi_shot = s.get("multi_shot", False)

        if not image_files:
            print(f"SHOT_FAIL:{shot}:캐시에 image_files 없음", flush=True)
            fail += 1
            continue

        if args.dry_run:
            print(
                f"SHOT_DRY:{shot}:[{image_mode}] model={model} "
                f"prompt_len={len(s['prompt'])} multi={multi_shot}",
                flush=True,
            )
            continue

        cmd = build_genvideo_cmd(model, s["prompt"], image_mode, image_files, multi_shot)
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

        background = s.get("background_file", f"{ep}/Image/{seq}/Background.png")
        conti_image = s.get("conti_image", f"{ep}/Conti/{seq}/{shot}_v1.png")
        characters = s.get("characters", [])

        # 캐릭터 시트 파일 탐색
        char_images = []
        for char_name in characters:
            if char_name in ("—", "", "-", "없음"):
                continue
            matches = glob.glob(str(ROOT / ep / "character" / f"{char_name}_Character*.png"))
            if matches:
                char_images.append(str(pathlib.Path(matches[0]).relative_to(ROOT)))

        if args.dry_run:
            print(
                f"SHOT_DRY:{shot}:model={model} bg={background} "
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
    gv.add_argument("--model", default="kling3_0", help="모델 (kling3_0 | seedance_2_0)")
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
