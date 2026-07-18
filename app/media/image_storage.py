"""Pluggable screenshot storage provider (Sprint 20 Phase 3).

Every chart screenshot the trader uploads gets read once by the vision
provider (``app/chart/vision_provider.py``) and, until now, thrown
away immediately after -- nothing was ever saved. That's fine for a
one-off read, but the trader explicitly wants every trade's screenshot
kept permanently: for the trade detail view, for the personal
playbook's example screenshots, and as the source material behind
every structured field the similarity/ML engines learn from.

Render's own filesystem is wiped on every redeploy/restart, so saving
files there would silently lose every screenshot the next time the
service restarts -- this has to be a real external store. Same
pluggable-provider shape as ``vision_provider.py`` and
``calendar_provider.py`` so the rest of the app depends on one small
interface, never a specific vendor's SDK:

* ``PlaceholderImageStorageProvider`` -- always active when no
  Cloudinary credentials are configured. Returns ``None`` rather than
  a fake URL (there is nothing honest to fake here -- a made-up URL
  would just 404), so callers must handle "screenshot wasn't saved"
  as a real, expected case, not an error.
* ``CloudinaryImageStorageProvider`` -- real, permanent storage via
  Cloudinary's free tier, used automatically the moment
  ``CLOUDINARY_CLOUD_NAME`` / ``CLOUDINARY_API_KEY`` /
  ``CLOUDINARY_API_SECRET`` are set (e.g. as Render environment
  variables). No other code changes required to go from placeholder
  to real, same as the vision provider.

Adding another backend (S3, Cloudflare R2, ...) later means writing
one more class here and one line in ``get_image_storage_provider`` --
nothing else in the app needs to know.
"""
from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod

from app.config import get_settings


class ImageStorageProvider(ABC):
    """One method: image bytes in, a permanent URL (or ``None``) out."""

    name: str = "base"

    @abstractmethod
    async def upload(self, image_bytes: bytes, mime_type: str, *, folder: str) -> str | None:
        """Returns a permanent, publicly-fetchable URL for the
        uploaded image, or ``None`` if this provider can't actually
        store anything (the placeholder). Raises
        ``ImageStorageProviderError`` (never a raw SDK/HTTP exception)
        on a real upload failure."""
        raise NotImplementedError


class ImageStorageProviderError(Exception):
    """Raised by a real ``ImageStorageProvider`` on failure (bad
    credentials, network error, provider-side rejection, ...). Callers
    catch this and treat it as "couldn't save the screenshot this
    time" -- never fatal to the trade save itself, since the
    structured vision read is the important part and already
    succeeded by the time an upload is attempted."""


class PlaceholderImageStorageProvider(ImageStorageProvider):
    """No credentials configured -- honestly returns ``None`` instead
    of a fake URL. Every caller must already treat "no screenshot URL"
    as a normal, handled case (a trade logged before Cloudinary was
    configured, or logged manually with no screenshot at all)."""

    name = "placeholder"

    async def upload(self, image_bytes: bytes, mime_type: str, *, folder: str) -> str | None:
        return None


class CloudinaryImageStorageProvider(ImageStorageProvider):
    """Real, permanent screenshot storage via Cloudinary's signed
    upload API (https://cloudinary.com/documentation/upload_images).
    Uses ``httpx`` directly (already a project dependency, same as
    ``FinnhubCalendarProvider``/``JblankedCalendarProvider``) rather
    than adding the ``cloudinary`` SDK as a new dependency -- a signed
    upload is a single multipart POST."""

    name = "cloudinary"

    def __init__(self, cloud_name: str, api_key: str, api_secret: str) -> None:
        self._cloud_name = cloud_name
        self._api_key = api_key
        self._api_secret = api_secret

    def _sign(self, params: dict[str, str]) -> str:
        """Cloudinary's signing scheme: every param EXCEPT ``file``,
        ``api_key``, and ``resource_type``, sorted alphabetically as
        ``key=value&key2=value2``, with the API secret appended, then
        SHA-1 hex-digested. See https://cloudinary.com/documentation/
        signatures -- signature verifies the upload wasn't tampered
        with in transit, not authentication itself (that's api_key)."""
        to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params)) + self._api_secret
        return hashlib.sha1(to_sign.encode("utf-8")).hexdigest()  # noqa: S324 - Cloudinary's own required scheme, not a security choice of ours

    async def upload(self, image_bytes: bytes, mime_type: str, *, folder: str) -> str | None:
        import httpx

        timestamp = str(int(time.time()))
        signed_params = {"timestamp": timestamp, "folder": folder}
        signature = self._sign(signed_params)

        url = f"https://api.cloudinary.com/v1_1/{self._cloud_name}/image/upload"
        data = {**signed_params, "api_key": self._api_key, "signature": signature}
        files = {"file": (f"screenshot.{mime_type.split('/')[-1] or 'png'}", image_bytes, mime_type)}

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, data=data, files=files)
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPStatusError as exc:
            body_snippet = exc.response.text[:300] if exc.response is not None else ""
            raise ImageStorageProviderError(
                f"Cloudinary upload failed: {exc} -- response body: {body_snippet!r}"
            ) from exc
        except Exception as exc:  # network error, timeout, bad JSON, etc.
            raise ImageStorageProviderError(f"Cloudinary upload failed: {exc}") from exc

        secure_url = body.get("secure_url") or body.get("url")
        if not secure_url:
            raise ImageStorageProviderError(
                f"Cloudinary response had no secure_url/url field: {body!r}"
            )
        return secure_url


def get_image_storage_provider() -> ImageStorageProvider:
    """Factory: real provider if Cloudinary credentials are configured,
    placeholder otherwise. Single switch point, same convention as
    ``get_vision_provider``/``get_calendar_provider``."""
    settings = get_settings()
    cloud_name = getattr(settings, "cloudinary_cloud_name", None)
    api_key = getattr(settings, "cloudinary_api_key", None)
    api_secret = getattr(settings, "cloudinary_api_secret", None)
    if cloud_name and api_key and api_secret:
        return CloudinaryImageStorageProvider(cloud_name, api_key, api_secret)
    return PlaceholderImageStorageProvider()
