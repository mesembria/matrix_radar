# Sweep that reveals planes, and a better details page: design

## Why
- The sweep was decorative: dots crept along on their own and jumped every ~20 s when new data came. Philippe wants the sweep to do the revealing, like a real radar.
- On the details page he keeps looking planes up to learn what type they are. He also wants the page to keep the sense of where the plane is.

## Radar: sweep reveals, then fades (Philippe approved the on-panel test)
- Sweep period by range: 5 mi = 10 s, 10 mi and 20 mi = 20 s (tuned to small planes, ~110 kt, which are most of his traffic; capped at the 20 s data rate). Replaces SWEEP_MS = 4000.
- A plane's mark is drawn where the sweep last crossed its bearing, and moves only then. New planes appear when the sweep first reaches them.
- After each pass a mark fades in steps: 100%, 70%, 50%, 33% over one sweep period. Never fully dark.
- Sweep off: marks move every frame at full brightness, as before.
- Altitude scale, counts and details stay live (not tied to the sweep).

## Details page
Layout (64x32):
- Left (about 10 characters wide): ID, with "n/N" at the right of that area when several planes are in the ring. Route as airport codes ("DEN>SFO"), or ground speed for planes with no route. Height in band color.
- Right: mini radar about 20x20 px. House dot in the middle, faint ring at the edge, the plane as an arrow in its band color pointing along its heading. Edge = inner ring distance.
- Full-width line near the bottom: plane type name ("CESSNA 172", "BOEING 737-800"), at most 16 characters. Falls back to the type code ("C172").
- Bottom bar: closeness. Full when over the house, empty at the inner ring's edge. Band color.
- Removed: the "1.1MI NW" line (the mini radar and bar replace it) and the rotation countdown in the bar ("n/N" is enough). Rotation every 6 s and the 30 s pause after a tap stay; while paused the bar turns gray as before.

## Data: plane type names (approach A, Philippe's pick)
- HA adds a 9th field to each `packed` record: the Flightradar24 integration's aircraft model, upper case, only `A-Z 0-9 - space`, cut to 16 characters, empty if missing.
- The board accepts 8 or 9 fields, so an old package keeps working.
- Expect messages up to about 2.3 KB with 40 planes. Check on the board before relying on it.

## Approaches considered (names)
- A. HA sends the name for every plane (picked: fewest moving parts).
- B. HA sends names only for planes within ~5 mi: smaller messages, but a fast plane can show the code for up to 20 s.
- C. A code-to-name table on the board: no HA change, but memory on a tight board and gaps for unlisted types.

## Not doing
Closest-approach line, big ID font, climb/descend arrow, city names (Philippe said no or skipped).

## Constraints
- Frame rate at least 8 fps with 40 planes and the sweep on (the test version ran at 16 fps with 18 planes).
- Plane bands keep their colors; radar parts stay green.
- Writing style for any text: plain short words, no em dashes.

## Left to the builder
Exact pixel positions, arrow shape, how names are shortened beyond the 16-character cut, palette layout for fade levels.
