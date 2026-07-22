#!/usr/bin/env python3
"""
Directioner - One-command setup and run script (Python version for cross-platform support)

Usage:
    python run.py setup    - Build and install
    python run.py check    - Verify configuration
    python run.py health   - Comprehensive health check
    python run.py test     - Run test suite
    python run.py run      - Start the bot
    python run.py clean    - Clean build artifacts
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
os.chdir(SCRIPT_DIR)


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


def log_info(msg: str) -> None:
    print(f"{Colors.GREEN}[INFO]{Colors.NC} {msg}")


def log_warn(msg: str) -> None:
    print(f"{Colors.YELLOW}[WARN]{Colors.NC} {msg}")


def log_error(msg: str) -> None:
    print(f"{Colors.RED}[ERROR]{Colors.NC} {msg}", file=sys.stderr)


def log_step(msg: str) -> None:
    print(f"\n{Colors.BLUE}▶ {msg}{Colors.NC}")


def run_command(cmd: list[str], *, cwd: Path | None = None, capture: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    
    return subprocess.run(
        cmd,
        cwd=cwd or SCRIPT_DIR,
        capture_output=capture,
        text=True,
        env=merged_env,
    )


def check_python_version() -> tuple[int, int]:
    """Check Python version, return (major, minor)."""
    return sys.version_info.major, sys.version_info.minor


def setup() -> None:
    """Build and install the project."""
    log_step("Setting up Directioner...")

    major, minor = check_python_version()
    if major < 3 or (major == 3 and minor < 11):
        log_error(f"Python 3.11+ required, found {major}.{minor}")
        sys.exit(1)
    log_info(f"Python {major}.{minor} detected")

    # Check for Rust
    rust_check = run_command(["rustc", "--version"], capture=False)
    if rust_check.returncode != 0:
        log_warn("Rust not found. Installing via rustup...")
        subprocess.run(["curl", "--proto", "=https", "--tlsv1.2", "-sSf", "https://sh.rustup.rs"], check=True)
        subprocess.run(["sh", "-s", "--", "-y"], input=subprocess.DEVNULL)
        # Source cargo env
        cargo_env = SCRIPT_DIR / ".cargo" / "env"
        if cargo_env.exists():
            subprocess.run(["bash", "-c", f"source {cargo_env} && rustc --version"], check=True)
    else:
        log_info(f"Rust detected: {rust_check.stdout.strip()}")

    # Create virtual environment
    venv_path = SCRIPT_DIR / ".venv"
    if not venv_path.exists():
        log_info("Creating virtual environment...")
        venv.create(venv_path, with_pip=True)
    else:
        log_info("Using existing virtual environment...")

    # Determine pip and python in venv
    if sys.platform == "win32":
        venv_python = venv_path / "Scripts" / "python.exe"
        venv_pip = venv_path / "Scripts" / "pip.exe"
    else:
        venv_python = venv_path / "bin" / "python"
        venv_pip = venv_path / "bin" / "pip"

    # Upgrade pip
    log_info("Upgrading pip...")
    run_command([str(venv_pip), "install", "--upgrade", "pip"], capture=False)

    # Install maturin
    log_info("Installing maturin...")
    run_command([str(venv_pip), "install", "maturin"], capture=False)

    # Build Rust native extension
    log_step("Building Rust native extension...")
    result = run_command(
        ["maturin", "build", "--manifest-path", "native/rust/Cargo.toml", "--out", "dist"],
        capture=True,
    )
    if result.returncode != 0:
        log_error(f"Rust build failed:\n{result.stderr}")
        sys.exit(1)
    
    # Find the wheel
    dist_dir = SCRIPT_DIR / "dist"
    wheels = list(dist_dir.glob("*.whl"))
    if wheels:
        wheel_path = wheels[0]
        log_info(f"Installing native wheel: {wheel_path.name}")
        run_command([str(venv_pip), "install", str(wheel_path)], capture=False)
    else:
        log_error("No wheel found in dist/")
        sys.exit(1)

    # Install Python dependencies
    log_step("Installing Python dependencies...")
    run_command([str(venv_pip), "install", "-e", "."], capture=False)

    # Install test dependencies
    log_info("Installing test dependencies...")
    run_command([str(venv_pip), "install", "pytest", "pytest-asyncio"], capture=False)

    log_step("Setup complete!")
    log_info("Run './run.sh check' or 'python run.py check' to verify.")


def get_venv_python() -> tuple[Path, bool]:
    """Get the Python executable in the venv. Returns (python_path, using_system_python)."""
    if sys.platform == "win32":
        venv_python = SCRIPT_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python = SCRIPT_DIR / ".venv" / "bin" / "python"
    
    if venv_python.exists():
        return venv_python, False
    return Path(sys.executable), True


def run_python_module(module: str, args: list[str] | None = None) -> int:
    """Run a Python module with PYTHONPATH set."""
    venv_python, using_system = get_venv_python()
    if using_system:
        log_warn("No venv found, using system Python")
    env = {
        "PYTHONPATH": str(SCRIPT_DIR / "src"),
    }
    cmd = [str(venv_python), "-m", module]
    if args:
        cmd.extend(args)
    result = subprocess.run(cmd, env=env)
    return result.returncode


def check() -> None:
    """Run configuration and health checks."""
    log_step("Running configuration check...")
    run_python_module("directioner.app", ["check"])
    print()
    log_step("Running health check...")
    run_python_module("directioner.app", ["health-check"])


def health() -> None:
    """Run comprehensive health check."""
    log_step("Running comprehensive health check...")
    run_python_module("directioner.app", ["health-check"])


def test() -> None:
    """Run the test suite."""
    log_step("Running test suite...")
    venv_python, using_system = get_venv_python()
    if using_system:
        log_warn("No venv found, using system Python")
    env = {"PYTHONPATH": str(SCRIPT_DIR / "src")}
    result = subprocess.run(
        [str(venv_python), "-m", "pytest", "tests/", "-v", "--tb=short"],
        env=env,
    )
    sys.exit(result.returncode)


def run_bot() -> None:
    """Start the Discord bot."""
    # Check for config
    config_path = SCRIPT_DIR / "configs" / "app.yaml"
    if not config_path.exists():
        example_path = SCRIPT_DIR / "configs" / "app.example.yaml"
        if example_path.exists():
            log_warn("No config found. Copying example config...")
            shutil.copy(example_path, config_path)
            log_warn("Please edit configs/app.yaml and add your Discord bot token.")
        else:
            log_error("No configuration found!")
            sys.exit(1)

    log_step("Starting Directioner bot...")
    run_python_module("directioner.app", ["run", "--config", "configs/app.yaml"])


def clean() -> None:
    """Clean build artifacts."""
    log_step("Cleaning build artifacts...")
    
    items_to_remove = [
        ".venv",
        "dist",
        "build",
        ".pytest_cache",
    ]
    
    for item in items_to_remove:
        path = SCRIPT_DIR / item
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            log_info(f"Removed: {item}")
    
    # Clean Rust target
    rust_target = SCRIPT_DIR / "native" / "rust" / "target"
    if rust_target.exists():
        log_info("Note: Rust target directory preserved (run 'cargo clean' inside native/rust/ for full clean)")
    
    # Clean pycache
    for pycache in SCRIPT_DIR.rglob("__pycache__"):
        shutil.rmtree(pycache)
    for pyc in SCRIPT_DIR.rglob("*.pyc"):
        pyc.unlink()
    
    log_info("Clean complete.")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        print("Commands: setup, check, health, test, run, clean")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "setup":
        setup()
    elif command == "check":
        check()
    elif command == "health":
        health()
    elif command == "test":
        test()
    elif command == "run":
        run_bot()
    elif command == "clean":
        clean()
    elif command in ("help", "--help", "-h"):
        print(__doc__)
        sys.exit(0)
    else:
        log_error(f"Unknown command: {command}")
        print("Run 'python run.py help' for usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()
