# sdb
The Slick Debugger

![](https://github.com/delphix/sdb/workflows/.github/workflows/main.yml/badge.svg)

### Installation

Ensure you have the following dependencies:
* Python 3.6 or newer
* [libkdumpfile](https://github.com/ptesarik/libkdumpfile) (optional - needed for kdump-compressed crash dumps)
* [drgn](https://github.com/osandov/drgn/)

Note that in order for `drgn` to support kdump files it needs to be *compiled* with `libkdumpfile`. Unfortunately that means that users should always install `libkdumpfile` first before installing `drgn`.

Finally run the following to install `sdb`:
```
$ git clone https://github.com/delphix/sdb.git
$ cd sdb
$ sudo python3 setup.py install
```

The above should install `sdb` under `/usr/local/bin/`.

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

#### Linting

```
$ python3 -m pip install pylint pytest
$ python3 -m pylint -d duplicate-code -d invalid-name sdb
$ python3 -m pylint -d duplicate-code -d invalid-name tests
```

#### Type Checking

```
$ python3 -m pip install mypy==0.730
$ python3 -m mypy --strict --show-error-codes -p sdb
$ python3 -m mypy --strict --ignore-missing-imports --show-error-codes -p tests
```

#### Style Checks

```
$ python3 -m pip install yapf
$ python3 -m yapf --diff --style google --recursive sdb
$ python3 -m yapf --diff --style google --recursive tests
```

If `yapf` has suggestions you can apply them automatically by substituting
`--diff` with `-i` like this:
```
$ python3 -m yapf -i --style google --recursive sdb
$ python3 -m yapf -i --style google --recursive tests
```

#### Regression Testing

Regression testing is currently done by downloading a refererence crash/core
dump and running a predetermined set of commads on it, ensuring that they
return the same reference output before and after your changes. To see the list
of reference crash dumps refer to the testing matrix of the `pytest` Github
action in `.github/workflows/main.yml`. Here is an example of running the
regression test commands against `dump.201912060006.tar.lzma` with code
coverage and verbose output:

```
$ python3 -m pip install python-config pytest pytest-cov
$ .github/scripts/download-dump-from-s3.sh dump.201912060006.tar.lzma
$ python3 -m pytest -v --cov sdb --cov-report xml tests
```

If you want `pytest` to stop on the first failure it encounters add
`-x/--exitfirst` in the command above.

If you've added new test commands or found mistakes in the current reference
output and you want (re)generate reference output for a crash dump - let's say
`dump.201912060006` from above:
```
$ PYTHONPATH=$(pwd) python3 tests/integration/gen_regression_output.py dump.201912060006
```

or more generically:
```
$ PYTHONPATH=$(pwd) python3 tests/integration/gen_regression_output.py <dump name>
```

For the time being, the test suite is not smart enought to handle the testing
of multiple crash dumps at the same time. Until that happens, developers that
want to test multiple crash dumps need to delete their current crash dump
before downloading the next to run `pytest`. Here is a sequence of commands to
run `pytest` against two crash dumps:
```
$ .github/scripts/download-dump-from-s3.sh dump.201912060006.tar.lzma
$ python3 -m pytest -v --cov sdb --cov-report xml tests
$ .github/scripts/clear-dump.sh
$ .github/scripts/download-dump-from-s3.sh dump.202303131823.tar.gz
$ python3 -m pytest -v --cov sdb --cov-report xml tests
```
