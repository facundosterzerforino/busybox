#!/usr/bin/env python
"""Compile and link busybox for Android 2.3 (static, armeabi-v7a) with NDK r10e.

Reads the generated Kbuild files to pick the objects enabled in .config
(a small evaluator for the Makefile subset they use), compiles them with the
flags from Makefile.flags, and links a static binary.

usage: build.py <busybox-src> <ndk-r10e> <out-dir>
"""
import concurrent.futures, hashlib, os, pathlib, re, subprocess, sys

SRC, NDK, OUT = [pathlib.Path(a).resolve() for a in sys.argv[1:4]]
DIRS = """applets archival archival/libarchive console-tools coreutils coreutils/libcoreutils
debianutils klibc-utils e2fsprogs editors findutils init libbb libbb/yescrypt libpwdgrp
loginutils mailutils miscutils modutils networking networking/libiproute networking/udhcp
printutils procps runit selinux shell sysklogd util-linux util-linux/volume_id""".split()


def kbuild_objects(cfg):
    objs = []
    for d in DIRS:
        f = SRC / d / 'Kbuild'
        if not f.exists():
            continue
        text = f.read_text().replace('\\\n', ' ')
        var = {'CONFIG_' + k: v for k, v in cfg.items()}
        stack = [True]
        for raw in text.splitlines():
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            m = re.match(r'(ifeq|ifneq)\s*\((.*),(.*)\)$', line)
            if m:
                a = expand(m.group(2).strip(), var)
                b = expand(m.group(3).strip(), var)
                stack.append(stack[-1] and ((a == b) == (m.group(1) == 'ifeq')))
                continue
            if line == 'else':
                stack[-1] = (not stack[-1]) and stack[-2]
                continue
            if line == 'endif':
                stack.pop()
                continue
            if not stack[-1]:
                continue
            m = re.match(r'([^\s:+?=]+)\s*(:=|\+=|=|\?=)\s*(.*)$', line)
            if not m:
                continue
            name = expand(m.group(1), var)
            val = expand(m.group(3), var)
            if m.group(2) == '+=':
                var[name] = (var.get(name, '') + ' ' + val).strip()
            else:
                var[name] = val
        for key in ('lib-y', 'obj-y'):
            for o in var.get(key, '').split():
                if o.endswith('.o'):
                    c = SRC / d / (o[:-2] + '.c')
                    objs.append(c if c.exists() else SRC / d / (o[:-2] + '.S'))
    seen, out = set(), []
    for o in objs:
        if o not in seen:
            seen.add(o)
            out.append(o)
    return out


def expand(s, var):
    for _ in range(10):
        n = re.sub(r'\$\(([^()]+)\)', lambda m: var.get(m.group(1), ''), s)
        if n == s:
            break
        s = n
    return s


def main():
    cfg = dict(re.findall(r'^CONFIG_(\w+)=(.*)$', (SRC / '.config').read_text(), re.M))
    cfg = {k: v.strip('"') for k, v in cfg.items()}
    host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64'
    sfx = '.exe' if os.name == 'nt' else ''
    b = NDK / 'toolchains/arm-linux-androideabi-4.9/prebuilt' / host / 'bin'
    gcc, strip = b / ('arm-linux-androideabi-gcc' + sfx), b / ('arm-linux-androideabi-strip' + sfx)
    sysroot = '--sysroot=' + str(NDK / 'platforms/android-9/arch-arm')
    flags = ['-march=armv7-a', '-mfloat-abi=softfp', '-mthumb', '-Os', '-std=gnu99',
             '-Iinclude', '-Ilibbb', '-include', 'include/autoconf.h',
             '-D_GNU_SOURCE', '-DNDEBUG', '-DBB_VER="1.38.0 xt550"', '-DBB_BT="xt550"',
             '-Wall', '-Wno-format-security', '-Wno-unused-parameter',
             '-finline-limit=0', '-fno-builtin-strlen', '-fomit-frame-pointer',
             '-ffunction-sections', '-fdata-sections', '-fno-guess-branch-probability',
             '-funsigned-char', '-static-libgcc', '-falign-functions=1', '-falign-jumps=1',
             '-falign-labels=1', '-falign-loops=1', '-fno-unwind-tables',
             '-fno-asynchronous-unwind-tables', '-fno-builtin-printf']
    srcs = kbuild_objects(cfg)
    objdir = OUT / 'obj'
    objdir.mkdir(parents=True, exist_ok=True)

    def cc(src):
        rel = src.relative_to(SRC)
        obj = objdir / (str(rel).replace(os.sep, '__').replace('/', '__').rsplit('.', 1)[0] + '.o')
        r = subprocess.run([str(gcc), sysroot, *flags, '-c', str(rel), '-o', str(obj)],
                           cwd=SRC, capture_output=True, text=True)
        return str(rel), r.returncode, r.stderr, obj

    objs, failed = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        for name, rc, err, obj in ex.map(cc, srcs):
            if rc != 0:
                failed.append(name)
                print('--', name, '\n' + '\n'.join(l for l in err.splitlines() if 'error' in l)[:1500])
            objs.append(obj)
    print(len(srcs), 'sources,', len(failed), 'failed')
    if failed:
        raise SystemExit(1)
    exe = OUT / 'busybox'
    r = subprocess.run([str(gcc), sysroot, '-static', '-Wl,--gc-sections', '-Wl,--sort-common',
                        '-Wl,--build-id=none', '-march=armv7-a',
                        '-o', str(exe), *[str(o) for o in objs], '-lm'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-4000:])
        raise SystemExit('link failed')
    subprocess.run([str(strip), '--strip-all', str(exe)], check=True)
    print('busybox:', exe, exe.stat().st_size, 'bytes, SHA256', hashlib.sha256(exe.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
