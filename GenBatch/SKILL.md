---
version: 0.3.0
name: GenBatch
description: |
  Batch image-to-video generation from images in the current working directory.
  Reads BasePrompt.md as the shared base prompt, optionally reads ShotPrompt.md for
  per-shot Korean directives (translated to English), then analyzes each image with vision.
  Pair images (N-1.png + N-2.png) use start-end i2v; single images (N.png) use start-image i2v.
  Default model: Kling 3.0. Pass "seedance" to use Seedance 2.0.
  Use when: "배치로 영상 만들어", "전체 이미지 i2v", "GenBatch", batch i2v generation.
argument-hint: "<N-M | N,M,... | all> [seedance]"
allowed-tools: Bash, Read
---

# GenBatch

Batch i2v generation skill. Default model: Kling 3.0. Pass `seedance` as last argument to use Seedance 2.0.

**Final prompt per image = BasePrompt + ShotPrompt (번역, 있을 때만) + 이미지 시각 분석**

> **중요:** BasePrompt.md와 ShotPrompt.md는 스킬 실행 시 **반드시 Read 툴로 파일을 새로 읽어야 합니다.** 대화 컨텍스트에 이전에 읽은 내용이 있더라도 절대 재사용하지 않습니다. 파일이 수정되었을 수 있습니다.

## Step 1 — Parse Arguments

- First argument: image range/list/all
  - `all` → scan directory for all image numbers
  - `1-3` → expand to [1, 2, 3]
  - `1,3,4` → parse to [1, 3, 4]
- Last argument (optional): model selector
  - nothing / omitted → **Kling 3.0** (`kling3_0`)
  - `seedance` → **Seedance 2.0** (`seedance_2_0`)

To find all image numbers when `all` is specified:
```bash
ls i2v/*.png 2>/dev/null | grep -oE '/[0-9]+' | grep -oE '[0-9]+' | sort -un
```

## Step 2 — Read BasePrompt.md (Required)

**매번 Read 툴로 파일을 새로 읽습니다. 이전 대화에서 읽은 내용은 무시합니다.**

Search in order:
1. `i2v/BasePrompt.md`
2. `BasePrompt.md` (parent/cwd fallback)

Use whichever exists first. If neither exists, stop and report:
```
❌ BasePrompt.md not found in i2v/ or current directory. Please create one before running GenBatch.
```

## Step 3 — Read ShotPrompt.md (Optional)

**매번 Read 툴로 파일을 새로 읽습니다. 이전 대화에서 읽은 내용은 무시합니다.**

Search only in `i2v/ShotPrompt.md`.  
If it does not exist, skip — all images will use BasePrompt + vision only.

ShotPrompt.md format:
```
1-1. 심장이 뛰는 모습
2. 세포막이 위아래로 흐느적거리는 모습
5.심혈관에 적혈구가 튀어나온다
```

Store the contents in memory for per-image lookup in Step 5.

## Step 4 — Resolve Image Files per Number

All images live inside the `i2v/` subfolder. For each image number N (in order):

1. Check if both `i2v/{N}-1.png` AND `i2v/{N}-2.png` exist → **Pair mode**
2. Else check if `i2v/{N}.png` exists → **Single mode**
3. Else → skip with warning: `⚠️ Image {N}: no matching file found, skipping`

```bash
ls i2v/{N}-1.png i2v/{N}-2.png 2>/dev/null | wc -l
ls i2v/{N}.png 2>/dev/null
```

## Step 5 — Per-Image: ShotPrompt Lookup + Vision Analysis + Prompt Construction

For each valid image entry:

### 5a. ShotPrompt Lookup
**Key lookup rule:**
- **Pair mode**: look for a line starting with `{N}-1.`
- **Single mode**: look for a line starting with `{N}.`

If found: extract Korean text → **translate to English** → prepare as `[Shot Direction]` block.  
If not found: no shot direction for this image (skip silently).

### 5b. Vision Analysis
Use Read tool to open and analyze the image(s):
- **Pair**: Read `i2v/{N}-1.png` and `i2v/{N}-2.png`
- **Single**: Read `i2v/{N}.png`

Compose an image-specific prompt addition:
- Key visual elements (anatomy, texture, structure, color)
- Motion that fits the image content AND the shot direction (if provided)
- Atmospheric/lighting nuances

### 5c. Construct Final Prompt

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

## Step 6 — Generate Video

All image paths must be absolute. Use `pwd` to get the current directory and append `i2v/` to construct the full path.

### Kling 3.0 — Pair:
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

### Kling 3.0 — Single:
```bash
higgsfield generate create kling3_0 \
  --start-image "/absolute/path/i2v/{N}.png" \
  --prompt "..." \
  --mode pro \
  --aspect_ratio 16:9 \
  --duration 5 \
  --wait --wait-timeout 20m
```

### Seedance 2.0 — Pair:
```bash
higgsfield generate create seedance_2_0 \
  --start-image "/absolute/path/i2v/{N}-1.png" \
  --end-image "/absolute/path/i2v/{N}-2.png" \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --duration 5 \
  --wait --wait-timeout 20m
```

### Seedance 2.0 — Single:
```bash
higgsfield generate create seedance_2_0 \
  --start-image "/absolute/path/i2v/{N}.png" \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --duration 5 \
  --wait --wait-timeout 20m
```

Note: Seedance 2.0 does not use `--mode`. Use absolute paths.

## Step 7 — Report Results

After each image:
- **Success** → `✅ Image {N} [pair/single | kling/seedance]: {URL}`
- **Failure** → `❌ Image {N}: {error} — skipping`, continue to next

Final summary:
```
--- GenBatch Complete ---
✅ Succeeded: N
❌ Failed/Skipped: N
```

## UX Rules

- Reply in the user's language (Korean or English)
- Do not dump raw JSON or job IDs
- Do not pre-estimate cost
- Process all images sequentially without asking for confirmation between each
