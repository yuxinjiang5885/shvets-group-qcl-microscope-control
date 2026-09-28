"""Supervised Prior X +100 um and return check; UI closed, emission off.

No DAQ, homing, zeroing, speed, or acceleration commands. Native SDK calls
cannot be interrupted by the software deadlines; keep independent stop available.
"""

import time

from instruments.hld117 import stage
from experiment.scan_adapters import PriorStageAdapter
from experiment.scan_1d import StageBounds


START = (4918, -23417)
OUTBOUND = (5018, -23417)
BOUNDS = StageBounds(4917, 5019, -23418, -23416,
                     frame_id="prior-x100-validation-current-frame")


def log(message):
    print(message, flush=True)


class GuardedStage(stage):
    def __init__(self):
        self.movement_attempted = False
        self.move_count = 0
        self.return_authorized = False
        super().__init__(model="HLD117")

    def message(self, command, verbose=False):
        moves = (
            "controller.stage.goto-position 5018 -23417",
            "controller.stage.goto-position 4918 -23417",
        )
        allowed = {
            "controller.connect 3", "controller.disconnect",
            "controller.stage.position.get", "controller.stage.busy.get",
        }
        is_move = command in moves
        if is_move:
            if self.move_count >= 2 or command != moves[self.move_count]:
                raise RuntimeError("Blocked repeated or out-of-order move")
            if self.move_count == 1 and not self.return_authorized:
                raise RuntimeError("Return has not been authorized by readback")
        elif command == "controller.stop.smoothly":
            if not self.movement_attempted:
                raise RuntimeError("Blocked stop before any movement attempt")
        elif command not in allowed:
            raise RuntimeError(f"Command blocked: {command}")

        log(f"Sending: {command}")
        if is_move:
            # Set immediately before driver entry, not before adapter validation.
            # An exception/late reply cannot prove the controller rejected a move.
            self.movement_attempted = True
            self.move_count += 1
        status, reply = super().message(command, verbose=verbose)
        log(f"Reply: status={status}, payload={reply!r}")
        if status != 0:
            raise RuntimeError(f"Prior command failed: {status}")
        return status, reply


def remaining(deadline):
    budget = deadline - time.monotonic()
    if budget <= 0:
        raise TimeoutError("Movement/completion/readback deadline expired")
    return budget


def check_position(position, target, *, exact=False):
    log(f"Readback: X={position[0]:g} um, Y={position[1]:g} um")
    if not BOUNDS.contains(position):
        raise RuntimeError("Readback outside test bounds")
    if any(abs(actual - expected) > 1 for actual, expected in zip(position, target)):
        raise RuntimeError(f"Readback outside +/-1 um per axis of {target}")
    if exact and tuple(position) != target:
        raise RuntimeError(f"Strict coordinate gate failed: expected exactly {target}")


def move_and_verify(adapter, target, *, exact=False):
    deadline = time.monotonic() + 5.0
    adapter.move_to(*target, timeout_s=remaining(deadline))
    idle_since = None
    while True:
        busy = adapter.is_busy(timeout_s=remaining(deadline))
        now = time.monotonic()
        remaining(deadline)
        if busy:
            idle_since = None
        elif idle_since is None:
            idle_since = now
        elif now - idle_since >= 0.1:
            break
        time.sleep(min(0.01, remaining(deadline)))
    position = adapter.get_position(timeout_s=remaining(deadline))
    check_position(position, target, exact=exact)
    if adapter.is_busy(timeout_s=remaining(deadline)):
        raise RuntimeError("Stage reported busy after readback")
    remaining(deadline)


def main():
    device = None
    adapter = None
    connection_attempted = False
    stop_attempted = False
    errors = []
    try:
        device = GuardedStage()
        if device.session < 0:
            raise RuntimeError("Prior SDK did not open a valid session")
        adapter = PriorStageAdapter(device, bounds=BOUNDS)
        connection_attempted = True
        device.message("controller.connect 3")
        if adapter.is_busy(timeout_s=2.0):
            raise RuntimeError("Stage initially busy; aborting without movement")
        check_position(adapter.get_position(timeout_s=2.0), START, exact=True)
        move_and_verify(adapter, OUTBOUND, exact=True)
        device.return_authorized = True
        move_and_verify(adapter, START)
        log("Both movement legs and readbacks verified")
    except BaseException as error:
        errors.append(f"{type(error).__name__}: {error}")
        log(f"TEST FAILURE: {errors[-1]}")
        if device is not None and device.movement_attempted:
            stop_attempted = True
            log("Attempting protective smooth stop; no further positioning")
            try:
                adapter.stop(timeout_s=2.0)
                log("Protective stop confirmed idle")
            except BaseException as stop_error:
                errors.append(f"Protective stop failed: {stop_error}")
                log(errors[-1] + "; physical state uncertain, use independent stop")
    finally:
        if device is not None and device.session >= 0:
            try:
                if connection_attempted:
                    device.message("controller.disconnect")
            except BaseException as error:
                errors.append(f"Disconnect failed: {error}")
            finally:
                try:
                    status = device.close_session()
                    log(f"CloseSession status={status}")
                    if status != 0:
                        raise RuntimeError(f"SDK status {status}")
                except BaseException as error:
                    errors.append(f"CloseSession failed: {error}")

    if errors:
        moved = device is not None and device.movement_attempted
        phase = "after a movement attempt" if moved else "before any movement attempt"
        log(f"FAIL {phase}; protective stop attempted: {stop_attempted}")
        for error in errors:
            log(f"  {error}")
        # Cleanup-only failures occur after verified idle and do not send a stop
        # through a disconnected/closed session. They still prevent PASS.
        return 1
    log("PASS: outbound, return, readbacks, disconnect, and session closure completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
