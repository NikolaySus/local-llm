#!/usr/bin/env python3
import os
from pathlib import Path

import pexpect


REMOTE_USER = os.environ.get("REMOTE_USER", "root")
REMOTE_HOST = os.environ.get("REMOTE_HOST", "109.73.203.55")
REMOTE_SSH_PORT = os.environ.get("REMOTE_SSH_PORT", "22")
SSH_KEY = Path(os.environ.get("SSH_KEY", "~/.ssh/local_llm_proxy_ed25519")).expanduser()
PASSWORD = os.environ.get("VPS_PASSWORD")


def run_password_ssh(command: str) -> None:
    if not PASSWORD:
        raise SystemExit("VPS_PASSWORD is required for first-time key installation")
    ssh_command = (
        f"ssh -p {REMOTE_SSH_PORT} -o StrictHostKeyChecking=accept-new "
        f"{REMOTE_USER}@{REMOTE_HOST} {command!r}"
    )
    child = pexpect.spawn(ssh_command, encoding="utf-8", timeout=30)
    while True:
        index = child.expect([
            "password:",
            "Permission denied",
            pexpect.EOF,
            pexpect.TIMEOUT,
        ])
        if index == 0:
            child.sendline(PASSWORD)
        elif index == 1:
            raise SystemExit("SSH permission denied")
        elif index == 2:
            if child.exitstatus not in (0, None):
                raise SystemExit(f"ssh exited with {child.exitstatus}")
            return
        else:
            raise SystemExit("ssh timed out")


def main() -> None:
    SSH_KEY.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not SSH_KEY.exists():
        os.system(f"ssh-keygen -t ed25519 -N '' -f {SSH_KEY}")

    public_key = SSH_KEY.with_suffix(SSH_KEY.suffix + ".pub").read_text().strip()
    command = (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
        f"grep -qxF {public_key!r} ~/.ssh/authorized_keys 2>/dev/null || "
        f"echo {public_key!r} >> ~/.ssh/authorized_keys && "
        "chmod 600 ~/.ssh/authorized_keys"
    )
    run_password_ssh(command)
    print(f"Installed {SSH_KEY}.pub on {REMOTE_USER}@{REMOTE_HOST}")


if __name__ == "__main__":
    main()
