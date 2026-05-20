---
version: 0.3.0
name: GenSingle
description: |
  Single image-to-video generation. Reads BasePrompt.md, analyzes the target image,
  and generates a video with Kling 3.0 (default) or Seedance 2.0.
  Pair images (N-1.png + N-2.png) use start-end i2v; single image (N.png) uses start-image only.
  Optionally reads ShotPrompt.md for per-shot Korean directives (translated to English).
  Use when: "GenSingle", "이 이미지 하나만 영상으로", single i2v for one image number.
argument-hint: "<image-number> [seedance]"
allowed-tools: Bash, Read
---

# GenSingle

Single i2v generation skill. Default model: Kling 3.0. Pass `seedance` as second argument to use Seedance 2.0.

**Final prompt = BasePrompt + ShotPrompt (번역, 있을 때만) + 이미지 시각 분석**

> **중요:** BasePrompt.md와 ShotPrompt.md는 스킬 실행 시 **반드시 Read 툴로 파일을 새로 읽어야 합니다.** 대화 컨텍스트에 이전에 읽은 내용이 있더라도 절대 재사용하지 않습니다. 파일이 수정되었을 수 있습니다.

## Step 1 — Parse Arguments

- First argument: image number N (e.g., `5`)
- Second argument (optional): model selector
  - nothing / omitted → **Kling 3.0** (`kling3_0`)
  - `seedance` → **Seedance 2.0** (`seedance_2_0`)

## Step 2 — Read BasePrompt.md (Required)

**매번 Read 툴로 파일을 새로 읽습니다. 이전 대화에서 읽은 내용은 무시합니다.**

Search in order:
1. `i2v/BasePrompt.md`
2. `BasePrompt.md` (parent/cwd fallback)

Use whichever exists first. If neither exists, stop and report:
```
❌ BasePrompt.md not found in i2v/ or current directory. Please create one before running GenSingle.
```

## Step 3 — Resolve Image Files

All images live inside the `i2v/` subfolder. For image number N:

1. Check if both `i2v/{N}-1.png` AND `i2v/{N}-2.png` exist → **Pair mode**
2. Else check if `i2v/{N}.png` exists → **Single mode**
3. Else → report error and stop

```bash
ls i2v/{N}-1.png i2v/{N}-2.png 2>/dev/null | wc -l
ls i2v/{N}.png 2>/dev/null
```

## Step 4 — Read ShotPrompt.md (Optional)

**매번 Read 툴로 파일을 새로 읽습니다. 이전 대화에서 읽은 내용은 무시합니다.**

Search only in `i2v/ShotPrompt.md`.  
If it does not exist, skip.

**Key lookup rule:**
- **Pair mode**: look for a line starting with `{N}-1.`
- **Single mode**: look for a line starting with `{N}.`

Example format:
```
1-1. 심장이 뛰는 모습
2. 세포막이 위아래로 흐느적거리는 모습
5.심혈관에 적혈구가 튀어나온다
```

If found: extract Korean text → **translate to English** → include as `[Shot Direction]` in prompt.  
If not found: skip, proceed without shot direction (current behavior unchanged).

## Step 5 — Vision Analysis

Use Read tool to open and analyze the image(s):
- **Pair**: Read `i2v/{N}-1.png` and `i2v/{N}-2.png`
- **Single**: Read `i2v/{N}.png`

Compose an image-specific prompt addition:
- Key visual elements (anatomy, texture, structure, color)
- Motion that fits the image content AND the shot direction (if provided)
- Atmospheric/lighting nuances

## Step 6 — Construct Final Prompt

**With ShotPrompt entry:**
```
{BasePrompt.md contents}

[Shot Direction]: {English translation of Korean directive}

{image-specific motion and scene description}
```

**Without ShotPrompt entry:**
```
{BasePrompt.md contents}

{image-specific motion and scene description}
```

## Step 7 — Generate Video

All image paths must be absolute. Use `pwd` to get the current directory and append `i2v/` to construct the full path.

### Kling 3.0 — Pair mode:
```bash
higgsfield generate create kling3_0 \
  --start-image "/absolute/path/i2v/{N}-1.png" \
  --end-image "/absolute/path/i2v/{N}-2.png" \
  --prompt "..." \
  --mode pro \
  --aspect_ratio 16:9 \
  --duration 5 \
  --wait --wait-timeout 20m
```

### Kling 3.0 — Single mode:
```bash
higgsfield generate create kling3_0 \
  --start-image "/absolute/path/i2v/{N}.png" \
  --prompt "..." \
  --mode pro \
  --aspect_ratio 16:9 \
  --duration 5 \
  --wait --wait-timeout 20m
```

### Seedance 2.0 — Pair mode:
```bash
higgsfield generate create seedance_2_0 \
  --start-image "/absolute/path/i2v/{N}-1.png" \
  --end-image "/absolute/path/i2v/{N}-2.png" \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --duration 5 \
  --wait --wait-timeout 20m
```

### Seedance 2.0 — Single mode:
```bash
higgsfield generate create seedance_2_0 \
  --start-image "/absolute/path/i2v/{N}.png" \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --duration 5 \
  --wait --wait-timeout 20m
```

Note: Seedance 2.0 does not use `--mode`. Use absolute paths. Get current directory with `pwd` if needed.

## Step 8 — Deliver

- **Success** → `✅ Image {N} [single/pair | kling/seedance]: {URL}`
- **Failure** → `❌ Image {N}: {error message}`

## UX Rules

- Reply in the user's language (Korean or English)
- Do not dump raw JSON or job IDs
- Do not pre-estimate cost
