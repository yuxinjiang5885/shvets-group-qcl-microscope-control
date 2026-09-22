"""Print bounded, hardware-independent GDS feature summaries.

Author: Yuxin Jiang
Email: yj546@cornell.edu
"""

import argparse

from experiment.gds_layout import load_gds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="GDS file to read without modification")
    parser.add_argument("--depth", type=int, default=1, help="Hierarchy levels below roots")
    parser.add_argument("--limit", type=int, default=100, help="Maximum children shown per parent")
    args = parser.parse_args()
    if args.depth < 0 or args.limit < 1:
        parser.error("depth must be nonnegative and limit must be positive")
    try:
        print(load_gds(args.source).summary(depth=args.depth, limit=args.limit))
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"GDS inspection failed: {error}\n")


if __name__ == "__main__":
    main()
