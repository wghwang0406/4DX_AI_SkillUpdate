# Higgsfield Skill Reference

스킬 사용 시 이 파일을 먼저 참조한다. 원본 SKILL.md 파일은 재분석하지 않는다.
모든 프로젝트에서 자동으로 로드된다 (`~/.claude/CLAUDE.md`).

---

## 워크플로우 순서

```
GenInit → GenConti → GenImg2Img → GenConti2Img → GenVideo
```

---

## 공통 규칙

- **파일명:** `{SEQ}_{SHOT}_v{N}.{ext}` (예: `S41_0010_v1.png`)
- **모델 단축명:** `gpt` = gpt_image_2 / `nano` = nano_banana_2 / `cinema` = cinematic_studio_2_5
- **폴더 구조:** `{EP}/Image/{SEQ}/` / `{EP}/Conti/{SEQ}/` / `{EP}/character/`
- **config.md:** `project_code` + Episode Mapping 필수 — 모든 스킬에서 참조
- **캐시:** `runner.py` + `.cache.json` — 분석 완료 샷 재분석 스킵 (GenVideo, GenConti2Img)

---

## 스킬별 요약

### GenInit (v5.0.0)
**목적:** 소스 파일 분석 → MD 프롬프트 파일 + 캐릭터 시트 자동 생성

**인자:** `[EP##] [S##]` (없으면 config.md 첫 번째 매핑 사용)

**소스 우선순위:** PDF > 샷단위영상(`0010_v1.mp4`) > 시퀀스영상 > 콘티이미지

**생성 파일:**
- `Projectprompt.md` ← **신규 프로젝트는 항상 비어있음, GenInit이 최초 실행 시 자동 생성**
- `{EP}/character/Character.md`
- `{EP}/Image/{SEQ}/Sceneprompt.md`
- `{EP}/Image/{SEQ}/Shotprompt.md`
- `{EP}/Conti/{SEQ}/shotlist_{SEQ}.md`

**규칙:**
- 이미 내용 있는 파일은 절대 덮어쓰지 않음 (비어있는 파일만 채움)
- 영상 모드: ffmpeg으로 첫 프레임 추출 → `{SEQ}_{SHOT}_v1.png`
- 캐릭터 시트: GPT Image 2, 목록 확인 후 사용자 승인 받고 생성
- 모든 MD 파일은 한국어로 작성

---

### GenConti (v1.1.0)
**목적:** PDF 시나리오 → 콘티(storyboard) 이미지 배치 생성

**인자:** `<PDF_PATH> <SEQ_ID> [sketch|cinematic]`
- `sketch` (기본): 흑백 연필 선화
- `cinematic`: 풀컬러 3D CG 스타일

**출력:** `{EP}/Conti/{SEQ}/{SEQ}_{SHOT}_v{N}.png`

**추적 파일:** `shotlist_{SEQ}.md` / `urls_{SEQ}.md` (꺾쇠 URL `<https://...>` 형식)

**절대 규칙:**
- 대사 있는 줄은 예외 없이 독립 샷 (뭉뚱그리거나 합치지 않음)
- **한 컷씩 생성 → 보여주기 → 사용자 OK → 다음 컷 (병렬 생성 금지)**
- 샷 분해 테이블 먼저 보여주고 사용자 승인 후 생성 시작
- Projectprompt.md 없으면 PDF 전체 분석해 자동 생성

---

### GenImg2Img (v1.1.0)
**목적:** 레퍼런스 이미지 기반 스타일 변환

**인자:** `<gpt|nano|cinema> <프롬프트>`

**이미지 입력 (둘 중 하나):**
- 방법 A: 채팅에 이미지 드래그 첨부 (우선)
- 방법 B: 메시지에 파일 경로/이름 텍스트 입력
  - 절대경로 → 그대로 사용
  - 상대경로 → 절대경로 변환
  - 파일명만 → 프로젝트 폴더에서 `find`로 탐색

**한국어 프롬프트** → 자동 영문 번역·확장 후 생성 전 출력

**기본:** 16:9, resolution 2k

---

### GenConti2Img (v1.3.0)
**목적:** 콘티 이미지 → 최종 씬 이미지 배치 생성

**인자:** `<SEQ_ID> [gpt|nano|cinema]` (기본: gpt)

**입력:** `{EP}/Conti/{SEQ}/` 콘티 이미지 + `shotlist_{SEQ}.md`

**출력:** `{EP}/Image/{SEQ}/{SEQ}_{SHOT}_v{N}.png`

**자동 보완:**
- Sceneprompt/Shotprompt 비어있으면 콘티 분석해 자동 채움
- Background.png 없으면 Sceneprompt 기반 자동 생성

**Vision 분석 3가지만:** 샷사이즈 / 카메라앵글 / 표정(감정)

**프롬프트 금지:** 캐릭터 외형(머리색·의상 등) 기술 금지 → 캐릭터 시트 레퍼런스가 담당

**러너 위임:** `python3 runner.py genconti2img {SEQ_ID} all --model {model}`

---

### GenVideo (v1.2.0)
**목적:** 이미지 → 영상 생성 (싱글/배치)

**인자:** `<SEQ_ID> <SHOT_SPEC> [seedance]`

**SHOT_SPEC 형식:**
- `0010` : 단일 샷
- `0010-0030` : 범위 (10단위 확장)
- `0010+0020` : 명시적 페어 (start+end)
- `all` : 폴더 전체

**모델:** Kling 3.0 기본 / `seedance` 입력 시 Seedance 2.0

**이미지 탐색 우선순위:** `{SEQ}_{SHOT}-1_v*.png` → `{SEQ}_{SHOT}_v*.png`

**페어 자동 감지:** `-1_v*.png` + `-2_v*.png` 둘 다 존재 시 자동

**`[multi]` 태그 (Shotprompt에서):**
- Kling + `[multi]` → 멀티샷 모드
- Seedance + `[multi]` → 앞뒤 샷 이미지 레퍼런스 추가

**프롬프트 구성:** Projectprompt + Sceneprompt + Shotprompt + Vision 분석

---

### GenT2I (v1.0.0)
**목적:** 텍스트만으로 이미지 생성

**인자:** `<gpt|nano|cinema> <프롬프트>`

**한국어 프롬프트** → 자동 영문 번역·확장 후 생성 전 출력

**기본:** 16:9, resolution 2k
