"""Convenience wrapper around backend.app.gcn.train.

Usage::

    python -m scripts.train_gcn --task friendliness
"""

from backend.app.gcn.train import main

if __name__ == "__main__":
    main()
