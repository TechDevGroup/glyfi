# Human-readable mirror of the runnable BDD specs in tests/uitest/test_specs.py.
# These read as the SPEC for the core TUI behaviors and DRIVE downstream development. Each Scenario maps 1:1 to a
# runnable flow over the REAL glyfi.ui MVVM (mocked transport, virtual clock — headless + CI-safe).

Feature: command palette
  Scenario: filter to config and open it
    Given a fresh app
    When  I press '/'                       # opens the slash palette (same keymap as the curses runtime)
    And   I type 'config'                   # filters the command list
    And   I press <Enter>                   # runs the exact-name 'config' command
    Then  the app conforms to "mode==CONFIG & cell_highlighted(state)"

Feature: the OpenAI context pane
  Scenario: /ask from the palette opens the OpenAI pane
    Given a fresh app with the openai_pane plugin loaded
    When  I press '/'                       # opens the slash palette
    And   I type 'ask hello there'          # the /ask command + a seed prompt
    And   I press <Enter>                   # the command bridges to opening the pane widget
    Then  the OpenAI pane is the active widget   # the operator can now type a prompt that POSTs a completion

Feature: ephemeral status ticker
  Scenario: a pushed status is shown, expires after its TTL, and Tab cycles the ring
    Given a fresh app
    And   a status "a transient notice" was pushed
    Then  the status is "a transient notice"
    When  time passes beyond the status TTL          # WaitUntil advances the VirtualClock — no wall-clock
    Then  the status is blank                          # the ephemeral line auto-clears
    When  I press Tab                                  # advances the ticker ring
    Then  an event "TickerCycled" was emitted
    When  I press Tab                                  # advance to the 'hints' provider
    Then  the status is the input hint

Feature: input history
  Scenario: Up recalls older submitted inputs
    Given a fresh app
    And   I submitted "first-entry"
    And   I submitted "second-entry"
    When  I press Up                                   # recalls the newest submission
    And   I press Up                                   # recalls the older one
    Then  the input is " > first-entry"
    And   an event "HistoryNavigated" was emitted

Feature: bottom-anchored content
  Scenario: the newest turn sits at the bottom; PgUp reveals older turns
    Given a fresh app
    And   a seeded transcript of turns [msg-one, msg-two, msg-three]
    Then  the newest turn occupies the bottom row of the content region
    When  (on a small window) I press PgUp
    Then  older turns are revealed

Feature: the one-turn law (no auto-loop)
  Scenario: a prompt walks EXACTLY one turn
    Given a fresh app with a scripted transport
    And   the next prompt is (subj-7, "send it")
    When  I clear events
    And   I invoke 'request_prompt'                    # ONE explicit prompt → one turn → STOP
    Then  the transcript length is 1
    And   exactly 1 "TurnRecorded" event was emitted
    And   the seq is 1
    And   region 'content' contains "STAGED-7"
    #     and exactly ONE request was issued to the (mock) transport — proving no auto-loop.

  Scenario: a scripted fault is fail-loud and does NOT advance the seq
    Given a fresh app with a scripted fault for (subj-9, "forbidden")
    And   the next prompt is (subj-9, "forbidden")
    When  I clear events
    And   I invoke 'request_prompt'
    Then  the transcript length is 1                   # the failed turn is RECORDED (shown, never swallowed)
    And   region 'content' contains "403"             # the fail-loud envelope is visible
    And   the seq is 0                                 # a faulted turn must NOT advance the seq
    And   exactly 1 "TurnRecorded" event was emitted   # still one explicit turn — no retry loop
