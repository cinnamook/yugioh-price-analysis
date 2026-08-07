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

## Tier 1 — the biggest coverage-per-effort gaps

- **Life Points tracker + calculator** — an LP value with a quick +/- keypad and
  simple math (subtract 2000, halve, etc.), and an entry in the action log. Even
  in solo, LP is core to testing burn/OTK lines.
- **Per-card counters** — add / remove / set a counter number on any card, shown
  as a small badge (spell counters, Sylvan, etc.).
- **Manual ATK/DEF adjustment** — set a temporary ATK/DEF on a monster to
  represent buffs/debuffs and continuous effects, with a one-tap reset.
- **Xyz materials (overlay)** — attach monsters *under* an Xyz monster as
  materials with a visible count, and detach a material to GY/hand. (Board slots
  already hold stacks, so this is mostly the attach/detach UX + material badge.)
- **Equip / attach card-to-card** — attach a spell (or a monster) to a monster as
  an equip; they move together; unattach to the right pile.
- **Tokens** — spawn a token with a custom name / ATK / DEF / level / attribute
  and place it in a zone.
- **Place to any specific zone, any orientation** — confirm a card can be sent to
  *any* zone or pile in face-up/face-down and ATK/DEF from anywhere (the manual
  "escape hatch" that makes odd effects representable).

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

A second player's field, change-of-control (moving a card to the opponent's side),
targeting graphics, in-duel chat, spectating, replays-as-shared-links, matchmaking.
These are the north-star **online duels** feature and sit on the auth + sync +
backend base, so they come after sync — not part of the solo-board work.

## Suggested build order

1. **Tap-and-drag** movement alongside tap-to-move (small, and every later tool
   feels better with it).
2. **Tier 1**, roughly in listed order — each is small and each multiplies how many
   real cards the board can represent.
3. **Tier 2**, with the **action log + undo** prioritized (they change the whole
   feel of the board).
4. **Tier 3** snapshots when you want repeatable combo testing.
5. Online-duel layer only after sync/backend exists.

## Sources

- DuelingBook — Rules: https://www.duelingbook.com/rules
- DuelingBook — Welcome / overview: https://www.duelingbook.com/welcome
- Duelists Unite — Guide to Manual Mode: https://forum.duelistsunite.org/t/guide-to-manual-mode/7666
