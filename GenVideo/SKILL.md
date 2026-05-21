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

**Final prompt = Projectprompt + Sceneprompt + Shotprompt (번역, 있을 때만) + 이미지 시각 분석**

캐시가 있으면 분석을 스킵하고, 없으면 기존 분석 후 캐시에 저장한다.

## Step 0 — 캐시 확인

인자 파싱 전에 먼저 프로젝트 루트를 감지하고 캐시 상태를 확인한다.

```bash
PROJ_ROOT=$(python3 -c "import pathlib,sys; p=pathlib.Path('.').resolve(); [sys.exit(print(str(x))) or 0 for x in [p]+list(p.parents) if (x/'config.md').exists()]; sys.exit(print(str(p)))")
RUNNER="$PROJ_ROOT/runner.py"
CACHE="$PROJ_ROOT/.cache.json"
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
❌ config.md를 찾을 수 없습니다. 먼저 /GenInit을 실행하세요.
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

## Step 4 — Sceneprompt.md 읽기 (Required)

```bash
ls "{EP}/Image/{SEQ}/Sceneprompt.md" 2>/dev/null | head -1
```

없으면 중단:
```
❌ Sceneprompt not found: {EP}/Image/{SEQ}/Sceneprompt.md
```

## Step 5 — Shotprompt.md 읽기 (Optional)

```bash
ls "{EP}/Image/{SEQ}/Shotprompt.md" 2>/dev/null | head -1
```

없으면 스킵.

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
- 한국어 텍스트 → 영어 번역 → `[Shot Direction]` 블록으로 사용
찾지 못하면: Shot Direction 없이 진행, `MULTI_SHOT=false`.

### 7b. Vision 분석

Read 툴로 이미지 분석:
- **Pair**: start 이미지(`{SHOT}-1_v*.png` 또는 `{START}_v*.png`) + end 이미지(`{SHOT}-2_v*.png` 또는 `{END}_v*.png`) 둘 다
- **Single**: `{EP}/Image/{SEQ}/{SHOT}_v{N}.png` (최신 버전)

분석 요소:
- 핵심 시각 요소 (인물, 질감, 구조, 색감)
- 이미지 내용과 Shot Direction에 맞는 동작
- 분위기/조명 뉘앙스

### 7c. 최종 프롬프트 구성

**Shotprompt 있을 때:**
```
{Projectprompt contents (있을 때만)}

{Sceneprompt contents}

[Shot Direction]: {English translation}

{image-specific motion and scene description}
```

**Shotprompt 없을 때:**
```
{Projectprompt contents (있을 때만)}

{Sceneprompt contents}

{image-specific motion and scene description}
```

## Step 7d — 캐시 저장 (분석한 샷만)

`needs_analysis` 샷 각각에 대해 분석이 끝나면 캐시에 저장한다.

각 샷마다 아래 JSON을 구성하고 `write-shot`에 파이프로 전달:

```bash
echo '{
  "shot": "0010",
  "prompt": "완성된 최종 프롬프트 전체",
  "vision_text": "이미지 분석 요약",
  "image_files": ["EP01/Image/S41/S41_0010_v1.png"],
  "image_sigs": [],
  "image_mode": "single",
  "multi_shot": false,
  "workflow": "genvideo"
}' | python3 "$RUNNER" write-shot {SEQ_ID}
```

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
