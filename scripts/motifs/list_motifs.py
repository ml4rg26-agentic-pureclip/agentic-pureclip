#!/usr/bin/env python3
"""List available motif databases, RBPs, and loaded motifs.

Usage:
    python scripts/motifs/list_motifs.py                    # list all databases and RBPs
    python scripts/motifs/list_motifs.py --rbp RBFOX2        # show motifs for a specific RBP
    python scripts/motifs/list_motifs.py --db mCrossBase     # show all RBPs in a database
    python scripts/motifs/list_motifs.py --rbp RBFOX2 --cell K562  # cell-line specific
"""

import argparse
import json
import sys

from agentic_pureclip.pipeline.motifs import (
    available_databases,
    available_rbps,
    get_best_motif,
    load_all_motifs,
    load_motifs_for_rbp,
)


def main():
    parser = argparse.ArgumentParser(description="Explore the integrated motif database.")
    parser.add_argument("--rbp", help="Filter by RBP name")
    parser.add_argument("--db", help="Filter by database name")
    parser.add_argument("--cell", help="Filter by cell line")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    dbs = available_databases()

    if not dbs:
        print("No motif databases found.")
        print(f"Place transfac files in: data/motifs/{{database}}/{{RBP}}/{{cell_line}}/*.transfac")
        print("Example: data/motifs/mCrossBase/RBFOX2/K562/motif.transfac")
        return

    if args.json:
        result = {
            "databases": dbs,
            "rbps_by_db": available_rbps(),
        }
        if args.rbp:
            result["motifs"] = {}
            for db in dbs:
                entries = load_motifs_for_rbp(db, args.rbp, args.cell)
                if entries:
                    result["motifs"][db] = [
                        {
                            "pattern": e.pattern,
                            "type": e.type,
                            "motif_id": e.pwm.motif_id if e.pwm else None,
                            "consensus": e.pwm.consensus if e.pwm else None,
                            "length": e.pwm.length if e.pwm else None,
                        }
                        for e in entries
                    ]
        print(json.dumps(result, indent=2))
    else:
        print("=" * 70)
        print("MOTIF DATABASES")
        print("=" * 70)
        for db in dbs:
            rbps = sorted(available_rbps().get(db, []))
            print(f"\n  {db}/ ({len(rbps)} RBPs)")
            for rbp in rbps:
                print(f"    - {rbp}")

        if args.rbp:
            print(f"\n{'=' * 70}")
            print(f"MOTIFS FOR {args.rbp}" + (f" ({args.cell})" if args.cell else ""))
            print("=" * 70)
            all_entries = load_all_motifs(args.rbp, args.cell)
            for db, entries in all_entries.items():
                print(f"\n  [{db}]")
                for e in entries:
                    pwm_info = ""
                    if e.pwm:
                        pwm_info = f"  PWM: {e.pwm.motif_id} (len={e.pwm.length}, consensus={e.pwm.consensus})"
                    print(f"    pattern={e.pattern}  type={e.type}{pwm_info}")

            best = get_best_motif(args.rbp, args.cell)
            if best:
                print(f"\n  → Best motif: {best.pattern}" +
                      (f" (from {best.source_database})" if best.source_database else ""))


if __name__ == "__main__":
    main()
