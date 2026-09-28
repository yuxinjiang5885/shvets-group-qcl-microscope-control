"""Read-only PriorStageAdapter hardware check. UI must be closed."""

from instruments.hld117 import stage
from experiment.scan_adapters import PriorStageAdapter
from experiment.scan_1d import StageBounds


class ReadOnlyStage(stage):
    # Reject any command outside this test's explicit connection/read scope.
    def message(self, command, verbose=False):
        allowed = {
            "controller.connect 3",
            "controller.stage.position.get",
            "controller.stage.busy.get",
            "controller.disconnect",
        }
        if command not in allowed:
            raise RuntimeError(f"Command blocked: {command}")
        status, reply = super().message(command, verbose=verbose)
        print(f"{command}: status={status}, reply={reply!r}", flush=True)
        if status != 0:
            raise RuntimeError(f"Prior command failed: {status}")
        return status, reply


def main():
    device = ReadOnlyStage(model="HLD117")
    if device.session < 0:
        raise RuntimeError("Prior SDK did not open a valid session")

    try:
        device.message("controller.connect 3")

        # Required constructor metadata only, not validated travel bounds.
        # Movement commands are blocked independently by ReadOnlyStage.
        bounds = StageBounds(
            4918, 4918, -23417, -23417,
            frame_id="readonly-current-controller-frame",
        )
        adapter = PriorStageAdapter(device, bounds=bounds)

        busy = adapter.is_busy(timeout_s=2.0)
        print(f"Adapter busy: {busy}", flush=True)
        if busy:
            raise RuntimeError("Expected stationary stage; ending test")

        x, y = adapter.get_position(timeout_s=2.0)
        print(f"Adapter position: X={x:g} um, Y={y:g} um", flush=True)

        if adapter.is_busy(timeout_s=2.0):
            raise RuntimeError("Stage reported busy after position read")

        # Comparison allowance for the UI's whole-micrometer display;
        # this is not a calibrated positioning tolerance.
        if abs(x - 4918) > 1 or abs(y + 23417) > 1:
            raise RuntimeError("Position differs from recorded UI baseline")
    finally:
        try:
            device.message("controller.disconnect")
        finally:
            status = device.close_session()
            print(f"CloseSession status={status}", flush=True)
            if status != 0:
                raise RuntimeError("Prior SDK session cleanup failed")

    print("PASS: read-only adapter check and cleanup completed", flush=True)


if __name__ == "__main__":
    main()
