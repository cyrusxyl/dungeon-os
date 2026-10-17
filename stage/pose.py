"""Poses made from a standing LPC frame, because the sprite sheet has no sitting art.

All humanoid frames are 64 px and built alike: the head is rows 13-33, the torso 33-48, the legs 48-62 (the
thigh is rows 48-54, the shin and foot rows 55-62). `sit` keeps everything above the hip and copies the shin
and foot rows as drawn, only moved. The thigh rows are sampled, never repeated, so a seated actor is never
taller than a standing one. Seen from the side, each thigh row is shifted forward a little more than the one
above, and the shin and foot hang from its end. Seen from the front or back, the thigh points at the viewer,
so it keeps fewer rows.
The result is 64 px wide and `SIT_H` high, and the hip stays on row `HIP`, so a stand point (the hip) maps to
the frame the same way for every pose.
"""

from __future__ import annotations

from PIL import Image

HIP = 48  # first leg row of a standing frame
FEET = 62  # last row of the feet
KNEE = 55  # first shin row
SIDE_ROWS = 4  # rows the thigh keeps in the side view
SHEAR = 8  # px the shin moves forward in the side view
FRONT_ROWS = 5  # rows the thigh keeps in the front view
SIT_H = 64  # a seated frame is never taller than a standing one


def _row(frame: Image.Image, y: int) -> Image.Image:
    return frame.crop((0, y, frame.width, y + 1))


def _base(frame: Image.Image) -> Image.Image:
    out = Image.new("RGBA", (frame.width, SIT_H))
    out.alpha_composite(frame.crop((0, 0, frame.width, HIP)))
    return out


def _thigh(frame: Image.Image, out: Image.Image, rows: int, shift: int) -> int:
    """Draw `rows` rows sampled from the thigh, each shifted a bit more toward `shift`. Returns the next free row."""
    for i in range(rows):
        out.alpha_composite(_row(frame, HIP + i * (KNEE - HIP) // rows), (round(shift * (i + 1) / rows), HIP + i))
    return HIP + rows


def _shin(frame: Image.Image, out: Image.Image, y: int, shift: int) -> None:
    for r in range(KNEE, FEET + 1):
        out.alpha_composite(_row(frame, r), (shift, y + r - KNEE))


def _side(frame: Image.Image) -> Image.Image:
    """Seated, facing right."""
    out = _base(frame)
    _shin(frame, out, _thigh(frame, out, SIDE_ROWS, SHEAR), SHEAR)
    return out


def sit(frame: Image.Image, facing: str = "down") -> Image.Image:
    """The actor seated, from a standing 64 px frame facing `down`, `up`, `left` or `right`."""
    if frame.size != (64, 64):
        return frame  # a monster tile: no joints, so it keeps standing
    if facing == "right":
        return _side(frame)
    if facing == "left":
        flip = Image.Transpose.FLIP_LEFT_RIGHT
        return _side(frame.transpose(flip)).transpose(flip)
    out = _base(frame)
    _shin(frame, out, _thigh(frame, out, FRONT_ROWS, 0), 0)
    return out
