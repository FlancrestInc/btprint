"""Create a thick-bar CTP500 test image for vertical-edge calibration."""

from PIL import Image, ImageDraw


WIDTH = 384
HEIGHT = 256
BAR_WIDTH = 8
INSETS = (4, 32)


def main():
    image = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(image)
    for inset in INSETS:
        draw.rectangle((inset, 4, inset + BAR_WIDTH - 1, HEIGHT - 5), fill=0)
        right = WIDTH - inset - BAR_WIDTH
        draw.rectangle((right, 4, right + BAR_WIDTH - 1, HEIGHT - 5), fill=0)
    draw.rectangle((4, 4, WIDTH - 5, 11), fill=0)
    draw.rectangle((4, HEIGHT - 12, WIDTH - 5, HEIGHT - 5), fill=0)
    image.save("ctp500-margin-bars.png")


if __name__ == "__main__":
    main()
