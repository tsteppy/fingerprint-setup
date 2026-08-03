"""Draws which enrolment positions have been completed.

This shows *instructed* coverage. fprintd never reports where a press
actually landed, so a filled zone means "you were asked to press there and
the device accepted it" -- not that the reader confirmed that part of the
finger was captured. The label in the UI says "Positions completed" for
exactly this reason.
"""

import math

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

# (x, y, radius) in a 0..1 space over the fingertip drawing.
ZONE_LAYOUT: dict[str, tuple[float, float, float]] = {
    "centre": (0.50, 0.50, 0.15),
    "top": (0.50, 0.26, 0.14),
    "bottom": (0.50, 0.75, 0.14),
    "left": (0.24, 0.50, 0.13),
    "right": (0.76, 0.50, 0.13),
    "roll-left": (0.28, 0.71, 0.12),
    "roll-right": (0.72, 0.71, 0.12),
    "centre-2": (0.50, 0.92, 0.10),
}


class FingertipMap(Gtk.DrawingArea):
    def __init__(self) -> None:
        super().__init__()
        self._completed: list[str] = []
        self._target: str | None = None
        self.set_content_width(200)
        self.set_content_height(250)
        self.set_draw_func(self._draw)

    def set_completed(self, zones: list[str]) -> None:
        self._completed = list(zones)
        self.queue_draw()

    def set_target(self, zone: str | None) -> None:
        self._target = zone
        self.queue_draw()

    def _draw(self, _area, cr, width: int, height: int) -> None:
        style = self.get_style_context()
        accent = style.lookup_color("accent_bg_color")
        success = style.lookup_color("success_color")
        dim = style.lookup_color("insensitive_fg_color")

        accent_rgba = accent[1] if accent[0] else None
        success_rgba = success[1] if success[0] else None
        dim_rgba = dim[1] if dim[0] else None

        # fingertip outline
        cr.save()
        cr.translate(width / 2, height / 2)
        cr.scale(width * 0.36, height * 0.44)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        if dim_rgba:
            cr.set_source_rgba(dim_rgba.red, dim_rgba.green, dim_rgba.blue, 0.25)
        else:
            cr.set_source_rgba(0.5, 0.5, 0.5, 0.25)
        cr.set_line_width(2)
        cr.stroke()

        for zone, (zx, zy, zr) in ZONE_LAYOUT.items():
            cx, cy, r = zx * width, zy * height, zr * min(width, height)
            cr.arc(cx, cy, r, 0, 2 * math.pi)

            if zone in self._completed:
                if success_rgba:
                    cr.set_source_rgba(
                        success_rgba.red, success_rgba.green, success_rgba.blue, 0.85
                    )
                else:
                    cr.set_source_rgba(0.18, 0.49, 0.36, 0.85)
                cr.fill()
            elif zone == self._target:
                if accent_rgba:
                    cr.set_source_rgba(accent_rgba.red, accent_rgba.green, accent_rgba.blue, 1)
                else:
                    cr.set_source_rgba(0.29, 0.52, 0.89, 1)
                cr.set_line_width(3)
                cr.stroke()
            else:
                if dim_rgba:
                    cr.set_source_rgba(dim_rgba.red, dim_rgba.green, dim_rgba.blue, 0.35)
                else:
                    cr.set_source_rgba(0.5, 0.5, 0.5, 0.35)
                cr.set_line_width(1.5)
                cr.set_dash([4, 4])
                cr.stroke()
                cr.set_dash([])
