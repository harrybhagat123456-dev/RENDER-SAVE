# Auto-commit and push changes to GitHub every 5 minutes
# Uses GITHUB_PAT secret to authenticate pushes

import os
import subprocess
import threading
import time

_REPO_URL = "https://github.com/harrybhagat123456-dev/RENDER-SAVE"
_INTERVAL = 300  # seconds between auto-commits


def _run(cmd, **kwargs):
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _clear_git_locks():
    """Remove stale git lock files that block config writes."""
    for lock in [".git/config.lock", ".git/index.lock", ".git/HEAD.lock"]:
        try:
            if os.path.exists(lock):
                os.remove(lock)
                print(f"[AUTOGIT] Removed stale lock: {lock}")
        except Exception:
            pass


def _setup_remote():
    """Configure the git remote to use the PAT for authentication."""
    pat = os.environ.get("GITHUB_PAT", "")
    if not pat:
        print("[AUTOGIT] GITHUB_PAT not set — auto-push disabled.")
        return False

    _clear_git_locks()

    # Extract repo path from URL
    repo_path = _REPO_URL.replace("https://github.com/", "")
    auth_url = f"https://{pat}@github.com/{repo_path}"

    code, _, err = _run(["git", "remote", "set-url", "origin", auth_url])
    if code != 0:
        print(f"[AUTOGIT] Could not set remote URL: {err}")
        return False

    # Set git identity if not already set
    _run(["git", "config", "user.email", "bot@replit.auto"])
    _run(["git", "config", "user.name", "SaveRestrictedBot"])
    print("[AUTOGIT] Remote configured with PAT.")
    return True


def _commit_and_push():
    """Commit any pending changes then push — always pushes so unpushed commits land too."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    # Stage and commit only if there are local changes
    code, status, _ = _run(["git", "status", "--porcelain"])
    if status:
        _run(["git", "add", "-A"])
        _run(["git", "reset", "--", "*.session", "*.session-journal"])
        code, out, err = _run(["git", "commit", "-m", f"Auto-commit: {timestamp}"])
        if code != 0:
            print(f"[AUTOGIT] Commit failed: {err}")

    # Force-push local state — Replit's checkpoint system also pushes to this
    # remote, causing divergence. Our local code is always authoritative.
    code, out, err = _run(["git", "push", "origin", "main", "--force"])
    if code == 0:
        print(f"[AUTOGIT] Pushed successfully at {timestamp}")
    else:
        print(f"[AUTOGIT] Push failed: {err}")


def _auto_push_loop():
    """Background loop: push immediately at startup, then every _INTERVAL seconds."""
    if not _setup_remote():
        return
    # Push right away on startup to catch any unpushed commits
    try:
        _commit_and_push()
    except Exception as e:
        print(f"[AUTOGIT] Error during startup push: {e}")
    while True:
        time.sleep(_INTERVAL)
        try:
            _commit_and_push()
        except Exception as e:
            print(f"[AUTOGIT] Error during auto-push: {e}")


def start_auto_push():
    """Start the background auto-push thread."""
    t = threading.Thread(target=_auto_push_loop, daemon=True)
    t.start()
    print(f"[AUTOGIT] Auto-push thread started (every {_INTERVAL}s).")
