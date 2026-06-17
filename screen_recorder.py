import tkinter as tk
from tkinter import filedialog, ttk
import cv2
import numpy as np
import mss
import threading
import time
import os
import subprocess
from datetime import datetime
from PIL import Image, ImageTk
from imageio_ffmpeg import get_ffmpeg_exe


class RegionSelector:
    def __init__(self, parent):
        self.parent = parent
        self.result = None

        with mss.MSS() as sct:
            vm = sct.monitors[0]
            raw = sct.grab(vm)
            self.screen_img = Image.frombytes("RGB", raw.size, raw.rgb)
            self.screen_w, self.screen_h = raw.size
            self.vm_left, self.vm_top = vm["left"], vm["top"]

        self.tk_img = ImageTk.PhotoImage(self.screen_img)

        self.top = tk.Toplevel(parent)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.geometry(f"{self.screen_w}x{self.screen_h}+{self.vm_left}+{self.vm_top}")

        self.canvas = tk.Canvas(self.top, cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

        self.rect_id = None
        self.info_id = None
        self.start_x = None
        self.start_y = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.top.bind("<Escape>", lambda e: self.cancel())

        self.canvas.create_text(
            self.screen_w // 2, 30,
            text="Trascina per selezionare l\u2019area  |  ESC per annullare",
            fill="white", font=("Segoe UI", 15, "bold"),
        )

        self.top.grab_set()
        self.top.focus_force()
        self.top.update()

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        if self.info_id:
            self.canvas.delete(self.info_id)
        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#00aaff", width=2,
        )

    def on_drag(self, event):
        if not self.rect_id:
            return
        self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)
        if self.info_id:
            self.canvas.delete(self.info_id)
            self.info_id = None
        w = abs(event.x - self.start_x)
        h = abs(event.y - self.start_y)
        cx = (self.start_x + event.x) // 2
        cy = (self.start_y + event.y) // 2
        self.info_id = self.canvas.create_text(
            cx, max(cy, 50),
            text=f"{w} \u00d7 {h}",
            fill="#00aaff", font=("Segoe UI", 14, "bold"),
        )

    def on_release(self, event):
        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x, event.y
        x = min(x1, x2) + self.vm_left
        y = min(y1, y2) + self.vm_top
        w = abs(x2 - x1)
        h = abs(y2 - y1)

        if w > 10 and h > 10:
            self.result = (x, y, w, h)
        self.top.destroy()

    def cancel(self):
        self.result = None
        self.top.destroy()

    def get_region(self):
        self.parent.wait_window(self.top)
        return self.result


class ScreenRecorder:
    QUALITY_MAP = {"Alta (CRF 18)": 18, "Media (CRF 23)": 23, "Bassa (CRF 28)": 28}

    def __init__(self, root):
        self.root = root
        self.root.title("Screen Recorder")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1a1a1a")
        self.root.geometry("280x200")
        self.root.resizable(False, False)

        self.recording = False
        self.region = None
        self.thread = None
        self.frames = []
        self.sct = mss.MSS()
        self._ffmpeg = None
        self._drag_data = {"x": 0, "y": 0}

        self.setup_ui()

    def _start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _do_drag(self, event):
        x = self.root.winfo_x() + event.x - self._drag_data["x"]
        y = self.root.winfo_y() + event.y - self._drag_data["y"]
        self.root.geometry(f"+{x}+{y}")

    def setup_ui(self):
        C = {"bg": "#1a1a1a", "fg": "#e0e0e0", "accent": "#d32f2f",
             "input": "#2a2a2a", "disabled": "#444", "muted": "#888"}

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=C["bg"], foreground=C["fg"],
                        fieldbackground=C["input"], selectbackground=C["accent"])
        style.configure("TFrame", background=C["bg"])
        style.configure("TLabel", background=C["bg"], foreground=C["fg"])
        style.map("TLabel", foreground=[("disabled", C["muted"])])
        style.configure("Red.TButton", background=C["accent"], foreground="white",
                        bordercolor=C["accent"], focuscolor="none", padding=(8, 4))
        style.map("Red.TButton",
            background=[("active", "#b71c1c"), ("disabled", C["disabled"])],
            foreground=[("disabled", "#777")])
        style.configure("TCombobox", fieldbackground=C["input"], background=C["input"],
                        foreground=C["fg"], arrowcolor=C["fg"], padding=(4, 2))
        style.map("TCombobox", fieldbackground=[("readonly", C["input"])])
        style.configure("TSpinbox", fieldbackground=C["input"], background=C["input"],
                        foreground=C["fg"], arrowcolor=C["fg"], padding=(4, 2))
        style.map("TSpinbox", fieldbackground=[("readonly", C["input"])])

        title_bar = tk.Frame(self.root, bg="#222", height=28)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        title_bar.bind("<ButtonPress-1>", self._start_drag)
        title_bar.bind("<B1-Motion>", self._do_drag)

        close_btn = tk.Label(title_bar, text="\u2715", fg=C["muted"], bg="#222",
                              font=("Segoe UI", 11), cursor="hand2")
        close_btn.pack(side="right", padx=(0, 8))
        close_btn.bind("<ButtonRelease-1>", lambda e: self.root.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=C["accent"]))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=C["muted"]))

        title_text = tk.Label(title_bar, text="SCREEN RECORDER",
                               font=("Segoe UI", 10, "bold"),
                               fg=C["accent"], bg="#222")
        title_text.pack(side="left", padx=(8, 0))
        title_text.bind("<ButtonPress-1>", self._start_drag)
        title_text.bind("<B1-Motion>", self._do_drag)

        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)

        row_fps = ttk.Frame(frame)
        row_fps.pack(fill="x", pady=1)
        ttk.Label(row_fps, text="FPS").pack(side="left")
        self.fps_spin = ttk.Spinbox(row_fps, from_=1, to=60, width=5)
        self.fps_spin.set(20)
        self.fps_spin.pack(side="right")

        row_qual = ttk.Frame(frame)
        row_qual.pack(fill="x", pady=1)
        ttk.Label(row_qual, text="Qualit\u00e0").pack(side="left")
        self.quality_combo = ttk.Combobox(row_qual, values=list(self.QUALITY_MAP.keys()),
                                           state="readonly", width=11)
        self.quality_combo.set("Alta (CRF 18)")
        self.quality_combo.pack(side="right")

        self.region_btn = ttk.Button(frame, text="SELEZIONA AREA",
                                      command=self.select_region, style="Red.TButton")
        self.region_btn.pack(fill="x", pady=(6, 1))

        self.region_label = tk.Label(frame, text="Nessuna area selezionata",
                                      fg=C["muted"], bg=C["bg"], font=("Segoe UI", 9))
        self.region_label.pack(anchor="center")

        self.record_btn = ttk.Button(frame, text="AVVIA REGISTRAZIONE",
                                      command=self.toggle_recording,
                                      state="disabled", style="Red.TButton")
        self.record_btn.pack(fill="x", pady=(4, 3))

        self.status_label = tk.Label(frame, text="Pronto",
                                      fg=C["muted"], bg=C["bg"], font=("Segoe UI", 9))
        self.status_label.pack(anchor="center")

    def select_region(self):
        selector = RegionSelector(self.root)
        region = selector.get_region()
        self.root.lift()

        if region:
            self.region = region
            x, y, w, h = region
            self.region_label.config(
                text=f"Area: ({x}, {y})  {w}\u00d7{h}",
                fg="#d32f2f"
            )
            self.record_btn.config(state="normal")

    def toggle_recording(self):
        if not self.recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        if not self.region:
            return

        self.recording = True
        self.frames = []
        self.record_btn.config(text="Arresta Registrazione")
        self.status_label.config(text="Registrazione in corso...", fg="#d32f2f")

        self.thread = threading.Thread(target=self._record, daemon=True)
        self.thread.start()

    def _record(self):
        x, y, w, h = self.region
        w -= w % 2
        h -= h % 2
        monitor = {"top": y, "left": x, "width": w, "height": h}
        self._record_start = time.perf_counter()

        while self.recording:
            img = self.sct.grab(monitor)
            frame = np.array(img)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            self.frames.append(frame)

    def stop_recording(self):
        self.recording = False

        if self.thread:
            self.thread.join(timeout=10)

        if not self.frames:
            self.status_label.config(text="Nessun frame registrato", fg="#555")
            self.record_btn.config(text="Avvia Registrazione")
            return

        default_name = f"registrazione_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("Video MP4", "*.mp4"), ("Tutti i file", "*.*")],
            initialfile=default_name,
        )

        if not file_path:
            self._after_stop()
            return

        self.status_label.config(text="Salvataggio video in corso...", fg="#555")
        self.root.update()

        h, w = self.frames[0].shape[:2]
        duration = time.perf_counter() - self._record_start
        actual_fps = max(1, round(len(self.frames) / max(duration, 0.01)))

        crf = self.QUALITY_MAP[self.quality_combo.get()]
        ok = self._encode_ffmpeg(file_path, w, h, actual_fps, crf)

        if not ok:
            self.status_label.config(text="Errore codifica video", fg="#d32f2f")
            self._after_stop()
            return

        mb = os.path.getsize(file_path) / (1024 * 1024)
        self.status_label.config(
            text=f"Salvato: {os.path.basename(file_path)}  ({mb:.1f} MB)",
            fg="#2e7d32"
        )
        self._after_stop()

    def _encode_ffmpeg(self, file_path, w, h, fps, crf):
        if self._ffmpeg is None:
            try:
                self._ffmpeg = get_ffmpeg_exe()
            except Exception:
                self._ffmpeg = False

        if self._ffmpeg:
            try:
                proc = subprocess.Popen(
                    [self._ffmpeg, "-y",
                     "-f", "rawvideo",
                     "-vcodec", "rawvideo",
                     "-s", f"{w}x{h}",
                     "-pix_fmt", "bgr24",
                     "-r", str(fps),
                     "-i", "-",
                     "-c:v", "libx264",
                     "-crf", str(crf),
                     "-preset", "medium",
                     "-pix_fmt", "yuv420p",
                     file_path],
                    stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
                for frame in self.frames:
                    proc.stdin.write(frame.tobytes())
                proc.stdin.close()
                proc.wait()
                return True
            except Exception:
                pass

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(file_path, fourcc, fps, (w, h))
        if not out.isOpened():
            return False
        for frame in self.frames:
            out.write(frame)
        out.release()
        return True

    def _after_stop(self):
        self.frames.clear()
        self.record_btn.config(text="Avvia Registrazione", state="normal")


if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenRecorder(root)
    root.mainloop()
