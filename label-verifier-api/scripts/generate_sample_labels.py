"""Create synthetic label images for a manual demo."""

from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont

from app.services import GOVERNMENT_WARNING

OUTPUT = Path(__file__).parents[1] / "samples"
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ) if bold else FONT_CANDIDATES
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], width: int, text_font, leading: int) -> int:
    x, y = xy
    for line in wrap(text, width=width):
        draw.text((x, y), line, fill="#121826", font=text_font)
        y += leading
    return y


def label(name: str, abv: str = "45% Alc./Vol. (90 Proof)", volume: str = "750 mL", warning: str = GOVERNMENT_WARNING, rotate: bool = False) -> None:
    image = Image.new("RGB", (1800, 2500), "#f8f1dc")
    draw = ImageDraw.Draw(image)
    draw.rectangle((90, 90, 1710, 2410), outline="#102a43", width=8)
    draw.text((220, 250), "OLD TOM DISTILLERY", fill="#102a43", font=font(72, bold=True))
    draw.text((220, 470), "Kentucky Straight Bourbon Whiskey", fill="#121826", font=font(52))
    draw.text((220, 620), abv, fill="#121826", font=font(52))
    draw.text((220, 710), volume, fill="#121826", font=font(52))
    draw.text((220, 800), "Product of United States", fill="#121826", font=font(42))
    warning_heading, warning_body = warning.split(":", maxsplit=1)
    y = 1780
    draw.text((220, y), f"{warning_heading}:", fill="#121826", font=font(35, bold=True))
    draw_wrapped(draw, warning_body.strip(), (220, y + 60), width=86, text_font=font(35), leading=48)
    if rotate:
        image = image.rotate(4, expand=True, fillcolor="white")
    image.save(OUTPUT / name)


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    label("01-perfect-match.png")
    label("02-wrong-abv.png", abv="40% Alc./Vol. (80 Proof)")
    label("03-wrong-volume.png", volume="1000 mL")
    label("04-warning-title-case.png", warning=GOVERNMENT_WARNING.replace("GOVERNMENT WARNING", "Government Warning"))
    label("05-rotated.png", rotate=True)
    print(f"Generated {len(list(OUTPUT.glob('*.png')))} labels in {OUTPUT}")


if __name__ == "__main__":
    main()
