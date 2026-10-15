"""Shared query/catalog crop policy, independent of image libraries and HTTP."""

from .nail_contracts import (
    NailLocalization,
    NailProcessingError,
    ProcessedPhoto,
    RegionCrop,
    RgbImage,
)
from .nail_ports import NailImageStorePort, NailLocalizationPort


class NailImageProcessor:
    def __init__(
        self,
        images: NailImageStorePort,
        localization: NailLocalizationPort,
        decode_profile,
        localization_profile,
        max_regions,
    ):
        if type(max_regions) is not int or max_regions <= 0:
            raise NailProcessingError("RESOURCE_LIMIT")
        self.images = images
        self.localization = localization
        self.decode_profile = decode_profile
        self.localization_profile = localization_profile
        self.max_regions = max_regions

    def process(self, photo):
        image = self.images.read_rgb(photo, self.decode_profile)
        result = self.localization.localize(image, self.localization_profile)
        if not isinstance(result, NailLocalization):
            raise NailProcessingError("INVALID_OUTPUT")
        if len(result.regions) > self.max_regions:
            raise NailProcessingError("RESOURCE_LIMIT")
        crops = []
        for region in result.regions:
            mask = region.mask
            if (mask.width, mask.height) != (image.width, image.height):
                raise NailProcessingError("INVALID_OUTPUT")
            x0, y0, x1, y1 = image.width, image.height, 0, 0
            for index, pixel in enumerate(mask.pixels):
                if pixel:
                    y, x = divmod(index, image.width)
                    x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x + 1), max(y1, y + 1)
            pixels = bytearray()
            for y in range(y0, y1):
                for x in range(x0, x1):
                    i = y * image.width + x
                    pixels.extend(
                        image.pixels[3 * i : 3 * i + 3] if mask.pixels[i] else b"\xff\xff\xff"
                    )
            crops.append(
                RegionCrop(
                    region.ordinal,
                    region.detector_box_xyxy,
                    (x0, y0, x1, y1),
                    mask,
                    RgbImage(x1 - x0, y1 - y0, bytes(pixels)),
                )
            )
        return ProcessedPhoto(photo.photo_ordinal, photo.input_sha256, result.status, tuple(crops))
