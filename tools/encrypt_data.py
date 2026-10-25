"""Encrypt data files into an AES-256 zip archive with a passkey of your choice.

The passkey is typed at a hidden prompt (asked twice) and is never stored or printed.

Usage:
  python tools/encrypt_data.py private/pseudonymised/srs_gpr_raw.xlsx -o release/srs_gpr_data.zip
  python tools/encrypt_data.py private/pseudonymised/srs_gpr_clean.xlsx -o release/srs_gpr_clean.zip

Students open the archive in the notebook with the same passkey.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

import pyzipper

MIN_LENGTH = 8


def encrypt(files: list[Path], out: Path, passkey: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    with pyzipper.AESZipFile(out, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as z:
        z.setpassword(passkey.encode("utf-8"))
        z.setencryption(pyzipper.WZ_AES, nbits=256)
        for f in files:
            z.write(f, arcname=f.name)

    # Check: every file reads back with the passkey, and the archive is really encrypted
    with pyzipper.AESZipFile(out) as z:
        z.setpassword(passkey.encode("utf-8"))
        bad = z.testzip()
        if bad is not None:
            raise RuntimeError(f"Archive check failed on {bad}")
        if not all(info.flag_bits & 0x1 for info in z.infolist()):
            raise RuntimeError("Archive is not encrypted")


def ask_passkey() -> str:
    first = getpass.getpass("Passkey: ")
    if len(first) < MIN_LENGTH:
        sys.exit(f"Passkey must be at least {MIN_LENGTH} characters.")
    if getpass.getpass("Repeat passkey: ") != first:
        sys.exit("Passkeys do not match.")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path, help="files to put in the archive")
    parser.add_argument("-o", "--output", type=Path, required=True, help="output .zip path")
    args = parser.parse_args()

    missing = [str(f) for f in args.files if not f.is_file()]
    if missing:
        sys.exit(f"File not found: {', '.join(missing)}")

    encrypt(args.files, args.output, ask_passkey())
    size_mb = args.output.stat().st_size / 1e6
    print(f"Wrote {args.output} ({size_mb:.1f} MB): {', '.join(f.name for f in args.files)}")


if __name__ == "__main__":
    main()
