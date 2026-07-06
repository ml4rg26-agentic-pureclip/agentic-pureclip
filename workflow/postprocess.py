import sys

import numpy as np
import pandas as pd
import yaml

from agent.logging_config import setup_logger


logger = setup_logger("postprocess")


def load_bed(path):
    try:
        df = pd.read_csv(
            path,
            sep="\t",
            header=None,
            names=["chrom", "start", "end", "name", "score", "strand"],
        )
        return df
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return pd.DataFrame(columns=["chrom", "start", "end", "name", "score", "strand"])


def count_events(name_str):
    """Number of crosslink events encoded in a PureCLIP region 'name' field."""
    if not isinstance(name_str, str):
        return 0
    return len([x for x in name_str.split(";") if x])


def merge_within_gap(regions, gap):
    """Merge same-chrom/strand regions whose gap is <= ``gap`` nt.

    Adjacent PureCLIP binding regions are often fragments of one footprint;
    ``cluster_gap_width`` controls how aggressively they are stitched back
    together before a fixed-width window is placed. Coordinates take the union,
    crosslink-event names are concatenated (so event counts aggregate), and the
    max region score is kept.
    """
    if gap is None or gap <= 0 or regions.empty:
        return regions.reset_index(drop=True)

    regions = regions.sort_values(["chrom", "strand", "start"]).reset_index(drop=True)
    merged = []
    cur = None
    for _, r in regions.iterrows():
        if (
            cur is not None
            and r["chrom"] == cur["chrom"]
            and r["strand"] == cur["strand"]
            and r["start"] <= cur["end"] + gap
        ):
            cur["end"] = max(cur["end"], r["end"])
            cur["name"] = f"{cur['name']};{r['name']}"
            try:
                cur["score"] = max(cur["score"], r["score"])
            except TypeError:
                pass
        else:
            if cur is not None:
                merged.append(cur)
            cur = r.to_dict()
    if cur is not None:
        merged.append(cur)
    return pd.DataFrame(merged, columns=regions.columns)


def build_site_index(sites):
    """Group crosslink sites by (chrom, strand) into sorted (starts, scores)."""
    index = {}
    if sites.empty:
        return index
    s = sites.copy()
    s["score"] = pd.to_numeric(s["score"], errors="coerce").fillna(0.0)
    for key, grp in s.groupby(["chrom", "strand"]):
        grp = grp.sort_values("start")
        index[key] = (grp["start"].to_numpy(), grp["score"].to_numpy())
    return index


def summit_of(region, site_index):
    """Position of the highest-scoring crosslink site within ``region``.

    Falls back to the region's geometric midpoint when no crosslink site (with a
    usable score) lies inside it — e.g. when the sites file is absent.
    """
    key = (region["chrom"], region["strand"])
    starts_scores = site_index.get(key)
    if starts_scores is not None:
        starts, scores = starts_scores
        lo = np.searchsorted(starts, region["start"], side="left")
        hi = np.searchsorted(starts, region["end"], side="right")
        if hi > lo:
            local = scores[lo:hi]
            return int(starts[lo + int(np.argmax(local))])
    return int((region["start"] + region["end"]) // 2)


def main(config_path, out_path, regions_path=None, sites_path=None):
    run_logger = setup_logger("postprocess_run", f"{out_path}.log")
    run_logger.info("Starting postprocessing using %s", config_path)
    cfg = yaml.safe_load(open(config_path))
    pp = cfg["postprocessing"]
    width = pp["force_width"]
    half = width // 2
    results_dir = cfg.get("output", {}).get("results_dir", "results")

    regions = load_bed(regions_path or f"{results_dir}/PureCLIP.binding_regions.bed")
    sites = load_bed(sites_path or f"{results_dir}/PureCLIP.crosslink_sites.bed")

    # 1. length + crosslink-event support filters (on the raw regions)
    regions = regions[(regions["end"] - regions["start"]) >= pp["min_region_length_nt"]]
    if "min_crosslink_events" in pp:
        regions = regions[regions["name"].apply(count_events) >= pp["min_crosslink_events"]]

    # 2. stitch fragmented footprints back together (cluster_gap_width)
    n_before = len(regions)
    regions = merge_within_gap(regions, pp.get("cluster_gap_width"))
    run_logger.info("Gap-merge (gap=%s): %d regions -> %d clusters",
                    pp.get("cluster_gap_width"), n_before, len(regions))

    # 3. centre a fixed-width window on the true crosslink summit of each cluster
    site_index = build_site_index(sites)
    n_summit = 0
    out_rows = []
    for _, region in regions.iterrows():
        summit = summit_of(region, site_index)
        if summit != (region["start"] + region["end"]) // 2:
            n_summit += 1
        new_start = max(0, summit - half)
        out_rows.append({
            "chrom": region["chrom"],
            "start": new_start,
            "end": new_start + width,
            "name": region["name"],
            "score": region["score"],
            "strand": region["strand"],
        })

    out = pd.DataFrame(out_rows)
    out.to_csv(out_path, sep="\t", header=False, index=False)
    run_logger.info("Wrote %d binding sites (width=%s, %d centred on a crosslink summit) to %s",
                    len(out), width, n_summit, out_path)


if __name__ == "__main__":
    main(
        sys.argv[1],
        sys.argv[2],
        sys.argv[3] if len(sys.argv) > 3 else None,
        sys.argv[4] if len(sys.argv) > 4 else None,
    )
