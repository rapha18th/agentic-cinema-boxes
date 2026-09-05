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

fig, ax = plt.subplots(figsize=(21, 11.0), dpi=135)
ax.set_xlim(0, 21); ax.set_ylim(0, 11.0); ax.axis("off")
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
    if title:
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


def ghost(cx, cy, color, r=0.34):
    """Two translucent hexes stacked behind a tile: this stage fans out across
    many concurrent workers, one per objective, fragment, or evidence pair."""
    for k, a in ((2, 0.14), (1, 0.28)):
        ax.add_patch(RegularPolygon((cx + k * 0.16, cy + k * 0.17), 6, radius=r, orientation=np.pi / 2,
                                    fc=color, ec="white", lw=1.0, alpha=a, zorder=5))


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


ax.text(0.3, 10.6, "THE BOXES", fontsize=20, weight="bold", color=INK)
ax.text(0.3, 10.2, "Autonomous multimodal research department for filmmakers      ·      Agentic Cinema, Parallel track",
        fontsize=9.5, color=SUB)

# -- Zone: browser -----------------------------------------------------
zone(0.3, 0.7, 3.1, 8.9, "User's browser", Z_BLUE)
tile(1.85, 6.9, "React app", "map · console\nledger · reel", color=YELLOW, r=0.5)
tile(1.85, 3.4, "Firebase Auth", "isolated per user", color=GREEN, r=0.5)

# -- Zone: Google Cloud ---------------------------------------------
zone(3.7, 0.7, 17.0, 8.9, "Google Cloud", Z_GREY, dots=True)

# left column: Hosting + Cloud Run
tile(5.05, 7.85, "Firebase Hosting", "static app · /api", color=YELLOW, r=0.42)
tile(5.05, 4.5, "Cloud Run", "boxes-api · FastAPI", color=BLUE, r=0.5)

# top strip: external APIs + Vertex AI
cluster(6.7, 6.95, 4.9, 1.9, "Parallel + TMDB  ·  external APIs", ec=PURPLE, tc="#5B3FCF")
tile(7.7, 7.95, "Search API", "web", color=PURPLE, r=0.32)
tile(9.1, 7.95, "Extract API", "full text", color=PURPLE, r=0.32)
tile(10.6, 7.95, "TMDB", "movie prior art", color=PURPLE, r=0.32)
cluster(12.1, 6.95, 4.15, 1.9, "Vertex AI  ·  global")
tile(13.2, 7.95, "Gemini 3.8 Flash", "planning · verdicts", color=BLUE, r=0.36)
tile(15.15, 7.95, "Gemini Embedding 2", "one multimodal space", color=BLUE, r=0.36)

# -- the loop -----------------------------------------------------
cluster(6.7, 1.65, 9.6, 4.15, "")
ax.text(6.95, 5.5, "Autonomous research loop", fontsize=10, color=INK, weight="bold", ha="left", zorder=4)
ax.text(6.95, 5.26, "concurrent Python  ·  ADK tool surface  ·  Cloud Run service",
        fontsize=8, color=SUB, ha="left", zorder=4)

seq = [("1 PLAN", GREEN, None), ("2 ACQUIRE", RED, "per objective"), ("3 EMBED", BLUE, "per fragment"),
       ("4 MEASURE", YELLOW, None), ("5 VERIFY", RED, "per pair"), ("6 GAP", GREEN, None)]
lx0, dx, ly, R = 7.4, 1.44, 3.7, 0.34
cxs = [lx0 + i * dx for i in range(6)]
mid = (cxs[0] + cxs[-1]) / 2
for cx, (t, col, sub) in zip(cxs, seq):
    if sub:
        ghost(cx, ly, col, r=R)
    tile(cx, ly, t, color=col, r=R)
    if sub:
        ax.text(cx, ly - R - 0.44, sub, fontsize=7.0, color=SUB, ha="center", va="top", zorder=7)
for a, b in zip(cxs, cxs[1:]):
    wire([(a + R, ly), (b - R, ly)], lw=1.9)

# entry: Cloud Run -> PLAN, into the top of the row
wire([(5.55, 4.5), (6.3, 4.5), (6.3, 4.32), (cxs[0], 4.32), (cxs[0], ly + R)], lw=2.0)

# feedback: GAP -> PLAN, routed under the row and clear of every label
wire([(cxs[5] + R, ly), (cxs[5] + 0.62, ly), (cxs[5] + 0.62, 2.6), (cxs[0] - 0.62, 2.6),
      (cxs[0] - 0.62, ly), (cxs[0] - R, ly)],
     color=BLUE, dash=True, lw=1.8, text="loop until the confidence target is met",
     tp=(mid, 2.6), tcol=BLUE)

# the concurrency note: the current engineering edge, stated plainly
ax.text(mid, 2.30, "Query-writing collapses to one call per round.",
        fontsize=7.3, color=INK, ha="center", va="center", zorder=10)
ax.text(mid, 2.07, "Per-objective research, embedding, and contradiction checks run concurrently.",
        fontsize=7.3, color=SUB, ha="center", va="center", zorder=10)
ax.text(mid, 1.85, "Thread-local model clients; a semaphore caps in-flight model calls at three.",
        fontsize=7.0, color=SUB, ha="center", va="center", zorder=10)

# loop <-> external APIs, one channel left of the clusters
wire([(cxs[1], ly + R), (cxs[1], 4.72), (6.4, 4.72), (6.4, 7.95), (7.7 - 0.32, 7.95)],
     color=PURPLE, tcol="#5B3FCF", text="objectives + queries  ⇄  text & media", tp=(7.35, 6.35))

# loop -> Vertex AI, through the in-flight gate
wire([(cxs[2], ly + R), (cxs[2], 4.72), (12.4, 4.72), (12.4, 7.95), (12.84, 7.95)], color=BLUE)
ax.add_patch(FancyBboxPatch((10.86, 4.5), 1.3, 0.44, boxstyle="round,pad=0.02,rounding_size=0.08",
                            fc="white", ec=BLUE, lw=1.3, zorder=9))
ax.text(11.51, 4.72, "gate · 3 in-flight", fontsize=6.7, color=BLUE, weight="bold",
        ha="center", va="center", zorder=10)

# right column: Data
cluster(16.5, 1.6, 3.9, 6.75, "Data")
tile(18.45, 6.6, "Cloud Firestore", "boxes · evidence\nruns · verdicts · reel", color=GREEN, r=0.44)
tile(18.45, 3.5, "Cloud Storage", "source files · uploads", color=YELLOW, r=0.44)

# -- browser <-> Cloud Run --------------------------------------
wire([(4.63, 7.85), (2.55, 7.3)], text="serves", tp=(3.6, 7.9))
wire([(2.6, 6.85), (3.55, 6.85), (3.55, 4.9), (4.58, 4.8)], text="REST + ID token", tp=(3.95, 6.0))
wire([(4.58, 4.4), (4.0, 4.4), (4.0, 6.25), (2.6, 6.25)],
     color=BLUE, tcol=BLUE, text="SSE stream", tp=(3.55, 4.78))

# Cloud Run -> Data (bottom rail; enters the Data tiles on the left, clear of labels)
wire([(5.05, 4.0), (5.05, 1.25), (17.15, 1.25), (17.15, 3.3), (18.05, 3.3)],
     color=GREEN, tcol="#1E7B34", text="persist live: evidence · progress · files", tp=(10.6, 1.05))
wire([(17.7, 3.5), (17.15, 3.5), (17.15, 6.6), (18.05, 6.6)], color=GREEN, lw=2.0)

ax.text(0.3, 0.32, "Vertex AI serves Gemini on the  global  location.        Parallel Search + Extract runs on every "
        "research round.        TMDB seeds the prior-art survey.", fontsize=8, color=SUB)

plt.savefig("architecture.png", dpi=135, bbox_inches="tight", facecolor="white", pad_inches=0.28)
print("ok")
