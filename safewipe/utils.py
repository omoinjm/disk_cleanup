"""
utils.py — Common utility functions for safewipe.
"""

from typing import Optional

def format_bytes(n: int) -> str:
    """Format bytes to human-readable size (B, KB, MB, GB, TB, PB)."""
    if n == 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def format_speed(bps: float) -> str:
    """Format bytes per second as human-readable speed."""
    return format_bytes(int(bps)) + "/s"


def format_eta(seconds: Optional[float]) -> str:
    """Format seconds as human-readable time (s, m, h)."""
    if seconds is None:
        return "—"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"
