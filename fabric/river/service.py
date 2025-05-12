import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from fabric.core.service import Property, Service, Signal
from fabric.utils.helpers import idle_add
from gi.repository import GLib
from loguru import logger

# Import pywayland components - ensure these imports are correct
from pywayland.client import Display
from pywayland.protocol.wayland import WlOutput, WlSeat

from .protocols.generated.river_control_unstable_v1 import ZriverControlV1
from .protocols.generated.river_status_unstable_v1 import ZriverStatusManagerV1


@dataclass
class OutputInfo:
    """Information about a River output"""

    name: int
    output: WlOutput
    status: Any = None  # ZriverOutputStatusV1
    tags_view: List[int] = field(default_factory=list)
    tags_focused: List[int] = field(default_factory=list)
    tags_urgent: List[int] = field(default_factory=list)


@dataclass(frozen=True)
class RiverEvent:
    """Event data from River compositor"""

    name: str
    data: List[Any]
    output_id: Optional[int] = None


class River(Service):
    """Connection to River Wayland compositor via river-status protocol"""

    @Property(bool, "readable", "is-ready", default_value=False)
    def ready(self) -> bool:
        return self._ready

    @Property(str, "readable", "active-window", default_value="")
    def active_window(self) -> str:
        """Get the title of the currently active window"""
        return self._active_window_title

    @Signal
    def ready_signal(self):
        return self.notify("ready")

    @Signal("event", flags="detailed")
    def event(self, event: object): ...

    def __init__(self, **kwargs):
        """Initialize the River service"""
        super().__init__(**kwargs)
        self._ready = False
        self._active_window_title = ""
        self.outputs: Dict[int, OutputInfo] = {}
        self.river_status_mgr = None
        self.river_control = None
        self.seat = None
        self.seat_status = None

        # Start the connection in a separate thread
        self.river_thread = GLib.Thread.new(
            "river-status-service", self._river_connection_task
        )

    def _river_connection_task(self):
        """Main thread that connects to River and listens for events"""
        try:
            logger.info("[RiverService] Starting connection to River")

            logger.debug(
                f"[RiverService] XDG_RUNTIME_DIR={os.environ.get('XDG_RUNTIME_DIR', 'Not set')}"
            )
            logger.debug(
                f"[RiverService] WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY', 'Not set')}"
            )

            display = Display()
            display.connect()
            logger.debug("[RiverService] Display connection created")

            # Get the registry
            registry = display.get_registry()
            logger.debug("[RiverService] Registry obtained")

            # Create state object to hold our data
            state = {
                "display": display,
                "registry": registry,
                "outputs": {},
                "river_status_mgr": None,
                "river_control": None,
                "seat": None,
                "seat_status": None,
            }

            def handle_global(registry, name, iface, version):
                logger.debug(
                    f"[RiverService] Global: {iface} (v{version}, name={name})"
                )
                if iface == "zriver_status_manager_v1":
                    state["river_status_mgr"] = registry.bind(
                        name, ZriverStatusManagerV1, version
                    )
                    logger.info("[RiverService] Found river status manager")
                elif iface == "zriver_control_v1":
                    state["river_control"] = registry.bind(
                        name, ZriverControlV1, version
                    )
                    logger.info("[RiverService] Found river control interface")
                elif iface == "wl_output":
                    output = registry.bind(name, WlOutput, version)
                    state["outputs"][name] = OutputInfo(name=name, output=output)
                    logger.info(f"[RiverService] Found output {name}")
                elif iface == "wl_seat":
                    state["seat"] = registry.bind(name, WlSeat, version)
                    logger.info("[RiverService] Found seat")

            def handle_global_remove(registry, name):
                if name in state["outputs"]:
                    logger.info(f"[RiverService] Output {name} removed")
                    del state["outputs"][name]
                    idle_add(
                        lambda: self.emit(
                            "event::output_removed",
                            RiverEvent("output_removed", [name]),
                        )
                    )

            # Set up the dispatchers
            registry.dispatcher["global"] = handle_global
            registry.dispatcher["global_remove"] = handle_global_remove

            # Discover globals
            logger.debug("[RiverService] Performing initial roundtrip")
            display.roundtrip()

            # Check if we found the river status manager
            if not state["river_status_mgr"]:
                logger.error("[RiverService] River status manager not found")
                return

                # Handle the window title updates through seat status

            if not state["river_control"]:
                logger.error(
                    "[RiverService] River control interface not found - falling back to riverctl"
                )
                # You could still fall back to the old riverctl method here if needed

            def focused_view_handler(_, title):
                logger.debug(f"[RiverService] Focused view title: {title}")
                self._active_window_title = title
                idle_add(lambda: self._emit_active_window(title))

                # Get the seat status to track active window

            if state["seat"]:
                seat_status = state["river_status_mgr"].get_river_seat_status(
                    state["seat"]
                )
                seat_status.dispatcher["focused_view"] = focused_view_handler
                state["seat_status"] = seat_status
                logger.info("[RiverService] Set up seat status for window tracking")

            # Create view tags and focused tags handlers
            def make_view_tags_handler(output_id):
                def handler(_, tags):
                    decoded = self._decode_bitfields(tags)
                    state["outputs"][output_id].tags_view = decoded
                    logger.debug(
                        f"[RiverService] Output {output_id} view tags: {decoded}"
                    )
                    idle_add(lambda: self._emit_view_tags(output_id, decoded))

                return handler

            def make_focused_tags_handler(output_id):
                def handler(_, tags):
                    decoded = self._decode_bitfields(tags)
                    state["outputs"][output_id].tags_focused = decoded
                    logger.debug(
                        f"[RiverService] Output {output_id} focused tags: {decoded}"
                    )
                    idle_add(lambda: self._emit_focused_tags(output_id, decoded))

                return handler

            def make_urgent_tags_handler(output_id):
                def handler(_, tags):
                    decoded = self._decode_bitfields(tags)
                    state["outputs"][output_id].tags_urgent = decoded
                    logger.debug(
                        f"[RiverService] Output {output_id} urgent tags: {decoded}"
                    )
                    idle_add(lambda: self._emit_urgent_tags(output_id, decoded))

                return handler

            # Bind output status listeners
            for name, info in list(state["outputs"].items()):
                status = state["river_status_mgr"].get_river_output_status(info.output)
                status.dispatcher["view_tags"] = make_view_tags_handler(name)
                status.dispatcher["focused_tags"] = make_focused_tags_handler(name)
                status.dispatcher["urgent_tags"] = make_urgent_tags_handler(name)
                info.status = status
                logger.info(f"[RiverService] Set up status for output {name}")

            # Initial data fetch
            logger.debug("[RiverService] Performing second roundtrip")
            display.roundtrip()

            # Update our outputs dictionary
            self.outputs.update(state["outputs"])
            self.river_status_mgr = state["river_status_mgr"]
            self.river_control = state["river_control"]
            self.seat = state["seat"]
            self.seat_status = state.get("seat_status")
            self._display = display

            # Mark service as ready
            idle_add(self._set_ready)

            # Main event loop
            logger.info("[RiverService] Entering main event loop")
            while True:
                display.dispatch(block=True)
                time.sleep(0.01)  # Small sleep to prevent CPU spinning

        except Exception as e:
            logger.error(f"[RiverService] Error in River connection: {e}")
            import traceback

            logger.error(traceback.format_exc())

        return True

    def _set_ready(self):
        """Set the service as ready (called on main thread via idle_add)"""
        self._ready = True
        logger.info("[RiverService] Service ready")
        self.ready_signal.emit()
        return False  # Don't repeat

    def _emit_view_tags(self, output_id, tags):
        """Emit view_tags events (called on main thread)"""
        event = RiverEvent("view_tags", tags, output_id)
        self.emit("event::view_tags", event)
        self.emit(f"event::view_tags::{output_id}", tags)
        return False  # Don't repeat

    def _emit_focused_tags(self, output_id, tags):
        """Emit focused_tags events (called on main thread)"""
        event = RiverEvent("focused_tags", tags, output_id)
        self.emit("event::focused_tags", event)
        self.emit(f"event::focused_tags::{output_id}", tags)
        return False  # Don't repeat

    def _emit_active_window(self, title):
        """Emit active window title events (called on main thread)"""
        event = RiverEvent("active_window", [title])
        self.emit("event::active_window", event)
        self.notify("active-window")
        return False  # Don't repeat

    def _emit_urgent_tags(self, output_id, tags):
        """Emit urgent_tags events (called on main thread)"""
        event = RiverEvent("urgent_tags", tags, output_id)
        self.emit("event::urgent_tags", event)
        self.emit(f"event::urgent_tags::{output_id}", tags)
        return False  # Don't repeat

    @staticmethod
    def _decode_bitfields(bitfields) -> List[int]:
        """Decode River's tag bitfields into a list of tag indices"""
        tags: Set[int] = set()

        # Ensure we have an iterable
        if not hasattr(bitfields, "__iter__"):
            bitfields = [bitfields]

        for bits in bitfields:
            for i in range(32):
                if bits & (1 << i):
                    tags.add(i)

        return sorted(tags)

    def run_command(self, command, *args, callback=None):
        """Run a riverctl command"""
        if not self.river_control or not self.seat:
            logger.warning(
                "[RiverService] River control or seat not available, falling back to riverctl"
            )
            return self._run_command_fallback(command, *args)

        self.river_control.add_argument(command)
        for arg in args:
            self.river_control.add_argument(str(arg))

        # Execute the command
        command_callback = self.river_control.run_command(self.seat)

        # Set up callback handlers
        result = {"stdout": None, "stderr": None, "success": None}

        def handle_success(_, output):
            logger.debug(f"[RiverService] Command success: {output}")
            result["stdout"] = output
            result["success"] = True
            if callback:
                idle_add(lambda: callback(True, output, None))

        def handle_failure(_, failure_message):
            logger.debug(f"[RiverService] Command failure: {failure_message}")
            result["stderr"] = failure_message
            result["success"] = False
            if callback:
                idle_add(lambda: callback(False, None, failure_message))

        command_callback.dispatcher["success"] = handle_success
        command_callback.dispatcher["failure"] = handle_failure

        if hasattr(self, "_display"):
            self._display.flush()

        return True

    def _run_command_fallback(self, command, *args):
        """Fallback to riverctl"""
        import subprocess

        cmd = ["riverctl", command] + [str(arg) for arg in args]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"[RiverService] Ran command: {' '.join(cmd)}")
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(
                f"[RiverService] Command failed: {' '.join(cmd)}, error: {e.stderr}"
            )
            return None

    def toggle_focused_tag(self, tag, callback=None):
        """Toggle a tag in the focused tags"""
        tag_mask = 1 << int(tag)
        self.run_command("set-focused-tags", str(tag_mask), callback=callback)
