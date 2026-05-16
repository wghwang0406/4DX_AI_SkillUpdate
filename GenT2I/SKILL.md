---
version: 1.0.0
name: GenT2I
description: |
  Text-to-image generation with model shorthand: gpt / nano / cinema.
  gpt = GPT Image 2 (gpt_image_2), nano = Nano Banana Pro (nano_banana_2),
  cinema = Cinematic Studio 2.5 (cinematic_studio_2_5).
  No BasePrompt — user supplies the full prompt directly after the model keyword.
  Use when: "GenT2I", "텍스트로 이미지 생성", t2i, text to image generation.
argument-hint: "<gpt|nano|cinema> <prompt>"
allowed-tools: Bash
---

# GenT2I

Text-to-image generation using Higgsfield. The first argument is the model shorthand; everything after is the prompt.

## Step 1 — Parse Arguments

- First word: model shorthand
  - `gpt` → `gpt_image_2`
  - `nano` → `nano_banana_2`
  - `cinema` → `cinematic_studio_2_5`
  - Anything else → print error and stop: `❌ Unknown model. Use: gpt / nano / cinema`
- Remaining words: the full prompt

## Step 2 — Translate & Enhance Prompt

If the prompt contains Korean (or any non-English text), translate it into English and **expand it into a detailed, descriptive image generation prompt**. Make it vivid and specific — add lighting, mood, style, composition, and detail as appropriate. Do NOT call any external API; perform the translation and expansion yourself using your own language capabilities.

Show the enhanced prompt to the user before generating:
> 🔍 Enhanced prompt: `{enhanced English prompt}`

Use the enhanced English prompt for generation.

## Step 3 — Generate Image

Default aspect ratio is **16:9** unless the user specifies otherwise.

### gpt (GPT Image 2):
```bash
higgsfield generate create gpt_image_2 \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --resolution 2k \
  --quality high \
  --wait --wait-timeout 10m
```

### nano (Nano Banana Pro):
```bash
higgsfield generate create nano_banana_2 \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --resolution 2k \
  --wait --wait-timeout 10m
```

### cinema (Cinematic Studio 2.5):
```bash
higgsfield generate create cinematic_studio_2_5 \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --resolution 2k \
  --wait --wait-timeout 10m
```

## Step 4 — Deliver

**Success:**
```
✅ [model]
[결과 이미지]({URL})
{URL}
```

**Failure:** `❌ [model]: {error message}`

## UX Rules

- Reply in the user's language (Korean or English)
- Do not dump raw JSON or job IDs
- Do not pre-estimate cost
- Always show both the markdown link AND the raw URL — markdown link for viewing, raw URL for right-click "Save link as..."
