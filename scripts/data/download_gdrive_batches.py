#!/usr/bin/env python3
"""Download the new CLIP dataset batches from Google Drive onto the runner.

Three shared Google Drive folders each contain per-dataset ``*.tar.gz`` archives.
They are mirrored into ``data/incoming_gdrive/<batch>/`` -- kept SEPARATE on purpose,
because dataset names collide both across the three folders AND (in batch 2) within
a single folder (there are two distinct ``RBFOX2_partners.tar.gz`` objects).

Every file is downloaded individually by its Drive file-ID via
``rclone backend copyid`` so that no file is ever silently dropped due to a name
clash. Within a folder, colliding names are disambiguated with a ``.dup-<id8>``
suffix. The run is idempotent: files already present with the expected byte size
are skipped, so it can be safely re-run / resumed.

Prerequisite: an rclone remote named ``gdrive`` configured with (read-only) access
to the shared folders.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

RCLONE = os.environ.get("RCLONE_BIN", os.path.expanduser("~/.local/bin/rclone"))
REMOTE = "gdrive"
DEST_ROOT = Path("data/incoming_gdrive")
RETRIES = 3

# (Drive folder ID, local subdirectory name). Order = order of the links given.
FOLDERS = [
    ("1Su44OGWqxBdRmmaQ6QlRPPQFrXwB0JRr", "new_batch_1__1Su44OGW"),
    ("1jykCsPeu3IsuL3erb2ftKmzNSSXfrizV", "new_batch_2__1jykCsPe"),
    ("1xX8-pJ2O7oTMPYIk5yEklWI3r440AQ5u", "new_batch_3__1xX8-pJ2"),
]


def human(n: int) -> str:
    x = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if x < 1024 or unit == "TiB":
            return f"{x:.2f} {unit}"
        x /= 1024


def lsjson(folder_id: str) -> list[dict]:
    p = subprocess.run(
        [RCLONE, "lsjson", f"{REMOTE}:", "--drive-root-folder-id", folder_id],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        sys.exit(f"[FATAL] lsjson failed for {folder_id}:\n{p.stderr}")
    return [f for f in json.loads(p.stdout) if not f.get("IsDir")]


def build_plan(files: list[dict]) -> list[tuple[str, str, int]]:
    """Return [(file_id, local_name, size)] with duplicate names disambiguated."""
    counts = Counter(f["Name"] for f in files)
    plan = []
    for f in sorted(files, key=lambda x: x["Name"]):
        name = f["Name"]
        if counts[name] > 1:
            name = f"{name}.dup-{f['ID'][:8]}"
        plan.append((f["ID"], name, int(f["Size"])))
    return plan


def download_one(file_id: str, dest: Path, expected: int) -> str:
    if dest.exists() and dest.stat().st_size == expected:
        return "skip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, RETRIES + 1):
        if tmp.exists():
            tmp.unlink()
        p = subprocess.run(
            [RCLONE, "backend", "copyid", f"{REMOTE}:", file_id, str(tmp),
             "--drive-acknowledge-abuse", "--retries", "5", "--low-level-retries", "10"],
        )
        if p.returncode == 0 and tmp.exists() and tmp.stat().st_size == expected:
            tmp.replace(dest)
            return "ok"
        got = tmp.stat().st_size if tmp.exists() else 0
        print(f"    ! attempt {attempt}/{RETRIES} failed "
              f"(rc={p.returncode}, got {got}/{expected} bytes); retrying...",
              flush=True)
        time.sleep(5 * attempt)
    if tmp.exists():
        tmp.unlink()
    return "FAIL"


def main() -> int:
    if not os.path.exists(RCLONE):
        sys.exit(f"[FATAL] rclone not found at {RCLONE}")
    DEST_ROOT.mkdir(parents=True, exist_ok=True)

    grand_files = grand_bytes = 0
    failures: list[str] = []

    for folder_id, subdir in FOLDERS:
        dest_dir = DEST_ROOT / subdir
        print(f"\n{'='*72}\nFOLDER {folder_id}\n  -> {dest_dir}\n{'='*72}", flush=True)
        files = lsjson(folder_id)
        plan = build_plan(files)
        total = sum(sz for _, _, sz in plan)
        print(f"  {len(plan)} files, {human(total)} total", flush=True)

        manifest = dest_dir / "_manifest.tsv"
        dest_dir.mkdir(parents=True, exist_ok=True)
        with manifest.open("w") as mf:
            mf.write("file_id\tlocal_name\tsize_bytes\tstatus\n")
            done = 0
            for i, (fid, name, size) in enumerate(plan, 1):
                dest = dest_dir / name
                print(f"  [{i}/{len(plan)}] {name}  ({human(size)}) ...",
                      end=" ", flush=True)
                t0 = time.time()
                status = download_one(fid, dest, size)
                dt = time.time() - t0
                rate = human(size / dt) + "/s" if dt > 0 and status == "ok" else "-"
                print(f"{status} ({rate})", flush=True)
                mf.write(f"{fid}\t{name}\t{size}\t{status}\n")
                if status in ("ok", "skip"):
                    done += size
                    grand_files += 1
                    grand_bytes += size
                else:
                    failures.append(f"{subdir}/{name} [{fid}]")
        print(f"  folder done: {human(done)} present", flush=True)

    print(f"\n{'#'*72}")
    print(f"SUMMARY: {grand_files} files OK/skip, {human(grand_bytes)} on disk")
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All files downloaded successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
