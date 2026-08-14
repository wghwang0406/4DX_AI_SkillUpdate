---
version: 1.2.0
name: GenImg2Img
description: |
  Image-to-image generation. User provides a reference image (drag into chat OR type file path/name)
  along with an optional model shorthand and a prompt.
  gpt = GPT Image 2, nano = Nano Banana Pro (edits, always first),
  cinema = Cinematic Studio 2.5, soul = Soul 2.0, soulcine = Soul Cinema,
  seed = Seedream 4.5 (texture pass only). Routes by Lira when no model is given.
  Accepts image via chat attachment OR text-based file path/name input.
  Use when: "GenImg2Img", "이미지 스타일 변환", "레퍼런스 이미지로 생성", i2i, image to image.
argument-hint: "[gpt|nano|cinema|soul|soulcine|seed] <prompt>"
allowed-tools: Bash, Read, Skill
---

# GenImg2Img

Image-to-image generation using Higgsfield. The first argument is the model shorthand; everything after is the prompt.
Reference image can be provided by dragging into chat OR by typing the file path/name in the message.

## 원문 규격 참조 (필수)

프롬프트를 쓰기 전에 `~/.claude/skills/Lira/SKILL.md`를 Read한다
(특히 *Surgical-edit template*, *Model routing*).
`~/.claude/CLAUDE.md`의 **프롬프트 규칙 10개**는 항상 적용된다.

> Lira는 저장소에 없다 (힉스필드 배포본, 별도 설치). 없으면 위 프롬프트 규칙 10개를
> 근거로 진행한다 — 중단하지 않는다.

## Step 1 — Parse Arguments

- First word: model shorthand
  - `gpt` → `gpt_image_2`
  - `nano` → `nano_banana_2` (Nano Banana Pro)
  - `cinema` → `cinematic_studio_2_5`
  - `soul` → `text2image_soul_v2` (Soul 2.0 — 인물)
  - `soulcine` → `soul_cinematic` (Soul Cinema — 배경)
  - `seed` → `seedream_v4_5` (텍스처 패스 전용)
  - Anything else → print error and stop:
    `❌ Unknown model. Use: gpt / nano / cinema / soul / soulcine / seed`
  - **생략 가능** — 모델을 안 쓰면 Step 2의 라우팅으로 자동 선택한다
- Remaining words: the full prompt

## Step 2 — 요청 종류 판별: 편집인가 생성인가

이게 갈리면 프롬프트 구조가 완전히 달라진다.

**편집** (원본을 최소로 고침) — "이 부분만 바꿔줘", "간판 글자 바꿔줘", "가로등 지워줘",
"피부 텍스처 살려줘", "리버스 앵글로":
→ Lira의 **surgical-edit 템플릿**을 쓴다. 최소 CHANGE, 상세 PRESERVE EXACTLY, 한 번에 하나씩.
```
Edit the image: {한 줄 목표}.

CHANGE: {바뀌는 단 하나만, 정확하게}.

PRESERVE EXACTLY:
- {동일하게 남아야 하는 것 전부: 얼굴, 의상, 소품, 위치, 벽/바닥, 카메라 앵글, 기존 그림자}
- Color grade, palette, contrast, grain, falloff

ONLY CHANGE: {그 하나를 다시 명시}. 100% identical otherwise.
```
- **편집에서는 제거가 합법 연산**이다. 단 **채울 것을 함께** 쓴다
  (`Remove the lamppost` + `continuous brick wall behind`).
- 프레임을 다시 짜야 하는 건 편집이 아니다 → 새로 생성한다.
- **너무 많이 바뀌었다는 말이 나오면 = 실제로 많이 바꾼 것이다.** 더 잠그고 덜 바꾼다.

**생성** (레퍼런스를 참고해 새로 만듦) → Step 2-B의 4-D 확장을 쓴다.

### 모델 라우팅 (Lira, CLI 확인 완료)

| 상황 | 단축명 | 모델 ID |
|---|---|---|
| 프레임 편집 — **언제나 1순위** | `nano` | `nano_banana_2` |
| 뭉개진 AI 텍스처 되살리기 (피부·직물·표면) | `seed` | `seedream_v4_5` — **텍스처 패스 전용, 국소 편집 금지** |
| NBP가 못 잡은 **가장 미세한 국소 편집** | `gpt` | `gpt_image_2` — 전역은 지저분해지지만 국소는 강하다 |
| **장소 뷰 변경**(리버스 앵글 등) | `gpt` | `gpt_image_2` — Lira가 이 작업에 잘 맞는다고 명시 |
| 인물 신규 생성 | `soul` | `text2image_soul_v2` (**21:9 없음**) |
| 장소 신규 생성 | `soulcine` | `soul_cinematic` (21:9 지원) |

편집 순서는 고정: **NBP → Seedream(텍스처만) → GPT Image 2(최후).**
사용자가 모델을 지정했으면 그대로 따르되, 라우팅과 어긋나면 한 줄로 알린다.

**Seedream 4.5 텍스처 패스** (유일한 용도):
```
Edit the image: revive the sloppy AI textures.

CHANGE: skin pores and micro-detail, fabric weave, surface dirt and grain on {표면}.

PRESERVE EXACTLY:
- composition, identity, facial structure, pose, wardrobe shapes
- lighting direction and intensity, color grade, contrast
```
국소 편집(무엇 하나를 지우거나 바꾸기)은 **절대 Seedream에 주지 않는다.**

CLI 파라미터가 모델마다 다르다:
- `nano_banana_2` / `gpt_image_2` — `--resolution 1k|2k|4k` (gpt는 `--quality low|medium|high`도 있음)
- `text2image_soul_v2` / `soul_cinematic` — **`--quality 1.5k|2k`, `resolution` 없음**
- `seedream_v4_5` — `--quality basic|high`, 입력은 `input_images`

**NBP로 장소 뷰를 바꿀 때는** 새 배치를 **오브젝트별로 전부 명시**해야 한다
(`메인 뷰에서 오른쪽에 있던 소파가 리버스 뷰에서는 왼쪽에, 카메라 뒤에 있던 문이 이제 정면에`).
안 하면 지오메트리가 깨진다.

## Step 2-B — Translate & Enhance (생성일 때, Lira 4-D)

한국어 입력은 영어로 번역하고 **자유롭게 부풀리지 말고** Lira의 4-D
(DECONSTRUCT → DIAGNOSE → DEVELOP → DELIVER)로 확장한다.

- **자연스러운 산문.** 키워드 스택 금지. 총 1500–2000자 이내.
- **긍정으로.** 생성 프롬프트에는 NOT 스택을 쓰지 않는다 (그 개념을 주입한다).
- **조명·재질은 기술적으로**, 팔레트는 **60/30/10** — 레퍼런스에서 끌어오고 지어내지 않는다.
- **화면비·해상도는 프롬프트에 넣지 않는다** (CLI 파라미터).
- `rule of thirds`를 넣는다 — 캐릭터 시트만 예외.
- 실존 인물 이름·IP·브랜드 금지.

## Step 2-C — 레퍼런스의 역할을 명시한다

레퍼런스마다 **무엇을 물려받고 무엇을 물려받지 않을지** 프롬프트에 직접 쓴다.
역할을 안 적으면 모델이 알아서 정하는데 대개 틀린다 — 얼굴 대신 구도를 베끼거나 색을 가져온다.

```
Follow the reference image for {얼굴·의상만 / 구도·앵글만 / 색감·질감만}.
Do NOT inherit {물려받으면 안 되는 것} from it.
```

Do NOT call any external API; perform the translation and expansion yourself.

Show the final prompt to the user before generating:
> 🔍 Enhanced prompt: `{final English prompt}`

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

### soul / soulcine (Soul 2.0 / Soul Cinema):
**플래그가 다르다** — `--quality`가 `1.5k|2k`이고 `--resolution`이 없다.
Soul 2.0에는 21:9가 없다.
```bash
higgsfield generate create text2image_soul_v2 \
  --image "/absolute/path/to/image" \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --quality 2k \
  --wait --wait-timeout 10m
```
Soul ID가 있으면 `--custom_reference_id {ID}`를 붙인다 (`higgsfield soul-id list`).
장소면 `text2image_soul_v2` 자리에 `soul_cinematic`.

### seed (Seedream 4.5 — 텍스처 패스 전용):
`--quality`가 `basic|high`다.
```bash
higgsfield generate create seedream_v4_5 \
  --image "/absolute/path/to/image" \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --quality high \
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
