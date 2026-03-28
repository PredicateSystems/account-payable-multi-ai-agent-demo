"""Tests for sidecar bootstrap and management."""

from __future__ import annotations

import json
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from account_payable_demo.config import SidecarConfig
from account_payable_demo.sidecar import (
    LOCAL_BOOTSTRAP_SUPPORTED_OS,
    OS,
    Architecture,
    DownloadResult,
    Platform,
    Release,
    ReleaseAsset,
    _is_path_within_directory,
    _validate_archive_members,
    detect_architecture,
    detect_os,
    detect_platform,
    download_sidecar,
    extract_archive,
    fetch_release,
    find_asset_for_platform,
    find_binary_in_dir,
    get_manual_install_instructions,
    health_check,
    is_process_running,
    normalize_architecture,
    normalize_os,
    resolve_download_url,
    stop_sidecar,
)


class TestOS:
    """Tests for OS enum."""

    def test_darwin_value(self):
        assert OS.DARWIN.value == "darwin"

    def test_linux_value(self):
        assert OS.LINUX.value == "linux"

    def test_windows_value(self):
        assert OS.WINDOWS.value == "windows"


class TestArchitecture:
    """Tests for Architecture enum."""

    def test_x64_value(self):
        assert Architecture.X64.value == "x64"

    def test_arm64_value(self):
        assert Architecture.ARM64.value == "arm64"


class TestPlatform:
    """Tests for Platform dataclass."""

    def test_asset_suffix_darwin_arm64(self):
        plat = Platform(os=OS.DARWIN, arch=Architecture.ARM64)
        assert plat.asset_suffix == "darwin-arm64.tar.gz"

    def test_asset_suffix_linux_x64(self):
        plat = Platform(os=OS.LINUX, arch=Architecture.X64)
        assert plat.asset_suffix == "linux-x64.tar.gz"

    def test_asset_suffix_windows_x64(self):
        plat = Platform(os=OS.WINDOWS, arch=Architecture.X64)
        assert plat.asset_suffix == "windows-x64.zip"

    def test_asset_name_darwin_arm64(self):
        plat = Platform(os=OS.DARWIN, arch=Architecture.ARM64)
        assert plat.asset_name == "predicate-authorityd-darwin-arm64.tar.gz"

    def test_asset_name_linux_x64(self):
        plat = Platform(os=OS.LINUX, arch=Architecture.X64)
        assert plat.asset_name == "predicate-authorityd-linux-x64.tar.gz"

    def test_supports_local_bootstrap_darwin(self):
        plat = Platform(os=OS.DARWIN, arch=Architecture.ARM64)
        assert plat.supports_local_bootstrap is True

    def test_supports_local_bootstrap_linux(self):
        plat = Platform(os=OS.LINUX, arch=Architecture.X64)
        assert plat.supports_local_bootstrap is True

    def test_supports_local_bootstrap_windows(self):
        plat = Platform(os=OS.WINDOWS, arch=Architecture.X64)
        assert plat.supports_local_bootstrap is False


class TestLocalBootstrapSupportedOS:
    """Tests for LOCAL_BOOTSTRAP_SUPPORTED_OS constant."""

    def test_darwin_supported(self):
        assert OS.DARWIN in LOCAL_BOOTSTRAP_SUPPORTED_OS

    def test_linux_supported(self):
        assert OS.LINUX in LOCAL_BOOTSTRAP_SUPPORTED_OS

    def test_windows_not_supported(self):
        assert OS.WINDOWS not in LOCAL_BOOTSTRAP_SUPPORTED_OS


class TestDetectOS:
    """Tests for detect_os function."""

    def test_detect_darwin(self):
        with patch("platform.system", return_value="Darwin"):
            assert detect_os() == OS.DARWIN

    def test_detect_linux(self):
        with patch("platform.system", return_value="Linux"):
            assert detect_os() == OS.LINUX

    def test_detect_windows(self):
        with patch("platform.system", return_value="Windows"):
            assert detect_os() == OS.WINDOWS

    def test_detect_unsupported(self):
        with patch("platform.system", return_value="FreeBSD"):
            assert detect_os() is None


class TestDetectArchitecture:
    """Tests for detect_architecture function."""

    def test_detect_x86_64(self):
        with patch("platform.machine", return_value="x86_64"):
            assert detect_architecture() == Architecture.X64

    def test_detect_amd64(self):
        with patch("platform.machine", return_value="AMD64"):
            assert detect_architecture() == Architecture.X64

    def test_detect_arm64(self):
        with patch("platform.machine", return_value="arm64"):
            assert detect_architecture() == Architecture.ARM64

    def test_detect_aarch64(self):
        with patch("platform.machine", return_value="aarch64"):
            assert detect_architecture() == Architecture.ARM64

    def test_detect_unsupported(self):
        with patch("platform.machine", return_value="i386"):
            assert detect_architecture() is None


class TestDetectPlatform:
    """Tests for detect_platform function."""

    def test_detect_darwin_arm64(self):
        with patch("platform.system", return_value="Darwin"):
            with patch("platform.machine", return_value="arm64"):
                plat = detect_platform()
                assert plat is not None
                assert plat.os == OS.DARWIN
                assert plat.arch == Architecture.ARM64

    def test_detect_linux_x64(self):
        with patch("platform.system", return_value="Linux"):
            with patch("platform.machine", return_value="x86_64"):
                plat = detect_platform()
                assert plat is not None
                assert plat.os == OS.LINUX
                assert plat.arch == Architecture.X64

    def test_detect_unsupported_os(self):
        with patch("platform.system", return_value="FreeBSD"):
            with patch("platform.machine", return_value="x86_64"):
                assert detect_platform() is None

    def test_detect_unsupported_arch(self):
        with patch("platform.system", return_value="Linux"):
            with patch("platform.machine", return_value="i386"):
                assert detect_platform() is None


class TestNormalizeOS:
    """Tests for normalize_os function."""

    def test_normalize_darwin(self):
        assert normalize_os("darwin") == OS.DARWIN
        assert normalize_os("Darwin") == OS.DARWIN
        assert normalize_os("DARWIN") == OS.DARWIN

    def test_normalize_macos(self):
        assert normalize_os("macos") == OS.DARWIN
        assert normalize_os("mac") == OS.DARWIN

    def test_normalize_linux(self):
        assert normalize_os("linux") == OS.LINUX
        assert normalize_os("Linux") == OS.LINUX

    def test_normalize_windows(self):
        assert normalize_os("windows") == OS.WINDOWS
        assert normalize_os("win") == OS.WINDOWS
        assert normalize_os("win32") == OS.WINDOWS
        assert normalize_os("win64") == OS.WINDOWS

    def test_normalize_unknown(self):
        assert normalize_os("freebsd") is None
        assert normalize_os("") is None


class TestNormalizeArchitecture:
    """Tests for normalize_architecture function."""

    def test_normalize_x64(self):
        assert normalize_architecture("x86_64") == Architecture.X64
        assert normalize_architecture("amd64") == Architecture.X64
        assert normalize_architecture("x64") == Architecture.X64
        assert normalize_architecture("AMD64") == Architecture.X64

    def test_normalize_arm64(self):
        assert normalize_architecture("arm64") == Architecture.ARM64
        assert normalize_architecture("aarch64") == Architecture.ARM64
        assert normalize_architecture("ARM64") == Architecture.ARM64

    def test_normalize_unknown(self):
        assert normalize_architecture("i386") is None
        assert normalize_architecture("") is None


class TestFindAssetForPlatform:
    """Tests for find_asset_for_platform function."""

    @pytest.fixture
    def sample_release(self):
        return Release(
            tag_name="v0.7.2",
            assets=[
                ReleaseAsset(
                    name="predicate-authorityd-darwin-arm64.tar.gz",
                    download_url="https://example.com/darwin-arm64.tar.gz",
                    size=4000000,
                ),
                ReleaseAsset(
                    name="predicate-authorityd-darwin-arm64.tar.gz.sha256",
                    download_url="https://example.com/darwin-arm64.tar.gz.sha256",
                    size=64,
                ),
                ReleaseAsset(
                    name="predicate-authorityd-linux-x64.tar.gz",
                    download_url="https://example.com/linux-x64.tar.gz",
                    size=4500000,
                ),
                ReleaseAsset(
                    name="predicate-authorityd-windows-x64.zip",
                    download_url="https://example.com/windows-x64.zip",
                    size=4600000,
                ),
            ],
        )

    def test_find_darwin_arm64(self, sample_release):
        plat = Platform(os=OS.DARWIN, arch=Architecture.ARM64)
        asset = find_asset_for_platform(sample_release, plat)
        assert asset is not None
        assert asset.name == "predicate-authorityd-darwin-arm64.tar.gz"

    def test_find_linux_x64(self, sample_release):
        plat = Platform(os=OS.LINUX, arch=Architecture.X64)
        asset = find_asset_for_platform(sample_release, plat)
        assert asset is not None
        assert asset.name == "predicate-authorityd-linux-x64.tar.gz"

    def test_find_windows_x64(self, sample_release):
        plat = Platform(os=OS.WINDOWS, arch=Architecture.X64)
        asset = find_asset_for_platform(sample_release, plat)
        assert asset is not None
        assert asset.name == "predicate-authorityd-windows-x64.zip"

    def test_find_missing_platform(self, sample_release):
        plat = Platform(os=OS.LINUX, arch=Architecture.ARM64)
        asset = find_asset_for_platform(sample_release, plat)
        assert asset is None

    def test_skips_checksum_files(self, sample_release):
        plat = Platform(os=OS.DARWIN, arch=Architecture.ARM64)
        asset = find_asset_for_platform(sample_release, plat)
        assert asset is not None
        assert not asset.name.endswith(".sha256")


class TestExtractArchive:
    """Tests for extract_archive function."""

    def test_extract_tar_gz(self, tmp_path):
        # Create a test tar.gz
        archive_path = tmp_path / "test.tar.gz"
        extract_dir = tmp_path / "extracted"
        content_dir = tmp_path / "content"
        content_dir.mkdir()
        (content_dir / "test.txt").write_text("hello")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(content_dir / "test.txt", arcname="test.txt")

        result = extract_archive(archive_path, extract_dir)
        assert result is True
        assert (extract_dir / "test.txt").exists()
        assert (extract_dir / "test.txt").read_text() == "hello"

    def test_extract_zip(self, tmp_path):
        # Create a test zip
        archive_path = tmp_path / "test.zip"
        extract_dir = tmp_path / "extracted"

        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("test.txt", "hello zip")

        result = extract_archive(archive_path, extract_dir)
        assert result is True
        assert (extract_dir / "test.txt").exists()
        assert (extract_dir / "test.txt").read_text() == "hello zip"

    def test_extract_unsupported_format(self, tmp_path):
        archive_path = tmp_path / "test.rar"
        archive_path.write_text("not a real archive")
        extract_dir = tmp_path / "extracted"

        result = extract_archive(archive_path, extract_dir)
        assert result is False

    def test_extract_rejects_path_traversal_tar(self, tmp_path):
        """Test that tar.gz with path traversal entries is rejected."""
        archive_path = tmp_path / "malicious.tar.gz"
        extract_dir = tmp_path / "extracted"

        # Create a tar.gz with a path traversal entry
        with tarfile.open(archive_path, "w:gz") as tar:
            # Add a normal file
            info = tarfile.TarInfo(name="normal.txt")
            info.size = 5
            tar.addfile(info, fileobj=__import__("io").BytesIO(b"hello"))
            # Add a malicious path traversal entry
            info = tarfile.TarInfo(name="../../../etc/passwd")
            info.size = 6
            tar.addfile(info, fileobj=__import__("io").BytesIO(b"hacked"))

        result = extract_archive(archive_path, extract_dir)
        assert result is False
        # Verify nothing was extracted
        assert not extract_dir.exists() or not any(extract_dir.iterdir())

    def test_extract_rejects_path_traversal_zip(self, tmp_path):
        """Test that zip with path traversal entries is rejected."""
        archive_path = tmp_path / "malicious.zip"
        extract_dir = tmp_path / "extracted"

        # Create a zip with a path traversal entry
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("normal.txt", "hello")
            zf.writestr("../../../etc/passwd", "hacked")

        result = extract_archive(archive_path, extract_dir)
        assert result is False

    def test_extract_rejects_absolute_paths_tar(self, tmp_path):
        """Test that tar.gz with absolute paths is rejected."""
        archive_path = tmp_path / "malicious.tar.gz"
        extract_dir = tmp_path / "extracted"

        with tarfile.open(archive_path, "w:gz") as tar:
            info = tarfile.TarInfo(name="/etc/passwd")
            info.size = 6
            tar.addfile(info, fileobj=__import__("io").BytesIO(b"hacked"))

        result = extract_archive(archive_path, extract_dir)
        assert result is False


class TestPathTraversalHelpers:
    """Tests for path traversal validation helpers."""

    def test_is_path_within_directory_valid(self, tmp_path):
        assert _is_path_within_directory(Path("subdir/file.txt"), tmp_path) is True
        assert _is_path_within_directory(Path("file.txt"), tmp_path) is True

    def test_is_path_within_directory_traversal(self, tmp_path):
        assert _is_path_within_directory(Path("../outside.txt"), tmp_path) is False
        assert _is_path_within_directory(Path("subdir/../../outside.txt"), tmp_path) is False

    def test_validate_archive_members_valid(self, tmp_path):
        members = ["file.txt", "subdir/file.txt", "deep/nested/file.txt"]
        assert _validate_archive_members(members, tmp_path) is True

    def test_validate_archive_members_traversal(self, tmp_path):
        members = ["file.txt", "../etc/passwd"]
        assert _validate_archive_members(members, tmp_path) is False

    def test_validate_archive_members_absolute(self, tmp_path):
        members = ["/etc/passwd", "file.txt"]
        assert _validate_archive_members(members, tmp_path) is False


class TestFindBinaryInDir:
    """Tests for find_binary_in_dir function."""

    def test_find_binary(self, tmp_path):
        binary_path = tmp_path / "bin" / "predicate-authorityd"
        binary_path.parent.mkdir(parents=True)
        binary_path.write_text("#!/bin/sh\necho test")

        found = find_binary_in_dir(tmp_path)
        assert found is not None
        assert found.name == "predicate-authorityd"

    def test_find_binary_nested(self, tmp_path):
        nested_path = tmp_path / "deep" / "nested" / "path" / "predicate-authorityd"
        nested_path.parent.mkdir(parents=True)
        nested_path.write_text("binary")

        found = find_binary_in_dir(tmp_path)
        assert found is not None
        assert "predicate-authorityd" in found.name

    def test_skip_checksum_files(self, tmp_path):
        (tmp_path / "predicate-authorityd.sha256").write_text("abc123")
        (tmp_path / "predicate-authorityd").write_text("binary")

        found = find_binary_in_dir(tmp_path)
        assert found is not None
        assert not found.name.endswith(".sha256")

    def test_not_found(self, tmp_path):
        (tmp_path / "other-file").write_text("not the binary")
        found = find_binary_in_dir(tmp_path)
        assert found is None


class TestHealthCheck:
    """Tests for health_check function."""

    def test_health_check_success(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("account_payable_demo.sidecar.urlopen", return_value=mock_response):
            assert health_check("http://localhost:8787") is True

    def test_health_check_failure(self):
        from urllib.error import URLError

        with patch("account_payable_demo.sidecar.urlopen", side_effect=URLError("Connection refused")):
            assert health_check("http://localhost:8787") is False

    def test_health_check_timeout(self):
        from urllib.error import URLError

        with patch("account_payable_demo.sidecar.urlopen", side_effect=URLError("timed out")):
            assert health_check("http://localhost:8787", timeout=0.1) is False


class TestIsProcessRunning:
    """Tests for is_process_running function."""

    def test_process_running(self):
        # Current process should be running
        import os

        assert is_process_running(os.getpid()) is True

    def test_process_not_running(self):
        # PID 0 is typically not a user process
        assert is_process_running(999999999) is False


class TestStopSidecar:
    """Tests for stop_sidecar function."""

    def test_stop_nonexistent_process(self):
        result = stop_sidecar(999999999)
        assert result is False


class TestGetManualInstallInstructions:
    """Tests for get_manual_install_instructions function."""

    def test_instructions_with_platform(self):
        plat = Platform(os=OS.DARWIN, arch=Architecture.ARM64)
        instructions = get_manual_install_instructions(plat)
        assert "darwin-arm64" in instructions
        assert "predicate-authorityd" in instructions
        assert "policy.yaml" in instructions

    def test_instructions_unknown_platform(self):
        # Mock detect_platform to return None to simulate unsupported platform
        with patch("account_payable_demo.sidecar.detect_platform", return_value=None):
            instructions = get_manual_install_instructions(None)
            assert "Automatic sidecar download is not available" in instructions
            assert "releases/latest" in instructions

    def test_instructions_auto_detect(self):
        with patch("platform.system", return_value="Linux"):
            with patch("platform.machine", return_value="x86_64"):
                instructions = get_manual_install_instructions()
                assert "linux-x64" in instructions


class TestFetchRelease:
    """Tests for fetch_release function."""

    def test_fetch_release_success(self):
        mock_data = {
            "tag_name": "v0.7.2",
            "assets": [
                {
                    "name": "predicate-authorityd-darwin-arm64.tar.gz",
                    "browser_download_url": "https://example.com/download",
                    "size": 4000000,
                }
            ],
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("account_payable_demo.sidecar.urlopen", return_value=mock_response):
            release = fetch_release()
            assert release is not None
            assert release.tag_name == "v0.7.2"
            assert len(release.assets) == 1
            assert release.assets[0].name == "predicate-authorityd-darwin-arm64.tar.gz"

    def test_fetch_release_network_error(self):
        from urllib.error import URLError

        with patch("account_payable_demo.sidecar.urlopen", side_effect=URLError("Network error")):
            release = fetch_release()
            assert release is None


class TestResolveDownloadUrl:
    """Tests for resolve_download_url function."""

    def test_resolve_url_success(self):
        mock_data = {
            "tag_name": "v0.7.2",
            "assets": [
                {
                    "name": "predicate-authorityd-darwin-arm64.tar.gz",
                    "browser_download_url": "https://example.com/darwin-arm64.tar.gz",
                    "size": 4000000,
                }
            ],
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        plat = Platform(os=OS.DARWIN, arch=Architecture.ARM64)

        with patch("account_payable_demo.sidecar.urlopen", return_value=mock_response):
            url = resolve_download_url(plat=plat)
            assert url == "https://example.com/darwin-arm64.tar.gz"

    def test_resolve_url_no_matching_asset(self):
        mock_data = {
            "tag_name": "v0.7.2",
            "assets": [
                {
                    "name": "predicate-authorityd-linux-x64.tar.gz",
                    "browser_download_url": "https://example.com/linux-x64.tar.gz",
                    "size": 4000000,
                }
            ],
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        plat = Platform(os=OS.DARWIN, arch=Architecture.ARM64)

        with patch("account_payable_demo.sidecar.urlopen", return_value=mock_response):
            url = resolve_download_url(plat=plat)
            assert url is None


class TestDownloadSidecar:
    """Tests for download_sidecar function."""

    def test_download_already_exists(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        binary = bin_dir / "predicate-authorityd"
        binary.write_text("#!/bin/sh\necho test")
        binary.chmod(0o755)

        config = SidecarConfig()
        result = download_sidecar(config, bin_dir)

        assert result.success is True
        assert result.binary_path == binary

    def test_download_unsupported_platform(self, tmp_path):
        bin_dir = tmp_path / "bin"
        config = SidecarConfig()

        with patch("account_payable_demo.sidecar.detect_platform", return_value=None):
            result = download_sidecar(config, bin_dir)
            assert result.success is False
            assert "Unsupported platform" in result.error

    def test_download_no_release_url(self, tmp_path):
        bin_dir = tmp_path / "bin"
        config = SidecarConfig()
        plat = Platform(os=OS.DARWIN, arch=Architecture.ARM64)

        with patch("account_payable_demo.sidecar.detect_platform", return_value=plat):
            with patch("account_payable_demo.sidecar.resolve_download_url", return_value=None):
                result = download_sidecar(config, bin_dir)
                assert result.success is False
                assert "Could not resolve download URL" in result.error

    def test_download_windows_not_supported(self, tmp_path):
        """Test that Windows platform is rejected for local bootstrap."""
        bin_dir = tmp_path / "bin"
        config = SidecarConfig()
        plat = Platform(os=OS.WINDOWS, arch=Architecture.X64)

        with patch("account_payable_demo.sidecar.detect_platform", return_value=plat):
            result = download_sidecar(config, bin_dir)
            assert result.success is False
            assert "not supported" in result.error.lower()
            assert "windows" in result.error.lower()
