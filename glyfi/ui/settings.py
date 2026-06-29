"""settings -- the NAMED, PLUGGABLE display Settings for the app (fenced regions, rule char, keys, title).

Engineering standard (hard): NO magic values. Every appearance/anchor/key tunable is a NAMED field on a frozen
``AppSettings`` dataclass with a NAMED default -- never a bare literal at a render site. Settings are PLUGGABLE:
a caller can construct a custom ``AppSettings`` (different regions, key bindings, sizes) and hand it to the
ViewModel/View; the defaults here are just the out-of-the-box fenced layout.

This module is pure data. It references the layout anchor vocabulary (a sibling module) so a settings-defined
region names a real anchor.

The FENCED region set (top -> bottom):
  * REGION_TITLE        anchored TOP    h=1 -- the title line (line 1).
  * REGION_STATE        anchored TOP    h=1 -- the STATE strip (line 2): config-bound slots spread across the width.
  * REGION_HEADER_RULE  anchored TOP    h=1 -- a full-width rule fencing the header off from content.
  * REGION_CONTENT      FILL                -- the bottom-anchored content view (transcript / help / overlays).
  * REGION_STATUS       anchored BOTTOM h=1 -- the EPHEMERAL ticker line (its OWN line, ABOVE the input fence).
  * REGION_INPUT_RULE   anchored BOTTOM h=1 -- the top of the input fence (a full-width rule).
  * REGION_INPUT        anchored BOTTOM h=1 -- the input + HINTS line ``> {buffer-or-hint}``.
  * REGION_STATUS_RULE  anchored BOTTOM h=1 -- the bottom of the input fence (a full-width rule).
  * REGION_DETAILS      anchored BOTTOM h=1 -- the details bar: left group left-justified, right group right-justified.

BOTTOM bands carve bottom-UP in region order, so the bottommost (details) is listed FIRST among the BOTTOM
regions and the topmost-of-the-bottom (status) LAST. The on-screen bottom block then reads top->bottom as:
status, input_rule, input, status_rule, details. Adding the status line costs the FILL content exactly one row.
"""
from dataclasses import dataclass, field
from typing import Dict, Tuple
from glyfi.ui.layout import Region, ANCHOR_TOP, ANCHOR_BOTTOM, ANCHOR_FILL

# ---- NAMED region names (the fenced layout) ---------------------------------------------------------------
REGION_TITLE = 'title'
REGION_STATE = 'state'
REGION_HEADER_RULE = 'header_rule'
REGION_CONTENT = 'content'
REGION_STATUS = 'status'         # the EPHEMERAL ticker line -- its OWN line, ABOVE the input fence
REGION_INPUT_RULE = 'input_rule'
REGION_INPUT = 'input'
REGION_STATUS_RULE = 'status_rule'
REGION_DETAILS = 'details'

# regions a power-user may passively hide via UserConfig.visible (NO interactive toggle command).
HIDEABLE_REGIONS = (REGION_STATE, REGION_DETAILS)

# ---- NAMED band heights (all single-line bands; no magic literals) ----------------------------------------
DEFAULT_TITLE_HEIGHT = 1
DEFAULT_STATE_HEIGHT = 1
DEFAULT_RULE_HEIGHT = 1
DEFAULT_STATUS_HEIGHT = 1
DEFAULT_INPUT_HEIGHT = 1
DEFAULT_DETAILS_HEIGHT = 1

# ---- NAMED render chars ------------------------------------------------------------------------------------
RULE_CHAR = '─'                 # the full-width fence rule (repeated to the region width)
INPUT_PROMPT = ' > '            # the slash-command input prompt prefix
SLOT_SEP = '  '                 # the gap between state-strip slots when not spread-justified
DETAILS_GROUP_SEP = '  '        # the gap between slots within a details group

# ---- NAMED responsive HINT variants (the input-line hint shrinks gracefully -- never ellipsis off-screen) ---
# When the pane is too narrow for the LONG hint, the View picks the next shorter NAMED variant that fits (and
# the SHORT variant as a last resort) rather than truncating the hint into another region / off the screen edge.
INPUT_HINT_LONG = 'type / for commands · ↑↓ history · Tab ticker'
INPUT_HINT_MED = '/ commands · ↑↓ history'
INPUT_HINT_SHORT = '/ for commands'
INPUT_HINT_VARIANTS = (INPUT_HINT_LONG, INPUT_HINT_MED, INPUT_HINT_SHORT)  # widest -> narrowest

# ---- NAMED per-region MINIMUM band heights (the responsive SMUSH floor; content yields first, chrome holds) -
# Single-line chrome bands have a hard floor of 1 (they never vanish); the FILL content has no floor (it yields
# all its real-estate first). NAMED so the smush has no magic literal.
MIN_BAND_HEIGHT = 1

# ---- NAMED key bindings (NORMAL-mode operator keys; modal keys are handled in the curses view) ------------
KEY_QUIT = 'q'
KEY_PROMPT = 's'
KEY_MODE_CYCLE = 'm'
KEY_PALETTE = '/'               # opens the slash-command palette (starts the input buffer)
KEY_TRAVERSE = 'c'              # enters CONTENT-TRAVERSAL: a wrap-aware line caret over the content (not scrolling)
DEFAULT_TITLE = 'glyfi'

# ---- NAMED special keys (handled by the curses adapter against curses key codes; named here, no magic) -----
# Content scroll is OFF Up/Down (those are input history now) ONTO PgUp/PgDn (+ optional Ctrl-U / Ctrl-D).
KEY_SCROLL_PAGE_UP = 'page_up'      # PgUp -- scroll content history UP (toward older)
KEY_SCROLL_PAGE_DOWN = 'page_down'  # PgDn -- scroll content history DOWN (toward newest)
KEY_SCROLL_HALF_UP = 'half_up'      # Ctrl-U -- half-page up
KEY_SCROLL_HALF_DOWN = 'half_down'  # Ctrl-D -- half-page down
KEY_HISTORY_OLDER = 'history_older' # Up -- recall an OLDER submitted input
KEY_HISTORY_NEWER = 'history_newer' # Down -- recall a NEWER submitted input
KEY_TICKER_CYCLE = 'ticker_cycle'   # Tab -- advance the ephemeral ticker ring
# the literal control bytes for Ctrl-U / Ctrl-D / Tab (NAMED, so the adapter has no bare ints).
CTRL_U = 21
CTRL_D = 4
TAB = 9


def _default_regions() -> Tuple[Region, ...]:
    """The default FENCED layout. BOTTOM bands carve bottom-UP, so list the bottommost (details) FIRST and
    the topmost-of-the-bottom (status) LAST among the BOTTOM regions.

    On-screen the bottom block then reads (top->bottom): status, input_rule, input, status_rule, details.
    The status line sits ABOVE the input fence (status listed AFTER input_rule among the BOTTOM regions so it
    carves a row higher up); the FILL content loses exactly that one row.
    """
    return (
        Region(name=REGION_TITLE, anchor=ANCHOR_TOP, size=DEFAULT_TITLE_HEIGHT),
        Region(name=REGION_STATE, anchor=ANCHOR_TOP, size=DEFAULT_STATE_HEIGHT),
        Region(name=REGION_HEADER_RULE, anchor=ANCHOR_TOP, size=DEFAULT_RULE_HEIGHT),
        Region(name=REGION_DETAILS, anchor=ANCHOR_BOTTOM, size=DEFAULT_DETAILS_HEIGHT),
        Region(name=REGION_STATUS_RULE, anchor=ANCHOR_BOTTOM, size=DEFAULT_RULE_HEIGHT),
        Region(name=REGION_INPUT, anchor=ANCHOR_BOTTOM, size=DEFAULT_INPUT_HEIGHT),
        Region(name=REGION_INPUT_RULE, anchor=ANCHOR_BOTTOM, size=DEFAULT_RULE_HEIGHT),
        Region(name=REGION_STATUS, anchor=ANCHOR_BOTTOM, size=DEFAULT_STATUS_HEIGHT),
        Region(name=REGION_CONTENT, anchor=ANCHOR_FILL),
    )


def _default_keys() -> Dict[str, str]:
    """The default NORMAL-mode key->command map (a custom Settings can rebind any key)."""
    return {KEY_QUIT: 'quit', KEY_PROMPT: 'prompt', KEY_MODE_CYCLE: 'mode_cycle',
            KEY_PALETTE: 'palette', KEY_TRAVERSE: 'traverse'}


@dataclass(frozen=True)
class AppSettings:
    """The PLUGGABLE app settings -- fenced regions, key bindings, and the title. All NAMED, no magic.

    Construct a custom instance to re-anchor regions, resize bands, or rebind keys; the defaults give the
    out-of-the-box fenced layout. Frozen (immutable) so a View can trust the settings won't shift under it.
    """
    title: str = DEFAULT_TITLE
    regions: Tuple[Region, ...] = field(default_factory=_default_regions)
    keys: Dict[str, str] = field(default_factory=_default_keys)
    # C7: F-key (or any int key code) -> registered widget name. First-class binding for the
    # downstream ``widget_keys`` convention. OCP default: EMPTY -- no key opens a widget, so
    # NORMAL-mode dispatch is byte-identical to today until a consumer populates this.
    widget_keys: Dict[int, str] = field(default_factory=dict)

    def command_for(self, key: str) -> str:
        """The command bound to ``key``, or the empty string if the key is unbound (the View ignores it)."""
        return self.keys.get(key, '')

    def widget_for(self, ch: int) -> str:
        """The widget name bound to int key code ``ch``, or '' if unbound (NORMAL-mode dispatch ignores it)."""
        return self.widget_keys.get(ch, '')
