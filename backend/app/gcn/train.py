"""Training entrypoints for the two GNN tasks.

Run::

    python -m backend.app.gcn.train --task friendliness
    python -m backend.app.gcn.train --task match

Skeleton only. Member A fills in dataset assembly + optimisation loops.
"""

from __future__ import annotations

import argparse


def train_friendliness() -> None:
    raise NotImplementedError("Week 3 deliverable. See model.py / docs/proposal.md §4-Module 2.")


def train_match() -> None:
    raise NotImplementedError("Week 3 deliverable.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=["friendliness", "match"], required=True)
    args = parser.parse_args()
    if args.task == "friendliness":
        train_friendliness()
    else:
        train_match()


if __name__ == "__main__":
    main()
