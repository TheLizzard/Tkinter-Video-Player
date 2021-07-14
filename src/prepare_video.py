from tkinter.filedialog import askopenfilename
from threading import Thread
import tkinter as tk
import time
import os

from libraries.bettertk import BetterTk
from libraries.terminal import Terminal


WIDGET_KWARGS = dict(bg="black", fg="white")
THREADS = 10


class App:
    def __init__(self):
        self.selected_files = []
        self.preparing = False

        self.root = BetterTk()
        self.root.bind_all("<Escape>", self.stop)
        clear_button = tk.Button(self.root, text="Clear cache", command=self.clear_cache, **WIDGET_KWARGS)
        clear_button.pack(fill="x")

        select_files = tk.Button(self.root, text="Select video files", command=self.select_video_files, **WIDGET_KWARGS)
        select_files.pack(fill="x")

        self.selected_files_text = tk.Text(self.root, height=1, width=30, state="disabled", **WIDGET_KWARGS)
        self.selected_files_text.pack(fill="x", expand=True)

        prepare_files = tk.Button(self.root, text="Prepare files", command=self.prepare_files, **WIDGET_KWARGS)
        prepare_files.pack(fill="x")

        self.var = tk.BooleanVar(self.root)
        check_button = tk.Checkbutton(root, text="Video", variable=self.var,
                                      relief="flat", activebackground="black",
                                      activeforeground="white",
                                      electcolor="black", **WIDGET_KWARGS)
        # check_button.pack()

        clear_button = tk.Button(self.root, text="Clear", command=self.clear_terminal, **WIDGET_KWARGS)
        clear_button.pack(fill="x")

        self.terminal = Terminal(self.root, height=5, width=120,
                                 keep_only_last_line=True,
                                 font=("DejaVu Sans Mono", 10))
        self.terminal.pack(fill="both", expand=True)

    def clear_terminal(self) -> None:
        self.terminal.clear()

    def stop(self, event:tk.Event=None) -> None:
        self.preparing = False
        self.terminal.kill()

    def select_video_files(self) -> None:
        selected_files = list(self.get_video_files())
        self.selected_files.extend(selected_files)
        self.update_selected_files()

    def update_selected_files(self) -> None:
        self.selected_files_text.config(state="normal")
        self.selected_files_text.delete("0.0", "end")
        self.selected_files_text.insert("end", "\n".join(self.selected_files))
        self.selected_files_text.config(height=len(self.selected_files))
        self.selected_files_text.config(state="disabled")

    def prepare_files(self) -> None:
        if self.preparing:
            return None
        self.preparing = True
        self._prepare_files(True)

    def _prepare_files(self, first:bool=False) -> None:
        if (self.terminal.poll() is None) and (not first):
            self.selected_files.insert(0, self.file)
            self.update_selected_files()
            self.preparing = False
            return None
        if not self.preparing:
            self.terminal.write("[Debug]: Stopping\n", tag="error")
        if len(self.selected_files) > 0:
            self.file = self.selected_files.pop(0)
            soundfile = self.file.replace("\\", "/").split("/")[-1]
            soundfile = f"tmp/{soundfile}_sound.mp3"

            file_pretty_print = self.file.replace("/", "\\")
            soundfile_pretty_print = soundfile.replace("/", "\\")
            self.terminal.write(f"Preparing: {file_pretty_print} => " \
                                f"{soundfile_pretty_print}\n", tag="error")

            pipe = self.terminal.stdout[1]
            command = f"ffmpeg -y -v 2 -stats -threads {THREADS} " \
                      f"-i {self.file} -vcodec mpeg1video -acodec " \
                      f"libmp3lame -intra {soundfile}"

            #width = 1826
            #command = f"ffmpeg -y -v 2 -stats -threads {THREADS} -i " \
            #          f"{self.file} -vf " \
            #          f"scale=\"{width}:-1\" {soundfile}.ts"

            self.terminal.run(command, self._prepare_files)
            self.update_selected_files()
        else:
            self.terminal.write("[Debug]: Done\n", tag="error")
            self.preparing = False

    def get_video_files(self) -> tuple:
        filetypes = (("Video File", "*.ts;*.mp4"), ("All files", "*.*"))
        filepath = askopenfilename(initialdir=r"D:\videos\pokemon\videos",
                                   filetypes=filetypes, multiple=True,
                                   title="Select video files")
        return filepath

    def clear_cache(self) -> None:
        self.delete_mp3s("tmp/")

    def mainloop(self) -> None:
        self.root.mainloop()

    def delete_mp3s(self, folder:str) -> None:
        """
        Delete all `.mp3` files from `folder` and all of its subdirs
        """
        for file in os.listdir(folder):
            if file == "vid.ts_sound.mp3":
                continue
            if file[-10:] == "_sound.mp3":
                file_path = os.path.join(folder, file)
                file_path_pprint = file_path.replace("/", "\\")
                self.terminal.write(f"[Debug]: Deleting {file_path_pprint}\n",
                                    tag="error")
                os.remove(file_path)


if __name__ == "__main__":
    app = App()
    app.mainloop()
