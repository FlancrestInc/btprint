# Native RFCOMM transport design

## Goal

Make CTP500 printing work on the host Python runtime without PyBluez.

## Decision

Use Python's built-in Linux Bluetooth socket API. Create an RFCOMM stream socket
with `socket.AF_BLUETOOTH`, `socket.SOCK_STREAM`, and
`socket.BTPROTO_RFCOMM`. Connect it to the supplied MAC address and channel,
then send the complete ESC/POS stream.

## Scope

- Keep image preparation and CTP500 command generation unchanged.
- Keep the existing command-line arguments and automatic paired-device lookup.
- Replace the lazy PyBluez import and `BluetoothSocket` construction in
  `print.py` with a small standard-library transport helper.
- Add `send_rfcomm_stream(mac, channel, stream)`. It receives the printer
  address, RFCOMM channel, and complete byte stream; it owns the socket,
  calls `sendall(stream)`, and closes every socket it creates in `finally`.
- Treat missing `AF_BLUETOOTH` or `BTPROTO_RFCOMM` constants as unsupported
  Python or platform support. Treat socket creation, connection, and send
  errors as transport failures. The CLI reports each as a concise
  `parser.error` message.
- Add `README.md` with setup and smoke-test instructions that require Pillow
  and BlueZ only, not PyBluez. Update the older image-printing plan to mark
  its PyBluez setup and transport instructions superseded by this design.

## Verification

Unit tests will mock `socket.socket` and assert the address family, stream
type, RFCOMM protocol, connection target, exact `sendall(stream)` payload, and
close behavior. They will also cover missing Bluetooth constants plus socket
creation, connection, and send failures; every created socket must close and
the CLI must exit with code 2. Existing renderer and CLI tests must still
pass. A real printer smoke test will use the supplied MAC address directly.
