"""Unit tests for app/media/image_storage.py -- placeholder honestly
returns None (never a fake URL), factory switches on Cloudinary env
vars, and (mocked, no real network calls) the real provider signs
requests correctly and wraps failures as ImageStorageProviderError."""
import pytest

from app.config import get_settings
from app.media.image_storage import (
    CloudinaryImageStorageProvider,
    ImageStorageProviderError,
    PlaceholderImageStorageProvider,
    get_image_storage_provider,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_placeholder_provider_returns_none_not_a_fake_url():
    provider = PlaceholderImageStorageProvider()
    result = await provider.upload(b"fake-image-bytes", "image/png", folder="tradeedge")
    assert result is None


def test_factory_returns_placeholder_when_no_credentials(monkeypatch):
    monkeypatch.delenv("CLOUDINARY_CLOUD_NAME", raising=False)
    monkeypatch.delenv("CLOUDINARY_API_KEY", raising=False)
    monkeypatch.delenv("CLOUDINARY_API_SECRET", raising=False)
    provider = get_image_storage_provider()
    assert isinstance(provider, PlaceholderImageStorageProvider)


def test_factory_requires_all_three_credentials(monkeypatch):
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "demo")
    monkeypatch.setenv("CLOUDINARY_API_KEY", "fake-key-not-real")
    monkeypatch.delenv("CLOUDINARY_API_SECRET", raising=False)
    provider = get_image_storage_provider()
    assert isinstance(provider, PlaceholderImageStorageProvider)


def test_factory_returns_cloudinary_when_all_three_set(monkeypatch):
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "demo")
    monkeypatch.setenv("CLOUDINARY_API_KEY", "fake-key-not-real")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "fake-secret-not-real")
    provider = get_image_storage_provider()
    assert isinstance(provider, CloudinaryImageStorageProvider)


def test_signature_matches_cloudinarys_documented_scheme():
    # Worked example from Cloudinary's own signature docs style: sign
    # every param except file/api_key/resource_type, sorted, joined as
    # key=value&key2=value2, api_secret appended, sha1 hex digest.
    provider = CloudinaryImageStorageProvider(cloud_name="demo", api_key="key", api_secret="abcd")
    import hashlib

    params = {"timestamp": "1690000000", "folder": "tradeedge"}
    expected = hashlib.sha1(f"folder=tradeedge&timestamp=1690000000abcd".encode()).hexdigest()
    assert provider._sign(params) == expected


@pytest.mark.asyncio
async def test_cloudinary_provider_wraps_network_failure(monkeypatch):
    provider = CloudinaryImageStorageProvider(cloud_name="demo", api_key="key", api_secret="secret")

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise RuntimeError("simulated network failure")

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    with pytest.raises(ImageStorageProviderError, match="Cloudinary upload failed"):
        await provider.upload(b"fake-bytes", "image/png", folder="tradeedge")


@pytest.mark.asyncio
async def test_cloudinary_provider_wraps_missing_secure_url(monkeypatch):
    provider = CloudinaryImageStorageProvider(cloud_name="demo", api_key="key", api_secret="secret")

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"unexpected": "shape"}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return _FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    with pytest.raises(ImageStorageProviderError, match="no secure_url"):
        await provider.upload(b"fake-bytes", "image/png", folder="tradeedge")


@pytest.mark.asyncio
async def test_cloudinary_provider_returns_secure_url_on_success(monkeypatch):
    provider = CloudinaryImageStorageProvider(cloud_name="demo", api_key="key", api_secret="secret")

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"secure_url": "https://res.cloudinary.com/demo/image/upload/v1/tradeedge/abc123.png"}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return _FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    url = await provider.upload(b"fake-bytes", "image/png", folder="tradeedge")
    assert url == "https://res.cloudinary.com/demo/image/upload/v1/tradeedge/abc123.png"
