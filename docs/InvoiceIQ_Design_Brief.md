# InvoiceIQ — Design Brief

Put this file in `docs/`. It defines how every page looks and moves. Build section 14 of the build guide in this style.

**Direction in one line:** calm, light-grey editorial canvas; oversized black type; monospace "voice" for the AI; pixel and dot-matrix accents that come alive under the cursor. Inspired by zamp.ai's design language, **not a copy of it**.

## 0. Rules

1. **Inspired, never copied.** Do not use Zamp's logo, wordmark, role avatars, illustrations, images, copy or font files. Everything here is InvoiceIQ's own: own name, own mascot, own mark, own words.
2. **Finance first.** Numbers, decisions and reasons must be instantly readable. Decoration never sits behind data.
3. **Motion is feedback, not noise.** Every animation says something happened (a stage finished, a decision landed). Respect `prefers-reduced-motion`.
4. **Styling never changes behaviour.** Restyling must not alter API calls, data flow or logic.

## 1. Design tokens

Put these as CSS variables in `index.css` and map them in the Tailwind theme.

### Colour

| Token | Value | Use |
| --- | --- | --- |
| `--canvas` | `#F0F0EF` | Page background |
| `--surface` | `#F5F5F4` | Large containers (same family as canvas, separated by border) |
| `--raised` | `#FFFFFF` | Pills, inputs, popovers, secondary buttons |
| `--line` | `#E2E2E0` | 1px borders and dividers |
| `--ink` | `#0A0A0A` | Headings, primary buttons, vertical title bars |
| `--ink-2` | `#55555A` | Body and secondary text |
| `--ink-3` | `#9A9A9F` | Captions, placeholders, logo marquee |
| `--accent` | `#2B5CF6` | Electric blue: links, focus rings, active step, dot-matrix panels |
| `--approve` | `#12A150` on `#E7F6EE` | Approve |
| `--hold` | `#C77700` on `#FDF3E1` | Hold |
| `--reject` | `#D6333A` on `#FCE9EA` | Reject |
| `--fraud` | `#D6333A` on `#FCE9EA` + dithered red border | Fraud banner (4.6, 4.7) |

**Texture palette** (only for pixel mascot, dots and sample-pill markers, never for data): violet `#8B5CF6`, teal `#14B8A6`, pink `#EC4899`, lime `#A3E635`, sky `#38BDF8`, amber `#F59E0B`.

### Type

| Role | Font | Notes |
| --- | --- | --- |
| Headings and body | **Geist** (`@fontsource-variable/geist`) | Headings tight: `letter-spacing: -0.02em`, weight 500–600 |
| AI voice, buttons, labels, codes | **Geist Mono** (`@fontsource-variable/geist-mono`) | Agent speech bubble, all buttons, uppercase section labels, finding codes, run IDs |
| Numbers in tables | Geist with `font-variant-numeric: tabular-nums` | Right-aligned money |

Free alternatives if needed: Inter Tight + JetBrains Mono.

Scale: display 72/64 (page hero only), h1 40, h2 28, h3 20, body 16, small 14, label 12 mono uppercase `letter-spacing: 0.08em`.

### Shape and depth

- Radius: big containers `28px`, cards `20px`, inputs `14px`, pills and buttons `9999px`.
- Borders do the separating: 1px `--line`. Shadows only on floating things (popovers, toasts): `0 8px 30px rgba(0,0,0,0.06)`.
- Spacing base 4px; containers pad 40–56px on desktop.

## 2. Signature components

### Buttons (pill, mono)
- **Primary:** black pill, white Geist Mono text, 44px tall. Hover: background slides to `--accent` (200 ms), trailing pixel arrow nudges 3px right.
- **Secondary:** white pill, 1px `--line`, black mono text. Hover: border `--ink`.
- **Link with arrow:** text + our own 5×5 pixel arrow SVG; underline grows left→right on hover.

### Section title with bar
A 6px × 36px black rounded bar, then an h2. Used at the top of every content panel ("How I'm checking this invoice").

### Split container (the core layout)
One big rounded `--surface` container per page with a 1px border, split into:
- **Left rail (~320px):** page title (h1), the agent bubble or context, and at the bottom a stack of **pill links** (white pill, small textured dot + label) to jump between sections of the page.
- **Right panel:** the content, separated by a vertical 1px line.

### Pill link / sample pill
White pill, 48px tall, a 14px circle filled with a texture colour (noise gradient), label in Geist. Active: border `--ink`. Hover: lifts 1px.

### Agent speech bubble ("the AI's voice")
Rounded 20px box, `#E8E8E6` fill, Geist Mono 15px, generous line-height. It narrates:
- Idle: "Hi, I'm Iris, your AP associate. Drop an invoice and I'll check it against your POs, vendors and tax rules."
- During a run, one short line per stage, typed in (30 ms/char, instant if reduced motion): "Reading the invoice… it's a scan, reading it visually." → "Found 'PO 105'. That's PO-2026-105." → "Bank account doesn't match the one on file. Stopping for Finance."
- Name "Iris" is a placeholder; the owner may rename it.

### Pixel mascot (our own)
A 12×12 pixel character drawn as an SVG `rect` grid, **our own silhouette** (for example, a small invoice-shaped robot with a folded corner). Fill with a texture gradient + SVG noise filter so it looks printed. States via small pixel changes: idle (blinks every 4 s), thinking (eyes scan left-right), approved (smile), hold (one raised pixel "eyebrow"), reject (flat mouth). Sits next to the speech bubble.

### Dot-matrix wordmark (the cursor effect)
Canvas component that draws "InvoiceIQ" (or any text) as a grid of dots:
1. Render text to an offscreen canvas; sample every 10px; keep points where alpha > 0.5.
2. Draw circles (radius 3–4px). On mouse move, dots within 90px are pushed away, then spring back (simple velocity + damping).
3. Pause with IntersectionObserver when off-screen; static if `prefers-reduced-motion`; DPR-aware; no libraries.

Use it on the **Process empty state** (big, in `--accent` panel with white dots) and in a **footer band** of the app shell. Never behind data.

### Pixel / dither accents
- Dropzone hover: a CSS dither pattern (tiny repeating gradient dots) fades in at 15% opacity.
- Decision card edge: a 6px dithered strip in the decision colour.
- Arrows: pixel SVG, not a regular icon.
All lightweight CSS/SVG. **No WebGPU, no WebGL.**

### Accordion (evidence)
Same pattern for stage evidence and FAQs: row with bold label; open state gets `#EAEAE8` background and the content indented with a 3px light left bar.

### Top bar (headroom)
Own mark (left), centre nav links (Process, Review, Dashboard, Purchase orders, Vendors, Outbox, Tests), right: role selector as a secondary pill and "Process invoice" primary pill. **Hides when scrolling down, reappears when scrolling up** (translateY, 250 ms). Settings under a small menu on the right.

### Own mark
Simple and ours: e.g. a 3×3 pixel "i" with a dot, or two pixel brackets. **Not** Zamp's two slanted bars.

## 3. Pages in this style

### Process (the demo page)
- **Left rail:** "Process" h1, mascot + speech bubble, then sample pills (one per sample, texture dot, name like "Happy path", "No PO reference", "Bank changed"). Hover shows the story in a small popover.
- **Right panel, before a run:** big dropzone ("Drop an invoice PDF") with the dot-matrix wordmark band below it.
- **Right panel, during and after a run:**
  1. **Decision card** on top once decided: big mono stamp (APPROVED / ON HOLD / REJECTED) that scales in, headline sentence ("Pay ₹2,65,500 to Deccan Office Interiors by 04 Nov 2026."), reasons list, dithered edge strip. Fraud: red banner "Finance must verify: bank account changed".
  2. **Timeline "How I'm checking this invoice":** 9 steps like "Step 1 … Step 9", each a row with number, name, one-line result, status chip (pass / warn / fail / info) and duration. Rows slide up + fade in as SSE events arrive (stagger 60 ms). Current step shows a thinking shimmer. Click a row to open its evidence accordion (tables for PO elimination and scores, ledger, tax split).
  3. **Invoice vs PO** comparison table, mismatched cells tinted `--hold`.
  4. **PDF preview** in a collapsible panel.

### Dashboard
Split container: left rail with KPI summary pills; right with metric cards (big numbers, tabular), decisions-over-time bars and top hold reasons (Recharts, monochrome + one accent), runs table with hover rows.

### Review, POs, Vendors, Outbox, Tests, Settings
Same split container. Tables: no zebra, 1px row dividers, row hover `#EAEAE8`, money right-aligned, codes in mono chips.

## 4. Motion spec

| Moment | Motion |
| --- | --- |
| Page enter | Fade + 8px rise, 250 ms, ease-out |
| Stage arrives | Slide up 12px + fade, 220 ms, 60 ms stagger |
| Current stage | 1.2 s shimmer on the row background |
| Decision lands | Stamp scales 0.9 → 1 with slight overshoot, 300 ms; mascot changes state |
| Button hover | Colour 200 ms; arrow +3px |
| Top bar | Hide/show on scroll direction, 250 ms |
| Dots | Cursor repel + spring back |

All motion off (instant) under `prefers-reduced-motion`.

## 5. Accessibility and quality

- Text contrast ≥ 4.5:1; decision colours always paired with a word, never colour alone.
- Visible focus ring: 2px `--accent`, offset 2px.
- Keyboard: every pill, row and button reachable; accordions use buttons with `aria-expanded`.
- Works at 1280px and above for the demo; degrades sensibly to tablet.
- Money always `₹` with en-IN grouping.
