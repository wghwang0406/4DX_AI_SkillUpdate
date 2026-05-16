---
version: 1.1.0
name: GenConti2Img
description: |
  Storyboard(콘티) 이미지를 레퍼런스로 삼아 GPT Image 2 / Nano Banana Pro / Cinematic Studio 2.5로
  씬별 최종 이미지를 배치 생성한다.
  콘티 이미지는 {EP}/Conti/{SEQ_ID}/ 폴더에서 읽고, shotlist_{SEQ_ID}.md에서 캐릭터 정보를 추출한다.
  배경 이미지와 캐릭터 시트를 자동으로 찾아 레퍼런스로 넣고, 콘티 구도를 vision으로 분석해 프롬프트를 작성한다.
  Use when: "GenConti2Img", "GenConti2image", "콘티로 이미지 만들어", "씬 이미지 생성", "storyboard to image".
  Model shorthand: gpt(default) / nano / cinema
argument-hint: "<SEQUENCE_ID> [gpt|nano|cinema]"
allowed-tools: Bash, Read
---

# GenConti2Img

콘티(storyboard) → 최종 씬 이미지 배치 생성 스킬.

## 폴더 구조 규칙

```
{project_root}/
├── config.md
├── Projectprompt.md
├── EP01/
│   ├── character/
│   │   └── {name}_Character*.png
│   ├── Conti/
│   │   └── S41/
│   │       ├── 0010_v1.png    ← 콘티 이미지
│   │       ├── 0020_v1.png
│   │       └── shotlist_S41.md
│   └── Image/
│       └── S41/
│           ├── Background.png
│           ├── 0010_v1.png    ← 씬 이미지 출력
│           └── 0020_v1.png
```

## 모델 단축명

| 단축명 | 모델 ID | 특징 |
|---|---|---|
| `gpt` | `gpt_image_2` | 기본값. 레퍼런스 이미지 처리 우수 |
| `nano` | `nano_banana_2` | 빠른 생성 |
| `cinema` | `cinematic_studio_2_5` | 시네마틱 스타일 |

인자 없으면 `gpt` 사용.

## Step 1 — config.md 읽기

```bash
ls config.md 2>/dev/null | head -1
```

없으면 중단:
```
❌ config.md를 찾을 수 없습니다. 먼저 /GenInit을 실행하세요.
```

Read 툴로 config.md 읽어 `project_code`와 Episode Mapping 파악.

## Step 2 — 인자 파싱

- 첫 번째 인자: SEQUENCE_ID (예: `S41` 또는 `41` → `S41` 변환)
- 두 번째 인자 (선택): 모델 단축명 (`gpt` / `nano` / `cinema`)

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

배경 이미지 확인:
```bash
ls "{EP}/Image/{SEQ_ID}/Background.png" 2>/dev/null || echo "NOT FOUND"
```

없으면 에러: `❌ Background 파일을 찾을 수 없습니다: {EP}/Image/{SEQ_ID}/Background.png`

## Step 3 — 콘티 이미지 목록 수집

```bash
ls "{EP}/Conti/{SEQ_ID}/"[0-9]*.png 2>/dev/null | sort -V
```

파일명에서 샷 번호 추출: `0010_v1.png` → `0010` (최신 버전만 사용, sort -V 후 tail로 선택)

## Step 4 — shotlist에서 샷별 캐릭터 정보 추출

Read 툴로 `{EP}/Conti/{SEQ_ID}/shotlist_{SEQ_ID}.md` 읽기.

없으면 에러: `❌ shotlist_{SEQ_ID}.md를 찾을 수 없습니다.`

shotlist 테이블의 "인물" 컬럼에서 각 샷 번호에 해당하는 캐릭터 목록 파악:

```
| 0010 | EWS | — | 비포장 산길 진입 | ✅ |   → 캐릭터 없음
| 0070 | CU  | 해수 | 권총 꺼냄 | ⏳ |      → 해수
| 0090 | MS  | 해수, 의현 | 반격 | ⏳ |     → 해수, 의현
```

`—` 또는 비어있으면 캐릭터 없음으로 처리.

## Step 5 — 캐릭터 레퍼런스 탐색

```bash
ls "{EP}/character/{name}_Character*.png" 2>/dev/null | head -1
```

shotlist에서 추출한 캐릭터마다 glob으로 탐색. 없으면 경고만 표시하고 진행.

## Step 6 — 콘티 Vision 분석

각 콘티 이미지를 읽어서 다음 **세 가지만** 파악한다.
캐릭터 외형(머리색, 의상, 체형 등)은 절대 콘티에서 읽지 않는다 — 캐릭터 시트가 기준:

- **샷 사이즈** (wide shot / medium shot / close-up / extreme close-up 등)
- **카메라 앵글** (eye-level / low angle / high angle / OTS 등)
- **표정/감정** (shocked, laughing, playful, commanding 등)

## Step 7 — 이미지 생성

각 shot마다 생성. 출력 파일명: `{EP}/Image/{SEQ_ID}/{SHOT}_v{N}.png`
(이미 존재하면 버전 숫자 증가: v1 → v2 → v3)

`--image` 순서: 배경 → 콘티 → 캐릭터 시트(등장 인물 전원)

### gpt (기본):
```bash
higgsfield generate create gpt_image_2 \
  --prompt "{프롬프트}" \
  --image "{EP}/Image/{SEQ_ID}/Background.png" \
  --image "{EP}/Conti/{SEQ_ID}/{SHOT}_v{N}.png" \
  --image "{EP}/character/{char1}_Character*.png" \
  --image "{EP}/character/{char2}_Character*.png" \
  --aspect_ratio 16:9 \
  --quality high \
  --resolution 2k \
  --wait --wait-timeout 10m
```

### nano:
```bash
higgsfield generate create nano_banana_2 \
  --prompt "{프롬프트}" \
  --image "{EP}/Image/{SEQ_ID}/Background.png" \
  --image "{EP}/Conti/{SEQ_ID}/{SHOT}_v{N}.png" \
  --image "{EP}/character/{char1}_Character*.png" \
  --aspect_ratio 16:9 \
  --resolution 2k \
  --wait --wait-timeout 10m
```

### cinema:
```bash
higgsfield generate create cinematic_studio_2_5 \
  --prompt "{프롬프트}" \
  --image "{EP}/Image/{SEQ_ID}/Background.png" \
  --image "{EP}/Conti/{SEQ_ID}/{SHOT}_v{N}.png" \
  --image "{EP}/character/{char1}_Character*.png" \
  --aspect_ratio 16:9 \
  --resolution 2k \
  --wait --wait-timeout 10m
```

## 프롬프트 작성 규칙

Vision 분석에서 추출한 **샷 사이즈 / 카메라 앵글 / 표정**만 사용.

### 프롬프트에 절대 쓰지 않는 것
- 캐릭터 외형: 머리색, 의상, 체형 등 → 캐릭터 시트가 기준
- 캐릭터 위치/포즈/행동 → 콘티 이미지 레퍼런스가 전달
- 씬 설명, 대사 내용 → 포함 금지

### 프롬프트에 써야 하는 것
- 샷 사이즈: extreme close-up / close-up / medium shot / wide shot
- 카메라 앵글: eye-level / low angle / high angle / OTS
- 표정/감정: terrified / laughing / playful / commanding 등

```
3D animated film cinematic still, Pixar-quality CG animation.
{샷 사이즈}, {카메라 앵글} — {캐릭터명(들)} with {표정/감정} expression(s).
Follow each character reference image exactly for all character appearance, clothing, and 3D style.
Follow the background reference image exactly for the environment.
Use the storyboard image for shot size, camera angle, and composition only — do NOT copy character appearance or art style from it.
No text, no subtitles, no watermarks, no storyboard annotations.
```

## Step 8 — 결과 저장 및 표시

각 이미지:
```
✅ Shot {SHOT} → {EP}/Image/{SEQ_ID}/{SHOT}_v{N}.png
[{SHOT}_v{N}.png]({URL})
{URL}
```

완료 요약: "✅ {N}개 이미지 생성 완료 → {EP}/Image/{SEQ_ID}/"

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
| Background.png 없음 | 에러 중단, 위치 안내 |
| shotlist 없음 | 에러 중단 |
| 캐릭터 시트 없음 | 경고 후 캐릭터 레퍼런스 없이 생성 |
| NSFW 차단 | 해당 shot 스킵, 완료 후 재시도 안내 |
| 생성 실패 | 해당 shot 스킵, 에러 메시지 표시 |
