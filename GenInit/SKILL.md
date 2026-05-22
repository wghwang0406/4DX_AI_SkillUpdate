---
version: 5.0.0
name: GenInit
description: |
  소스 파일(PDF/영상 샷클립/콘티이미지)을 감지해 MD 프롬프트 파일 작성 + 캐릭터 시트 이미지 생성.
  영상 모드: 샷 단위 클립(0010_v1.mp4) → 첫/끝 프레임을 Image 폴더에 연속 번호로 저장.
  캐릭터 시트: 소스 스타일 자동 감지 후 GPT Image 2로 무드보드형 생성.
  MD 출력 전체 한국어. 폴더가 없으면 자동으로 생성한다.
  Use when: "GenInit", "프롬프트 파일 채워줘", "소스 분석해줘", "초기화해줘", source-to-md.
argument-hint: "[EP##] [S##]"
allowed-tools: Bash, Read, Write
---

# GenInit

소스 파일(PDF·영상 샷클립·콘티이미지)을 분석해 MD 프롬프트 파일을 자동으로 채우고 캐릭터 시트를 생성한다.  
폴더가 없으면 자동으로 생성한다.  
**모든 MD 파일은 한국어로 작성한다.**

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
mkdir -p {EP}/character
touch {EP}/Image/{SEQ}/Sceneprompt.md
touch {EP}/Image/{SEQ}/Shotprompt.md
touch {EP}/Conti/{SEQ}/shotlist_{SEQ}.md
```

새로 만들었으면 출력:
```
📁 폴더 생성: {EP}/Image/{SEQ}/, {EP}/Conti/{SEQ}/
```

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
프로젝트 폴더 또는 Conti/{SEQ}/ 에 파일을 넣고 /GenInit을 다시 실행하세요.
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

**4-A. 등장인물 추출 → Character.md (한국어)**

비어있으면: PDF 전체에서 등장인물 이름·외모·의상 추출.

```markdown
{이름} : {외모 묘사}. {의상 묘사}.
```

파일 위치: `{EP}/character/Character.md`

**4-B. 씬 지문 분석 → Sceneprompt.md (한국어)**

비어있으면: 해당 시퀀스 지문 추출, 4줄 형식:

```
1줄: 스타일 + 시대 + 시간대
2줄: 장소 + 주요 액션 요약
3줄: 카메라 스타일 + 색조
4줄: 시대 고증 핵심 항목
```

파일 위치: `{EP}/Image/{SEQ}/Sceneprompt.md`

**4-C. 샷 묘사 → Shotprompt.md (한국어)**

비어있으면: 씬에서 대표 샷 선정, 번호 리스트 형식:

```
0010. {카메라 포지션} — {주요 액션/움직임}. {인물 감정/표정}.
0020. ...
```

파일 위치: `{EP}/Image/{SEQ}/Shotprompt.md`

**4-D. 전체 샷 분해 → shotlist_{SEQ}.md (한국어)**

비어있으면: 씬 전체를 샷으로 분해.

- 대사 있는 모든 줄 → 독립 샷 (예외 없음)
- 샷 번호: 0010, 0020, 0030... (4자리, 10 단위)
- 상태 기본값: ⏳

```markdown
# 시퀀스 {SEQ} — {씬 제목}

> 상태: ✅완료 / ⏳대기 / ❌스킵 / 🔄재생성중

| # | 샷사이즈 | 인물 | 묘사 | 상태 |
|---|---|---|---|---|
| 0010 | EWS | — | ... | ⏳ |
...
```

파일 위치: `{EP}/Conti/{SEQ}/shotlist_{SEQ}.md`

**4-E. Projectprompt.md (한국어)**

신규 프로젝트는 Projectprompt.md가 없거나 비어있는 게 정상이다. GenInit이 최초 실행 시 자동으로 생성한다.
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

- `{SEQ}_{SHOT}_v1.png` → GenImg2Img 스타일 변환 소스 / GenVideo 싱글 이미지
- 페어 필요 시 수동으로 `{SEQ}_{SHOT}-1_v1.png`(스타트), `{SEQ}_{SHOT}-2_v1.png`(엔드) 파일 추가
- Conti 폴더에는 저장하지 않음

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

## Step 5 — 캐릭터 시트 생성

Character.md에 등장인물이 있으면 무드보드형 캐릭터 시트를 생성한다.

### 스타일 결정 기준

| 소스 상황 | DETECTED_STYLE |
|---|---|
| 3D CG 애니메이션 영상/이미지 | `Pixar/Disney 3D CG animated film` |
| 실사 촬영본 | `photorealistic cinematic live-action` |
| 2D 일러스트 | `2D illustration, flat design` |
| PDF / 콘티 스케치 | `black and white pencil sketch, storyboard style` |
| 불분명 | Projectprompt.md 스타일 키워드 사용 |

### 확인 후 생성

```
📋 캐릭터 시트 생성 예정 [{DETECTED_STYLE}]:
  • {이름1} → {EP}/character/{이름1}_Character_v1.png
  • {이름2} → {EP}/character/{이름2}_Character_v1.png
생성할까요? (y/n)
```

### 프롬프트 구조

```
Character reference sheet, {DETECTED_STYLE} style, white background.
Top-left: three full-body views (front, three-quarter, back) showing complete outfit.
Top-right: 9 facial expression portraits in 3×3 grid (happy, laughing, surprised, angry, sad, worried, playful, sleepy, neutral).
Bottom-left: one full body pose + detail close-ups (eye, hair texture, clothing fabric, accessories).
Bottom center: color palette swatches (6–8 colors).
Bottom-right: 2 personality/action poses.
Character: {Character.md 외형 묘사 → 영어 번역 삽입}.
Consistent design across all views, white background.
No text, no labels, no watermarks.
```

생성 전 **각 캐릭터마다 전체 프롬프트를 채팅에 출력**한 뒤 생성 진행:

```
🔍 {이름} 프롬프트:
{위 프롬프트 구조에 실제 값이 채워진 전체 텍스트}
```

### 생성 CLI

```bash
higgsfield generate create gpt_image_2 \
  --prompt "..." \
  --aspect_ratio 16:9 \
  --quality high \
  --resolution 2k \
  --wait --wait-timeout 10m
```

생성 완료 후:
```bash
curl -o "{EP}/character/{이름}_Character_v1.png" "{URL}"
```

출력:
```
✅ {이름} 캐릭터 시트 생성 완료
[{이름}_Character_v1.png]({URL})
{URL}
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

생성된 캐릭터 시트:
  {EP}/character/{이름}_Character_v1.png

스킵 (이미 존재):
  (해당 파일 목록 또는 없으면 생략)

다음 단계:
  /GenImg2Img → 스타일 변환 (영상 소스일 때)
  /GenConti2Img → 씬 이미지 생성
  /GenVideo → 영상 생성
```

## UX 규칙

- 사용자 언어(한국어/영어)로 응답
- 모든 MD 출력은 한국어로 작성
- 이미 내용이 있는 파일은 절대 덮어쓰지 않고 "스킵" 표시
- 빈 파일(0바이트)은 채워도 됨
- Character.md는 에피소드 단위 — 해당 EP에 이미 내용이 있으면 스킵
- 캐릭터 시트 생성 전 반드시 목록과 스타일 확인 후 진행
