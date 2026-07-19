"""Extract CTP500 write frames from an Apple PacketLogger capture."""

from pathlib import Path


def extract_write_frames(path):
    """Return printer frames from a binary ``.pklg`` capture.

    PacketLogger stores records as a big-endian payload length followed by an
    eight-byte timestamp and packet metadata.  0x0241 records are host-to-
    device ATT traffic.  The printer protocol frames carry their own little-
    endian payload length, so they can be recovered without guessing packet
    boundaries.
    """
    data = Path(path).read_bytes()
    # Older captures use big-endian lengths after a 1000-byte header. Newer
    # iOS captures start at byte zero and use little-endian lengths.
    little_length = int.from_bytes(data[:4], "little")
    big_length = int.from_bytes(data[:4], "big")
    if 8 <= little_length <= 5000 and little_length + 4 <= len(data):
        offset, byteorder, host_types = 0, "little", {b"\x02\x5f"}
    else:
        offset, byteorder, host_types = 1000, "big", {b"\x02\x41"}
    frames = []
    while offset + 4 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], byteorder)
        end = offset + 4 + length
        if length < 8 or length > 5000 or end > len(data):
            break
        record = data[offset + 4 : end]
        if len(record) >= 10 and record[8:10] in host_types:
            cursor = 0
            while True:
                start = record.find(b"\x51\x78", cursor)
                if start < 0:
                    break
                if start + 6 > len(record):
                    break
                payload_length = int.from_bytes(
                    record[start + 4 : start + 6], "little"
                )
                frame_end = start + 8 + payload_length
                if frame_end <= len(record) and record[frame_end - 1] == 0xFF:
                    frames.append(record[start:frame_end])
                    cursor = frame_end
                else:
                    cursor = start + 2
        offset = end
    if not frames:
        raise ValueError("no CTP500 write frames found in PacketLogger capture")
    return frames
