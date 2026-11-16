#!/usr/bin/env python
"""Generate busybox's build-time headers without host C programs.

Python ports of applets/applet_tables.c, applets/usage.c (+ usage_compressed),
and the trivial cases of scripts/generate_BUFSIZ.sh and scripts/embedded_scripts.
The C preprocessor of the cross compiler expands include/applets.h and
include/usage.h exactly as the host programs would see them.

usage: gen_headers.py <busybox-src> <path-to-arm-linux-androideabi-gcc>
"""
import ast, os, re, subprocess, sys

SRC, GCC = sys.argv[1], sys.argv[2]
INC = os.path.join(SRC, 'include')


def cpp(text):
    r = subprocess.run([GCC, '-E', '-P', '-x', 'c', '-I', INC, '-'], input=text,
                       capture_output=True, text=True, check=True)
    return r.stdout


def c_strings(s):
    """Concatenate adjacent C string literals into bytes."""
    out = b''
    for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', s, re.S):
        out += ast.literal_eval('b"' + lit.replace('\n', '') + '"')
    return out


def applet_tables(cfg):
    pre = cpp('#include "autoconf.h"\n#define NAME_MAIN 1\n#include "applets.h"\n')
    applets = []
    for line in pre.splitlines():
        t = line.split()
        if len(t) == 2 and t[1].endswith('_main'):
            applets.append((t[0], t[1][:-len('_main')]))
    applets.sort(key=lambda a: a[0].encode())
    names = [a[0] for a in applets]
    if len(set(names)) != len(names):
        raise SystemExit('duplicate applet names')
    n = len(applets)
    known = 8
    if n < 128:
        known = 4
    if n < 32:
        known = 0
    o = ["/* This is a generated file, don't edit */\n", '#define NUM_APPLETS %u' % n]
    if n == 1:
        o.append('#define SINGLE_APPLET_STR "%s"' % names[0])
        o.append('#define SINGLE_APPLET_MAIN %s_main' % applets[0][1])
    o.append('#define KNOWN_APPNAME_OFFSETS %u\n' % known)
    if known:
        index = [i * n // known for i in range(known)]
        offset, ofs = {}, 0
        for i, name in enumerate(names):
            for j in range(known):
                if i == index[j]:
                    offset[j] = ofs
            ofs += len(name) + 1
        o.append('const uint16_t applet_nameofs[] ALIGN2 = {')
        o += ['%d,' % offset[i] for i in range(1, known)]
        o.append('};\n')
    o.append('const char applet_names[] ALIGN1 = ""')
    o += ['"%s" "\\0"' % name for name in names]
    o.append(';\n')
    o += ['#define APPLET_NO_%s %d' % (name, i) for i, name in enumerate(names)
          if re.fullmatch(r'[A-Za-z0-9_]+', name)]
    o.append('')
    o.append('#ifndef SKIP_applet_main')
    o.append('int (*const applet_main[])(int argc, char **argv) = {')
    o += ['%s_main,' % m for _, m in applets]
    o.append('};')
    o.append('#endif\n')
    for flag in ('FEATURE_PREFER_APPLETS', 'FEATURE_SH_STANDALONE', 'FEATURE_SH_NOFORK',
                 'FEATURE_SUID', 'FEATURE_INSTALLER'):
        if cfg.get(flag) == 'y':
            raise SystemExit(flag + ' needs applet flag tables: not supported by this generator')
    open(os.path.join(INC, 'applet_tables.h'), 'w', newline='\n').write('\n'.join(o) + '\n')
    open(os.path.join(INC, 'NUM_APPLETS.h'), 'w', newline='\n').write('#define NUM_APPLETS %u\n' % n)
    return names


def usage(cfg):
    hdr = ('#include "autoconf.h"\n'
           '#if ENABLE_NOMMU\n# define BB_MMU 0\n# define USE_FOR_NOMMU(...) __VA_ARGS__\n# define USE_FOR_MMU(...)\n'
           '#else\n# define BB_MMU 1\n# define USE_FOR_NOMMU(...)\n# define USE_FOR_MMU(...) __VA_ARGS__\n#endif\n'
           '#include "usage.h"\n'
           '#define MAKE_USAGE(aname, usage) @@U aname @@S usage @@E\n'
           '#include "applets.h"\n')
    pre = cpp(hdr)
    items = []
    for m in re.finditer(r'@@U\s*("(?:[^"\\]|\\.)*")\s*@@S(.*?)@@E', pre, re.S):
        items.append((c_strings(m.group(1)), c_strings(m.group(2))))
    items.sort(key=lambda x: x[0])
    blob = b''.join(u + b'\0' for _, u in items)
    lines = ['#define UNPACKED_USAGE "" \\']
    for i in range(0, len(blob), 16):
        lines.append('"' + ''.join('\\%03o' % b for b in blob[i:i + 16]) + '" \\')
    lines.append('')
    lines.append('#define UNPACKED_USAGE_LENGTH %d' % len(blob))
    lines.append('')
    lines.append('#define PACKED_USAGE \\')
    lines.append('')
    open(os.path.join(INC, 'usage_compressed.h'), 'w', newline='\n').write('\n'.join(lines) + '\n')
    return len(items)


def main():
    cfg = dict(re.findall(r'^CONFIG_(\w+)=(.*)$', open(os.path.join(SRC, '.config')).read(), re.M))
    if cfg.get('FEATURE_COMPRESS_USAGE') == 'y':
        raise SystemExit('set FEATURE_COMPRESS_USAGE=n')
    if cfg.get('FEATURE_USE_BSS_TAIL') == 'y':
        raise SystemExit('set FEATURE_USE_BSS_TAIL=n')
    names = applet_tables(cfg)
    nu = usage(cfg)
    open(os.path.join(INC, 'common_bufsiz.h'), 'w', newline='\n').write(
        'enum { COMMON_BUFSIZE = 1024 };\nextern char bb_common_bufsiz1[];\n'
        '#define setup_common_bufsiz() ((void)0)\n')
    open(os.path.join(INC, 'embedded_scripts.h'), 'w', newline='\n').write('#define NUM_SCRIPTS 0\n')
    print(len(names), 'applets:', ' '.join(names))
    print(nu, 'usage texts')


if __name__ == '__main__':
    main()
