"""Key out a generated illustration's chroma-green background, crop and downscale.

gpt-image-2 draws a checkerboard instead of real transparency, so the art is generated on
#00FF00 and keyed here. Usage: python tools/cutout.py IN.png OUT.png [max_side]
"""

import sys

from PIL import Image


def main() -> None:
    src, out = sys.argv[1], sys.argv[2]
    side = int(sys.argv[3]) if len(sys.argv) > 3 else 320
    im = Image.open(src).convert("RGBA")
    data = []
    for r, g, b, _ in im.getdata():
        # How much greener than the other channels: small = subject, large = background.
        spill = g - max(r, b)
        alpha = 255 if spill < 40 else 0 if spill > 120 else int(255 * (120 - spill) / 80)
        if spill > 0:
            g = max(r, b)  # remove green spill on the edges
        data.append((r, g, b, alpha))
    im.putdata(data)
    im = im.crop(im.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox())
    im.thumbnail((side, side), Image.LANCZOS)
    im.save(out, optimize=True)
    print(out, im.size)


if __name__ == "__main__":
    main()
