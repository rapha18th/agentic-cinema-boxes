"""THE BOXES - architecture diagram, Google Cloud style. -> architecture.png"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Circle

BLUE, GREEN, YELLOW, RED = "#4285F4", "#34A853", "#FBBC04", "#EA4335"
PURPLE = "#7B5CFF"
INK, SUB, EDGE = "#202124", "#5F6368", "#D6D9DE"

fig, ax = plt.subplots(figsize=(19, 12.3), dpi=130)
ax.set_xlim(0, 19); ax.set_ylim(0, 12.3); ax.axis("off")
fig.patch.set_facecolor("white")


def box(x, y, w, h, ec, fc="none", dash=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.15",
                                fc=fc, ec=ec, lw=1.6, zorder=1,
                                linestyle=(0, (6, 4)) if dash else "solid"))


def glabel(x, y, text, color=SUB, dots=False):
    lx = x
    if dots:
        for i, c in enumerate([BLUE, RED, YELLOW, GREEN]):
            ax.add_patch(Circle((x + 0.16 + i * 0.34, y), 0.12, color=c, zorder=4))
        lx = x + 4 * 0.34 + 0.35
    ax.text(lx, y, text, fontsize=13, color=color, weight="bold", va="center", zorder=4)


def card(x, y, w, h, title, lines=None, accent=BLUE, tsize=11, tag=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.09",
                                fc="white", ec=EDGE, lw=1.2, zorder=5))
    ax.add_patch(Rectangle((x, y + h - 0.08), w, 0.08, fc=accent, ec="none", zorder=6))
    ty = y + h - 0.34
    ax.text(x + w / 2, ty, title, fontsize=tsize, color=INK, weight="bold", ha="center", va="top", zorder=7)
    if lines:
        ax.text(x + w / 2, ty - 0.42, "\n".join(lines), fontsize=8.7, color=SUB,
                ha="center", va="top", zorder=7, linespacing=1.6)
    if tag:
        ax.text(x + w - 0.05, y + h + 0.22, tag, fontsize=7.5, color="white", weight="bold",
                ha="right", va="center", zorder=8,
                bbox=dict(boxstyle="round,pad=0.28", fc=accent, ec="none"))


def arrow(p1, p2, text=None, color=SUB, lw=1.8, rad=0.0, tcol=None, dash=False, tpos=0.5, tdy=0.24):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=18, color=color, lw=lw,
                                 connectionstyle=f"arc3,rad={rad}", zorder=9,
                                 linestyle="--" if dash else "-"))
    if text:
        mx = p1[0] + (p2[0] - p1[0]) * tpos
        my = p1[1] + (p2[1] - p1[1]) * tpos
        ax.text(mx, my + tdy, text, fontsize=8.2, color=tcol or SUB, ha="center", va="center", zorder=10,
                bbox=dict(boxstyle="round,pad=0.24", fc="white", ec="none", alpha=0.97))


ax.text(0.35, 11.95, "THE BOXES", fontsize=23, weight="bold", color=INK)
ax.text(0.35, 11.52, "Autonomous multimodal research department for filmmakers      ·      Agentic Cinema, Parallel track",
        fontsize=10.5, color=SUB)

# ---- browser ----
box(0.4, 9.35, 12.6, 1.45, "#9AA0A6")
glabel(0.6, 11.02, "User's browser")
card(0.85, 9.53, 7.7, 1.08, "React app   ·   helenia-11f98.web.app",
     ["research map · cinematic console · expandable ledger · reference reel"], accent=YELLOW, tsize=10.5)
card(8.85, 9.53, 3.75, 1.08, "Firebase Auth",
     ["Google sign-in · isolated BOXES per user"], accent=GREEN, tsize=10.5)

# ---- Google Cloud ----
box(0.4, 0.5, 18.2, 8.35, "#9AA0A6")
glabel(0.8, 8.42, "Google Cloud", dots=True)

card(0.9, 6.8, 3.3, 0.95, "Firebase Hosting", ["static app · /api rewrite"], accent=YELLOW, tsize=9.8)
card(4.5, 6.7, 4.5, 1.05, "Cloud Run  —  boxes-api",
     ["FastAPI · verifies ID token", "SSE stream · ffmpeg trims a/v"], accent=BLUE, tsize=10.3)

# ---- research loop ----
box(0.9, 0.95, 11.4, 5.4, BLUE, fc="#F6FAFF", dash=True)
ax.text(1.2, 6.02, "Autonomous research loop", fontsize=12, color=BLUE, weight="bold", zorder=4)

tw, th = 3.35, 1.45
cx = [1.25, 4.95, 8.65]
ry = [3.35, 1.10]
S = {
    "PLAN": (cx[0], ry[0], "1  PLAN", ["Gemini 3.8 Flash writes", "the research ontology"], GREEN),
    "ACQUIRE": (cx[1], ry[0], "2  ACQUIRE", ["Parallel Search + Extract;", "harvest img·pdf·audio·video"], RED),
    "EMBED": (cx[2], ry[0], "3  EMBED", ["Gemini Embedding 2:", "one 768-d multimodal space"], BLUE),
    "GAP": (cx[0], ry[1], "6  GAP", ["thinnest objective +", "an emergent box it opens"], GREEN),
    "VERIFY": (cx[1], ry[1], "5  VERIFY", ["embedding finds pairs,", "Gemini rules contradiction"], RED),
    "MEASURE": (cx[2], ry[1], "4  MEASURE", ["coverage per objective", "+ research confidence"], YELLOW),
}
for k, (x, y, t, ls, acc) in S.items():
    card(x, y, tw, th, t, ls, accent=acc, tsize=9.6)


def E(k, s):
    x, y = S[k][0], S[k][1]
    return {"r": (x + tw, y + th / 2), "l": (x, y + th / 2), "t": (x + tw / 2, y + th), "b": (x + tw / 2, y)}[s]


arrow(E("PLAN", "r"), E("ACQUIRE", "l"))
arrow(E("ACQUIRE", "r"), E("EMBED", "l"))
arrow(E("EMBED", "b"), E("MEASURE", "t"))
arrow(E("MEASURE", "l"), E("VERIFY", "r"))
arrow(E("VERIFY", "l"), E("GAP", "r"))
arrow(E("GAP", "b"), E("ACQUIRE", "b"), "loop until confident", rad=0.42, dash=True, color=BLUE, tcol=BLUE, tdy=-0.28)

# ---- Parallel: partner card floating above ACQUIRE, inside the loop ----
px, py, pw, ph = cx[1] - 0.15, 5.15, 3.65, 1.05
card(px, py, pw, ph, "Parallel  —  Search + Extract",
     ["objective + queries  →  URLs · excerpts · full text"], accent=PURPLE, tsize=9.7, tag="PARTNER")
arrow((px + pw * 0.32, py), (E("ACQUIRE", "t")[0] - 0.45, E("ACQUIRE", "t")[1]), color=PURPLE, lw=2.3)
arrow((E("ACQUIRE", "t")[0] + 0.45, E("ACQUIRE", "t")[1]), (px + pw * 0.68, py), color=PURPLE, lw=2.3)
ax.text(E("ACQUIRE", "t")[0], (py + E("ACQUIRE", "t")[1]) / 2, "hot path,\nevery round",
        fontsize=7.8, color="#5B3FCF", ha="center", va="center", zorder=10,
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.95))

# ---- right stack: Vertex / Firestore / Storage ----
rx, rw = 13.0, 5.35
card(rx, 5.35, rw, 1.5, "Vertex AI   ·   global",
     ["Gemini 3.8 Flash  —  planning, verdicts", "Gemini Embedding 2  —  multimodal, 768-d"],
     accent=BLUE, tsize=10.3)
card(rx, 3.05, rw, 1.9, "Cloud Firestore",
     ["users/{uid}/ …", "projects · boxes · evidence (+ vectors)", "runs · verdicts · reel"], accent=GREEN, tsize=10.3)
card(rx, 0.95, rw, 1.7, "Cloud Storage",
     ["users/{uid}/ …", "harvested source files · director uploads"], accent=YELLOW, tsize=10.3)

arrow(E("EMBED", "r"), (rx, 6.05), "media + caption\n→ vector", color=BLUE, rad=-0.12, tdy=0.0)
arrow((9.02, 6.7), (rx, 4.75), "persist live:\nevidence · progress · files", color=GREEN, rad=0.5,
      tpos=0.10, tdy=0.0, tcol="#1E7B34")
arrow((9.02, 6.55), (rx, 2.15), "", color=YELLOW, rad=0.66)

# ---- browser <-> cloud run ----
arrow((5.0, 9.53), (6.0, 7.85), "REST + Firebase ID token", color=GREEN, rad=0.1, tdy=0.0)
arrow((7.2, 7.85), (5.4, 9.53), "SSE:  plan · progress · evidence · contradiction · reel",
      color=BLUE, tcol=BLUE, lw=1.9, rad=0.34, tdy=0.0)

ax.text(0.4, 0.16, "Vertex AI serves Gemini on the  global  location.       Parallel Search + Extract is imported and "
        "invoked in runtime code on every research round.", fontsize=8.6, color=SUB)

plt.savefig("architecture.png", dpi=130, bbox_inches="tight", facecolor="white", pad_inches=0.3)
print("ok")
