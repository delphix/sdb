# sdb
The Slick/Simple Debugger

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

### Resources

User and developer resources for sdb can be found in the [project's wiki](https://github.com/delphix/sdb/wiki).
