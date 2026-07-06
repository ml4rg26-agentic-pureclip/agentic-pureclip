#!/usr/bin/env python3
"""Reorganize extracted motif tarballs into the expected hierarchy:

    data/motifs/{database}/{RBP}/[{cell_line}/]*.transfac

From the tarball structure:
    {database}/preprocessed/{RBP}/{FILENAME}.transfac

For mCrossBase, filenames like "K562.PCM.001.transfac" encode the cell line.
For other databases, we just strip the "preprocessed/" level.
"""
import re
import shutil
from pathlib import Path

MOTIFS_DIR = Path("data/motifs")
TARBALL_DIR = MOTIFS_DIR / "rbp_binding_motifs_tarballs"

# Cell line pattern for mCrossBase: "K562.PCM.001.transfac"
# Other patterns seen: "Homo_sapiens.PPM.000.transfac", "PPM.000.transfac", "human.PPM.000.transfac"
CELL_LINE_PATTERN = re.compile(
    r"^(K562|HepG2|HEK293|HeLa|MCF7|A549|Jurkat|GM12878|HUVEC|"
    r"U2OS|HCT116|HT1080|SK-N-SH|H1|IMR90|NHEK|"
    r"Hep-G2|K-562)\.",
    re.IGNORECASE,
)


def parse_cell_line(filename: str) -> str | None:
    """Try to extract cell line from filename."""
    m = CELL_LINE_PATTERN.match(filename)
    if m:
        cl = m.group(1)
        # Normalize common variants
        cl = cl.replace("Hep-G2", "HepG2").replace("K-562", "K562")
        return cl
    return None


def main():
    assert MOTIFS_DIR.exists(), f"{MOTIFS_DIR} not found"

    dbs = [d for d in MOTIFS_DIR.iterdir() if d.is_dir() and d.name != "rbp_binding_motifs_tarballs"]
    print(f"Found databases: {[d.name for d in dbs]}")

    for db_path in dbs:
        db_name = db_path.name
        preprocessed = db_path / "preprocessed"
        if not preprocessed.exists():
            print(f"  {db_name}: no preprocessed/ dir, skipping")
            continue

        rbp_dirs = sorted(d for d in preprocessed.iterdir() if d.is_dir())
        print(f"  {db_name}: {len(rbp_dirs)} RBPs")

        for rbp_src in rbp_dirs:
            rbp_name = rbp_src.name
            transfac_files = sorted(rbp_src.glob("*.transfac"))

            if not transfac_files:
                continue

            # Determine if we need cell-line subdirs
            has_cell_lines = any(
                parse_cell_line(f.name) for f in transfac_files
            )

            if has_cell_lines:
                # Group by cell line
                by_cell: dict[str, list[Path]] = {}
                for tf in transfac_files:
                    cl = parse_cell_line(tf.name)
                    if cl:
                        by_cell.setdefault(cl, []).append(tf)
                    else:
                        by_cell.setdefault("_unknown", []).append(tf)

                for cell, files in by_cell.items():
                    dest = db_path / rbp_name / cell
                    dest.mkdir(parents=True, exist_ok=True)
                    for f in files:
                        shutil.copy2(f, dest / f.name)
                print(f"    {rbp_name}: {len(transfac_files)} motifs → {len(by_cell)} cell lines")
            else:
                # Flat: {DB}/{RBP}/
                dest = db_path / rbp_name
                dest.mkdir(parents=True, exist_ok=True)
                for f in transfac_files:
                    shutil.copy2(f, dest / f.name)
                print(f"    {rbp_name}: {len(transfac_files)} motifs (no cell line)")

        # Remove preprocessed/ dir (already copied)
        shutil.rmtree(preprocessed)

    # Remove tarballs to clean up
    if TARBALL_DIR.exists():
        shutil.rmtree(TARBALL_DIR)

    print("\nFinal structure:")
    for db in sorted(MOTIFS_DIR.iterdir()):
        if db.is_dir():
            rbp_count = sum(1 for _ in db.rglob("*.transfac"))
            rbps = sorted(set(
                p.parent.parent.name if p.parent.parent != db else p.parent.name
                for p in db.rglob("*.transfac")
            ))
            print(f"  {db.name}/ ({rbp_count} motifs, {len(rbps)} RBPs)")


if __name__ == "__main__":
    main()
