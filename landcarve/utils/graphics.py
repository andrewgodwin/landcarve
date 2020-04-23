import PIL.Image
import PIL.ImageDraw


def bitmap_array_to_image(array):
    """
    Converts an array containing True/False values into a 1-bit image
    """
    mask_image = PIL.Image.new("1", (array.shape[1], array.shape[0]))
    for y in range(array.shape[0]):
        for x in range(array.shape[1]):
            mask_image.putpixel((x, y), int(array[y, x]))
    return mask_image


def draw_border(image, colour=(100, 100, 100, 255)):
    """
    Draws a one-pixel-thin border around an image. Operates on the image in-place.
    """
    d = PIL.ImageDraw.Draw(image)
    mx = image.size[0] - 1
    my = image.size[1] - 1
    d.line([0, 0, mx, 0], colour)
    d.line([0, my, mx, my], colour)
    d.line([0, 0, 0, my], colour)
    d.line([mx, 0, mx, my], colour)


def draw_crosshatch(image, colour=(10, 10, 10, 255), step=20, width=1):
    d = PIL.ImageDraw.Draw(image)
    mx = image.size[0] - 1
    my = image.size[1] - 1
    max_size = mx + my
    for x in range(0, max_size, step):
        d.line([x, 0, x - max_size, max_size], colour, width=width)
    for x in range(0 - my, mx, step):
        d.line([x, 0, x + max_size, max_size], colour, width=width)


def draw_contours(image, contours, colour=(200, 10, 200, 255), step=20, width=2):
    d = PIL.ImageDraw.Draw(image)
    for contour in contours:
        d.line(contour, colour, width=width)
