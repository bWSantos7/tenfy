from cloudinary_storage.storage import MediaCloudinaryStorage


class OptimizedCloudinaryStorage(MediaCloudinaryStorage):
    """
    Extends MediaCloudinaryStorage to inject f_auto,q_auto into every served URL.

    This tells Cloudinary's CDN to:
    - f_auto: serve WebP/AVIF to browsers that support it, JPEG otherwise
    - q_auto: choose the optimal quality level automatically (typically 60-80%)

    Result: up to 70% smaller images with no visible quality loss.
    No changes needed at upload time — transformation is applied on CDN delivery.
    """

    def url(self, name: str) -> str:
        raw_url = super().url(name)
        marker = '/image/upload/'
        if marker in raw_url and 'f_auto' not in raw_url:
            raw_url = raw_url.replace(marker, f'{marker}f_auto,q_auto/')
        return raw_url
