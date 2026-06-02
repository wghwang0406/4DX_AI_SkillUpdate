#!/usr/bin/env python3
"""
transition_to_single_frame.py — Shotprompt 페어(-1/-2) → 단일프레임(-1) 일괄 변환

목적
  GenVideo 의 "페어 모드"(시작 이미지 -1 + 끝 이미지 -2)로 작성된 Shotprompt 를
  "단일 프레임 모드"(-1 한 장만)로 일괄 정리한다. 페어 영상에서 단일 영상으로
  방향을 바꿀 때, Shotprompt.md 들을 수동으로 고치지 않고 한 번에 변환한다.
  in-place 로 수정하며, 변경 전 원본은 .bak 으로 백업한다.

변환 규칙
  1) `{SHOT}-2_v*.png` 같은 -2(끝) 프레임 참조 라인 → 제거
  2) `{SHOT}-1_v*.png` (시작) 프레임 참조 → 유지
  3) `0010+0020` 형태의 페어 스펙 → `0010` 으로 축약
  4) `[multi]` 태그 → 제거
  5) "pair"/"페어"/"end image"/"끝 이미지" 류 표현이 든 라인은 변경 후에도
     남아 혼란을 주지 않도록 위 패턴 기준으로만 정리 (보수적 처리)

폴더/명명 규약 (PDF 트리)
  대상 :  Image/{SEQ}/{SEQ}_{SHOT}/Shotprompt.md

사용법
  python3 transition_to_single_frame.py S41 [0010] [--dry-run]
    샷 생략 시 해당 시퀀스의 모든 Shotprompt.md 변환
    --dry-run : 파일을 고치지 않고 변경 예정 내용(diff)만 출력

의존성
  - 순수 stdlib (외부 의존성 없음)
"""

import argparse
import difflib
import glob
import pathlib
import re
import sys

# -2(끝) 프레임 참조가 들어간 줄 (줄바꿈까지 제거)
RE_END_FRAME_LINE = re.compile(r"^.*-2_v\d+\.\w+.*$\n?", re.MULTILINE)
# 0010+0020 형태 페어 스펙 → 앞 샷만
RE_PAIR_SPEC = re.compile(r"\b(\d{4})\+\d{4}\b")
# [multi] 태그 (줄바꿈은 보존하도록 가로 공백만 흡수)
RE_MULTI_TAG = re.compile(r"[ \t]*\[multi\][ \t]*", re.IGNORECASE)


def normalize_seq(seq_id: str) -> str:
    seq_id = seq_id.strip()
    if seq_id.isdigit():
        return f"S{int(seq_id):02d}"
    return seq_id if seq_id.upper().startswith("S") else f"S{seq_id}"


def pad_shot(shot: str) -> str:
    return f"{int(shot):04d}" if str(shot).isdigit() else str(shot)


def project_root() -> pathlib.Path:
    p = pathlib.Path(__file__).resolve().parent
    for cand in [p, *p.parents]:
        if (cand / "config.md").exists():
            return cand
    return p


def convert(text: str) -> str:
    # 1) -2 프레임 참조 라인 제거
    text = RE_END_FRAME_LINE.sub("", text)
    # 3) 페어 스펙 축약
    text = RE_PAIR_SPEC.sub(r"\1", text)
    # 4) [multi] 태그 제거
    text = RE_MULTI_TAG.sub(" ", text)
    # 줄 끝 공백 제거 + 빈 줄 3개 이상 → 2개로 정리
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def target_files(root: pathlib.Path, seq: str, shot: str) -> list:
    if shot:
        f = root / "Image" / seq / f"{seq}_{shot}" / "Shotprompt.md"
        return [f] if f.exists() else []
    files = glob.glob(str(root / "Image" / seq / f"{seq}_*" / "Shotprompt.md"))
    # 시퀀스 공용 Shotprompt.md 도 있으면 포함
    common = root / "Image" / seq / "Shotprompt.md"
    if common.exists():
        files.append(str(common))
    return sorted(pathlib.Path(f) for f in files)


def main():
    p = argparse.ArgumentParser(
        prog="transition_to_single_frame.py",
        description="Shotprompt 페어(-1/-2) → 단일프레임(-1) 일괄 변환 (in-place)",
    )
    p.add_argument("seq_id", help="시퀀스 ID (예: S41)")
    p.add_argument("shot", nargs="?", default="", help="샷 번호 (생략 시 시퀀스 전체)")
    p.add_argument("--dry-run", action="store_true", help="파일을 고치지 않고 변경 diff만 출력")
    args = p.parse_args()

    root = project_root()
    seq = normalize_seq(args.seq_id)
    shot = pad_shot(args.shot) if args.shot else ""

    files = target_files(root, seq, shot)
    if not files:
        print(f"ERROR: 변환할 Shotprompt.md 를 찾지 못했습니다 ({seq} {shot or '전체'}).",
              file=sys.stderr)
        return 1

    changed = unchanged = 0
    for f in files:
        original = f.read_text(encoding="utf-8")
        converted = convert(original)
        rel = f.relative_to(root)
        if converted == original:
            print(f"NOCHANGE:{rel}", flush=True)
            unchanged += 1
            continue
        if args.dry_run:
            print(f"--- DIFF:{rel} ---", flush=True)
            diff = difflib.unified_diff(
                original.splitlines(), converted.splitlines(),
                fromfile=str(rel), tofile=f"{rel} (변환후)", lineterm="",
            )
            for line in diff:
                print(line, flush=True)
            changed += 1
            continue
        # 백업 후 in-place 저장
        f.with_suffix(".md.bak").write_text(original, encoding="utf-8")
        f.write_text(converted, encoding="utf-8")
        print(f"CONVERTED:{rel} (백업: {rel}.bak)", flush=True)
        changed += 1

    verb = "변경 예정" if args.dry_run else "변환"
    print(f"DONE: {verb} {changed}개 / 변경없음 {unchanged}개", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
