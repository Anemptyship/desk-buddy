from pathlib import Path

import numpy as np


def hlg_to_srgb(encoded: np.ndarray):
    """BT.2100 inverse HLG OETF, BT.2020→709, fixed Hable viewing transform.

    A fixed exposure avoids per-frame auto-exposure flicker. This is an SDR
    analysis viewing transform, not a Dolby Vision mastering reproduction.
    """
    a, b, c = .17883277, .28466892, .55991073
    linear = np.where(encoded <= .5, encoded**2 / 3,
                      (np.exp((encoded-c)/a) + b) / 12)
    matrix = np.array([[1.660491, -.587641, -.072850],
                       [-.124550, 1.132900, -.008349],
                       [-.018151, -.100579, 1.118730]])
    linear = np.maximum(linear @ matrix.T, 0)

    def hable(x):
        return ((x*(.15*x+.05)+.004)/(x*(.15*x+.5)+.06)) - .02/.3

    mapped = np.clip(hable(linear * 8) / hable(11.2), 0, 1)
    return np.where(mapped <= .0031308, 12.92*mapped, 1.055*mapped**(1/2.4)-.055)


def write_hlg_lut(path: Path, size=33):
    lines = ['TITLE "DESK BUDDY fixed HLG2020 to SDR sRGB"', f"LUT_3D_SIZE {size}",
             "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    values = np.linspace(0, 1, size)
    # .cube ordering: red changes fastest.
    rgb = np.array([[r, g, b] for b in values for g in values for r in values])
    lines.extend("%.7f %.7f %.7f" % tuple(v) for v in hlg_to_srgb(rgb))
    path.write_text("\n".join(lines) + "\n")
