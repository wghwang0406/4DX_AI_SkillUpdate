# Higgsfield Skill Reference

스킬 사용 시 이 파일을 먼저 참조한다. 원본 SKILL.md 파일은 재분석하지 않는다.
모든 프로젝트에서 자동으로 로드된다 (`~/.claude/CLAUDE.md`).

---

## 워크플로우 순서

```
GenSetup → GenConti → GenImg2Img → GenConti2Img → GenVideo
```

## 원문 규격 스킬 (참조 전용, 직접 호출도 가능)

프롬프트를 쓸 때 **요약본이 아니라 이 원문을 읽는다.** 힉스필드 Hell Grind 배포본 무손실.

| 스킬 | 무엇 | 누가 읽나 |
|---|---|---|
| `Cinedance` | 영상 프롬프트 12섹션 + 대각 화각 옵틱 + 블로킹·물리·조명 락 | GenVideo, GenSetup |
| `Lira` | 이미지 프롬프트 4-D + 모델 라우팅 + 시트/장소/소품/편집 템플릿 | GenSetup, GenConti2Img, GenConti, GenT2I, GenImg2Img |
| `Acting` | 캐릭터 연기 — 마스터 프로필, eye life, states not transitions | GenSetup, GenVideo |

---

## 공통 규칙

- **파일명:** `{SEQ}_{SHOT}_v{N}.{ext}` (예: `S41_0010_v1.png`)
- **모델 단축명:** `gpt` = gpt_image_2 / `nano` = nano_banana_2 / `cinema` = cinematic_studio_2_5
  / `soul` = text2image_soul_v2 (Soul 2.0) / `soulcine` = soul_cinematic (Soul Cinema)
  / `seed` = seedream_v4_5 (텍스처 패스 전용)

## 이미지 모델 라우팅 (Lira, CLI 확인 완료 2026-08-10)

| 작업 | 모델 | ID | 근거 |
|---|---|---|---|
| 등장체 시트·초상·캐스팅 | Soul 2.0 | `text2image_soul_v2` | Soul ID(`custom_reference_id`)로 얼굴 고정. **21:9 없음** — 와이드 인물은 Soul Cinema로 |
| 배경·환경·establishing·필름 스틸 | Soul Cinema | `soul_cinematic` | 21:9 지원, Soul ID 인물을 씬에 넣을 수 있음 |
| 소품·제품형 오브젝트 | NBP / GPT Image 2 | `nano_banana_2` / `gpt_image_2` | 실사 제품 컨텍스트가 강함 |
| **프레임 편집 — 언제나 1순위** | Nano Banana Pro | `nano_banana_2` | 원본 후처리. 최대 4K, 레퍼런스 14장, 프레임 내 문자 렌더링 최상 |
| 뭉개진 AI 텍스처 되살리기 (피부·직물·표면) | Seedream 4.5 | `seedream_v4_5` | **텍스처 패스 전용.** 국소 편집에 절대 쓰지 않는다 |
| 최후의 미세 국소 편집 · **장소 뷰 변경** | GPT Image 2 | `gpt_image_2` | 전역은 지저분해지지만 국소는 강함 |
| 캐릭터 시트 자동 생성 (UI 도구) | Soul Cast | `soul_cast` | `prompt`가 object + `budget` — UI에서 파라미터를 잡는 도구라 스킬에서 직접 호출하지 않음 |

**Soul ID:** `higgsfield soul-id create/list/wait`로 만든다. 정체성은 **프로즈가 아니라 Soul ID**가
담당하고 프로즈 앵커는 보강일 뿐이다. 만든 게 없으면 시트 레퍼런스 + 앵커에만 의존하게 된다.

편집 순서는 고정: **NBP → Seedream(텍스처만) → GPT Image 2(최후)**.
프레임을 다시 짜야 하는 건 편집이 아니다 → Soul 계열로 재생성.
- **폴더 구조:** `{EP}/Image/{SEQ}/` / `{EP}/Conti/{SEQ}/` / `{EP}/character/{char,loc,prop}/`
- **config.md:** `project_code` + Episode Mapping 필수 — 모든 스킬에서 참조
- **캐시:** `runner.py` + `.cache.json` — 분석 완료 샷 재분석 스킵 (GenVideo, GenConti2Img)

---

## 프롬프트 규칙 (원문 스킬: Cinedance / Lira / Acting)

프롬프트를 쓰거나 MD 초안을 채울 때 **상세는 해당 원문 스킬을 Read해서 따른다.**
영상 → `Cinedance` / 이미지 → `Lira` / 연기 → `Acting`.
아래는 세 파일에서 뽑은 공통 항목이고, 요약본으로 원문을 대체하지 않는다.

1. **레퍼런스 계층.** 정체성 ref = 얼굴·체형·비율·의상 / 장소 ref = 지리·재질·랜드마크·조명
   방향 (**구도·앵글·프레이밍 상속 금지**) / 소품 ref = 형태·스케일·재질·손 접촉·상태.
   스타일 ref는 정체성·블로킹·옵틱·조명을 덮지 못한다. 프로즈로 레퍼런스를 덮어쓰지 않는다.
2. **공간.** LOCATION MAP은 장면당 한 번 쓰고 모든 컷에 붙인다. 블로킹은 측정 가능하게
   (`within 1 meter`, `hand on the handle`). `near`·`around`·`beside`·`nearby` 금지.
   **몸 방향과 시선 방향은 따로** 쓴다.
3. **첫 프레임.** 필요한 인물이 첫 프레임에 이미 다 들어가 있다.
   빈 establishing 프레임 금지, 인물 등장 지연 금지.
4. **옵틱.** mm·f값·ISO·렌즈 브랜드를 주요 제어로 쓰지 않는다. **대각 화각**
   (47° / 84° / 107° / 29° / 18° / 8°) + 관찰 가능한 결과로 쓴다.
   콘텐츠 타입과 화각을 맞추고, 한 비트에 다른 콘텐츠 클래스를 섞지 않는다.
   화각별 언어 뱅크와 렌즈 결정 트리는 `Cinedance` 원문에 있다.
5. **연기.** 감정 표시가 아니라 **압박 속의 행동.** 목적(파트너를 향한 동사) + 장애·스테이크
   + 전술 + 비트 변화 2~4개(행동으로 보이게) + 서브텍스트.
   눈의 생명(사케이드·깜빡임 질·캐치라이트)은 필수. **상태를 쓰고 전환을 쓰지 않는다.**
   Voice 프롬프트는 캐릭터당 고정, 대사가 있으면 verbatim.
6. **긍정 우선, 국소 negative 허용.** 생성 프롬프트에선 원하는 것을 쓴다
   (`clean dry skin`, `empty deserted street`). 편집 프롬프트에선 제거가 합법이되
   **채울 것을 함께** 쓴다. 거대 NEGATIVE 블록은 기본 생략하고 국소 인라인 락을 쓴다.
7. **상수는 한 곳에.** 스타일 앵커 = 프로젝트 / LOCATION MAP = 시퀀스 /
   외형 설명글·연기 마스터 프로필 = `Character.md`. 프롬프트 본문엔 **@태그만** 쓴다.
   한 곳만 고치면 전체 컷에 반영돼야 한다.
8. **비대해지지 않게.** 정밀함이 장황함을 이긴다 (이미지 ≤1500–2000자).
   자연스러운 산문으로 쓰고 키워드 스택(`4k, masterpiece, trending`)은 쓰지 않는다.
   aspect ratio·resolution은 **플랫폼 파라미터** — 프롬프트 텍스트에 넣지 않는다.
9. **실존 인물 이름·IP·브랜드 금지.** 단, **나이는 캐릭터 앵커에 쓴다** —
   CINEDANCE 공식이 요구한다: `@TAG: age + role/body type + current state + 시각 앵커 +
   행동에 필요한 소품/신체 상태. 100% matches the reference.`
10. **상태가 바뀌면 별개 에셋.** 젖음·손상·환복은 각각 다른 @태그, 장소도 낮·밤·비가 각각.

> ⚠️ 널리 도는 한국어 요약글에는 위와 어긋나는 항목이 있다. 원문 기준으로는
> "정면 전신에서 머리 제거"·"시트는 평평한 조명"·"나이 언급 금지"·"첫 1초는 빈 와이드
> establishing"이 **모두 틀렸다.** 원문이 기준이다.

---

## 스킬별 요약

### GenSetup (v5.2.0)
**목적:** 소스 파일 분석 → MD 프롬프트 파일 + **에셋 라이브러리**(등장체/배경/소품) 생성 (구 GenInit)

**인자:** `[EP##] [S##]` (없으면 config.md 첫 번째 매핑 사용)

**소스 우선순위:** PDF > 샷단위영상(`0010_v1.mp4`) > 시퀀스영상 > 콘티이미지

**생성 파일:**
- `Projectprompt.md` ← **신규 프로젝트는 항상 비어있음, GenSetup이 최초 실행 시 자동 생성**
- `{EP}/character/Character.md`
- `{EP}/Image/{SEQ}/Sceneprompt.md`
- `{EP}/Image/{SEQ}/Shotprompt.md`
- `{EP}/Conti/{SEQ}/shotlist_{SEQ}.md`

**에셋 라이브러리:** `{EP}/character/{char,loc,prop}/`
- 등장체(char) = 인물·동물·크리처. Lira **3패널 시트**(정면 전신 / 후면 전신 / 클로즈업 초상) 정본 1장 + 파생 3장
- 배경(loc) 4뷰: `wide` / `34` / `top` / `detail` — `top`은 레퍼런스로 안 물리고 LOCATION MAP 근거로만
- 소품(prop) 3뷰: `top` / `34` / `detail`
- 등장체·소품 시트는 **무채색 배경 + soft directional 조명**, 배경 에셋은 반대로 **시네마틱**

**규칙:**
- 이미 내용 있는 파일은 절대 덮어쓰지 않음 (비어있는 파일만 채움)
- 영상 모드: ffmpeg으로 첫 프레임 추출 → `{SEQ}_{SHOT}_v1.png`
- 에셋 생성 전 **분류·목록·총 장수** 확인 후 승인받고 생성
- 일관성 검증은 **기존 이미지 vision 대조, 추가 생성 0장**. 실패하면 모델이 아니라 **앵커(설명글)를 고침**
- Lira 금칙어: `character reference sheet` / `painterly` / 시트에 `rule of thirds`
- 모든 MD 파일은 한국어 (영문 앵커·마스터 프로필·Voice는 예외)

---

### GenConti (v1.2.0)
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

### GenImg2Img (v1.2.0)
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

### GenConti2Img (v1.4.0)
**목적:** 콘티 이미지 → 최종 씬 이미지 배치 생성

**인자:** `<SEQ_ID> [gpt|nano|cinema]` (기본: gpt)

**입력:** `{EP}/Conti/{SEQ}/` 콘티 이미지 + `shotlist_{SEQ}.md`

**출력:** `{EP}/Image/{SEQ}/{SEQ}_{SHOT}_v{N}.png`

**자동 보완:**
- Sceneprompt/Shotprompt 비어있으면 콘티 분석해 자동 채움
- Background.png 없으면 Sceneprompt 기반 자동 생성

**Vision 분석 3가지만:** 샷사이즈 / 카메라앵글 / **표정(감정어 아닌 근육의 일)**

**샷 사이즈별 뷰 자동 선택:** EWS·WS→`loc_wide`+`char_front` / MS·OTS→`loc_34`+`char_front` / CU·ECU→`loc_detail`+`char_face`

**프롬프트 금지:** 캐릭터 외형(머리색·의상 등) 기술 금지 → 캐릭터 시트 레퍼런스가 담당.
스타일 문장 직접 박기 금지 → Projectprompt에서 가져옴 (상수)

**러너 위임:** `python3 runner.py genconti2img {SEQ_ID} all --model {model}`

---

### GenVideo (v1.4.0)
**목적:** 이미지 → 영상 생성 (싱글/배치)

**인자:** `<SEQ_ID> <SHOT_SPEC> [seedance]`

**SHOT_SPEC 형식:**
- `0010` : 단일 샷 / `0010-0030` : 범위 (10단위 확장) / `all` : 폴더 전체

**샷 이미지 두 가지 (v1.4.0):**
- **순서 키프레임** `{SEQ}_{SHOT}-1_v*.png`, `-2`, `-3`… — 숫자가 시간 순서, 개수 무제한
- **레퍼런스 폴더** `{SEQ}_{SHOT}_ref/` — 순서 없음, 무조건 레퍼런스, 필요한 샷에만 직접 생성
- 키프레임 없으면 `{SEQ}_{SHOT}_v*.png` 한 장이 시작 프레임. 둘은 같이 써도 됨
- 러너가 `find_shot_media()`로 디스크에서 직접 찾음 — 캐시에 경로를 적을 필요 없음

**모델:** Kling 3.0 기본 / `seedance` 입력 시 Seedance 2.0

**CLI 매핑:** 키프레임 1장→`--start-image` / 2장→`--start-image`+`--end-image` /
3장+→`--start-image`+중간 `--image`+`--end-image` / 레퍼런스→전부 `--image`

**모델 제약 (`model get`으로 확인):**
| | Kling 3.0 | Seedance 2.0 |
|---|---|---|
| 레퍼런스 이미지 | **없음** (파라미터 자체가 없음) | `image_references` |
| 이미지 총 상한 | 2장 (start/end) | **9장** (start·end 포함) |

**자동 전환:** 키프레임 3장+ & Kling 기본값 → Seedance로 전환.
모델을 명시하면 전환 안 하고 "첫/끝 2장만 사용" 경고. Kling+레퍼런스 → 레퍼런스 제외 경고

**`[multi]` 태그 폐지:** `--multi_shots`는 Kling에 없는 파라미터라 실패한다.
멀티샷은 **프롬프트 FORMAT MODE**로 만들고, 부를 때 한국어로 지시한다
(`컷으로` / `멀티샷으로` / `한 테이크로`). 지시가 없으면 키프레임을 vision 비교해 자동 판정.
**컷 지시는 절대 모델을 바꾸지 않는다.** 기존 `[multi]`는 "컷으로"로 읽고 넘어감

**프롬프트 구성:** 모델은 영문 슬롯만 채우고 runner가 **CINEDANCE 12섹션** 순서로 합성 → `--prompt`.
`scene_context` / `active_refs` / `location_map` / `first_frame` / `format_mode` / `optics` / `camera` /
`action_timing`(+`acting_en`) / `physics` / `lighting` / `style` / `audio`(+`voice_en`) / `positive_constraints`.
**상수 분리:** `style_en`→프로젝트 / `location_map_en`→시퀀스 (한 곳 고치면 전 샷 반영, 샷 재분석 불필요).
레거시 3슬롯(`scene_en`/`shot_dir_en`/`vision_en`)과 단일 `prompt`도 폴백 지원.
**옵틱은 대각 화각**(47°/84°/107°/29°/18°/8°) — mm·f값 금지. Seedance=타임코드 / Kling=Custom Multi-Shot

**빈 MD 자동 보완:** Sceneprompt/Shotprompt 비어있으면 샷 이미지 Vision 분석해 자동 생성(한국어) → 보여주고 진행. Projectprompt 제외(GenSetup 소관). 보완으로 MD 새로 쓰면 해당 샷 needs_analysis로 재판정

---

### GenT2I (v1.1.0)
**목적:** 텍스트만으로 이미지 생성

**인자:** `<gpt|nano|cinema> <프롬프트>`

**한국어 프롬프트** → 자동 영문 번역·확장 후 생성 전 출력

**기본:** 16:9, resolution 2k
