---
version: 1.2.0
name: GenVideo
description: |
  Image-to-video generation. Single shot or batch (range/all).
  Reads config.md for project code and episode mapping.
  Reads {EP}/Image/{SEQ}/Sceneprompt.md + Shotprompt.md, analyzes images with vision, generates video.
  Pair mode: if "{SHOT}-1_v*.png" + "{SHOT}-2_v*.png" both exist, auto-pair on single spec. Or pass "0010+0020" explicitly.
  Single images use start-image only. Default model: Kling 3.0. Pass "seedance" to use Seedance 2.0.
  Use when: "GenVideo", "영상 만들어", "i2v", "GenSingle", "GenBatch", batch or single video generation.
argument-hint: "<SEQUENCE_ID> <0010 | 10+11 | 0010-0030 | all> [seedance]"
allowed-tools: Bash, Read
---

# GenVideo

Image-to-video generation skill. Handles single shot or batch. Default model: Kling 3.0.

**프롬프트 합성은 runner가 코드로 담당한다.** 모델은 번역된 슬롯(`scene_en` / `shot_dir_en` / `vision_en`)만 채워 캐시에 저장하고, runner가 이를 **모션 우선 구조**로 조립해 `--prompt`에 넣는다. (i2v는 정지 화면을 이미지가 담당하므로 정적 재묘사보다 카메라·모션·동작이 중요)

**빈 MD 자동 보완:** Sceneprompt/Shotprompt가 비어있으면 샷 이미지를 Vision 분석해 자동으로 채운다(한국어). Projectprompt는 제외(GenSetup 소관). 슬롯이 채워지려면 이 MD가 있어야 하므로 슬롯 작성(Step 7) 전에 수행한다.

캐시가 있으면 분석을 스킵하고, 없으면 기존 분석 후 캐시에 저장한다.

## Step 0 — 캐시 확인

인자 파싱 전에 먼저 프로젝트 루트를 감지하고 캐시 상태를 확인한다.

```bash
PROJ_ROOT=$(python3 -c "import pathlib,sys; p=pathlib.Path('.').resolve(); [sys.exit(print(str(x))) or 0 for x in [p]+list(p.parents) if (x/'config.md').exists()]; sys.exit(print(str(p)))")
RUNNER="$PROJ_ROOT/runner.py"
CACHE="$PROJ_ROOT/.cache.json"
# 엔진 자동 확보: runner.py 없으면 공유 번들에서 복사 (있으면 안 덮음)
[ -f "$RUNNER" ] || cp -n "$HOME/.claude/skills/_shared/scripts/core/runner.py" "$HOME/.claude/skills/_shared/scripts/core/cache.py" "$PROJ_ROOT/" 2>/dev/null
```

```bash
ls "$CACHE" 2>/dev/null | head -1
```

파일이 있으면:
```bash
python3 "$RUNNER" check-cache {SEQ_ID} {SHOT_SPEC} --workflow genvideo
```

출력 JSON의 `needs_analysis` 배열 = 분석이 필요한 샷 목록.
출력 JSON의 `cached` 배열 = 캐시 히트 샷 (Step 3~7 스킵).

파일이 없으면: `needs_analysis = 전체 샷`, `cached = []` 로 간주하고 Step 1부터 진행.

> **Step 3~7은 `needs_analysis` 샷에만 실행.** `cached` 샷은 바로 Step 8로.

## Step 1 — config.md 읽기 (Required)

```bash
ls config.md 2>/dev/null | head -1
```

없으면 중단:
```
❌ config.md를 찾을 수 없습니다. 먼저 /GenSetup을 실행하세요.
```

있으면 Read 툴로 읽어 `project_code`와 Episode Mapping 테이블을 메모리에 보관.

```bash
grep "project_code:" config.md | awk '{print $2}'
```

## Step 2 — 인자 파싱

- 첫 번째 인자: SEQUENCE_ID
  - `S41` 그대로 사용 / `41` 입력 시 → `S41`로 변환
- 두 번째 인자: SHOT_SPEC
  - `all` → `{EP}/Image/{SEQ}/`에서 전체 샷 탐색 (싱글 모드만)
  - `0010-0030` → [0010, 0020, 0030] 확장 (10 단위)
  - `0010,0030,0050` → [0010, 0030, 0050]
  - `0010` → 단일 샷
  - `0010` 단일 지정 시 이미지 자동 탐색:
    1. `0010-1_v*.png` 존재 → START = `0010-1_v*.png`; `0010-2_v*.png`도 존재 → **자동 페어 모드**
    2. `0010-1_v*.png` 없음 → `0010_v*.png` 사용 (싱글 모드)
  - `0010+0020` 또는 `10+20` → **명시적 Pair 모드**: 각 샷의 최우선 이미지 사용 (`-1_v*.png` → 없으면 `_v*.png`)
  - `10+20,30,40+50` → 혼합 목록 (페어 + 단독 혼용 가능)
  - 짧은 번호 자동 패딩: `10+20` → `0010+0020`, `7` → `0007`
  - 번호가 연속일 필요 없음: `14+17`, `10+50` 모두 가능
  - Seedance + 단일 샷: `0010-1`, `0010-2`, `0010-3`... 존재하는 모든 `-N` 파일을 `--image`로 첨부
- 마지막 인자 (선택):
  - 없으면 → Kling 3.0 (`kling3_0`)
  - `seedance` → Seedance 2.0 (`seedance_2_0`)

config.md의 Episode Mapping에서 해당 시퀀스의 에피소드 파악:
```
| S41 | EP01 | → EPISODE=EP01
```

테이블에 없으면:
```
⚠️ {SEQ}의 에피소드 매핑이 config.md에 없습니다. config.md에 추가해주세요.
❌ 중단
```

시퀀스 폴더 확인:
```bash
ls "{EP}/Image/{SEQ}/" 2>/dev/null || echo "NOT FOUND"
```

없으면 중단:
```
❌ Scene folder not found: {EP}/Image/{SEQ}/
```

`all` 지정 시 샷 목록 탐색 (`{SEQ}_` 접두사 포함, 싱글 모드):
```bash
ls "{EP}/Image/{SEQ}/{SEQ}_"[0-9]*_v*.png 2>/dev/null \
  | xargs -I{} basename {} | sed "s/^{SEQ}_//" | grep -oE '^[0-9]{4}' | sort -un
```

## Step 3 — Projectprompt.md 읽기 (Optional)

```bash
ls "Projectprompt.md" 2>/dev/null | head -1
```

없으면 스킵.

## Step 4 — Sceneprompt.md 읽기 + 자동 보완 (Required)

```bash
wc -c "{EP}/Image/{SEQ}/Sceneprompt.md" 2>/dev/null || echo "0 NOT_FOUND"
```

**내용이 있으면** → Read로 읽어 사용 (덮어쓰지 않음).

**비어있거나(헤더/공백만) 없으면** → **중단하지 말고 자동 보완**:
```
⚙️ Sceneprompt.md가 비어있어 샷 이미지에서 자동 생성합니다...
```
1. 대상 시퀀스 샷 이미지 중 대표 1~2장을 Read 툴로 Vision 분석.
2. 씬 분위기·장소·조명·카메라 스타일을 **한국어로** Sceneprompt.md에 작성 (Write).
3. 작성한 내용을 사용자에게 **출력해 보여준 뒤** 이어서 진행 (승인 대기 없음).
4. MD를 새로 썼으므로 → **캐시 정합성 처리**(아래 노트) 적용.

> **⚠️ 캐시 정합성:** Step 0 `check-cache`는 보완 **이전** MD sig로 판정한다.
> Sceneprompt/Shotprompt를 새로 채웠다면 해당 시퀀스 대상 샷을 **전부 `needs_analysis`로
> 간주**하고 Step 3부터 재진행한다 (또는 `check-cache`를 재실행). 채운 내용이 슬롯·sig에 반영됨.

## Step 5 — Shotprompt.md 읽기 + 자동 보완 (Optional → 자동 채움)

```bash
wc -c "{EP}/Image/{SEQ}/Shotprompt.md" 2>/dev/null || echo "0 NOT_FOUND"
```

**내용이 있으면** → Read로 읽어 사용 (덮어쓰지 않음).

**비어있거나 없으면** → **자동 보완**:
```
⚙️ Shotprompt.md가 비어있어 샷 이미지에서 자동 생성합니다...
```
1. 대상 각 샷 이미지를 Vision 분석 (있으면 `{EP}/Conti/{SEQ}/shotlist_{SEQ}.md` 참고).
2. **i2v용이므로 정지 묘사보다 움직임/카메라워크를 추론**해 샷별 한국어 방향을 작성 (Write):
   ```
   0010. {카메라 움직임} — {인물/피사체 동작·감정 변화}.
   0020. ...
   ```
3. 작성한 내용을 **출력해 보여준 뒤** 이어서 진행. MD를 새로 썼으면 위 캐시 정합성 노트 적용.

Shotprompt.md 형식:
```
0010. 첫 번째 샷 방향
0020. [multi] 두 번째 샷 방향
0030. 페어 샷도 start 번호로 작성 (0030 자동 페어 시 0030. 으로 찾음)
```

`[multi]` 태그 동작 — **싱글 샷 전용** (페어 스펙 `+`와 무관):
- **Kling + `[multi]`**: Kling 멀티샷 모드 — 단일 이미지에서 여러 클립 생성. runner.py 없으면 일반 싱글로 폴백.
- **Seedance + `[multi]`**: 멀티 참조 모드 — `--image {현재}` + `--image {이전(-10)}` + `--image {다음(+10)}`. 앞뒤 샷 없으면 해당 `--image` 생략.

페어 스펙 (`0010+0020`): `[multi]` 무관, 두 모델 모두 `--start-image` + `--end-image` 자동 사용.
페어 모드에서 Shotprompt는 **start 번호**(`{SHOT}.`)로 조회한다.

## Step 6 — 이미지 파일 탐색 (샷별)

SHOT_SPEC에 `+`가 포함된 경우 → **명시적 Pair mode**: START와 END 번호 분리 후 각각 최우선 이미지 탐색.
그 외 → 단일 샷 번호로 이미지 자동 탐색 (아래 우선순위).

```bash
# 단일 샷 이미지 탐색 우선순위 (파일명: {SEQ}_{SHOT}-1_v*.png 형식)
SHOT_IMG_1=$(ls "{EP}/Image/{SEQ}/{SEQ}_{SHOT}-1_v"*.png 2>/dev/null | sort -V | tail -1)
SHOT_IMG_PLAIN=$(ls "{EP}/Image/{SEQ}/{SEQ}_{SHOT}_v"*.png 2>/dev/null | sort -V | tail -1)
START_IMG="${SHOT_IMG_1:-$SHOT_IMG_PLAIN}"
# START_IMG 없으면 ⚠️ 이미지 없음 — 스킵

SHOT_IMG_2=$(ls "{EP}/Image/{SEQ}/{SEQ}_{SHOT}-2_v"*.png 2>/dev/null | sort -V | tail -1)
# SHOT_IMG_2 있으면 → 자동 Pair mode (END_IMG = SHOT_IMG_2)
# SHOT_IMG_2 없으면 → Single mode

# 명시적 Pair mode (SHOT_SPEC = "0010+0020" → START=0010, END=0020)
START_IMG=$(ls "{EP}/Image/{SEQ}/{SEQ}_{START}-1_v"*.png 2>/dev/null | sort -V | tail -1)
START_IMG="${START_IMG:-$(ls "{EP}/Image/{SEQ}/{SEQ}_{START}_v"*.png 2>/dev/null | sort -V | tail -1)}"
END_IMG=$(ls "{EP}/Image/{SEQ}/{SEQ}_{END}-1_v"*.png 2>/dev/null | sort -V | tail -1)
END_IMG="${END_IMG:-$(ls "{EP}/Image/{SEQ}/{SEQ}_{END}_v"*.png 2>/dev/null | sort -V | tail -1)}"
# 둘 다 있어야 함. 하나라도 없으면 ⚠️ 스킵
```

## Step 7 — Shotprompt 조회 + Vision 분석 + 프롬프트 구성

### 7a. Shotprompt 조회

모드에 관계없이 **`{START}.`** (start 번호 + 점)로 시작하는 줄 찾기.
- Pair mode(`0010+0020` 또는 자동 페어) → `0010.` 로 시작하는 줄 찾기
- Single mode(`0010`) → `0010.` 로 시작하는 줄 찾기

찾으면:
- `[multi]` 태그 → `MULTI_SHOT=true` (Single 전용, Pair는 무시)
- 한국어 텍스트 → 영어 번역 → `shot_dir_en` 슬롯에 사용 (7c)
찾지 못하면: `shot_dir_en`을 이미지 기반 모션으로 채우고, `MULTI_SHOT=false`.

### 7b. Vision 분석

Read 툴로 이미지 분석:
- **Pair**: start 이미지(`{SHOT}-1_v*.png` 또는 `{START}_v*.png`) + end 이미지(`{SHOT}-2_v*.png` 또는 `{END}_v*.png`) 둘 다
- **Single**: `{EP}/Image/{SEQ}/{SHOT}_v{N}.png` (최신 버전)

분석 요소:
- 핵심 시각 요소 (인물, 질감, 구조, 색감)
- 이미지 내용과 Shot Direction에 맞는 동작
- 분위기/조명 뉘앙스

### 7c. 프롬프트 슬롯 작성 (모델은 슬롯만, 조립은 runner)

최종 프롬프트를 직접 이어붙이지 말 것. 대신 아래 **3개 슬롯을 영문·간결하게** 채운다.
runner가 `scene_en → Camera & motion(shot_dir_en) → Action(vision_en)` 순서로 조립한다.

| 슬롯 | 내용 | 소스 |
|---|---|---|
| `scene_en` | 씬 무드/조명/톤 (필수). Projectprompt 핵심 톤이 있으면 1줄로 녹여 포함 | Projectprompt + Sceneprompt 번역 |
| `shot_dir_en` | **카메라워크·모션·액션 디렉션 (핵심).** i2v에서 가장 중요 — 비우지 말 것 | Shotprompt 해당 샷 줄 번역 |
| `vision_en` | 이미지에서 읽은 **움직임/표정변화/카메라 흐름만.** 정지 화면(구도·색·의상·인물 외형) 재묘사 **금지** | 이미지 vision 분석 |

- 한국어 소스는 모두 **영어로 번역**해 넣는다.
- Shotprompt에 해당 샷 줄이 없으면 `shot_dir_en`은 이미지 기반 모션으로 대체하되 최대한 채운다.
- 정적 묘사를 늘리면 영상 모델의 모션 신호가 희석되므로 **각 슬롯은 짧고 명료하게.**

## Step 7d — 캐시 저장 (분석한 샷만)

`needs_analysis` 샷 각각에 대해 분석이 끝나면 캐시에 저장한다.

각 샷마다 아래 JSON을 구성하고 `write-shot`에 파이프로 전달:

```bash
echo '{
  "shot": "0010",
  "scene_en": "번역된 씬 무드/조명/톤 (Project 핵심 톤 포함)",
  "shot_dir_en": "번역된 카메라워크·모션·액션 디렉션 (핵심)",
  "vision_en": "이미지에서 읽은 움직임/표정변화/카메라 흐름만 (정적 재묘사 금지)",
  "vision_text": "이미지 분석 요약 (참고 저장용)",
  "image_files": ["EP01/Image/S41/S41_0010_v1.png"],
  "image_sigs": [],
  "image_mode": "single",
  "multi_shot": false,
  "workflow": "genvideo"
}' | python3 "$RUNNER" write-shot {SEQ_ID}
```

`scene_en`/`shot_dir_en`/`vision_en` 3개 슬롯이 runner의 최종 프롬프트 재료다 (Step 7c 참조).
레거시 단일 `prompt` 필드도 여전히 허용되며, 슬롯이 하나도 없을 때만 폴백으로 사용된다.
`image_sigs`는 비워두면 Python이 자동으로 파일에서 읽는다.
Pair 모드면 `image_files`에 [start_file, end_file] 두 파일 모두, `image_mode`는 `"pair"`.
`shot` 키는 항상 **start 번호** 사용 (러너가 캐시를 start 번호로 조회).
`MULTI_SHOT=true`면 `"multi_shot": true`.

출력: `CACHE_WRITE:0010:ok`

## Step 8 — 영상 생성

runner.py가 있으면 러너에 위임, 없으면 higgsfield CLI 직접 실행.

**runner.py 있을 때:**
```bash
cd "$PROJ_ROOT" && python3 "$RUNNER" \
  genvideo {SEQ_ID} {SHOT_SPEC} --model {model}
```

**runner.py 없을 때 (직접 CLI):**

```bash
# 일반 싱글 샷
higgsfield generate create {model} \
  --image "{SHOT_IMG}" \
  --prompt "..." \
  --wait --wait-timeout 10m

# [multi] + Kling → runner.py 없으면 일반 싱글로 폴백
higgsfield generate create kling3_0 \
  --image "{SHOT_IMG}" \
  --prompt "..." \
  --wait --wait-timeout 10m

# [multi] + Seedance → 앞뒤 샷 --image 레퍼런스 추가
higgsfield generate create seedance_2_0 \
  --image "{SHOT_IMG}" \
  --image "{PREV_IMG}" \   # 이전샷(-10) 있을 때만
  --image "{NEXT_IMG}" \   # 다음샷(+10) 있을 때만
  --prompt "..." \
  --wait --wait-timeout 10m
```

모델 인자: `kling3_0` (기본) 또는 `seedance_2_0`

**stdout 파싱 규칙:**

| 출력 | 표시 |
|---|---|
| `SHOT_START:0010` | `[진행 중] Shot 0010...` |
| `SHOT_DONE:0010:{url}` | `✅ Shot 0010\n[{SEQ}_0010_v1.mp4]({url})\n{url}` |
| `SHOT_SKIP:0010:{url}` | `⏳ Shot 0010: 이미 완료됨` |
| `SHOT_FAIL:0010:{err}` | `❌ Shot 0010: {err}` |
| `BATCH_DONE:{s}:{f}:{k}` | 최종 요약 출력 |

완료 후 Safari로 미리보기 (우클릭 → 저장 가능):
```bash
open -a "Safari" "{마지막_완료_URL}"
```

## Step 9 — 결과 보고

runner.py 없는 직접 CLI 경로에서는 로컬 저장 없이 URL만 표시.
(runner.py 있을 때는 runner가 저장 담당)

**성공:**
```
# Single
✅ Shot 0010 [single | kling]
{URL}

# Pair
✅ Shot 0010+0011 [pair | kling]
{URL}
```

**실패:**
```
❌ Shot {SHOT}: {error} — 스킵
```

배치 완료 시 요약:
```
--- GenVideo Complete ---
✅ 성공: N
❌ 실패/스킵: N
```

## UX 규칙

- 사용자 언어(한국어/영어)로 응답
- 마크다운 링크 + Raw URL 둘 다 표시
- Job ID, raw JSON 노출 금지
- 비용 예측 금지
- 배치 모드: 확인 없이 순서대로 처리
