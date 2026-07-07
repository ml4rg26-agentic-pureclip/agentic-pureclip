"""Regression tests for agentic_pureclip.postprocess.postprocess — the
cluster_gap_width merge and the crosslink-summit centring (both were previously
dead / midpoint-only)."""
import pandas as pd
import pytest
import yaml

from agentic_pureclip.postprocess import postprocess


def _regions(rows):
    return pd.DataFrame(rows, columns=["chrom", "start", "end", "name", "score", "strand"])


def test_merge_within_gap_stitches_adjacent_same_strand():
    regions = _regions([
        ["chr21", 1000, 1030, "a;b;c", 5, "+"],
        ["chr21", 1040, 1060, "d;e;f", 7, "+"],   # gap = 10
        ["chr21", 5000, 5040, "g;h;i", 9, "-"],   # far away / other strand
    ])
    merged = postprocess.merge_within_gap(regions, gap=10)
    assert len(merged) == 2
    first = merged.iloc[0]
    assert first["start"] == 1000 and first["end"] == 1060      # union of the fragments
    assert first["name"] == "a;b;c;d;e;f"                        # events aggregated
    assert first["score"] == 7                                   # max score kept


def test_merge_within_gap_respects_strand_and_gap():
    regions = _regions([
        ["chr21", 1000, 1030, "a", 5, "+"],
        ["chr21", 1040, 1060, "b", 5, "-"],   # same gap but opposite strand → no merge
    ])
    assert len(postprocess.merge_within_gap(regions, gap=10)) == 2
    # gap too large to stitch
    far = _regions([
        ["chr21", 1000, 1030, "a", 5, "+"],
        ["chr21", 1100, 1120, "b", 5, "+"],
    ])
    assert len(postprocess.merge_within_gap(far, gap=10)) == 2


def test_summit_picks_highest_scoring_crosslink():
    sites = _regions([
        ["chr21", 1005, 1006, "s", 3, "+"],
        ["chr21", 1045, 1046, "s", 99, "+"],   # the summit
        ["chr21", 1055, 1056, "s", 8, "+"],
    ])
    idx = postprocess.build_site_index(sites)
    region = {"chrom": "chr21", "start": 1000, "end": 1060, "strand": "+"}
    assert postprocess.summit_of(region, idx) == 1045          # not the midpoint (1030)


def test_summit_falls_back_to_midpoint_without_sites():
    region = {"chrom": "chr21", "start": 1000, "end": 1060, "strand": "+"}
    assert postprocess.summit_of(region, {}) == 1030            # geometric midpoint


def test_end_to_end_window_centred_on_summit(tmp_path):
    (tmp_path / "regions.bed").write_text(
        "chr21\t1000\t1030\ta;b;c\t5\t+\n"
        "chr21\t1040\t1060\td;e;f\t7\t+\n"
    )
    (tmp_path / "sites.bed").write_text(
        "chr21\t1045\t1046\ts\t99\t+\n"
        "chr21\t1005\t1006\ts\t3\t+\n"
    )
    cfg = {
        "postprocessing": {"force_width": 9, "min_region_length_nt": 3,
                           "min_crosslink_events": 3, "cluster_gap_width": 10},
        "output": {"results_dir": str(tmp_path)},
    }
    (tmp_path / "cfg.yaml").write_text(yaml.safe_dump(cfg))
    out = tmp_path / "out.bed"
    postprocess.main(str(tmp_path / "cfg.yaml"), str(out),
                     str(tmp_path / "regions.bed"), str(tmp_path / "sites.bed"))
    df = pd.read_csv(out, sep="\t", header=None)
    assert len(df) == 1                       # the two fragments merged into one cluster
    assert df.iloc[0][1] == 1041 and df.iloc[0][2] == 1050   # 9-nt window centred on 1045
