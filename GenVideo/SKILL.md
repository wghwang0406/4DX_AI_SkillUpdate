---
version: 1.2.0
name: GenVideo
description: |
  Image-to-video generation. Single shot or batch (range/all).
  Reads config.md for project code and episode mapping.
  Reads {EP}/Image/{SEQ}/Sceneprompt.md + Shotprompt.md, analyzes images with vision, generates video.
  Pair mode: pass "10+11" or "0010+0011" as shot spec — start-end i2v using _v*.png files.
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
GRB_ROOT=$(python3 -c "import pathlib,sys; p=pathlib.Path('.').resolve(); [sys.exit(print(str(x))) or 0 for x in [p]+list(p.parents) if (x/'config.md').exists()]; sys.exit(print(str(p)))")
RUNNER="$GRB_ROOT/grb_runner.py"
CACHE="$GRB_ROOT/.grb_cache.json"
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
  - `0010+0011` 또는 `10+11` → **Pair 모드**: `0010_v*.png`(스타트) + `0011_v*.png`(엔드)
  - `10+11,12,13+17` → 혼합 목록 (페어 + 단독 혼용 가능)
  - 짧은 번호 자동 패딩: `10+11` → `0010+0011`, `7` → `0007`
  - 번호가 연속일 필요 없음: `14+17`, `10+50` 모두 가능
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

`all` 지정 시 샷 목록 탐색 (`_v*.png` 단독 파일만, 싱글 모드):
```bash
ls "{EP}/Image/{SEQ}/"[0-9]*_v*.png 2>/dev/null \
  | xargs -I{} basename {} | grep -oE '^[0-9]{4}' | sort -un
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
0030. 페어 샷도 start 번호로 작성 (0030+0031 호출 시 0030. 으로 찾음)
```

`[multi]` 태그가 있으면 해당 샷 multi_shots 모드 활성화 (싱글 이미지 전용).
페어 모드에서 Shotprompt는 **start 번호**(`{SHOT}.`)로 조회한다.

## Step 6 — 이미지 파일 탐색 (샷별)

SHOT_SPEC에 `+`가 포함된 경우 → **Pair mode**: START와 END 번호 분리 후 각각 `_v*.png` 탐색.
그 외 → **Single mode**: `{SHOT}_v*.png` 탐색.

```bash
# Pair mode (SHOT_SPEC = "0010+0011" → START=0010, END=0011)
START_IMG=$(ls "{EP}/Image/{SEQ}/{START}_v"*.png 2>/dev/null | sort -V | tail -1)
END_IMG=$(ls "{EP}/Image/{SEQ}/{END}_v"*.png 2>/dev/null | sort -V | tail -1)
# 둘 다 있어야 함. 하나라도 없으면 ⚠️ 스킵

# Single mode
ls "{EP}/Image/{SEQ}/{SHOT}_v"*.png 2>/dev/null | sort -V | tail -1
# 없으면 ⚠️ 이미지 없음 — 스킵
```

## Step 7 — Shotprompt 조회 + Vision 분석 + 프롬프트 구성

### 7a. Shotprompt 조회

모드에 관계없이 **`{START}.`** (start 번호 + 점)로 시작하는 줄 찾기.
- Pair mode(`0010+0011`) → `0010.` 로 시작하는 줄 찾기
- Single mode(`0010`) → `0010.` 로 시작하는 줄 찾기

찾으면:
- `[multi]` 태그 → `MULTI_SHOT=true` (Single 전용, Pair는 무시)
- 한국어 텍스트 → 영어 번역 → `[Shot Direction]` 블록으로 사용
찾지 못하면: Shot Direction 없이 진행, `MULTI_SHOT=false`.

### 7b. Vision 분석

Read 툴로 이미지 분석:
- **Pair**: start 이미지(`{START}_v*.png`) + end 이미지(`{END}_v*.png`) 둘 다
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
  "image_files": ["EP01/Image/S41/0010_v1.png"],
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

## Step 8 — 영상 생성 (Python 러너 위임)

캐시에 프롬프트가 저장된 후 Python 러너에게 API 호출을 위임한다.

```bash
cd "$GRB_ROOT" && python3 "$RUNNER" \
  genvideo {SEQ_ID} {SHOT_SPEC} --model {model}
```

모델 인자: `--model kling3_0` (기본) 또는 `--model seedance_2_0`

**stdout 파싱 규칙:**

| 출력 | 표시 |
|---|---|
| `SHOT_START:0010` | `[진행 중] Shot 0010...` |
| `SHOT_DONE:0010:{url}` | `✅ Shot 0010\n[0010_v1.mp4]({url})\n{url}` |
| `SHOT_SKIP:0010:{url}` | `⏳ Shot 0010: 이미 완료됨` |
| `SHOT_FAIL:0010:{err}` | `❌ Shot 0010: {err}` |
| `BATCH_DONE:{s}:{f}:{k}` | 최종 요약 출력 |

완료 후 `open "{url}"` 호출로 브라우저 미리보기:
```bash
open "{마지막_완료_URL}"
```

## Step 9 — 결과 보고

출력 파일명: `{SHOT}_v{N}.mp4`
- 소스 이미지가 `0010_v2.png`면 → `0010_v2.mp4`
- 소스가 페어 또는 최초 single이면 → `0010_v1.mp4`

**성공:**
```
# Single
✅ Shot 0010 [single | kling]
[0010_v1.mp4]({URL})
{URL}

# Pair
✅ Shot 0010+0011 [pair | kling]
[0010_v1.mp4]({URL})
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
