"""Isometrische Druckbett-Grafik für die Modellkarte in Blatt 01.

Zweck:   Zeichnet den Bauraum des Druckers als Kiste und das Modell als Quader mittig am Boden, dazu je drei Massketten
         für Bauraum (aussen, grau) und Modell (innen, in der Farbe des Urteils). Die Masszahlen sind HTML-Elemente,
         weil sie gedreht werden (X 30°, Y −30°, Z −90°); die Abstände sorgen dafür, dass keine Linie eine Zahl kreuzt.
         Reine Funktion ohne NiceGUI – so ist sie einzeln prüfbar (tests/test_bed_iso.py).
Eingabe: Bauraum und Modell je (X, Y, Z) in mm, Urteil «ok», «knapp» oder «gross» (ui.model_info.fit_class)
Ausgabe: HTML-Text: <div> 374 × 224 px mit dem <svg> und den sechs Masszahlen als <span>
"""

C, S, W, H, PAD = 0.866, 0.5, 374, 224, 18
COLORS = {  # Oberseite, linke Seite, rechte Seite, Linie
    "ok": ("#CDEBE5", "#8ED2C6", "#6CC0B2", "#0E8F7E"),
    "knapp": ("#F6E2C1", "#EBC27F", "#DDA85A", "#B4690E"),
    "gross": ("#F6CDCE", "#EC9DA0", "#E07E82", "#D03B40"),
}


def _raw(x, y, z):
    """Isometrische Projektion eines Punktes (vor Massstab und Verschiebung)."""
    return ((x - y) * C, (x + y) * S - z)


def bed_iso_svg(bed: tuple[float, float, float], model: tuple[float, float, float], level: str) -> str:
    """Bauraum ``bed`` und Modell ``model`` (je X, Y, Z in mm) als Isometrie; ``level`` färbt das Modell."""
    bx, by, bz = bed
    mx, my, mz = model
    x0, y0 = (bx - mx) / 2, (by - my) / 2          # Modell mittig am Boden
    x1, y1 = x0 + mx, y0 + my
    o = 0.09 * max(bx, by, bz)                       # Abstand Masskette Modell
    o2, e, lo = 4.2 * o, 0.3 * o, 1.6 * o            # Masskette Bauraum, Überstand Hilfslinie, Abstand Zahl
    # (linie_a, linie_b, hilfslinien, zahl_punkt, drehung_grad, wert, ist_bauraum, x_versatz_px)
    dims = [
        ((x0, by + o, 0), (x1, by + o, 0), [((x0, y1, 0), (x0, by + o + e, 0)), ((x1, y1, 0), (x1, by + o + e, 0))],
         [(x0 + x1) / 2, by + o + lo, 0], 30, mx, False, 0),
        ((0, by + o2, 0), (bx, by + o2, 0), [((0, by, 0), (0, by + o2 + e, 0)), ((bx, by, 0), (bx, by + o2 + e, 0))],
         [bx / 2, by + o2 + lo, 0], 30, bx, True, 0),
        ((bx + o, y0, 0), (bx + o, y1, 0), [((x1, y0, 0), (bx + o + e, y0, 0)), ((x1, y1, 0), (bx + o + e, y1, 0))],
         [bx + o + lo, (y0 + y1) / 2, 0], -30, my, False, 0),
        ((bx + o2, 0, 0), (bx + o2, by, 0), [((bx, 0, 0), (bx + o2 + e, 0, 0)), ((bx, by, 0), (bx + o2 + e, by, 0))],
         [bx + o2 + lo, by / 2, 0], -30, by, True, 0),
        ((bx + o, -o, 0), (bx + o, -o, mz), [((x1, y0, mz), (bx + o + e, -o - e, mz)), ((bx, 0, 0), (bx + o + e, -o - e, 0))],
         [bx + o, -o, mz / 2], -90, mz, False, 12),
        ((-o2, by, 0), (-o2, by, bz), [((0, by, 0), (-o2 - e, by, 0)), ((0, by, bz), (-o2 - e, by, bz))],
         [-o2, by, bz / 2], -90, bz, True, -12),
    ]
    pts = [_raw(x, y, z) for x in (0, bx, x0, x1) for y in (0, by, y0, y1) for z in (0, max(bz, mz))]
    for d in dims:
        pts += [_raw(*d[0]), _raw(*d[1]), _raw(*d[3])]
    min_x, max_x = min(p[0] for p in pts), max(p[0] for p in pts)
    min_y, max_y = min(p[1] for p in pts), max(p[1] for p in pts)
    s = min((W - 2 * PAD) / (max_x - min_x), (H - 2 * PAD) / (max_y - min_y))
    ox = (W - (max_x - min_x) * s) / 2 - min_x * s
    oy = (H - (max_y - min_y) * s) / 2 - min_y * s
    dims[4][3][2] = max(mz / 2, 31 / s)              # Höhenzahl Modell frei über der Bodenkante

    def p(q):
        r = _raw(*q)
        return r[0] * s + ox, r[1] * s + oy

    def pt(q):
        x, y = p(q)
        return f"{x:.1f} {y:.1f}"

    def poly(a):
        return "M" + "L".join(pt(q) for q in a) + "Z"

    def seg(a, b):
        return f"M{pt(a)}L{pt(b)}"

    def tick(q):
        x, y = p(q)
        return f"M{x - 2:.1f} {y + 2:.1f}L{x + 2:.1f} {y - 2:.1f}"

    def chain(is_bed):
        return "".join(seg(d[0], d[1]) + "".join(seg(a, b) for a, b in d[2]) + tick(d[0]) + tick(d[1])
                       for d in dims if d[6] == is_bed)

    top, left, right, line = COLORS[level]
    floor = poly([(0, 0, 0), (bx, 0, 0), (bx, by, 0), (0, by, 0)])
    back = seg((0, 0, 0), (0, 0, bz)) + seg((0, 0, 0), (bx, 0, 0)) + seg((0, 0, 0), (0, by, 0))
    front = "".join(seg(a, b) for a, b in [((bx, 0, 0), (bx, 0, bz)), ((0, by, 0), (0, by, bz)), ((bx, by, 0), (bx, by, bz)),
        ((0, 0, bz), (bx, 0, bz)), ((bx, 0, bz), (bx, by, bz)), ((bx, by, bz), (0, by, bz)), ((0, by, bz), (0, 0, bz))])
    m_top = poly([(x0, y0, mz), (x1, y0, mz), (x1, y1, mz), (x0, y1, mz)])
    m_left = poly([(x0, y1, 0), (x1, y1, 0), (x1, y1, mz), (x0, y1, mz)])
    m_right = poly([(x1, y0, 0), (x1, y1, 0), (x1, y1, mz), (x1, y0, mz)])
    svg = (f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" style="display:block">'
           f'<path d="{floor}" fill="#ECE8E0" stroke="#FF6B2C" stroke-width="1.2"/>'
           f'<path d="{back}" fill="none" stroke="#8A8E95" stroke-width="1" stroke-dasharray="3 3"/>'
           f'<path d="{m_right}" fill="{right}" stroke="{line}" stroke-width="1" stroke-linejoin="round"/>'
           f'<path d="{m_left}" fill="{left}" stroke="{line}" stroke-width="1" stroke-linejoin="round"/>'
           f'<path d="{m_top}" fill="{top}" stroke="{line}" stroke-width="1" stroke-linejoin="round"/>'
           f'<path d="{front}" fill="none" stroke="#5E6269" stroke-width="1"/>'
           f'<path d="{chain(True)}" fill="none" stroke="#8A8E95" stroke-width="0.8"/>'
           f'<path d="{chain(False)}" fill="none" stroke="{line}" stroke-width="0.8"/>'
           '</svg>')
    labels = ""
    for d in dims:
        x, y = p(d[3])
        color = "#5E6269" if d[6] else line
        font = "400 10px/1 'IBM Plex Mono',monospace" if d[6] else "600 10.5px/1 'IBM Plex Mono',monospace"
        labels += (f'<span style="position:absolute;left:{x + d[7]:.1f}px;top:{y:.1f}px;'
                   f'transform:translate(-50%,-50%) rotate({d[4]}deg);font:{font};color:{color};'
                   f'white-space:nowrap;pointer-events:none">{round(d[5])} mm</span>')
    return f'<div style="position:relative;width:{W}px;height:{H}px">{svg}{labels}</div>'
