"""產生 App 圖示：深靛藍底上三條階級表色帶（S 紅、A 橘、B 黃）加一道白色斜槓，跟 App 左上角的標誌同一個圖形。"""
import pathlib

from PIL import Image, ImageDraw, ImageFilter

OUT = pathlib.Path(__file__).resolve().parent.parent / 'site' / 'icons'
BG_TOP, BG_BOT = (35, 40, 97), (17, 19, 54)
S_COL, A_COL, B_COL, INK = (255, 122, 138), (255, 174, 98), (255, 223, 110), (243, 242, 255)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw(size, maskable=False):
    S = 1024
    im = Image.new('RGB', (S, S))
    d = ImageDraw.Draw(im)
    for y in range(S):
        d.line([(0, y), (S, y)], fill=lerp(BG_TOP, BG_BOT, y / S))
    k = 0.62 if maskable else 0.8          # 圖形占畫面的比例
    u = S * k / 32                          # 對應 32×32 的標誌座標
    ox = oy = (S - 32 * u) / 2
    P = lambda pts: [(ox + x * u, oy + y * u) for x, y in pts]  # noqa: E731
    shapes = [((4, 6), (21, 6), (17, 12), (4, 12), S_COL), ((4, 14), (16, 14), (12, 20), (4, 20), A_COL),
              ((4, 22), (11, 22), (7, 28), (4, 28), B_COL), ((22, 8), (28, 8), (19, 26), (13, 26), INK)]
    sh = Image.new('L', (S, S), 0)
    sd = ImageDraw.Draw(sh)
    for *pts, col in shapes:
        sd.polygon([(x + 10, y + 18) for x, y in P(pts)], fill=150)
    sh = sh.filter(ImageFilter.GaussianBlur(22))
    im = Image.composite(Image.new('RGB', (S, S), (6, 7, 26)), im, sh)
    d = ImageDraw.Draw(im)
    for *pts, col in shapes:
        d.polygon(P(pts), fill=col)
    return im.resize((size, size), Image.LANCZOS)


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    draw(512).save(OUT / 'icon-512.png', optimize=True)
    draw(192).save(OUT / 'icon-192.png', optimize=True)
    draw(512, maskable=True).save(OUT / 'icon-maskable-512.png', optimize=True)
    draw(180).save(OUT / 'apple-touch-icon.png', optimize=True)
    draw(32).save(OUT / 'favicon-32.png', optimize=True)
    print('icons ok')
