import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.scanner.processing import process_file
from app.scanner.thumbnails import ensure_thumbnail, thumbnail_path
from tests.images import make_image


def test_concurrent_generation_of_same_sha_all_succeed(tmp_path: Path) -> None:
    """Two panes of an exact-duplicate compare request the same sha256 preview
    at once; concurrent generation must not corrupt the file or fail."""
    source = make_image(tmp_path / "shared.jpg", size=(1200, 900))
    sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    cache = tmp_path / "cache"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: ensure_thumbnail(str(source), sha256, cache, 512),
                range(24),
            )
        )

    assert all(path is not None for path in results)
    final = thumbnail_path(cache, sha256, 512)
    assert final.is_file()
    with Image.open(final) as image:  # must be a valid, fully-written webp
        assert image.format == "WEBP"
        assert max(image.size) == 512
    # No temp files left behind.
    assert not list(cache.rglob("*.tmp"))


def test_processing_computes_phash_and_writes_sha_keyed_thumbnail(tmp_path: Path) -> None:
    photo = make_image(tmp_path / "p.jpg", size=(800, 600))
    cache = tmp_path / "cache"

    result = process_file(str(photo), thumb_dir=str(cache), thumb_size=256)

    assert result.phash is not None
    assert result.sha256 is not None
    thumb = thumbnail_path(cache, result.sha256, 256)
    assert thumb.is_file()
    with Image.open(thumb) as image:
        assert image.format == "WEBP"
        assert max(image.size) == 256


def test_identical_content_shares_one_thumbnail(tmp_path: Path) -> None:
    original = make_image(tmp_path / "a.jpg", color="navy")
    copy = tmp_path / "b.jpg"
    copy.write_bytes(original.read_bytes())
    cache = tmp_path / "cache"

    first = process_file(str(original), thumb_dir=str(cache))
    second = process_file(str(copy), thumb_dir=str(cache))

    assert first.sha256 == second.sha256
    assert first.phash == second.phash
    webps = list(cache.rglob("*.webp"))
    assert len(webps) == 1


def test_similar_images_have_close_phash_and_different_have_distant(
    tmp_path: Path,
) -> None:
    from PIL import ImageDraw

    base = Image.new("RGB", (400, 300))
    draw = ImageDraw.Draw(base)
    for x in range(0, 400, 40):
        draw.rectangle([x, 0, x + 20, 300], fill=(200, 80, 40))
    base.save(tmp_path / "orig.jpg", quality=95)
    base.resize((200, 150)).save(tmp_path / "resized.jpg", quality=70)
    other_image = Image.new("RGB", (400, 300))
    other_draw = ImageDraw.Draw(other_image)
    for y in range(0, 300, 30):
        other_draw.ellipse([y, y // 2, y + 120, y // 2 + 80], fill=(40, 90, 200 - y // 3))
    other_image.save(tmp_path / "other.jpg")

    orig = process_file(str(tmp_path / "orig.jpg"))
    resized = process_file(str(tmp_path / "resized.jpg"))
    other = process_file(str(tmp_path / "other.jpg"))

    assert orig.phash is not None and resized.phash is not None and other.phash is not None
    close = bin(orig.phash ^ resized.phash).count("1")
    far = bin(orig.phash ^ other.phash).count("1")
    assert close <= 6, f"resized copy should hash close to original (distance {close})"
    assert far > 10, f"unrelated image should hash far away (distance {far})"


def test_corrupt_file_yields_no_phash_or_thumbnail(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"garbage")
    cache = tmp_path / "cache"

    result = process_file(str(bad), thumb_dir=str(cache))

    assert result.phash is None
    assert result.error is not None
    assert not list(cache.rglob("*.webp")) if cache.exists() else True


def _scan(client: TestClient, root: Path) -> int:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202
    return client.get("/api/photos").json()["items"][0]["id"]


def test_thumbnail_endpoint_serves_webp_after_scan(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "p.jpg", size=(600, 400))
    photo_id = _scan(client, tmp_path)

    response = client.get(f"/api/photos/{photo_id}/thumbnail")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert "immutable" in response.headers["cache-control"]
    assert len(response.content) > 100


def test_thumbnail_is_regenerated_on_demand_after_cache_wipe(
    client: TestClient, tmp_path: Path
) -> None:
    make_image(tmp_path / "p.jpg")
    photo_id = _scan(client, tmp_path)
    cache_dir = get_settings().thumbnail_cache_dir
    shutil.rmtree(cache_dir, ignore_errors=True)

    response = client.get(f"/api/photos/{photo_id}/thumbnail")

    assert response.status_code == 200
    assert list(Path(cache_dir).rglob("*.webp"))


def test_preview_endpoint_serves_larger_rendition(client: TestClient, tmp_path: Path) -> None:
    make_image(tmp_path / "p.jpg", size=(3000, 2000))
    photo_id = _scan(client, tmp_path)

    thumb = client.get(f"/api/photos/{photo_id}/thumbnail")
    preview = client.get(f"/api/photos/{photo_id}/preview")

    assert preview.status_code == 200
    assert len(preview.content) > len(thumb.content)


def test_thumbnail_404_when_original_is_gone_and_cache_empty(
    client: TestClient, tmp_path: Path
) -> None:
    photo_path = make_image(tmp_path / "p.jpg")
    photo_id = _scan(client, tmp_path)
    shutil.rmtree(get_settings().thumbnail_cache_dir, ignore_errors=True)
    photo_path.unlink()

    assert client.get(f"/api/photos/{photo_id}/thumbnail").status_code == 404


def test_thumbnail_404_for_unknown_photo(client: TestClient) -> None:
    assert client.get("/api/photos/999999/thumbnail").status_code == 404
