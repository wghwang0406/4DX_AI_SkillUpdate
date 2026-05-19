---
version: 4.0.0
name: GenInit
description: |
  소스 파일(PDF/영상/콘티이미지)을 감지해 Character.md, Sceneprompt.md,
  Shotprompt.md, shotlist를 자동으로 채운다.
  폴더 구조는 별도 처리 — 이 스킬은 분석·채우기만 담당.
  Use when: "GenInit", "프롬프트 파일 채워줘", "소스 분석해줘", source-to-md.
argument-hint: "[EP##] [S##]"
allowed-tools: Bash, Read, Write
---

# GenInit

소스 파일(PDF·영상·콘티이미지)을 분석해 MD 프롬프트 파일을 자동으로 채운다.  
폴더 구조 생성은 하지 않음 — 이미 존재하는 구조에서만 동작한다.

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

## Step 2 — 대상 경로 존재 확인

폴더를 만들지 않음. 실제 존재하는지만 확인:

```bash
ls {EP}/Image/{SEQ}/ 2>/dev/null || echo "PATH_MISSING"
ls {EP}/Conti/{SEQ}/ 2>/dev/null || echo "PATH_MISSING"
ls {EP}/character/ 2>/dev/null || echo "PATH_MISSING"
```

경로 없으면:
```
⚠️ {EP}/Image/{SEQ}/ 폴더가 없습니다.
폴더 구조를 먼저 만들어주세요.
```
→ 중단

## Step 3 — 소스 파일 감지

우선순위: **PDF > 영상 > 콘티이미지**

```bash
# PDF (있으면 다른 소스 무시하고 PDF 모드로)
find . -maxdepth 2 -name "*.pdf" 2>/dev/null

# 영상
find . -maxdepth 2 \( -name "*.mp4" -o -name "*.mov" -o -name "*.MOV" -o -name "*.MP4" \) 2>/dev/null

# 콘티 이미지 — PDF가 없을 때만:
# 1순위: Conti/{SEQ}/ 폴더 안 기존 이미지 (_v# 제외)
find "{EP}/Conti/{SEQ}" -maxdepth 1 \( -name "*.png" -o -name "*.PNG" -o -name "*.jpg" -o -name "*.JPG" -o -name "*.jpeg" \) 2>/dev/null | grep -v "_v[0-9]" | sort -V

# 2순위: 루트 근처 외부 이미지 (Image/, character/ 제외, _v# 제외)
find . -maxdepth 4 \( -name "*.jpg" -o -name "*.JPG" -o -name "*.jpeg" -o -name "*.png" -o -name "*.PNG" \) 2>/dev/null | grep -v "_v[0-9]" | grep -v "/Image/" | grep -v "/character/"
```

**영상·이미지 소스일 때**: PDF 없으면 Conti/{SEQ}/ 폴더를 먼저 확인.  
Conti 폴더에 이미지가 있으면 그걸 소스로 사용 — 루트에 별도 파일 불필요.

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

**7-A. 등장인물 추출 → Character.md**

비어있으면: PDF 전체에서 등장인물 이름·외모·의상 추출.

```markdown
{이름} : {외모 묘사}. {의상 묘사}.
```

파일 위치: `{EP}/character/Character.md`

**7-B. 씬 지문 분석 → Sceneprompt.md**

비어있으면: 해당 시퀀스 지문(ト書き) 추출, 4줄 형식:

```
Line 1: 스타일 (완전 실사 시네마틱 영상) + 시대 + 시간대
Line 2: 장소 + 주요 액션 요약
Line 3: 카메라 스타일 + 색조 + 그레인
Line 4: 시대 고증 핵심 항목
```

파일 위치: `{EP}/Image/{SEQ}/Sceneprompt.md`

**7-C. 샷 묘사 → Shotprompt.md**

비어있으면: 씬에서 대표 5개 샷 선정, 번호 리스트 형식:

```
1. {카메라 포지션} — {주요 액션/움직임}. {인물 감정/표정}.
2. ...
```

파일 위치: `{EP}/Image/{SEQ}/Shotprompt.md`

**7-D. 전체 샷 분해 → shotlist_{SEQ}.md**

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

**7-E. Projectprompt.md**

비어있으면: PDF 전체 분석해 장르·세계관·주요 공간·색감·조명 방향성 채우기.

---

### 영상 모드

**ffmpeg 확인:**

```bash
which ffmpeg 2>/dev/null || echo "NOT_FOUND"
```

없으면:
```
⚠️ ffmpeg이 설치되어 있지 않습니다. brew install ffmpeg
```
→ 중단

**첫 프레임·마지막 프레임 추출:**

```bash
ffmpeg -i "{VIDEO_PATH}" -vframes 1 "{EP}/Conti/{SEQ}/frame_first.png" -y
ffmpeg -sseof -1 -i "{VIDEO_PATH}" -vframes 1 "{EP}/Conti/{SEQ}/frame_last.png" -y
```

두 프레임을 Read 툴로 Vision 분석 → 씬 상황·배경·인물 외형·카메라 앵글 파악  
→ 7-A~D와 동일하게 4개 MD 생성.

---

### 콘티이미지 모드

감지된 jpg/png 이미지를 Read 툴로 순서대로 Vision 분석:
- 각 이미지에서 샷사이즈·앵글·인물·액션 추출
- 캐릭터 외형 추출 (Character.md용, 추정값)

→ 7-A~D와 동일하게 4개 MD 생성.

---

## Step 5 — 완료 보고

```
✅ 소스 감지: {파일명} ({타입: PDF/영상/콘티이미지})
✅ 시퀀스 {SEQ} 분석 완료

채워진 파일:
  {EP}/character/Character.md
  {EP}/Conti/{SEQ}/shotlist_{SEQ}.md   ← {N}샷
  {EP}/Image/{SEQ}/Sceneprompt.md
  {EP}/Image/{SEQ}/Shotprompt.md

스킵 (이미 존재):
  (해당 파일 목록 또는 없으면 생략)

다음 단계:
  /GenConti → 콘티 이미지 생성
  /GenConti2Img → 최종 씬 이미지 생성
  /GenVideo → 영상 생성
```

## UX 규칙

- 사용자 언어(한국어/영어)로 응답
- 이미 내용이 있는 파일은 절대 덮어쓰지 않고 "스킵" 표시
- 빈 파일(0바이트)은 채워도 됨
- Character.md는 에피소드 단위 — 해당 EP에 이미 내용이 있으면 스킵
