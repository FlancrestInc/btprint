"""Create a concentric-rectangle image for CTP500 margin testing."""

from PIL import Image, ImageDraw


WIDTH = 384
HEIGHT = 256
INSETS = (0, 2, 4, 8, 16, 32)


def main():
    image = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(image)
    for inset in INSETS:
        draw.rectangle(
            (inset, inset, WIDTH - 1 - inset, HEIGHT - 1 - inset),
            outline=0,
            width=1,
        )
    image.save("ctp500-margin-test.png")


if __name__ == "__main__":
    main()
