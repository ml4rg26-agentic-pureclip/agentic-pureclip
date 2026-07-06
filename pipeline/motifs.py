"""
Motif registry and loader for RNA-binding protein motifs.

Motifs are stored in data/motifs/ organized as:
    data/motifs/{database}/{rbp}/{cell_line}/*.transfac

Supported format: TRANSFAC (count/frequency matrices).
Also supports simple IUPAC consensus strings as a fallback.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── IUPAC expansion table (RNA → DNA) ──────────────────────────────────────
IUPAC_TABLE: dict[str, str] = {
    "A": "A", "C": "C", "G": "G", "T": "T", "U": "T",
    "R": "[AG]", "Y": "[CT]", "M": "[AC]", "K": "[GT]",
    "W": "[AT]", "S": "[GC]", "B": "[CGT]", "D": "[AGT]",
    "H": "[ACT]", "V": "[ACG]", "N": "[ACGT]",
}

# Standard nucleotide order in TRANSFAC matrices
NUC_ORDER = ["A", "C", "G", "T"]

# Log-odds scoring parameters
PSEUDOCOUNT = 0.01          # smoothing added to each base frequency
BACKGROUND_FREQ = 0.25      # uniform background (A/C/G/T equally likely)


# ── Data types ─────────────────────────────────────────────────────────────

@dataclass
class MotifPWM:
    """Position Weight Matrix with metadata."""
    motif_id: str
    rbp_name: str
    database: str
    cell_line: str | None = None
    # pwm[row][base] = log-odds or frequency; row index = position 0..N-1
    pwm: list[dict[str, float]] = field(default_factory=list)
    consensus: str = ""
    length: int = 0

    def __post_init__(self):
        self._log_odds_cache: list[dict[str, float]] | None = None
        if self.pwm:
            self.length = len(self.pwm)
            self.consensus = "".join(
                max(pos, key=pos.get) for pos in self.pwm
            )

    @property
    def consensus_iupac(self) -> str:
        """Return the PWM consensus (DNA alphabet)."""
        return self.consensus

    @property
    def log_odds(self) -> list[dict[str, float]]:
        """Per-position log2 odds: log2((freq + pseudo) / background).

        The stored ``pwm`` holds per-position base frequencies. Converting to
        log-odds gives a proper position weight matrix: conserved positions
        contribute large scores, uninformative (flat) positions contribute ~0,
        and bases rarer than background contribute negative scores.
        """
        if self._log_odds_cache is None:
            log_odds: list[dict[str, float]] = []
            for pos in self.pwm:
                total = sum(pos.get(b, 0.0) for b in NUC_ORDER) or 1.0
                row = {}
                for base in NUC_ORDER:
                    freq = (pos.get(base, 0.0) / total + PSEUDOCOUNT) / (1 + 4 * PSEUDOCOUNT)
                    row[base] = math.log2(freq / BACKGROUND_FREQ)
                log_odds.append(row)
            self._log_odds_cache = log_odds
        return self._log_odds_cache

    def score_range(self) -> tuple[float, float]:
        """Minimum and maximum achievable log-odds score for this PWM."""
        rows = self.log_odds
        return (
            sum(min(row.values()) for row in rows),
            sum(max(row.values()) for row in rows),
        )

    def match_threshold(self, pct: float) -> float:
        """Score cutoff at ``pct`` of the way from the min to max possible score.

        ``pct=0`` accepts everything; ``pct=1`` only accepts the consensus.
        Robust to negative log-odds values (unlike a fraction of the max).
        """
        low, high = self.score_range()
        return low + pct * (high - low)

    def score_sequence(self, seq: str) -> float:
        """Best log-odds score of this PWM over all offsets in ``seq``."""
        if len(seq) < self.length:
            return float("-inf")
        rows = self.log_odds
        best = float("-inf")
        for offset in range(len(seq) - self.length + 1):
            score = 0.0
            for i, base in enumerate(seq[offset : offset + self.length]):
                score += rows[i].get(base, 0.0)  # non-ACGT base => background (0)
            if score > best:
                best = score
        return best


@dataclass
class MotifEntry:
    """A single motif entry that can be either PWM or IUPAC consensus."""
    pattern: str  # IUPAC consensus string (e.g. "UGCAUG")
    type: str = "target"  # "target", "control", etc.
    pwm: MotifPWM | None = None
    source_database: str | None = None


# ── TRANSFAC loader ────────────────────────────────────────────────────────

def _parse_transfac(content: str, motif_id: str = "unknown") -> MotifPWM | None:
    """Parse a single TRANSFAC-format matrix from text content.

    TRANSFAC format example:
        ID   M00001
        BF   species
        P0   A  C  G  T
        01   1  2  3  4  X
        02   5  6  7  8  X
        ...
        XX
        //
    """
    rows: list[list[float]] = []
    motif_id_parsed = motif_id
    in_matrix = False

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("XX") or line.startswith("//"):
            continue
        if line.startswith("ID"):
            motif_id_parsed = line[2:].strip()
            continue
        if line.startswith("P0") or line.startswith("PO"):
            in_matrix = True
            continue
        if in_matrix and line[0].isdigit():
            parts = line.split()
            if len(parts) >= 4:
                try:
                    values = [float(p) for p in parts[1:5]]
                    rows.append(values)
                except ValueError:
                    continue

    if not rows:
        return None

    # Normalize to frequencies (if they are counts)
    pwm: list[dict[str, float]] = []
    for row in rows:
        total = sum(row)
        if total > 0:
            freqs = {NUC_ORDER[i]: v / total for i, v in enumerate(row)}
        else:
            freqs = {b: 0.25 for b in NUC_ORDER}
        pwm.append(freqs)

    return MotifPWM(
        motif_id=motif_id_parsed,
        rbp_name="",  # filled by caller
        database="",  # filled by caller
        pwm=pwm,
    )


def load_transfac_file(path: str | Path) -> list[MotifPWM]:
    """Load all motifs from a TRANSFAC file.

    Each motif is delimited by '//'. Returns a list of MotifPWM objects.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Motif file not found: {path}")

    content = path.read_text()
    # Split on "//" to get individual motifs
    blocks = content.split("//")
    motifs: list[MotifPWM] = []
    for i, block in enumerate(blocks):
        block = block.strip()
        if not block:
            continue
        pwm = _parse_transfac(block, motif_id=f"{path.stem}_{i}")
        if pwm:
            motifs.append(pwm)
    return motifs


# ── Motif registry ─────────────────────────────────────────────────────────

# Where motif databases live relative to repo root
MOTIFS_ROOT = Path("data/motifs")


def _resolve_path(db: str, rbp: str, cell_line: str | None = None) -> Path:
    """Resolve path to motif directory for a given database/RBP/cell_line.

    Structure:
        data/motifs/{database}/{RBP}/*.transfac
        or
        data/motifs/{database}/{RBP}/{cell_line}/*.transfac
    """
    base = MOTIFS_ROOT / db / rbp
    if cell_line:
        cell_path = base / cell_line
        if cell_path.exists():
            return cell_path
    return base


def list_motif_files(
    database: str,
    rbp: str,
    cell_line: str | None = None,
) -> list[Path]:
    """List all .transfac (or .txt, .pwm) files for a given RBP in a database."""
    motif_dir = _resolve_path(database, rbp, cell_line)
    if not motif_dir.exists():
        return []
    # Search recursively (handles cell_line subdirs like mCrossBase/RBFOX2/K562/)
    files = sorted(motif_dir.rglob("*.transfac"))
    if not files:
        files = sorted(motif_dir.rglob("*.txt"))
    if not files:
        files = sorted(motif_dir.rglob("*.pwm"))
    return files


def _extract_cell_line_from_path(filepath: Path, rbp_dir: Path) -> str | None:
    """Try to extract cell line from a path like mCrossBase/RBFOX2/K562/file.transfac."""
    try:
        rel = filepath.relative_to(rbp_dir)
        parts = rel.parts
        if len(parts) >= 2:
            # The first part after RBP dir is likely the cell line
            return parts[0]
    except ValueError:
        pass
    return None


def load_motifs_for_rbp(
    database: str,
    rbp: str,
    cell_line: str | None = None,
) -> list[MotifEntry]:
    """Load all motifs for an RBP from a specific database.

    Returns list of MotifEntry objects with both PWM and IUPAC consensus.
    For databases with cell-line subdirectories (e.g. mCrossBase), the
    cell line is extracted from the path.
    """
    entries: list[MotifEntry] = []
    files = list_motif_files(database, rbp, cell_line)

    rbp_dir = MOTIFS_ROOT / database / rbp

    for filepath in files:
        pwms = load_transfac_file(filepath)
        # Extract cell line from path if not explicitly provided
        inferred_cl = cell_line or _extract_cell_line_from_path(filepath, rbp_dir)
        for pwm in pwms:
            pwm.rbp_name = rbp
            pwm.database = database
            pwm.cell_line = inferred_cl
            entries.append(MotifEntry(
                pattern=pwm.consensus_iupac,
                type="target",
                pwm=pwm,
                source_database=database,
            ))

    return entries


def load_all_motifs(
    rbp: str,
    cell_line: str | None = None,
    databases: list[str] | None = None,
) -> dict[str, list[MotifEntry]]:
    """Load motifs for an RBP across multiple databases.

    Returns dict keyed by database name, each value is a list of MotifEntry.
    """
    if databases is None:
        if not MOTIFS_ROOT.exists():
            return {}
        databases = [d.name for d in MOTIFS_ROOT.iterdir() if d.is_dir()]

    result: dict[str, list[MotifEntry]] = {}
    for db in databases:
        entries = load_motifs_for_rbp(db, rbp, cell_line)
        if entries:
            result[db] = entries
    return result


def get_best_motif(
    rbp: str,
    cell_line: str | None = None,
    databases: list[str] | None = None,
) -> MotifEntry | None:
    """Get the best available motif for an RBP (prefer mCrossBase, then first available)."""
    all_motifs = load_all_motifs(rbp, cell_line, databases)

    # Prefer mCrossBase
    preferred = ["mCrossBase", "mcrossbase", "ATtRACT", "CISBP-RNA"]
    for pref in preferred:
        if pref in all_motifs and all_motifs[pref]:
            return all_motifs[pref][0]

    # Fall back to first available database
    for db_entries in all_motifs.values():
        if db_entries:
            return db_entries[0]

    return None


def available_databases() -> list[str]:
    """List available motif databases in data/motifs/."""
    if not MOTIFS_ROOT.exists():
        return []
    return sorted(d.name for d in MOTIFS_ROOT.iterdir() if d.is_dir())


def available_rbps(database: str | None = None) -> dict[str, list[str]]:
    """Map databases to their available RBPs."""
    if not MOTIFS_ROOT.exists():
        return {}
    result: dict[str, list[str]] = {}
    dbs = [database] if database else available_databases()
    for db in dbs:
        db_path = MOTIFS_ROOT / db
        rbps = sorted(d.name for d in db_path.iterdir() if d.is_dir())
        if rbps:
            result[db] = rbps
    return result


# ── IUPAC → regex (kept for backward compatibility) ───────────────────────

def iupac_to_regex(motif: str) -> str:
    """Convert IUPAC RNA motif to DNA regex pattern."""
    return "".join(IUPAC_TABLE.get(base.upper(), base) for base in motif)


def compile_motif_regex(motif: str) -> re.Pattern:
    """Compile an IUPAC motif into a compiled regex."""
    return re.compile(iupac_to_regex(motif))


# ── PWM-based scanning ────────────────────────────────────────────────────

def scan_sequence_with_pwm(
    sequence: str,
    pwm: MotifPWM,
    threshold: float | None = None,
) -> list[tuple[int, float]]:
    """Scan a DNA sequence with a PWM, returning positions and scores above threshold.

    Args:
        sequence: DNA sequence (uppercase)
        pwm: MotifPWM to scan with
        threshold: Minimum log-odds score to report. If None, reports every offset.

    Returns:
        List of (position, score) tuples sorted by score descending.
    """
    if len(sequence) < pwm.length:
        return []

    rows = pwm.log_odds
    hits: list[tuple[int, float]] = []
    for offset in range(len(sequence) - pwm.length + 1):
        score = 0.0
        for i, base in enumerate(sequence[offset : offset + pwm.length]):
            score += rows[i].get(base, 0.0)  # non-ACGT base => background (0)
        if threshold is None or score >= threshold:
            hits.append((offset, score))

    return sorted(hits, key=lambda x: x[1], reverse=True)


def calculate_motif_enrichment(
    sequences: list[str],
    motif_entries: list[MotifEntry],
    threshold_pct: float = 0.80,
) -> dict[str, float]:
    """Calculate motif hit rates across a list of sequences using PWM scoring.

    For each motif entry, computes the fraction of sequences that contain
    a PWM log-odds hit at or above threshold_pct of the score range.

    Falls back to IUPAC regex if no PWM is available.
    """
    results: dict[str, float] = {}
    n = len(sequences)
    if n == 0:
        return {}

    for entry in motif_entries:
        if entry.pwm is not None:
            # PWM log-odds scoring
            threshold = entry.pwm.match_threshold(threshold_pct)
            hits = sum(
                1 for seq in sequences
                if scan_sequence_with_pwm(seq, entry.pwm, threshold)
            )
            label = f"{entry.pwm.motif_id}" if entry.pwm.motif_id else entry.pattern
        else:
            # Fallback to IUPAC regex
            rx = compile_motif_regex(entry.pattern)
            hits = sum(1 for seq in sequences if rx.search(seq))
            label = entry.pattern

        results[label] = round(hits / n, 4)

    return results
