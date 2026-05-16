---
version: 1.1.0
name: GenConti
description: |
  PDF 시나리오에서 특정 시퀀스를 추출해 콘티(storyboard) 이미지를 배치 생성한다.
  시퀀스 텍스트를 분석해 샷 리스트(샷 사이즈/앵글/액션)를 만들고,
  각 샷마다 GPT Image 2로 러프 스케치 또는 시네마틱 스틸을 생성한다.
  Characters.md가 있으면 캐릭터 묘사에 활용한다.
  Use when: "GenConti", "시나리오 콘티 만들어", "씬 샷 분해", "PDF 콘티 생성", "storyboard from screenplay".
argument-hint: "<PDF_PATH> <SEQUENCE_ID> [sketch|cinematic]"
allowed-tools: Bash, Read, Write
---

# GenConti

PDF 시나리오 → 샷 분해 → 러프 콘티 이미지 배치 생성 스킬.

**최종 이미지 = 샷 사이즈/앵글 + 장소/분위기 + 캐릭터 묘사 + 스타일**

## Step 0 — config.md 읽기

```bash
ls config.md 2>/dev/null | head -1
```

없으면 중단:
```
❌ config.md를 찾을 수 없습니다. 먼저 /GenInit을 실행하세요.
```

Read 툴로 config.md 읽기. `project_code` 파악 (예: `GRB`).

## Step 1 — 인자 파싱

- 첫 번째 인자: PDF 경로 (상대 또는 절대)
- 두 번째 인자: 시퀀스 식별자 — 숫자 (예: `41`) 또는 부분 이름 (예: `군산 외곽`)
  - 숫자만 입력 시 → `S41` 형태의 SEQ_ID로 변환
- 세 번째 인자 (선택): `sketch` (기본값) 또는 `cinematic`

절대 경로 확인:
```bash
realpath "<PDF_PATH>" 2>/dev/null || echo "NOT FOUND"
```

없으면 중단:
```
❌ PDF를 찾을 수 없습니다: <PDF_PATH>
```

**스타일 정의:**
- `sketch` → 흑백 연필 선화, 러프 스토리보드 스케치, 구도와 액션 중심
- `cinematic` → 풀컬러, 시네마틱 스틸, Pixar/Disney 3D CG 애니메이션 품질

config.md의 Episode Mapping에서 해당 시퀀스의 에피소드 파악:
```
| S41 | EP01 | → EPISODE=EP01
```

테이블에 없으면:
```
⚠️ {SEQ_ID}의 에피소드 매핑이 config.md에 없습니다. config.md에 추가해주세요.
❌ 중단
```

## Step 2 — PDF에서 시퀀스 추출

Read 툴로 PDF를 읽는다. 시퀀스 식별자로 해당 씬을 찾는다.

한국 시나리오 포맷: 시퀀스는 아래 형식으로 시작:
```
41. 장소명 -D/-N
```
또는
```
S#41 장소명
```

해당 헤딩부터 다음 시퀀스 헤딩 (`다음번호.` 또는 `FADE OUT` 또는 `END`) 직전까지 추출.

없으면 중단:
```
❌ 시퀀스 "<SEQUENCE_ID>"를 PDF에서 찾을 수 없습니다.
```

## Step 3 — Projectprompt.md 확인 및 자동 생성

```bash
ls "Projectprompt.md" 2>/dev/null | head -1
```

**있으면:** 내용을 읽어 메모리에 보관. Step 7 프롬프트 구성 시 `[Project Style]` 블록으로 삽입.

**없으면:** 전체 PDF를 다시 분석해 Projectprompt.md를 자동 생성한다.

분석 항목:
- 장르 및 세계관 (예: 현실, 판타지, SF, 시대물)
- 전체 분위기 및 무드 키워드 (예: 쓸쓸함, 따뜻함, 긴장감)
- 주요 공간/배경 유형과 색감
- 조명 방향성 (낮/밤, 자연광/인공광, 색온도)
- 카메라 무드 (핸드헬드, 정적, 시네마틱)
- 등장인물 요약 (이름, 관계, 핵심 외형 힌트)

생성 포맷:

```markdown
# <프로젝트명> — Master Projectprompt

## Project Identity
<장르, 세계관, 핵심 주제 2~3문장>

---

## Universal Rules (All Scenes)
- <스타일 규칙 bullet>

---

## 주요 공간 #1 (<공간명>)
**Color & Light:** ...
**Texture & Detail:** ...
**Motion Style for i2v:** ...
**Mood:** ...
```

생성 후 `Projectprompt.md`로 저장하고 사용자에게 알린다:
```
📝 Projectprompt.md 자동 생성 완료 — 내용을 확인하고 수정하세요.
```

## Step 4 — Characters.md 확인 (선택)

**Read 툴로 새로 읽는다. 캐릭터 외형 묘사 참조용.**

```bash
ls "{EP}/character/Character.md" 2>/dev/null | head -1
```

있으면: 캐릭터명 → 외형 묘사 매핑을 메모리에 보관.
없으면: 시나리오 텍스트의 캐릭터 묘사만 사용.

## Step 5 — 출력 폴더 및 추적 파일 초기화

```bash
mkdir -p "{EP}/Conti/{SEQ_ID}"
```

**shotlist_{SEQ_ID}.md** 생성 (없으면):
```markdown
# 시퀀스 {SEQ_ID} — <씬 제목>

> 상태: ✅완료 / ⏳대기 / ❌스킵 / 🔄재생성중

| # | 샷사이즈 | 인물 | 묘사 | 상태 |
|---|---|---|---|---|
| 0010 | EWS | — | ... | ⏳ |
...
```

파일 위치: `{EP}/Conti/{SEQ_ID}/shotlist_{SEQ_ID}.md`

**urls_{SEQ_ID}.md** 생성 (없으면):
```markdown
# 시퀀스 {SEQ_ID} — 생성 URL

| # | URL |
|---|---|
| 0010 | ⏳ |
...
```

파일 위치: `{EP}/Conti/{SEQ_ID}/urls_{SEQ_ID}.md`

URL 형식은 반드시 `<https://...>` 꺾쇠 형식 — VS Code 에디터에서 Cmd+클릭으로 직접 열 수 있음.

## Step 6 — 샷 분해

추출한 시퀀스 텍스트를 분석해 샷 리스트를 구성한다.

**샷 번호 부여:** 0010, 0020, 0030... (4자리, 10 단위 증가)

**샷 분해 기준:**

> ⚠️ **절대 규칙 — 대사는 예외 없이 무조건 독립 샷**
> 시나리오에 대사가 한 줄이라도 있으면 반드시 별도 샷으로 분리한다. 뭉뚱그리거나 다른 행동 묘사에 합치지 않는다.

1. **대사 비트 (최우선)** — 대사가 있는 모든 줄은 무조건 독립 샷. 예외 없음.
   - 발화 샷: 말하는 인물의 MCU/CU — 묘사에 `[대사] "..."` 형식으로 반드시 기재
   - 반응 샷: 상대방 반응이 암시되면 바로 다음 샷으로 추가. `[반응]` 태그 사용
   - 괄호 지문 `(잠시)`, `(끄덕)`, `(쓴웃음)` 등도 독립 샷으로 처리
   - 대사가 여러 줄이면 줄마다 각각 독립 샷

2. **액션 비트 단위** — 주요 행동이 바뀌는 지점마다 새 샷. 한 문장 = 최소 1샷.
3. **공간 → 인물 → 디테일 드릴다운** — 시퀀스 시작은 Wide로 장소 설정, 이후 인물로 좁히고, 감정 피크는 Close/ECU
4. **시나리오 지문 힌트** — `(고속)`, `(슬로우)`, 시선/반응 명시 부분은 별도 샷.
5. **감정 곡선** — 긴장감이 올라가면 샷이 점점 좁아지고 짧아지도록 설계

**샷 사이즈 기준:**
| 크기 | 용도 |
|---|---|
| EWS (Extreme Wide Shot) | 압도적 장소 강조 |
| WS (Wide Shot) | 장소 설정, 공간 맥락 |
| MWS (Medium Wide Shot) | 인물 그룹, 환경과 인물 관계 |
| MS (Medium Shot) | 1~2인물, 대화 |
| MCU (Medium Close-Up) | 표정 강조, 대사 발화 |
| CU (Close-Up) | 얼굴, 감정, 반응 |
| ECU (Extreme Close-Up) | 특정 디테일 (눈, 손, 오브젝트) |
| POV | 캐릭터 시점 |
| Insert | 중요 소품 |

분해 결과를 테이블로 표시 후 **사용자 승인을 받은 뒤** 생성 진행:

```
| # | 샷사이즈 | 인물 | 묘사 | 상태 |
|---|---|---|---|---|
| 0010 | EWS | — | 군산 외곽 도로, 새벽 안개 | ⏳ |
| 0020 | WS | — | 트럭 진입 | ⏳ |
...
```

## Step 7 — 이미지 생성

모든 이미지 경로는 절대경로 사용.

**한 컷씩 생성 → 보여주기 → 사용자 OK → 다음 컷** (병렬 생성 금지)

출력 파일명: `{EP}/Conti/{SEQ_ID}/{SHOT_NUM}_v{N}.png` (예: `EP01/Conti/S41/0010_v1.png`)
재생성 시 버전 증가: v1 → v2 → v3

각 샷마다 프롬프트 구성 후 생성:

### 프롬프트 구성

**sketch 스타일:**
```
Rough storyboard sketch, black and white pencil line art, minimal shading, no color.
[Shot]: {shot size}, {camera angle}.
[Scene]: {location and atmosphere from screenplay}.
[Action]: {key action or moment}.
{캐릭터가 있을 경우}: [Character]: {캐릭터 외형 묘사 — Character.md 참조 또는 시나리오 기반}
{Projectprompt.md 있을 경우}: [Project Style]: {Universal Rules + 해당 공간 색감/조명/무드 핵심만 1~2줄}
Animated film storyboard pre-visualization, clear composition, rough and fast sketch style.
No text, no subtitles, no watermarks.
```

**cinematic 스타일:**
```
Pixar/Disney quality 3D CG animation, cinematic 16:9 still frame.
[Shot]: {shot size}, {camera angle}.
[Scene]: {location and atmosphere from screenplay}.
[Action]: {key action or moment, character poses and expressions}.
{캐릭터가 있을 경우}: [Character]: {캐릭터 외형 묘사 — Character.md 참조 또는 시나리오 기반}
{Projectprompt.md 있을 경우}: [Project Style]: {Universal Rules + 해당 공간 색감/조명/무드 핵심만 1~2줄}
Cinematic lighting, film grain, no text, no subtitles, no watermarks.
```

### 생성 명령 (gpt_image_2)

```bash
higgsfield generate create gpt_image_2 \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --quality high \
  --resolution 2k \
  --wait --wait-timeout 10m
```

## Step 8 — 결과 보고 및 파일 업데이트

**생성 완료 시마다 즉시:**

1. 채팅에 출력:
```
✅ Shot {SHOT_NUM} [{shot size} | sketch/cinematic]
<{URL}>
```

2. `{EP}/Conti/{SEQ_ID}/urls_{SEQ_ID}.md` 해당 행 업데이트:
```
| 0010 | <https://...> |
```

3. `{EP}/Conti/{SEQ_ID}/shotlist_{SEQ_ID}.md` 해당 행 상태 ⏳ → ✅ 업데이트

오류 시:
```
❌ Shot {SHOT_NUM}: {오류 메시지} — 스킵
```
shotlist 상태 → ❌

## 스토리보드 합성

사용자가 **"0010~0050 스토리보드 만들어줘"** 또는 **"스토리보드"** 요청 시:

1. `{EP}/Conti/{SEQ_ID}/urls_{SEQ_ID}.md`에서 해당 범위 URL 읽기
2. 이미 로컬에 있으면 스킵, 없으면 다운로드:
```bash
curl -o "{EP}/Conti/{SEQ_ID}/{SHOT_NUM}_v1.png" "<URL>"
```
3. Python Pillow로 그리드 합성:
```python
from PIL import Image, ImageDraw, ImageFont

base = "<작업경로>/{EP}/Conti/{SEQ_ID}"
files = ["0010_v1.png", "0020_v1.png", ...]
labels = ["Shot 0010", "Shot 0020", ...]

thumb_w, thumb_h = 380, 214
pad = 8
label_h = 22
cols = len(files)

canvas_w = (thumb_w + pad) * cols + pad
canvas_h = pad + label_h + thumb_h + pad
canvas = Image.new("RGB", (canvas_w, canvas_h), (17, 17, 17))
draw = ImageDraw.Draw(canvas)

try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
except:
    font = ImageFont.load_default()

for i, (f, label) in enumerate(zip(files, labels)):
    img = Image.open(f"{base}/{f}").convert("RGB").resize((thumb_w, thumb_h), Image.LANCZOS)
    x = pad + i * (thumb_w + pad)
    canvas.paste(img, (x, pad + label_h))
    draw.text((x + thumb_w // 2, pad + 4), label, fill=(255,255,255), font=font, anchor="mt")

canvas.save(f"{base}/storyboard_{SEQ_ID}_{START}-{END}.jpg", "JPEG", quality=92)
```
4. 저장 경로 알림: `{EP}/Conti/{SEQ_ID}/storyboard_{SEQ_ID}_{START}-{END}.jpg`

## UX 규칙

- 사용자 언어(한국어/영어)로 응답
- **샷 분해 테이블을 먼저 보여주고 사용자 승인 받은 뒤 생성 시작**
- **한 컷씩 생성 → 보여주기 → 사용자 OK → 다음 컷** (병렬 생성 금지)
- URL은 채팅에서도 `<URL>` 꺾쇠 형식으로 표시
- Job ID, raw JSON 노출 금지
- 비용 예측 금지
- 스토리보드 합성은 사용자 요청 시에만 실행 (자동 실행 금지)
