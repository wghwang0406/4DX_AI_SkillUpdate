#!/usr/bin/env python3
"""
models.py — 모델 별칭·능력표 단일 출처 (single source of truth)

왜 있나
  MODEL_MAP이 runner.py / gen_helper.py / genconti2img_minimal.py 에 3벌로
  흩어져 있었고 내용이 서로 달랐다. CLAUDE.md 규칙 7번("상수는 한 곳에")
  위반이라 여기로 모은다.

무엇이 들어 있나
  MODEL_MAP  단축명 → 모델 ID
  CAPS       모델별로 "어떤 파라미터를 받는가". argv를 하드코딩하지 않고
             이 표를 보고 조립하기 위한 것.
  헬퍼       resolve_model() / image_flags() / video_max_images()

CAPS를 고칠 때
  값은 전부 `higgsfield model get <id>` 또는 `higgsfield workflow get <id>`
  출력에서 그대로 옮긴 것이다. 짐작으로 채우지 않는다.
  이 표가 낡으면 조용히 틀린 argv가 나가므로, 모델을 추가하거나 의심스러우면
  아래 자기검사를 돌린다:

      python3 models.py --check      # 라이브 CLI와 CAPS를 대조

순수 stdlib, Python 3.9+.
"""

import subprocess
import sys

# ── 단축명 → 모델 ID ─────────────────────────────────────────────────────────
#
# 자기 자신을 가리키는 항목(예: "kling3_0": "kling3_0")은 사용자가 단축명 대신
# 모델 ID를 그대로 쳐도 통하게 하려는 것이다. 표에 없는 이름은 그대로 통과시켜
# CLI가 판단하게 둔다 (MODEL_MAP.get(x, x) 관용구).

MODEL_MAP = {
    # ── 이미지 ──
    "gpt": "gpt_image_2",
    "nano": "nano_banana_2",          # 서버 별칭. nano_banana_pro 로 해석된다
    "nbp": "nano_banana_2",
    "cinema": "cinematic_studio_2_5",
    "soul": "text2image_soul_v2",
    "soulcine": "soul_cinematic",
    "seed": "seedream_v4_5",
    # ── 영상 ──
    "kling": "kling3_0",
    "kling3_0": "kling3_0",
    "seedance": "seedance_2_0",
    "seedance_2_0": "seedance_2_0",
    "seedance25": "seedance_2_5",
    "seedance_2_5": "seedance_2_5",
    # ── 업스케일 ──
    "upscale": "bytedance_video_upscale",
    "topaz": "topaz_video",
}

# 서버가 별칭을 해석해 주는 것들. CAPS 조회 전에 정본 ID로 펴 준다.
CANONICAL = {
    "nano_banana_2": "nano_banana_pro",
}


# ── 모델별 능력표 ────────────────────────────────────────────────────────────
#
# quality / resolution / aspect : 받는 값의 튜플. None = 그 파라미터가 없다.
#                                 None인데 플래그를 붙이면 CLI가 거부한다.
# refs        : image_references 를 받는가
# max_images  : 레퍼런스 총 상한 (start/end 포함). None = 명시된 제한 없음
# folder      : folder_id 를 받는가
# soul_id     : custom_reference_id 를 받는가
# prompt_lang : prompt_language 를 받는가 (기본값이 zh 라 en 강제가 필요하다)

_1K2K4K = ("1k", "2k", "4k")
_SOULQ = ("1.5k", "2k")
_A_WIDE = ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9")
_A_NARROW = ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3")

CAPS = {
    # ── 이미지 ── (higgsfield model get <id>)
    "gpt_image_2": {
        "kind": "image", "quality": ("low", "medium", "high"),
        "resolution": _1K2K4K, "aspect": _A_NARROW,       # 21:9 없음
        "refs": True, "folder": False, "soul_id": False,
    },
    "nano_banana_pro": {
        "kind": "image", "quality": None,                  # quality 파라미터 자체가 없다
        "resolution": _1K2K4K,
        "aspect": ("1:1", "3:2", "2:3", "4:3", "3:4", "4:5", "5:4", "9:16", "16:9", "21:9"),
        "refs": True, "max_images": 14, "folder": False, "soul_id": False,
    },
    "text2image_soul_v2": {
        "kind": "image", "quality": _SOULQ, "resolution": None,
        "aspect": _A_NARROW,                               # 21:9 없음
        "refs": True, "folder": False, "soul_id": True,
    },
    "soul_cinematic": {
        "kind": "image", "quality": _SOULQ, "resolution": None, "aspect": _A_WIDE,
        "refs": True, "folder": False, "soul_id": True,
    },
    "seedream_v4_5": {
        "kind": "image", "quality": ("basic", "high"), "resolution": None,
        "aspect": ("1:1", "4:3", "16:9", "3:2", "21:9", "3:4", "9:16", "2:3"),
        "refs": True, "folder": False, "soul_id": False,
    },
    # ── 이미지 · Cinema Studio 계열 ── (higgsfield workflow get <id>)
    "cinematic_studio_2_5": {
        "kind": "image", "quality": None, "resolution": _1K2K4K,
        "aspect": ("1:1", "3:2", "2:3", "4:3", "3:4", "4:5", "5:4", "16:9", "9:16", "21:9"),
        "refs": True, "folder": True, "soul_id": False,
    },
    "soul_cinema_studio": {
        "kind": "image", "quality": _SOULQ, "resolution": None, "aspect": _A_WIDE,
        "refs": True, "folder": False, "soul_id": True,
    },
    "cinematic_studio_soul_cast": {
        "kind": "image", "quality": None, "resolution": None,
        "aspect": _A_WIDE + ("9:21",),
        "refs": False, "folder": False, "soul_id": False,
    },
    "cinematic_studio_soul_location": {
        "kind": "image", "quality": None, "resolution": None,
        "aspect": _A_WIDE + ("9:21",),
        "refs": False, "folder": False, "soul_id": False,
    },
    # ── 영상 ── (higgsfield model get <id>)
    "kling3_0": {
        "kind": "video", "quality": None, "resolution": None,
        "aspect": ("16:9", "9:16", "1:1"),                 # 21:9 없음
        "refs": False, "max_images": 2, "folder": False,
        "mode": ("std", "pro", "4k"),
    },
    "seedance_2_0": {
        "kind": "video", "quality": None,
        "resolution": ("480p", "720p", "1080p", "4k"),
        "aspect": ("auto", "16:9", "9:16", "4:3", "3:4", "1:1", "21:9"),
        "refs": True, "max_images": 9, "folder": False,
    },
    "seedance_2_5": {
        "kind": "video", "quality": None,
        "resolution": ("480p", "720p"),                    # 1080p·4k 없음 — 업스케일로 올린다
        "aspect": ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        "refs": True, "max_images": 30, "folder": False,
        # start/end 이미지는 mode omni_reference 에서만 허용된다
        "needs_omni_mode": True,
    },
    # ── 영상 · Cinema Studio 계열 ── (higgsfield workflow get <id>)
    "cinematic_studio_3_0": {
        "kind": "video", "quality": None,
        "resolution": ("480p", "720p", "1080p", "4k"),
        "aspect": ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        "refs": True, "max_images": 15, "folder": True,
        "prompt_lang": True, "multi_shots": True,
    },
    "cinematic_studio_video_3_5": {
        "kind": "video", "quality": None,
        "resolution": ("480p", "720p", "1080p"),
        "aspect": ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        "refs": True, "folder": False,
        "prompt_lang": True, "multi_shots": True,
        "duration_default": 15,                            # 안 넘기면 15초로 3배 과금된다
    },
    "cinematic_studio_video_4_0": {
        "kind": "video", "quality": None,
        "resolution": ("480p", "720p"),                    # seedance_2_5 와 같은 엔진
        "aspect": ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        "refs": True, "max_images": 30, "folder": False,
        "needs_omni_mode": True,
    },
    # ── 업스케일 ──
    "bytedance_video_upscale": {
        "kind": "video", "quality": None,
        "resolution": ("1080p", "2k", "4k"), "aspect": None,
        "refs": True, "folder": False,
        "preset": ("common", "aigc", "short_series", "ugc", "old_film"),
    },
    "topaz_video": {
        "kind": "video", "quality": None,
        "resolution": ("1080p", "2160p"),
        "aspect": ("auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        "refs": True, "folder": False,
    },
    "video_upscale": {
        "kind": "video", "quality": None, "resolution": None, "aspect": None,
        "refs": True, "folder": True,
    },
}

# CAPS에 없는 모델을 만났을 때 쓰는 값. 아무 플래그도 붙이지 않아
# "모르면 안 붙인다"로 안전하게 떨어진다.
_UNKNOWN = {"kind": None, "quality": None, "resolution": None, "aspect": None,
            "refs": True, "folder": False, "soul_id": False}


# ── 조회 헬퍼 ────────────────────────────────────────────────────────────────

def resolve_model(name: str) -> str:
    """단축명 → 모델 ID. 표에 없으면 그대로 돌려준다(CLI가 판단하게)."""
    return MODEL_MAP.get((name or "").strip(), (name or "").strip())


def caps(model_id: str) -> dict:
    """모델 능력표. 서버 별칭은 정본으로 펴서 찾는다."""
    return CAPS.get(CANONICAL.get(model_id, model_id), _UNKNOWN)


def _pick(allowed, want, fallback=None):
    """모델이 받는 값 중에서 고른다. 파라미터가 없으면 None."""
    if not allowed:
        return None
    if want in allowed:
        return want
    if fallback in (allowed or ()):
        return fallback
    return allowed[-1]          # 없으면 가장 높은 값


def image_flags(model_id: str, quality: str = "high", resolution: str = "2k") -> list:
    """
    이미지 모델에 붙일 품질 플래그를 argv 조각으로 돌려준다.

    모델마다 받는 파라미터가 다르다:
      gpt_image_2          --quality high   --resolution 2k
      nano_banana_pro                       --resolution 2k   (quality 없음)
      soul_cinematic       --quality 2k                       (resolution 없음)
      cinematic_studio_2_5                  --resolution 2k   (quality 없음)

    "high"처럼 그 모델에 없는 값은 그 모델에서 가장 높은 값으로 옮겨 준다.
    """
    c = caps(model_id)
    out = []
    q = _pick(c.get("quality"), quality, fallback="2k")
    if q:
        out += ["--quality", q]
    r = _pick(c.get("resolution"), resolution)
    if r:
        out += ["--resolution", r]
    return out


def supports_aspect(model_id: str, aspect: str) -> bool:
    """이 모델이 해당 화면비를 받는가. 표에 없으면 True(막지 않는다)."""
    allowed = caps(model_id).get("aspect")
    return True if not allowed else aspect in allowed


def video_max_images(model_id: str, default: int = 9) -> int:
    """레퍼런스 총 상한. 표에 없으면 default."""
    return caps(model_id).get("max_images") or default


# ── 자기검사: CAPS vs 라이브 CLI ─────────────────────────────────────────────

def _live_params(model_id: str) -> dict:
    """`model get` / `workflow get` 을 읽어 {param: 허용값들} 로 만든다."""
    for sub in ("model", "workflow"):
        try:
            r = subprocess.run(["higgsfield", sub, "get", model_id],
                               capture_output=True, text=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {}
        if r.returncode != 0:
            continue
        params = {}
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2 or not parts[0].islower():
                continue
            spec = parts[1]
            params[parts[0]] = tuple(spec.split(",")) if "," in spec else None
        if params:
            return params
    return {}


def _check() -> int:
    """CAPS가 라이브 CLI와 어긋나는지 본다. 어긋나면 종료코드 1."""
    bad = 0
    for model_id in sorted(CAPS):
        live = _live_params(model_id)
        if not live:
            print(f"?  {model_id}: CLI 조회 실패 — 건너뜀")
            continue
        for field in ("quality", "resolution"):
            ours, theirs = CAPS[model_id].get(field), live.get(field)
            if ours != theirs:
                print(f"X  {model_id}.{field}: CAPS={ours} / CLI={theirs}")
                bad += 1
    print("\nCAPS가 CLI와 일치합니다." if not bad else f"\n{bad}건 어긋납니다 — CAPS를 고치세요.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_check() if "--check" in sys.argv else
             print("사용법: python3 models.py --check") or 0)
