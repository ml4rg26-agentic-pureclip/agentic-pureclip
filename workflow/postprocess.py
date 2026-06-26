import sys

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


def main(config_path, out_path, regions_path=None):
    run_logger = setup_logger("postprocess_run", f"{out_path}.log")
    run_logger.info("Starting postprocessing using %s", config_path)
    cfg = yaml.safe_load(open(config_path))
    pp = cfg["postprocessing"]
    width = pp["force_width"]
    half = width // 2
    results_dir = cfg.get("output", {}).get("results_dir", "results")

    regions = load_bed(regions_path or f"{results_dir}/PureCLIP.binding_regions.bed")

    regions = regions[(regions["end"] - regions["start"]) >= pp["min_region_length_nt"]]

    if "min_crosslink_events" in pp:

        def count_events(name_str):
            if not isinstance(name_str, str):
                return 0
            return len([x for x in name_str.split(";") if x])

        regions = regions[regions["name"].apply(count_events) >= pp["min_crosslink_events"]]

    sites = []
    for _, region in regions.iterrows():
        summit = (region["start"] + region["end"]) // 2
        new_start = max(0, summit - half)
        sites.append(
            {
                "chrom": region["chrom"],
                "start": new_start,
                "end": new_start + width,
                "name": region["name"],
                "score": region["score"],
                "strand": region["strand"],
            }
        )

    out = pd.DataFrame(sites)
    out.to_csv(out_path, sep="\t", header=False, index=False)
    run_logger.info("Wrote %d binding sites (width=%s) to %s", len(out), width, out_path)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
