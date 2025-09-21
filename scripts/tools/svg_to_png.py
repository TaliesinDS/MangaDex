import sys
from pathlib import Path

def main():
    try:
        from cairosvg import svg2png  # type: ignore
    except Exception as e:
        print("ERROR: cairosvg not installed. Install with: pip install cairosvg")
        sys.exit(2)

    if len(sys.argv) < 4:
        print("Usage: python scripts/tools/svg_to_png.py <input.svg> <output.png> <size>")
        print("Example: python scripts/tools/svg_to_png.py assets/icon_seiyomi_sei.svg assets/icon_256.png 256")
        sys.exit(1)

    inp = Path(sys.argv[1])
    outp = Path(sys.argv[2])
    size = int(sys.argv[3])
    if not inp.exists():
        print(f"Input not found: {inp}")
        sys.exit(3)
    outp.parent.mkdir(parents=True, exist_ok=True)
    svg_bytes = inp.read_bytes()
    svg2png(bytestring=svg_bytes, write_to=str(outp), output_width=size, output_height=size)
    print(f"Wrote {outp} ({size}x{size})")

if __name__ == "__main__":
    main()
