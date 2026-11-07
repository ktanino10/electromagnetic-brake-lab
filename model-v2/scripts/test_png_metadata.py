import struct
import unittest
import zlib

from png_metadata import SIGNATURE, chunks, private_text_fields, strip_text, text_fields


def chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


class PngMetadataTests(unittest.TestCase):
    def test_all_text_encodings_and_unchanged_nontext_chunks(self):
        private = b"/" + b"Users/example/private-scene.blend"
        ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        idat = chunk(b"IDAT", zlib.compress(b"\0\x01\x02\x03\xff"))
        end = chunk(b"IEND", b"")
        metadata = [
            chunk(b"tEXt", b"File\0" + private),
            chunk(b"zTXt", b"File\0\0" + zlib.compress(private)),
            chunk(b"iTXt", b"File\0\0\0ja\0File\0" + private),
            chunk(b"iTXt", b"File\0\1\0ja\0File\0" + zlib.compress(private)),
        ]
        original = SIGNATURE + ihdr + b"".join(metadata) + idat + end
        self.assertEqual(len(text_fields(original)), 4)
        self.assertEqual(len(private_text_fields(original, [b"/" + b"Users/"])), 4)
        stripped = strip_text(original)
        self.assertEqual(stripped, SIGNATURE + ihdr + idat + end)
        self.assertEqual(text_fields(stripped), [])
        self.assertEqual(strip_text(stripped), stripped)

    def test_invalid_crc_truncation_and_compression_fail(self):
        valid = SIGNATURE + chunk(b"IEND", b"")
        for invalid in (valid[:-1], valid[:-1] + b"\1", valid + b"extra", SIGNATURE):
            with self.assertRaises(ValueError):
                list(chunks(invalid))
        malformed = SIGNATURE + chunk(b"zTXt", b"File\0\1payload") + chunk(b"IEND", b"")
        with self.assertRaises(ValueError):
            text_fields(malformed)


if __name__ == "__main__":
    unittest.main()
