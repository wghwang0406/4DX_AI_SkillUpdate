---
version: 1.4.0
name: GenVideo
description: |
  Image-to-video generation. Single shot or batch (range/all).
  Reads config.md for project code and episode mapping.
  Reads {EP}/Image/{SEQ}/Sceneprompt.md + Shotprompt.md, analyzes images with vision, generates video.
  Keyframes (ordered): {SHOT}-1, -2, -3 … as many as you want. References (unordered): {SHOT}_ref/ folder.
  Single images use start-image only. Default model: Kling 3.0. Pass "seedance" to use Seedance 2.0.
  Multi-shot/cuts are given in Korean at call time ("컷으로" / "한 테이크로"), not as a tag.
  Prompts follow the CINEDANCE 12-section architecture (see the Cinedance skill).
  Use when: "GenVideo", "영상 만들어", "i2v", "GenSingle", "GenBatch", batch or single video generation.
argument-hint: "<SEQUENCE_ID> <0010 | 0010-0030 | all> [seedance] [컷으로|한 테이크로]"
allowed-tools: Bash, Read, Skill
---

# GenVideo

Image-to-video generation skill. Handles single shot or batch. Default model: Kling 3.0.

## 원문 규격 참조 (필수)

프롬프트 슬롯을 채우기 전에 반드시 Read한다. 요약본으로 대체하지 않는다.

| 무엇을 쓸 때 | 읽을 파일 |
|---|---|
| 12섹션 전체, 옵틱·블로킹·물리·조명 락 | `~/.claude/skills/Cinedance/SKILL.md` **(별도 설치)** |
| ACTION TIMING 안의 연기, Voice | `~/.claude/skills/Acting/SKILL.md` **(별도 설치)** |

> 두 파일은 저장소에 포함돼 있지 않다 (힉스필드 배포본). 없으면 이 스킬은 그대로 돌지만
> `~/.claude/CLAUDE.md`의 **프롬프트 규칙 10개**만 근거로 슬롯을 채우게 된다.

`~/.claude/CLAUDE.md`의 **프롬프트 규칙 10개**는 항상 적용된다.

**프롬프트 합성은 runner가 코드로 담당한다.** 모델은 영문 슬롯만 채워 캐시에 저장하고,
runner가 **CINEDANCE 12섹션 순서**로 조립해 `--prompt`에 넣는다.
섹션 라벨을 직접 이어붙이지 않는다 — 슬롯 값만 채운다.

**빈 MD 자동 보완:** Sceneprompt/Shotprompt가 비어있으면 샷 이미지를 Vision 분석해 자동으로 채운다(한국어). Projectprompt는 제외(GenSetup 소관). 슬롯이 채워지려면 이 MD가 있어야 하므로 슬롯 작성(Step 7) 전에 수행한다.

캐시가 있으면 분석을 스킵하고, 없으면 기존 분석 후 캐시에 저장한다.

## Step 0 — 캐시 확인

인자 파싱 전에 먼저 프로젝트 루트를 감지하고 캐시 상태를 확인한다.

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
  - 짧은 번호 자동 패딩: `7` → `0007`
- 모델 (선택):
  - 없으면 → Kling 3.0 (`kling3_0`)
  - `seedance` → Seedance 2.0 (`seedance_2_0`)
  - `seedance25` → Seedance 2.5 (`seedance_2_5`) — 레퍼런스 30장까지, 단 **720p 상한**
  - **모델을 명시하면 러너가 자동 전환하지 않는다** (아래 모델 전환 규칙 참조)
- 컷 지시 (선택, 한국어): `컷으로` / `멀티샷으로` / `컷 나눠서` / `한 테이크로` / `한 컷으로`
  - 있으면 `format_mode` 슬롯에 그대로 반영한다
  - 없으면 키프레임을 vision으로 비교해 자동 판정한다 (Step 7b)
  - **컷 지시는 절대로 모델을 바꾸지 않는다.** 멀티샷은 파라미터가 아니라 프롬프트로 만든다

## 샷 이미지 규칙 — 두 가지 케이스

| | 케이스 1 — 순서대로 영상 | 케이스 2 — 레퍼런스만 |
|---|---|---|
| **어디에** | `{SEQ}_{SHOT}-N_v*.png` | `{SEQ}_{SHOT}_ref/` 폴더 안 |
| **순서** | **있다.** N이 시간 순서 | **없다.** 그냥 재료 |
| **개수** | 무제한 (모델 상한까지) | 무제한 (모델 상한까지) |
| **시작 프레임** | `-1` | `{SEQ}_{SHOT}_v*.png` |

```
EP01/Image/S41/
  S41_0010_v1.png            ← 단일 시작 프레임
  S41_0020-1_v1.png          ← 순서 키프레임 3장
  S41_0020-2_v1.png
  S41_0020-3_v1.png
  S41_0030_v1.png
  S41_0030_ref/              ← 0030만 레퍼런스가 필요해서 만든 폴더
    매대잡는손.png
    기관집질감.jpg
```

- **`_ref/` 폴더는 무조건 레퍼런스다.** 어떤 경우에도 키프레임이 되지 않는다.
- **둘은 같이 쓸 수 있다** — 키프레임으로 흐름을 잡고 `_ref/`로 재료를 더 준다.
- **`_ref/` 폴더를 미리 만들지 않는다.** 필요한 샷에만 사용자가 직접 만든다. 없으면 그냥 지나간다.
- 폴더 안 `.png/.jpg/.jpeg/.webp`만 읽는다. 메모 파일이 섞여 있어도 무시된다.

**러너가 알아서 찾는다.** 스킬은 샷 번호만 넘기면 되고 파일 경로를 캐시에 적을 필요가 없다.

## 모델 제약과 자동 전환

`higgsfield model get`으로 확인한 값이다.

| | Kling 3.0 | Seedance 2.0 | Seedance 2.5 |
|---|---|---|---|
| 시작/끝 프레임 | `start_image` / `end_image` | `start_image` / `end_image` | `start_image` / `end_image` |
| 레퍼런스 이미지 | **없음** (파라미터 자체가 없다) | `image_references` | `image_references` |
| 이미지 총 상한 | 2장 (start/end) | **9장** (start·end 포함) | **30장** |
| 최대 해상도 | 4k (`--mode 4k`) | **4k** | **720p** |
| 21:9 | **없음** | 있음 | 있음 |
| 컷/멀티샷 파라미터 | 없음 — 프롬프트로 | 없음 — 프롬프트로 | 없음 — 프롬프트로 |

> **2.5는 720p가 끝이다.** 고해상도가 필요하면 2.0을 쓰거나, 2.5로 뽑고
> `bytedance_video_upscale`(최대 4k, `--preset aigc`) / `topaz_video`(최대 2160p)로 올린다.
>
> **2.5는 `start_image`/`end_image`를 쓰려면 `--mode omni_reference`가 필요하다.**
> 기본 `t2v` 모드는 레퍼런스를 아예 받지 않는다.

러너의 처리 (`plan_shot_media`):
- 키프레임 3장 이상 + Kling **기본값** → **Seedance로 자동 전환** + 알림
- 키프레임 3장 이상 + `seedance`/`kling` **명시** → 전환하지 않고 `첫/끝 2장만 사용` 경고
- Kling인데 `_ref/`가 있으면 → 레퍼런스 제외 + 경고 (Kling이 못 받음)
- 이미지 총합이 9장을 넘으면 → 레퍼런스부터 잘라내고 경고 (키프레임은 지키지 않고 자르지 않음)

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

## Step 3 — Projectprompt.md 읽기 → 스타일 앵커 (Optional)

```bash
ls "Projectprompt.md" 2>/dev/null | head -1
```

있으면 Read해서 **스타일 앵커 한 덩어리**를 영문으로 뽑아 `style_en`에 넣는다.
필름 스톡 / 그레이딩 / 텍스처 / 필요하면 촬영감독 무드 앵커 한둘 정도로 짧게.
```
Kodak Vision3 500T, naturalistic low-key backlit silhouette, real grain, grounded physical cinema texture.
```
- 스타일은 **프로젝트 상수**다. 샷 슬롯에 복붙하지 않는다 — 한 곳만 고쳐 전 샷에 반영되어야 한다.
- 스타일이 카메라·조명 락과 충돌하면 안 된다. 긴 촬영감독 이름 나열은 노이즈다.
- Projectprompt가 바뀌지 않았으면 이후 샷의 write-shot에서 `style_en`을 생략해도 된다.

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
   `{EP}/character/loc/{장소}_Location_top_v*.png`(탑다운 평면도)가 있으면 **같이 읽는다** —
   공간 배치를 읽는 근거가 된다. 이 뷰는 레퍼런스로 물리지 않고 여기서만 쓴다.
2. 씬 분위기·장소·조명·카메라 스타일을 **한국어로** Sceneprompt.md에 작성 (Write).
   **LOCATION MAP 절을 반드시 포함한다** — 인물도 동작도 없이 장소만:
   카메라 위치·바라보는 방향 / 전경·중경·배경 / 주요 랜드마크 위치 / 동선 / 조명 방향 /
   카메라가 넘지 않는 선. 모델은 앞 컷을 기억하지 못하므로 이게 없으면 컷마다 인물이 순간이동한다.
3. 작성한 내용을 사용자에게 **출력해 보여준 뒤** 이어서 진행 (승인 대기 없음).
4. LOCATION MAP을 영역해 `location_map_en`에 넣는다 (시퀀스 레벨 저장 — 샷마다 다시 쓰지 않는다).
5. MD를 새로 썼으므로 → **캐시 정합성 처리**(아래 노트) 적용.

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
2. **i2v용이므로 정지 묘사보다 움직임/카메라워크를 추론**해 샷별 한국어 방향을 작성 (Write).
   형식은 **모델에 따라 갈린다:**
   ```
   # Seedance 2.0 — 타임코드 블록
   0010. [84°] 0:00–0:03 {카메라 거동} / {동작}. 0:03–0:06 {다음 동작}.

   # Kling 3.0 — 타임코드 없음 (Custom Multi-Shot)
   0010. [84°] {카메라 거동} — {동작 순서}.
   ```
   - **대각 화각** `[47°]`~`[8°]`을 각 줄에 붙인다 (mm·f값 아님).
   - 동작은 감정어가 아니라 **관찰 가능한 몸의 일**로, **전환이 아니라 상태**로 쓴다.
   - 한 구간에 상충하는 동작을 몰아넣지 않는다.
3. 작성한 내용을 **출력해 보여준 뒤** 이어서 진행. MD를 새로 썼으면 위 캐시 정합성 노트 적용.

Shotprompt.md 형식 — **태그를 쓰지 않는다:**
```
0010. [84°] 카메라 고정 — 파이프를 치켜든다.
0020. [29°] 0:00–0:02 얼굴에 붙었다가 0:02–0:05 손으로 내려간다.
```

> **`[multi]` 태그는 폐지됐다.** 예전에 쓰던 `--multi_shots` 파라미터는 **Kling 3.0에 존재하지 않아**
> 넘기면 `Unknown params`로 실패한다. 멀티샷은 파라미터가 아니라 **프롬프트의 FORMAT MODE**로 만든다.
>
> 기존 파일에 `[multi]`가 남아 있으면 **"컷으로"와 같은 뜻으로 읽고** 에러 없이 진행한다.
> 새로 쓸 때는 넣지 않는다.

## Step 6 — 샷 미디어 탐색

**러너가 `find_shot_media()`로 직접 찾으므로 스킬이 경로를 계산할 필요가 없다.**
확인만 하려면:

```bash
# 순서 키프레임 (-N, 시간 순서)
ls "{EP}/Image/{SEQ}/{SEQ}_{SHOT}-"*_v*.png 2>/dev/null | sort -V
# 키프레임이 없으면 단일 시작 프레임
ls "{EP}/Image/{SEQ}/{SEQ}_{SHOT}_v"*.png 2>/dev/null | sort -V | tail -1
# 레퍼런스 폴더 (있을 때만)
ls "{EP}/Image/{SEQ}/{SEQ}_{SHOT}_ref/" 2>/dev/null
```

탐색 규칙:
- `-N`은 **N 오름차순**으로 정렬한다. `-2` 다음이 `-10`이다 (문자열 정렬이 아니라 숫자 정렬).
- 같은 N에 버전이 여러 개면 `_v` 최대본을 쓴다.
- 키프레임이 하나도 없으면 `{SEQ}_{SHOT}_v*.png` 한 장을 시작 프레임으로 쓴다.
- 둘 다 없으면 그 샷은 스킵한다.

이미지가 하나도 없으면: `SHOT_FAIL:{SHOT}:이미지를 찾을 수 없음`

## Step 7 — Shotprompt 조회 + Vision 분석 + 프롬프트 구성

### 7a. Shotprompt 조회

**`{SHOT}.`** (샷 번호 + 점)로 시작하는 줄을 찾는다.

찾으면 한국어 텍스트를 영어로 번역해 `action_timing` / `camera` / `optics` 슬롯에 나눠 넣는다.
찾지 못하면 이미지 기반으로 채운다.

`[multi]` 태그가 남아 있으면 **"컷으로"와 같은 뜻**으로 읽는다 (아래 7b의 컷 판정에서 우선).

### 7b. Vision 분석 + 컷/테이크 판정

Read 툴로 **키프레임 전부**를 읽는다. 레퍼런스(`_ref/`)는 프롬프트를 쓰는 재료로만 참고하고
구도·모션 판정에는 쓰지 않는다 (순서가 없기 때문).

분석 요소:
- 핵심 시각 요소 (인물, 질감, 구조, 색감)
- 이미지 내용과 Shot Direction에 맞는 동작
- 분위기/조명 뉘앙스

**키프레임이 2장 이상이면 연속한 키프레임끼리 비교한다** — 이게 `format_mode`의 근거다.

| 비교 결과 | 판정 | 이유 |
|---|---|---|
| 카메라 위치·화각·조명 방향이 **같다** | `SINGLE CONTINUOUS TAKE` | 피사체가 움직인 것이므로 모델이 실제로 애니메이션할 수 있다 |
| 하나라도 **다르다** | `CONTROLLED MULTI-SHOT SEQUENCE` | 한 테이크로 이을 물리적 방법이 없다 |

**여기가 슬라이드쇼가 생기는 지점이다.** 구도가 다른 두 이미지를 한 테이크로 지시하면
모델이 이을 방법이 없어 크로스디졸브로 때운다. 그래서 컷이면 컷이라고 선언해야 한다.

**사용자가 한국어로 지시했으면 그게 우선한다** — vision 판정을 덮어쓴다.
`컷으로`/`멀티샷으로` → 멀티샷 / `한 테이크로`/`한 컷으로` → 싱글 테이크.

판정 결과를 한 줄로 보여준 뒤 진행한다:
```
🎬 Shot 0020 — 키프레임 3장, 카메라가 각각 달라 컷으로 처리합니다 (HARD CUT ×2)
```

### 7c. 프롬프트 슬롯 작성 (모델은 슬롯만, 조립은 runner)

최종 프롬프트를 직접 이어붙이지 말 것. 아래 슬롯을 **영문**으로 채우면
runner가 CINEDANCE 12섹션 순서로 조립한다. 값이 빈 섹션은 자동 생략된다.

**저장 레벨이 다르다 — 상수는 샷에 복붙하지 않는다.**

| 슬롯 | 저장 레벨 | 내용 |
|---|---|---|
| `style_en` | **프로젝트** | 스타일 앵커. 한 곳 고치면 전 샷 반영. 예: `Kodak Vision3 500T, naturalistic low-key backlit silhouette, real grain, grounded physical cinema texture.` |
| `location_map_en` | **시퀀스** | Sceneprompt의 LOCATION MAP 번역. **장면당 한 번**, 모든 컷이 공유 |
| 나머지 | 샷 | 아래 표 |

**샷 슬롯 (CINEDANCE 섹션 순서)**

| 슬롯 | 섹션 | 내용 |
|---|---|---|
| `scene_context` | SCENE CONTEXT | 이 샷에서 일어나는 일 1–2문장. 씬 번호·이전 씬 요약·이 샷에 없는 인물 금지 |
| `active_refs` | ACTIVE REFERENCES | 이 샷에 **실제로 보이는** @태그만. 앵커 공식: `@TAG: age + role/body type + current state + 시각 앵커 + 행동에 필요한 소품/신체 상태. 100% matches the reference.` 지난 샷의 stale 태그 금지 |
| `first_frame` | FIRST FRAME AND SPATIAL BLOCKING | **첫 프레임에 필요한 인물이 이미 다 들어가 있다고 명시.** 빈 establishing 금지. 그리고 스크린 위치 / 월드 위치 / 랜드마크와의 거리 / 몸 방향 / **시선 방향(따로)** / 이동 방향. `within 1 meter`처럼 측정 가능하게 — `near`·`beside`·`around` 금지 |
| `format_mode` | FORMAT MODE | **7b 판정 결과를 여기 쓴다.** 아래 상세 참조 |
| `optics` | OPTICS | **대각 화각**으로 쓴다. `47°/84°/107°/29°/18°/8°` 중 콘텐츠 타입에 맞는 것을 렌즈 결정 트리로 고르고, 해당 **언어 뱅크를 그대로 인용**한다. mm·f값·ISO·렌즈 브랜드 금지. 망원이면 visual outcome 4개 이상, 광각이면 3개 이상 |
| `camera` | CAMERA | 물리적 오퍼레이터 행동으로. 높이·거리·각도·어느 쪽·피사체 크기·화면 배치·움직임·포커스·핸드헬드 질감 |
| `action_timing` | ACTION TIMING | **Seedance**: `0:00 to 0:03` 타임코드 블록. **Kling**: 타임코드 없이 샷 단위 서술. 한 블록에 상충하는 동작을 몰아넣지 않는다 |
| `acting_en` | (ACTION TIMING에 병합) | Acting 스킬 규격. Character.md 마스터 프로필을 **이 씬에 맞게 다시 쓴다**(붙여넣기 금지). 목적·장애·전술·비트 변화 2~4개·서브텍스트, eye life 필수. 감정어 대신 근육의 일. **상태를 쓰고 전환을 쓰지 않는다** |
| `physics` | PHYSICS | 중력·질량·관성·마찰·접촉·무게 이동·천/머리 지연·액체 점성·입자. 떠다니는 몸, 무게 없는 무기, 마찰 없는 발 금지 |
| `lighting` | LIGHTING | 주광원·방향·카메라가 광원의 어느 쪽·그림자/림·배경 밝기·**노출 우선순위**. 조명은 장식이 아니라 우선순위 락이다 |
| `audio` | AUDIO | 환경음. 대사는 여기에만 — 동작 슬롯엔 한 글자도 넣지 않는다. 자막·음악은 요청 없으면 없음 |
| `voice_en` | (AUDIO에 병합) | 대사가 있으면 Character.md의 Voice 프롬프트를 **verbatim** 으로. 말이 없으면 생략 |
| `positive_constraints` | POSITIVE CONSTRAINTS | 원하는 상태를 긍정문으로. 인원수·소품 개수를 못박는다(`exactly three people`) |

### `format_mode` 상세 — 슬라이드쇼를 막는 자리

**한 테이크** (키프레임들이 같은 카메라·조명):
```
SINGLE CONTINUOUS TAKE. Real-time motion. No subtitles, no music.
```
그리고 `camera` 슬롯에 **카메라가 어떻게 움직이는지** 반드시 쓴다.
구도가 조금 달라졌는데 한 테이크로 갈 거라면 그건 컷이 아니라 카메라가 움직인 것이므로
`slow push in` / `pan left` / `handheld track` 처럼 명시한다. 이게 없으면 모델이 보간만 한다.

**컷** (카메라·조명이 다름) — CINEDANCE 원문 표현을 그대로 쓴다:
```
CONTROLLED MULTI-SHOT SEQUENCE with HARD CUT at 2.0 seconds.
Shot A — 84° wide, @HERO1 within 1 meter of the car, hand on the hood.
HARD CUT.
Shot B — 29° short telephoto, same eyeline, same key light from camera-right.
NO fade-to-black. NO crossfade. NO dissolve. HARD CUTS only.
```
- 컷 타입은 `HARD` / `SMASH` / `MATCH` / `INSERT` / `REVERSE` / `WHIP`만 쓴다.
- 컷마다 지속시간·카메라·첫 프레임 피사체·블로킹·액션을 적는다.
- 컷을 넘어가도 **같은 인물·지오메트리·스크린 방향·조명 방향**을 유지한다고 명시한다.

**두 경우 모두** `action_timing`에 **키프레임 사이 구간별 물리 동작**을 쓴다.
이게 비면 모델에 모션 신호가 0이라 크로스디졸브로 때운다 — 슬라이드쇼의 직접적 원인이다.
```
0:00 to 0:02 he raises the pipe, the weight pulling his wrist down before the arm locks.
0:02 to 0:05 the shoulders drop and the grip tightens.
```
(Kling은 타임코드를 쓰지 않으므로 `First … then …` 처럼 순서로 쓴다)

- 한국어 소스는 모두 **영어로 번역**해 넣는다.
- **긴 게 좋은 게 아니다.** 제어가 필요한 곳만 촘촘하게: 정체성 앵커·블로킹·첫 프레임·시선·랜드마크 근접·손 상태·타이밍·옵틱·조명·물리·대사.
  배경 엑스트라, 레퍼런스에 이미 명백한 것, 장식적 형용사는 늘리지 않는다.
- 거대 NEGATIVE 블록은 만들지 않는다. 필요하면 해당 긍정 규칙 **바로 옆에 국소 락**을 붙인다
  (`Faces remain in deep shadow; no flat front light.`).
- 출력 전 `Cinedance` 원문의 *Silent self-QA* 항목을 스스로 점검한다.

**레거시:** 기존 캐시의 `scene_en`/`shot_dir_en`/`vision_en` 3슬롯과 단일 `prompt`도
runner가 그대로 폴백 처리한다. 새로 쓸 때만 위 슬롯을 쓴다.

## Step 7d — 캐시 저장 (분석한 샷만)

`needs_analysis` 샷 각각에 대해 분석이 끝나면 캐시에 저장한다.

각 샷마다 아래 JSON을 구성하고 `write-shot`에 파이프로 전달:

```bash
echo '{
  "shot": "0010",

  "style_en": "Kodak Vision3 500T, naturalistic low-key backlit silhouette, real grain.",
  "location_map_en": "Camera on the south kerb facing north at the burned-out car. Foreground: wet asphalt. Midground: the car, its hood facing camera-left. Background: collapsed overpass. Key light from camera-right behind the subjects. Camera does not cross to the north side.",

  "scene_context": "A wounded young man stands beside a burned-out car in heavy rain while two companions face him from the foreground.",
  "active_refs": "@HERO1: 20yo broad-shouldered wounded male, tangled blond hair over his eyes, blood-streaked grey hoodie, right shoulder roughly bandaged, left hand gripping a dented steel pipe. 100% matches the reference.",
  "first_frame": "The first visible frame already contains all required characters in their correct positions. No empty establishing frame. @HERO1 stands within 1 meter of the car, right hand on the scorched hood, torso facing the pair, eyes locked on @HERO2. @HERO2 and @HERO3 stand together in the foreground, camera-right and camera-left of the pair, both bodies and gaze lines on @HERO1.",
  "format_mode": "SINGLE CONTINUOUS TAKE. Real-time motion. No subtitles, no music.",
  "optics": "84 degree diagonal field of view, classic wide-angle lens character, camera 1 to 1.5 meters from subject. Wide-angle lens with strong but natural perspective expansion, foreground body presence feels larger and closer, environment remains visible to the frame edges, deep readable spatial context, straight architectural lines stay rectilinear, no fisheye curve.",
  "camera": "Camera fixed at hip height on the shadow side of @HERO1, subject occupying screen-left third, negative space camera-right. Handheld with operator breath and micro-settling, no digital jitter.",
  "action_timing": "0:00 to 0:03 @HERO1 raises the pipe one-handed, the weight pulling his wrist down before the arm locks.",
  "acting_en": "@HERO1 wants them to leave without him and cannot say it. Jaw clenches then releases; a shallow exhale through the nose; the gaze drops to the pipe a beat before the head follows, blinks rare and slow. When @HERO2 steps in, the shoulders drop half an inch and the grip tightens instead.",
  "physics": "Rain runs off the hoodie in sheets and beads at the cuff. The pipe carries visible mass, wrist angle reacting to it. Feet find friction on wet asphalt with weight transfer through the whole foot.",
  "lighting": "The camera stays on the shadow side of @HERO1. Sodium street light from camera-right, behind and to the side, creating a hard rim along his shoulders while his camera-facing front stays dark. Exposed for the backlight, not for the face. No flat front light, no beauty fill.",
  "audio": "Rain on sheet metal, distant structural groan. No music.",
  "voice_en": "\"A 20-year-old, working-class city accent. Low and hoarse; short flat sentences; going quieter, never louder, as things get serious.\"",
  "positive_constraints": "Exactly three people in frame. Exactly one steel pipe.",

  "vision_text": "이미지 분석 요약 (참고 저장용)",
  "image_files": ["EP01/Image/S41/S41_0010_v1.png"],
  "image_sigs": [],
  "workflow": "genvideo"
}' | python3 "$RUNNER" write-shot {SEQ_ID}
```

- `style_en`은 **프로젝트**, `location_map_en`은 **시퀀스**에 저장된다 — runner가 알아서 빼서 올린다.
  같은 시퀀스의 다음 샷부터는 이 두 키를 **생략해도 된다.** Projectprompt/Sceneprompt가 바뀌었을 때만 다시 넣는다.
- 값이 빈 섹션은 최종 프롬프트에서 자동으로 빠진다.
- `acting_en`은 ACTION TIMING 뒤에, `voice_en`은 AUDIO 뒤에 붙는다.
- 레거시 단일 `prompt`와 3슬롯(`scene_en`/`shot_dir_en`/`vision_en`)도 여전히 폴백으로 동작한다.
- **이미지 경로를 캐시에 적을 필요가 없다.** 러너가 `find_shot_media()`로 디스크에서 직접 찾는다.
  `image_files`는 vision 분석 기록·시그니처용으로만 남긴다 (디스크에서 못 찾을 때의 폴백이기도 하다).
- `image_sigs`는 비워두면 Python이 자동으로 파일에서 읽는다.
- `image_mode` / `multi_shot`은 **더 이상 쓰이지 않는다.** 있어도 무시되니 새로 쓸 때는 넣지 않는다.

출력: `CACHE_WRITE:0010:ok`

## Step 8 — 영상 생성

runner.py가 있으면 러너에 위임, 없으면 higgsfield CLI 직접 실행.

**runner.py 있을 때** (권장 — 미디어 탐색·모델 전환·상한 처리를 전부 러너가 한다):
```bash
cd "$PROJ_ROOT" && python3 "$RUNNER" genvideo {SEQ_ID} {SHOT_SPEC}
# 모델을 명시할 때만 (명시하면 자동 전환이 꺼진다)
cd "$PROJ_ROOT" && python3 "$RUNNER" genvideo {SEQ_ID} {SHOT_SPEC} --model seedance
```

**runner.py 없을 때 (직접 CLI):**

```bash
# 키프레임 1장
higgsfield generate create kling3_0 --mode pro \
  --start-image "{K1}" \
  --prompt "..." \
  --aspect_ratio 16:9 --duration 5 --wait --wait-timeout 20m

# 키프레임 2장 (시작 / 끝)
higgsfield generate create kling3_0 --mode pro \
  --start-image "{K1}" --end-image "{K2}" \
  --prompt "..." \
  --aspect_ratio 16:9 --duration 5 --wait --wait-timeout 20m

# 키프레임 3장 이상 → Seedance (Kling은 중간 키프레임을 못 받음)
higgsfield generate create seedance_2_0 \
  --start-image "{K1}" --image "{K2}" --end-image "{K3}" \
  --prompt "..." \
  --aspect_ratio 16:9 --duration 5 --wait --wait-timeout 20m

# 레퍼런스 폴더까지 (Seedance 전용, 총 9장 이내)
higgsfield generate create seedance_2_0 \
  --start-image "{K1}" --end-image "{K2}" \
  --image "{REF1}" --image "{REF2}" \
  --prompt "..." \
  --aspect_ratio 16:9 --duration 5 --wait --wait-timeout 20m
```

- 모델 인자: `kling3_0` (기본, `--mode pro`) 또는 `seedance_2_0`
- **`--image`는 `--image-references`의 짧은 별칭이다** (CLI 1.1.x). 둘 다 동작한다.
- Kling에는 `image_references` 파라미터가 없어 `--image`를 줘도 반영되지 않는다.

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
✅ Shot 0010 [키프레임 1 | kling]
{URL}

✅ Shot 0020 [키프레임 3 + 레퍼런스 2 | seedance · 컷 2개]
{URL}
```

**실패:**
```
❌ Shot {SHOT}: {error} — 스킵
```

**러너 경고는 그대로 전달한다** (stderr `⚠️`):
```
⚠️ Shot 0020: 키프레임 3장 — Kling은 2장까지라 Seedance 2.0으로 전환합니다
⚠️ Shot 0030: 레퍼런스 2장은 Kling이 받지 않아 제외됩니다 (Seedance를 쓰세요)
⚠️ Shot 0040: 이미지 총 12장 — 상한 9장이라 레퍼런스 3장을 뺐습니다
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
