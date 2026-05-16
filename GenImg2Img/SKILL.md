---
version: 1.0.0
name: GenImg2Img
description: |
  Image-to-image generation. User drags a reference image into the chat, then provides
  model shorthand (gpt/nano/cinema) and a prompt.
  gpt = GPT Image 2 (gpt_image_2), nano = Nano Banana Pro (nano_banana_2),
  cinema = Cinematic Studio 2.5 (cinematic_studio_2_5).
  Extracts the attached image path from conversation context and passes it as --image.
  Use when: "GenImg2Img", "이미지 스타일 변환", "레퍼런스 이미지로 생성", i2i, image to image.
argument-hint: "<gpt|nano|cinema> <prompt>"
allowed-tools: Bash, Read
---

# GenImg2Img

Image-to-image generation using Higgsfield. User must drag a reference image into the chat before (or together with) the command. The first argument is the model shorthand; everything after is the prompt.

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

## Step 3 — Extract Attached Image Path

Look at the conversation context for a file attachment (image dragged into chat by the user). The attached image will appear as a file path in the conversation context — typically shown as an `ide_opened_file` or file attachment tag, or visible in the user's message.

Extract the **absolute file path** of the attached image.

If no image attachment is found:
```
❌ No image attached. Please drag an image into the chat before running GenImg2Img.
```
Stop here.

## Step 4 — Generate Image

Default aspect ratio is **16:9** unless the user specifies otherwise.

### gpt (GPT Image 2):
```bash
higgsfield generate create gpt_image_2 \
  --image "/absolute/path/to/image" \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --resolution 2k \
  --quality high \
  --wait --wait-timeout 10m
```

### nano (Nano Banana Pro):
```bash
higgsfield generate create nano_banana_2 \
  --image "/absolute/path/to/image" \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --resolution 2k \
  --wait --wait-timeout 10m
```

### cinema (Cinematic Studio 2.5):
```bash
higgsfield generate create cinematic_studio_2_5 \
  --image "/absolute/path/to/image" \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --resolution 2k \
  --wait --wait-timeout 10m
```

## Step 5 — Deliver

**Success:**
```
✅ [model] i2i
[결과 이미지]({URL})
{URL}
```

**Failure:** `❌ [model]: {error message}`

## UX Rules

- Reply in the user's language (Korean or English)
- Do not dump raw JSON or job IDs
- Do not pre-estimate cost
- Always show both the markdown link AND the raw URL — markdown link for viewing, raw URL for right-click "Save link as..."
