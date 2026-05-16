---
version: 1.1.0
name: GenVideo
description: |
  Image-to-video generation. Single shot or batch (range/all).
  Reads config.md for project code and episode mapping.
  Reads {EP}/Image/{SEQ}/Sceneprompt.md + Shotprompt.md, analyzes images with vision, generates video.
  Pair images (0010-1.png + 0010-2.png) use start-end i2v; single images use start-image only.
  Default model: Kling 3.0. Pass "seedance" to use Seedance 2.0.
  Use when: "GenVideo", "영상 만들어", "i2v", "GenSingle", "GenBatch", batch or single video generation.
argument-hint: "<SEQUENCE_ID> <0010 | 0010-0030 | all> [seedance]"
allowed-tools: Bash, Read
---

# GenVideo

Image-to-video generation skill. Handles single shot or batch. Default model: Kling 3.0.

**Final prompt = Projectprompt + Sceneprompt + Shotprompt (번역, 있을 때만) + 이미지 시각 분석**

> **중요:** 모든 프롬프트 파일은 스킬 실행 시 **반드시 Read 툴로 새로 읽어야 합니다.**

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
  - `all` → `{EP}/Image/{SEQ}/`에서 전체 샷 탐색
  - `0010-0030` → [0010, 0020, 0030] 확장 (10 단위)
  - `0010,0030,0050` → [0010, 0030, 0050]
  - `0010` → 단일 샷
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

`all` 지정 시 샷 목록 탐색:
```bash
# 단일 이미지 탐색
ls "{EP}/Image/{SEQ}/"[0-9]*_v*.png 2>/dev/null \
  | xargs -I{} basename {} | grep -oE '^[0-9]{4}' | sort -un
# 페어 이미지 탐색
ls "{EP}/Image/{SEQ}/"[0-9]*-1.png 2>/dev/null \
  | xargs -I{} basename {} | grep -oE '^[0-9]{4}' | sort -un
```

병합 후 `sort -un`.

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
0030-1. 페어 샷 방향
```

`[multi]` 태그가 있으면 해당 샷 multi_shots 모드 활성화 (싱글 이미지 전용).

## Step 6 — 이미지 파일 탐색 (샷별)

각 샷 번호 `{SHOT}` (예: `0010`)에 대해 우선순위 순으로 탐색:

1. `{EP}/Image/{SEQ}/{SHOT}-1.png` + `{SHOT}-2.png` → **Pair mode**
2. `{EP}/Image/{SEQ}/{SHOT}_v*.png` → **Single mode** (최신 버전)
3. Else → `⚠️ Shot {SHOT}: 이미지 없음 — 스킵`

```bash
# Pair 체크
ls "{EP}/Image/{SEQ}/{SHOT}-1.png" "{EP}/Image/{SEQ}/{SHOT}-2.png" 2>/dev/null | wc -l
# Single (최신 버전)
ls "{EP}/Image/{SEQ}/{SHOT}_v"*.png 2>/dev/null | sort -V | tail -1
```

## Step 7 — Shotprompt 조회 + Vision 분석 + 프롬프트 구성

### 7a. Shotprompt 조회

- **Pair mode**: `{SHOT}-1.` 로 시작하는 줄 찾기
- **Single mode**: `{SHOT}.` 로 시작하는 줄 찾기

찾으면:
- `[multi]` 태그 → `MULTI_SHOT=true` (Single 전용, Pair는 무시)
- 한국어 텍스트 → 영어 번역 → `[Shot Direction]` 블록으로 사용
찾지 못하면: Shot Direction 없이 진행, `MULTI_SHOT=false`.

### 7b. Vision 분석

Read 툴로 이미지 분석:
- **Pair**: `{EP}/Image/{SEQ}/{SHOT}-1.png`, `{SHOT}-2.png` 둘 다
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

## Step 8 — 영상 생성

모든 경로는 절대경로. `pwd`로 현재 디렉토리 확인.

### Kling 3.0 — Pair:
```bash
higgsfield generate create kling3_0 \
  --start-image "/abs/path/{EP}/Image/{SEQ}/{SHOT}-1.png" \
  --end-image "/abs/path/{EP}/Image/{SEQ}/{SHOT}-2.png" \
  --prompt "..." \
  --mode pro \
  --aspect_ratio 16:9 \
  --duration 5 \
  --wait --wait-timeout 20m
```

### Kling 3.0 — Single:
```bash
higgsfield generate create kling3_0 \
  --start-image "/abs/path/{EP}/Image/{SEQ}/{SHOT}_v{N}.png" \
  --prompt "..." \
  --mode pro \
  --aspect_ratio 16:9 \
  --duration 5 \
  --wait --wait-timeout 20m
```

### Kling 3.0 — Single + Multi-shot (`MULTI_SHOT=true`):
```bash
higgsfield generate create kling3_0 \
  --start-image "/abs/path/{EP}/Image/{SEQ}/{SHOT}_v{N}.png" \
  --prompt "..." \
  --mode pro \
  --aspect_ratio 16:9 \
  --duration 5 \
  --multi_shots true \
  --multi_shot_mode auto \
  --wait --wait-timeout 20m
```

### Seedance 2.0 — Pair:
```bash
higgsfield generate create seedance_2_0 \
  --start-image "/abs/path/{EP}/Image/{SEQ}/{SHOT}-1.png" \
  --end-image "/abs/path/{EP}/Image/{SEQ}/{SHOT}-2.png" \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --duration 5 \
  --wait --wait-timeout 20m
```

### Seedance 2.0 — Single:
```bash
higgsfield generate create seedance_2_0 \
  --start-image "/abs/path/{EP}/Image/{SEQ}/{SHOT}_v{N}.png" \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --duration 5 \
  --wait --wait-timeout 20m
```

Note: Seedance 2.0은 `--mode` 없음.

생성 완료 후 즉시:
```bash
open "{URL}"
```
macOS 기본 브라우저에서 영상 미리보기. 우클릭 → 다른 이름으로 저장.

## Step 9 — 결과 보고

출력 파일명: `{SHOT}_v{N}.mp4`
- 소스 이미지가 `0010_v2.png`면 → `0010_v2.mp4`
- 소스가 페어 또는 최초 single이면 → `0010_v1.mp4`

**성공:**
```
✅ Shot {SHOT} [pair/single/single+multi | kling/seedance]
[{SHOT}_v{N}.mp4]({URL})
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
