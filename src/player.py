from tkinter.filedialog import askopenfilename
from PIL import Image, ImageTk
from threading import Thread
from sys import stderr
import tkinter as tk
import tempfile
import pygame
import time
import cv2
import os

from libraries.progressbar import ProgressBar


def timeit(function, *args, number:int=100) -> float:
    start = time.perf_counter()
    for i in range(number):
        function(*args)
    return time.perf_counter() - start


"""
Filter      Downscaling quality    Upscaling quality    Performance
NEAREST                                                 #####
BOX         #                                           ####
BILINEAR    #                      #                    ###
HAMMING     ##                                          ###
BICUBIC     ###                    ###                  ##
LANCZOS     ####                   ####                 #
"""

RESAMPLE_OPTIONS = {0: Image.NEAREST,
                    1: Image.BOX,
                    2: Image.BILINEAR,
                    3: Image.HAMMING,
                    4: Image.BICUBIC,
                    5: Image.LANCZOS}
RESAMPLE = RESAMPLE_OPTIONS[4]

ABOVE = 31.1
BELLOW = 15.1
FRAMES_DELAY = 20

pygame.init()


STATUS_BAR = True
STATUS_BAR_FRAME_NUMBER = False
ALLOWED_SLEEP = False

DEBUGGING = True
PHOTOIMAGE_IN_MAIN = True  # Very, very unstable if it's set to `False`
PRE_PREPARED_SOUND = True

FRAMES_NOT_LOADED_THRESHOLD = 5 # If we can't load `FRAMES_NOT_LOADED_THRESHOLD`
                                #   frames in a row pause for:
TIME_PAUSED = 2000              #   `TIME_PAUSED` milliseconds


class StatusBar(tk.Frame):
    def __init__(self, master, **kwargs):
        self._loading = 0
        fg = kwargs.pop("fg", None)
        super().__init__(master, **kwargs)
        super().columnconfigure((1, 2, 3, 4), weight=1)

        self._fps = -1

        self.frame_number_label = tk.Label(self, fg=fg, justify="left",
                                           **kwargs)
        self.frame_number_label.grid(row=1, column=1, sticky="w")

        self.loading_label = tk.Label(self, fg=fg, justify="left", **kwargs)
        self.loading_label.grid(row=1, column=2, sticky="w")

        self.time_label = tk.Label(self, fg=fg, justify="left", **kwargs)
        self.time_label.grid(row=1, column=3, sticky="w")

        self.fps_label = tk.Label(self, fg=fg, text="FPS", justify="right",
                                  **kwargs)
        self.fps_label.grid(row=1, column=4, sticky="e")

        self.full_length = "00:00:00"

    @property
    def fps(self) -> None:
        return self._fps

    @fps.setter
    def fps(self, new_value) -> None:
        if self._fps != new_value:
            self.fps_label.config(text=f"FPS: {new_value}")
            self._fps = new_value

    @property
    def loading(self) -> int:
        return self._loading

    @loading.setter
    def loading(self, new_value:int) -> None:
        if self._loading == new_value:
            return None
        self._loading = new_value % 20 + 1
        if new_value == 0:
            text = ""
        else:
            text = "Loading" + "." * self._loading
        self.loading_label.config(text=text)

    @property
    def frame_number(self) -> None:
        return None

    @frame_number.setter
    def frame_number(self, new_value:int) -> None:
        self.frame_number_label.config(text=f"Frame number: {new_value}")

    @property
    def time(self) -> None:
        return None

    @time.setter
    def time(self, secs:int) -> None:
        mins, secs = divmod(int(secs), 60)
        hours, mins = divmod(mins, 60)
        mins = str(mins).zfill(2)
        secs = str(secs).zfill(2)
        if hours == 0:
            self.time_label.config(text=f"{mins}:{secs}/{self.full_length}")
        else:
            self.time_label.config(text=f"{hours}:{mins}:{secs}/"\
                                        f"{self.full_length}")

    def set_full_length(self, secs:int) -> None:
        mins, secs = divmod(int(secs), 60)
        hours, mins = divmod(mins, 60)
        mins = str(mins).zfill(2)
        secs = str(secs).zfill(2)
        if hours == 0:
            self.full_length = f"{mins}:{secs}"
        else:
            self.full_length = f"{hours}:{mins}:{secs}"


class BasePlayer(tk.Frame):
    __slots__ = ("width", "height", "cap", "NUMBER_OF_FRAMES",
                 "BASE_WIDTH", "BASE_HEIGHT", "FPS", "sounddir", "proc")
    def __init__(self, master, **kwargs):
        self.sounddir = None

        super().__init__(master, bd=0, highlightthickness=0)
        self.canvas = tk.Canvas(self, bd=0, highlightthickness=0, **kwargs)
        if STATUS_BAR:
            self.status_bar = StatusBar(self, bd=0, highlightthickness=0,
                                        bg="black", fg="white")
            self.status_bar.pack(side="bottom", fill="x")
        self.canvas.pack(side="top", fill="both", expand=True)

    def __del__(self) -> None:
        self.close_sounddir()
        self.cap.release()

    def set_up(self, filename:str) -> None:
        self.filename = filename
        self.get_sound()

        self.resized = False
        self.cap = cv2.VideoCapture(self.filename)
        self.NUMBER_OF_FRAMES = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.BASE_WIDTH = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.BASE_HEIGHT = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.FPS = self.cap.get(cv2.CAP_PROP_FPS)

        self.progressbar = ProgressBar(self.canvas, self.NUMBER_OF_FRAMES)
        if STATUS_BAR:
            self.status_bar.set_full_length(self.NUMBER_OF_FRAMES // self.FPS)

    def show_image(self, image:(Image.Image or ImageTk.PhotoImage)) -> None:
        if PHOTOIMAGE_IN_MAIN:
            image = ImageTk.PhotoImage(image, master=self)
        self.tk_image = image
        try:
            self.canvas.itemconfig(self.image_id, image=self.tk_image)
        except:
            self.image_id = self.canvas.create_image(0, 0, anchor="nw",
                                                     image=self.tk_image,
                                                     tags=("image", ))

    def read_next_frame(self) -> Image.Image:
        _, image_matrix = self.cap.read()
        image_matrix = cv2.cvtColor(image_matrix, cv2.COLOR_RGB2BGR)
        return Image.fromarray(image_matrix)

    def _resize(self, image:Image.Image) -> Image.Image:
        """
        Resizes the given `Image.Image` based on
        `self.width` and `self.height`
        """
        if self.resized:
            return image.resize((self.width, self.height), RESAMPLE)
        else:
            return image

    def resize(self, width:int=None, height:int=None) -> None:
        """
        Resizes the video based on the width/height that is given.
        It perseveres the aspect ratio.
        """
        if width is None:
            xfactor = float("inf")
        else:
            assert isinstance(width, int), "The `width` must be an `int`."
            xfactor = width/self.BASE_WIDTH

        if height is None:
            yfactor = float("inf")
        else:
            assert isinstance(height, int), "The `height` must be an `int`."
            yfactor = height/self.BASE_HEIGHT

        factor = min(xfactor, yfactor)
        self.width = int(factor * self.BASE_WIDTH)
        self.height = int(factor * self.BASE_HEIGHT)

        self.canvas.config(width=self.width, height=self.height)
        self.resized = not (self.width == self.BASE_WIDTH)
        stderr.write(f"[Debug]: Resize {self.width}x{self.height}  \t"\
                     f"resized={self.resized}\n")

    def goto_frame_number(self, frame_number:int) -> None:
        """
        Goes to the frame number specified.
        """
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

    def get_sound(self) -> None:
        """
        Saves the sound from the file given in another file. The filename
        for the sound file is:

            if PRE_PREPARED_SOUND or DEBUGGING:
                f"tmp/{self.filename}_sound.mp3"
            else:
                <BasePlayer>.sounddir.name + "/sound.mp3"
        """
        if PRE_PREPARED_SOUND or DEBUGGING:
            self.soundfile = self.filename.replace("\\", "/").split("/")[-1]
            self.soundfile = f"tmp/{self.soundfile}_sound.mp3"
            stderr.write("[Debug]: Using this sound file: " \
                         f"\"{self.soundfile}\"\n")
            assert os.path.isfile(self.soundfile), "Not pre-prepared"

            if PRE_PREPARED_SOUND:
                higher_quality = self.filename.replace("\\", "/").split("/")[-1]
                higher_quality = f"tmp/{higher_quality}_video.ts"
                if os.path.isfile(higher_quality):
                    self.filename = higher_quality

            return None

        self.sounddir = tempfile.TemporaryDirectory()
        self.soundfile = self.sounddir.name + "/sound.mp3"

        command = f"ffmpeg -i {self.filename} -vcodec mpeg1video -acodec " \
                  f"libmp3lame -intra {self.soundfile}"
        os.system(command)

    def close_sounddir(self) -> None:
        """
        Stops the sound and deletes the sound file.
        It's called automatically from `.__del__()`
        """
        self.stop_sound()
        if not (DEBUGGING or PRE_PREPARED_SOUND):
            if self.sounddir is None:
                return None
            self.sounddir.cleanup()
            self.sounddir = None

    def play_sound(self) -> None:
        pygame.mixer.music.load(self.soundfile)
        pygame.mixer.music.play()

    def pause_sound(self) -> None:
        pygame.mixer.music.pause()

    def unpause_sound(self) -> None:
        pygame.mixer.music.unpause()

    def sound_goto(self, time:float) -> None:
        pygame.mixer.music.rewind()
        if 0 < time < self.NUMBER_OF_FRAMES / self.FPS:
            pygame.mixer.music.set_pos(time)

    def stop_sound(self) -> None:
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()


class Player(BasePlayer):
    __slots__ = ("frames", "time_paused", "base_timer", "playing",
                 "frame_number_shown", "loading_frames", "last_frame_loaded")

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.clear_frames_cache()
        self.frame_number_shown = 0
        self.last_frame_loaded = -1
        super().focus()
        super().bind("<space>", self.toggle_pause, add=True)
        super().bind("<Left>", self.left_pressed, add=True)
        super().bind("<Right>", self.right_pressed, add=True)
        super().bind("<Control-r>", self.clear_frames_cache, add=True)

        self.last_5_fps = [0, 0, 0, 0, 0]
        self.temp_pause_after_id = None

        self.frames_coundnt_load = 0

    def clear_frames_cache(self, event:tk.Event=None) -> None:
        self.frames = {}
        self.change_frame_shown()

    def change_frame_shown(self) -> None:
        self.changed_frame_shown = dict(main=True)

    def left_pressed(self, event:tk.Event=None) -> None:
        now = time.perf_counter()
        self.base_timer = min(self.base_timer + 5, now)
        time_delta = now - self.base_timer
        super().sound_goto(time_delta)
        self.frame_number_shown = int(time_delta * self.FPS)
        self.change_frame_shown()
        self.start_pause_time = now
        self.progressbar.last_mouse_movement = now
        self.progressbar.value = self.frame_number_shown
        if STATUS_BAR:
            if STATUS_BAR_FRAME_NUMBER:
                self.status_bar.frame_number = self.frame_number_shown
            self.status_bar.time = self.frame_number_shown // self.FPS
        self._show_frame_when_paused(self.frame_number_shown)
        stderr.write(f"[Debug]: Calling goto {self.frame_number_shown}\n")

    def right_pressed(self, event:tk.Event=None) -> None:
        self.base_timer -= 5
        now = time.perf_counter()
        time_delta = now - self.base_timer
        if time_delta > self.NUMBER_OF_FRAMES/self.FPS:
            self.base_timer += 5
            self.pause()
        else:
            super().sound_goto(time_delta)
        self.frame_number_shown = int(time_delta * self.FPS)
        self.change_frame_shown()
        self.start_pause_time = now
        self.progressbar.last_mouse_movement = now
        self.progressbar.value = self.frame_number_shown
        if STATUS_BAR:
            if STATUS_BAR_FRAME_NUMBER:
                self.status_bar.frame_number = self.frame_number_shown
            self.status_bar.time = self.frame_number_shown // self.FPS
        self._show_frame_when_paused(self.frame_number_shown)
        stderr.write(f"[Debug]: Calling goto {self.frame_number_shown}\n")

    def goto(self, frame_number:int) -> None:
        self.frame_number_shown = frame_number
        self.change_frame_shown()
        self.base_timer = time.perf_counter() - frame_number / self.FPS
        if STATUS_BAR:
            if STATUS_BAR_FRAME_NUMBER:
                self.status_bar.frame_number = frame_number
            self.status_bar.time = self.frame_number_shown // self.FPS
        self._show_frame_when_paused(frame_number)
        stderr.write(f"[Debug]: Calling goto {self.frame_number_shown}\n")

    def _show_frame_when_paused(self, frame_number) -> None:
        if self.temp_pause_after_id is not None:
            super().after_cancel(self.temp_pause_after_id)
            self.temp_pause_after_id = None
        if self.playing:
            return None
        if frame_number in self.frames:
            super().show_image(self.frames[self.frame_number_shown])
        else:
            f = self._show_frame_when_paused
            self.temp_pause_after_id = super().after(100, f, frame_number)

    def set_up(self, filename:str):
        super().set_up(filename)
        self.canvas.bind("<Button-1>", self.toggle_pause, add=True)
        self.progressbar.callback = self.goto
        self.progressbar.dragging_start_callback = self.temp_pause
        self.progressbar.dragging_end_callback = self.temp_unpause
        self.loading_frames = True
        thread = Thread(target=self.load_frames, daemon=True)
        thread.start()
        thread = Thread(target=self.cleanup_loop, daemon=True)
        thread.start()

    def temp_pause(self) -> None:
        self._playing = self.playing
        if self.playing:
            self.pause()

    def temp_unpause(self) -> None:
        if self._playing:
            self.unpause(change_base_timer=False)
        if self.temp_pause_after_id is not None:
            super().after_cancel(self.temp_pause_after_id)
            self.temp_pause_after_id = None

    def start(self) -> None:
        self.playing = True
        self.base_timer = time.perf_counter()
        self.last_updated = self.base_timer
        self.display_loop()
        super().play_sound()

    def toggle_pause(self, event:tk.Event=None) -> None:
        if self.playing:
            self.pause()
        else:
            self.unpause()

    def pause(self) -> None:
        if not self.playing:
            return False
        self.playing = False
        self.change_frame_shown()
        self.start_pause_time = time.perf_counter()
        self.progressbar.show(hide=False)
        super().pause_sound()

    def unpause(self, change_base_timer=True) -> None:
        if self.playing:
            return False
        self.playing = True
        if change_base_timer:
            self.base_timer += time.perf_counter() - self.start_pause_time
        super().unpause_sound()
        self.display_loop()
        self.progressbar.hide()

    def display_loop(self, update_number=1) -> None:
        if not self.playing:
            return None

        now = time.perf_counter()
        time_delta = now - self.base_timer

        self.frame_number_shown = max(0, int(time_delta * self.FPS))
        if self.frame_number_shown > self.NUMBER_OF_FRAMES:
            return None
        self.progressbar.value = self.frame_number_shown

        if (update_number - 20) % 500 == 0:
            super().sound_goto(time_delta)

        if self.frame_number_shown in self.frames:
            super().show_image(self.frames[self.frame_number_shown])
            self.frames_coundnt_load = 0
            if STATUS_BAR:
                global ABOVE
                self.last_5_fps.append(int(1/(now - self.last_updated) + 0.5))
                self.last_5_fps.pop(0)
                fps = int(sum(self.last_5_fps) / 5)
                self.status_bar.fps = fps
                self.last_updated = now
                # If the FPS is high enough we can afford to increase `ABOVE`
                if fps > 25:
                    # Add one to `ABOVE` but make sure that it's not >31
                    # Also make sure it can't go lower than the default `ABOVE`
                    #   from the min
                    ABOVE = max(ABOVE, min(ABOVE+1, 31))
                self.status_bar.loading = 0
        else:
            #stderr.write("[Debug]: Needing frame number " \
            #             f"{self.frame_number_shown}\n")
            self.frames_coundnt_load += 1
            if self.frames_coundnt_load == FRAMES_NOT_LOADED_THRESHOLD:
                self.pause()
                stderr.write("[Debug]: Paused because can't show frames\n")
                super().after(TIME_PAUSED, self.unpause)
            if STATUS_BAR:
                self.status_bar.loading += 1

        if STATUS_BAR:
            if STATUS_BAR_FRAME_NUMBER:
                self.status_bar.frame_number = self.frame_number_shown
            self.status_bar.time = self.frame_number_shown // self.FPS
        super().after(FRAMES_DELAY, self.display_loop, (update_number+1)%1000)

    def cleanup_loop(self) -> None:
        time.sleep(1)
        while self.loading_frames:
            self._cleanup_loop()

    def _cleanup_loop(self) -> None:
        current_frame_number = self.frame_number_shown
        lower = current_frame_number - int(BELLOW * self.FPS)
        upper = current_frame_number + int(ABOVE * self.FPS)
        upper = min(self.NUMBER_OF_FRAMES, upper)
        for frame_number in tuple(self.frames.keys()):
            if not (lower < self.frame_number_shown < upper):
                break
            if not (lower < frame_number < upper):
                del self.frames[frame_number]
        time.sleep(2)

    def sleep_load_frames(self, tag:str) -> None:
        for i in range(10):
            if self.changed_frame_shown[tag]:
                stderr.write("[Debug]: Stop sleeping\n")
                return None
            time.sleep(0.01)

    def load_frames(self) -> None:
        while self.loading_frames:
            self.changed_frame_shown["main"] = False
            orig = self.frame_number_shown - 1
            top = min(self.NUMBER_OF_FRAMES, orig + int(ABOVE * self.FPS))
            self._load_frames(orig, top)
            if (not self.changed_frame_shown["main"]) and ALLOWED_SLEEP:
                self.sleep_load_frames("main")

    def _load_frames(self, orig:int, top:int) -> None:
        for i in range(orig, top):
            if (self.changed_frame_shown["main"]) or (not self.loading_frames):
                stderr.write("[Debug]: Stop loading frames\n")
                return None
            if i not in self.frames:
                try:
                    self.load_frame(i)
                except cv2.error:
                    pass

    def load_frame(self, frame_number) -> None:
        if self.last_frame_loaded + 1 != frame_number:
            stderr.write(f"[Debug]: ({self.last_frame_loaded} => " \
                         f"{frame_number})\n")
            super().goto_frame_number(frame_number)
        self.last_frame_loaded = frame_number

        if not self.loading_frames:
            return None

        image = super()._resize(super().read_next_frame())
        if not PHOTOIMAGE_IN_MAIN:
            self.frames[frame_number] = self.convert_image_to_tk(image)
        else:
            self.frames[frame_number] = image

    def convert_image_to_tk(self, image:Image.Image) -> ImageTk.PhotoImage:
        image.draft("RGB", image.size)
        return ImageTk.PhotoImage(image)

    def destroy(self) -> None:
        self.loading_frames = False
        super().stop_sound()
        super().close_sounddir()
        super().destroy()

    def stop(self) -> None:
        self.loading_frames = False


if __name__ == "__main__":
    from libraries.bettertk import BetterTk

    def fullscreen(event:tk.Event=None) -> None:
        root.fullscreen_button.invoke()

    def default_size(event:tk.Event=None) -> None:
        player.resize(width=player.BASE_WIDTH)
        assert not player.resized, "Internal error"
        root.geometry("")

    def resized(new_geometry:str) -> None:
        # If window is resized:
        if "x" in new_geometry:
            player.canvas.update()
            width = player.canvas.winfo_width()
            height = player.canvas.winfo_height()
            player.resize(width=int(width), height=int(height))

    root = BetterTk()
    root.geometry_bindings.append(resized)
    root.title("Video Player")
    root.bind_all("<KeyPress-f>", fullscreen)
    root.bind_all("<KeyPress-g>", default_size)

    player = Player(root, bg="black")
    player.pack(fill="both", expand=True)

    if DEBUGGING:
        filepath = "tmp/vid.ts"
    else:
        filetypes = (("Video File", "*.ts;*.mp4"), ("All files", "*.*"))
        filepath = askopenfilename(initialdir=r"D:\videos\pokemon\videos",
                                   filetypes=filetypes, defaultextension="*.*",
                                   title="Select video file")
    if filepath != "":
        player.set_up(filepath)
        player.resize(width=1280)
        time.sleep(0.2) # Just to allow some of the frames to be read.
        player.start()

        root.mainloop()
