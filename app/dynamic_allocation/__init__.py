"""Point-in-time dynamic allocation research components.

The package is research-only. It never connects to a broker or executes orders.
"""

from .contracts import PointInTimeObservation

__all__ = ["PointInTimeObservation"]
