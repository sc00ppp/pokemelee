"""
observe.py -- watch a running Slippi Melee for crashes/hangs while a mod is
loaded, reading live state from RAM. Boot a modded ISO, get into a match, and
have the Observer tell you objectively whether the mod ran or crashed.

Ported from tools/ingame/nucleus/observe.py: the Observer class is identical (the
crash/hang verdict logic is the validated core). The dev CLI main() and
capture_diagnostics (which shelled out to `node control.js shot`) are dropped --
screenshots are taken by the runner via screenshot.py (stdlib ctypes + PIL).

Crash/hang signals (most reliable first):
  - process death            -> CRASH
  - MEM1 / GALE01 gone        -> CRASH
  - frame counter frozen      -> HANG
  - left in-game unexpectedly -> ENDED (soft crash to menu)

Scene state (Melee 1.02): major 0x80479D30 == 0x02 in VS mode; in-match substate
0x80479D33 == 0x02 in-game (0x00 = character select). Frame counter 0x80479D60.
"""

import json

import time

SCENE_MAJOR = 0x80479D30

SCENE_SUBSTATE = 0x80479D33

FRAME_COUNTER = 0x80479D60

def is_in_game(d):
    """True when the VS in-match scene is up (major 0x02 / substate 0x02)."""
    return d.u8(SCENE_MAJOR) == 0x02 and d.u8(SCENE_SUBSTATE) == 0x02

def wait_in_game(d, timeout=30.0, poll=0.1, log=None):
    """Block until the match is actually IN-GAME, then return True. This absorbs
    host-variable stage LOAD time: a slower machine simply spends longer on the
    black load screen, and we wait for the real scene flag instead of guessing
    with a fixed sleep. Returns False on timeout or if Dolphin dies."""
    start = time.time()
    while time.time() - start < timeout:
        if not d.alive():
            return False
        if is_in_game(d):
            if log:
                log(f"in-game after {time.time() - start:.1f}s")
            return True
        time.sleep(poll)
    return is_in_game(d)

def wait_game_frames(d, frames, fps_floor=10.0, poll=0.02, log=None):
    """Observe every requested game frame, with a bounded inactivity deadline.

    Concurrent emulators can advance below the assumed throughput without
    hanging. The old total wall-clock deadline rejected those healthy loads.
    Keep the same safety budget, renewed ONLY by an observed counter advance;
    a stopped/unreadable counter or dead process still fails. Counter resets
    start the requested interval again, and an absolute bound prevents endless
    scene changes from renewing the wait forever.
    """
    frames = max(0, int(frames))
    if not frames:
        return True
    timeout = max(2.0, frames / max(1.0, fps_floor) + 2.0)
    start = time.monotonic()
    deadline = start + timeout
    absolute = start + (frames + 1) * timeout
    f0 = last = d.u32(FRAME_COUNTER)
    if f0 is None:
        if log:
            log(f"wait_game_frames({frames}) failed: counter unreadable")
        return False
    reason = 'counter made no progress within the safety budget'
    while time.monotonic() < min(deadline, absolute):
        if not d.alive():
            reason = 'process exited'
            break
        f = d.u32(FRAME_COUNTER)
        if f is not None:
            if f < last:
                # A scene flip invalidates the previous interval. The reset
                # itself does not count as forward progress or renew a budget.
                f0 = f
            elif f > last:
                deadline = time.monotonic() + timeout
            last = f
            if f - f0 >= frames:
                elapsed = time.monotonic() - start
                if log and elapsed > timeout:
                    log(f"wait_game_frames({frames}) observed {f-f0} frames in {elapsed:.2f}s; slow progress retained")
                return True
        time.sleep(poll)
    else:
        if time.monotonic() >= absolute:
            reason = 'absolute scene-reset bound reached'
    if log:
        log(f"wait_game_frames({frames}) failed after {time.monotonic()-start:.2f}s: "
            f"{reason}; start={f0}, last={last}")
    return False
