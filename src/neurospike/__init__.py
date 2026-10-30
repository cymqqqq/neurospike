"""NeuroSpike: reproducible offline action-potential measurements."""

# pyABF imports pyplot indirectly; keep its backend independent of the Qt GUI.
import os

os.environ.setdefault("MPLBACKEND", "Agg")

__version__ = "0.1.0"
