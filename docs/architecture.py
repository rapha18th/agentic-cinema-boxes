"""THE BOXES - architecture diagram. Google-Cloud-style zones, left-to-right flow,
orthogonal connectors.  ->  architecture.png"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, RegularPolygon, Circle

BLUE, GREEN, YELLOW, RED = "#4285F4", "#34A853", "#FBBC04", "#EA4335"
PURPLE = "#7B5CFF"
INK, SUB, WIRE = "#202124", "#5F6368", "#3C4043"
Z_BLUE, Z_GREY = "#E8F0FE", "#F1F3F4"

fig, ax = plt.subplots(figsize=(21, 10.4), dpi=135)
ax.set_xlim(0, 21); ax.set_ylim(0, 10.4); ax.axis("off")
fig.patch.set_facecolor("white")


def zone(x, y, w, h, title, fill, dots=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.12",
                                fc=fill, ec="#C6CAD2", lw=1.3, zorder=1))
    if dots:
        for i, c in enumerate([BLUE, RED, YELLOW, GREEN]):
            ax.add_patch(Circle((x + 0.44 + i * 0.27, y + h - 0.4), 0.10, color=c, zorder=3))
        ax.text(x + 0.44 + 4 * 0.27 + 0.18, y + h - 0.4, title, fontsize=12.5, color=SUB, weight="bold",
                va="center", zorder=3)
    else:
        ax.text(x + w / 2, y + h - 0.4, title, fontsize=12.5, color=SUB, weight="bold", ha="center", zorder=3)


def cluster(x, y, w, h, title, ec="#D6D9DE", tc=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.09",
                                fc="white", ec=ec, lw=1.4, zorder=3))
    ax.text(x + w / 2, y + h - 0.28, title, fontsize=10, color=tc, weight="bold", ha="center", zorder=4)


def tile(cx, cy, label, cap=None, color=BLUE, r=0.42):
    ax.add_patch(RegularPolygon((cx, cy), 6, radius=r, orientation=np.pi / 2, fc=color, ec="white",
                                lw=1.5, zorder=6))
    ax.add_patch(RegularPolygon((cx, cy), 6, radius=r * 0.5, orientation=np.pi / 2, fc="white",
                                ec="none", alpha=0.3, zorder=7))
    ax.text(cx, cy - r - 0.18, label, fontsize=8.6, color=INK, weight="bold", ha="center", va="top", zorder=7)
    if cap:
        ax.text(cx, cy - r - 0.46, cap, fontsize=7.0, color=SUB, ha="center", va="top", zorder=7,
                linespacing=1.4)


def wire(pts, color=WIRE, lw=2.3, dash=False, text=None, tp=None, tcol=None):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=color, lw=lw, zorder=8, solid_joinstyle="round", solid_capstyle="round",
            linestyle="--" if dash else "-")
    ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=16, color=color,
                                 lw=lw, connectionstyle="arc3,rad=0", zorder=8))
    if text:
        ax.text(*(tp or ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2)), text,
                fontsize=7.5, color=tcol or SUB, ha="center", va="center", zorder=10,
                bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="none", alpha=0.97))


ax.text(0.3, 10.05, "THE BOXES", fontsize=20, weight="bold", color=INK)
ax.text(0.3, 9.66, "Autonomous multimodal research department for filmmakers      ·      Agentic Cinema, Parallel track",
        fontsize=9.5, color=SUB)

# ── Zone: browser ─────────────────────────────────────────────────────
zone(0.3, 0.5, 3.1, 8.4, "User's browser", Z_BLUE)
tile(1.85, 6.4, "React app", "map · console\nledger · reel", color=YELLOW, r=0.5)
tile(1.85, 3.0, "Firebase Auth", "isolated per user", color=GREEN, r=0.5)

# ── Zone: Google Cloud ───────────────────────────────────────────────
zone(3.7, 0.5, 17.0, 8.4, "Google Cloud", Z_GREY, dots=True)

# left column: Hosting + Cloud Run
tile(5.05, 7.35, "Firebase Hosting", "static app · /api", color=YELLOW, r=0.42)
tile(5.05, 4.2, "Cloud Run", "boxes-api · FastAPI\nSSE · ffmpeg", color=BLUE, r=0.5)

# top strip: Parallel (partner) + Vertex AI
cluster(6.8, 6.5, 3.8, 1.9, "Parallel  ·  partner", ec=PURPLE, tc="#5B3FCF")
tile(7.9, 7.45, "Search API", color=PURPLE, r=0.36)
tile(9.6, 7.45, "Extract API", color=PURPLE, r=0.36)
cluster(11.0, 6.5, 4.6, 1.9, "Vertex AI  ·  global")
tile(12.2, 7.45, "Gemini 3.8 Flash", color=BLUE, r=0.36)
tile(14.35, 7.45, "Gemini Embedding 2", color=BLUE, r=0.36)

# middle strip: the loop
cluster(6.4, 2.6, 9.8, 2.5, "Autonomous research loop   ·   ADK on Cloud Run")
seq = [("1 PLAN", GREEN), ("2 ACQUIRE", RED), ("3 EMBED", BLUE),
       ("4 MEASURE", YELLOW), ("5 VERIFY", RED), ("6 GAP", GREEN)]
lx0, dx, ly = 7.4, 1.45, 3.85
cxs = [lx0 + i * dx for i in range(6)]
for cx, (t, col) in zip(cxs, seq):
    tile(cx, ly, t, color=col, r=0.36)
for a, b in zip(cxs, cxs[1:]):
    wire([(a + 0.36, ly), (b - 0.36, ly)], lw=2.0)
wire([(cxs[-1], ly - 0.36), (cxs[-1], 3.0), (cxs[1], 3.0), (cxs[1], ly - 0.36)],
     color=BLUE, dash=True, lw=1.9, text="loop until confident", tp=((cxs[1] + cxs[-1]) / 2, 2.82), tcol=BLUE)

# right column: Data
cluster(16.5, 1.5, 3.9, 6.9, "Data")
tile(18.45, 6.7, "Cloud Firestore", "boxes · evidence\nruns · verdicts · reel", color=GREEN, r=0.44)
tile(18.45, 3.5, "Cloud Storage", "source files · uploads", color=YELLOW, r=0.44)

# ── flow ─────────────────────────────────────────────────────────────
wire([(4.63, 7.35), (2.5, 6.7)], text="serves", tp=(3.5, 7.3))
wire([(2.55, 6.15), (3.8, 6.15), (3.8, 4.55), (4.58, 4.42)], text="REST + ID token", tp=(3.8, 5.45))
wire([(4.58, 4.02), (4.05, 4.02), (4.05, 5.75), (2.55, 5.75)],
     color=BLUE, tcol=BLUE, text="SSE stream", tp=(3.25, 5.02))
wire([(5.55, 4.2), (6.4, 4.2), (6.4, ly), (cxs[0] - 0.36, ly)], lw=2.0)

# loop <-> Parallel (up)
wire([(cxs[1], ly + 0.36), (cxs[1], 5.55), (7.9, 5.55), (7.9, 7.09)],
     color=PURPLE, tcol="#5B3FCF", text="objective + queries", tp=(cxs[1], 5.85))
wire([(9.6, 7.09), (9.6, 5.9), (cxs[1] + 0.5, 5.9), (cxs[1] + 0.5, ly + 0.36)], color=PURPLE)

# loop -> Vertex (up)
wire([(cxs[0], ly + 0.36), (cxs[0], 5.75), (12.2, 5.75), (12.2, 7.09)], text="Gemini 3.8 Flash",
     tp=(9.9, 6.02))
wire([(cxs[2], ly + 0.36), (cxs[2], 5.35), (14.35, 5.35), (14.35, 7.09)], color=BLUE,
     text="media + caption → vector", tp=(12.2, 5.62))

# Cloud Run -> Data (bottom rail, inside Google Cloud)
wire([(5.05, 3.7), (5.05, 1.15), (18.45, 1.15), (18.45, 2.86)], color=GREEN, tcol="#1E7B34",
     text="persist live: evidence · progress · files", tp=(10.6, 0.93))
wire([(18.45, 3.74), (18.45, 6.16)], color=GREEN, lw=2.0)

ax.text(0.3, 0.14, "Vertex AI serves Gemini on the  global  location.        Parallel Search + Extract is imported and "
        "invoked in runtime code on every research round.", fontsize=8, color=SUB)

plt.savefig("architecture.png", dpi=135, bbox_inches="tight", facecolor="white", pad_inches=0.28)
print("ok")
