from tkinter.filedialog import askopenfilename
from PIL import Image, ImageTk
from threading import Thread
import tkinter as tk
import tempfile
import pygame
import time
import cv2
import os

from progressbar import ProgressBar

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

ABOVE = 11
BELLOW = 6
FRAMES_DELAY = 20

pygame.init()


DEBUGGING = False


class StatusBar(tk.Frame):
    def __init__(self, master, **kwargs):
        self._loading = 0
        fg = kwargs.pop("fg", None)
        super().__init__(master, **kwargs)
        super().columnconfigure((1, 2, 3, 4), weight=1)

        self.frame_number_label = tk.Label(self, fg=fg, justify="left", **kwargs)
        self.frame_number_label.grid(row=1, column=1, sticky="w")

        self.loading_label = tk.Label(self, fg=fg, justify="left", **kwargs)
        self.loading_label.grid(row=1, column=2, sticky="w")

        self.time_label = tk.Label(self, fg=fg, justify="left", **kwargs)
        self.time_label.grid(row=1, column=3, sticky="w")

        self.fps_label = tk.Label(self, fg=fg, text="FPS", justify="right", **kwargs)
        self.fps_label.grid(row=1, column=4, sticky="e")

        self.full_length = "00:00:00"

    @property
    def fps(self) -> None:
        return None

    @fps.setter
    def fps(self, new_value) -> None:
        self.fps_label.config(text=f"FPS: {new_value}")

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
        self.status_bar = StatusBar(self, bd=0, highlightthickness=0,
                                    bg="black", fg="white")
        self.status_bar.pack(side="bottom", fill="x")
        self.canvas.pack(side="top", fill="both", expand=True)

    def __del__(self) -> None:
        self.close_sounddir()

    def set_up(self, filename:str) -> None:
        self.get_sound(filename)

        self.cap = cv2.VideoCapture(filename)
        self.NUMBER_OF_FRAMES = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.BASE_WIDTH = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        self.BASE_HEIGHT = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        self.FPS = self.cap.get(cv2.CAP_PROP_FPS)

        self.progressbar = ProgressBar(self.canvas, self.NUMBER_OF_FRAMES)
        self.status_bar.set_full_length(self.NUMBER_OF_FRAMES // self.FPS)

    def show_image(self, image:Image.Image) -> None:
        self.tk_image = ImageTk.PhotoImage(image)
        self.canvas.delete("image")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image,
                                 tags=("image", ))
        self.canvas.tag_lower("image")

    def read_next_frame(self) -> Image.Image:
        _, image_matrix = self.cap.read()
        image_matrix = cv2.cvtColor(image_matrix, cv2.COLOR_RGB2BGR)
        return Image.fromarray(image_matrix)

    def _resize(self, image:Image.Image) -> Image.Image:
        """
        Resizes the given `Image.Image` based on `self.width`
        """
        return image.resize((self.width, self.height), RESAMPLE)

    def resize(self, width:int=None, height:int=None) -> None:
        """
        Resizes the video based on the width/height that is given.
        Only one of them can be given because this forces the video
        to keep its aspect ratio.
        """
        assert (width is not None) ^ (height is not None), "You must specify " \
               "either the width or the height."
        if width is not None:
            assert isinstance(width, int), "The `width` must be an `int`."
            self.width = width
            self.height = int(width/self.BASE_WIDTH*self.BASE_HEIGHT + 0.5)

        if height is not None:
            assert isinstance(height, int), "The `height` must be an `int`."
            self.height = height
            self.width = int(height/self.BASE_HEIGHT*self.BASE_WIDTH + 0.5)

        self.canvas.config(width=self.width, height=self.height)

    def resize_keep_aspect(self, width:int, height:int) -> None:
        """
        Resizes the video based on the width/height that is given. It also
        keeps the aspect ratio.
        """
        w_aspect = width/self.BASE_WIDTH
        h_aspect = height/self.BASE_HEIGHT
        aspect = min(w_aspect, h_aspect)

        self.width = int(aspect * self.BASE_WIDTH + 0.5)
        self.height = int(aspect * self.BASE_HEIGHT + 0.5)

        self.canvas.config(width=self.width, height=self.height)

    def goto_frame_number(self, frame_number:int) -> None:
        """
        Goes to the frame number specified.
        """
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

    def get_sound(self, filename:str) -> None:
        """
        Saves the sound from the file given in a temporary directory.
        The filename for the sound file is:
        <BasePlayer>.sounddir.name + "/sound.mp3"
        """
        if DEBUGGING:
            if not os.path.isfile("sound.mp3"):
                command = f"ffmpeg -i {filename} -vcodec mpeg1video -acodec " \
                          f"libmp3lame -intra sound.mp3"
                os.system(command)
        else:
            sounddir = tempfile.TemporaryDirectory()
            soundfile = sounddir.name + "/sound.mp3"

            command = f"ffmpeg -i {filename} -vcodec mpeg1video -acodec " \
                      f"libmp3lame -intra {soundfile}"
            os.system(command)

            # Signal that we have the sound file:
            self.sounddir = sounddir

    def close_sounddir(self) -> None:
        """
        Deletes the sound file. It's called automatically from `.__del__()`
        """
        if DEBUGGING:
            pass
        else:
            if self.sounddir is None:
                return None
            self.stop_sound()
            self.sounddir.cleanup()
            self.sounddir = None

    def play_sound(self) -> None:
        if DEBUGGING:
            pygame.mixer.music.load("sound.mp3")
            pygame.mixer.music.play()
        else:
            assert self.sounddir is not None, "No sound file was generated."
            pygame.mixer.music.load(self.sounddir.name + "/sound.mp3")
            pygame.mixer.music.play()

    def pause_sound(self) -> None:
        pygame.mixer.music.pause()

    def unpause_sound(self) -> None:
        pygame.mixer.music.unpause()

    def sound_goto(self, time:float) -> None:
        pygame.mixer.music.rewind()
        if time > 0:
            pygame.mixer.music.set_pos(time)

    def stop_sound(self) -> None:
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()


class Player(BasePlayer):
    __slots__ = ("frames", "time_paused", "base_timer", "playing",
                 "frame_number_shown", "loading_frames", "last_frame_loaded")

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.frames = {}
        self.frame_number_shown = 0
        self.last_frame_loaded = -1
        super().focus()
        super().bind("<space>", self.toggle_pause, add=True)
        super().bind("<Left>", self.left_pressed, add=True)
        super().bind("<Right>", self.right_pressed, add=True)
        super().bind("<Control-r>", self.clear_frames_cache, add=True)

        self.last_5_fps = [0, 0, 0, 0, 0]
        self.temp_pause_after_id = None

    def clear_frames_cache(self, event:tk.Event=None) -> None:
        self.frames = {}
        self.changed_frame_shown = True

    def left_pressed(self, event:tk.Event=None) -> None:
        now = time.perf_counter()
        self.base_timer = min(self.base_timer + 5, now)
        time_delta = now - self.base_timer
        super().sound_goto(time_delta)
        self.frame_number_shown = int(time_delta * self.FPS)
        self.changed_frame_shown = True
        self.start_pause_time = now
        self.progressbar.last_mouse_movement = now
        self.progressbar.value = self.frame_number_shown
        self.status_bar.frame_number = self.frame_number_shown
        self.status_bar.time = self.frame_number_shown // self.FPS
        self._show_frame_when_paused(self.frame_number_shown)
        print(f"[Debug]: Calling goto {self.frame_number_shown}")

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
        self.changed_frame_shown = True
        self.start_pause_time = now
        self.progressbar.last_mouse_movement = now
        self.progressbar.value = self.frame_number_shown
        self.status_bar.frame_number = self.frame_number_shown
        self.status_bar.time = self.frame_number_shown // self.FPS
        self._show_frame_when_paused(self.frame_number_shown)
        print(f"[Debug]: Calling goto {self.frame_number_shown}")

    def goto(self, frame_number:int) -> None:
        self.frame_number_shown = frame_number
        self.changed_frame_shown = True
        self.base_timer = time.perf_counter() - frame_number / self.FPS
        self.status_bar.frame_number = frame_number
        self.status_bar.time = self.frame_number_shown // self.FPS
        self._show_frame_when_paused(frame_number)
        print(f"[Debug]: Calling goto {self.frame_number_shown}")

    def _show_frame_when_paused(self, frame_number) -> None:
        if self.temp_pause_after_id is not None:
            super().after_cancel(self.temp_pause_after_id)
            self.temp_pause_after_id = None
        if self.playing:
            return None
        if frame_number in self.frames:
            super().show_image(self.frames[self.frame_number_shown])
        else:
            self.temp_pause_after_id = super().after(100, self._show_frame_when_paused, frame_number)

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
        self.changed_frame_shown = True
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
        if update_number % 3 == 0:
            super().sound_goto(time_delta)

        self.frame_number_shown = max(0, int(time_delta * self.FPS))
        self.progressbar.value = self.frame_number_shown

        if self.frame_number_shown in self.frames:
            super().show_image(self.frames[self.frame_number_shown])

            self.last_5_fps.append(int(1/(now - self.last_updated) + 0.5))
            self.last_5_fps.pop(0)
            self.status_bar.fps = int(sum(self.last_5_fps) / 5)
            self.status_bar.loading = 0
            self.last_updated = now
        else:
            print(f"[Debug]: Needing frame number {self.frame_number_shown}")
            self.status_bar.loading += 1

        self.status_bar.time = self.frame_number_shown // self.FPS
        self.status_bar.frame_number = self.frame_number_shown
        super().after(FRAMES_DELAY, self.display_loop, (update_number+1)%1000)

    def cleanup_loop(self) -> None:
        time.sleep(1)
        while self.loading_frames:
            self._cleanup_loop()

    def _cleanup_loop(self) -> None:
        current_frame_number = self.frame_number_shown
        lower = current_frame_number - int(BELLOW * self.FPS)
        upper = current_frame_number + int(ABOVE * self.FPS)
        for frame_number in tuple(self.frames.keys()):
            if not (lower < self.frame_number_shown < upper):
                break
            if not (lower < frame_number < upper):
                del self.frames[frame_number]
        time.sleep(2)

    def load_frames(self) -> None:
        while self.loading_frames:
            self.changed_frame_shown = False
            orig = self.frame_number_shown - 1
            top = orig + int(ABOVE * self.FPS)
            self._load_frames(orig, top)
            if not self.changed_frame_shown:
                self.sleep_load_frames()

    def sleep_load_frames(self) -> None:
        for i in range(100):
            if self.changed_frame_shown:
                print("[Debug]: Stop sleeping")
                return None
            time.sleep(0.01)

    def _load_frames(self, orig:int, top:int) -> None:
        for i in range(orig, top):
            if self.changed_frame_shown:
                print("[Debug]: Stop loading frames")
                return None
            if i not in self.frames:
                try:
                    self.load_frame(i)
                except cv2.error:
                    pass

    def load_frame(self, frame_number) -> None:
        if self.last_frame_loaded + 1 != frame_number:
            print(f"[Debug]: ({self.last_frame_loaded} => {frame_number})")
            super().goto_frame_number(frame_number)

        pil_image = super()._resize(super().read_next_frame())
        self.frames[frame_number] = pil_image
        self.last_frame_loaded = frame_number

    def destroy(self) -> None:
        self.loading_frames = False
        super().stop_sound()
        super().close_sounddir()
        super().destroy()

    def stop(self) -> None:
        self.loading_frames = False


if __name__ == "__main__":
    from bettertk import BetterTk

    def fullscreen(event:tk.Event=None) -> None:
        root.fullscreen_button.invoke()

    def resized(new_geometry:str) -> None:
        if "x" in new_geometry:
            width, rest = new_geometry.split("x")
            if "+" in rest:
                height = rest.split("+")[0]
            else:
                height = rest
            if height == 1080:
                height = 1000
            print(f"[Debug]: {width}x{height}")
            player.resize_keep_aspect(width=int(width), height=int(height))

    root = BetterTk()
    root.geometry_bindings.append(resized)
    root.title("Video Player")
    root.bind_all("<KeyPress-f>", fullscreen)

    player = Player(root, bg="black")
    player.pack(fill="both", expand=True)
    if DEBUGGING:
        filepath = "vid.ts"
    else:
        filetypes = (("Video File", "*.ts;*.mp4"), ("All files", "*.*"))
        filepath = askopenfilename(initialdir=r"D:\videos\pokemon\videos",
                                   filetypes=filetypes,
                                   title="Select video file")
    if filepath != "":
        player.set_up(filepath)
        player.resize(width=1280)
        time.sleep(0.2) # Just to allow some of the frames to be read.
        player.start()

        if not DEBUGGING:
            root.mainloop()
