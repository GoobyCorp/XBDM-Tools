#!/usr/bin/env python3

from io import BytesIO
from struct import pack, unpack

from PIL import Image

IMAGE_WIDTH_PIXELS = 1280  # 640  # 320  # 160  # 80  # 40 # 20 # 10 # 5
IMAGE_HEIGHT_PIXELS = 720  # 360  # 180  # 90   # 45

IMAGE_WIDTH_BYTES = IMAGE_WIDTH_PIXELS * 4
IMAGE_HEIGHT_BYTES = IMAGE_HEIGHT_PIXELS * 4

IMAGE_SIZE = IMAGE_WIDTH_PIXELS * IMAGE_HEIGHT_PIXELS * 4

TILE_SIZE_BYTES = 4096  # 8192
TILE_TOTAL = 920  # 460 - len(data) / TILE_SIZE_BYTES
TILE_WIDTH_PIXELS = 32
TILE_HEIGHT_PIXELS = 32

TILE_WIDTH_BYTES = TILE_WIDTH_PIXELS * 4    # RGBA
TILE_HEIGHT_BYTES = TILE_HEIGHT_PIXELS * 4  # RGBA

TILES_X = int(IMAGE_WIDTH_PIXELS / TILE_WIDTH_PIXELS)
TILES_Y = int(IMAGE_HEIGHT_PIXELS / TILE_HEIGHT_PIXELS)

if __name__ == "__main__":
    with open("screenshot.bin", "rb") as f:
        data = f.read()

    with BytesIO(data) as bio_i:
        with BytesIO() as bio_o:
            for x in range(0, len(data), 4):
                (b, g, r, a) = unpack(">4B", bio_i.read(4))
                bio_o.write(pack("<4B", r, g, b, a))
            buff_o = bio_o.getvalue()  # output converted to RGBA

    tiles = []
    with BytesIO(buff_o) as bio_i:
        for x in range(0, len(data), TILE_SIZE_BYTES):  # read in chunks (tiles)
            tile_data = bio_i.read(TILE_SIZE_BYTES)
            tile = Image.frombytes("RGBA", (TILE_WIDTH_PIXELS, TILE_HEIGHT_PIXELS), tile_data)
            #tile = tile.resize((TILE_WIDTH_PIXELS + 16, TILE_HEIGHT_PIXELS + 8))
            tiles.append(tile)

    with Image.new("RGBA", (1280, 720)) as img:
        # box variables
        left = 0
        upper = 0
        right = TILE_WIDTH_PIXELS
        lower = TILE_HEIGHT_PIXELS
        # current tile number
        tile_num = 0
        # loop over Y axis
        for y in range(TILES_Y):
            # loop over X axis
            for x in range(TILES_X):
                img.paste(tiles[tile_num], (left, upper, right, lower))
                # move left and right boundaries to the right
                left += TILE_WIDTH_PIXELS
                right += TILE_WIDTH_PIXELS
                # increment tile number
                tile_num += 1
            # move back to left and move down
            left = 0
            upper += TILE_HEIGHT_PIXELS
            right = TILE_WIDTH_PIXELS
            lower += TILE_HEIGHT_PIXELS

        with open("save.png", "wb") as f:
            img.save(f, "png")
        with open("save.bin", "wb") as f:
            f.write(img.tobytes("raw"))
        img.show()