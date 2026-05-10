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


def _setup_remote():
    """Configure the git remote to use the PAT for authentication."""
    pat = os.environ.get("GITHUB_PAT", "")
    if not pat:
        print("[AUTOGIT] GITHUB_PAT not set — auto-push disabled.")
        return False

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
    """Commit any changes and push to origin/main."""
    # Check if there's anything to commit
    code, status, _ = _run(["git", "status", "--porcelain"])
    if not status:
        return  # Nothing changed

    # Stage all changes (exclude session files and pycache)
    _run(["git", "add", "-A"])
    _run(["git", "reset", "--", "*.session", "*.session-journal"])

    # Commit
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    code, out, err = _run(["git", "commit", "-m", f"Auto-commit: {timestamp}"])
    if code != 0:
        print(f"[AUTOGIT] Commit failed: {err}")
        return

    # Push
    code, out, err = _run(["git", "push", "origin", "main"])
    if code == 0:
        print(f"[AUTOGIT] Pushed successfully at {timestamp}")
    else:
        print(f"[AUTOGIT] Push failed: {err}")


def _auto_push_loop():
    """Background loop: commit+push every _INTERVAL seconds."""
    if not _setup_remote():
        return
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
