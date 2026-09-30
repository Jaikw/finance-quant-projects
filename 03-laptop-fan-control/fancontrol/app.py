"""Tkinter UI: live temperatures, a history graph, an RPM slider and an Auto button."""
from __future__ import annotations

import atexit
import ctypes
import queue
import sys
import tkinter as tk
from collections import deque
from tkinter import ttk

from .controller import AUTO, FanController, HardwareWorker, State
from .core import RPM_MAX, RPM_MIN, RPM_STEP

BG, CARD, TEXT, MUTED = "#14171c", "#1d2128", "#e8eaed", "#8b93a1"
ACCENT, GREEN, AMBER, RED = "#4c9aff", "#3ecf8e", "#f5a524", "#ff5d5d"

HISTORY_POINTS = 150
APPLY_DELAY_MS = 350  # wait for the slider to settle before writing to the fan


def temp_color(celsius: float) -> str:
    return GREEN if celsius < 60 else AMBER if celsius < 80 else RED


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return True  # not Windows: nothing to warn about


class App:
    def __init__(self, root: tk.Tk, worker: HardwareWorker) -> None:
        self.root, self.worker = root, worker
        self.controller = worker.controller
        self.history: deque[float] = deque(maxlen=HISTORY_POINTS)
        self._apply_job: str | None = None
        self._dragging = False

        root.title("Laptop Thermals")
        root.configure(bg=BG)
        root.geometry("760x820")
        root.minsize(620, 680)
        self._style()
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._pump()

    # -- construction -----------------------------------------------------------
    def _style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                        borderwidth=0, bordercolor=CARD, lightcolor=CARD, darkcolor=CARD,
                        rowheight=26, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=BG, foreground=MUTED, borderwidth=0,
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", CARD)], foreground=[("selected", TEXT)])
        style.configure("Vertical.TScrollbar", background="#2a303a", troughcolor=CARD, borderwidth=0,
                        bordercolor=CARD, lightcolor="#2a303a", darkcolor="#2a303a", arrowcolor=MUTED)
        style.map("Vertical.TScrollbar", background=[("active", "#3a4250")])

    def _label(self, parent, text="", size=10, color=TEXT, bold=False, **kw) -> tk.Label:
        return tk.Label(parent, text=text, bg=parent["bg"], fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kw)

    def _build(self) -> None:
        pad = {"padx": 16}
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", pady=(14, 6), **pad)
        self._label(header, "Laptop Thermals", 18, bold=True).pack(side="left")
        self._label(header, self.controller.source.name, 9, MUTED).pack(side="right")

        self.banner_slot = tk.Frame(self.root, bg=BG)
        self.banner_slot.pack(fill="x", **pad)
        self.banner = tk.Label(self.banner_slot, text="", bg=AMBER, fg="#241a00", anchor="w", justify="left",
                               wraplength=700, font=("Segoe UI", 10, "bold"), padx=12, pady=8)

        # Headline temperature + fan speed
        top = tk.Frame(self.root, bg=CARD)
        top.pack(fill="x", pady=6, **pad)
        left = tk.Frame(top, bg=CARD)
        left.pack(side="left", padx=20, pady=14)
        self.temp_value = self._label(left, "--", 54, bold=True)
        self.temp_value.pack(anchor="w")
        self.temp_name = self._label(left, "waiting for sensors", 10, MUTED)
        self.temp_name.pack(anchor="w")

        right = tk.Frame(top, bg=CARD)
        right.pack(side="right", padx=20, pady=14)
        self.fan_value = self._label(right, "--", 30, bold=True)
        self.fan_value.pack(anchor="e")
        self.fan_caption = self._label(right, "fan speed", 10, MUTED)
        self.fan_caption.pack(anchor="e")

        # History graph
        self.graph = tk.Canvas(self.root, height=170, bg=CARD, highlightthickness=0)
        self.graph.pack(fill="x", pady=6, **pad)
        self.graph.bind("<Configure>", lambda _e: self._draw_graph())

        # Fan control
        ctl = tk.Frame(self.root, bg=CARD)
        ctl.pack(side="bottom", fill="x", pady=(6, 14), **pad)
        row = tk.Frame(ctl, bg=CARD)
        row.pack(fill="x", padx=20, pady=(14, 0))
        self._label(row, "Fan control", 12, bold=True).pack(side="left")
        self.mode_label = self._label(row, "", 10, MUTED)
        self.mode_label.pack(side="right")

        self.rpm_readout = self._label(ctl, f"{RPM_MIN:,} RPM", 22, bold=True)
        self.rpm_readout.pack(anchor="w", padx=20, pady=(6, 0))

        self.slider = tk.Scale(
            ctl, from_=RPM_MIN, to=RPM_MAX, resolution=RPM_STEP, orient="horizontal", showvalue=False,
            bg=ACCENT, fg=TEXT, troughcolor=BG, activebackground="#6aaeff", highlightthickness=0,
            bd=0, sliderlength=24, width=22, sliderrelief="flat", command=self._on_slider,
        )
        self.slider.pack(fill="x", padx=20, pady=(4, 0))
        # Only real input counts as the user choosing a speed. (The slider's own `command`
        # callback also fires for programmatic .set() calls - asynchronously - so it must
        # never be used to decide that the user wants manual mode.)
        self.slider.bind("<ButtonPress-1>", lambda _e: setattr(self, "_dragging", True))
        self.slider.bind("<ButtonRelease-1>", self._on_release)
        self.slider.bind("<KeyRelease>", self._on_key)

        ends = tk.Frame(ctl, bg=CARD)
        ends.pack(fill="x", padx=20)
        self._label(ends, f"{RPM_MIN:,} RPM", 9, MUTED).pack(side="left")
        self._label(ends, f"{RPM_MAX:,} RPM", 9, MUTED).pack(side="right")

        self.auto_button = tk.Button(
            ctl, text="Auto  (system default)", command=self._on_auto, relief="flat", bd=0,
            font=("Segoe UI", 11, "bold"), padx=16, pady=8, cursor="hand2",
        )
        self.auto_button.pack(anchor="w", padx=20, pady=(12, 6))
        self.control_note = self._label(ctl, "", 9, MUTED, anchor="w", justify="left", wraplength=680)
        self.control_note.pack(fill="x", padx=20, pady=(0, 14))

        # All temperature sensors
        list_frame = tk.Frame(self.root, bg=CARD)
        list_frame.pack(fill="both", expand=True, pady=6, **pad)
        self.tree = ttk.Treeview(list_frame, columns=("group", "temp"), show="tree headings", selectmode="none", height=6)
        self.tree.heading("#0", text="Sensor", anchor="w")
        self.tree.heading("group", text="Component", anchor="w")
        self.tree.heading("temp", text="Temp", anchor="e")
        self.tree.column("#0", width=200, anchor="w")
        self.tree.column("group", width=280, anchor="w")
        self.tree.column("temp", width=90, anchor="e")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._render_mode(AUTO, None)

    # -- slider / buttons ---------------------------------------------------------
    def _on_slider(self, value: str) -> None:
        self.rpm_readout.configure(text=f"{int(float(value)):,} RPM")

    def _on_release(self, _event) -> None:
        self._dragging = False
        if self.controller.fan.available:
            self._schedule_apply()

    def _on_key(self, event) -> None:
        if event.keysym in ("Left", "Right", "Up", "Down", "Prior", "Next", "Home", "End") \
                and self.controller.fan.available:
            self._schedule_apply()

    def _schedule_apply(self) -> None:
        if self._apply_job is not None:
            self.root.after_cancel(self._apply_job)
        self._apply_job = self.root.after(APPLY_DELAY_MS, self._apply)

    def _apply(self) -> None:
        self._apply_job = None
        self.worker.set_manual(self.slider.get())

    def _on_auto(self) -> None:
        if self._apply_job is not None:
            self.root.after_cancel(self._apply_job)
            self._apply_job = None
        self.worker.set_auto()

    # -- state -> widgets ---------------------------------------------------------
    def _pump(self) -> None:
        state = None
        try:
            while True:
                state = self.worker.states.get_nowait()
        except queue.Empty:
            pass
        if state is not None:
            self._render(state)
        self.root.after(100, self._pump)

    def _render(self, st: State) -> None:
        snap = st.snapshot
        if snap is not None:
            head = snap.headline
            if head is not None:
                self.temp_value.configure(text=f"{head.celsius:.0f}°C", fg=temp_color(head.celsius))
                self.temp_name.configure(text=f"{head.name}  ·  {head.group}" if head.group else head.name)
                self.history.append(head.celsius)
            rpm = snap.fan_rpm
            self.fan_value.configure(text=f"{rpm:,.0f} RPM" if rpm is not None else "n/a")
            self.fan_caption.configure(
                text="fan speed" if rpm is not None else "this laptop doesn't expose a fan tachometer"
            )
            self._render_sensor_list(snap)
            self._draw_graph()
            if st.mode == AUTO and rpm is not None and not self._dragging and self._apply_job is None:
                self._set_slider(min(RPM_MAX, max(RPM_MIN, rpm)))  # show the fan's actual speed

        self._render_mode(st.mode, st.target_rpm)
        self.control_note.configure(text=st.control_note)
        self._render_notice(st.notice, st.can_control)

    def _render_mode(self, mode: str, target: int | None) -> None:
        can = self.controller.fan.available
        manual = mode != AUTO
        self.mode_label.configure(
            text=f"MANUAL · {target:,} RPM target" if manual and target else "AUTO · system controlled",
            fg=AMBER if manual else GREEN,
        )
        self.auto_button.configure(
            state="normal" if (manual and can) else "disabled",
            bg=ACCENT if manual else BG, fg="#ffffff" if manual else MUTED,
            activebackground="#6aaeff", activeforeground="#ffffff", disabledforeground=MUTED,
        )
        self.slider.configure(state="normal" if can else "disabled")
        if manual and target and not self._dragging and self._apply_job is None:
            self._set_slider(target)

    def _set_slider(self, rpm: float) -> None:
        self.slider.set(rpm)
        self.rpm_readout.configure(text=f"{int(self.slider.get()):,} RPM")

    def _render_notice(self, notice: str, can_control: bool) -> None:
        if not notice and not can_control:
            notice = "Fan control isn't available on this laptop - showing temperatures only."
        if not notice and not _is_admin():
            notice = "Not running as Administrator - some sensors may be missing."
        if notice:
            self.banner.configure(text=notice)
            self.banner.pack(fill="x", pady=(0, 8))
        else:
            self.banner.pack_forget()

    def _render_sensor_list(self, snap) -> None:
        wanted = {}
        for t in sorted(snap.temps, key=lambda t: t.celsius, reverse=True):
            wanted[f"{t.group}|{t.name}"] = t
        existing = set(self.tree.get_children())
        for iid in existing - wanted.keys():
            self.tree.delete(iid)
        for index, (iid, t) in enumerate(wanted.items()):
            values = (t.group, f"{t.celsius:.1f} °C")
            if iid in existing:
                self.tree.item(iid, text=t.name, values=values)
            else:
                self.tree.insert("", "end", iid=iid, text=t.name, values=values)
            self.tree.move(iid, "", index)

    def _draw_graph(self) -> None:
        g = self.graph
        g.delete("all")
        w, h = g.winfo_width(), g.winfo_height()
        if w < 50 or h < 50:
            return
        left, right, top, bottom = 44, 12, 12, 22
        data = list(self.history)
        lo = min(30.0, min(data, default=30.0) - 5)
        hi = max(100.0, max(data, default=100.0) + 5)

        def y(v: float) -> float:
            return top + (hi - v) / (hi - lo) * (h - top - bottom)

        tick = int(lo // 10 * 10) + 10
        while tick < hi:
            g.create_line(left, y(tick), w - right, y(tick), fill="#2a303a")
            g.create_text(left - 8, y(tick), text=f"{tick}°", fill=MUTED, anchor="e", font=("Segoe UI", 8))
            tick += 10
        limit = self.controller.safety_temp
        if lo < limit < hi:
            g.create_line(left, y(limit), w - right, y(limit), fill=RED, dash=(4, 4))
            g.create_text(w - right - 4, y(limit) - 8, text="safety limit", fill=RED, anchor="e", font=("Segoe UI", 8))
        g.create_text(left, h - 8, text=f"last {HISTORY_POINTS} readings", fill=MUTED, anchor="w", font=("Segoe UI", 8))
        if len(data) >= 2:
            step = (w - left - right) / (HISTORY_POINTS - 1)
            x0 = w - right - step * (len(data) - 1)
            points = [c for i, v in enumerate(data) for c in (x0 + i * step, y(v))]
            g.create_line(*points, fill=temp_color(data[-1]), width=2, smooth=True)

    # -- shutdown -----------------------------------------------------------------
    def close(self) -> None:
        self.worker.stop()  # the worker returns the fan to Auto as it exits
        self.worker.join(timeout=5)
        self.root.destroy()


def run(controller: FanController, interval: float = 1.0) -> None:
    try:  # crisp text on high-DPI Windows displays
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    worker = HardwareWorker(controller, interval)
    atexit.register(controller.shutdown)  # last line of defence if the process dies oddly
    root = tk.Tk()
    App(root, worker)
    worker.start()
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        if worker.is_alive():
            worker.stop()
            worker.join(timeout=5)
