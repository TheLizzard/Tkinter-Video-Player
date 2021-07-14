import tkinter as tk
from time import perf_counter


TIME_TO_HIDE = 3 # Seconds
PADX = 10        # Pixels
PADY = 10        # Pixels
THICKNESS = 10   # Pixels


class ProgressBar:
    def __init__(self, canvas:tk.Canvas, _max:int, callback=None,
                 dragging_start_callback=None, dragging_end_callback=None,
                 hide_cursor:bool=True):
        canvas.bind("<Configure>", None, add=True)
        canvas.bind("<Motion>", self.motion, add=True)
        canvas.bind("<Leave>", self.leave, add=True)
        canvas.bind("<ButtonPress-1>", self.press, add=True)
        canvas.bind("<ButtonRelease-1>", self.release, add=True)

        # No idea why this doesn't work:
        # canvas.tag_bind("progressbar", "<ButtonPress-1>", self.press, add=True)
        # canvas.tag_bind("progressbar", "<ButtonRelease-1>", self.release, add=True)

        self.shown = False
        self.canvas = canvas
        self.max = _max
        self._value = 0
        self.callback = callback
        self.dragging = False
        self.last_mouse_movement = 0
        self.hide_cursor = hide_cursor

        width = int(self.canvas.winfo_width())
        height = int(self.canvas.winfo_height())
        self.set_up(width, height)

        canvas.update()
        self.check_mouse_pos()

        self.dragging_start_callback = dragging_start_callback
        self.dragging_end_callback = dragging_end_callback

    def check_mouse_pos(self) -> None:
        startx = self.canvas.winfo_rootx()
        starty = self.canvas.winfo_rooty()
        endx = startx + self.canvas.winfo_width()
        endy = starty + self.canvas.winfo_height()
        if ((startx < self.canvas.winfo_pointerx() < endx) and\
            (starty < self.canvas.winfo_pointery() < endy)):
            self.shown = True
            self.canvas.itemconfigure("progressbar", state="normal")
        else:
            self.shown = False
            self.canvas.itemconfigure("progressbar", state="hidden")

    def get_x1_y1_x2_y2(self) -> (int, int, int, int):
        return (PADX, self.height-PADY-THICKNESS, self.width-PADX,
                self.height-PADY)

    def leave(self, event:tk.Event) -> None:
        if not self.dragging:
            self.hide()

    def press(self, event:tk.Event) -> None:
        x1, y1, x2, y2 = self.get_x1_y1_x2_y2()
        if (x1 < event.x < x2) and (y1 < event.y < y2):
            if self.dragging_start_callback is not None:
                self.dragging_start_callback()
            self.dragging = True
            self.motion(event)
            return "break"

    def release(self, event:tk.Event) -> None:
        if self.dragging:
            if self.dragging_end_callback is not None:
                self.dragging_end_callback()
            self.dragging = False
            self.check_mouse_pos()
            return "break"

    def motion(self, event:tk.Event) -> None:
        if self.dragging:
            self.last_mouse_movement = max(perf_counter(),
                                           self.last_mouse_movement)
            x1, _, x2, _ = self.get_x1_y1_x2_y2()
            value = int((event.x - x1)/(x2 - x1)*self.max + 0.5)
            self.value = min(max(value, 0), self.max)
            self.update_progressbar(keep_updating=False)
            if self.callback is not None:
                self.callback(self.value)
        else:
            self.show()

    def set_up(self, width:int, height:int) -> None:
        self.width, self.height = width, height

        x1, y1, x2, y2 = self.get_x1_y1_x2_y2()
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="grey",
                                     tags=("progressbar", ))

        self.canvas.create_rectangle(x1, y1, x1, y2, fill="white",
                                     tags=("progressbar", "past"))

        self.max_bar_width = x2 - x1

    def update_progressbar(self, keep_updating=True) -> None:
        if perf_counter() - self.last_mouse_movement > TIME_TO_HIDE:
            self.hide()
        if not self.shown:
            return None

        width = int(self.canvas.winfo_width())
        height = int(self.canvas.winfo_height())
        if (width != self.width) or (height != self.height):
            self.canvas.delete("progressbar")
            self.set_up(width, height)

        x1, y1, x2, y2 = self.get_x1_y1_x2_y2()
        x2 = self.max_bar_width * (self.value / self.max) + x1
        self.canvas.coords("past", x1, y1, x2, y2)

        if keep_updating:
            self.canvas.after(100, self.update_progressbar, True)

    def show(self, hide=True) -> None:
        if self.shown:
            return None
        self.shown = True
        self.canvas.itemconfigure("progressbar", state="normal")
        if hide:
            self.last_mouse_movement = perf_counter()
        else:
            # Never hide the progressbar
            self.last_mouse_movement = float("inf")
        self.update_progressbar()
        if self.hide_cursor:
            self.canvas.config(cursor="")

    def hide(self, event:tk.Event=None) -> None:
        if (not self.shown) or self.dragging:
            return None
        self.shown = False
        self.canvas.itemconfigure("progressbar", state="hidden")
        if self.hide_cursor:
            self.canvas.config(cursor="none")

    @property
    def value(self) -> int:
        return self._value

    @value.setter
    def value(self, new_value:int) -> None:
        self._value = new_value


if __name__ == "__main__":
    root = tk.Tk()

    canvas = tk.Canvas(root, bg="black")
    canvas.pack(fill="both", expand=True)

    pbar = ProgressBar(canvas, 100)
    pbar.callback = print
