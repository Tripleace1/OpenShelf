"""Draw the OpenShelf icon (same design as web/icon.svg) as a Windows .ico.

    python packaging/make_icon.py        (needs Pillow: pip install pillow)
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "openshelf.ico")


def draw(size=256):
    s = size / 64.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # blue -> navy diagonal gradient, clipped to a rounded square
    grad = Image.new("RGBA", (size, size))
    gp = grad.load()
    a, b = (0x16, 0x52, 0xC8), (0x0B, 0x2A, 0x5B)
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            gp[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=14 * s, fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    r = 2 * s
    d.rounded_rectangle([13 * s, 14 * s, 21 * s, 48 * s], radius=r, fill="#ffffff")
    d.rounded_rectangle([24 * s, 18 * s, 32 * s, 48 * s], radius=r, fill="#cfe0ff")

    # tilted third book
    book = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(book).rounded_rectangle([35 * s, 15 * s, 42 * s, 48 * s], radius=r, fill="#ffffff")
    book = book.rotate(-14, center=(38 * s, 32 * s), resample=Image.BICUBIC)
    img.alpha_composite(book)

    d.rounded_rectangle([10 * s, 49 * s, 54 * s, 53 * s], radius=r, fill="#e63946")   # red shelf
    return img


if __name__ == "__main__":
    big = draw(256)
    big.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", OUT)
