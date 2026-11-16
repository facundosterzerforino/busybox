# BusyBox 1.38.0 for a Motorola XT550 (Android 2.3), built from source

This branch is official BusyBox tag `1_38_0`
(`fc71374dfccd46448c62947269a35f1420d7ee28`, from git.busybox.net). The
release tarball `busybox-1.38.0.tar.bz2` (SHA256 `34f9ea6f…3bb2`, as published
on busybox.net) has the same files. It adds the `xt550/` folder and one small
patch.

It replaces a prebuilt BusyBox 1.21 binary of unknown origin, from the Romaster
root tool, that was used as root over adb to maintain the phone.

## What is built

- One static binary for armeabi-v7a, Android 2.3 (bionic android-9), 304 KB.
- Only the 67 commands used for maintenance:
  - files: `cat cp mv rm rmdir ls mkdir chmod chown chgrp ln readlink realpath
    stat du dd sync`;
  - archives: `tar gzip gunzip zcat`;
  - checksums: `sha1sum sha256sum sha512sum md5sum cmp`;
  - text: `awk sed grep egrep fgrep head tail wc sort uniq tr cut tee od
    hexdump strings xargs printf echo test [ [[ expr seq basename dirname env
    true false which date`;
  - processes and network: `find killall pidof pgrep pkill free uptime nc
    sleep usleep`.
- No shell, no setuid, no network daemons.
- `df` and `touch` are left out: bionic android-9 has no `statvfs` or
  `utimensat`.

## Why not `make`

BusyBox's Kbuild needs a Linux host with a native C compiler. This was built on
Windows with only the Android NDK, so `xt550/` reproduces the generated files in
Python:

| BusyBox host step | here |
|---|---|
| `scripts/gen_build_files.sh` | run as is with a POSIX `sh` (Git for Windows) |
| `scripts/kconfig` (`make *config`) | `xt550/configure.py` with [Kconfiglib](https://github.com/ulfalizer/Kconfiglib) (ISC, `xt550/kconfiglib.py`), writing `.config` and `include/autoconf.h` in BusyBox's `ENABLE_`/`IF_` format |
| `applets/applet_tables.c`, `applets/usage.c` (+ `usage_compressed`) | `xt550/gen_headers.py` (the cross compiler's preprocessor expands `applets.h`/`usage.h`) |
| `scripts/generate_BUFSIZ.sh`, `scripts/embedded_scripts` | the trivial outputs for this config |
| Kbuild object lists, `Makefile.flags` | `xt550/build.py` |

Configuration choices (bionic android-9):
- `LFS` off: 32-bit `off_t`.
- `USE_BB_PWD_GRP` off: the system `passwd` has no `pw_gecos`.
- `FEATURE_SYNC_FANCY` off: no `syncfs`.
- Usage text uncompressed.

## Patch

`xt550/patches/0001-stat-bionic-timespec.patch` (already applied to
`coreutils/stat.c`): bionic before API 21 has `st_atime` + `st_atime_nsec`,
not `st_atim`. These have the same layout as `struct timespec`, so `stat`
reads them through that type.

## Build

```
sh scripts/gen_build_files.sh . .
python xt550/configure.py .
python xt550/gen_headers.py . <ndk>/toolchains/arm-linux-androideabi-4.9/prebuilt/windows-x86_64/bin/arm-linux-androideabi-gcc.exe
python xt550/build.py . <android-ndk-r10e> out
```

## Tested on the XT550

- The new binary gives the same `sha256sum` and `md5sum` as the old one on the
  same file.
- `find -xdev -perm -4000` lists the same three setuid files.
- `tar` + `gzip` round trip, `cp -a` + `cmp`, `stat -c '%u %a'`, `awk`, `sed`,
  `nc` and `printf` all work.
