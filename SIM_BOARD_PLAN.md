# Solo board → full manual simulator (DuelingBook-grade) — backlog

*Detailed expansion of ROADMAP.md's "Duel-field improvements". Researched from
DuelingBook's interface + rules and general manual-sim design. Last updated
2026-08-07.*

## Why DuelingBook covers every card interaction (the design principle)

DuelingBook does **not** automate card rulings. Instead it gives a fully **manual**
board where *any* card can be moved to *any* location in *any* state, plus a small
set of tools for the game elements that aren't cards (life points, counters,
tokens, dice). Because the **player enacts the effect by hand**, it covers 100% of
Yu-Gi-Oh's ~14k cards and every future card without coding a single ruling. The
versatility comes from a **rich, universal per-card action vocabulary** + **state
tools**, not from card logic.

CYBERSE's solo board already follows this philosophy. This backlog widens the
manual vocabulary to match DuelingBook, so a player can represent any line. It's
scoped to the **solo / goldfish** board we have today; true two-player online play
is the separate north-star "online duels" item and depends on the sync/backend
base.

## Already in CYBERSE's board

Proper field (5 monster / 5 S-T / 2 EMZ / field spell), tap-to-move, ATK/DEF/Set
placement, and pile viewers for deck / extra / GY / banished with draw, mill-top,
banish-top, shuffle, and view-and-act.

**Shipped 2026-08-07:**

- **Tap-and-drag** — pointer-event drag with a ghost card and drop highlighting,
  to zones *and* piles. Tap-to-move still works; a press only becomes a drag past
  an 8px threshold.
- **Life Points tracker** — both players, −100/−500/−1000/halve, a free-entry
  amount with −/+, exact undo (the applied delta is stored, so undo is correct
  even when a hit was clamped at 0) and reset.
- **Xyz materials** — attach under a monster, count badge, a viewer to detach
  individually, materials travel with the host between zones and are sent to the
  GY when it leaves the field.
- **Tokens** — custom name / ATK / DEF, placed into the first free monster zone,
  draggable like any card. Tokens carry their own values instead of a card id.
- **Declared effects** — one tap records that a card activated (★ badge) and adds
  it to a running **Declared** list; a note is optional, for clarifying what it's
  doing. This is the seed of the Tier 2 action log.
- **Opponent's side** — mirrored monster and S/T rows across a shared EMZ, their
  own field spell, and a compact strip of their deck / extra / GY / banished /
  hand. Change-of-control is a drag across the middle.
- **Pile action menus** — tapping a pile opens View / Draw / Open 5 / Open 6 /
  Mill top / Banish top / Shuffle rather than jumping straight into the viewer.
- **Turn phases** — DP SP M1 BP M2 EP with a turn counter; advancing past EP
  rolls the turn.
- **Card info** — the full card popup (text, printings, prices) from the board.
- **Mobile ergonomics** — hold-to-drag (a flick scrolls instead), a fixed action
  panel so the toolbar is never scrolled away, an x to close it, LP as a chip in
  the EMZ row's empty middle column, and no image save-callout on long press.

**Second pass, same day** — after live testing:

- **Symmetric opponent side** — a true 180-degree mirror. Their hand at the far
  edge, deck/extra flanking their spell-traps, graveyard/field spell flanking
  their monsters, banished opposite yours across the shared EMZ.
- **Dice and coin**, logged into the Declared list alongside effects.
- **Panels open where you tap**, clamped to the viewport, instead of anchoring to
  the top of the screen.
- **Desktop side panels** (>1200px): selected card's text and price on the left,
  the working pile's contents on the right, so board-and-graveyard is no longer a
  one-at-a-time affair.
- **Banish face-down**, with a clear marker in the pile viewer.
- **Taps stopped moving cards around.** A tap only places into an *empty* zone;
  tapping an occupied zone or a pile selects/opens instead. Stacking is deliberate
  (Attach or drag). This was the single biggest usability fix.
- The card menu persists through actions and closes only on the x or a click away.
- **Build stamp** in the menu savebar matching the service-worker id, so "did the
  phone actually update?" is answerable rather than guesswork.

The whole board — both sides, hand included — fits without scrolling from 360px
phones to 1920px desktops.

**Status: parked.** The board is in a good place for goldfishing. The next
meaningful step is the networked opponent, which belongs to the online-duel
milestone below — so the remaining Tier 1/2 items wait unless something specific
gets in the way while playing.

## Tier 1 — remaining

- **Per-card counters** — add / remove / set a counter number on any card, shown
  as a small badge (spell counters, Sylvan, etc.).
- **Manual ATK/DEF adjustment** — set a temporary ATK/DEF on a monster to
  represent buffs/debuffs and continuous effects, with a one-tap reset.
- **Equip / attach card-to-card** — attach a spell (or a monster) to a monster as
  an equip; they move together; unattach to the right pile. (The `mat` array added
  for Xyz materials is the obvious mechanism to reuse.)
- **Place to any specific zone, any orientation** — confirm a card can be sent to
  *any* zone or pile in face-up/face-down and ATK/DEF from anywhere (the manual
  "escape hatch" that makes odd effects representable).
- LP changes are not yet written into the declared/action log — only the last
  delta is shown. Worth folding in when the full action log lands.

## Tier 2 — fuller vocabulary

- **Reveal / peek** — reveal a card (or the whole hand) to the log for effects, and
  privately peek at a face-down card.
- **Excavate top N** — look at the top N of the deck, then reorder / keep / send.
- **Return-from-pile destinations** — from GY or banished back to hand / field /
  deck top / deck bottom (the pile viewer already opens; ensure every destination
  is offered).
- **Multi-select / group move** — select several cards at once (e.g. shuffle 3 back
  from hand).
- **Coin flip & dice roll** — with the result written to the log.
- **Phase indicator + turn/pass** — a DP / SP / MP1 / BP / MP2 / EP tracker and a
  "new turn" that handles the standby/draw step; structures goldfish reps.
- **Action log** — a running text log of every board action (DuelingBook's "duel
  log"). Invaluable for reviewing a line — and it's the backbone for future
  replays.
- **Undo last action** — enormously useful on a manual board; a misclick shouldn't
  end a test.

## Tier 3 — snapshots & review

- **Save / restore a board state** — snapshot a set-up board and reload it, so you
  can test a specific scenario or combo start repeatedly.
- **Board replay** — step through the action log. (A stepping-stone toward the
  online-duel layer.)

## Belongs to the online-duel layer (far horizon — not the solo board)

Targeting graphics, in-duel chat, spectating, replays-as-shared-links,
matchmaking, and a *networked* second player. These are the north-star **online
duels** feature and sit on the auth + sync + backend base, so they come after
sync — not part of the solo-board work.

**Note (2026-08-07):** a *manual* opponent side now exists on the solo board —
mirrored monster and S/T rows with a shared EMZ, their own field spell, and a
compact strip of their deck / extra / GY / banished / hand. Change-of-control is
therefore just a drag across the middle. None of this is networked; it's somewhere
to park and attack into their cards while goldfishing. Their deck and extra start
empty by design — this is not a second goldfish deck.

## Suggested build order

1. ~~**Tap-and-drag** movement alongside tap-to-move~~ — done 2026-08-07.
2. **Tier 1**, roughly in listed order — each is small and each multiplies how many
   real cards the board can represent. Life points, Xyz materials and tokens are
   done; counters, manual ATK/DEF and equips remain.
3. **Tier 2**, with the **action log + undo** prioritized (they change the whole
   feel of the board).
4. **Tier 3** snapshots when you want repeatable combo testing.
5. Online-duel layer only after sync/backend exists.

## Sources

- DuelingBook — Rules: https://www.duelingbook.com/rules
- DuelingBook — Welcome / overview: https://www.duelingbook.com/welcome
- Duelists Unite — Guide to Manual Mode: https://forum.duelistsunite.org/t/guide-to-manual-mode/7666
