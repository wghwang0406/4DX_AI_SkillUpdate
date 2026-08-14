---
version: 1.1.0
name: GenT2I
description: |
  Text-to-image generation with model shorthand: gpt / nano / cinema / soul / soulcine.
  gpt = GPT Image 2, nano = Nano Banana Pro, cinema = Cinematic Studio 2.5,
  soul = Higgsfield Soul 2.0 (characters), soulcine = Soul Cinema (locations, 21:9).
  Routes by Lira when no model is given.
  No BasePrompt — user supplies the full prompt directly after the model keyword.
  Use when: "GenT2I", "텍스트로 이미지 생성", t2i, text to image generation.
argument-hint: "[gpt|nano|cinema|soul|soulcine] <prompt>"
allowed-tools: Bash, Read, Skill
---

# GenT2I

Text-to-image generation using Higgsfield. The first argument is the model shorthand; everything after is the prompt.

## 원문 규격 참조 (필수)

프롬프트를 확장하기 전에 `~/.claude/skills/Lira/SKILL.md`를 Read한다.

> 이 파일은 이 저장소에 함께 들어 있다 (출처: Higgsfield). 못 찾으면 `~/.claude/CLAUDE.md`의
> **프롬프트 규칙 10개**를 근거로 진행한다 — 중단하지 않는다.
`~/.claude/CLAUDE.md`의 **프롬프트 규칙 10개**는 항상 적용된다.

## Step 1 — Parse Arguments

- First word: model shorthand
  - `gpt` → `gpt_image_2`
  - `nano` → `nano_banana_2` (Nano Banana Pro)
  - `cinema` → `cinematic_studio_2_5`
  - `soul` → `text2image_soul_v2` (Soul 2.0 — 인물. **21:9 없음**)
  - `soulcine` → `soul_cinematic` (Soul Cinema — 배경·필름 스틸. 21:9 지원)
  - Anything else → print error and stop: `❌ Unknown model. Use: gpt / nano / cinema / soul / soulcine`
- Remaining words: the full prompt

**모델을 지정하지 않았으면 Lira 라우팅으로 고른다:** 인물·캐스팅 → `soul` /
장소·환경·필름 스틸 → `soulcine` / 소품·제품형 → `nano` 또는 `gpt`.
라우팅과 다른 모델을 지정했으면 한 줄로 알리고 지정대로 진행한다.

## Step 2 — Translate & Enhance Prompt (Lira 4-D)

한국어(또는 비영어) 입력은 영어로 번역하고, **자유롭게 부풀리지 말고 Lira의 4-D로** 확장한다.

1. **DECONSTRUCT** — 핵심 의도·피사체·맥락을 분리한다. 주어진 것과 빠진 것을 가른다.
2. **DIAGNOSE** — 모호한 곳을 찾는다: 카메라 앵글 / 조명 / 팔레트 / 인원수 / 프레이밍.
   알려진 실패 모드(일러스트 드리프트, 문자·문신 아티팩트, 다중 인물 붕괴, 과대 프롬프트) 위험을 본다.
3. **DEVELOP** — 요청 타입에 맞는 Lira 템플릿을 고른다
   (인물 / 장소·환경 / 소품 / 편집). 모델에 명확한 역할(카메라·렌즈·촬영 무드)을 준다.
4. **DELIVER** — 완성 프롬프트를 낸다.

**확장할 때 지키는 것:**
- **자연스러운 산문.** 키워드 스택(`4k, masterpiece, trending`)은 아무 효과가 없다. CAPS 헤더도 쓰지 않는다.
- **부풀리지 않는다.** 촘촘한 80–150단어가 흩어진 400단어를 이긴다. 총 1500–2000자 이내.
- **긍정으로.** 네거티브 프롬프트 파라미터가 없는 모델들이라 NOT 스택은 그 개념을 주입한다.
  `no acne` ✗ → `clean dry skin` ✓ / `no people` ✗ → `empty deserted street` ✓
- **조명·재질은 기술적으로.** `dramatic cinematic lighting` ✗ →
  `single overhead key light, soft 2:1 ratio, smooth falloff` ✓. 재질은 이름 + 마감으로
  (`board-formed concrete`, `oxidized copper verdigris`).
- **팔레트는 60/30/10.** 실제 색 이름으로. 사용자 지시·장면 맥락·업로드 레퍼런스에서 끌어오고
  **없는 팔레트를 지어내지 않는다.**
- **화면비·해상도는 프롬프트에 넣지 않는다.** CLI 파라미터로 넘긴다.
- **`rule of thirds`를 넣는다** — 캐릭터 시트만 예외.
- 문자를 넣을 땐 **정확한 문구를 따옴표로** + 폰트·굵기·색.
  문신은 구체적인 실제 도안 + `clean line-work`.
- 실존 인물 이름·IP·브랜드 금지 → 특징 서술로 바꾼다.
- 포토리얼이면 `painterly` / `character reference sheet` 금지 (일러스트 트리거).

Do NOT call any external API; perform the translation and expansion yourself.

Show the enhanced prompt to the user before generating:
> 🔍 Enhanced prompt: `{enhanced English prompt}`

Use the enhanced English prompt for generation.

## Step 3 — Generate Image

Default aspect ratio is **16:9** unless the user specifies otherwise.
Aspect ratio and resolution are **platform parameters** — they belong in the CLI flags below, never in the prompt text.

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

### soul (Soul 2.0 — 인물):
`quality`가 `1.5k|2k`이고 **`resolution` 파라미터가 없다.** **21:9도 없다.**
```bash
higgsfield generate create text2image_soul_v2 \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --quality 2k \
  --wait --wait-timeout 10m
```
Soul ID가 있으면 `--custom_reference_id {ID}`를 붙여 얼굴을 고정한다 (`higgsfield soul-id list`).

### soulcine (Soul Cinema — 배경·필름 스틸):
`quality`가 `1.5k|2k`이고 **`resolution` 파라미터가 없다.** 21:9 지원.
```bash
higgsfield generate create soul_cinematic \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --quality 2k \
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
