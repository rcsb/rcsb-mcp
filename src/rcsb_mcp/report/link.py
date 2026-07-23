"""Self-contained report links: the report JSON, gzip+base64url-packed into a URL.

The whole report survives inside the link, so a stateless replica can render any
link on demand with nothing stored server-side. Compression is what makes it fit a
URL — report JSON is highly repetitive and shrinks ~8-12x, so a 20-row report is
under 1 KB encoded. (Percent-encoding, by contrast, *inflates* the JSON and blows
past URL limits; it is the wrong tool here.)

``decode_report`` runs on a PUBLIC endpoint over attacker-supplied input, so the
two size limits below are load-bearing, not hygiene:

* ``MAX_ENCODED`` bounds the work done before we ever touch zlib.
* ``MAX_DECOMPRESSED`` stops a gzip bomb — a few hundred bytes of ``d=`` that would
  otherwise inflate to gigabytes and exhaust the pod's memory.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import zlib

__all__ = ["encode_report", "decode_report", "LinkError", "MAX_ENCODED", "MAX_DECOMPRESSED"]

# Reject a `d=` token longer than this before decoding anything. 16 KiB holds a very
# large report comfortably while staying an order of magnitude below any DoS concern.
MAX_ENCODED = 16_384
# Hard ceiling on the decompressed JSON. A real report is a few KB and the tool's own
# URL-length gate keeps emitted links well under this; 128 KiB is generous headroom
# for a large report yet bounds the work a single crafted request can trigger.
MAX_DECOMPRESSED = 131_072

_WBITS_GZIP = 16 + zlib.MAX_WBITS  # select the gzip container when decompressing


class LinkError(ValueError):
    """A report link could not be decoded — missing, malformed, or over a limit."""


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
    """Reverse ``encode_report``, enforcing both size guards.

    Raises ``LinkError`` on anything malformed or oversized; never raises on
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
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LinkError("decompressed report is not valid UTF-8") from exc
