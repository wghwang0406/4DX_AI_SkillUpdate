---
version: 1.4.0
name: GenConti2Img
description: |
  Storyboard(콘티) 이미지를 레퍼런스로 삼아 씬별 최종 이미지를 배치 생성한다.
  샷 사이즈에 따라 배경·등장체 레퍼런스 뷰를 자동 선택한다.
  콘티 이미지는 {EP}/Conti/{SEQ_ID}/ 폴더에서 읽고, shotlist_{SEQ_ID}.md에서 캐릭터 정보를 추출한다.
  배경 이미지와 캐릭터 시트를 자동으로 찾아 레퍼런스로 넣고, 콘티 구도를 vision으로 분석해 프롬프트를 작성한다.
  Use when: "GenConti2Img", "GenConti2image", "콘티로 이미지 만들어", "씬 이미지 생성", "storyboard to image".
  Model shorthand: gpt(default) / nano / cinema / soulcine
argument-hint: "<SEQUENCE_ID> [gpt|nano|cinema|soulcine]"
allowed-tools: Bash, Read, Skill
---

# GenConti2Img

콘티(storyboard) → 최종 씬 이미지 배치 생성 스킬.

캐시가 있으면 콘티 Vision 분석을 스킵하고, 없으면 분석 후 캐시에 저장한다.

## 원문 규격 참조 (필수)

프롬프트를 쓰기 전에 `~/.claude/skills/Lira/SKILL.md`를 Read한다 (특히 *CRITICAL: Anti-fail rules*).
표정을 쓸 때는 `~/.claude/skills/Acting/SKILL.md`.

> 두 파일은 저장소에 없다 (힉스필드 배포본, 별도 설치). 없으면 `~/.claude/CLAUDE.md`의
> **프롬프트 규칙 10개**를 근거로 진행한다 — 중단하지 않는다.
`~/.claude/CLAUDE.md`의 **프롬프트 규칙 10개**는 항상 적용된다.

## 폴더 구조 규칙

```
{project_root}/
├── config.md
├── Projectprompt.md
├── EP01/
│   ├── character/
│   │   ├── Character.md              ← 에셋 사전 (@태그 ↔ 앵커)
│   │   ├── char/  {name}_Character_{sheet,front,back,face}_v*.png
│   │   ├── loc/   {name}_Location_{wide,34,top,detail}_v*.png
│   │   └── prop/  {name}_Prop_{top,34,detail}_v*.png
│   ├── Conti/
│   │   └── S41/
│   │       ├── S41_0010_v1.png    ← 콘티 이미지
│   │       ├── S41_0020_v1.png
│   │       └── shotlist_S41.md
│   └── Image/
│       └── S41/
│           ├── S41_Background.png  ← 에셋이 없을 때만 쓰는 폴백
│           ├── S41_0010_v1.png    ← 씬 이미지 출력
│           └── S41_0020_v1.png
```

**하위호환:** `char/` `loc/` `prop/`이 없고 `{EP}/character/{name}_Character*.png`만 있는
기존 프로젝트도 그대로 동작한다 — runner가 하위폴더에서 못 찾으면 flat 경로로 폴백한다.

## 샷 사이즈 → 레퍼런스 뷰 (runner가 자동 선택)

| 샷 사이즈 | 배경 | 등장체 |
|---|---|---|
| EWS / WS / LS | `loc_wide` | `char_front` |
| MS / MWS / MLS / OTS | `loc_34` | `char_front` |
| CU / ECU / BCU | `loc_detail` | `char_face` |
| 뒷모습 샷 | 샷 사이즈 따름 | `char_back` (`char_view` 로 지정) |

**`loc_top`(탑다운 평면도)은 레퍼런스로 물리지 않는다.** Sceneprompt의 LOCATION MAP을
쓸 때 vision으로 읽는 용도다.

## 모델 단축명

| 단축명 | 모델 ID | 특징 |
|---|---|---|
| `gpt` | `gpt_image_2` | 기본값. 레퍼런스 이미지 처리 우수 |
| `nano` | `nano_banana_2` | Nano Banana Pro. 레퍼런스 최대 14장, 최대 4K |
| `cinema` | `cinematic_studio_2_5` | 시네마틱 스타일 |
| `soulcine` | `soul_cinematic` | Soul Cinema — 배경·환경·필름 스틸. 21:9 지원 |

인자 없으면 `gpt` 사용. 배경 폴백 생성은 단축명과 무관하게 `soul_cinematic`을 쓴다.

## Step 0 — 캐시 확인

```bash
PROJ_ROOT=$(python3 -c "import pathlib,sys; p=pathlib.Path('.').resolve(); [sys.exit(print(str(x))) or 0 for x in [p]+list(p.parents) if (x/'config.md').exists()]; sys.exit(print(str(p)))")
RUNNER="$PROJ_ROOT/runner.py"
CACHE="$PROJ_ROOT/.cache.json"
# 엔진 자동 확보: runner.py 없으면 공유 번들에서 복사 (있으면 안 덮음)
[ -f "$RUNNER" ] || cp -n "$HOME/.claude/skills/_shared/scripts/core/runner.py" "$HOME/.claude/skills/_shared/scripts/core/cache.py" "$HOME/.claude/skills/_shared/scripts/core/models.py" "$PROJ_ROOT/" 2>/dev/null
# runner.py 는 있는데 models.py 만 없는 프로젝트도 보정한다 (runner가 import 한다)
[ -f "$PROJ_ROOT/models.py" ] || cp -n "$HOME/.claude/skills/_shared/scripts/core/models.py" "$PROJ_ROOT/" 2>/dev/null
```

```bash
ls "$CACHE" 2>/dev/null | head -1
```

파일이 있으면:
```bash
python3 "$RUNNER" check-cache {SEQ_ID} all --workflow genconti2img
```

출력 JSON의 `needs_analysis` = 분석 필요한 샷.
출력 JSON의 `cached` = 캐시 히트 샷 (Step 4~6 스킵, 바로 Step 7 API 호출로).

파일 없으면: 전체 샷을 `needs_analysis`로 간주, Step 1부터 정상 진행.

## Step 1 — config.md 읽기

```bash
ls config.md 2>/dev/null | head -1
```

없으면 중단:
```
❌ config.md를 찾을 수 없습니다. 먼저 /GenSetup을 실행하세요.
```

Read 툴로 config.md 읽어 `project_code`와 Episode Mapping 파악.

## Step 2 — 인자 파싱

- 첫 번째 인자: SEQUENCE_ID (예: `S41` 또는 `41` → `S41` 변환)
- 두 번째 인자 (선택): 모델 단축명 (`gpt` / `nano` / `cinema` / `soulcine`)

Episode Mapping에서 해당 시퀀스의 에피소드 파악:
```
| S41 | EP01 | → EPISODE=EP01
```

테이블에 없으면:
```
⚠️ {SEQ_ID}의 에피소드 매핑이 config.md에 없습니다. config.md에 추가해주세요.
❌ 중단
```

콘티 폴더 확인:
```bash
ls "{EP}/Conti/{SEQ_ID}/" 2>/dev/null || echo "NOT FOUND"
```

없으면 에러: `❌ 콘티 폴더를 찾을 수 없습니다: {EP}/Conti/{SEQ_ID}/`

## Step 2-A — Sceneprompt.md 자동 보완

```bash
wc -c "{EP}/Image/{SEQ_ID}/Sceneprompt.md" 2>/dev/null
```

비어있거나 없으면 → 콘티 이미지 중 첫 번째를 Read 툴로 Vision 분석해 씬 분위기·장소·카메라 스타일을 **한국어로** Sceneprompt.md에 작성.

```
⚙️ Sceneprompt.md가 비어있어 콘티 이미지에서 자동 생성합니다...
```

## Step 2-B — Shotprompt.md 자동 보완

```bash
wc -c "{EP}/Image/{SEQ_ID}/Shotprompt.md" 2>/dev/null
```

비어있거나 없으면 → shotlist_{SEQ_ID}.md 읽기 + 콘티 이미지 각 샷 Vision 분석 → 샷별 한국어 방향 항목을 Shotprompt.md에 작성:

```
0010. {샷 사이즈} — {카메라 앵글}. {주요 액션/감정}.
0020. ...
```

```
⚙️ Shotprompt.md가 비어있어 콘티 이미지에서 자동 생성합니다...
```

## Step 2-C — 배경 레퍼런스 확보

**먼저 배경 에셋이 있는지 본다.** 있으면 runner가 샷 사이즈에 맞는 뷰를 자동으로 고르므로
여기서 할 일이 없다.

```bash
ls "{EP}/character/loc/"*_Location_*.png 2>/dev/null | head -5
```

**있으면** → 스킵. shotlist의 `장소` 컬럼 값을 그대로 `location` 필드에 넣기만 하면 된다.

**없으면** → 폴백. 시퀀스 배경 한 장을 만든다:
```bash
ls "{EP}/Image/{SEQ_ID}/{SEQ_ID}_Background.png" 2>/dev/null || echo "NOT_FOUND"
```
```
⚙️ 배경 에셋이 없어 시퀀스 배경 한 장을 생성합니다.
   (클로즈업 샷에도 이 와이드 한 장이 물립니다 — /GenSetup으로 배경 4뷰를 만들면 샷 사이즈에 맞는 뷰가 자동 선택됩니다)
```

Sceneprompt.md 기반, Lira의 *Location / environment* 템플릿으로 **Soul Cinema**에서:
```bash
higgsfield generate create soul_cinematic \
  --prompt "{카메라 앵커}. {장소 정체성}. {주요 요소}. {광원+방향+색온도}. {팔레트}. {tech block}. Empty deserted interior, bare walls, still air." \
  --aspect_ratio 16:9 \
  --quality 2k \
  --wait --wait-timeout 10m
```
> ⚠️ Soul 계열은 `--quality`가 `1.5k|2k`이고 **`--resolution` 파라미터가 없다.**
> `gpt`/`nano`/`cinema`와 플래그가 다르니 섞어 쓰지 않는다.
- 인물을 넣지 않는다. **비어 있음은 긍정문으로** 쓴다 (`empty deserted` ○ / `no people` ✗).
- 옵틱·DOF 언어는 배경에서 뺀다 (인물 전용).
- 그레인 단어를 겹쳐 쌓지 않는다 — 시네마 모델이 네이티브로 갖고 있다.

생성 후 로컬 저장:
```bash
curl -o "{EP}/Image/{SEQ_ID}/{SEQ_ID}_Background.png" "{URL}"
```

완료 메시지:
```
✅ {SEQ_ID}_Background.png 생성 완료 → {EP}/Image/{SEQ_ID}/{SEQ_ID}_Background.png
```

## Step 3 — 콘티 이미지 목록 수집

```bash
ls "{EP}/Conti/{SEQ_ID}/{SEQ_ID}_"[0-9]*.png 2>/dev/null | sort -V
```

파일명에서 샷 번호 추출: `{SEQ_ID}_0010_v1.png` → `{SEQ_ID}_` 접두사 제거 후 4자리 숫자 추출 → `0010` (최신 버전만 사용, sort -V 후 tail로 선택)

## Step 4 — shotlist에서 샷별 캐릭터 정보 추출

Read 툴로 `{EP}/Conti/{SEQ_ID}/shotlist_{SEQ_ID}.md` 읽기.

없으면 에러: `❌ shotlist_{SEQ_ID}.md를 찾을 수 없습니다.`

각 샷마다 **샷사이즈 / 인물 / 장소 / 소품**을 뽑는다.
샷사이즈는 러너가 레퍼런스 뷰를 고르는 근거이므로 정확히 읽는다.

```
| # | 샷사이즈 | 인물 | 장소 | 소품 | 묘사 | 상태 |
| 0010 | EWS | — | 카페 | — | 비포장 산길 진입 | ✅ |   → 인물 없음, 배경 wide
| 0070 | CU  | 해수 | 카페 | 권총 | 권총 꺼냄 | ⏳ |     → 해수 face, 배경 detail, 소품 권총
| 0090 | MS  | 해수, 의현 | 카페 | — | 반격 | ⏳ |       → 둘 다 front, 배경 34
```

- `—` 또는 비어있으면 없음으로 처리.
- **구형 5컬럼 테이블**(`# / 샷사이즈 / 인물 / 묘사 / 상태`)도 그대로 읽는다.
  장소·소품 컬럼이 없으면 해당 필드를 비우고 진행 — 배경은 기존 `Background.png` 폴백을 쓴다.

## Step 5 — 레퍼런스 탐색

runner가 샷 사이즈에 맞는 뷰를 자동으로 고르므로 **여기선 이름만 넘기면 된다**
(`characters` / `location` / `props`). 탐색 순서는 하위폴더의 요청 뷰 → 대체 뷰 → 레거시 flat.

에셋이 실제로 있는지만 확인해 없으면 경고한다:
```bash
ls "{EP}/character/char/" "{EP}/character/loc/" "{EP}/character/prop/" 2>/dev/null
ls "{EP}/character/"*_Character*.png 2>/dev/null | head -3   # 레거시 flat
```

없으면 경고만 표시하고 진행:
```
⚠️ @해수 시트를 찾을 수 없습니다 — 캐릭터 일관성이 흔들릴 수 있습니다. /GenSetup으로 생성하세요.
```

## Step 6 — 콘티 Vision 분석

각 콘티 이미지를 읽어서 다음 **세 가지만** 파악한다.
캐릭터 외형(머리색, 의상, 체형 등)은 절대 콘티에서 읽지 않는다 — 캐릭터 시트가 기준:

- **샷 사이즈** (EWS / WS / MS / MWS / OTS / CU / ECU) — 러너의 뷰 선택 입력값이므로 약어로 정확히
- **카메라 앵글** (eye-level / low angle / high angle / OTS 등)
- **표정** — 감정어가 아니라 **관찰 가능한 근육의 일**로 쓴다 (Acting 규격)

| ✗ 감정어 | ✓ 몸 |
|---|---|
| `terrified` | `eyes wide, jaw slack, shoulders drawn up` |
| `angry` | `jaw set, brow low and still, nostrils flared` |
| `sad` | `lower lip loose, gaze dropped, breath held high in the chest` |

모델에 감정 단어를 주면 알아서 지어낸다. 근육의 일을 주면 그것만 한다.

## Step 6b — 캐시 저장 (분석한 샷만)

`needs_analysis` 샷 각각에 대해 Vision 분석 + 프롬프트 구성이 끝나면 캐시에 저장:

```bash
echo '{
  "shot": "0070",
  "prompt": "완성된 최종 프롬프트 전체",
  "vision_text": "샷 사이즈 / 앵글 / 표정 분석 요약",
  "shot_size": "CU",
  "location": "카페",
  "props": ["권총"],
  "characters": ["해수"],
  "image_files": [],
  "image_sigs": [],
  "image_mode": "single",
  "multi_shot": false,
  "workflow": "genconti2img",
  "conti_image": "EP01/Conti/S41/S41_0070_v1.png",
  "background_file": "EP01/Image/S41/S41_Background.png"
}' | python3 "$RUNNER" write-shot {SEQ_ID}
```

| 필드 | 용도 |
|---|---|
| `shot_size` | **러너가 배경/등장체 뷰를 고르는 근거.** 없으면 wide/front로 처리 |
| `location` | 배경 에셋 이름. 없거나 못 찾으면 `background_file`로 폴백 |
| `props` | 소품 에셋 이름 목록. 없으면 `[]` |
| `characters` | 등장체 이름 목록. 없으면 `[]` |
| `char_view` | (선택) 뒷모습 샷이면 `"back"`으로 덮어씀 |
| `background_file` | 배경 에셋이 없을 때 쓰는 폴백 경로 — 기존 동작 유지용 |

출력: `CACHE_WRITE:0010:ok`

## Step 7 — 이미지 생성 (Python 러너 위임)

캐시에 프롬프트가 저장된 후 Python 러너에게 API 호출을 위임한다.

```bash
cd "$PROJ_ROOT" && python3 "$RUNNER" \
  genconti2img {SEQ_ID} all --model {model}
```

모델 인자: `--model gpt` (기본) / `--model nano` / `--model cinema`

**stdout 파싱 규칙:**

| 출력 | 표시 |
|---|---|
| `SHOT_START:0010` | `[1/N] Shot 0010 생성 중...` |
| `SHOT_DONE:0010:{url}` | `✅ Shot 0010 → EP01/Image/S41/S41_0010_v1.png\n[S41_0010_v1.png]({url})\n{url}` |
| `SHOT_SKIP:0010:{url}` | `⏳ Shot 0010: 이미 완료됨` |
| `SHOT_FAIL:0010:{err}` | `❌ Shot 0010: {err}` |
| `BATCH_DONE:{s}:{f}:{k}` | `✅ {s}개 이미지 생성 완료` |

## 프롬프트 작성 규칙

Vision 분석에서 추출한 **샷 사이즈 / 카메라 앵글 / 표정(근육)** 만 사용.

### 프롬프트에 절대 쓰지 않는 것
- 캐릭터 외형: 머리색, 의상, 체형 등 → 캐릭터 시트가 기준
- 캐릭터 위치/포즈/행동 → 콘티 이미지 레퍼런스가 전달
- 씬 설명, 대사 내용 → 포함 금지
- **스타일 문장을 직접 박아넣기** → Projectprompt.md에서 가져온다 (아래)
- `character reference sheet`, `painterly` → Lira 금칙어 (일러스트 드리프트 트리거)
- 키워드 스택(`4k, masterpiece, trending`) → 아무 효과 없다
- 화면비·해상도를 프롬프트 텍스트에 → CLI 파라미터로 넘긴다

### 프롬프트에 써야 하는 것
- 샷 사이즈: extreme close-up / close-up / medium shot / wide shot
- 카메라 앵글: eye-level / low angle / high angle / OTS
- 표정: **관찰 가능한 근육의 일** (`eyes wide, jaw slack` — `terrified` ✗)
- `rule of thirds` — 시트가 아닌 모든 이미지에 넣는다 (Lira 상시 규칙)
- 인원수·소품 개수를 못박는 긍정 제약

### 스타일은 상수다

첫 줄의 스타일 문장은 **Projectprompt.md에서 읽어온다.** 템플릿에 박아두지 않는다.
Projectprompt를 한 줄 고치면 이후 전 샷에 반영되어야 한다.
Projectprompt가 없거나 스타일 항목이 비어 있으면 `DETECTED_STYLE`로 폴백한다.

```
{Projectprompt의 스타일 앵커}.
{샷 사이즈}, {카메라 앵글} — {캐릭터명(들)}, {표정을 근육의 일로}.
Follow each character reference image exactly for all character appearance, clothing, and style.
Follow the background reference image for the environment, materials and lighting direction only.
Use the storyboard image for shot size, camera angle, and composition only — do NOT copy character appearance or art style from it, and do NOT inherit its color.
Rule of thirds. Exactly {N} people in frame{, exactly one 소품}.
Clean plate with no lettering: unmarked surfaces, no subtitles, no watermarks, no storyboard annotations.
```

마지막 줄이 부정문 나열이 아니라 **원하는 상태를 먼저 쓰고** 그 옆에 국소 락을 붙인 형태인 점에 주의.
Lira: 생성 프롬프트에서 NOT 스택은 그 개념을 오히려 주입한다.

**길이:** 1500–2000자를 넘기지 않는다. 정밀함이 장황함을 이긴다.

## Step 8 — 결과 저장 및 표시

각 이미지:
```
✅ Shot {SHOT} → {EP}/Image/{SEQ_ID}/{SEQ_ID}_{SHOT}_v{N}.png
[{SEQ_ID}_{SHOT}_v{N}.png]({URL})
{URL}
```

완료 요약: "✅ {N}개 이미지 생성 완료 → {EP}/Image/{SEQ_ID}/"

## Step 9 — 드리프트 확인 (추가 생성 0장, 배치당 1회)

배치가 끝나면 방금 만든 이미지 **1~2장**을 등장체 시트와 Read(vision)로 대조한다.
새로 생성하지 않는다. 배치마다 한 번만 한다 — 샷마다 하면 느려진다.

인물이 나온 샷 하나를 골라 `char/{이름}_Character_sheet_v*.png`와 나란히 보고,
얼굴 구조·헤어·의상·체형이 유지됐는지 본다.

어긋났으면 경고만 하고 끝낸다 (재생성은 사용자가 결정):
```
⚠️ 드리프트 감지 — Shot 0090의 @해수 헤어 길이가 시트와 다릅니다.
   Character.md 앵커의 "shoulder-length black hair"가 모호합니다.
   → "shoulder-length black hair, blunt cut, always tied back in a low ponytail"
   앵커를 고치고 해당 샷만 --force로 재생성하면 됩니다.
```

문제가 없으면 한 줄:
```
✅ 드리프트 확인 (기존 이미지 2장 대조, 생성 0장) — 이상 없음
```

## UX 규칙

- 사용자 언어(한국어/영어)로 응답
- 각 shot 진행 상황 간략히 표시: `[1/4] Shot 0010 생성 중...`
- 에러 시 명확한 메시지와 원인 표시
- Job ID 노출 금지
- 모든 결과에 마크다운 링크와 Raw URL 둘 다 표시

## 콘티 이미지 제외 판단 기준

콘티의 캐릭터 디자인이 캐릭터 시트와 크게 다를 경우 콘티를 `--image`에서 제외하고 구도를 프롬프트에 직접 기술.

| 상황 | 콘티 포함 여부 |
|---|---|
| 콘티 캐릭터 ≈ 시트 | 포함 (구도 레퍼런스로 활용) |
| 콘티 캐릭터 ≠ 시트 | 제외, 구도를 프롬프트로 기술 |

## 에러 처리

| 상황 | 대응 |
|---|---|
| {EP}/Conti/{SEQ_ID}/ 없음 | 에러 중단, GenConti 먼저 실행 안내 |
| Background.png 없음 | Sceneprompt 기반 자동 생성 후 진행 |
| shotlist 없음 | 에러 중단 |
| 캐릭터 시트 없음 | 경고 후 캐릭터 레퍼런스 없이 생성 |
| NSFW 차단 | 해당 shot 스킵, 완료 후 재시도 안내 |
| 생성 실패 | 해당 shot 스킵, 에러 메시지 표시 |
