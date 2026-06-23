# workflow/postprocess.py
import sys
import yaml
import pandas as pd
from agent.logging_config import setup_logger

logger = setup_logger("postprocess", "results/logs/postprocess.log")

def load_bed(path):
    try:
        df = pd.read_csv(path, sep="\t", header=None,
                         names=["chrom", "start", "end", "name", "score", "strand"])
        return df
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return pd.DataFrame(columns=["chrom", "start", "end", "name", "score", "strand"])

def main(config_path, out_path):
    logger.info(f"Starting postprocessing using {config_path}")
    cfg = yaml.safe_load(open(config_path))
    pp = cfg["postprocessing"]
    width = pp["force_width"]
    half = width // 2

    regions = load_bed("results/PureCLIP.binding_regions.bed")

    # Drop regions shorter than min_region_length_nt
    regions = regions[(regions["end"] - regions["start"]) >= pp["min_region_length_nt"]]

    if "min_crosslink_events" in pp:
        # The 'name' column in pureclip_regions.bed contains semicolon-separated site scores
        # We can count the number of sites merged into the region
        def count_events(name_str):
            if not isinstance(name_str, str):
                return 0
            return len([x for x in name_str.split(";") if x])
            
        regions = regions[regions["name"].apply(count_events) >= pp["min_crosslink_events"]]

    sites = []
    for _, r in regions.iterrows():
        summit = (r["start"] + r["end"]) // 2
        new_start = max(0, summit - half)
        sites.append({
            "chrom": r["chrom"],
            "start": new_start,
            "end": new_start + width,
            "name": r["name"],
            "score": r["score"],
            "strand": r["strand"],
        })

    out = pd.DataFrame(sites)
    out.to_csv(out_path, sep="\t", header=False, index=False)
    logger.info(f"Wrote {len(out)} binding sites (width={width}) to {out_path}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
