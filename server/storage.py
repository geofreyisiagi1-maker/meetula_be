from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage
from storages.backends.s3 import S3Storage


LEGACY_CLOUDINARY_PREFIX = "cloudinary-legacy://"


def _legacy_cloudinary_url(name):
    if not settings.CLOUDINARY_CLOUD_NAME:
        raise ImproperlyConfigured(
            "Set CLOUD_NAME to keep serving images previously stored in Cloudinary."
        )
    from cloudinary.utils import cloudinary_url

    public_id = name[len(LEGACY_CLOUDINARY_PREFIX) :]
    return cloudinary_url(public_id)[0]


class CloudflareR2Storage(S3Storage):
    def url(self, name, parameters=None, expire=None):
        if name.startswith(LEGACY_CLOUDINARY_PREFIX):
            return _legacy_cloudinary_url(name)

        if not settings.R2_PUBLIC_URL:
            raise ImproperlyConfigured("Set R2_PUBLIC_URL to serve images from R2.")
        return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{quote(name, safe='/')}"


class LocalImageStorage(FileSystemStorage):
    def url(self, name):
        if name.startswith(LEGACY_CLOUDINARY_PREFIX):
            return _legacy_cloudinary_url(name)
        return super().url(name)
