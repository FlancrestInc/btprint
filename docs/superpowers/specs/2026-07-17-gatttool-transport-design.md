# CTP500 direct LE GATT transport design

## Goal

Print on this Linux host despite BlueZ choosing the printer's Classic SPP
profile when Bleak requests a GATT connection.

## Decision

Keep the proven `ctp500_ble` frames unchanged. Replace the Bleak connection
layer with one persistent BlueZ `gatttool` interactive session, which has
already completed direct LE GATT service discovery on this host.

Host evidence from `gatttool -i hci0 -b 20:DC:8B:CD:CA:C0 -t public
--characteristics`: AE01 is characteristic `0x0005`, has property `0x04`
(write without response), and its value handle is `0x0006`.

## Transport flow

1. Start `gatttool -i hci0 -b ADDRESS -t public -m 247 -I` with a pseudo
   terminal.
2. Send `connect` and wait up to 15 seconds for `Connection successful`.
3. For every existing BLE frame, write
   `char-write-cmd 0x0006 HEX_FRAME\n` to the session. Handle `0x0006` is the
   write-without-response value handle for the proven AE01 characteristic.
4. Sleep 30 ms after every frame, exactly as before.
5. On success or failure, send `quit`, then terminate and wait for the child
   process if it remains alive.

## Boundaries

- Put pseudo-terminal session management in a new `ctp500_gatttool` module.
- Keep protocol construction in `ctp500_ble.py` and the CLI boundary in
  `print.py`.
- Replace the Bleak dependency and all asynchronous transport code. The new
  runtime dependency is BlueZ's `gatttool`; Pillow remains required. Update
  the existing README to state that `gatttool` must be installed, the adapter
  is `hci0`, and the printer uses a public BLE address. Remove Bleak setup.
- Preserve the `image [mac]`, `--dither`, and `--dry-run` CLI behavior.
- Convert missing `gatttool`, connection timeout/failure, closed process, and
  command-write failures into concise `parser.error` messages.

## Verification

Unit-test the exact child-process arguments, `connect` handshake, AE01 handle
commands, frame hex encoding, 30 ms pacing, connection timeout, child failure,
and reliable cleanup. The reader must tolerate terminal echo and prompts while
waiting for `Connection successful`, and fail immediately on EOF or child exit.
Each frame succeeds only when its full command is written to the PTY; do not
wait for a response to a write-without-response command. Cleanup is bounded:
attempt `quit`, wait, terminate and wait, then kill and wait; close both PTY
file descriptors, and preserve the original operation error if cleanup fails.
Test early exit, EOF, partial/broken command writes, failed quit, termination
timeout/kill, and original-error preservation. Test that every frame from
`build_print_frames` is emitted unchanged, once, and in order as
`char-write-cmd 0x0006 HEX`, with one 30 ms delay per frame. Mock the session
at the CLI boundary. Preserve all frame/image/dry-run tests, including that a
dry run imports no transport and launches no child. The PTY writer loops until
all command bytes are written, retrying interrupted writes; any zero-byte or
other broken write is a terminal transport failure. Add a missing-executable
`FileNotFoundError` regression test that becomes a concise parser error, and
assert dry run invokes neither subprocess nor `gatttool`. Then run the asymmetric
hardware smoke test with the printer powered on.
