import argparse

from pipeline.configs import save_config, validate_config
from pipeline.datasets import dataset_to_config, list_datasets


def main():
    parser = argparse.ArgumentParser(description="Write a run config for a local data/ dataset.")
    parser.add_argument("dataset", choices=list_datasets())
    parser.add_argument("--out", default=None, help="Output YAML path. Defaults to config/datasets/<dataset>.yaml")
    parser.add_argument("--results-root", default="results/datasets")
    parser.add_argument("--no-input-covariate", action="store_true")
    args = parser.parse_args()

    cfg = dataset_to_config(
        args.dataset,
        results_root=args.results_root,
        use_input_covariate=not args.no_input_covariate,
    )
    validate_config(cfg)
    out = args.out or f"config/datasets/{args.dataset}.yaml"
    save_config(cfg, out)
    print(out)


if __name__ == "__main__":
    main()
