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

### Resources

User and developer resources for sdb can be found in the [project's wiki](https://github.com/delphix/sdb/wiki).
