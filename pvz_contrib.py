"""
Zombie Contribution Eater — a "snake game" style animation (same concept as
Platane/snk) but the mover is a zombie chewing through your GitHub
contribution graph instead of a snake.

Key differences from a naive version:
  - The zombie's path visits EVERY cell of the full graph in a proper
    boustrophedon (snake) order — same traversal snk uses.
  - Movement is smoothly interpolated between cells (not a per-cell jump),
    so it actually looks like it's crawling.
  - Eaten cells shrink/fade out over a few frames instead of vanishing
    instantly — gives the "eating" feel.
  - A short zombie trail follows behind for motion feedback.

Usage:
    python3 zombie_contrib.py <github_username> <output.gif>
"""

import sys
import re
import requests
from datetime import datetime
from PIL import Image, ImageDraw

CELL = 12
GAP = 2
STEP_FRAMES = 5       # animation frames per cell-to-cell move (higher = smoother/slower)
SCALE = 2             # final upscale for crisp pixel look
FPS = 18

BG = (13, 17, 13)
EMPTY_CELL = (35, 40, 38)
LEVEL_COLORS = [
    (35, 40, 38),
    (60, 110, 60),
    (60, 150, 65),
    (70, 190, 75),
    (90, 230, 95),
]
ZOMBIE_HEAD = (150, 190, 90)
ZOMBIE_HEAD_DARK = (95, 130, 55)
ZOMBIE_EYE = (230, 40, 40)
TRAIL_COLOR = (110, 150, 70)
EATEN_FLASH = (230, 240, 200)


def fetch_contributions(username: str):
    url = f"https://github.com/users/{username}/contributions"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    html = resp.text
    pattern = r'data-date="([\d-]+)"[^>]*id="contribution-day-component[^"]*"[^>]*data-level="(\d)"'
    matches = re.findall(pattern, html)
    if not matches:
        raise RuntimeError("Could not parse contribution data — GitHub markup may have changed.")
    return [{"date": d, "level": int(lv)} for d, lv in matches]


def to_grid(days):
    cols = []
    col = [None] * 7
    for d in days:
        dt = datetime.strptime(d["date"], "%Y-%m-%d")
        weekday = (dt.weekday() + 1) % 7  # Sun=0..Sat=6
        if weekday == 0 and any(c is not None for c in col):
            cols.append(col)
            col = [None] * 7
        col[weekday] = d["level"]
    cols.append(col)
    for c in cols:
        for i in range(7):
            if c[i] is None:
                c[i] = 0
    return cols


def boustrophedon_path(n_cols, n_rows):
    """Snake-style traversal: down a column, up the next, etc. — same as snk."""
    path = []
    for c in range(n_cols):
        rows = range(n_rows) if c % 2 == 0 else range(n_rows - 1, -1, -1)
        for r in rows:
            path.append((c, r))
    return path


def cell_center(c, r):
    x = c * (CELL + GAP) + CELL // 2
    y = r * (CELL + GAP) + CELL // 2
    return x, y


def draw_cell(draw, c, r, color, eaten_progress=0.0):
    x0 = c * (CELL + GAP)
    y0 = r * (CELL + GAP)
    if eaten_progress > 0:
        shrink = int((CELL / 2) * eaten_progress)
        x0 += shrink
        y0 += shrink
        size = CELL - shrink * 2
        if size <= 0:
            return
        draw.rectangle([x0, y0, x0 + size, y0 + size], fill=color)
    else:
        draw.rectangle([x0, y0, x0 + CELL, y0 + CELL], fill=color)


def draw_zombie(draw, x, y, wobble):
    r = CELL * 0.62
    bob = 1 if wobble else 0
    draw.ellipse([x - r, y - r + bob, x + r, y + r + bob], fill=ZOMBIE_HEAD, outline=ZOMBIE_HEAD_DARK)
    eye_off = r * 0.4
    for sign in (-1, 1):
        ex = x + sign * eye_off
        ey = y - r * 0.15 + bob
        draw.ellipse([ex - 1.6, ey - 1.6, ex + 1.6, ey + 1.6], fill=ZOMBIE_EYE)
    # jagged mouth
    draw.line([x - r * 0.5, y + r * 0.35 + bob, x - r * 0.2, y + r * 0.55 + bob,
               x + r * 0.1, y + r * 0.3 + bob, x + r * 0.4, y + r * 0.55 + bob],
              fill=ZOMBIE_HEAD_DARK, width=2)


def render(username, out_path, max_weeks=None):
    days = fetch_contributions(username)
    grid = to_grid(days)
    if max_weeks:
        grid = grid[-max_weeks:]
    n_cols, n_rows = len(grid), 7

    path = boustrophedon_path(n_cols, n_rows)

    width = n_cols * (CELL + GAP)
    height = n_rows * (CELL + GAP)

    # state: which cells eaten, and their shrink progress (for a fade-out over a few frames)
    eaten = {}  # (c,r) -> progress 0..1
    trail = []  # recent zombie centers, for the tail

    frames = []

    for i in range(len(path) - 1):
        c0, r0 = path[i]
        c1, r1 = path[i + 1]
        x0, y0 = cell_center(c0, r0)
        x1, y1 = cell_center(c1, r1)

        for f in range(STEP_FRAMES):
            t = f / STEP_FRAMES
            zx = x0 + (x1 - x0) * t
            zy = y0 + (y1 - y0) * t

            # mark current cell as being eaten partway through the move
            if t > 0.35:
                eaten[(c0, r0)] = min(1.0, eaten.get((c0, r0), 0) + 0.35)

            img = Image.new("RGB", (width, height), BG)
            draw = ImageDraw.Draw(img)

            for cc in range(n_cols):
                for rr in range(n_rows):
                    lvl = grid[cc][rr]
                    base_color = LEVEL_COLORS[lvl]
                    progress = eaten.get((cc, rr), 0)
                    if progress >= 1.0:
                        continue  # fully eaten, cell stays empty
                    if progress > 0:
                        # flash bright right as it's being eaten, then shrink away
                        color = EATEN_FLASH if progress < 0.4 else base_color
                        draw_cell(draw, cc, rr, color, eaten_progress=progress)
                    else:
                        draw_cell(draw, cc, rr, base_color)

            # trail
            trail.append((zx, zy))
            if len(trail) > 5:
                trail.pop(0)
            for ti, (tx, ty) in enumerate(trail[:-1]):
                rr = CELL * 0.28 * (ti + 1) / len(trail)
                draw.ellipse([tx - rr, ty - rr, tx + rr, ty + rr], fill=TRAIL_COLOR)

            draw_zombie(draw, zx, zy, wobble=(f % STEP_FRAMES) >= STEP_FRAMES // 2)

            if SCALE != 1:
                img = img.resize((width * SCALE, height * SCALE), Image.NEAREST)
            frames.append(img)

    # hold the final "cleared lawn" frame briefly
    for _ in range(FPS // 2):
        frames.append(frames[-1])

    frames[0].save(
        out_path, save_all=True, append_images=frames[1:],
        duration=int(1000 / FPS), loop=0, optimize=True
    )
    print(f"Saved {out_path} — {len(frames)} frames, {width*SCALE}x{height*SCALE}px, {n_cols} weeks")


if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else "OmidBehzadpoor"
    out = sys.argv[2] if len(sys.argv) > 2 else "zombie_contrib.gif"
    weeks = int(sys.argv[3]) if len(sys.argv) > 3 else None
    render(username, out, max_weeks=weeks)