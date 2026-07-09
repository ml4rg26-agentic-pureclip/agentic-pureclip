"""``agentic-pureclip-run`` — launch a parameter-search run from the terminal.

The dashboard's Plan page builds an invocation of this command (it no longer
launches runs itself); paste it on the runner, from the repo root, to start the
same run the UI would have. It writes the standard overnight-batch manifest and
launches ``scripts/run/overnight_batch.py`` on it.

    agentic-pureclip-run --dataset RBFOX2_K562 --optimizer llm \
        --max-iter 8 --hours 4 --threads 32 --chr21 \
        --weight reproducibility=0.5 --weight motif=0.25 --weight recall=0.25 \
        --param pureclip.bandwidth_nt=20:100 --param postprocessing.force_width=3:15
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .launcher import DEFAULT_PURECLIP_DIR, launch_detached, overnight_command, write_manifest
from .schedule import ScheduleError, WEIGHT_KEYS, build_manifest


def _parse_param(values: list[str]) -> dict[str, dict[str, list[int]]]:
    """``section.key=lo:hi`` → ``{section: {key: [lo, hi]}}`` (nested bounds)."""
    bounds: dict[str, dict[str, list[int]]] = {}
    for raw in values:
        try:
            name, rng = raw.split("=", 1)
            section, key = name.split(".", 1)
            lo, hi = rng.split(":", 1)
            bounds.setdefault(section, {})[key] = [int(lo), int(hi)]
        except ValueError:
            raise SystemExit(f"error: --param must be section.key=lo:hi, got {raw!r}")
    return bounds


def _parse_weight(values: list[str]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for raw in values:
        try:
            name, val = raw.split("=", 1)
            weights[name] = float(val)
        except ValueError:
            raise SystemExit(f"error: --weight must be name=value, got {raw!r}")
    unknown = set(weights) - set(WEIGHT_KEYS)
    if unknown:
        raise SystemExit(f"error: unknown weight(s) {sorted(unknown)}; expected {list(WEIGHT_KEYS)}")
    return weights


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agentic-pureclip-run",
        description="Launch a PureCLIP parameter-search run (the CLI behind the dashboard Plan page).",
    )
    p.add_argument("--dataset", required=True, help="dataset id, e.g. RBFOX2_K562")
    p.add_argument("--optimizer", choices=("llm", "optuna"), default="llm")
    p.add_argument("--max-iter", type=int, default=8, help="iterations / trials (1-50)")
    p.add_argument("--hours", type=float, default=4.0, help="wall-clock budget (0.1-24)")
    p.add_argument("--threads", type=int, default=32, help="threads (1-64)")
    p.add_argument("--chr21", action=argparse.BooleanOptionalAction, default=True,
                   help="restrict to chr21 fast mode (default: on; use --no-chr21 for genome-wide)")
    p.add_argument("--weight", action="append", default=[], metavar="NAME=VALUE",
                   help="objective weight, repeatable: reproducibility|motif|recall")
    p.add_argument("--param", action="append", default=[], metavar="SECTION.KEY=LO:HI",
                   help="parameter to optimize with its search range, repeatable")
    p.add_argument("--pureclip-dir", default=DEFAULT_PURECLIP_DIR,
                   help="dir containing the pureclip2 binary (prepended to PATH)")
    p.add_argument("--dry-run", action="store_true",
                   help="validate and print the manifest + launch command, but don't launch")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    spec = {
        "dataset": args.dataset,
        "optimizer": args.optimizer,
        "max_iter": args.max_iter,
        "hours": args.hours,
        "threads": args.threads,
        "learn_on_chr21": args.chr21,
        "weights": _parse_weight(args.weight),
        "bounds": _parse_param(args.param),
    }
    try:
        job_id, manifest, meta = build_manifest(spec)
    except ScheduleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not Path("scripts/run/overnight_batch.py").exists():
        print("error: run this from the repo root (scripts/run/overnight_batch.py not found).",
              file=sys.stderr)
        return 2

    if args.dry_run:
        import yaml
        print(f"# job_id: {job_id}")
        print(yaml.safe_dump(manifest, sort_keys=False), end="")
        print("# would launch:")
        print("  " + " ".join(overnight_command(f"config/ui_runs/{job_id}.yaml",
                                                meta["hours"], args.pureclip_dir)))
        return 0

    manifest_path = write_manifest(job_id, manifest)
    log_path = launch_detached(job_id, manifest_path, meta["hours"], args.pureclip_dir)
    print(f"✓ launched {meta['optimizer'].upper()} run on {meta['dataset']} "
          f"({meta['max_iter']} iters, {meta['n_params']} parameter(s))")
    print(f"  job id:   {job_id}")
    print(f"  manifest: {manifest_path}")
    print(f"  log:      {log_path}   (follow with: tail -f {log_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
