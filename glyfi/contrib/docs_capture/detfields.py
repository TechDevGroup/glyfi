"""detfields -- the shared DETERMINISTIC detail-field pin for reproducible, trace-free captured docs.

A captured Markdown artifact must embed NO machine-specific path and NO real wall clock, so it is byte-stable
across runs and across machines. The two live detail fields the UI renders -- the working directory (cwd) and
the local time -- are therefore PINNED to fixed neutral placeholders for a capture run.

This is the single owner of that override so both the gallery and the spec-doc generator pin the SAME values
through the SAME public field-registry seam (``override_field_fn``). Normal runtime is untouched (a real user
still sees their own cwd / time); the override is applied only inside a doc-generation process.

Self-contained: the public ``glyfi.ui.fields`` registry seam + stdlib only.
"""
from glyfi.ui import fields as fields_mod

# ---- NAMED neutral placeholders (committed docs must be reproducible) --------------------------------------
DETERMINISTIC_CWD = '~/glyfi'          # neutral placeholder -- not the real cwd, no machine path
DETERMINISTIC_LOCALTIME = '00:00:00'   # fixed clock -- reproducible across runs


def pin_deterministic_fields() -> None:
    """Pin the live detail fields (cwd / localtime) to fixed neutral values for a capture run ONLY.

    Idempotent: re-applies the override at the start of each build so a generated artifact never embeds the real
    working directory or the real wall clock. Uses the public field-registry seam so the slot LABELS the config
    editor shows are preserved; only the rendered VALUE is pinned.
    """
    fields_mod.override_field_fn(fields_mod.ALIAS_CWD, lambda _vm: DETERMINISTIC_CWD)
    fields_mod.override_field_fn(fields_mod.ALIAS_LOCALTIME, lambda _vm: DETERMINISTIC_LOCALTIME)
