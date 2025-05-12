from fabric.core.service import Property
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from gi.repository import Gdk
from loguru import logger

from fabric.river.service import River

connection: River | None = None


def get_river_connection() -> River:
    global connection
    if not connection:
        connection = River()
    return connection


class RiverWorkspaceButton(Button):
    @Property(int, "readable")
    def id(self) -> int:
        return self._id

    @Property(bool, "read-write", default_value=False)
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, value: bool):
        self._active = value
        (self.remove_style_class if not value else self.add_style_class)("active")

    @Property(bool, "read-write", default_value=False)
    def empty(self) -> bool:
        return self._empty

    @empty.setter
    def empty(self, value: bool):
        self._empty = value
        (self.remove_style_class if not value else self.add_style_class)("empty")

    @Property(bool, "read-write", default_value=False)
    def urgent(self) -> bool:
        return self._urgent

    @urgent.setter
    def urgent(self, value: bool):
        self._urgent = value
        self._update_style()

    def __init__(self, id: int, label: str = None, **kwargs):
        super().__init__(label or str(id), **kwargs)
        self._id = id
        self._active = False
        self._empty = True
        self._urgent = False

    def _update_style(self):
        """Update button styles based on states"""
        # Remove all state-related styles first
        self.remove_style_class("active")
        self.remove_style_class("empty")
        self.remove_style_class("urgent")

        # Then apply current states
        if self._active:
            self.add_style_class("active")
        if self._empty:
            self.add_style_class("empty")
        if self._urgent:
            self.add_style_class("urgent")


class RiverWorkspaces(EventBox):
    def __init__(self, output_id, river_service=None, max_tags=9, **kwargs):
        super().__init__(events="scroll")
        self._box = Box(**kwargs)
        self.children = self._box

        if river_service:
            self.river = river_service
        else:
            self.river = get_river_connection()

        # Store output_id as received
        self.output_id = output_id

        self.max_tags = max_tags
        # Create buttons for tags 0 to max_tags-1 (to match River's 0-based tag indexing)
        self._buttons = {i: RiverWorkspaceButton(i) for i in range(max_tags)}

        for btn in self._buttons.values():
            btn.connect("clicked", self.on_workspace_click)
            self._box.add(btn)

        # Connect to service events
        self.river.connect("event::focused_tags", self.on_focus_change_general)
        self.river.connect("event::view_tags", self.on_view_change_general)
        self.river.connect("event::urgent_tags", self.on_urgent_change_general)
        self.river.connect("event::output_removed", self.on_output_removed)

        # Initial setup when service is ready
        if self.river.ready:
            self.on_ready(None)
        else:
            self.river.connect("event::ready", self.on_ready)

        self.connect("scroll-event", self.on_scroll)

    def on_ready(self, _):
        """Initialize widget state when service is ready"""

        if self.output_id is None and self.river.outputs:
            self.output_id = next(iter(self.river.outputs.keys()))
            logger.info(f"[RiverWorkspaces] Selected output {self.output_id}")

        if self.output_id is not None and self.output_id in self.river.outputs:
            output_info = self.river.outputs[self.output_id]

            focused_tags = output_info.tags_focused
            view_tags = output_info.tags_view
            urgent_tags = output_info.tags_urgent

            for i, btn in self._buttons.items():
                btn.active = i in focused_tags
                btn.empty = i not in view_tags
                btn.urgent = i in urgent_tags

    def on_focus_change(self, _, tags):
        """Handle focused tags change for our specific output"""
        logger.info(
            f"[RiverWorkspaces] Focus change on output {self.output_id}: {tags}"
        )
        for i, btn in self._buttons.items():
            btn.active = i in tags

    def on_view_change(self, _, tags):
        """Handle view tags change for our specific output"""
        logger.info(f"[RiverWorkspaces] View change on output {self.output_id}: {tags}")
        for i, btn in self._buttons.items():
            btn.empty = i not in tags

    def on_focus_change_general(self, _, event):
        """Handle general focused tags event"""
        # Only handle event if it's for our output
        if event.output_id == self.output_id:
            logger.info(
                f"[RiverWorkspaces] General focus change for output {self.output_id}"
            )
            self.on_focus_change(_, event.data)

    def on_view_change_general(self, _, event):
        """Handle general view tags event"""
        # Only handle event if it's for our output
        if event.output_id == self.output_id:
            logger.info(
                f"[RiverWorkspaces] General view change for output {self.output_id}"
            )
            self.on_view_change(_, event.data)

    def on_urgent_change(self, _, tags):
        """Handle urgent tags change for our specific output"""
        logger.info(
            f"[RiverWorkspaces] Urgent change on output {self.output_id}: {tags}"
        )
        for i, btn in self._buttons.items():
            btn.urgent = i in tags

    def on_urgent_change_general(self, _, event):
        """Handle general urgent tags event"""
        # Only handle event if it's for our output
        if event.output_id == self.output_id:
            logger.info(
                f"[RiverWorkspaces] General urgent change for output {self.output_id}"
            )
            self.on_urgent_change(_, event.data)

    def on_output_removed(self, _, event):
        """Handle output removal"""
        removed_id = event.data[0]

        if removed_id == self.output_id:
            logger.info(f"[RiverWorkspaces] Our output {self.output_id} was removed")

            # Try to find another output
            if self.river.outputs:
                self.output_id = next(iter(self.river.outputs.keys()))
                logger.info(f"[RiverWorkspaces] Switching to output {self.output_id}")

                # Update state for new output
                if self.output_id in self.river.outputs:
                    output_info = self.river.outputs[self.output_id]
                    # Access fields directly on the OutputInfo dataclass
                    focused_tags = output_info.tags_focused
                    view_tags = output_info.tags_view

                    for i, btn in self._buttons.items():
                        btn.active = i in focused_tags
                        btn.empty = i not in view_tags

    def on_workspace_click(self, btn):
        """Handle workspace button click"""
        logger.info(f"[RiverWorkspaces] Clicked on workspace {btn.id}")
        self.river.toggle_focused_tag(btn.id)

    def on_scroll(self, _, event):
        """Handle scroll events"""
        direction = event.direction
        if direction == Gdk.ScrollDirection.DOWN:
            logger.info("[RiverWorkspaces] Scroll down - focusing next view")
            self.river.run_command("focus-view", "next")
        elif direction == Gdk.ScrollDirection.UP:
            logger.info("[RiverWorkspaces] Scroll up - focusing previous view")
            self.river.run_command("focus-view", "previous")


class RiverActiveWindow(Label):
    """Widget to display the currently active window's title"""

    def __init__(self, max_length=None, ellipsize="end", river_service=None, **kwargs):
        super().__init__(**kwargs)

        if river_service:
            self.river = river_service
        else:
            self.river = get_river_connection()

        self.max_length = max_length
        self.ellipsize = ellipsize

        # Set initial state
        if self.river.ready:
            self.on_ready(None)
        else:
            self.river.connect("event::ready", self.on_ready)

        # Connect to active window changes
        self.river.connect("event::active_window", self.on_active_window_changed)

    def on_ready(self, _):
        """Initialize widget when service is ready"""
        logger.info("[RiverActiveWindow] Connected to service")
        self.update_title(self.river.active_window)

    def on_active_window_changed(self, _, event):
        """Update widget when active window changes"""
        title = event.data[0] if event.data else ""
        logger.debug(f"[RiverActiveWindow] Window changed to: {title}")
        self.update_title(title)

    def update_title(self, title):
        """Update the label with the window title"""
        if not title:
            self.label = ""
            self.set_label(self.label)
            return

        if self.max_length and len(title) > self.max_length:
            if self.ellipsize == "end":
                title = title[: self.max_length] + "..."
            elif self.ellipsize == "middle":
                half = (self.max_length - 3) // 2
                title = title[:half] + "..." + title[-half:]
            elif self.ellipsize == "start":
                title = "..." + title[-self.max_length :]

        self.label = title
        self.set_label(self.label)
