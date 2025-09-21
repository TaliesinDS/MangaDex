# App Icon (整)

This folder contains a scalable SVG for the Seiyomi (整読み) icon.

- Primary glyph: 整 ("organize")
- Colors:
  - Disc: #000000 (black)
  - Ring: #46A0FF (light blue)
  - Glyph: #FFFFFF (white)
- Canvas: 512×512 viewBox

Exports
- Recommended PNG sizes: 16, 20, 24, 32, 48, 64, 128, 256, 512
- Windows .ico: combine sizes (16/32/48/64/128/256)

Notes
- The SVG currently keeps the glyph as text for easy editing; for perfect rendering without font dependency, convert the glyph to outlines (paths) in your vector editor.
- The GUI will pick up `assets/icon_256.png` as the window icon if present (`PhotoImage`), while the EXE can use a multi-size `.ico`.
