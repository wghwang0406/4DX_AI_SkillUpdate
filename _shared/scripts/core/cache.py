"""
cache.py — 캐시 매니저
순수 stdlib, Python 3.9+. 외부 의존성 없음.
"""

import hashlib
import json
import os
import pathlib
import re
import time
from typing import Optional

ROOT = pathlib.Path(__file__).parent


class CacheManager:
    CACHE_FILE = ROOT / ".cache.json"

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if self.CACHE_FILE.exists():
            try:
                return json.loads(self.CACHE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                return self._empty()
        return self._empty()

    @staticmethod
    def _empty() -> dict:
        return {
            "_version": "1.0",
            "_schema": "cache-v1",
            "_updated_at": 0.0,
            "project": {},
            "sequences": {},
        }

    def _save(self) -> None:
        self._data["_updated_at"] = time.time()
        tmp = self.CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, self.CACHE_FILE)

    # ── 파일 서명 ────────────────────────────────────────────────────────────

    @staticmethod
    def file_sig(path) -> Optional[str]:
        p = pathlib.Path(path)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            return None
        st = p.stat()
        return f"{st.st_mtime:.1f}:{st.st_size}"

    @staticmethod
    def context_hash(*sigs: Optional[str]) -> str:
        combined = ":".join(s or "missing" for s in sigs)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    # ── 프로젝트 레벨 ────────────────────────────────────────────────────────

    def is_project_valid(self) -> bool:
        p = self._data.get("project", {})
        return (
            bool(p)
            and p.get("config_sig") == self.file_sig(ROOT / "config.md")
            and p.get("projectprompt_sig") == self.file_sig(ROOT / "Projectprompt.md")
        )

    def set_project(self, config_content: dict, projectprompt_text: str) -> None:
        self._data["project"] = {
            "config_sig": self.file_sig(ROOT / "config.md"),
            "config_content": config_content,
            "projectprompt_sig": self.file_sig(ROOT / "Projectprompt.md"),
            "projectprompt_text": projectprompt_text,
        }
        self._save()

    def get_project(self) -> Optional[dict]:
        return self._data.get("project") if self.is_project_valid() else None

    # ── 시퀀스 레벨 ──────────────────────────────────────────────────────────

    def _seq_key(self, ep: str, seq: str) -> str:
        return f"{ep}/{seq}"

    def _seq(self, ep: str, seq: str) -> dict:
        k = self._seq_key(ep, seq)
        return self._data["sequences"].setdefault(k, {})

    def is_sequence_valid(self, ep: str, seq: str) -> bool:
        s = self._seq(ep, seq)
        if not s:
            return False
        sceneprompt = ROOT / ep / "Image" / seq / "Sceneprompt.md"
        shotprompt = ROOT / ep / "Image" / seq / "Shotprompt.md"
        character = ROOT / ep / "character" / "Character.md"
        return (
            s.get("sceneprompt_sig") == self.file_sig(sceneprompt)
            and s.get("shotprompt_sig") == self.file_sig(shotprompt)
            and s.get("character_sig") == self.file_sig(character)
        )

    def set_sequence(self, ep: str, seq: str, data: dict) -> None:
        self._data["sequences"].setdefault(self._seq_key(ep, seq), {}).update(data)
        self._save()

    def get_sequence(self, ep: str, seq: str) -> Optional[dict]:
        return self._seq(ep, seq) if self.is_sequence_valid(ep, seq) else None

    def invalidate_sequence(self, ep: str, seq: str) -> None:
        key = self._seq_key(ep, seq)
        if key in self._data["sequences"]:
            del self._data["sequences"][key]
            self._save()

    # ── 샷 레벨 ──────────────────────────────────────────────────────────────

    def _shot(self, ep: str, seq: str, shot: str) -> dict:
        return self._seq(ep, seq).setdefault("shots", {}).setdefault(shot, {})

    def get_shot(self, ep: str, seq: str, shot: str) -> Optional[dict]:
        return self._seq(ep, seq).get("shots", {}).get(shot)

    def is_vision_valid(self, ep: str, seq: str, shot: str) -> bool:
        s = self.get_shot(ep, seq, shot)
        if not s or not s.get("vision_text"):
            return False
        cached_sigs = s.get("image_sigs", [])
        actual_sigs = [self.file_sig(ROOT / f) for f in s.get("image_files", [])]
        return bool(cached_sigs) and cached_sigs == actual_sigs and all(actual_sigs)

    def is_prompt_valid(self, ep: str, seq: str, shot: str) -> bool:
        s = self.get_shot(ep, seq, shot)
        if not s or not s.get("prompt_sig"):
            return False
        # 레거시 단일 prompt 또는 구조화 슬롯(genvideo) 중 하나라도 있으면 유효
        has_text = bool(s.get("prompt")) or any(
            s.get(k) for k in ("scene_en", "shot_dir_en", "vision_en")
        )
        if not has_text:
            return False
        seq_data = self._seq(ep, seq)
        proj_data = self._data.get("project", {})
        expected = self.context_hash(
            proj_data.get("projectprompt_sig"),
            seq_data.get("sceneprompt_sig"),
            seq_data.get("shotprompt_sig"),
            seq_data.get("character_sig"),
            ":".join(s.get("image_sigs", [])),
        )
        return s["prompt_sig"] == expected

    def set_shot_vision(
        self,
        ep: str,
        seq: str,
        shot: str,
        vision_text: str,
        image_files: list,
        image_sigs: list,
    ) -> None:
        self._shot(ep, seq, shot).update(
            {
                "vision_text": vision_text,
                "image_files": image_files,
                "image_sigs": image_sigs,
            }
        )
        self._save()

    def set_shot_prompt(
        self,
        ep: str,
        seq: str,
        shot: str,
        prompt: str,
        workflow: str,
        **extra,
    ) -> None:
        seq_data = self._seq(ep, seq)
        proj_data = self._data.get("project", {})
        s = self._shot(ep, seq, shot)
        prompt_sig = self.context_hash(
            proj_data.get("projectprompt_sig"),
            seq_data.get("sceneprompt_sig"),
            seq_data.get("shotprompt_sig"),
            seq_data.get("character_sig"),
            ":".join(s.get("image_sigs", [])),
        )
        s.update(
            {
                "workflow": workflow,
                "prompt": prompt,
                "prompt_sig": prompt_sig,
                "prompt_assembled_at": time.time(),
                "status": s.get("status", "pending"),
                **extra,
            }
        )
        self._save()

    def set_shot_result(
        self,
        ep: str,
        seq: str,
        shot: str,
        result_url: str,
        job_id: str,
        result_local: Optional[str] = None,
    ) -> None:
        self._shot(ep, seq, shot).update(
            {
                "status": "done",
                "result_url": result_url,
                "job_id": job_id,
                "result_local": result_local,
                "generated_at": time.time(),
            }
        )
        self._save()

    def set_shot_status(self, ep: str, seq: str, shot: str, status: str) -> None:
        self._shot(ep, seq, shot)["status"] = status
        self._save()

    # ── 배치 조회 ────────────────────────────────────────────────────────────

    def cache_info(self, ep: str, seq: str, shots: list) -> dict:
        result = {
            "seq_id": seq,
            "ep": ep,
            "project_valid": self.is_project_valid(),
            "sequence_valid": self.is_sequence_valid(ep, seq),
            "shots": {},
            "summary": {},
        }
        for shot in shots:
            s = self.get_shot(ep, seq, shot)
            result["shots"][shot] = {
                "vision_cached": self.is_vision_valid(ep, seq, shot),
                "prompt_cached": self.is_prompt_valid(ep, seq, shot),
                "status": (s or {}).get("status", "unknown"),
                "result_url": (s or {}).get("result_url"),
            }
        total = len(shots)
        done = sum(1 for d in result["shots"].values() if d["status"] == "done")
        v_hit = sum(1 for d in result["shots"].values() if d["vision_cached"])
        p_hit = sum(1 for d in result["shots"].values() if d["prompt_cached"])
        result["summary"] = {
            "total": total,
            "done": done,
            "pending": total - done,
            "vision_hit": v_hit,
            "vision_miss": total - v_hit,
            "prompt_hit": p_hit,
            "prompt_miss": total - p_hit,
        }
        return result

    def all_shots(self, ep: str, seq: str) -> list:
        return list(self._seq(ep, seq).get("shots", {}).keys())


class ShotlistUpdater:
    STATUS_DONE = "✅"
    STATUS_PENDING = "⏳"
    STATUS_FAIL = "❌"
    STATUS_RETRY = "🔄"

    # 상태 컬럼을 헤더 이름으로 찾는다. shotlist 컬럼 수는 프로젝트마다 다르다
    # (5컬럼 구형 / 7컬럼 GenSetup v5.2). 컬럼 수를 가정하면 나머지가 날아간다.
    STATUS_HEADERS = ("상태", "status")

    @staticmethod
    def _split(line: str) -> list:
        return [p.strip() for p in line.strip().strip("|").split("|")]

    @classmethod
    def _status_index(cls, headers: list) -> int:
        """헤더 행에서 상태 컬럼의 위치. 못 찾으면 -1(마지막 컬럼)."""
        for line in headers:
            stripped = line.strip()
            if not stripped.startswith("|") or stripped.startswith("|---"):
                continue
            cells = [c.lower() for c in cls._split(line)]
            for i, c in enumerate(cells):
                if c in cls.STATUS_HEADERS:
                    return i
            break
        return -1

    @classmethod
    def read(cls, path: pathlib.Path) -> tuple:
        """Returns (lines_before_table, header_lines, shot_rows).

        행은 `{"cells": [...]}` 로 원본 컬럼을 **전부** 보존한다.
        """
        lines = path.read_text(encoding="utf-8").splitlines()
        before, headers, rows = [], [], []
        in_table = False
        for line in lines:
            stripped = line.strip()
            if not in_table:
                if stripped.startswith("| #") or stripped.startswith("|#"):
                    in_table = True
                    headers.append(line)
                else:
                    if not headers:
                        before.append(line)
                    else:
                        headers.append(line)
            else:
                if stripped.startswith("|---"):
                    headers.append(line)
                elif stripped.startswith("|"):
                    cells = cls._split(line)
                    rows.append({"shot": cells[0], "cells": cells})
                else:
                    rows.append({"_raw": line})
        return before, headers, rows

    @staticmethod
    def write(
        path: pathlib.Path,
        before: list,
        headers: list,
        rows: list,
    ) -> None:
        out = before + headers
        for r in rows:
            if "_raw" in r:
                out.append(r["_raw"])
            elif "cells" in r:
                out.append("| " + " | ".join(r["cells"]) + " |")
            else:
                # 구 호출부 호환 — 5컬럼 dict를 직접 만들어 넘기는 경우
                out.append(
                    f"| {r['shot']} | {r.get('size', '')} | {r.get('chars', '')} | "
                    f"{r.get('desc', '')} | {r.get('status', '')} |"
                )
        tmp = path.with_suffix(".md.tmp")
        tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def update_status(
        cls, path: pathlib.Path, shot_num: str, status_emoji: str
    ) -> None:
        if not path.exists():
            return
        before, headers, rows = cls.read(path)
        idx = cls._status_index(headers)
        for r in rows:
            if "_raw" in r or r["shot"].strip() != shot_num.strip():
                continue
            cells = r["cells"]
            if idx == -1:
                # 상태 헤더가 없다 — 마지막 컬럼이 상태라고 본다
                if len(cells) < 2:
                    break
                cells[-1] = status_emoji
            else:
                # 헤더보다 짧은 행은 빈 칸으로 늘린다. 마지막 칸을 덮어쓰면
                # 그 칸에 있던 실제 데이터가 사라진다
                while len(cells) <= idx:
                    cells.append("")
                cells[idx] = status_emoji
            break
        cls.write(path, before, headers, rows)

    @staticmethod
    def update_url(urls_path: pathlib.Path, shot_num: str, url: str) -> None:
        if not urls_path.exists():
            return
        text = urls_path.read_text(encoding="utf-8")
        pattern = rf"(\|\s*{re.escape(shot_num)}\s*\|)[^\n]*"
        replacement = rf"\1 {url} |"
        new_text = re.sub(pattern, replacement, text)
        if new_text == text:
            new_text = text.rstrip() + f"\n| {shot_num} | {url} |\n"
        tmp = urls_path.with_suffix(".md.tmp")
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, urls_path)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 cache.py info")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "info":
        cm = CacheManager()
        print(json.dumps(cm._data, indent=2, ensure_ascii=False))
    elif cmd == "clear":
        if CacheManager.CACHE_FILE.exists():
            CacheManager.CACHE_FILE.unlink()
            print("캐시 삭제 완료")
        else:
            print("캐시 파일 없음")
