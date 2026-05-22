---
version: 1.1.0
name: GenImg2Img
description: |
  Image-to-image generation. User provides a reference image (drag into chat OR type file path/name)
  along with model shorthand (gpt/nano/cinema) and a prompt.
  gpt = GPT Image 2 (gpt_image_2), nano = Nano Banana Pro (nano_banana_2),
  cinema = Cinematic Studio 2.5 (cinematic_studio_2_5).
  Accepts image via chat attachment OR text-based file path/name input.
  Use when: "GenImg2Img", "이미지 스타일 변환", "레퍼런스 이미지로 생성", i2i, image to image.
argument-hint: "<gpt|nano|cinema> <prompt>"
allowed-tools: Bash, Read
---

# GenImg2Img

Image-to-image generation using Higgsfield. The first argument is the model shorthand; everything after is the prompt.
Reference image can be provided by dragging into chat OR by typing the file path/name in the message.

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

## Step 3 — Resolve Image Path

이미지 경로를 두 가지 방법으로 받는다. **방법 A를 우선 확인하고, 없으면 방법 B를 시도한다.**

**방법 A — 채팅 첨부 (드래그 또는 IDE attachment):**
대화 컨텍스트에서 첨부된 파일 경로를 추출한다.
`ide_opened_file` 태그, 파일 첨부 태그, 또는 메시지 내 첨부 경로에서 탐지.

**방법 B — 텍스트 입력 (파일명 또는 경로):**
사용자 메시지(또는 프롬프트 인자)에서 이미지 파일 경로/이름을 파싱한다.
- 절대 경로 (`/Users/.../image.png`) → 그대로 사용
- 상대 경로 (`EP01/Image/S41/xxx.png`) → 현재 작업 디렉토리 기준으로 절대 경로 변환
- 파일명만 (`image.png`) → 현재 프로젝트 폴더에서 `find`로 탐색:
  ```bash
  find . -maxdepth 6 -name "image.png" 2>/dev/null | head -1
  ```
  여러 개 발견 시 가장 최근 수정된 파일 사용.

**둘 다 없으면:**
```
❌ No image found. Drag an image into the chat, or include the file path/name in your message.
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
