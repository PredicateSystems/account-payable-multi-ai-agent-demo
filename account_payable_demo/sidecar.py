"""Sidecar bootstrap and management for the Account Payable Demo."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from account_payable_demo.config import SidecarConfig


class OS(str, Enum):
    """Supported operating systems."""

    DARWIN = "darwin"
    LINUX = "linux"
    WINDOWS = "windows"


class Architecture(str, Enum):
    """Supported CPU architectures."""

    X64 = "x64"
    ARM64 = "arm64"


# Platforms that support local sidecar bootstrap
# Windows is excluded because:
# - Binary naming differs (.exe suffix)
# - chmod is not applicable
# - Shell launcher is Unix-oriented
LOCAL_BOOTSTRAP_SUPPORTED_OS = frozenset({OS.DARWIN, OS.LINUX})


@dataclass
class Platform:
    """Detected platform information."""

    os: OS
    arch: Architecture

    @property
    def asset_suffix(self) -> str:
        """Get the expected release asset suffix for this platform."""
        if self.os == OS.WINDOWS:
            return f"{self.os.value}-{self.arch.value}.zip"
        return f"{self.os.value}-{self.arch.value}.tar.gz"

    @property
    def asset_name(self) -> str:
        """Get the expected release asset name for this platform."""
        return f"predicate-authorityd-{self.asset_suffix}"

    @property
    def supports_local_bootstrap(self) -> bool:
        """Check if this platform supports local sidecar bootstrap."""
        return self.os in LOCAL_BOOTSTRAP_SUPPORTED_OS


def detect_os() -> Optional[OS]:
    """
    Detect the current operating system.

    Returns:
        OS enum value or None if unsupported.
    """
    system = platform.system().lower()
    os_map = {
        "darwin": OS.DARWIN,
        "linux": OS.LINUX,
        "windows": OS.WINDOWS,
    }
    return os_map.get(system)


def detect_architecture() -> Optional[Architecture]:
    """
    Detect the current CPU architecture.

    Returns:
        Architecture enum value or None if unsupported.
    """
    machine = platform.machine().lower()
    arch_map = {
        "x86_64": Architecture.X64,
        "amd64": Architecture.X64,
        "arm64": Architecture.ARM64,
        "aarch64": Architecture.ARM64,
    }
    return arch_map.get(machine)


def detect_platform() -> Optional[Platform]:
    """
    Detect the current platform (OS and architecture).

    Returns:
        Platform instance or None if unsupported.
    """
    os_val = detect_os()
    arch_val = detect_architecture()

    if os_val is None or arch_val is None:
        return None

    return Platform(os=os_val, arch=arch_val)


def normalize_os(raw: str) -> Optional[OS]:
    """
    Normalize OS string to enum.

    Args:
        raw: Raw OS string (e.g., from uname).

    Returns:
        OS enum or None.
    """
    normalized = raw.lower().strip()
    mapping = {
        "darwin": OS.DARWIN,
        "macos": OS.DARWIN,
        "mac": OS.DARWIN,
        "linux": OS.LINUX,
        "windows": OS.WINDOWS,
        "win": OS.WINDOWS,
        "win32": OS.WINDOWS,
        "win64": OS.WINDOWS,
    }
    return mapping.get(normalized)


def normalize_architecture(raw: str) -> Optional[Architecture]:
    """
    Normalize architecture string to enum.

    Args:
        raw: Raw architecture string (e.g., from uname -m).

    Returns:
        Architecture enum or None.
    """
    normalized = raw.lower().strip()
    mapping = {
        "x86_64": Architecture.X64,
        "amd64": Architecture.X64,
        "x64": Architecture.X64,
        "arm64": Architecture.ARM64,
        "aarch64": Architecture.ARM64,
    }
    return mapping.get(normalized)


@dataclass
class ReleaseAsset:
    """GitHub release asset information."""

    name: str
    download_url: str
    size: int


@dataclass
class Release:
    """GitHub release information."""

    tag_name: str
    assets: list[ReleaseAsset]


def fetch_release(
    repo: str = "PredicateSystems/predicate-authority-sidecar",
    version: str = "latest",
    timeout: float = 30.0,
) -> Optional[Release]:
    """
    Fetch release information from GitHub API.

    Args:
        repo: GitHub repository in owner/repo format.
        version: Version tag or "latest".
        timeout: Request timeout in seconds.

    Returns:
        Release instance or None on error.
    """
    if version == "latest":
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    else:
        api_url = f"https://api.github.com/repos/{repo}/releases/tags/{version}"

    try:
        request = Request(api_url)
        request.add_header("Accept", "application/vnd.github.v3+json")
        request.add_header("User-Agent", "predicate-demo/1.0")

        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))

        assets = [
            ReleaseAsset(
                name=asset["name"],
                download_url=asset["browser_download_url"],
                size=asset.get("size", 0),
            )
            for asset in data.get("assets", [])
        ]

        return Release(tag_name=data.get("tag_name", version), assets=assets)

    except (HTTPError, URLError, json.JSONDecodeError, KeyError):
        return None


def find_asset_for_platform(
    release: Release,
    plat: Platform,
) -> Optional[ReleaseAsset]:
    """
    Find the matching release asset for a platform.

    Args:
        release: Release information.
        plat: Target platform.

    Returns:
        Matching ReleaseAsset or None.
    """
    expected_name = plat.asset_name

    # First try exact match
    for asset in release.assets:
        if asset.name == expected_name:
            return asset

    # Fall back to pattern matching
    os_pattern = plat.os.value
    arch_pattern = plat.arch.value

    for asset in release.assets:
        name_lower = asset.name.lower()
        # Skip checksum files
        if name_lower.endswith(".sha256") or name_lower.endswith(".md5"):
            continue
        # Check for OS and arch in name
        if os_pattern in name_lower and arch_pattern in name_lower:
            return asset

    return None


def resolve_download_url(
    repo: str = "PredicateSystems/predicate-authority-sidecar",
    version: str = "latest",
    plat: Optional[Platform] = None,
) -> Optional[str]:
    """
    Resolve the download URL for the sidecar binary.

    Args:
        repo: GitHub repository.
        version: Version tag or "latest".
        plat: Target platform (auto-detected if None).

    Returns:
        Download URL or None.
    """
    if plat is None:
        plat = detect_platform()
        if plat is None:
            return None

    release = fetch_release(repo, version)
    if release is None:
        return None

    asset = find_asset_for_platform(release, plat)
    if asset is None:
        return None

    return asset.download_url


def download_file(url: str, dest: Path, timeout: float = 120.0) -> bool:
    """
    Download a file from URL.

    Args:
        url: Download URL.
        dest: Destination path.
        timeout: Request timeout.

    Returns:
        True on success, False on error.
    """
    try:
        request = Request(url)
        request.add_header("User-Agent", "predicate-demo/1.0")

        with urlopen(request, timeout=timeout) as response:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                shutil.copyfileobj(response, f)
        return True
    except (HTTPError, URLError, OSError):
        return False


def _is_path_within_directory(path: Path, directory: Path) -> bool:
    """
    Check if a path is safely within a directory (no path traversal).

    Args:
        path: The path to check.
        directory: The directory that should contain the path.

    Returns:
        True if path is within directory, False otherwise.
    """
    try:
        resolved_path = (directory / path).resolve()
        resolved_dir = directory.resolve()
        return resolved_path.is_relative_to(resolved_dir)
    except (ValueError, OSError):
        return False


def _validate_archive_members(members: list[str], dest_dir: Path) -> bool:
    """
    Validate that all archive members extract safely within dest_dir.

    Args:
        members: List of member paths from the archive.
        dest_dir: Destination directory.

    Returns:
        True if all members are safe, False if any would escape dest_dir.
    """
    for member in members:
        # Reject absolute paths
        if Path(member).is_absolute():
            return False
        # Reject path traversal
        if not _is_path_within_directory(Path(member), dest_dir):
            return False
    return True


def extract_archive(archive: Path, dest_dir: Path) -> bool:
    """
    Extract a tar.gz or zip archive safely.

    Validates archive members to prevent path traversal attacks.

    Args:
        archive: Path to archive file.
        dest_dir: Destination directory.

    Returns:
        True on success, False on error or if archive contains unsafe paths.
    """
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = archive.name.lower()

        if name.endswith(".tar.gz") or name.endswith(".tgz"):
            with tarfile.open(archive, "r:gz") as tar:
                members = [m.name for m in tar.getmembers()]
                if not _validate_archive_members(members, dest_dir):
                    return False
                tar.extractall(dest_dir)
            return True

        if name.endswith(".zip"):
            with zipfile.ZipFile(archive, "r") as zf:
                members = zf.namelist()
                if not _validate_archive_members(members, dest_dir):
                    return False
                zf.extractall(dest_dir)
            return True

        return False
    except (tarfile.TarError, zipfile.BadZipFile, OSError):
        return False


def find_binary_in_dir(search_dir: Path, binary_name: str = "predicate-authorityd") -> Optional[Path]:
    """
    Find the sidecar binary in a directory tree.

    Args:
        search_dir: Directory to search.
        binary_name: Binary name to find.

    Returns:
        Path to binary or None.
    """
    for path in search_dir.rglob("*"):
        if path.is_file() and binary_name in path.name:
            # Skip checksum/signature files
            if path.suffix in (".sha256", ".md5", ".sig", ".asc"):
                continue
            return path
    return None


@dataclass
class DownloadResult:
    """Result of a sidecar download attempt."""

    success: bool
    binary_path: Optional[Path] = None
    error: Optional[str] = None


def download_sidecar(
    config: SidecarConfig,
    bin_dir: Path,
    tmp_dir: Optional[Path] = None,
) -> DownloadResult:
    """
    Download and extract the sidecar binary.

    Args:
        config: Sidecar configuration.
        bin_dir: Directory to place the binary.
        tmp_dir: Temporary directory for downloads.

    Returns:
        DownloadResult with status and path.
    """
    dest_binary = bin_dir / "predicate-authorityd"

    # Already exists
    if dest_binary.exists() and os.access(dest_binary, os.X_OK):
        return DownloadResult(success=True, binary_path=dest_binary)

    # Detect platform
    plat = detect_platform()
    if plat is None:
        return DownloadResult(
            success=False,
            error="Unsupported platform. Manual installation required.",
        )

    # Check if platform supports local bootstrap
    if not plat.supports_local_bootstrap:
        return DownloadResult(
            success=False,
            error=f"Local bootstrap is not supported on {plat.os.value}. "
            f"Please use Docker mode or install the sidecar manually.",
        )

    # Resolve download URL
    url = resolve_download_url(
        repo=config.release_repo,
        version=config.version,
        plat=plat,
    )
    if url is None:
        return DownloadResult(
            success=False,
            error=f"Could not resolve download URL for {plat.os.value}-{plat.arch.value}",
        )

    # Download
    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="predicate-sidecar-"))

    archive_name = url.split("/")[-1]
    archive_path = tmp_dir / archive_name

    if not download_file(url, archive_path):
        return DownloadResult(
            success=False,
            error=f"Failed to download from {url}",
        )

    # Handle different archive types
    if archive_name.endswith((".tar.gz", ".tgz", ".zip")):
        extract_dir = tmp_dir / "extracted"
        if not extract_archive(archive_path, extract_dir):
            return DownloadResult(
                success=False,
                error="Failed to extract archive",
            )

        binary = find_binary_in_dir(extract_dir)
        if binary is None:
            return DownloadResult(
                success=False,
                error="Binary not found in extracted archive",
            )
    else:
        # Assume raw binary
        binary = archive_path

    # Copy to final location
    bin_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, dest_binary)
    dest_binary.chmod(0o755)

    return DownloadResult(success=True, binary_path=dest_binary)


def health_check(url: str, timeout: float = 5.0) -> bool:
    """
    Check if the sidecar is healthy.

    Args:
        url: Sidecar base URL.
        timeout: Request timeout.

    Returns:
        True if healthy, False otherwise.
    """
    health_url = f"{url.rstrip('/')}/health"
    try:
        request = Request(health_url)
        request.add_header("User-Agent", "predicate-demo/1.0")
        with urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except (HTTPError, URLError, OSError):
        return False


def wait_for_healthy(
    url: str,
    max_attempts: int = 30,
    interval: float = 1.0,
) -> bool:
    """
    Wait for the sidecar to become healthy.

    Args:
        url: Sidecar base URL.
        max_attempts: Maximum number of health check attempts.
        interval: Seconds between attempts.

    Returns:
        True if healthy within timeout, False otherwise.
    """
    import time

    for _ in range(max_attempts):
        if health_check(url):
            return True
        time.sleep(interval)
    return False


@dataclass
class SidecarProcess:
    """Information about a running sidecar process."""

    pid: int
    binary_path: Path
    policy_path: Path
    log_path: Optional[Path] = None


def start_sidecar(
    binary_path: Path,
    policy_path: Path,
    log_dir: Optional[Path] = None,
) -> Optional[SidecarProcess]:
    """
    Start the sidecar process.

    Args:
        binary_path: Path to the sidecar binary.
        policy_path: Path to the policy file.
        log_dir: Directory for log files.

    Returns:
        SidecarProcess or None on error.
    """
    if not binary_path.exists():
        return None
    if not policy_path.exists():
        return None

    log_path = None
    stdout = subprocess.DEVNULL
    stderr = subprocess.DEVNULL

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "sidecar.log"
        log_file = open(log_path, "w")
        stdout = log_file
        stderr = subprocess.STDOUT

    try:
        process = subprocess.Popen(
            [str(binary_path), "--policy-file", str(policy_path)],
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        return SidecarProcess(
            pid=process.pid,
            binary_path=binary_path,
            policy_path=policy_path,
            log_path=log_path,
        )
    except OSError:
        return None


def stop_sidecar(pid: int) -> bool:
    """
    Stop a running sidecar process.

    Args:
        pid: Process ID.

    Returns:
        True if stopped, False otherwise.
    """
    import signal

    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except (OSError, ProcessLookupError):
        return False


def is_process_running(pid: int) -> bool:
    """
    Check if a process is running.

    Args:
        pid: Process ID.

    Returns:
        True if running, False otherwise.
    """
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def get_manual_install_instructions(plat: Optional[Platform] = None) -> str:
    """
    Get manual installation instructions.

    Args:
        plat: Target platform (auto-detected if None).

    Returns:
        Instruction text.
    """
    if plat is None:
        plat = detect_platform()

    base_url = "https://github.com/PredicateSystems/predicate-authority-sidecar/releases/latest"

    if plat is None:
        return f"""Automatic sidecar download is not available for your platform.

Manual installation:
1. Visit {base_url}
2. Download the appropriate binary for your OS and architecture
3. Extract and place 'predicate-authorityd' in your PATH or .bin/ directory
4. Run: predicate-authorityd --policy-file ./policy.yaml
"""

    return f"""Automatic sidecar download failed.

Manual installation for {plat.os.value}-{plat.arch.value}:
1. Download: {base_url}/download/{plat.asset_name}
2. Extract the archive
3. Move 'predicate-authorityd' to .bin/ or your PATH
4. Run: predicate-authorityd --policy-file ./policy.yaml
"""
