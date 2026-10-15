#!/usr/bin/env python3
"""Follow Arch's telegram-desktop package.

When Arch moves to a new tdesktop release (or changes its PKGBUILD), check
that our patch still applies to the release tarball and regenerate our
PKGBUILD from Arch's, with our changes applied on top.

Writes `result=uptodate|updated|conflict|manual`, `version=...` and, for
`manual`, `reason=...` to $GITHUB_OUTPUT (or prints them when run locally).
"""

import hashlib
import os
import re
import subprocess
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
REPO_URL = "https://github.com/iridium/tdesktop-wayland-notifications"
HEADER = """\
# Generated from the Arch Linux telegram-desktop PKGBUILD by
# .github/scripts/check-update.py, edit that script instead.
"""


class Manual(Exception):
    """Arch's PKGBUILD changed in a way we can't adapt to automatically."""


def output(**values):
    lines = "".join(f"{k}={v}\n" for k, v in values.items())
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a") as f:
            f.write(lines)
    print(lines, end="")


def field(pkgbuild, name):
    match = re.search(rf"^{name}=(\S+)$", pkgbuild, re.M)
    if not match:
        raise Manual(f"`{name}` not found in Arch's PKGBUILD")
    return match.group(1).strip("'\"")


def replace(text, pattern, repl, what, flags=re.M):
    result, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise Manual(f"couldn't {what} in Arch's PKGBUILD")
    return result


def append_to_array(text, name, item, what):
    # Inserts `item` before the closing parenthesis of `name=(...)`.
    return replace(
        text,
        rf"^({name}=\((?:[^()]|\([^()]*\))*?)\)",
        lambda m: m.group(1).rstrip() + f"\n  {item}\n)",
        what,
        flags=re.M | re.S,
    )


def make_pkgbuild(arch, patch_sum):
    """Applies our changes to Arch's PKGBUILD."""
    text = re.sub(r"\A(?:#.*\n)*\n*", "", arch)
    text = HEADER + "\n" + text
    text = replace(
        text,
        r"^pkgname=telegram-desktop$",
        "pkgname=telegram-desktop-wayland-notifications\n"
        "_pkgname=telegram-desktop",
        "rename the package",
    )
    text = replace(
        text,
        r"^pkgdesc=.*$",
        "pkgdesc='Official Telegram Desktop client, with an LLM-written "
        "patch for Telegram-style notifications on Wayland'",
        "set pkgdesc",
    )
    text = replace(text, r"^url=.*$", f'url="{REPO_URL}"', "set url")
    for dep in ("'layer-shell-qt'", "'wayland'"):
        text = append_to_array(text, "depends", dep, f"add {dep} to depends")
    text = replace(
        text,
        r"^(optdepends=\()",
        'provides=("${_pkgname}=${pkgver}")\n'
        'conflicts=("${_pkgname}")\n\\1',
        "add provides and conflicts",
    )
    text = append_to_array(
        text, "source", f'"{PATCH}"', "add the patch to source"
    )
    text = replace(
        text,
        r"^(sha512sums=\((?:[^()])*?)\)",
        lambda m: m.group(1) + f"\n            '{patch_sum}')",
        "add the patch checksum",
        flags=re.M | re.S,
    )
    apply = (
        '  patch -Np1 -d "tdesktop-${pkgver}-full" '
        f'-i "${{srcdir}}/{PATCH}"\n'
    )
    if re.search(r"^prepare\(\) \{$", text, re.M):
        # First, before Arch's prepare() changes directories.
        text = replace(
            text,
            r"^prepare\(\) \{\n",
            lambda m: m.group(0) + apply + "\n",
            "add the patch to prepare()",
        )
    else:
        text = replace(
            text,
            r"^build\(\) \{$",
            "prepare() {\n" + apply + "}\n\nbuild() {",
            "add prepare()",
        )

    # Sanity check: as many checksums as sources.
    sources = re.search(r"^source=\((.*?)^\)", text, re.M | re.S).group(1)
    sums = re.search(r"^sha512sums=\((.*?)\)", text, re.M | re.S).group(1)
    source_count = len(
        [line for line in sources.splitlines()
         if line.strip() and not line.strip().startswith("#")]
    )
    sum_count = len(re.findall(r"'(?:[0-9a-f]{128}|SKIP)'", sums))
    if source_count != sum_count:
        raise Manual(
            f"{source_count} sources but {sum_count} checksums after "
            "applying our changes"
        )
    return text


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
    with open(PATCH, "rb") as f:
        patch_sum = hashlib.sha512(f.read()).hexdigest()

    version = "unknown"
    try:
        version = field(arch, "pkgver")
        updated = make_pkgbuild(arch, patch_sum)
    except Manual as e:
        output(result="manual", version=version, reason=str(e))
        return
    if updated == ours:
        output(result="uptodate", version=version)
        return

    old_version = re.search(r"^pkgver=(\S+)$", ours, re.M)
    if (not old_version or old_version.group(1) != version) and (
        not patch_applies(version)
    ):
        output(result="conflict", version=version)
        return

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
