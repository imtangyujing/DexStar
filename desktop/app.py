from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from libs.common.url_utils import UnsupportedUrlError

from .core import DesktopDependencyError, DesktopDownloadError, DesktopDownloadResult, download_mp3


STEP_PROGRESS = {
    "步骤 1/5": 18,
    "步骤 2/5": 38,
    "步骤 3/5": 62,
    "步骤 4/5": 82,
    "步骤 5/5": 94,
}


@dataclass(frozen=True)
class DesktopBranding:
    window_title: str
    app_title: str
    subtitle: str
    cover_image_path: Path | None = None


DEFAULT_BRANDING = DesktopBranding(
    window_title="GRAB Desktop",
    app_title="GRAB Desktop",
    subtitle="粘贴 YouTube/B站链接，一键下载最高质量 MP3（含封面、命名、BPM）。",
)


class GrabDesktopApp:
    def __init__(self, root: tk.Tk, branding: DesktopBranding | None = None) -> None:
        self.root = root
        self.branding = branding or DEFAULT_BRANDING
        self.root.title(self.branding.window_title)
        self.root.geometry("920x720")
        self.root.minsize(820, 640)

        self.download_thread: threading.Thread | None = None

        self.url_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=str(Path.home() / "Downloads"))

        self.status_var = tk.StringVar(value="等待创建任务")
        self.progress_var = tk.IntVar(value=0)
        self.progress_text_var = tk.StringVar(value="0%")
        self.result_title_var = tk.StringVar(value="")
        self.result_line1_var = tk.StringVar(value="")
        self.result_line2_var = tk.StringVar(value="")
        self.cover_photo: tk.PhotoImage | None = None
        self.bg_canvas: tk.Canvas | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.root.configure(bg="#0f0f23")
        self._build_background()
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Root.TFrame", background="#0f0f23")
        style.configure("Root.TLabel", background="#0f0f23")
        style.configure("TopbarBrand.TLabel", background="#0f0f23", foreground="#f8fafc", font=("PingFang SC", 16, "bold"))
        style.configure("TopbarHint.TLabel", background="#0f0f23", foreground="#94a3b8", font=("PingFang SC", 11))
        style.configure("Chip.TLabel", background="#1b1c43", foreground="#a5b4fc", font=("PingFang SC", 10, "bold"), padding=(10, 5))
        style.configure(
            "Card.TFrame",
            background="#181a3a",
            borderwidth=0,
            relief="flat",
        )
        style.configure("Title.TLabel", background="#0f0f23", foreground="#f8fafc", font=("PingFang SC", 28, "bold"))
        style.configure("Sub.TLabel", background="#0f0f23", foreground="#94a3b8", font=("PingFang SC", 13))
        style.configure("CardTitle.TLabel", background="#181a3a", foreground="#cbd5e1", font=("PingFang SC", 11, "bold"))
        style.configure("CardText.TLabel", background="#181a3a", foreground="#f8fafc", font=("PingFang SC", 14))
        style.configure("ResultSuccess.TLabel", background="#181a3a", foreground="#22c55e", font=("PingFang SC", 17, "bold"))
        style.configure("ResultError.TLabel", background="#181a3a", foreground="#f87171", font=("PingFang SC", 17, "bold"))
        style.configure("ResultErrorText.TLabel", background="#181a3a", foreground="#fecaca", font=("PingFang SC", 14))
        style.configure(
            "Action.TButton",
            font=("PingFang SC", 15, "bold"),
            padding=(18, 14),
            foreground="#041307",
            background="#22c55e",
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Action.TButton",
            background=[("active", "#4ade80"), ("pressed", "#16a34a"), ("disabled", "#2c4b34")],
            foreground=[("disabled", "#9ca3af")],
        )
        style.configure(
            "Ghost.TButton",
            font=("PingFang SC", 12),
            padding=(12, 8),
            foreground="#dbeafe",
            background="#1f2560",
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#2b337f"), ("pressed", "#1e2559"), ("disabled", "#1a2148")],
            foreground=[("disabled", "#7f8fb1")],
        )
        style.configure(
            "Dark.TEntry",
            fieldbackground="#121739",
            background="#121739",
            foreground="#f8fafc",
            bordercolor="#121739",
            lightcolor="#121739",
            darkcolor="#121739",
            relief="flat",
        )
        style.configure(
            "Hero.Horizontal.TProgressbar",
            troughcolor="#0f1435",
            bordercolor="#0f1435",
            background="#22c55e",
            lightcolor="#4ade80",
            darkcolor="#16a34a",
        )

        container = ttk.Frame(self.root, padding=24, style="Root.TFrame")
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container, style="Root.TFrame")
        header.pack(fill=tk.X, pady=(2, 14))
        ttk.Label(header, text=self.branding.app_title, style="TopbarBrand.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text="Desktop MP3 Downloader", style="TopbarHint.TLabel").pack(side=tk.RIGHT)
        ttk.Label(container, text="Vibrant Audio Utility", style="Chip.TLabel").pack(anchor=tk.W, pady=(0, 12))

        self._render_cover(container)

        input_card = ttk.Frame(container, padding=18, style="Card.TFrame")
        input_card.pack(fill=tk.X, pady=(4, 0))

        ttk.Label(input_card, text="视频链接", style="CardTitle.TLabel").pack(anchor=tk.W)
        self.url_entry = ttk.Entry(input_card, textvariable=self.url_var, font=("PingFang SC", 15), style="Dark.TEntry")
        self.url_entry.pack(fill=tk.X, pady=(6, 12))

        ttk.Label(input_card, text="保存目录", style="CardTitle.TLabel").pack(anchor=tk.W)
        path_row = ttk.Frame(input_card, style="Card.TFrame")
        path_row.pack(fill=tk.X, pady=(6, 0))
        self.path_entry = ttk.Entry(path_row, textvariable=self.output_dir_var, font=("PingFang SC", 13), style="Dark.TEntry")
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.pick_button = ttk.Button(path_row, text="选择目录", style="Ghost.TButton", command=self._pick_output_dir)
        self.pick_button.pack(side=tk.LEFT, padx=(8, 0))

        self.action_card = ttk.Frame(container, padding=18, style="Card.TFrame")
        self.action_card.pack(fill=tk.X, pady=(14, 0))

        self.start_button = ttk.Button(self.action_card, text="创建任务并处理", style="Action.TButton", command=self._start_download)
        self.start_button.pack(fill=tk.X)

        self.progress_stage = ttk.Frame(self.action_card, style="Card.TFrame")

        status_head = ttk.Frame(self.progress_stage, style="Card.TFrame")
        status_head.pack(fill=tk.X)
        ttk.Label(status_head, text="处理状态", style="CardTitle.TLabel").pack(side=tk.LEFT)
        ttk.Label(status_head, textvariable=self.progress_text_var, style="CardTitle.TLabel").pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(
            self.progress_stage,
            mode="determinate",
            maximum=100,
            variable=self.progress_var,
            style="Hero.Horizontal.TProgressbar",
        )
        self.progress.pack(fill=tk.X, pady=(8, 10))
        ttk.Label(self.progress_stage, textvariable=self.status_var, style="CardText.TLabel").pack(anchor=tk.W)

        self.result_stage = ttk.Frame(self.action_card, style="Card.TFrame")
        self.result_title = ttk.Label(self.result_stage, textvariable=self.result_title_var, style="ResultSuccess.TLabel")
        self.result_title.pack(anchor=tk.W)
        self.result_line_row = ttk.Frame(self.result_stage, style="Card.TFrame")
        self.result_line_row.pack(fill=tk.X, pady=(6, 0))
        self.result_line1 = ttk.Label(self.result_line_row, textvariable=self.result_line1_var, style="CardText.TLabel")
        self.result_line1.pack(side=tk.LEFT, anchor=tk.W)
        self.result_line2 = ttk.Label(self.result_stage, textvariable=self.result_line2_var, style="CardText.TLabel")
        self.result_line2.pack(anchor=tk.W, pady=(4, 0))

        self.result_action_row = ttk.Frame(self.result_line_row, style="Card.TFrame")
        self.result_action_row.pack(side=tk.RIGHT)
        self.open_dir_button = ttk.Button(
            self.result_action_row,
            text="打开目录",
            style="Ghost.TButton",
            command=self._open_output_dir,
        )
        self.open_dir_button.pack(side=tk.LEFT)
        self.new_task_button = ttk.Button(
            self.result_action_row,
            text="新建任务",
            style="Ghost.TButton",
            command=self._reset_to_stage_one,
        )
        self.new_task_button.pack(side=tk.LEFT, padx=(8, 0))

    def _build_background(self) -> None:
        canvas = tk.Canvas(self.root, highlightthickness=0, bd=0, bg="#0f0f23")
        canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg_canvas = canvas
        self.root.bind("<Configure>", self._draw_glow_background)
        self._draw_glow_background()

    def _draw_glow_background(self, _event: object | None = None) -> None:
        if not self.bg_canvas:
            return
        canvas = self.bg_canvas
        width = max(canvas.winfo_width(), self.root.winfo_width(), 920)
        height = max(canvas.winfo_height(), self.root.winfo_height(), 720)
        canvas.delete("glow")
        canvas.create_rectangle(0, 0, width, height, fill="#0f0f23", outline="", tags="glow")
        canvas.create_oval(-260, -180, int(width * 0.58), int(height * 0.72), fill="#1e1b4b", outline="", stipple="gray25", tags="glow")
        canvas.create_polygon(
            -120,
            80,
            int(width * 0.22),
            -60,
            int(width * 0.40),
            int(height * 0.32),
            int(width * 0.16),
            int(height * 0.46),
            fill="#4338ca",
            outline="",
            smooth=True,
            splinesteps=24,
            stipple="gray50",
            tags="glow",
        )
        canvas.create_oval(int(width * 0.52), int(height * 0.44), width + 220, height + 180, fill="#1e1b4b", outline="", stipple="gray25", tags="glow")
        canvas.create_polygon(
            int(width * 0.70),
            int(height * 0.64),
            width + 120,
            int(height * 0.55),
            width + 60,
            height + 120,
            int(width * 0.62),
            height + 90,
            fill="#22c55e",
            outline="",
            smooth=True,
            splinesteps=20,
            stipple="gray50",
            tags="glow",
        )

    def _render_cover(self, container: ttk.Frame) -> None:
        cover_path = self.branding.cover_image_path
        if not cover_path:
            return
        if not cover_path.exists():
            return
        try:
            image = tk.PhotoImage(file=str(cover_path))
            max_width = 780
            max_height = 220
            scale_x = max(1, math.ceil(image.width() / max_width))
            scale_y = max(1, math.ceil(image.height() / max_height))
            scale = max(scale_x, scale_y)
            if scale > 1:
                image = image.subsample(scale, scale)
            self.cover_photo = image
            label = ttk.Label(container, image=self.cover_photo, style="Root.TLabel")
            label.pack(fill=tk.X, pady=(0, 12))
        except Exception:  # pragma: no cover
            return

    def _pick_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(Path.home()))
        if selected:
            self.output_dir_var.set(selected)

    def _append_log(self, line: str) -> None:
        if line:
            print(line)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _set_progress(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.progress_var.set(value)
        self.progress_text_var.set(f"{value}%")

    def _set_running(self, running: bool) -> None:
        if running:
            self.url_entry.configure(state=tk.DISABLED)
            self.path_entry.configure(state=tk.DISABLED)
            self.pick_button.configure(state=tk.DISABLED)
            self.new_task_button.configure(state=tk.DISABLED)
            self.open_dir_button.configure(state=tk.DISABLED)
        else:
            self.url_entry.configure(state=tk.NORMAL)
            self.path_entry.configure(state=tk.NORMAL)
            self.pick_button.configure(state=tk.NORMAL)
            self.new_task_button.configure(state=tk.NORMAL)
            self.open_dir_button.configure(state=tk.NORMAL)

    def _enter_stage_two(self) -> None:
        if self.start_button.winfo_manager():
            self.start_button.pack_forget()
        if self.result_stage.winfo_manager():
            self.result_stage.pack_forget()
        if not self.progress_stage.winfo_manager():
            self.progress_stage.pack(fill=tk.X)

    def _reset_to_stage_one(self) -> None:
        if self.download_thread and self.download_thread.is_alive():
            return
        if self.progress_stage.winfo_manager():
            self.progress_stage.pack_forget()
        if self.result_stage.winfo_manager():
            self.result_stage.pack_forget()
        if not self.start_button.winfo_manager():
            self.start_button.pack(fill=tk.X)
        self._set_progress(0)
        self._set_status("等待创建任务")
        self.result_title_var.set("")
        self.result_line1_var.set("")
        self.result_line2_var.set("")

    def _show_stage_three(self, success: bool, title: str, line1: str, line2: str = "") -> None:
        if self.progress_stage.winfo_manager():
            self.progress_stage.pack_forget()
        if self.start_button.winfo_manager():
            self.start_button.pack_forget()
        self.result_title_var.set(title)
        self.result_line1_var.set(line1)
        self.result_line2_var.set(line2)
        if title:
            if not self.result_title.winfo_manager():
                self.result_title.pack(anchor=tk.W, before=self.result_line_row)
        else:
            if self.result_title.winfo_manager():
                self.result_title.pack_forget()
        if success:
            self.result_title.configure(style="ResultSuccess.TLabel")
            self.result_line1.configure(style="CardText.TLabel")
            self.result_line2.configure(style="CardText.TLabel")
            if not self.result_action_row.winfo_manager():
                self.result_action_row.pack(side=tk.RIGHT)
        else:
            self.result_title.configure(style="ResultError.TLabel")
            self.result_line1.configure(style="ResultErrorText.TLabel")
            self.result_line2.configure(style="ResultErrorText.TLabel")
            if self.result_action_row.winfo_manager():
                self.result_action_row.pack_forget()
        if not self.result_stage.winfo_manager():
            self.result_stage.pack(fill=tk.X)

    def _start_download(self) -> None:
        if self.download_thread and self.download_thread.is_alive():
            self._set_status("已有任务在运行，请稍候。")
            return

        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入视频链接后再创建任务。")
            return

        output_dir = self.output_dir_var.get().strip() or str(Path.home() / "Downloads")
        self._enter_stage_two()
        self._set_running(True)
        self._set_progress(5)
        self._set_status("任务已创建，准备处理...")
        self._append_log(f"开始处理：{url} -> {output_dir}")

        self.download_thread = threading.Thread(
            target=self._run_download,
            args=(url, output_dir),
            daemon=True,
        )
        self.download_thread.start()

    def _run_download(self, url: str, output_dir: str) -> None:
        try:
            result = download_mp3(url, output_dir=output_dir, on_output=self._enqueue_log)
            self.root.after(0, lambda r=result: self._on_success(r))
        except UnsupportedUrlError:
            self.root.after(0, lambda: self._on_error("仅支持 YouTube / B站链接。"))
        except DesktopDependencyError as exc:
            self.root.after(0, lambda m=f"{exc}。请先安装后再试。": self._on_error(m))
        except DesktopDownloadError as exc:
            self.root.after(0, lambda m=str(exc): self._on_error(m))
        except Exception as exc:  # pragma: no cover
            self.root.after(0, lambda m=f"未知错误：{exc}": self._on_error(m))

    def _enqueue_log(self, line: str) -> None:
        self.root.after(0, lambda l=line: self._handle_worker_log(l))

    def _handle_worker_log(self, line: str) -> None:
        self._append_log(line)
        for marker, value in STEP_PROGRESS.items():
            if marker in line:
                self._set_progress(value)
                stage_text = line.split("：", 1)[-1].strip() if "：" in line else line
                self._set_status(stage_text or "处理中...")
                return
        if "失败" in line:
            self._set_status(line)

    def _on_success(self, result: DesktopDownloadResult) -> None:
        self._set_running(False)
        self._set_progress(100)
        self._show_stage_three(
            success=True,
            title="",
            line1=f"文件名：{result.final_filename}",
            line2="",
        )
        self._append_log(f"完成：{result.file_path}")

    def _on_error(self, message: str) -> None:
        self._set_running(False)
        self._set_progress(0)
        self._show_stage_three(
            success=False,
            title="下载失败",
            line1=f"错误：{message}",
            line2="请检查链接或稍后重试。",
        )
        self._append_log(message)

    def _open_output_dir(self) -> None:
        target = self.output_dir_var.get().strip() or str(Path.home() / "Downloads")
        subprocess.run(["open", target], check=False)


def run_app(branding: DesktopBranding | None = None) -> None:
    root = tk.Tk()
    GrabDesktopApp(root, branding=branding)
    root.mainloop()


def main() -> None:
    run_app()


if __name__ == "__main__":
    main()
