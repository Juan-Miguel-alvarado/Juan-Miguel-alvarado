"""Renders terminal.gif: a fake terminal session typed over a wallpaper.

    python make_gif.py [background image] [-o out.gif]

Needs pillow, qrcode and pyfiglet. Edit SCRIPT at the bottom to change what gets typed.
"""
import argparse
import random
from pathlib import Path

import pyfiglet
import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
FONT_DIR = Path("/usr/share/fonts/TTF")
FONT = FONT_DIR / "JetBrainsMonoNerdFontMono-Regular.ttf"
FONT_BOLD = FONT_DIR / "JetBrainsMonoNerdFontMono-Bold.ttf"

W, H = 840, 540
RADIUS = 12
TITLE_H = 34
PAD_X, PAD_Y = 20, 14
FONT_SIZE = 15
LINE_H = 20

COLORS = {
    "fg": (236, 236, 236),
    "out": (206, 206, 206),
    "dim": (140, 140, 140),
    "faint": (96, 96, 96),
    "bold": (255, 255, 255),
}
PROFILE_URL = "github.com/Juan-Miguel-alvarado"

random.seed(7)


# ---------------------------------------------------------------- background

def cover(img, w, h):
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))


def build_background(path):
    """Wallpaper, darkened towards the left where the text lives."""
    body_h = H - TITLE_H
    wall = cover(Image.open(path).convert("RGB"), W, body_h)
    wall = wall.filter(ImageFilter.GaussianBlur(0.6))

    # horizontal shade: ~78% black on the left, ~25% on the right, plus a top vignette
    shade = Image.new("L", (W, body_h))
    px = shade.load()
    for x in range(W):
        t = x / (W - 1)
        base = 205 - 185 * (t ** 1.3)
        for y in range(body_h):
            v = base + max(0, 40 - y) * 1.5
            px[x, y] = int(min(235, v))
    black = Image.new("RGB", (W, body_h), (6, 6, 8))
    wall = Image.composite(black, wall, shade)

    win = Image.new("RGB", (W, H), (22, 22, 24))
    win.paste(wall, (0, TITLE_H))
    return win


def draw_chrome(win):
    """Title bar, traffic lights and border. Drawn after quantizing the wallpaper so
    the small colored dots keep their exact palette entries."""
    d = ImageDraw.Draw(win)
    d.rectangle((0, 0, W, TITLE_H - 1), fill=(30, 30, 32))
    d.line((0, TITLE_H - 1, W, TITLE_H - 1), fill=(48, 48, 50))
    for i, c in enumerate(TRAFFIC):
        cx, cy = 22 + i * 20, TITLE_H // 2
        d.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=c)
    font = ImageFont.truetype(str(FONT_BOLD), 12)
    title = "alva@arch: ~"
    tw = d.textlength(title, font=font)
    d.text(((W - tw) / 2, TITLE_H / 2), title, font=font, fill=(150, 150, 152), anchor="lm")
    # 1px inner border
    d.rounded_rectangle((0, 0, W - 1, H - 1), RADIUS, outline=(58, 58, 60))
    return win


def corner_mask():
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, W - 1, H - 1), RADIUS, fill=255)
    return m.point(lambda v: 255 if v > 127 else 0)


# ---------------------------------------------------------------- terminal model

class Term:
    def __init__(self, bg):
        self.bg = bg
        self.lines = [[]]          # each line: list of (text, style)
        self.frames = []           # (rgba overlay drawer args, duration ms)
        self.font = ImageFont.truetype(str(FONT), FONT_SIZE)
        self.font_bold = ImageFont.truetype(str(FONT_BOLD), FONT_SIZE)
        self.cw = self.font.getlength("M")
        self.rows = (H - TITLE_H - 2 * PAD_Y) // LINE_H
        self.overlay = None        # (image, xy) drawn on top, e.g. the QR card

    # -- state helpers
    def _scroll(self):
        while len(self.lines) > self.rows:
            self.lines.pop(0)

    def write(self, text, style="out"):
        self.lines[-1].append((text, style))

    def newline(self):
        self.lines.append([])
        self._scroll()

    def prompt(self):
        self.write("alva", "bold")
        self.write("@arch ", "dim")
        self.write("~ ", "fg")
        self.write("❯ ", "bold")

    # -- rendering
    def render(self, cursor=True):
        img = self.bg.copy()
        d = ImageDraw.Draw(img)
        y = TITLE_H + PAD_Y
        for i, line in enumerate(self.lines):
            x = PAD_X
            for text, style in line:
                f = self.font_bold if style == "bold" else self.font
                d.text((x, y), text, font=f, fill=COLORS[style])
                x += self.cw * len(text)
            if cursor and i == len(self.lines) - 1:
                d.rectangle((x + 1, y + 2, x + self.cw, y + LINE_H - 3), fill=COLORS["fg"])
            y += LINE_H
        if self.overlay:
            ov, xy = self.overlay
            img.paste(ov, xy, ov)
        return img

    def snap(self, ms, cursor=True):
        self.frames.append((self.render(cursor), ms))

    # -- actions
    def idle(self, ms, blink=530):
        # browsers stretch GIF delays under 20ms to 100ms, so fold remainders in
        n = max(1, round(ms / blink))
        for i in range(n):
            self.snap(ms // n, cursor=i % 2 == 0)

    def type(self, cmd):
        self.prompt()
        self.idle(700)
        for ch in cmd:
            self.write(ch, "fg")
            # human rhythm: quick inside words, slower on spaces/punctuation
            ms = random.choice([40, 50, 60, 70]) + (60 if ch in " -|./" else 0)
            self.snap(ms)
        self.idle(350, blink=350)
        self.newline()

    def out(self, *lines, ms=45):
        """Each line is a str or a list of (text, style) spans."""
        for line in lines:
            spans = [(line, "out")] if isinstance(line, str) else line
            for text, style in spans:
                self.write(text, style)
            self.newline()
            self.snap(ms, cursor=False)

    def clear(self):
        self.type("clear")
        self.lines = [[]]
        self.snap(120)


# ---------------------------------------------------------------- content helpers

ARCH = [
    "       /\\       ",
    "      /  \\      ",
    "     /\\   \\     ",
    "    /      \\    ",
    "   /   ,,   \\   ",
    "  /   |  |  -\\  ",
    " /_-''    ''-_\\ ",
]


def fetch_lines():
    info = [
        [("alva", "bold"), ("@", "dim"), ("arch", "bold")],
        [("─" * 30, "faint")],
        [("os      ", "dim"), ("Arch Linux x86_64", "out")],
        [("wm      ", "dim"), ("Hyprland (lua config)", "out")],
        [("term    ", "dim"), ("kitty", "out")],
        [("shell   ", "dim"), ("bash", "out")],
        [("theme   ", "dim"), ("monochrome · matugen", "out")],
        [("langs   ", "dim"), ("rust · typescript · python · dart", "out")],
        [("", "out")],
        [("        ", "out")] + [("███", s) for s in ("bold", "fg", "out", "dim", "faint")],
    ]
    logo = ARCH + [" " * 16] * (len(info) - len(ARCH))
    return [[("  " + l, "bold")] + [("  ", "out")] + i for l, i in zip(logo, info)]


def projects():
    rows = [
        ("wisp", "rust", "yazi-compatible file manager, 6-14x faster startup"),
        ("why-cli", "rust", "git blame that answers why, not just who"),
        ("footballbot", "python", "discord bot: crest trivia, live scores, standings"),
        ("chess-coach", "ts", "chess.com + lichess stats for chess teachers"),
        ("chess-analyzer", "ts", "in-browser stockfish analysis with move ratings"),
        ("quizlive", "ts", "real-time quizzes · react + socket.io + prisma"),
        ("mono-favicons", "js", "chromium ext: every favicon in black and white"),
    ]
    out = []
    for name, lang, desc in rows:
        out.append([(f"{name + '/':<16}", "bold"), (f"{lang:<8}", "dim"), (desc, "out")])
    return out


def banner():
    art = pyfiglet.figlet_format("alva!", font="ansi_shadow").rstrip("\n").split("\n")
    lines = []
    for l in art:
        if not l.strip():
            continue
        spans = []
        for ch in l:
            style = "bold" if ch == "█" else "faint"
            if spans and spans[-1][1] == style:
                spans[-1] = (spans[-1][0] + ch, style)
            else:
                spans.append((ch, style))
        lines.append(spans)
    return lines


def qr_card(size=196):
    q = qrcode.QRCode(border=2, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data("https://" + PROFILE_URL)
    q.make(fit=True)
    m = q.make_image(fill_color=(14, 14, 16), back_color=(236, 236, 236)).convert("RGB")
    m = m.resize((size, size), Image.NEAREST)
    card = Image.new("RGBA", (size + 20, size + 44), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 0, card.width - 1, card.height - 1), 10, fill=(236, 236, 236, 255))
    card.paste(m, (10, 10))
    f = ImageFont.truetype(str(FONT_BOLD), 12)
    label = "scan me"
    d.text(((card.width - d.textlength(label, font=f)) / 2, size + 16), label, font=f, fill=(14, 14, 16))
    return card


def slide_in(t, card, ms_total=500, steps=10):
    x_end = W - card.width - 34
    y = TITLE_H + (H - TITLE_H - card.height) // 2
    for i in range(1, steps + 1):
        k = 1 - (1 - i / steps) ** 3      # ease-out cubic
        x = round(W + (x_end - W) * k)
        t.overlay = (card, (x, y))
        t.snap(ms_total // steps, cursor=False)


# ---------------------------------------------------------------- script

def script(t):
    t.idle(1100)
    t.type("whoami")
    t.out(*banner(), ms=60)
    t.out("", [("builder on arch linux · ", "dim"), ("i do whatever the problem calls for", "out")], "")
    t.idle(1600)

    t.type("fastfetch")
    t.out("", *fetch_lines(), "", ms=55)
    t.idle(2600)
    t.clear()

    t.type("ls ~/projects --featured")
    t.out(*projects(), "", ms=70)
    t.idle(2600)

    t.type("cat stack.txt")
    t.out(
        [("web     ", "dim"), ("react · vite · tailwind · supabase · socket.io", "out")],
        [("native  ", "dim"), ("rust · flutter", "out")],
        [("daily   ", "dim"), ("arch · hyprland · kitty · git", "out")],
        "",
        ms=70,
    )
    t.idle(2600)
    t.clear()

    t.type('echo "thanks for visiting"')
    t.out("thanks for visiting", "")
    t.idle(600)
    t.type(f"open {PROFILE_URL}")
    t.out([("→ ", "dim"), (PROFILE_URL, "bold")], "")
    slide_in(t, qr_card())
    t.idle(5200)


TRAFFIC = [(255, 95, 87), (254, 188, 46), (40, 200, 64)]
BG_COLORS = 216


def quantize_background(bg):
    """Dither the wallpaper once into BG_COLORS colors, then append a grey ramp for
    antialiased text plus the chrome colors. Frames are mapped to this palette without
    dithering, so untouched background pixels come out identical in every frame."""
    q = bg.quantize(colors=BG_COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    pal = q.getpalette()[: BG_COLORS * 3]
    extra = [(v, v, v) for v in range(4, 256, 8)] + TRAFFIC  # 32 + 3
    for c in extra:
        pal += list(c)
    pal += [0, 0, 0] * (255 - len(pal) // 3) + [255, 0, 255]  # index 255 = transparent corners
    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette(pal)
    return q.convert("RGB"), pal_img


def save_gif(frames, pal_img, out):
    mask = corner_mask()
    out_frames, durations = [], []
    for img, ms in frames:
        p = img.quantize(palette=pal_img, dither=Image.Dither.NONE)
        p.paste(255, mask=Image.eval(mask, lambda v: 255 - v))
        if out_frames and ms and p.tobytes() == out_frames[-1].tobytes():
            durations[-1] += ms
            continue
        out_frames.append(p)
        durations.append(ms)

    out_frames[0].save(
        out, save_all=True, append_images=out_frames[1:], duration=durations,
        loop=0, transparency=255, disposal=1, optimize=False,
    )
    print(f"{out}: {len(out_frames)} frames, {sum(durations) / 1000:.1f}s, "
          f"{Path(out).stat().st_size / 1e6:.2f} MB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("background", nargs="?", default=HERE / "bg.jpg")
    ap.add_argument("-o", "--out", default=HERE / "terminal.gif")
    args = ap.parse_args()
    bg, pal_img = quantize_background(build_background(args.background))
    draw_chrome(bg)
    t = Term(bg)
    script(t)
    save_gif(t.frames, pal_img, args.out)


if __name__ == "__main__":
    main()
