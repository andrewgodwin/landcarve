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
