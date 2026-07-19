# Native RFCOMM Transport Implementation Plan

> **Superseded transport note:**
> `docs/superpowers/plans/2026-07-17-ble-gatt-printing.md` supersedes this
> plan's runtime transport. BLE/GATT replaces its Bluetooth Classic RFCOMM and
> BlueZ transport instructions.

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send CTP500 print streams through Python's built-in Linux RFCOMM socket instead of PyBluez.

**Architecture:** Keep image preparation and stream construction in `ctp500.py`. Make `print.py` own a small standard-library transport helper that opens, uses, and always closes an RFCOMM socket. The CLI remains the error-reporting boundary.

**Tech Stack:** Python 3 standard-library `socket`, Pillow, BlueZ, unittest.

---

## Chunk 1: Test and replace the transport

### Task 1: Specify native RFCOMM behavior

**Files:**
- Modify: `tests/test_print_cli.py`
- Modify: `print.py`

- [ ] **Step 1: Write failing unit tests**

Add a test named `test_send_rfcomm_stream_connects_sends_and_closes` for a new
`send_rfcomm_stream(mac, channel, stream)` helper. Mock
`print_cli.socket.socket` and assert it is called with
`socket.AF_BLUETOOTH`, `socket.SOCK_STREAM`, and `socket.BTPROTO_RFCOMM`; that
the created socket connects to `(mac, channel)`; calls `sendall` with the exact
bytes; and closes. Add tests showing an existing socket closes when `connect`
or `sendall` raises `OSError`, and that socket-construction errors propagate.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `python3 -m unittest tests.test_print_cli.PrintCliTests.test_send_rfcomm_stream_connects_sends_and_closes -v`

Expected: FAIL because `send_rfcomm_stream` does not exist.

- [ ] **Step 3: Implement the minimal helper**

Import `socket`. Implement `send_rfcomm_stream` with
`socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)`;
call `connect((mac, channel))` and `sendall(stream)` in a `try` block; call
`close()` in `finally`.

- [ ] **Step 4: Replace the PyBluez call site**

In `main`, build the stream, then call `send_rfcomm_stream(mac, args.channel,
stream)`. Remove the PyBluez import and `BluetoothSocket` code. Do not change
the transport exception handler in this task.

- [ ] **Step 5: Run focused tests to verify they pass**

Run: `python3 -m unittest tests.test_print_cli -v`

Expected: PASS.

### Task 2: Add unsupported-platform regression coverage

**Files:**
- Modify: `tests/test_print_cli.py`
- Modify: `print.py`

- [ ] **Step 1: Write a failing CLI test**

Add helper-level tests that temporarily remove `AF_BLUETOOTH` and
`BTPROTO_RFCOMM`, separately, and verify that `send_rfcomm_stream` raises
`AttributeError`. Add four CLI tests that mock `send_rfcomm_stream` to raise,
respectively, `AttributeError("AF_BLUETOOTH")`, socket-construction `OSError`,
connection `OSError`, and send `OSError`. Each calls `main` with an explicit
MAC and a temporary valid image, then asserts exit code 2 and the error text
on stderr.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python3 -m unittest tests.test_print_cli.PrintCliTests.test_main_reports_missing_native_bluetooth_support -v`

Expected: FAIL because `AttributeError` is not handled.

- [ ] **Step 3: Add minimal error handling**

Include `AttributeError` in the existing transport exception tuple so the CLI
uses `parser.error` rather than emitting a traceback. This handler must also
continue to cover all socket `OSError` cases.

- [ ] **Step 4: Run the full test and syntax suite**

Run: `python3 -m unittest discover -v && python3 -m py_compile print.py ctp500.py`

Expected: all tests pass and compilation produces no output.

## Chunk 2: Operator documentation and hardware check

### Task 3: Document the dependency-free transport

**Files:**
- Create: `README.md`
- Modify: `docs/superpowers/plans/2026-07-16-ctp500-image-printing.md`

- [ ] **Step 1: Write README setup and print instructions**

State that the tool needs Pillow and BlueZ; do not mention PyBluez. Document
both an explicit-MAC command and automatic lookup. Include `--dither`,
`--dry-run`, and the asymmetric smoke-test command.

- [ ] **Step 2: Mark the old PyBluez plan superseded**

Add a brief top-level note to the older plan that PyBluez transport and setup
steps are superseded by this native RFCOMM plan.

- [ ] **Step 3: Re-run verification**

Run: `python3 -m unittest discover -v && python3 -m py_compile print.py ctp500.py`

Expected: all tests pass and compilation produces no output.

- [ ] **Step 4: Run the host smoke test**

On the Bluetooth-capable host with the printer awake, run:

```bash
python3 print.py ctp500-smoke.png 20:DC:8B:CD:CA:C0
```

Expected: the asymmetric pattern prints without a Python traceback.

## Notes

This workspace has no Git metadata. Do not create commits; report that
limitation in the handoff.
