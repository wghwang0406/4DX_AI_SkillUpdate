# 4DX AI Skills — Higgsfield 기반 AI 영상 제작 스킬 묶음

Claude Code용 스킬 모음. 시나리오(PDF)에서 콘티 → 씬 이미지 → 영상까지
[Higgsfield](https://higgsfield.ai) CLI로 잇는다.

```
GenSetup → GenConti → GenImg2Img → GenConti2Img → GenVideo
```

## 설치

```bash
# 1) 스킬 배치
git clone https://github.com/wghwang0406/4DX_AI_SkillUpdate.git ~/.claude/skills

# 2) 전역 지침 배치 (스킬들이 이 파일을 참조한다)
cp ~/.claude/skills/CLAUDE.md ~/.claude/CLAUDE.md

# 3) Higgsfield CLI
npm install -g @higgsfield/cli
higgsfield auth login
```

이미 `~/.claude/skills`를 쓰고 있으면 클론 대신 그 안에서 `git pull` 한다.

## 업데이트 — 2단계다. 1단계만 하면 반쪽이다

```bash
# 1) 스킬 본체
cd ~/.claude/skills && git pull
cp ~/.claude/skills/CLAUDE.md ~/.claude/CLAUDE.md
```

여기까지 하면 `SKILL.md`·`CLAUDE.md`·원문 규격 3종은 최신이 된다.
**파이썬 툴킷은 아직 옛날 것이다.**

`GenSetup`이 프로젝트 루트에 툴킷을 `cp -n`으로 복사하는데, `-n`은 **이미 있으면
덮지 않는다.** 프로젝트마다 처음 복사된 시점의 사본이 얼어붙어 있고, `git pull`은
그 사본을 건드리지 않는다. 버그 수정이 기존 프로젝트에 안 들어가는 이유다.

```bash
# 2) 프로젝트별 사본 갱신 — config.md가 있는 폴더에서
SHARED=~/.claude/skills/_shared/scripts/core
cp "$SHARED"/{runner,cache,models}.py .
mkdir -p scripts && cp "$SHARED"/{gen_helper,genconti2img_minimal}.py scripts/
```

- 프로젝트를 여러 개 쓰면 **폴더마다** 돌린다.
- `.cache.json`·MD·이미지는 건드리지 않는다. 덮이는 건 툴킷 `.py` 5개뿐이다.
- 세 파일은 서로 맞물려 있으니 **같이** 복사한다 (`runner`만 새 것이면 import가 어긋난다).
- 프로젝트 사본을 손으로 고쳐 뒀다면 그 수정은 사라진다. 먼저 `diff`로 확인한다.

동작 확인 — 모델 표가 현재 Higgsfield CLI와 맞는지 본다 (크레딧 0):

```bash
python3 ~/.claude/skills/_shared/scripts/core/models.py --check
# → "CAPS가 CLI와 일치합니다."
```

## 원문 규격 스킬 3종 — 함께 들어 있다

`Cinedance` · `Lira` · `Acting`은 Gen* 스킬이 프롬프트를 쓸 때 **읽는 규격 원문**이다.
힉스필드가 공개한 배포본을 무손실로 담았다 (출처는 [ATTRIBUTION.md](ATTRIBUTION.md)).

```
~/.claude/skills/Cinedance/SKILL.md    영상 프롬프트 12섹션 규격
~/.claude/skills/Lira/SKILL.md         이미지 프롬프트 4-D + 모델 라우팅
~/.claude/skills/Acting/SKILL.md       캐릭터 연기 작성 규격
```

**지워도 스킬은 전부 동작한다.** 다만 프롬프트를 쓸 때 참조할 원문이 없어 품질이
떨어진다 — 에러가 안 나는 종류의 저하라 알아채기 어렵다. `CLAUDE.md`의
**프롬프트 규칙 10개**가 세 원문에서 뽑은 요약이라 최소한의 대체는 된다.

## 스킬

| 스킬 | 하는 일 | 인자 |
|---|---|---|
| `GenSetup` | 소스(PDF/영상/콘티) 분석 → MD 프롬프트 + 에셋 라이브러리 | `[EP##] [S##]` |
| `GenConti` | 시나리오 → 콘티 이미지 배치 생성 | `<PDF> <SEQ> [sketch\|cinematic]` |
| `GenT2I` | 텍스트 → 이미지 | `<모델> <프롬프트>` |
| `GenImg2Img` | 레퍼런스 이미지 → 이미지 | `<모델> <프롬프트>` |
| `GenConti2Img` | 콘티 → 최종 씬 이미지 배치 | `<SEQ> [모델]` |
| `GenVideo` | 이미지 → 영상 (싱글/배치) | `<SEQ> <샷> [모델]` |

## 프로젝트 구조

스킬은 `config.md`가 있는 디렉토리를 프로젝트 루트로 잡는다.

```
{프로젝트}/
  config.md                 project_code + Episode Mapping (필수)
  Projectprompt.md          스타일 앵커 — 프로젝트 상수
  runner.py, cache.py       GenSetup이 자동 복사 (cp -n, 안 덮어씀)
  models.py
  {EP}/Conti/{SEQ}/         콘티
  {EP}/Image/{SEQ}/         씬 이미지
  {EP}/Video/{SEQ}/         영상
  {EP}/character/{char,loc,prop}/
```

`config.md` 최소 형태:

```markdown
project_code: MYPROJ
project_title: 작품명

## Sequences
| Sequence | Episode |
|---|---|
| S01 | EP01 |
```

> Episode Mapping의 두 번째 열은 **`EP`로 시작해야** 한다. 아니면 러너가
> "Episode mapping not found"로 중단한다.

## 모델

단축명 정본은 [`_shared/scripts/core/models.py`](_shared/scripts/core/models.py)다.
문서보다 이 파일이 먼저다.

| 종류 | 단축명 |
|---|---|
| 이미지 | `gpt` `nano` `cinema` `soul` `soulcine` `seed` |
| 영상 | `kling` `seedance` `seedance25` |
| 업스케일 | `upscale` `topaz` |

**모델마다 받는 품질 플래그가 다르다.** 코드에서는 `models.image_flags()`가 알아서
붙이지만, CLI를 직접 칠 때는 주의한다:

| 모델 | 붙이는 것 |
|---|---|
| `gpt_image_2` | `--quality low\|medium\|high` + `--resolution 1k\|2k\|4k` |
| `nano_banana_2` · `cinematic_studio_2_5` | `--resolution` — **`--quality` 없음** |
| `text2image_soul_v2` · `soul_cinematic` | `--quality 1.5k\|2k` — **`--resolution` 없음** |
| `seedream_v4_5` | `--quality basic\|high` |

21:9가 **없는** 모델: `gpt_image_2`, `text2image_soul_v2`, `kling3_0`.

## 요구사항

- Claude Code
- Python 3.9+ (표준 라이브러리만 쓴다)
- Higgsfield CLI + 계정
- ffmpeg (영상 소스에서 프레임 추출할 때만)

## 라이선스

`Gen*` 스킬 정의와 `_shared/` 파이썬 툴킷은 자유롭게 쓰고 고쳐도 된다.
`Cinedance` · `Lira` · `Acting`은 **내 저작물이 아니다** — 힉스필드 배포본을 그대로
담은 것이라 그쪽 조건을 따른다. [ATTRIBUTION.md](ATTRIBUTION.md) 참고.
