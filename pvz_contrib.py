"""
PvZ Contribution Graph — turns a GitHub contribution calendar into a
Plants-vs-Zombies-style animated GIF.

How it works:
  - Each column of the graph = one week (a "lane row" grid, 7 rows x ~53 cols)
  - Zombies march from the right edge for every day that HAS a contribution
    (the darker green, the tougher/bigger the zombie)
  - A plant spawns on the matching cell and shoots peas at the incoming zombie
  - Empty days (no contributions) = no zombie spawns that lane that frame,
    giving the "lawn" a breather
  - Fully self-drawn pixel-art shapes (no copyrighted Popcap art), rendered
    frame by frame with Pillow and exported as a looping GIF.

Usage:
    python3 pvz_contrib.py <github_username> <output.gif>
"""

import sys
import re
import random
import requests
from PIL import Image, ImageDraw

CELL = 14          # pixel size of one grid cell (before final upscale)
SCALE = 2            # final upscale factor for crisp pixel-art look
ROWS = 7            # days of week
COLS_VISIBLE = 20   # how many weeks to show per loop (last ~4-5 months, keeps file size reasonable)
FPS = 8
FRAMES_PER_STEP = 4  # animation frames per "day advance" step

BG = (10, 14, 10)
LAWN_A = (30, 60, 30)
LAWN_B = (26, 54, 26)
SUN_YELLOW = (255, 214, 92)
PLANT_GREEN = (86, 191, 90)
PLANT_DARK = (46, 130, 60)
PEA_GREEN = (150, 230, 110)
ZOMBIE_GREY = (176, 186, 176)
ZOMBIE_DARK = (100, 110, 100)
ZOMBIE_TATTER = (80, 88, 80)
TEXT_COLOR = (240, 235, 200)


def fetch_contributions(username: str):
    url = f"https://github.com/users/{username}/contributions"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    html = resp.text
    pattern = r'data-date="([\d-]+)"[^>]*id="contribution-day-component[^"]*"[^>]*data-level="(\d)"'
    matches = re.findall(pattern, html)
    if not matches:
        raise RuntimeError("Could not parse contribution data — GitHub markup may have changed.")
    days = [{"date": d, "level": int(lv)} for d, lv in matches]
    return days


def to_grid(days):
    """Arrange days into a 7-row grid (Sun..Sat) x N-week columns, GitHub style."""
    from datetime import datetime
    cols = []
    col = [None] * 7
    for d in days:
        dt = datetime.strptime(d["date"], "%Y-%m-%d")
        weekday = (dt.weekday() + 1) % 7  # convert Mon=0..Sun=6 -> Sun=0..Sat=6
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


def draw_plant(draw, x, y, level, frame):
    """Simple pixel-art peashooter, bigger/brighter for higher contribution levels."""
    bob = 1 if frame % 4 < 2 else 0
    cx, cy = x + CELL // 2, y + CELL // 2 - bob
    stem_h = 3 + level
    draw.rectangle([cx - 1, cy + 2, cx + 1, cy + 2 + stem_h], fill=PLANT_DARK)
    head_r = 3 + level
    draw.ellipse([cx - head_r, cy - head_r, cx + head_r, cy + head_r], fill=PLANT_GREEN)
    # little mouth / shooter nub
    draw.rectangle([cx + head_r - 1, cy - 1, cx + head_r + 2, cy + 1], fill=PLANT_DARK)
    # eyes
    draw.point((cx - 1, cy - 1), fill=(20, 20, 20))
    draw.point((cx + 1, cy - 1), fill=(20, 20, 20))


def draw_pea(draw, x, y):
    draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=PEA_GREEN)


def draw_zombie(draw, x, y, level, frame):
    """Simple pixel-art zombie, tattered more / bigger for higher levels."""
    stagger = 1 if frame % 6 < 3 else -1
    cx, cy = x + CELL // 2, y + CELL // 2
    w = 4 + level
    h = 6 + level
    # body
    draw.rectangle([cx - w // 2, cy - h // 2 + stagger, cx + w // 2, cy + h // 2 + stagger],
                    fill=ZOMBIE_GREY, outline=ZOMBIE_DARK)
    # head
    draw.ellipse([cx - 3, cy - h // 2 - 5 + stagger, cx + 3, cy - h // 2 + 1 + stagger],
                  fill=ZOMBIE_GREY, outline=ZOMBIE_DARK)
    # tattered arm reaching forward
    draw.line([cx + w // 2, cy + stagger, cx + w // 2 + 4, cy - 2 + stagger],
               fill=ZOMBIE_TATTER, width=2)
    # eyes
    draw.point((cx - 1, cy - h // 2 - 2 + stagger), fill=(255, 40, 40))
    draw.point((cx + 1, cy - h // 2 - 2 + stagger), fill=(255, 40, 40))


def render(username, out_path, weeks=COLS_VISIBLE):
    days = fetch_contributions(username)
    grid = to_grid(days)
    grid = grid[-weeks:]  # last N weeks only, keeps GIF snappy

    width = CELL * len(grid) + CELL * 3   # extra lane on the right for zombie spawn-in
    height = CELL * ROWS + CELL * 2

    frames = []
    total_steps = len(grid)

    # each lane (row) gets an independent zombie march timer so it doesn't feel robotic
    zombie_x = [width - CELL for _ in range(ROWS)]
    zombie_active = [False] * ROWS
    zombie_level = [0] * ROWS
    pea_particles = []  # list of [row, x, y]

    for step in range(total_steps):
        col = grid[step]
        for row in range(ROWS):
            lvl = col[row]
            if lvl > 0 and not zombie_active[row]:
                zombie_active[row] = True
                zombie_level[row] = lvl
                zombie_x[row] = width - CELL

        for f in range(FRAMES_PER_STEP):
            img = Image.new("RGB", (width, height), BG)
            draw = ImageDraw.Draw(img)

            # lawn stripes
            for c in range(len(grid) + 3):
                color = LAWN_A if c % 2 == 0 else LAWN_B
                draw.rectangle([c * CELL, CELL, c * CELL + CELL, CELL + CELL * ROWS], fill=color)

            # plants: draw for every day up to current step that had contributions
            for cstep in range(step + 1):
                for row in range(ROWS):
                    if grid[cstep][row] > 0:
                        px = cstep * CELL
                        py = CELL + row * CELL
                        draw_plant(draw, px, py, min(grid[cstep][row], 4), step * FRAMES_PER_STEP + f)

            # peas: spawn occasionally from the frontmost plant in an active lane
            for row in range(ROWS):
                if zombie_active[row] and random.random() < 0.5:
                    plant_x = step * CELL + CELL
                    pea_particles.append([row, plant_x, CELL + row * CELL + CELL // 2])

            new_peas = []
            for row, px, py in pea_particles:
                px += 6
                if zombie_active[row] and px < zombie_x[row] + CELL:
                    draw_pea(draw, px, py)
                    new_peas.append([row, px, py])
            pea_particles = new_peas

            # zombies march left, get "killed" (fade out) when reaching the plant line
            for row in range(ROWS):
                if zombie_active[row]:
                    zombie_x[row] -= 3
                    front = step * CELL + CELL
                    if zombie_x[row] <= front:
                        zombie_active[row] = False
                    else:
                        draw_zombie(draw, zombie_x[row], CELL + row * CELL, zombie_level[row],
                                    step * FRAMES_PER_STEP + f)

            # sun counter (total contribution-days so far, PvZ style currency readout)
            total = sum(sum(1 for v in c if v > 0) for c in grid[:step + 1])
            draw.ellipse([4, 2, 4 + 11, 2 + 11], fill=SUN_YELLOW, outline=(200, 160, 40))
            draw.text((19, 1), str(total), fill=TEXT_COLOR)

            if SCALE != 1:
                img = img.resize((width * SCALE, height * SCALE), Image.NEAREST)
            frames.append(img)

    frames[0].save(
        out_path, save_all=True, append_images=frames[1:],
        duration=int(1000 / FPS), loop=0, optimize=True
    )
    print(f"Saved {out_path} ({len(frames)} frames, {width}x{height}px)")


if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else "OmidBehzadpoor"
    out = sys.argv[2] if len(sys.argv) > 2 else "pvz_contrib.gif"
    render(username, out)
