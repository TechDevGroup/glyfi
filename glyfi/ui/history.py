"""history -- the PURE in-memory INPUT HISTORY: submitted inputs + an Up/Down navigation cursor.

The input line keeps a history of the operator's SUBMITTED inputs. **Up** walks to OLDER entries, **Down** walks
back toward NEWER (and past the newest back to the live, in-progress buffer). This is the shell-style recall the
``> `` line gives once Up/Down are freed from content scroll (scroll moved to PgUp/PgDn).

Pure + mechanism-testable (no curses): ``record(text)`` appends a submission; ``older()`` / ``newer()`` move the
cursor and return the buffer to restore; ``reset()`` drops the cursor back to the live edge. The ViewModel owns
the live buffer and asks this for what to restore on an arrow.

PERSISTENCE IS DEFERRED (explicit seam, in-memory only): per-session on-disk history is a future feature. The
seam is NAMED here -- ``input_history_scope`` -- and reuses the app-level session-persist seam; today the
history is purely IN-MEMORY (dropped when the app exits). No disk I/O here.

stdlib only; holds plain strings.
"""
from dataclasses import dataclass, field
from typing import List, Optional

# ---- NAMED deferred-persistence seam (in-memory only) -----------------------------------------------------
# When persistence lands it scopes the history per session and reuses the app-level session-persist seam.
SEAM_INPUT_HISTORY_SCOPE = 'input_history_scope'
# the navigation directions (NAMED -- emitted on a HistoryNavigated event).
DIR_OLDER = 'older'
DIR_NEWER = 'newer'


@dataclass
class InputHistory:
    """The PURE in-memory input history -- a list of submitted entries + a navigation cursor over them.

    ``entries`` is oldest->newest. ``cursor`` is the position the arrows point at: ``len(entries)`` means the
    LIVE edge (the in-progress buffer, not a recalled entry); ``len-1`` is the newest recalled entry, ``0`` the
    oldest. ``record`` appends and snaps the cursor back to the live edge (a fresh submission ends recall).

    DEFERRED: per-session persistence (``SEAM_INPUT_HISTORY_SCOPE``) -- in-memory only.
    """
    entries: List[str] = field(default_factory=list)
    cursor: int = 0
    # persistence scope seam (deferred): None == in-memory only.
    scope: Optional[str] = None

    def record(self, text: str) -> None:
        """Append a submitted input and snap the cursor to the live edge (recall starts fresh next time)."""
        text = str(text)
        if text:
            self.entries.append(text)
        self.cursor = len(self.entries)

    def older(self) -> Optional[str]:
        """Up -- move toward OLDER entries; return the entry to restore, or None if already at the oldest/empty."""
        if not self.entries:
            return None
        if self.cursor > 0:
            self.cursor -= 1
        return self.entries[self.cursor]

    def newer(self) -> Optional[str]:
        """Down -- move toward NEWER; return the entry to restore, or '' at the LIVE edge (clears the buffer)."""
        if not self.entries:
            return None
        if self.cursor < len(self.entries):
            self.cursor += 1
        if self.cursor >= len(self.entries):
            return ''            # past the newest -> the live edge: an empty buffer
        return self.entries[self.cursor]

    def reset(self) -> None:
        """Drop the cursor back to the live edge (call when the operator edits / submits)."""
        self.cursor = len(self.entries)
