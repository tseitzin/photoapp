import os
from pathlib import Path

from app.scanner.discovery import DiscoveredFile, DiscoveryError, walk_root


def _touch(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _found_paths(root: Path) -> set[str]:
    return {item.path for item in walk_root(root) if isinstance(item, DiscoveredFile)}


def test_finds_supported_images_recursively(tmp_path: Path) -> None:
    a = _touch(tmp_path / "a.jpg")
    b = _touch(tmp_path / "2024/iceland/b.PNG")
    c = _touch(tmp_path / "2024/deep/nested/dir/c.heic")

    assert _found_paths(tmp_path) == {str(a), str(b), str(c)}


def test_ignores_unsupported_extensions(tmp_path: Path) -> None:
    _touch(tmp_path / "movie.mp4")
    _touch(tmp_path / "notes.txt")
    _touch(tmp_path / "raw.cr3")
    _touch(tmp_path / "no_extension")
    keeper = _touch(tmp_path / "keeper.webp")

    assert _found_paths(tmp_path) == {str(keeper)}


def test_reports_size_and_mtime(tmp_path: Path) -> None:
    photo = _touch(tmp_path / "p.jpg", b"12345")

    (item,) = list(walk_root(tmp_path))

    assert isinstance(item, DiscoveredFile)
    assert item.size_bytes == 5
    assert item.mtime_ns == photo.stat().st_mtime_ns


def test_skips_hidden_files_and_directories(tmp_path: Path) -> None:
    _touch(tmp_path / ".hidden.jpg")
    _touch(tmp_path / ".cache/photo.jpg")
    visible = _touch(tmp_path / "visible.jpg")

    assert _found_paths(tmp_path) == {str(visible)}


def test_does_not_follow_symlinked_directories_or_files(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    _touch(outside / "secret.jpg")
    root = tmp_path / "root"
    root.mkdir()
    _touch(root / "real.jpg")
    os.symlink(outside, root / "link_dir")
    os.symlink(outside / "secret.jpg", root / "link.jpg")

    assert _found_paths(root) == {str(root / "real.jpg")}


def test_survives_a_symlink_cycle(tmp_path: Path) -> None:
    inner = tmp_path / "inner"
    inner.mkdir()
    os.symlink(tmp_path, inner / "loop")
    photo = _touch(tmp_path / "p.jpg")

    assert _found_paths(tmp_path) == {str(photo)}


def test_unreadable_directory_yields_error_and_walk_continues(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    _touch(locked / "unreachable.jpg")
    photo = _touch(tmp_path / "reachable.jpg")
    locked.chmod(0o000)
    try:
        items = list(walk_root(tmp_path))
    finally:
        locked.chmod(0o755)

    errors = [i for i in items if isinstance(i, DiscoveryError)]
    files = [i for i in items if isinstance(i, DiscoveredFile)]
    assert [f.path for f in files] == [str(photo)]
    assert len(errors) == 1
    assert errors[0].path == str(locked)


def test_walk_is_a_generator_not_a_list(tmp_path: Path) -> None:
    _touch(tmp_path / "p.jpg")

    walker = walk_root(tmp_path)

    assert next(walker) is not None
