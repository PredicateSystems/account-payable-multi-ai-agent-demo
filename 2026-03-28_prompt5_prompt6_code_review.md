# Code Review: Prompt 5 + Prompt 6

**Date:** 2026-03-28
**Scope reviewed:**

- `Prompt 5: Add Python packaging, config loading, and provider selection`
- `Prompt 6: Implement sidecar bootstrap and launcher behavior in Python-friendly modules`

**Repo:**

- `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo`

## Findings

### 1. `run-demo.sh --dry-run` is not actually dry

Severity: high

The launcher performs a real sidecar download before printing the simulated commands. I verified this by running:

```bash
./run-demo.sh --local --dry-run
```

and observing that `.bin/predicate-authorityd` was downloaded.

Why this matters:

- users expect dry-run mode to avoid network access and file mutations
- CI or review workflows may use dry-run specifically to avoid side effects
- the current behavior makes the launcher harder to trust

Relevant code:

```bash
download_sidecar() {
  ...
  result=$(python3 -c "
from account_payable_demo.sidecar import download_sidecar
...
result = download_sidecar(config, bin_dir, tmp_dir)
print(json.dumps({
    'success': result.success,
    'binary_path': str(result.binary_path) if result.binary_path else None,
    'error': result.error
}))
" 2>/dev/null) || result='{"success": false, "error": "Python module failed"}'
```

Recommendation:

- gate all download behavior behind a `DRY_RUN` check before the Python helper is invoked
- in dry-run mode, print the resolved actions only

### 2. Windows support is advertised but not correctly implemented end to end

Severity: medium

The sidecar module models Windows support, but the install and execution path is still Unix-oriented.

Problems:

- the binary is always written to `.bin/predicate-authorityd`
- no `.exe` handling exists
- the launcher later executes that exact Unix-style path

Why this matters:

- a Windows user may appear supported by platform detection but fail at runtime
- this creates a false portability signal in the local bootstrap story

Relevant code:

```python
class Platform:
    @property
    def asset_suffix(self) -> str:
        if self.os == OS.WINDOWS:
            return f"{self.os.value}-{self.arch.value}.zip"
        return f"{self.os.value}-{self.arch.value}.tar.gz"

    @property
    def asset_name(self) -> str:
        return f"predicate-authorityd-{self.asset_suffix}"
```

```python
def download_sidecar(...):
    dest_binary = bin_dir / "predicate-authorityd"
    ...
    shutil.copy2(binary, dest_binary)
    dest_binary.chmod(0o755)
```

Recommendation:

- either implement proper Windows binary naming and launcher behavior
- or explicitly narrow supported local bootstrap platforms for now

### 3. Archive extraction is unsafe for downloaded release assets

Severity: medium

The sidecar bootstrap uses unrestricted `extractall()` on downloaded archives.

Why this matters:

- release assets are network-downloaded content
- malformed or compromised archives can contain path traversal entries
- this can write files outside the extraction directory

Relevant code:

```python
if name.endswith(".tar.gz") or name.endswith(".tgz"):
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(dest_dir)
    return True

if name.endswith(".zip"):
    with zipfile.ZipFile(archive, "r") as zf:
        zf.extractall(dest_dir)
    return True
```

Recommendation:

- validate archive member paths before extraction
- reject entries that escape `dest_dir`

## Completion Status

### Prompt 5

Status: mostly complete

What is present:

- package structure under `account_payable_demo/`
- config model and `.env` loading
- provider abstraction for cloud and local paths
- pytest coverage for config and provider selection
- `pyproject.toml`, `requirements.txt`, and test layout
- `main.py --validate` works

What still does not exist:

- no actual workflow execution yet, which is acceptable for this prompt

Assessment:

- the implementation meets the intent of Prompt 5

### Prompt 6

Status: partially complete

What is present:

- `account_payable_demo/sidecar.py`
- tests for platform mapping, release resolution, extraction helpers, and health checks
- launcher updated to call Python helpers

What is still weak or incomplete:

- the launcher is not actually thin yet
- shell still contains substantial fallback bootstrap logic
- dry-run mode is incorrect
- platform support claims are broader than the executable behavior

Assessment:

- the implementation is directionally correct
- but Prompt 6 should not be considered fully complete until launcher behavior is corrected and support boundaries are made explicit

## Verification Performed

I ran the following commands:

```bash
cd /Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo
python3 -m pytest
python3 main.py --validate
./run-demo.sh --local --dry-run
```

Observed results:

- `python3 -m pytest`: passed, 130 tests
- `python3 main.py --validate`: succeeded
- `./run-demo.sh --local --dry-run`: exposed the dry-run side effect by downloading the sidecar

## Overall Assessment

The Python packaging/config/provider work is in good shape for this stage.

The sidecar/bootstrap work is useful progress, but it still has correctness and safety issues that should be fixed before relying on it as the recommended local bootstrap path.

## Recommended Next Fixes

1. Fix `--dry-run` so it performs no downloads or file writes.
2. Narrow or correctly implement platform support, especially Windows.
3. Add safe archive extraction.
4. Optionally move more fallback logic out of shell so `run-demo.sh` becomes thinner and easier to reason about.
