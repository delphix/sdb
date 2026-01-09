<p align="center">
    <picture>
        <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/sdimitro/sdb/master/assets/img/sdb-logo_white.png">
        <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/sdimitro/sdb/master/assets/img/sdb-logo.png">
        <img src="https://raw.githubusercontent.com/sdimitro/sdb/master/assets/img/sdb-logo.png" alt="SDB" width="350" height="300">
    </picture>
</p>

<p align="center">
    <a href="https://github.com/sdimitro/sdb/actions/workflows/main.yml"><img src="https://github.com/sdimitro/sdb/actions/workflows/main.yml/badge.svg" alt="CI"></a>
    <a href="https://pypi.org/project/sdb-debugger/"><img src="https://img.shields.io/pypi/v/sdb-debugger" alt="PyPI"></a>
    <a href="https://pypi.org/project/sdb-debugger/"><img src="https://img.shields.io/pypi/pyversions/sdb-debugger" alt="Python Versions"></a>
    <a href="https://github.com/sdimitro/sdb/blob/master/LICENSE"><img src="https://img.shields.io/github/license/sdimitro/sdb" alt="License"></a>
</p>

### Installation

#### From PyPI

```bash
pip install sdb-debugger
```

#### From Source

Ensure you have the following dependencies:
* Python 3.10 or newer
* [libkdumpfile](https://github.com/ptesarik/libkdumpfile) (optional - needed for kdump-compressed crash dumps)
* [drgn](https://github.com/osandov/drgn/)

Note that in order for `drgn` to support kdump files it needs to be *compiled* with `libkdumpfile`. Unfortunately that means that users should always install `libkdumpfile` first before installing `drgn`.

Then install `sdb`:
```bash
git clone https://github.com/sdimitro/sdb.git
cd sdb
pip install .
```

For development installation (editable mode with dev dependencies):
```bash
pip install -e ".[dev]"
```

### Quickstart

Running `sudo sdb` attaches sdb to the running kernel by default.
To debug a running program, run `sudo sdb -p <PID>`.
For post-mortem debugging (either a kernel crash dump or a userland core dump), use `sudo sdb <vmlinux path|userland binary path> <dump>`.

```
$ sudo sdb
sdb> find_task 1 | member comm
(char [16])"systemd"
sdb> find_task 1 | stack
TASK_STRUCT        STATE             COUNT
==========================================
0xffff89cea441dd00 INTERRUPTIBLE         1
                  __schedule+0x2e5
                  schedule+0x33
                  schedule_hrtimeout_range_clock+0xfd
                  schedule_hrtimeout_range+0x13
                  ep_poll+0x40a
                  do_epoll_wait+0xb7
                  __x64_sys_epoll_wait+0x1e
                  do_syscall_64+0x57
                  entry_SYSCALL_64+0x7c
sdb> addr modules | lxlist "struct module" list | member name ! sort | head -n 3
(char [56])"aesni_intel"
(char [56])"async_memcpy"
(char [56])"async_pq"
```

### Developer Testing

First, install the development dependencies:
```bash
pip install -e ".[dev]"
# Or using requirements file:
pip install -r requirements-dev.txt
```

#### Linting

```bash
pylint -d duplicate-code -d invalid-name sdb
pylint -d duplicate-code -d invalid-name tests
```

#### Ruff (Fast Linting and Formatting)

Ruff is a fast Python linter and formatter that combines multiple tools:

```bash
ruff check sdb tests
```

#### Type Checking

```bash
mypy --strict --show-error-codes -p sdb
mypy --strict --ignore-missing-imports --show-error-codes -p tests
```

Note: pytest is required for mypy to properly type-check test decorators.

#### Style Checks

```bash
yapf --diff --style google --recursive sdb
yapf --diff --style google --recursive tests
```

If `yapf` has suggestions you can apply them automatically by substituting
`--diff` with `-i` like this:
```bash
yapf -i --style google --recursive sdb
yapf -i --style google --recursive tests
```

#### Unit Testing

Unit tests don't require crash dumps and can be run quickly:

```bash
pytest -v --cov sdb --cov-report xml tests/unit
```

#### Integration Testing

Integration tests require crash/core dumps to test against live debugging scenarios:

```bash
.github/scripts/download-dumps-from-gdrive.sh
.github/scripts/extract-dump.sh dump.201912060006.tar.lzma
.github/scripts/extract-dump.sh dump.202303131823.tar.gz
pytest -v --cov sdb --cov-report xml tests/integration
```

To run all tests (unit + integration):
```bash
pytest -v --cov sdb --cov-report xml tests
```

If you want `pytest` to stop on the first failure it encounters add
`-x/--exitfirst` to the command.

If you've added new test commands or found mistakes in the current reference
output and you want to (re)generate reference output, download all crash/core
dumps (or the specific one you want to correct) and run the following:
```bash
PYTHONPATH=$(pwd) python3 tests/integration/gen_regression_output.py
```
