"""Create deterministic CTP500 geometry and tone calibration images."""

from PIL import Image, ImageDraw


WIDTH = 384
HEIGHT = 256


def geometry_test():
    image = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(image)
    # A square and circle reveal vertical aspect errors immediately.
    draw.rectangle((32, 32, 159, 159), outline=0, width=6)
    draw.ellipse((208, 32, 335, 159), outline=0, width=6)
    # Thick vertical and horizontal bars show lost columns or rows.
    draw.rectangle((24, 184, 359, 191), fill=0)
    draw.rectangle((24, 200, 31, 239), fill=0)
    draw.rectangle((352, 200, 359, 239), fill=0)
    image.save("ctp500-geometry-test.png")


def tone_test():
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    pixels = image.load()
    # Smooth grayscale ramp: the dither should become denser from left to right.
    for y in range(16, 96):
        for x in range(WIDTH):
            pixels[x, y] = x * 255 // (WIDTH - 1)
    # Eight controlled gray patches, from black to white.
    for index in range(8):
        value = index * 255 // 7
        left = index * 48
        for y in range(112, 176):
            for x in range(left, left + 48):
                pixels[x, y] = value
    draw = ImageDraw.Draw(image)
    # Fine-to-coarse checkerboards test retained detail.
    for box, cell in [((16, 192, 79, 255), 1), ((112, 192, 175, 255), 2),
                      ((208, 192, 271, 255), 4), ((304, 192, 367, 255), 8)]:
        left, top, right, bottom = box
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                if ((x - left) // cell + (y - top) // cell) % 2 == 0:
                    pixels[x, y] = 0
    image.save("ctp500-tone-test.png")


if __name__ == "__main__":
    geometry_test()
    tone_test()
