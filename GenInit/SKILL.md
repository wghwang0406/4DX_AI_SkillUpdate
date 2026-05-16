---
version: 3.0.0
name: GenInit
description: |
  새 프로젝트 폴더 초기화 스킬. 드라마/영화 유형 선택 후 폴더 구조와 빈 템플릿 파일 생성.
  드라마: EP01/{Conti,Image,Video,character} + 시퀀스 하위 폴더
  영화: 루트 바로 아래 {Conti,Image,Video,character} + 시퀀스 하위 폴더
  모든 md 파일은 빈 파일로 생성. 이미 존재하는 파일은 덮어쓰지 않음.
  소스 파일(PDF/영상/콘티이미지)이 있으면 자동 감지 후 Character.md, Sceneprompt.md, Shotprompt.md, shotlist를 채워줌.
  Use when: "GenInit", "새 프로젝트 초기화", "프로젝트 폴더 만들어줘", project setup.
argument-hint: "<PROJECT_CODE> <PROJECT_TITLE> [EP##] [S##]"
allowed-tools: Bash, Read, Write
---

# GenInit

새 프로젝트를 시작할 때 한 번 실행. 폴더 구조와 빈 템플릿 파일을 자동 생성한다.  
소스 파일(PDF·영상·콘티이미지)이 감지되면 MD 파일을 자동으로 채운다.

## Step 1 — 인자 파싱 및 현재 경로 확인

- 첫 번째 인자: PROJECT_CODE (예: `GRB`, `AWK`, `BLU`)
- 두 번째 인자 이후: PROJECT_TITLE (예: `고래별`, `어웨이크`)
- 선택 인자: EP 번호 (예: `EP01`), SEQ 번호 (예: `S41`)
  - 없으면 기본값 EP01, S01 사용

```bash
pwd
```

현재 디렉토리가 프로젝트 루트인지 확인하고 사용자에게 알림.

config.md가 이미 있으면 읽어서 PROJECT_CODE, PROJECT_TITLE, type 파악 후 인자 없어도 진행:
```bash
ls config.md 2>/dev/null | head -1
```

## Step 2 — 프로젝트 유형 선택

config.md에서 `type:` 이미 있으면 스킵.

없으면 사용자에게 물어봄:

```
프로젝트 유형을 선택하세요:
1. 드라마 (EP01, EP02... 에피소드 구조)
2. 영화 (EP 폴더 없이 단일 구조)
```

응답에 따라 TYPE = `drama` 또는 `movie` 로 설정.

## Step 3 — 폴더 및 빈 파일 생성

**드라마 (TYPE=drama):**

```bash
mkdir -p {EP}/Conti/{SEQ} {EP}/Image/{SEQ} {EP}/Video/{SEQ} {EP}/character
touch {EP}/Conti/{SEQ}/shotlist_{SEQ}.md
touch {EP}/Image/{SEQ}/Sceneprompt.md
touch {EP}/Image/{SEQ}/Shotprompt.md
touch {EP}/character/Character.md
```

**영화 (TYPE=movie):**

```bash
mkdir -p Conti/{SEQ} Image/{SEQ} Video/{SEQ} character
touch Conti/{SEQ}/shotlist_{SEQ}.md
touch Image/{SEQ}/Sceneprompt.md
touch Image/{SEQ}/Shotprompt.md
touch character/Character.md
```

이미 존재하는 파일은 `touch` 해도 내용 유지됨 — 안전.

## Step 4 — config.md 생성

이미 존재하면 스킵 (덮어쓰지 않음).

```bash
ls config.md 2>/dev/null | head -1
```

없으면 유형에 따라 생성:

**드라마:**
```markdown
# {PROJECT_TITLE} — Config

project_code: {PROJECT_CODE}
project_title: {PROJECT_TITLE}
type: drama

## Episode Mapping
| Sequence | Episode |
|---|---|
| {SEQ} | {EP} |
```

**영화:**
```markdown
# {PROJECT_TITLE} — Config

project_code: {PROJECT_CODE}
project_title: {PROJECT_TITLE}
type: movie

## Sequences
| Sequence |
|---|
| {SEQ} |
```

## Step 5 — Projectprompt.md 생성

이미 존재하면 스킵.

```bash
ls Projectprompt.md 2>/dev/null | head -1
```

없으면 생성 (유형 무관 동일):

```markdown
# {PROJECT_TITLE} — Master Projectprompt

## Project Identity
(장르, 세계관, 핵심 주제 2~3문장)

---

## Universal Rules (All Scenes)
- (스타일 규칙)

---

## 주요 공간 #1 (공간명)
**Color & Light:** 
**Texture & Detail:** 
**Motion Style for i2v:** 
**Mood:** 
```

## Step 6 — 소스 파일 감지

폴더 구조 생성 후 소스 파일을 탐색한다.

```bash
# PDF 탐색
find . -maxdepth 2 -name "*.pdf" 2>/dev/null

# 영상 탐색
find . -maxdepth 2 \( -name "*.mp4" -o -name "*.mov" -o -name "*.avi" -o -name "*.MP4" -o -name "*.MOV" \) 2>/dev/null

# 이미지 탐색 (생성 결과 파일 제외)
find . -maxdepth 4 \( -name "*.jpg" -o -name "*.JPG" -o -name "*.jpeg" \) 2>/dev/null | grep -v "_v[0-9]"
```

**감지 우선순위:** PDF > 영상 > 콘티이미지

소스 없으면:
```
📁 폴더 구조 생성 완료.
소스 파일(PDF / 영상 / 콘티이미지)을 프로젝트 폴더에 넣고 /GenInit을 다시 실행하면 MD를 자동으로 채워드립니다.
```
→ Step 9(완료 보고)로 이동

소스 있으면 → Step 7로

## Step 7 — 소스 타입별 분석

### PDF 모드

Read 툴로 PDF를 읽는다.

시퀀스 헤딩 찾기:
```
41. 장소명 -D/-N
또는
S#41 장소명
```

**7-A. 등장인물 추출 → Character.md**

이미 내용이 있으면 스킵.

PDF 전체에서 등장인물 이름, 외모 묘사, 의상 추출:
```markdown
{이름} : {외모 묘사}. {의상 묘사}.
```

파일 위치: `{EP}/character/Character.md`

**7-B. 씬 지문 분석 → Sceneprompt.md**

이미 내용이 있으면 스킵.

해당 시퀀스 지문(ト書き)에서 추출, 4줄 형식:
```
Line 1: 스타일 (완전 실사 시네마틱 영상) + 시대 + 시간대
Line 2: 장소 + 주요 액션 요약
Line 3: 카메라 스타일 + 색조 + 그레인
Line 4: 시대 고증 핵심 항목
```

파일 위치: `{EP}/Image/{SEQ}/Sceneprompt.md`

**7-C. 샷 묘사 → Shotprompt.md**

이미 내용이 있으면 스킵.

씬에서 대표 5개 샷 선정, 번호 리스트 형식:
```
1. {카메라 포지션} — {주요 액션/움직임}. {인물 감정/표정}.
2. ...
```

파일 위치: `{EP}/Image/{SEQ}/Shotprompt.md`

**7-D. 전체 샷 분해 → shotlist_{SEQ}.md**

이미 내용이 있으면 스킵.

GenConti Step 6과 동일한 샷 분해 규칙 적용:
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

**7-E. Projectprompt.md 자동 생성**

Step 5에서 빈 템플릿으로 생성된 경우, PDF 전체를 분석해 내용 채우기:
- 장르·세계관·주요 공간·색감·조명 방향성 추출
- GenConti Step 3과 동일한 포맷

---

### 영상 모드

**7-F. 프레임 추출**

ffmpeg 설치 확인:
```bash
which ffmpeg 2>/dev/null || echo "NOT_FOUND"
```

없으면:
```
⚠️ ffmpeg이 설치되어 있지 않습니다.
설치 후 다시 실행하세요: brew install ffmpeg
```
→ 이미지 모드로 폴백 (영상만 있고 이미지도 없으면 중단)

**첫 프레임과 마지막 프레임만 추출:**
```bash
mkdir -p "{EP}/Conti/{SEQ}"
ffmpeg -i "{VIDEO_PATH}" -vframes 1 "{EP}/Conti/{SEQ}/frame_first.png" -y
ffmpeg -sseof -1 -i "{VIDEO_PATH}" -vframes 1 "{EP}/Conti/{SEQ}/frame_last.png" -y
```

**7-G. 프레임 Vision 분석**

두 프레임을 Read 툴로 읽어 vision 분석:
- 씬 시작/끝 상황·배경·분위기 파악
- 등장인물 외형 (얼굴, 의상, 체형) 추출
- 카메라 앵글·사이즈 파악

분석 결과로 7-A~D와 동일하게 4개 MD 생성.

**7-H. 프레임 → Conti 이미지로 저장**

```bash
cp "{EP}/Conti/{SEQ}/frame_first.png" "{EP}/Conti/{SEQ}/0010_v1.png"
cp "{EP}/Conti/{SEQ}/frame_last.png" "{EP}/Conti/{SEQ}/0020_v1.png"
```

---

### 콘티이미지 모드

**7-I. 이미지 Vision 분석**

감지된 이미지들을 Read 툴로 순서대로 읽어 vision 분석:
- 각 이미지에서 샷사이즈·앵글·인물·액션 추출
- 캐릭터 외형 추출 (Character.md용)

분석 결과로 7-A~D와 동일하게 MD 생성 (단, Character.md는 추정값으로 생성).

이미지들을 Conti 폴더로 복사 (이미 있으면 스킵):
```bash
cp "{SOURCE_IMAGE}" "{EP}/Conti/{SEQ}/0010_v1.png"
# ...
```

## Step 8 — 완료 보고

### 소스 있는 경우:

```
✅ 소스 감지: {파일명} ({타입: PDF/영상/콘티이미지})
✅ 시퀀스 {SEQ} 분석 완료

채워진 파일:
  {EP}/character/Character.md      ← {인물 목록}
  {EP}/Conti/{SEQ}/shotlist_{SEQ}.md ← {샷 수}샷
  {EP}/Image/{SEQ}/Sceneprompt.md
  {EP}/Image/{SEQ}/Shotprompt.md

스킵된 파일 (이미 존재):
  (해당 파일 목록 또는 없으면 생략)

다음 단계:
  /GenConti → 콘티 이미지 생성
  /GenConti2Img → 최종 씬 이미지 생성
  /GenVideo → 영상 생성
```

### 소스 없는 경우:

```
✅ {PROJECT_TITLE} ({PROJECT_CODE}) {drama/movie} 프로젝트 초기화 완료

생성된 구조:
  config.md
  Projectprompt.md       ← 프로젝트 스타일 입력 필요
  {EP}/character/Character.md
  {EP}/Conti/{SEQ}/shotlist_{SEQ}.md
  {EP}/Image/{SEQ}/Sceneprompt.md
  {EP}/Image/{SEQ}/Shotprompt.md

소스 파일(PDF / 영상 / 콘티이미지)을 폴더에 넣고 /GenInit을 다시 실행하면 위 파일들을 자동으로 채워드립니다.
```

## UX 규칙

- 사용자 언어(한국어/영어)로 응답
- 이미 내용이 있는 파일은 덮어쓰지 않고 "이미 존재함 — 스킵" 표시
- 빈 파일(0바이트)은 채워도 됨
- Character.md는 에피소드 단위 — 해당 EP에 이미 내용이 있으면 스킵
- 영상 프레임 임시 폴더(`frames/`)는 분석 후 삭제하지 않음 (사용자가 확인할 수 있도록)
