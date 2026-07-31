"""Self-contained report links: the report JSON, gzip+base64url-packed into a URL.

The whole report survives inside the link, so a stateless replica can render any
link on demand with nothing stored server-side. Compression is what makes it fit a
URL — report JSON is highly repetitive and shrinks ~8-12x, so a 20-row report is
under 1 KB encoded. (Percent-encoding, by contrast, *inflates* the JSON and blows
past URL limits; it is the wrong tool here.)

``decode_report`` runs on a PUBLIC endpoint over attacker-supplied input, so three
guards are load-bearing, not hygiene:

* ``MAX_ENCODED`` bounds the work done before we ever touch zlib.
* ``MAX_DECOMPRESSED`` stops a gzip bomb — a few hundred bytes of ``d=`` that would
  otherwise inflate to gigabytes and exhaust the pod's memory.
* ``_verify`` rejects a token that was altered in transit. This one is easy to think
  you get for free and do not: ``zlib.decompressobj`` + ``flush()`` never validates
  the gzip trailer, so a flip in the last few bytes of the deflate stream yields
  plausible-looking garbage with no error raised (measured: ~1% of single-character
  flips). ``gzip.decompress`` does check it, but cannot be used here because it will
  happily inflate a bomb — so the bounded read and the CRC32/ISIZE check are done
  separately and both are required.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import zlib
from typing import Any

__all__ = ["encode_report", "decode_report", "LinkError", "MAX_ENCODED", "MAX_DECOMPRESSED"]

# Reject a `d=` token longer than this before decoding anything. 16 KiB holds a very
# large report comfortably while staying an order of magnitude below any DoS concern.
MAX_ENCODED = 16_384
# Hard ceiling on the decompressed JSON. A real report is a few KB and the tool's own
# URL-length gate keeps emitted links well under this; 128 KiB is generous headroom
# for a large report yet bounds the work a single crafted request can trigger.
MAX_DECOMPRESSED = 131_072

_WBITS_GZIP = 16 + zlib.MAX_WBITS  # select the gzip container when decompressing
_GZIP_TRAILER = 8  # CRC32 (4, little-endian) + ISIZE (4, little-endian, mod 2**32)


class LinkError(ValueError):
    """A report link could not be decoded — missing, malformed, oversized, or altered."""


def encode_report(report_json: str) -> str:
    """Pack a report JSON string into a URL-safe token (gzip, then base64url).

    ``mtime=0`` drops the timestamp so the output is stable for a given build: within
    a deployment (one image, one Python/zlib) the same report yields the same token,
    which makes the link content-addressed and cacheable. The byte layout can differ
    across Python/zlib major versions, but every build decodes every token, so that
    only affects cache-hit rate, never correctness.
    """
    packed = gzip.compress(report_json.encode("utf-8"), mtime=0)
    return base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")


def decode_report(token: str) -> str:
    """Reverse ``encode_report``, enforcing all three guards.

    Raises ``LinkError`` on anything malformed, oversized or corrupted; never raises on
    attacker-controlled input in a way the caller must special-case beyond that.
    """
    if not token:
        raise LinkError("empty report token")
    if len(token) > MAX_ENCODED:
        raise LinkError(f"report token exceeds {MAX_ENCODED} bytes")
    padded = token + "=" * (-len(token) % 4)  # restore stripped base64 padding
    try:
        packed = base64.urlsafe_b64decode(padded)
    except (binascii.Error, ValueError) as exc:
        raise LinkError("report token is not valid base64url") from exc
    return _bounded_gunzip(packed)


def _bounded_gunzip(packed: bytes) -> str:
    """Gunzip ``packed`` refusing to emit more than ``MAX_DECOMPRESSED`` bytes."""
    dec = zlib.decompressobj(wbits=_WBITS_GZIP)
    try:
        # max_length caps the OUTPUT; anything left in unconsumed_tail means the
        # stream would have produced more than the cap — i.e. a bomb.
        out = dec.decompress(packed, MAX_DECOMPRESSED + 1)
        if dec.unconsumed_tail or len(out) > MAX_DECOMPRESSED:
            raise LinkError(f"decompressed report exceeds {MAX_DECOMPRESSED} bytes")
        out += dec.flush()
    except zlib.error as exc:
        raise LinkError("report token is not a valid gzip stream") from exc
    if len(out) > MAX_DECOMPRESSED:
        raise LinkError(f"decompressed report exceeds {MAX_DECOMPRESSED} bytes")
    _verify(packed, out, dec)
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LinkError("decompressed report is not valid UTF-8") from exc


def _verify(packed: bytes, out: bytes, dec: Any) -> None:
    """Reject a stream that did not end cleanly or whose trailer does not match.

    ``flush()`` returns without complaint on a truncated or tail-corrupted stream, so
    neither condition is caught above. ``dec.eof`` reports whether the decompressor
    actually reached end-of-stream; the CRC32/ISIZE comparison catches the rest,
    including bytes appended after an otherwise valid member.
    """
    if not dec.eof:
        raise LinkError("report token is a truncated gzip stream")
    if len(packed) < _GZIP_TRAILER:
        raise LinkError("report token is too short to carry a gzip trailer")
    expected_crc = int.from_bytes(packed[-_GZIP_TRAILER:-4], "little")
    expected_size = int.from_bytes(packed[-4:], "little")
    if zlib.crc32(out) != expected_crc or (len(out) & 0xFFFF_FFFF) != expected_size:
        raise LinkError("report token failed its integrity check (it was altered in transit)")
