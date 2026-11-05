# SubFa brand mark

The mark is the product in one glance: a subtitle caption sitting on a
dark video frame. Two white caption lines, the second one shorter the
way real captions break, and one amber bar under them. The amber bar is
the active cue, the same signal the editor uses for the selected line
and the stage uses for progress. Nothing else is in the mark: no play
triangle, no speech bubble, no letterform trick.

## Construction

The mark is drawn on a 240 unit grid, taken from the caption-block
motif of the web design (direction «صحنه», see the design note in the
project design folder).

- Block: 240 x 240, corner radius 60 (a quarter of the side, the
  largest step of the product radius scale, because the block is a
  screen).
- Caption lines: height 24, fully rounded ends, left edge at x 60.
  First line width 120 at y 67, second line width 79 at y 113, amber
  bar width 120 at y 158. The lines sit in the left-centre of the
  frame, like a caption block aligned to the frame edge, not centred
  like a menu icon.
- Clearspace on every side: the height of the amber bar (24 units,
  a tenth of the mark). Nothing enters that zone.
- Minimum sizes: master mark 24 px, small variant 12 px. Below 24 px
  always use the small variant.

## The small-size variant

`logo-small.svg` is the same mark with reinforced strokes for favicon
and tab sizes: line height grows from 24 to 36 units and the shorter
line widens from 79 to 88, so at 16 px the three bars stay separate
and the amber bar still reads. The favicon files (`favicon.ico`,
`favicon-16.png`, `favicon-32.png`, `favicon-48.png`) are rendered
from this variant, never from the master.

## Colors

| Role | Hex | Notes |
| --- | --- | --- |
| Stage (the block) | `#0D1218` | The video frame from the design tokens |
| Caption amber | `#F2B705` | The one accent; 10.34:1 on the stage |
| Caption lines | `#FFFFFF` | 18.80:1 on the stage |
| Ink (wordmark) | `#182028` | 14.93:1 on paper |
| Paper (preview ground) | `#F2F4F6` | Social preview background |

Amber is never a background for the mark on light surfaces (1.65:1 on
paper); on light ground the block carries its own dark, so the mark
works unchanged on any background.

## Which file where

- `assets/logo.svg`: the master mark. App icons, docs, anywhere a
  square logo at 24 px or larger is needed.
- `assets/logo-small.svg`: the reinforced mark for under 24 px.
- `assets/logo-lockup.svg`: mark plus the SubFa wordmark (Vazirmatn
  ExtraBold, converted to vector paths, so it renders identically
  everywhere). README headers, site header, presentations. Use the
  lockup when the name is not already next to it in text.
- `assets/logo-512.png` down to `logo-32.png`: raster exports of the
  master for stores and embeds that cannot take SVG.
- `assets/bot-avatar-512.png`: the caption lines centred on a
  full-bleed stage ground with generous padding, sized for the
  Telegram bot profile photo, whose circular crop keeps the lines
  fully inside.
- `assets/social-preview.png` (1280 x 640): the GitHub social preview
  image; set it under the repository settings, Social preview.
- `assets/favicon.ico`: browser favicon, 48/32/16 in one file.

## Rules

- Do not recolor the lines, outline the block, add shadows or
  gradients, or put the mark on a busy photo. The block is the frame;
  it carries itself.
- Do not stretch, rotate, or separate the amber bar from the lines.
- The wordmark is never set in another font next to the mark; if the
  name appears without the lockup, plain text is fine.
