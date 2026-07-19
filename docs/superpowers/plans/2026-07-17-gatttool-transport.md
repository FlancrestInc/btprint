# CTP500 Direct GATTTool Transport Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send the proven CTP500 BLE frames through a persistent direct LE gatttool session.

**Architecture:** Keep frames in ctp500_ble.py. Add a PTY-backed ctp500_gatttool module. Keep print.py as the CLI boundary.

**Tech Stack:** Python 3, pty, subprocess, select, BlueZ gatttool, Pillow, unittest.

---

## Chunk 1: Direct GATT session

### Task 1: Implement a PTY-backed session

**Files:** Create ctp500_gatttool.py and tests/test_ctp500_gatttool.py.

- [ ] **Step 1: Write failing tests**

Cover launch arguments gatttool -i hci0 -b MAC -t public -m 247 -I, LF connect handshake, echoed prompts, explicit unsuccessful connection output, AE01 handle 0x0006 commands with unchanged hex frames, output draining and command-failure errors, 30 ms pacing, six-second post-job hold, exit/EOF, timeout, short/interrupted/zero writes, and Popen FileNotFoundError. Test a failed quit write, wait timeout forcing terminate then kill, FD closure, and that cleanup failures never mask the original operation error.

- [ ] **Step 2: Run the focused suite**

Run: python3 -m unittest tests.test_ctp500_gatttool -v

Expected: FAIL because the module is absent.

- [ ] **Step 3: Implement the session**

Use pty.openpty, subprocess.Popen, and select. Wait 15 seconds for Connection successful. Fully write each LF-terminated command, retrying interrupted and short writes, then drain available PTY output without blocking. After the last frame, hold the connection open for six seconds. Raise one transport error for EOF, child exit, timeout, broken write, or gatttool command-error output. Cleanup must try quit, then bounded wait, terminate/wait, kill/wait, and close FDs without masking the active error.

- [ ] **Step 4: Verify the focused suite**

Run: python3 -m unittest tests.test_ctp500_gatttool -v

Expected: PASS.

## Chunk 2: CLI transport

### Task 2: Replace Bleak with GATTTool

**Files:** Modify print.py and tests/test_print_cli.py.

- [ ] **Step 1: Write failing CLI tests**

Replace Bleak tests with mocked GatttoolSession tests. Assert ordered unchanged build_print_frames output, session close, missing gatttool FileNotFoundError parser error, explicit connection-failure parser error, command-write parser error, and dry-run imports neither ctp500_gatttool nor launches a session, subprocess, or gatttool.

- [ ] **Step 2: Run the focused suite**

Run: python3 -m unittest tests.test_print_cli -v

Expected: FAIL because the CLI still uses Bleak.

- [ ] **Step 3: Implement the boundary**

Remove asyncio and Bleak. Construct GatttoolSession(mac), send build_print_frames(prepared), and close in finally. Convert transport errors to parser.error. Keep dry-run before session creation.

- [ ] **Step 4: Verify all code**

Run: python3 -m unittest discover -v and python3 -m py_compile print.py ctp500.py ctp500_ble.py ctp500_gatttool.py

Expected: PASS.

## Chunk 3: Operator docs

### Task 3: Document direct GATT requirements

**Files:** Modify README.md and docs/superpowers/plans/2026-07-17-ble-gatt-printing.md.

- [ ] **Step 1: Update setup**

Remove bleak from the shown pip command. State that gatttool is a system BlueZ executable, not a pip dependency; also state adapter hci0, public BLE address, no pairing, and missing-tool guidance.

- [ ] **Step 2: Supersede the Bleak plan and verify**

Add a top-level supersession note, keep the direct-address smoke command, then rerun the full test/compile command.

- [ ] **Step 3: Run the hardware smoke test**

With the printer powered and nearby, run: python3 print.py ctp500-smoke.png 20:DC:8B:CD:CA:C0. Expected: the asymmetric test pattern prints without a CLI transport error.

## Notes

No usable Git metadata exists. Do not create commits. Run the physical smoke test only after automated checks.
