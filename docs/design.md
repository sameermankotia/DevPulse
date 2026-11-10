# Interface design notes

## The thesis

The product's subject is not code and not people — it is *elapsed time*, and
specifically the gap between how long work takes and how long a change waits.
Every interface decision below follows from making that gap visible.

## The signature element

The lifecycle track. Each segment's width is its share of median pipeline time,
so a stage that takes four days is literally four times wider than one that
takes a day. The same object appears at three scales:

- the hero, where scrolling draws it across the viewport
- the dashboard, where selecting a segment exposes its spread
- each table row, where it shrinks to an 8px bar

Same shape, same meaning, three levels of detail. Nothing else in the product
is allowed to be this loud.

## Colour

Saturation only ever encodes delivery state. There is no brand colour, no
tinted chrome, and no decorative gradient. Three data colours:

| Role | Meaning | Dark | Light |
|---|---|---|---|
| Flow | Active work | `#3FD9B5` | `#136B57` |
| Friction | Queued, nobody working | `#FF6F5E` | `#9E2A1C` |
| Pending | Waiting on a person | `#FFC24B` | `#8A7300` |

Every value was measured rather than estimated. Dark-mode text colours clear
7:1 against the base surface; the three data colours clear 7.1:1 or better.

The light palette needed a second pass. The first attempt put friction
(`#C03527`) and pending (`#7A5300`) at ΔE 2.4 under protanopia — effectively the
same colour for a red-blind reader — and at 14.9 for normal vision, below the
15 floor. Re-stepping to the values above moved the worst adjacent pair to
ΔE 9.2 (deutan) and 15.5 (normal vision).

`--pending` sits at 4.28:1 on the elevated light surface, so it is used for
marks and for bold or 18px-plus labels, never for body text.

Colour is never the only carrier. Queue stages are hatched as well as coloured,
severity is a border rule as well as a tint, and trend direction is an arrow and
a word before it is a colour.

## Typography

One family: SF Pro through the system stack, which resolves natively on Apple
platforms. Display sizes carry `-0.035em` tracking; body sits at 17px, Apple's
default reading size, with 13px as the smallest supported label.

SF Mono appears only where numbers are compared column to column. That is a
function, not a texture — every numeric readout is `tabular-nums`, so counting
digits never reflow.

## Motion

One orchestrated moment: the hero track drawing itself on scroll. Everything
else responds to a person's action — hover readouts, segment selection, the
analysis panel resolving.

At rest the track shows its outline, fully laid out. The widths are the data, so
collapsing them to zero before scrolling would be dishonest as well as looking
broken.

`prefers-reduced-motion` gets the finished state rather than a degraded
animation, and the hero's conclusion is also stated in text for anyone who skips
the scene.

## Appearance

Both appearances are specified, and there is no in-app appearance switch — the
system setting is the setting. `prefers-contrast: more` collapses the secondary
and tertiary inks into primary, and `prefers-reduced-transparency` replaces the
header's blurred material with a solid surface.

## What was deliberately left out

A decorative background grid, a brand accent on controls, a gradient hero
number, and per-card shadows at varying depths. The track is the one loud thing;
everything around it is quiet on purpose.
