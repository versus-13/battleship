# Battleship — design specification

Mockup sources: `Main.dc.html` (light theme), `Dark.dc.html` (dark), `Kit.dc.html`
(palette and states), `canvas.json` (canvas index).

Note: `.dc.html` is the design editor format (`<x-dc>`, `<sc-for>`, `class Component extends
DCLogic`). It is the source of truth for markup and styles, but not production code: in
production the markup is plain HTML and `sc-for`/`sc-if` are replaced by rendering the list
of cells and conditions.

## Fonts

- Headings, turn status, letters and digits along the board edges: **Caveat** 400–700,
  fallback `'Segoe Script', cursive`.
- Interface, counters, journal, coordinates: **IBM Plex Mono** 400–600,
  fallback `ui-monospace, Menlo, monospace`.
- Loading: `https://fonts.googleapis.com/css2?family=Caveat:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap`

## Tokens

| role | light | dark |
| --- | --- | --- |
| page background | `#FAF8F1` | `#14161A` |
| page grid line | `#D6E0E9` | `#262B33` |
| board grid line | `#A9C3D8` | `#39424F` |
| main stroke ("ink" / "chalk") | `#2A4A9A` | `#8FB6E8` |
| text | `#1B2F63` | `#E7E4DA` |
| hit | `#C2392F` | `#E8695C` |
| secondary text ("pencil") | `#6A7280` | `#8B9098` |
| ship fill | `rgba(42,74,154,0.10)` | `rgba(143,182,232,0.12)` |
| sunk fill | `rgba(194,57,47,0.12)` | `rgba(232,105,92,0.16)` |
| hover highlight | `rgba(42,74,154,0.09)` | `rgba(143,182,232,0.12)` |

Inputs/buttons: radius `2px`, border `1.5px`, the primary button has a "double outline"
`box-shadow: 3px 3px 0 rgba(ink, 0.18)`.

## Grid

Everything is built on a **40 px** module — both the notebook cell and the board cell.

- Page background: two `repeating-linear-gradient`s of 40 px (1 px line).
- Board: 10 × 10 cells = 400 × 400. The board frame is drawn with
  `box-shadow: 0 0 0 1.5px var(--ink)` so as not to break the 40 px layout.
- Coordinate rulers: 40 px on top (А Б В Г Д Е Ж З И К) and 40 px on the left (1–10),
  Caveat 26 px, ink color. The whole board block is 440 × 440.
- Desktop 1440 × 880: paddings `40px 40px 40px 80px`, the red vertical notebook margin
  line at `x = 40`. Columns: board 440 — gap 120 — board 440 — gap 120 — panel 200.
- Vertical: header 80, gap 40, work area 480, gap 40, journal 160.

## Cell states

All marks are SVG in `viewBox="0 0 40 40"`, strokes with rounded caps and a slight
curve: the line must look hand-drawn, not generated.

- **empty** — nothing.
- **hover** — `hover` background, `crosshair` cursor; focus — `outline: 2px solid var(--ink)`.
- **aim** — crosshair + dashed circle `r=6.5`, stroke 1.3–1.6 px.
- **miss** — `<circle r="3">` in ink color, opacity 0.5–0.6.
- **hit** — a cross of two `Q` curves, stroke 2.6 px, hit color.
- **sunk** — the cross + the ship outline in red; the perimeter cells automatically
  become "miss".
- **own ship** — an outline with deliberately uneven vertices over the cells:
  `M6 6.4 L34.4 5.4 L35 33.8 L5.6 34.8 Z` (1 deck, 40 × 40),
  `M6 6.2 L74.2 5.2 L75 34 L5.4 35 Z` (2 decks horizontal),
  the 3- and 4-deckers have a middle point with a ±1 px sag.

## Accessibility

- Cells of the enemy board are real `<button type="button">` with an `aria-label` like `Д6`.
- The own board is not interactive, marks are `aria-hidden`.
- Text contrast ≥ 4.5:1 in both themes; the secondary grey is already tuned to the minimum.

## Mobile version (draft)

The module scales: cell `min(9vw, 40px)`, board — `calc(10 * cell)`, coordinate
rulers — one cell. The right panel moves under the boards, the journal collapses
into a row. Minimum tap target is 44 px, so on narrow screens the active area of a
cell is expanded with padding, not the grid.
