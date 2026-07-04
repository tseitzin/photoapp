from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.dedupe.grouping import PhotoInfo
from app.dedupe.similarity import (
    band_values,
    derive_similar_groups,
    hamming,
    to_unsigned,
)


def _info(photo_id: int, sha: str, phash: int, size: int = 1000, wh: int = 100) -> PhotoInfo:
    return PhotoInfo(id=photo_id, sha256=sha, phash=phash, size_bytes=size, width=wh, height=wh)


def _flip_bits(value: int, *bits: int) -> int:
    for bit in bits:
        value ^= 1 << bit
    return value


BASE = 0x1234_5678_9ABC_DEF0


class TestBandingProperties:
    def test_hashes_within_distance_7_share_at_least_one_band(self) -> None:
        # Flip 7 bits spread across 7 different bands — band 3 stays untouched.
        other = _flip_bits(BASE, 0, 9, 18, 35, 44, 53, 62)

        assert hamming(BASE, other) == 7
        shared = [
            a == b for a, b in zip(band_values(BASE), band_values(to_unsigned(other)), strict=True)
        ]
        assert any(shared)

    def test_negative_stored_hash_round_trips_bands(self) -> None:
        # Top bit set -> stored as negative BIGINT; band extraction must agree.
        unsigned = 0xF000_0000_0000_00AA
        signed = unsigned - (1 << 64)

        assert to_unsigned(signed) == unsigned
        assert band_values(to_unsigned(signed))[0] == 0xAA
        assert band_values(to_unsigned(signed))[7] == 0xF0


class TestDeriveSimilarGroups:
    def test_close_hashes_group_and_score_by_distance_to_keeper(self) -> None:
        near = _flip_bits(BASE, 3, 17)  # distance 2 from BASE
        groups = derive_similar_groups(
            [
                _info(1, "sha-a", BASE, size=2000, wh=200),  # keeper (higher res)
                _info(2, "sha-b", near),
                _info(3, "sha-c", _flip_bits(BASE, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)),
            ],
            threshold=6,
        )

        assert len(groups) == 1
        group = groups[0]
        assert group.kind == "similar"
        assert group.keeper_photo_id == 1
        assert set(group.members) == {1, 2}
        assert group.members[1] == 100
        assert group.members[2] == round((64 - 2) / 64 * 100)

    def test_transitive_chain_merges_into_one_component(self) -> None:
        a = BASE
        b = _flip_bits(a, 0, 1, 2, 3)  # d(a,b)=4
        c = _flip_bits(b, 10, 11, 12, 13)  # d(b,c)=4, d(a,c)=8 > threshold
        groups = derive_similar_groups(
            [_info(1, "s1", a), _info(2, "s2", b), _info(3, "s3", c)], threshold=6
        )

        assert len(groups) == 1
        assert set(groups[0].members) == {1, 2, 3}

    def test_purely_exact_copies_do_not_form_a_similar_group(self) -> None:
        groups = derive_similar_groups(
            [_info(1, "same-sha", BASE), _info(2, "same-sha", BASE)], threshold=6
        )

        assert groups == []

    def test_distant_hashes_do_not_group(self) -> None:
        far = _flip_bits(BASE, *range(0, 16))
        groups = derive_similar_groups([_info(1, "s1", BASE), _info(2, "s2", far)], threshold=6)

        assert groups == []

    def test_threshold_is_respected(self) -> None:
        at_seven = _flip_bits(BASE, 0, 9, 18, 27, 36, 45, 54)
        photos = [_info(1, "s1", BASE), _info(2, "s2", at_seven)]

        assert derive_similar_groups(photos, threshold=6) == []
        assert len(derive_similar_groups(photos, threshold=7)) == 1


def _textured(path: Path, size: tuple[int, int], quality: int = 92) -> Path:
    image = Image.new("RGB", (800, 600))
    draw = ImageDraw.Draw(image)
    for x in range(0, 800, 50):
        draw.rectangle([x, 0, x + 25, 600], fill=(190, 90, 40))
    for y in range(0, 600, 60):
        draw.ellipse([y, y // 2, y + 90, y // 2 + 70], fill=(40, 80, 190))
    image.resize(size).save(path, quality=quality)
    return path


def _index(client: TestClient, root: Path) -> None:
    assert client.post("/api/scan-roots", json={"path": str(root)}).status_code == 201
    assert client.post("/api/scans", json={}).status_code == 202


def test_scan_groups_resized_copy_as_visually_similar(client: TestClient, tmp_path: Path) -> None:
    _textured(tmp_path / "original.jpg", (800, 600))
    _textured(tmp_path / "resized.jpg", (400, 300), quality=70)
    Image.new("RGB", (500, 500), "black").save(tmp_path / "unrelated.jpg")
    _index(client, tmp_path)

    similar = client.get("/api/duplicates/groups", params={"kind": "similar"}).json()

    assert similar["total"] == 1
    group = similar["items"][0]
    members = {m["photo"]["filename"]: m for m in group["members"]}
    assert set(members) == {"original.jpg", "resized.jpg"}
    assert members["original.jpg"]["similarity_pct"] == 100  # keeper
    assert 85 <= members["resized.jpg"]["similarity_pct"] <= 100
    keeper_member = next(
        m for m in group["members"] if m["photo"]["id"] == group["keeper_photo_id"]
    )
    assert keeper_member["photo"]["filename"] == "original.jpg"
    # exact groups untouched
    assert client.get("/api/duplicates/groups", params={"kind": "exact"}).json()["total"] == 0


def test_exact_copies_plus_resized_yield_both_group_kinds(
    client: TestClient, tmp_path: Path
) -> None:
    original = _textured(tmp_path / "original.jpg", (800, 600))
    (tmp_path / "copy.jpg").write_bytes(original.read_bytes())
    _textured(tmp_path / "resized.jpg", (400, 300), quality=70)
    _index(client, tmp_path)

    exact = client.get("/api/duplicates/groups", params={"kind": "exact"}).json()
    similar = client.get("/api/duplicates/groups", params={"kind": "similar"}).json()

    assert exact["total"] == 1
    assert len(exact["items"][0]["members"]) == 2
    assert similar["total"] == 1
    assert len(similar["items"][0]["members"]) == 3


def test_similar_endpoint_finds_resized_sibling_via_sql_bands(
    client: TestClient, tmp_path: Path
) -> None:
    _textured(tmp_path / "original.jpg", (800, 600))
    _textured(tmp_path / "resized.jpg", (400, 300), quality=70)
    Image.new("RGB", (500, 500), "white").save(tmp_path / "unrelated.jpg")
    _index(client, tmp_path)
    photos = {p["filename"]: p["id"] for p in client.get("/api/photos").json()["items"]}

    matches = client.get(f"/api/photos/{photos['original.jpg']}/similar").json()

    assert [m["photo"]["filename"] for m in matches] == ["resized.jpg"]
    assert matches[0]["distance"] <= 6
    assert matches[0]["similarity_pct"] >= 90
