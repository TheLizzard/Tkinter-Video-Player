from threading import Thread, Lock
from time import sleep
import tkinter as tk
import subprocess
import psutil
import os

import msvcrt
from ctypes import windll, byref, wintypes, GetLastError, WinError, POINTER
from ctypes.wintypes import HANDLE, DWORD, BOOL

LPDWORD = POINTER(DWORD)
PIPE_WAIT = wintypes.DWORD(0x00000000)
PIPE_NOWAIT = wintypes.DWORD(0x00000001)

def config_blocking(fd:int, blocking:bool=True) -> bool:
    if blocking:
        mode = PIPE_WAIT
    else:
        mode = PIPE_NOWAIT

    # Kindly plagiarised from: https://stackoverflow.com/a/34504971/11106801
    SetNamedPipeHandleState = windll.kernel32.SetNamedPipeHandleState
    SetNamedPipeHandleState.argtypes = [HANDLE, LPDWORD, LPDWORD, LPDWORD]
    SetNamedPipeHandleState.restype = BOOL

    handle = msvcrt.get_osfhandle(fd)

    res = SetNamedPipeHandleState(handle, byref(mode), None, None)
    assert not (res == 0), "Couldn't set the blocking attribute"

ALPHABET = "abcdefghijklmnopqrstuvwxyz"
ALPHABET += ALPHABET.upper()
ALPHANUMERIC = ALPHABET + "".join(map(str, range(10)))
ALPHANUMERIC_ = ALPHANUMERIC + "_"


class Terminal(tk.Text):
    def __init__(self, master, keep_only_last_line=False, bg="black", **kwargs):
        text_kwargs = dict(bg=bg, fg="white", state="disabled",
                           inactiveselectbackground=bg,
                           selectbackground=bg)
        text_kwargs.update(kwargs)
        super().__init__(master, **text_kwargs)

        super().tag_config("error", foreground="red")
        super().tag_config("my_sel", background="orange")

        self.pressed = False
        self.start_select = None
        self.last_mouse_location = None
        super().bind("<ButtonPress-1>", self.pressed_handle)
        super().bind("<ButtonRelease-1>", self.released_handle)
        super().bind("<Motion>", self.motion_handle)

        super().bind("<Control-c>", self.copy)
        super().bind("<Control-C>", self.copy)
        super().bind("<Control-x>", self.copy)
        super().bind("<Control-X>", self.copy)

        super().bind("<Control-Shift-c>", self.kill)
        super().bind("<Control-Shift-C>", self.kill)

        super().bind("<Shift-Left>", self.shift_left)
        super().bind("<Shift-Right>", self.shift_right)
        super().bind("<Control-Shift-Left>", self.control_shift_left)
        super().bind("<Control-Shift-Right>", self.control_shift_right)

        self.proc = None
        self.result = None
        self.lock = Lock()
        self.keep_only_last_line = keep_only_last_line

        self.stdout = os.pipe()
        config_blocking(self.stdout[0], blocking=False)

        super().focus()

    def destroy(self) -> None:
        try:
            os.close(self.stdout[0])
        except OSError:
            pass
        self.kill()
        super().destroy()

    def poll(self) -> int:
        return self.result

    def __del__(self) -> None:
        try:
            os.close(self.stdout[0])
        except OSError:
            pass
        self.kill()

    def kill(self, event:tk.Event=None) -> None:
        if self.proc is not None:
            process = psutil.Process(self.proc.pid)
            for proc in process.children(recursive=True):
                proc.kill()
            process.kill()
        try:
            self.proc.kill()
            self.proc = None
            self.write(self.pprint("Killed process"), tag="error")
        except AttributeError:
            pass

    def pprint(self, text:str) -> str:
        width = int(super().cget("width"))
        if width == 0:
            pad_start = ""
            pad_end = ""
        else:
            text = f" {text} "
            padding = width - len(text)
            pad_start = "#" * int((padding + 0.9)//2)
            pad_end = "#" * int(padding//2)
        return pad_start + text + pad_end + "\n"

    def run(self, command:str, callback=None, *args) -> None:
        if self.proc is not None:
            raise Exception("Process already running")
        self.result = None

        self.proc = subprocess.Popen(command, shell=True, close_fds=False,
                                     stdout=self.stdout[1],
                                     stderr=self.stdout[1])
        self.read_stdout_loop(callback, args)

    def read_stdout_loop(self, callback, args) -> None:
        self.read_stdout()
        if self.proc is None:
            if callback is not None:
                callback(*args)
        elif self.proc.poll() is not None:
            self.result = self.proc.poll()
            self.write(self.pprint(f"Process exit code: {self.result}"),
                       tag="error")
            self.proc = None
            if callback is not None:
                callback(*args)
        else:
            super().after(100, self.read_stdout_loop, callback, args)

    def read_stdout(self) -> None:
        try:
            data = os.read(self.stdout[0], 1024)
        except:
            return None
        data = data.decode()
        data = data.replace("\r\n", "\n").replace("\r", "\n")
        if len(data) > 0:
            self.write(data)

    def write(self, text:str, tag:str="terminal_stdout") -> None:
        if (self.proc is None) and (tag == "terminal_stdout"):
            return None
        with self.lock:
            super().config(state="normal")

            if self.keep_only_last_line and (tag == "terminal_stdout"):
                ranges = super().tag_ranges("terminal_stdout")
                if len(ranges) > 1:
                    if super().compare(ranges[-1], "==", "end-1c"):
                        super().delete(ranges[-2], ranges[-1])

            super().insert("end", text, tag)
            super().config(state="disabled")
            super().see("end")
            self.colour_sel()

    def clear(self) -> None:
        with self.lock:
            super().config(state="normal")
            super().delete("0.0", "end")
            super().config(state="disabled")
            self.start_select = None

    def pressed_handle(self, event:tk.Event) -> str:
        self.pressed = True
        self.start_select = super().index(f"@{event.x},{event.y}")
        self.last_mouse_location = self.start_select
        return "break"

    def released_handle(self, event:tk.Event) -> str:
        self.pressed = False
        if self.start_select == super().index(f"@{event.x},{event.y}"):
            self.start_select = None
        return "break"

    def motion_handle(self, event:tk.Event) -> str:
        if self.pressed:
            self.last_mouse_location = super().index(f"@{event.x},{event.y}")
            self.colour_sel()
        return "break"

    def colour_sel(self) -> None:
        super().tag_remove("my_sel", "0.0", "end")

        start = self.start_select
        end = self.last_mouse_location
        if (start is None) or (end is None):
            return None
        if super().compare(start, "!=", end):
            if super().compare(start, ">", end):
                start, end = end, start
            super().tag_add("my_sel", start, end)

    def copy(self, event:tk.Event) -> str:
        ranges = super().tag_ranges("my_sel")
        if len(ranges) == 2:
            data = super().get(*ranges)
            super().clipboard_clear()
            super().clipboard_append(data)
        return "break"

    def shift_left(self, event:tk.Event) -> str:
        if not self.pressed:
            base = self.last_mouse_location
            self.last_mouse_location = super().index(f"{base}" \
                                                     f"-1c")
            self.colour_sel()
        return "break"

    def shift_right(self, event:tk.Event) -> str:
        if not self.pressed:
            base = self.last_mouse_location
            self.last_mouse_location = super().index(f"{base}" \
                                                     f"+1c")
            self.colour_sel()
        return "break"

    def control_shift_left(self, event:tk.Event) -> str:
        if not self.pressed:
            skip = self.ctrl_left(str(self.last_mouse_location))
            self.last_mouse_location = super().index(f"{self.last_mouse_location}" \
                                                     f"-{skip}c")
            self.colour_sel()
        return "break"

    def control_shift_right(self, event:tk.Event) -> str:
        if not self.pressed:
            skip = self.ctrl_right(str(self.last_mouse_location))
            self.last_mouse_location = super().index(f"{self.last_mouse_location}" \
                                                     f"+{skip}c")
            self.colour_sel()
        return "break"

    def sort_idxs(self, idx1:str, idx2:str) -> (str, str):
        if super().compare(idx1, "<", idx2):
            return idx1, idx2
        else:
            return idx2, idx1

    ############## I copied the rest of the code from my other project. ##############
    ######################### So I have no idea how it works #########################

    def ctrl_left(self, start:str) -> int:
        chars_skipped = 0
        current_char = super().get(start+"-1c", start)
        last_char = current_char
        looking_for_alphabet = (current_char not in ALPHANUMERIC_)

        while not (looking_for_alphabet^(last_char not in ALPHANUMERIC_)):
            chars_skipped += 1
            left = start+"-%ic" % (chars_skipped+1)
            right = start+"-%ic" % chars_skipped
            last_char = super().get(left, right)

            if last_char in "(){}[]\n":
                if last_char == "\n":
                    chars_skipped += 1
                break
        return chars_skipped

    def ctrl_right(self, start:str) -> int:
        chars_skipped = 0
        current_char = super().get(start, start+"+1c")
        last_char = current_char
        looking_for_alphabet = (current_char not in ALPHANUMERIC_)

        while not (looking_for_alphabet^(last_char not in ALPHANUMERIC_)):
            chars_skipped += 1
            left = start+"+%ic" % chars_skipped
            right = start+"+%ic" % (chars_skipped+1)
            last_char = super().get(left, right)

            if last_char in "'\"(){}[]\n":
                break
        return chars_skipped


if __name__ == "__main__":
    root = tk.Tk()

    terminal = Terminal(root, height=15, width=71, keep_only_last_line=True)
    terminal.pack(fill="both", expand=True)

    command = "ffmpeg -y -v 1 -stats -i D:/videos/pokemon/videos/S20/E12.ts " \
              "-vcodec mpeg1video -acodec libmp3lame -intra temp.mp3"
    terminal.run(command, terminal.write, "Done\n", "error")

    root.mainloop()
    terminal.kill()
