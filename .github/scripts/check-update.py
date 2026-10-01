#!/usr/bin/env python3
"""Follow Arch's telegram-desktop package version.

When Arch moves to a new tdesktop release (or tdlib commit), download the
release tarball, check that our patch still applies, and update the PKGBUILD.

Writes `result=uptodate|updated|conflict` and `version=...` to
$GITHUB_OUTPUT (or prints them when run locally).
"""

import os
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ARCH_PKGBUILD = (
    "https://gitlab.archlinux.org/archlinux/packaging/packages/"
    "telegram-desktop/-/raw/main/PKGBUILD"
)
TARBALL = (
    "https://github.com/telegramdesktop/tdesktop/releases/download/"
    "v{0}/tdesktop-{0}-full.tar.gz"
)
PATCH = "wayland-notifications.patch"


def output(**values):
    lines = "".join(f"{k}={v}\n" for k, v in values.items())
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a") as f:
            f.write(lines)
    print(lines, end="")


def field(pkgbuild, name):
    match = re.search(rf"^{name}=(\S+)$", pkgbuild, re.M)
    if not match:
        sys.exit(f"{name} not found in PKGBUILD")
    return match.group(1).strip("'\"")


def checksums(pkgbuild):
    match = re.search(r"^sha512sums=\((.*?)\)", pkgbuild, re.M | re.S)
    if not match:
        sys.exit("sha512sums not found in PKGBUILD")
    return re.findall(r"'([0-9a-f]{128}|SKIP)'", match.group(1))


def patch_applies(version):
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "src.tar.gz")
        print(f"Downloading {TARBALL.format(version)}")
        urllib.request.urlretrieve(TARBALL.format(version), archive)
        with tarfile.open(archive) as tar:
            tar.extractall(tmp, filter="tar")
        result = subprocess.run(
            ["patch", "--dry-run", "-Np1", "-i", os.path.abspath(PATCH)],
            cwd=os.path.join(tmp, f"tdesktop-{version}-full"),
            capture_output=True,
            text=True,
        )
        print(result.stdout + result.stderr)
        return result.returncode == 0


def main():
    with urllib.request.urlopen(ARCH_PKGBUILD) as response:
        arch = response.read().decode()
    with open("PKGBUILD") as f:
        ours = f.read()

    version = field(arch, "pkgver")
    commit = field(arch, "_td_commit")
    if (version, commit) == (field(ours, "pkgver"), field(ours, "_td_commit")):
        output(result="uptodate", version=version)
        return

    if not patch_applies(version):
        output(result="conflict", version=version)
        return

    # Arch lists the tarball and tdlib checksums first, our patch is last.
    arch_sums = checksums(arch)
    our_sums = checksums(ours)
    if len(arch_sums) != 2 or len(our_sums) != 3:
        sys.exit("Unexpected sources in PKGBUILD, update it by hand")
    updated = ours
    updated = re.sub(r"^pkgver=.*$", f"pkgver={version}", updated, flags=re.M)
    updated = re.sub(
        r"^_td_commit=.*$", f"_td_commit={commit}", updated, flags=re.M
    )
    updated = re.sub(r"^pkgrel=.*$", "pkgrel=1", updated, flags=re.M)
    for old, new in zip(our_sums[:2], arch_sums):
        updated = updated.replace(f"'{old}'", f"'{new}'")
    with open("PKGBUILD", "w") as f:
        f.write(updated)

    with open("README.md") as f:
        readme = f.read()
    readme = re.sub(r"tdesktop-[0-9.]+-full", f"tdesktop-{version}-full", readme)
    with open("README.md", "w") as f:
        f.write(readme)

    output(result="updated", version=version)


if __name__ == "__main__":
    main()
