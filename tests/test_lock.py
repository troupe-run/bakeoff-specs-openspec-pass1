"""Commands against one theatre are serialised by a lock on its `.troupe/` directory."""

import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path


def test_set_waits_while_another_process_holds_the_theatre_lock(tmp_path: Path) -> None:
    config = tmp_path / ".troupe" / "troupe.yml"
    config.parent.mkdir()
    config.write_bytes(b"a: 1\n")
    fd = os.open(config.parent, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        proc = subprocess.Popen(
            [sys.executable, "-m", "troupe.cli", "config", "set", "a", "2", "--theatre", str(tmp_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(1.5)
        assert proc.poll() is None, "set ran while the lock was held"
        assert config.read_bytes() == b"a: 1\n"
    finally:
        os.close(fd)
    out, err = proc.communicate(timeout=30)
    assert (proc.returncode, out, err) == (0, b"", b"")
    assert config.read_bytes() == b"a: 2\n"
