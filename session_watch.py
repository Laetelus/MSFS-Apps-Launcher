"""Wait for an MSFS flight to be ready, using SimConnect's CAMERA STATE.

Public API:
    start_session_watch(sim_is_running, fallback_seconds=180) -> threading.Event
        Starts a background thread and returns an Event that is set once a
        flight is ready (or when the fallback kicks in, see below).

"Ready" means CAMERA STATE has stayed in a flight value for HOLD_POLLS polls
in a row. Menus, the world map and loading screens use other values.

Fallback: if SimConnect cannot be used at all (library missing, never
connects, or never returns a camera state) for fallback_seconds, the Event is
set anyway so apps are not held back forever.

The SimConnect library is imported lazily, so the launcher still runs if it
is not installed.
"""
import logging
import threading
import time

log = logging.getLogger("launcher")

# Observed on MSFS 2024: 2 = cockpit, 5 = fixed external view. 3 (external
# chase), 4 (drone) and 7 (six degrees of freedom) are listed as flight views
# in community notes and have not all been verified here.
FLIGHT_STATES = {2, 3, 4, 5, 7}
HOLD_POLLS = 5            # consecutive polls in a flight state before "ready"
POLL_SECONDS = 1.0
RECONNECT_AFTER = 10      # consecutive bad reads before reconnecting


def _try_connect():
    from SimConnect import SimConnect, AircraftRequests
    sm = SimConnect()
    aq = AircraftRequests(sm, _time=500)
    # CAMERA STATE is not in the library's built-in list, so add it.
    aq.PositionandSpeedData.list["CAMERA_STATE"] = [
        "Camera state", b"CAMERA STATE", b"Enum", "N"]
    return sm, aq


def _read(aq):
    try:
        return aq.get("CAMERA_STATE")
    except Exception:
        return None


def _close(sm):
    try:
        if sm is not None:
            sm.exit()
    except Exception:
        pass


def _watch(ready, sim_is_running, fallback_seconds):
    try:
        import SimConnect  # noqa: F401
    except Exception as exc:
        log.info("session watch: SimConnect not available (%s); "
                 "starting session apps now", exc)
        ready.set()
        return

    started = time.time()
    ever_connected = False
    hold = 0
    bad = 0
    last = None
    sm = aq = None

    while sim_is_running():
        if not ever_connected and time.time() - started > fallback_seconds:
            log.info("session watch: could not connect to SimConnect after %ss; "
                     "starting session apps now", fallback_seconds)
            ready.set()
            break

        if aq is None:
            try:
                sm, aq = _try_connect()
                ever_connected = True
                log.info("session watch: connected to SimConnect")
            except Exception:
                time.sleep(2)
                continue

        value = _read(aq)
        if isinstance(value, (int, float)):
            bad = 0
            state = int(value)
            if state != last:
                log.info("session watch: camera state %s", state)
                last = state
            hold = hold + 1 if state in FLIGHT_STATES else 0
            if hold >= HOLD_POLLS:
                log.info("session ready (camera state %s)", state)
                ready.set()
                break
        else:
            hold = 0
            bad += 1
            if bad >= RECONNECT_AFTER:
                _close(sm)
                sm = aq = None
                bad = 0
        time.sleep(POLL_SECONDS)

    _close(sm)


def start_session_watch(sim_is_running, fallback_seconds=180):
    """Start watching in the background. Returns an Event set when ready."""
    ready = threading.Event()
    threading.Thread(
        target=_watch, args=(ready, sim_is_running, fallback_seconds),
        daemon=True).start()
    return ready
