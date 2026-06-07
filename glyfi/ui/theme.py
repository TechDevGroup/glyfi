"""theme -- the NAMED VISUAL + ACCESSIBILITY convention palette: semantic colors, accents, focus markers.

The UI's color/decal state lives here as a small SEMANTIC palette -- every color is named by its MEANING (not
its hue), so a render site asks for ``ROLE_DESTRUCTIVE`` / ``ROLE_DIM`` / ``ROLE_ACCENT`` rather than a raw
xterm index. Each role maps to a NAMED xterm-256 index (no magic literal at a render site) AND to a NAMED curses
ATTRIBUTE fall-back, so the UI stays legible on a mono / no-color terminal (capability fall-back, never a spec
fall-back that hides a mis-config).

Color CONVENTIONS (a11y, WCAG-508 aligned):
  * RED is for DESTRUCTIVE actions ONLY -- never for non-destructive state/info. ``ROLE_DESTRUCTIVE`` is the only
    red role; nothing else may use it.
  * FOCUS / SELECTION is NEVER color-only. The View ALWAYS prefixes the selected row with a printed marker
    (``FOCUS_MARKER`` -- the arrow char) so the selection survives a no-color terminal (508: do not encode
    meaning in color alone). The maroon/reverse background is an ADDITIONAL cue, not the only one.
  * PLACEHOLDER / HELPER text renders DIM (``ROLE_DIM``) -- gray/faded, not full-bright -- so live content stands
    out from hints.
  * ACTIVE-MENU ACCENT: an open menu/submenu/palette/widget shows an ACCENT trim that MATCHES the helper text
    accent for that menu. PROGRESSIVE accents: nested depth uses ``ACCENT_RING`` in order (accent, accent-2, ...)
    so menu depth is legible by color.

Split so the module imports WITHOUT a terminal: the role -> color-index map + the named marker chars are plain
module constants (pure, importable in a test with no TTY); the actual ``curses.init_pair`` / attribute lookup
lives behind ``init_theme`` / ``role_attr`` / ``select_attr``, which a View calls AFTER curses has started.

Imports stdlib ``curses`` only (and that lazily, inside the functions, so a no-TTY import is safe).
"""
from typing import Dict, Tuple

# ---- NAMED color theme keys (a config picks one by name; default is the semantic palette) -------------------
THEME_MAROON_SELECT = 'maroon-select'
DEFAULT_THEME = THEME_MAROON_SELECT
THEMES = (THEME_MAROON_SELECT,)

# ---- NAMED SEMANTIC roles (a render site names the MEANING, never a hue) -----------------------------------
ROLE_NORMAL = 'normal'              # default foreground (live content)
ROLE_DIM = 'dim'                    # faded/gray -- placeholder + helper/hint text
ROLE_ACCENT = 'accent'             # the active-menu accent trim (depth 0)
ROLE_ACCENT_2 = 'accent2'          # the nested-submenu accent trim (depth 1+, progressive)
ROLE_SELECT = 'select'             # the selection-highlight background (the maroon edit/menu select)
ROLE_DESTRUCTIVE = 'destructive'   # RED -- DESTRUCTIVE actions ONLY (confirm prompts); never non-destructive
ROLES = (ROLE_NORMAL, ROLE_DIM, ROLE_ACCENT, ROLE_ACCENT_2, ROLE_SELECT, ROLE_DESTRUCTIVE)

# the PROGRESSIVE accent ring -- nested menu depth picks the next entry (wraps). Depth 0 = ACCENT, 1 = ACCENT_2.
ACCENT_RING = (ROLE_ACCENT, ROLE_ACCENT_2)

# ---- NAMED xterm-256 color indexes (semantic; no magic literal at a render site) ---------------------------
COLOR_SELECT_BG = 131           # the light-maroon background index for the selection highlight
COLOR_SELECT_FG = 231           # near-white foreground on the maroon (xterm-256 grayscale top)
COLOR_DIM = 244                 # mid-gray -- the faded placeholder/helper foreground
COLOR_ACCENT = 39               # cyan-ish accent (depth 0 active-menu trim)
COLOR_ACCENT_2 = 213            # magenta-ish accent-2 (nested-submenu trim, progressive)
COLOR_DESTRUCTIVE = 196         # bright red -- DESTRUCTIVE confirm ONLY
COLOR_DEFAULT_FG = -1           # the terminal default foreground (curses use_default_colors)

# ---- NAMED curses color-pair ids (1-based; 0 is reserved by curses for the default pair) -------------------
PAIR_SELECT = 1                 # selection highlight (maroon)
PAIR_DIM = 2                    # faded placeholder/helper
PAIR_ACCENT = 3                 # active-menu accent
PAIR_ACCENT_2 = 4               # nested-submenu accent-2
PAIR_DESTRUCTIVE = 5            # destructive (red)

# role -> (pair id, fg index, bg index). The select role is a fg-on-bg pair; the rest are fg-on-default.
_ROLE_PAIRS: Dict[str, Tuple[int, int, int]] = {
    ROLE_SELECT: (PAIR_SELECT, COLOR_SELECT_FG, COLOR_SELECT_BG),
    ROLE_DIM: (PAIR_DIM, COLOR_DIM, COLOR_DEFAULT_FG),
    ROLE_ACCENT: (PAIR_ACCENT, COLOR_ACCENT, COLOR_DEFAULT_FG),
    ROLE_ACCENT_2: (PAIR_ACCENT_2, COLOR_ACCENT_2, COLOR_DEFAULT_FG),
    ROLE_DESTRUCTIVE: (PAIR_DESTRUCTIVE, COLOR_DESTRUCTIVE, COLOR_DEFAULT_FG),
}

# ---- NAMED accessibility MARKER chars (survive a no-color terminal -- meaning is NOT color-only) ----
FOCUS_MARKER = '▸'              # prefixes the selected/focused row (508: not color-only)
FOCUS_MARKER_BLANK = ' '       # the non-focused row's leading column (keeps alignment with the marker)
BREADCRUMB_SEP = ' › '         # joins the progressive-menu breadcrumb path
ACCENT_TRIM = '┃'              # the active-menu accent trim char (a left rail on the active overlay)
SCROLLBAR_FULL = '█'           # the filled portion of the content scroll-position bar
SCROLLBAR_EMPTY = '░'          # the empty portion of the content scroll-position bar
NEW_BELOW_MARKER = '▼'         # the "N new below" scrollback-lock indicator char

# module-level flag so the attr lookups know whether ``init_theme`` actually wired color (set by init_theme).
_color_ready = False


def init_theme(theme: str = DEFAULT_THEME) -> bool:
    """Initialize the UI color pairs AFTER curses has started. Returns True iff color was actually wired.

    Guards on ``curses.has_colors()``: on a mono terminal it wires nothing and returns False (the View then
    falls back to ``A_REVERSE`` / ``A_DIM`` / ``A_BOLD`` for the roles). Fail LOUD on an unknown theme name -- a
    mis-named theme is a config fault, not a capability gap, so it is surfaced, never silently defaulted.
    """
    if theme not in THEMES:
        raise ValueError(f'unknown theme {theme!r} (known: {THEMES})')
    import curses
    global _color_ready
    if not curses.has_colors():
        _color_ready = False
        return False
    curses.start_color()
    curses.use_default_colors()
    for _role, (pair_id, fg, bg) in _ROLE_PAIRS.items():
        curses.init_pair(pair_id, fg, bg)
    _color_ready = True
    return True


def _fallback_attr(role: str) -> int:
    """The no-color capability fall-back for a role -- a curses ATTRIBUTE so the cue survives a mono terminal.

    508 alignment: the selection/destructive/accent meanings still read on a mono terminal (reverse/bold/dim),
    and the printed markers (FOCUS_MARKER / ACCENT_TRIM) carry the meaning independent of color regardless.
    """
    import curses
    return {
        ROLE_NORMAL: curses.A_NORMAL,
        ROLE_DIM: curses.A_DIM,
        ROLE_ACCENT: curses.A_BOLD,
        ROLE_ACCENT_2: curses.A_BOLD | curses.A_UNDERLINE,
        ROLE_SELECT: curses.A_REVERSE,
        ROLE_DESTRUCTIVE: curses.A_BOLD | curses.A_REVERSE,
    }[role]


def role_attr(role: str) -> int:
    """The curses attribute for a SEMANTIC role -- the color pair when wired, else the role's mono fall-back.

    Call AFTER ``init_theme``. Fail LOUD on an unknown role (a render site asking for a non-existent semantic
    role is a code fault, surfaced -- not a silent A_NORMAL that hides the typo).
    """
    if role not in ROLES:
        raise ValueError(f'unknown semantic role {role!r} (known: {ROLES})')
    import curses
    if role == ROLE_NORMAL:
        return curses.A_NORMAL
    if _color_ready:
        return curses.color_pair(_ROLE_PAIRS[role][0])
    return _fallback_attr(role)


def select_attr() -> int:
    """The SELECTION HIGHLIGHT attribute -- the maroon pair, or A_REVERSE on a mono term."""
    return role_attr(ROLE_SELECT)


def accent_for_depth(depth: int) -> str:
    """The PROGRESSIVE accent ROLE for a nested-menu depth (0 -> accent, 1+ -> accent-2, wrapping the ring)."""
    if depth < 0:
        raise ValueError(f'accent_for_depth: depth must be >= 0, got {depth}')
    return ACCENT_RING[depth % len(ACCENT_RING)]
