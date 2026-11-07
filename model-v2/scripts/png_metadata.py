"""Read PNG text metadata and remove only text chunks, preserving other bytes."""
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
TEXT_TYPES = {b"tEXt", b"zTXt", b"iTXt"}


def chunks(data):
    if not data.startswith(SIGNATURE):
        raise ValueError("Invalid PNG signature")
    offset = len(SIGNATURE)
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("Truncated PNG chunk")
        size = struct.unpack_from(">I", data, offset)[0]
        end = offset + size + 12
        if end > len(data):
            raise ValueError("Truncated PNG payload")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:end - 4]
        crc = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError("Invalid PNG chunk CRC")
        yield kind, payload, data[offset:end]
        offset = end
        if kind == b"IEND":
            if offset != len(data):
                raise ValueError("Unexpected data after PNG IEND")
            return
    raise ValueError("PNG IEND missing")


def text_fields(data):
    fields = []
    for kind, payload, _ in chunks(data):
        if kind not in TEXT_TYPES:
            continue
        keyword, content = payload.split(b"\0", 1)
        if not 1 <= len(keyword) <= 79:
            raise ValueError("Invalid PNG text keyword")
        if kind == b"zTXt":
            if not content or content[0] != 0:
                raise ValueError("Invalid PNG text compression method")
            content = zlib.decompress(content[1:])
        elif kind == b"iTXt":
            if len(content) < 2 or content[0] not in (0, 1) or content[1] != 0:
                raise ValueError("Invalid PNG international text compression")
            compressed = content[0]
            language, translated, content = content[2:].split(b"\0", 2)
            content = zlib.decompress(content) if compressed else content
            fields.append((kind, keyword + b"\0" + language + b"\0" + translated, content))
            continue
        fields.append((kind, keyword, content))
    return fields


def private_text_fields(data, markers):
    return [(kind, keyword) for kind, keyword, content in text_fields(data)
            if any(marker in keyword or marker in content for marker in markers)]


def strip_text(data):
    # Fully parse first so malformed input cannot be partially rewritten.
    parsed = list(chunks(data))
    return SIGNATURE + b"".join(raw for kind, _, raw in parsed if kind not in TEXT_TYPES)
