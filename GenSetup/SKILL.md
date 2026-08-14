---
version: 5.2.0
name: GenSetup
description: |
  소스 파일(PDF/영상 샷클립/콘티이미지)을 감지해 MD 프롬프트 파일 작성 + 에셋 라이브러리 생성.
  영상 모드: 샷 단위 클립(0010_v1.mp4) → 첫/끝 프레임을 Image 폴더에 연속 번호로 저장.
  에셋: 등장체(char) / 배경(loc) / 소품(prop) 3종을 각도별로 생성. 인물은 Lira 3패널 규격.
  MD 초안은 Cinedance 12섹션 순서의 한국어. 폴더가 없으면 자동으로 생성한다.
  Use when: "GenSetup", "GenInit"(레거시 별칭), "프롬프트 파일 채워줘", "소스 분석해줘", "초기화해줘", source-to-md.
argument-hint: "[EP##] [S##]"
allowed-tools: Bash, Read, Write, Skill
---

# GenSetup

소스 파일(PDF·영상 샷클립·콘티이미지)을 분석해 MD 프롬프트 파일을 자동으로 채우고 에셋 라이브러리를 생성한다.  
폴더가 없으면 자동으로 생성한다.  
**모든 MD 파일은 한국어로 작성한다.**

## 원문 규격 참조 (필수)

프롬프트를 쓰기 전에 해당 원문 스킬을 Read한다. 요약본으로 대체하지 않는다.

| 무엇을 쓸 때 | 읽을 파일 |
|---|---|
| 에셋 시트 프롬프트 (인물·배경·소품) | `~/.claude/skills/Lira/SKILL.md` |
| Sceneprompt / Shotprompt 초안 | `~/.claude/skills/Cinedance/SKILL.md` |
| Character.md 연기 마스터 프로필·Voice | `~/.claude/skills/Acting/SKILL.md` |

> 세 파일은 이 저장소에 함께 들어 있다 (출처: Higgsfield). 못 찾으면 `~/.claude/CLAUDE.md`의
> **프롬프트 규칙 10개**를 근거로 진행한다 — 중단하지 않는다.

`~/.claude/CLAUDE.md`의 **프롬프트 규칙 10개**는 항상 적용된다.

## Step 1 — config.md 읽기 + 인자 파싱

```bash
cat config.md 2>/dev/null || echo "NOT_FOUND"
```

- config.md가 있으면 `project_code`, `project_title`, `type`, Episode Mapping 파악
- 인자로 EP, SEQ가 전달되면 우선 사용
- 없으면 config.md Episode Mapping 첫 번째 행 사용
- config.md도 없고 인자도 없으면 사용자에게 `EP##`, `S##` 요청

Projectprompt.md가 있으면 읽어서 스타일 컨텍스트 파악:

```bash
cat Projectprompt.md 2>/dev/null | head -60
```

## Step 2 — 대상 경로 확인 및 자동 생성

폴더가 없으면 자동으로 만든다:

```bash
mkdir -p {EP}/Image/{SEQ}
mkdir -p {EP}/Conti/{SEQ}
mkdir -p {EP}/character/char {EP}/character/loc {EP}/character/prop
touch {EP}/Image/{SEQ}/Sceneprompt.md
touch {EP}/Image/{SEQ}/Shotprompt.md
touch {EP}/Conti/{SEQ}/shotlist_{SEQ}.md
```

`{EP}/character/` 아래 하위폴더 3개 = 등장체(`char`) / 배경(`loc`) / 소품(`prop`).
`char`는 인물 전용이 아니라 **등장체 전부**(인물·동물·크리처)를 담는다.

새로 만들었으면 출력:
```
📁 폴더 생성: {EP}/Image/{SEQ}/, {EP}/Conti/{SEQ}/, {EP}/character/{char,loc,prop}/
```

**기존 프로젝트 마이그레이션 (선택):** `{EP}/character/` 바로 아래에 flat 시트가 있으면 물어본다.
```bash
ls {EP}/character/*_Character*.png 2>/dev/null | head -5
```
있으면:
```
📦 기존 캐릭터 시트 N개가 {EP}/character/ 바로 아래에 있습니다. char/로 옮길까요? (y/n)
```
**거절해도 그대로 동작한다** — runner의 에셋 탐색이 하위폴더에서 못 찾으면 flat 경로로 폴백한다.
승인하면: `mv {EP}/character/*_Character*.png {EP}/character/char/`

### Step 2.5 — 공유 스크립트 시딩 (자동 복사)

범용 엔진·헬퍼를 공유 번들(`~/.claude/skills/_shared/scripts/`)에서 프로젝트로 복사한다.
**있으면 덮지 않는다(`cp -n`).** 프로젝트 루트(config.md 위치)를 `PROJ_ROOT`로 사용.

```bash
PROJ_ROOT=$(python3 -c "import pathlib,sys; p=pathlib.Path('.').resolve(); [sys.exit(print(str(x))) or 0 for x in [p]+list(p.parents) if (x/'config.md').exists()]; sys.exit(print(str(p)))")
SHARED="$HOME/.claude/skills/_shared/scripts"
mkdir -p "$PROJ_ROOT/scripts"
# 공통(영상 무관): 엔진 + 이미지 헬퍼
cp -n "$SHARED/core/runner.py" "$SHARED/core/cache.py" "$SHARED/core/models.py" "$PROJ_ROOT/" 2>/dev/null
cp -n "$SHARED/core/gen_helper.py" "$SHARED/core/genconti2img_minimal.py" "$PROJ_ROOT/scripts/" 2>/dev/null
```

**영상 소스가 있을 때만** 영상 컷 헬퍼도 시딩한다 (스토리보드 mp4 존재 시):
```bash
if find "$PROJ_ROOT" -maxdepth 4 -name "*.mp4" 2>/dev/null | grep -q .; then
  cp -n "$SHARED/optional/split_shot_cuts.py" "$SHARED/optional/extract_motion_frames.py" "$SHARED/optional/transition_to_single_frame.py" "$PROJ_ROOT/scripts/" 2>/dev/null
  echo "🎬 영상 소스 감지 → 컷분할 헬퍼 시딩"
fi
echo "🐍 스크립트 시딩: runner.py + cache.py (+scripts/ 헬퍼)"
```

> 영상 컷 헬퍼(split_shot_cuts·extract_motion_frames·transition_to_single_frame)는
> **스토리보드 영상(mp4)이 있어야** 동작하므로 영상 소스일 때만 복사한다.
> 공유 번들이 없으면(처음 셋업 전) 이 단계는 조용히 스킵.

config.md Episode Mapping에 해당 SEQ가 없으면 행 추가:
```
| {SEQ} | {EP} |
```

## Step 3 — 소스 파일 감지

우선순위: **PDF > 영상 > 콘티이미지**

```bash
# PDF (있으면 다른 소스 무시하고 PDF 모드로)
find . -maxdepth 2 -name "*.pdf" 2>/dev/null

# 영상 — 샷 단위 클립 우선 감지 (0010_v1.mp4 패턴)
find . -maxdepth 3 \( -name "*.mp4" -o -name "*.mov" -o -name "*.MOV" -o -name "*.MP4" \) 2>/dev/null \
  | grep -E '/[0-9]{4}' | sort -V

# 위 결과 없으면 시퀀스 단위 영상 탐색
find . -maxdepth 2 \( -name "*.mp4" -o -name "*.mov" -o -name "*.MOV" -o -name "*.MP4" \) 2>/dev/null \
  | grep -vE '/[0-9]{4}'

# 콘티 이미지 — PDF·영상이 없을 때만:
# 1순위: Conti/{SEQ}/ 폴더 안 이미지 (_v# 제외)
find "{EP}/Conti/{SEQ}" -maxdepth 1 \( -name "*.png" -o -name "*.PNG" -o -name "*.jpg" -o -name "*.JPG" \) 2>/dev/null | grep -v "_v[0-9]" | sort -V

# 2순위: 루트 근처 외부 이미지 (Image/, character/ 제외, _v# 제외)
find . -maxdepth 4 \( -name "*.jpg" -o -name "*.JPG" -o -name "*.jpeg" -o -name "*.png" -o -name "*.PNG" \) 2>/dev/null | grep -v "_v[0-9]" | grep -v "/Image/" | grep -v "/character/"
```

감지 결과 분류:
- 4자리 숫자 패턴 영상 → **샷 단위 영상 모드**
- 그 외 영상 → **시퀀스 단위 영상 모드** (기존 방식)

소스 없으면:
```
소스 파일(PDF / 영상 / 콘티이미지)이 없습니다.
프로젝트 폴더 또는 Conti/{SEQ}/ 에 파일을 넣고 /GenSetup을 다시 실행하세요.
```
→ 중단

## Step 4 — 소스 타입별 분석 및 MD 채우기

이미 내용이 있는 파일(0바이트 초과)은 스킵.

각 파일 크기 확인:
```bash
wc -c {EP}/character/Character.md 2>/dev/null
wc -c {EP}/Image/{SEQ}/Sceneprompt.md 2>/dev/null
wc -c {EP}/Image/{SEQ}/Shotprompt.md 2>/dev/null
wc -c {EP}/Conti/{SEQ}/shotlist_{SEQ}.md 2>/dev/null
```

---

### PDF 모드

Read 툴로 PDF를 읽는다.

**스타일 감지:** PDF 장르·세계관 파악 → `DETECTED_STYLE` 결정

**4-A. 에셋 사전 → Character.md (한국어 + 영문 앵커)**

비어있으면: PDF 전체에서 **등장체 / 배경 / 소품** 세 종류를 전부 추출한다.
`char`는 인물 전용이 아니다 — 동물·크리처도 등장체다.

각 항목에 붙는 것:
- **@태그** — 프롬프트 본문엔 이 태그만 쓴다. 외형 설명글은 이 파일 한 곳에만 둔다.
- **kind** — `human` / `animal` / `creature` (등장체만)
- **state** — `base` 기본. **상태가 바뀌면 별개 에셋**이므로 젖음·손상·환복은 행을 따로 만든다.
  장소도 낮·밤·비가 각각 다른 행. 시나리오에 **실제로 나올 때만** 추가한다(안 그러면 곱하기로 늘어난다).
- **앵커** — CINEDANCE 공식 그대로. `~/.claude/skills/Cinedance/SKILL.md`의 *Character description rule* 참조.
  `age + role/body type + current state + 시각 앵커 + 행동에 필요한 소품/신체 상태. 100% matches the reference.`
  **나이를 쓴다** — 공식이 요구한다.
- **마스터 프로필 / Voice** — 등장체만. `~/.claude/skills/Acting/SKILL.md` PART II 규격.
  프로필은 **150–220단어 영문 한 문단**, 고정 블록 순서, `However, when X →` 크랙 절 필수, eye life 필수.
  의상·카메라·색은 프로필에 넣지 않는다. Voice는 1–2문장 따옴표, 씬마다 수정하지 않는다.

```markdown
# 에셋 사전 — {EP}

## 등장체

### @해수
- kind: human / state: base
- 설명: {한국어 외형·의상 묘사}
- 앵커: 28yo lean female detective, shoulder-length black hair tied back, worn navy field
  jacket, right hand bandaged. 100% matches the reference.
- 시트: char/해수_Character_sheet_v1.png
- 마스터 프로필: Character acting as 해수. {영문 150–220단어 한 문단}
- Voice: "A 28-year-old ... "

### @해수_wet
- kind: human / state: wet (3막 추격 이후)
- 설명: ...

## 배경

### @loc_카페
- state: day
- 설명: {한국어 공간 묘사}
- 카메라 앵커: {Lira의 Location 템플릿에서 가장 중요한 항목 — 단순한 표현으로}
- 시트: loc/카페_Location_{wide,34,top,detail}_v1.png

## 소품

### @prop_권총
- state: base
- 설명: ...
- 시트: prop/권총_Prop_{top,34,detail}_v1.png
```

파일 위치: `{EP}/character/Character.md`

**4-B. 씬 지문 분석 → Sceneprompt.md (한국어)**

비어있으면: 해당 시퀀스 지문을 추출해 아래 절을 채운다.
**LOCATION MAP은 필수다** — 이게 없으면 컷이 바뀔 때 인물이 순간이동한다.

```markdown
## 스타일
{시대 + 시간대 + 색조 + 촬영 register}  ← 프로젝트 공통 스타일은 Projectprompt.md에 두고 여기선 씬 고유분만

## LOCATION MAP
{인물도 동작도 없이 장소만 쓴다}
- 카메라 위치 / 카메라가 바라보는 방향
- 전경 / 중경 / 배경에 각각 무엇이 있는지
- 주요 랜드마크 위치 (기준점)
- 인물이 움직이는 동선
- 조명 방향
- 카메라가 넘지 않는 선

## 조명
{주광원 + 방향 + 색온도 + 노출 우선순위}

## 사운드
{환경음. 대사는 여기에만 쓰고 동작 항목엔 넣지 않는다}
```

LOCATION MAP은 **장면당 한 번** 쓰고 모든 컷이 공유한다. 컷마다 다시 쓰지 않는다.
자세한 항목은 `~/.claude/skills/Cinedance/SKILL.md`의 *Location map* 절 참조.

파일 위치: `{EP}/Image/{SEQ}/Sceneprompt.md`

**4-C. 샷 묘사 → Shotprompt.md (한국어)**

비어있으면: 씬에서 대표 샷을 선정한다. 형식은 **목표 영상 모델에 따라 갈린다.**

- **Seedance 2.0** — 타임코드 블록. 한 블록에 동작 하나.
  ```
  0010. [84°] 0:00–0:03 {카메라 거동} / {동작}. 0:03–0:06 {다음 동작}.
  ```
- **Kling 3.0** — 타임코드 없음(Custom Multi-Shot). 샷 단위로 쓴다.
  ```
  0010. [84°] {카메라 거동} — {동작 순서}.
  0020. [multi] {멀티샷일 때}
  ```

각 줄에 넣는 것:
- **대각 화각** `[47°]` `[84°]` `[107°]` `[29°]` `[18°]` `[8°]` — mm·f값이 아니라 화각으로.
  콘텐츠 타입별 선택 기준은 `Cinedance` 원문의 *Lens decision tree* 참조.
- **카메라 거동** — 물리적 오퍼레이터 행동으로 (`카메라 고정`, `엉덩이 높이에서`, `그림자 쪽에 서서`)
- **동작** — 감정어가 아니라 **관찰 가능한 몸의 일**. "슬프게" ✗ → "턱이 물렸다 풀린다, 코로 얕은 숨" ✓
  전환이 아니라 **상태**를 쓴다. "가방에 손을 넣어 꺼내 치켜든다" ✗ → "던지는 중, 팔이 뻗어 있다" ✓

파일 위치: `{EP}/Image/{SEQ}/Shotprompt.md`

**4-D. 전체 샷 분해 → shotlist_{SEQ}.md (한국어)**

비어있으면: 씬 전체를 샷으로 분해.

- 대사 있는 모든 줄 → 독립 샷 (예외 없음)
- 샷 번호: 0010, 0020, 0030... (4자리, 10 단위)
- 상태 기본값: ⏳
- **장소·소품 컬럼을 채운다** — 러너가 이걸로 배경·소품 레퍼런스를 고른다
- **샷사이즈는 정확히 적는다** — 러너가 이걸로 배경/인물 뷰를 고른다
  (`EWS/WS`→wide+front, `MS/MWS/OTS`→34+front, `CU/ECU`→detail+face)

```markdown
# 시퀀스 {SEQ} — {씬 제목}

> 상태: ✅완료 / ⏳대기 / ❌스킵 / 🔄재생성중

| # | 샷사이즈 | 인물 | 장소 | 소품 | 묘사 | 상태 |
|---|---|---|---|---|---|---|
| 0010 | EWS | — | 카페 | — | ... | ⏳ |
| 0070 | CU | 해수 | 카페 | 권총 | ... | ⏳ |
...
```

기존 프로젝트의 5컬럼 테이블(`# / 샷사이즈 / 인물 / 묘사 / 상태`)도 그대로 읽는다 —
장소·소품 컬럼이 없으면 해당 레퍼런스를 생략하고 기존 동작으로 폴백한다.

파일 위치: `{EP}/Conti/{SEQ}/shotlist_{SEQ}.md`

**4-E. Projectprompt.md (한국어)**

신규 프로젝트는 Projectprompt.md가 없거나 비어있는 게 정상이다. GenSetup이 최초 실행 시 자동으로 생성한다.
이미 내용이 있으면 스킵.

비어있으면: PDF/영상/이미지 전체를 분석해 장르·세계관·주요 공간·색감·조명 방향성을 채운다.

---

### 샷 단위 영상 모드

**ffmpeg 확인:**

```bash
which ffmpeg 2>/dev/null || echo "NOT_FOUND"
```

없으면:
```
⚠️ ffmpeg이 설치되어 있지 않습니다. brew install ffmpeg
```
→ 중단

**스타일 감지:** 첫 번째 클립 프레임 Vision 분석으로 `DETECTED_STYLE` 결정

**프레임 추출 → Image 폴더 (연속 번호 방식):**

샷 단위 클립 하나당:

```bash
# 첫 프레임 → {SEQ}_{SHOT}_v1.png
ffmpeg -i "{SHOT}_v1.mp4" -vframes 1 "{EP}/Image/{SEQ}/{SEQ}_{SHOT}_v1.png" -y
```

- `{SEQ}_{SHOT}_v1.png` → GenImg2Img 스타일 변환 소스 / GenVideo 단일 시작 프레임
- Conti 폴더에는 저장하지 않음

**GenVideo용 추가 이미지는 두 가지 방식이 있다 — 필요할 때 직접 만든다:**

| 원하는 것 | 만드는 법 |
|---|---|
| **순서대로 흐르는 영상** | `{SEQ}_{SHOT}-1_v1.png`, `-2`, `-3` … 숫자가 시간 순서. 개수 제한 없음 |
| **순서 없는 레퍼런스만** | `{SEQ}_{SHOT}_ref/` 폴더를 만들고 이미지를 넣는다 |

```
EP01/Image/S41/
  S41_0010_v1.png            ← ffmpeg이 뽑은 시작 프레임
  S41_0020-1_v1.png          ← 순서 키프레임 (직접 추가)
  S41_0020-2_v1.png
  S41_0020-3_v1.png
  S41_0030_ref/              ← 레퍼런스 폴더 (직접 추가)
    매대잡는손.png
```

- **`_ref/` 폴더를 미리 만들지 않는다.** 40샷이면 빈 폴더 40개가 생긴다.
  레퍼런스가 필요한 샷에만 사용자가 직접 만들고, 없으면 GenVideo가 그냥 지나간다.
- `_ref/` 안의 이미지는 **무조건 레퍼런스**다. 키프레임이 되는 일이 없다.
- 레퍼런스는 **Seedance 전용**이다 — Kling 3.0에는 레퍼런스 이미지 파라미터가 없다.

**Vision 분석 → 각 샷 MD 채우기 (한국어):**

추출된 첫 프레임들을 순서대로 Read 툴로 분석:
- 씬 전체 공통 분위기 → Sceneprompt.md (첫 번째 샷 기준)
- 샷별 카메라 앵글·액션·표정 → Shotprompt.md 각 번호 항목
- 등장인물 외형 → Character.md

→ 4-A~E와 동일하게 MD 파일 채우기

---

### 시퀀스 단위 영상 모드

**ffmpeg 확인:**

```bash
which ffmpeg 2>/dev/null || echo "NOT_FOUND"
```

없으면 중단.

**첫 프레임·마지막 프레임 추출:**

```bash
ffmpeg -i "{VIDEO_PATH}" -vframes 1 "{EP}/Conti/{SEQ}/{SEQ}_frame_first.png" -y
ffmpeg -sseof -1 -i "{VIDEO_PATH}" -vframes 1 "{EP}/Conti/{SEQ}/{SEQ}_frame_last.png" -y
```

**스타일 감지:** 두 프레임 Vision 분석으로 `DETECTED_STYLE` 결정  
두 프레임을 분석 → 씬 상황·배경·인물 외형·카메라 앵글 파악  
→ 4-A~D와 동일하게 MD 생성 (한국어)

---

### 콘티이미지 모드

**스타일 감지:** 첫 번째 이미지 Vision 분석으로 `DETECTED_STYLE` 결정

감지된 jpg/png 이미지를 Read 툴로 순서대로 Vision 분석:
- 각 이미지에서 샷사이즈·앵글·인물·액션 추출
- 캐릭터 외형 추출 (Character.md용, 추정값)

→ 4-A~D와 동일하게 MD 생성 (한국어)

---

## Step 5 — 에셋 생성 (등장체 / 배경 / 소품)

Character.md의 에셋 사전을 근거로 세 종류를 각도별로 생성한다.
**본 컷을 만들기 전에 에셋을 먼저 잠근다** — 등장체·배경·소품이 확정되기 전에 씬 이미지를 뽑으면
나중에 전부 다시 만들게 된다.

### 스타일 결정 기준

| 소스 상황 | DETECTED_STYLE |
|---|---|
| 3D CG 애니메이션 영상/이미지 | `Pixar/Disney 3D CG animated film` |
| 실사 촬영본 | `photorealistic cinematic live-action` |
| 2D 일러스트 | `2D illustration, flat design` |
| PDF / 콘티 스케치 | `black and white pencil sketch, storyboard style` |
| 불분명 | Projectprompt.md 스타일 키워드 사용 |

### 확인 후 생성

Character.md의 세 종류를 **분류 추측과 총 장수까지 보여주고** 승인받는다.
로봇·차량·말하는 물건처럼 등장체인지 소품인지 애매한 건 **여기서 물어봐 정리한다.**

```
📋 에셋 생성 예정 [{DETECTED_STYLE}]  — 총 {N}장

  char/  해수      human     시트1 + 파생3
         누렁이    animal    시트1 + 파생3
         로봇 K-9  creature  시트1 + 파생3   ← 소품 아닌가요?
  loc/   카페      day       정본1 + 뷰변경3
  prop/  권총      base      3뷰

분류나 목록에서 고칠 거 있으면 말씀하세요 (y / 수정 / n)
```

`수정`이면 사용자 지시대로 Character.md를 고치고 표를 다시 보여준다.
`일부만` 지정하면 해당 항목만 생성한다.

### 5-A. 등장체 시트 — Lira 3패널 규격

**생성 전에 `~/.claude/skills/Lira/SKILL.md`의 *Character sheet (photoreal, 3-panel)* 절을 Read한다.**

정본은 **3패널 한 장**이다. 정체성 앵커(`the same real person in all three`)가 세 패널이
같은 이미지 안에 있어야 작동하므로 쪼개서 생성하지 않는다.

```
Three studio photographs of the same {person/animal/creature} arranged side by side on a flat
neutral mid-grey studio backdrop, a film character sheet: full-body front photo on the left,
full-body back photo in the middle, close-up portrait photo on the right, the same real
{subject} in all three, consistent across panels. Soft directional cinematic studio lighting
from one side, gentle natural shadow falloff, clean neutral cinematic look.

The {subject}: {Character.md 앵커 → age, build, face features, hair, distinctive marks}.

{Wardrobe, consistent in all panels}. {Distinctive props / signature items}.

On the left panel the {subject} stands straight facing the camera in a neutral pose, arms
relaxed at the sides, full figure head to feet. In the middle panel the same standing pose is
seen from behind. On the right panel a close-up head-and-shoulders portrait, {expression as
observable muscle work}.

{Palette line — 60/30/10}. {Tech block}.
```

**절대 지키는 것 (Lira 명시):**

| ✗ 쓰지 않는다 | ✓ 대신 |
|---|---|
| `character reference sheet` (일러스트 트리거) | `film character sheet` / `studio photographs` |
| `painterly` (포토리얼에서 일러스트 트리거) | 필름 스톡·렌즈·실제 재질 앵커를 강화 |
| `rule of thirds` | 시트는 **예외** — 넣지 않는다 |
| `LEFT/MIDDLE/RIGHT` CAPS 블록 | 패널은 **산문**으로 서술 |
| 평평한 조명 | `soft **directional**` — 평평한 건 **배경**이지 조명이 아니다 |

- 문신·특징은 구체적인 실제 도안 + `clean line-work`. 막연한 `tattoos`는 뭉개진다.
- 실존 인물 이름·IP·브랜드 금지 → 특징 서술로 바꿔 쓴다.
- **나이는 쓴다** (CINEDANCE 앵커 공식 요구).
- aspect ratio·resolution은 CLI 파라미터로 넘긴다 — 프롬프트 텍스트에 넣지 않는다.

동물·크리처도 같은 3패널을 쓰되 `the same real person` → `the same {animal}`로 바꾸고,
종 식별이 되도록 두상이 보이게 한다.

**파생 3장** (선택, 승인 시): 시트를 레퍼런스로 물려 개별 플레이트를 뽑는다.
Lira의 편집 라인 규격 — **NBP 우선, 최소 CHANGE / 상세 PRESERVE EXACTLY**.
```
Edit the image: isolate the {front / back / close-up} panel as a standalone plate.

CHANGE: output only the {front} panel, filling the frame.

PRESERVE EXACTLY:
- face, hair, wardrobe, props, body proportions, pose
- the flat neutral mid-grey backdrop, the directional key light and its shadow falloff
- Color grade, palette, contrast, grain, falloff

ONLY CHANGE: the crop. 100% identical otherwise.
```
→ `char/{이름}_Character_{front,back,face}_v1.png`

### 5-B. 배경 4뷰

**`~/.claude/skills/Lira/SKILL.md`의 *Location / environment* 절을 Read한다.**

정본 `wide`를 먼저 만들고, 나머지 3뷰는 **뷰 변경**으로 뽑는다 —
Lira가 *"location view change → GPT Image 2가 잘 처리한다"*고 명시했다.

```
{카메라 앵커 — 가장 어려운 항목이니 단단히 고정. 단순한 표현이 추상적 전문용어를 이긴다:
 "high angle three-quarter wide shot, camera high above the room looking diagonally down at a
 45 degree angle" ○ / CCTV·fisheye 같은 표현 ✗}.
{장소 정체성}. {주요 건축·자연 요소}. {광원 + 방향 + 색온도}.
{깊이로 물러나는 부차 요소}. {팔레트 60/30/10}. {Tech block}. {무드}.
{비어 있어야 하면 긍정문으로: "empty deserted interior, bare walls, still air"}.
```

- **인물 없음.** 배경 에셋에 인물을 넣지 않는다.
- **옵틱/DOF 언어는 빼기** — 인물 전용이다 (Lira 명시).
- **그레인 단어를 겹쳐 쌓지 않는다** — 시네마 모델이 이미 네이티브로 갖고 있다. tech block 한 줄이면 족하다.
- 등장체·소품 시트와 달리 **배경은 시네마틱하게** 만든다.
- 뷰 변경 시 NBP를 쓸 거면 **오브젝트별 새 배치를 전부 명시**한다
  (`메인 뷰에서 오른쪽에 있던 소파가 리버스 뷰에서는 왼쪽에`). 안 하면 지오메트리가 깨진다.

4뷰: `wide`(establishing) / `34`(3/4 앵글) / `top`(탑다운 평면도) / `detail`(디테일 클로즈업)
→ `loc/{이름}_Location_{view}_v1.png`

### 5-C. 소품 3뷰

**`~/.claude/skills/Lira/SKILL.md`의 *Prop sheet* 절을 Read한다.**
소품은 Soul 계열이 아니라 **NBP / GPT Image 2**로 간다 (실사 제품 컨텍스트가 강하다).

```
Photorealistic {top-down / three-quarter overhead} product shot of {prop} on a neutral grey
concrete surface, soft directional lighting, isolated subject.
{구체적 묘사, 재질, 마모 상태}. {로고·문자가 없어야 하면 긍정문으로:
"plain unbranded wrapper, blank matte surface"}. {Tech block}.
```

- **무기류는 안전 필터에 걸린다** — 중립적 재질·기능 서술로 우회한다 (Lira 명시).
- 상태별(깨끗/손상/피 묻음)은 **별개 에셋**이다. 한 시트에 섞지 않는다.

3뷰: `top` / `34` / `detail` → `prop/{이름}_Prop_{view}_v1.png`

### 생성 전 출력 + CLI

생성 전 **각 에셋마다 전체 프롬프트를 채팅에 출력**한다:
```
🔍 {이름} [{kind}/{view}] 프롬프트:
{실제 값이 채워진 전체 텍스트}
```

**모델마다 플래그가 다르다 — 섞어 쓰면 실패한다:**

```bash
# 등장체 시트 (Soul 2.0) / 배경 정본 (Soul Cinema)
#   → --quality 는 1.5k|2k, --resolution 파라미터 없음
higgsfield generate create text2image_soul_v2 \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --quality 2k \
  --wait --wait-timeout 10m
# (Soul ID가 있으면 --custom_reference_id {ID} 추가)
# (배경이면 모델을 soul_cinematic 으로)

# 소품 3뷰 / 등장체 파생 (Nano Banana Pro)
#   → --resolution 은 1k|2k|4k, --quality 없음
higgsfield generate create nano_banana_2 \
  --prompt "..." \
  --image "{레퍼런스}" \
  --aspect_ratio 1:1 \
  --resolution 2k \
  --wait --wait-timeout 10m

# 배경 뷰 변경 (GPT Image 2)
#   → --resolution 1k|2k|4k + --quality low|medium|high 둘 다 있음
higgsfield generate create gpt_image_2 \
  --prompt "..." \
  --image "{정본 wide}" \
  --aspect_ratio 16:9 \
  --resolution 2k \
  --quality high \
  --wait --wait-timeout 10m
```

모델 선택 (Lira 라우팅, CLI 확인 완료):

| 에셋 | 모델 | ID | aspect |
|---|---|---|---|
| 등장체 시트 (3패널) | Soul 2.0 | `text2image_soul_v2` | `16:9` — **21:9 불가** |
| 등장체 파생 플레이트 | Nano Banana Pro | `nano_banana_2` | 원본 따름 |
| 배경 4뷰 (정본) | Soul Cinema | `soul_cinematic` | `16:9` 또는 `21:9` |
| 배경 뷰 변경 (34/top/detail) | GPT Image 2 | `gpt_image_2` | 정본 따름 |
| 소품 3뷰 | Nano Banana Pro | `nano_banana_2` | `1:1` (긴 소품은 `3:4`) |

- **Soul 2.0에는 21:9가 없다** — 와이드 인물 플레이트가 필요하면 Soul Cinema에 Soul ID를 물려 쓴다.
- 배경 뷰 변경을 NBP로 하면 **오브젝트별 새 배치를 전부 명시**해야 한다. GPT Image 2가 이 작업에 맞다.

### Soul ID (선택, 강력 권장)

Lira는 **정체성을 프로즈가 아니라 Soul ID가 담당**한다고 못박는다. 프로즈 앵커는 보강일 뿐이다.

```bash
higgsfield soul-id list                 # 이미 만든 것 확인
higgsfield soul-id create --help        # 새로 만들 때 옵션 확인
```

- 등장체 시트를 만든 뒤, 주요 인물은 Soul ID를 만들어 두면 샷마다 얼굴이 고정된다.
- Soul 2.0 / Soul Cinema의 `custom_reference_id` 파라미터로 넘긴다.
- **학습에 시간과 비용이 든다.** 목록을 보여주고 **사용자 승인을 받은 뒤에만** 만든다.
- Soul ID가 없으면 캐릭터 일관성이 시트 레퍼런스 + 앵커에만 의존하므로 5-D 검증이 그만큼 중요해진다.

생성 완료 후:
```bash
curl -o "{EP}/character/{sub}/{이름}_{Suffix}_{view}_v1.png" "{URL}"
```

출력:
```
✅ {이름} [{kind}/{view}] 생성 완료
[{파일명}]({URL})
{URL}
```

### 5-D. 일관성 검증 — 추가 생성 0장

시트를 만든 뒤, **이미 폴더에 있는** 샷·콘티 이미지와 대조한다. 새로 생성하지 않는다.

```bash
ls {EP}/Image/{SEQ}/*.png {EP}/Conti/{SEQ}/*.png 2>/dev/null | head -20
```

1. 해당 에셋이 나온 이미지를 **최대 4장**까지 골라 Read(vision)로 시트와 나란히 본다.
2. 판정표를 출력한다:
   ```
   🔍 @해수 일관성 검증 (기존 이미지 3장 대조, 생성 0장)
   | 항목 | S41_0070 | S41_0090 | 콘티 0110 |
   |---|---|---|---|
   | 얼굴 구조 | ✅ | ✅ | ⚠️ 턱선 다름 |
   | 헤어 | ✅ | ❌ 길이 다름 | ✅ |
   | 의상 | ✅ | ✅ | ✅ |
   | 체형 | ✅ | ✅ | ✅ |
   ```
   등장체는 얼굴·헤어·의상·체형, 배경은 배치·재질·조명 방향, 소품은 형태·색·비율로 본다.
3. 불일치가 있으면 **모델이 아니라 설명글을 고친다.**
   Character.md 앵커에서 **어느 줄이 모호한지 지목**하고 수정안을 제시한다:
   ```
   ⚠️ 헤어가 흔들립니다. 앵커의 "shoulder-length black hair"가 모호합니다.
      → "shoulder-length black hair, blunt cut, always tied back in a low ponytail"
      고칠까요? (재생성은 승인 후에만)
   ```
4. 대조할 이미지가 하나도 없으면(신규 프로젝트) 스킵하고 안내:
   ```
   ℹ️ 대조할 기존 이미지가 없어 검증을 건너뜁니다. 샷 이미지가 생기면 자동으로 검증합니다.
   ```

---

## Step 6 — 완료 보고

```
✅ 소스 감지: {파일명} ({타입: PDF/샷단위영상/시퀀스영상/콘티이미지})
✅ 시퀀스 {SEQ} 분석 완료

채워진 파일:
  {EP}/character/Character.md
  {EP}/Conti/{SEQ}/shotlist_{SEQ}.md   ← {N}샷
  {EP}/Image/{SEQ}/Sceneprompt.md
  {EP}/Image/{SEQ}/Shotprompt.md

추출된 프레임: (샷 단위 영상 모드일 때만)
  {EP}/Image/{SEQ}/{SEQ}_0010_v1.png (첫프레임 → 스타트)
  {EP}/Image/{SEQ}/{SEQ}_0011_v1.png (끝프레임 → 엔드)
  ...

생성된 에셋:
  char/  {이름}_Character_sheet_v1.png (+ front/back/face 파생)
  loc/   {이름}_Location_{wide,34,top,detail}_v1.png
  prop/  {이름}_Prop_{top,34,detail}_v1.png

일관성 검증: 기존 이미지 {N}장 대조, 추가 생성 0장 — {통과/불일치 N건}

스킵 (이미 존재):
  (해당 파일 목록 또는 없으면 생략)

다음 단계:
  /GenImg2Img → 스타일 변환 (영상 소스일 때)
  /GenConti2Img → 씬 이미지 생성
  /GenVideo → 영상 생성
```

## UX 규칙

- 사용자 언어(한국어/영어)로 응답
- 모든 MD 출력은 한국어로 작성 (영문 앵커·마스터 프로필·Voice는 예외 — 원문 규격이 영문)
- 이미 내용이 있는 파일은 절대 덮어쓰지 않고 "스킵" 표시
- 빈 파일(0바이트)은 채워도 됨
- Character.md는 에피소드 단위 — 해당 EP에 이미 내용이 있으면 스킵
- 에셋 생성 전 반드시 **분류·목록·총 장수**를 확인받고 진행
- 일관성 검증은 **추가 생성 없이** 기존 이미지로만 한다. 재생성은 승인 후에만
- 실패하면 모델이 아니라 **설명글(앵커)을 고친다**
