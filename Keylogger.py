"""
pro_keylogger_visible_ask.py
Consent-first GUI key capture & dashboard (non-stealth).
Branding: Akanksha (ASK)
Default password: ASK123  (change in SETTINGS tab)
"""

import os
import sys
import time
import threading
import queue
import csv
from datetime import datetime, date
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from PIL import Image, ImageDraw, ImageFont
from pynput import keyboard
import pandas as pd
import psutil

# -------------------------
# CONFIGURATION 
# -------------------------
APP_NAME = "Pro Key Logger - Akanksha (ASK)"
BRAND = "Akanksha (ASK)"
DEFAULT_PASSWORD = "ASK123"  
LOG_DIR = Path.home() / "Documents" / "ASK_KeyLogger"
LOG_DIR.mkdir(parents=True, exist_ok=True)
RAW_LOG = LOG_DIR / "key_log_raw.txt"     
DAILY_DIR = LOG_DIR / "Daily_Reports"
DAILY_DIR.mkdir(exist_ok=True)
MAX_RAW_SIZE_BYTES = 500 * 1024 

# UI theme colors:
BG_COLOR = "#0a0a0a"    
MAROON = "#8b0000"      
CYAN = "#00ffff"        
FONT_MONO = ("Courier New", 10)


q = queue.Queue()

# -------------------------
# Helper: create small icons 
# -------------------------
def ensure_icons():
    ico_dir = LOG_DIR / "assets"
    ico_dir.mkdir(exist_ok=True)
    icon_active = ico_dir / "ask_active.png"
    icon_paused = ico_dir / "ask_paused.png"
    if not icon_active.exists() or not icon_paused.exists():
       
        for path, label, fill in ((icon_active, "A", "#00ff88"), (icon_paused, "A", "#ff6666")):
            img = Image.new("RGBA", (64, 64), (0,0,0,0))
            draw = ImageDraw.Draw(img)
           
            draw.rounded_rectangle((2,2,62,62), radius=12, fill=(12,12,12,255), outline=fill)
         
        try:
                 fnt = ImageFont.truetype("arial.ttf", 28)
        except Exception:
                 fnt = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), label, font=fnt)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]


        width, height = img.size
        draw.text(((width - w) / 2, (height - h) / 2), label , font=fnt, fill="white")

        img.save(path)
        return str(icon_active), str(icon_paused)

ICON_ACTIVE_PATH, ICON_PAUSED_PATH = ensure_icons()

# -------------------------
# Rotation & daily CSV helpers
# -------------------------
def rotate_raw_log_if_needed(max_size=MAX_RAW_SIZE_BYTES):
    try:
        if RAW_LOG.exists() and RAW_LOG.stat().st_size >= max_size:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_name = LOG_DIR / f"key_log_raw_{ts}.txt"
            RAW_LOG.rename(new_name)
       
            return f"Rotated raw log -> {new_name.name}"
    except Exception as e:
        return f"Rotation error: {e}"
    return None

def append_to_raw_log(ts, key):
    try:
        with open(RAW_LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts}: {key}\n")
    except Exception as e:
        print("Write error:", e)

def append_daily_csv(ts, key):
    try:
        filename = DAILY_DIR / f"log_{date.today().isoformat()}.csv"
        header = not filename.exists()
        with open(filename, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if header:
                writer.writerow(["Timestamp", "Key Pressed"])
            writer.writerow([ts, key])
    except Exception as e:
        print("Daily CSV error:", e)

# -------------------------
# Key capture worker (only active when start_recording invoked)
# -------------------------
class KeyCapture:
    def __init__(self, out_queue):
        self.listener = None
        self.running = False
        self.q = out_queue
        self._lock = threading.Lock()

    def _readable_key(self, key):
        try:
            return str(key.char)
        except AttributeError:
            mapping = {
                keyboard.Key.space: "[SPACE]",
                keyboard.Key.enter: "[ENTER]",
                keyboard.Key.backspace: "[BACKSPACE]",
                keyboard.Key.tab: "[TAB]",
                keyboard.Key.shift: "[SHIFT]",
                keyboard.Key.shift_r: "[SHIFT_R]",
                keyboard.Key.ctrl_l: "[CTRL_L]",
                keyboard.Key.ctrl_r: "[CTRL_R]",
                keyboard.Key.alt_l: "[ALT_L]",
                keyboard.Key.alt_r: "[ALT_R]",
                keyboard.Key.esc: "[ESC]"
            }
            return mapping.get(key, f"[{str(key)}]")

    def _on_press(self, key):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        k = self._readable_key(key)
  
        try:
            self.q.put((ts, k))
        except Exception:
            pass
     
        append_to_raw_log(ts, k)
        append_daily_csv(ts, k)
  
        rotate_raw_log_if_needed()

    def start(self):
        with self._lock:
            if self.running:
                return
            self.listener = keyboard.Listener(on_press=self._on_press)
            self.listener.start()
            self.running = True

    def stop(self):
        with self._lock:
            if not self.running:
                return
            try:
                if self.listener:
                    self.listener.stop()
            except Exception:
                pass
            self.running = False


capture = KeyCapture(q)

# -------------------------
# GUI Application
# -------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
   
        self.root.geometry("1100x700")
        self.root.minsize(1000, 600)

    
        self.style = tb.Style(theme='darkly')  
   
        self.root.configure(bg=BG_COLOR)

       
        self.password = DEFAULT_PASSWORD
        self.is_recording = False
        self.is_paused = False
        self.logs = []  # list of (ts, key)
        self.max_raw_size = MAX_RAW_SIZE_BYTES

        self._build_header()
        self._build_tabs()
        self._build_footer_ticker()
        self._build_system_stats()
        self._schedule_poll()
        self._status_message("Ready. Click START RECORDING to begin (consent required).")

    # -------------------------
    # UI Building
    # -------------------------
    def _build_header(self):
        top = tk.Frame(self.root, bg=BG_COLOR)
        top.pack(fill="x", padx=12, pady=(12,6))

        title = tk.Label(top, text=f"Pro Key Logger - {BRAND}", fg=CYAN, bg=BG_COLOR,
                         font=("Orbitron", 20, "bold"))
        title.pack(side="left", padx=(6,12))

        brand_lbl = tk.Label(top, text=f"Developed by {BRAND}", fg="#bfbfbf", bg=BG_COLOR, font=("Segoe UI",10))
        brand_lbl.pack(side="right")

    def _build_tabs(self):
     
        nb_style = {"bootstyle": "dark"}
        self.nb = tb.Notebook(self.root, bootstyle="dark", width=980)
        self.nb.pack(fill="both", expand=True, padx=12, pady=6)
        
        self.tab_live = tk.Frame(self.nb, bg=BG_COLOR)
        self.tab_search = tk.Frame(self.nb, bg=BG_COLOR)
        self.tab_settings = tk.Frame(self.nb, bg=BG_COLOR)

        self.nb.add(self.tab_live, text="📄 Live Logs")
        self.nb.add(self.tab_search, text="🔍 Search & Export")
        self.nb.add(self.tab_settings, text="⚙ Settings")

        self._build_live_tab()
        self._build_search_tab()
        self._build_settings_tab()

    def _build_live_tab(self):
        
        ctrl = tk.Frame(self.tab_live, bg=BG_COLOR)
        ctrl.pack(side="left", fill="y", padx=12, pady=12)

        lbl = tk.Label(ctrl, text="Controls", font=("Segoe UI",12,"bold"), fg=MAROON, bg=BG_COLOR)
        lbl.pack(anchor="nw", pady=(0,8))

        self.start_btn = tb.Button(ctrl, text="Start Recording", bootstyle=(MAROON, "outline"), command=self.start_recording)
        self.start_btn.pack(fill="x", pady=6)

        self.pause_btn = tb.Button(ctrl, text="Pause Logging", bootstyle=("info"), command=self.toggle_pause, state="disabled")
        self.pause_btn.pack(fill="x", pady=6)

        self.clear_btn = tb.Button(ctrl, text="Clear Logs (password)", bootstyle=("danger-outline"), command=self.clear_logs)
        self.clear_btn.pack(fill="x", pady=6)

        self.export_btn = tb.Button(ctrl, text="Export (TXT/CSV)", bootstyle=("success"), command=self.export_dialog)
        self.export_btn.pack(fill="x", pady=6)


        self.status_var = tk.StringVar(value="Status: Idle")
        status_lbl = tk.Label(ctrl, textvariable=self.status_var, bg=BG_COLOR, fg="#d0d0d0", font=("Segoe UI",10))
        status_lbl.pack(anchor="w", pady=(18,0))

    
        tree_frame = tk.Frame(self.tab_live, bg=BG_COLOR)
        tree_frame.pack(side="left", fill="both", expand=True, padx=12, pady=12)

        cols = ("timestamp", "key")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        self.tree.heading("timestamp", text="Timestamp")
        self.tree.heading("key", text="Key Pressed")
        self.tree.column("timestamp", width=240, anchor="w")
        self.tree.column("key", anchor="w")
        self.tree.pack(fill="both", expand=True, side="left")


        style = ttk.Style()
        style.configure("Treeview.Heading", font=("Segoe UI",10,"bold"), foreground=CYAN, background=BG_COLOR)
        style.configure("Treeview", rowheight=22, background="#0f0f0f", fieldbackground="#0f0f0f", foreground="#e6e6e6")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")

    def _build_search_tab(self):
        top = tk.Frame(self.tab_search, bg=BG_COLOR)
        top.pack(fill="x", padx=12, pady=12)

        tk.Label(top, text="Search:", fg="#e0e0e0", bg=BG_COLOR).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = tb.Entry(top, textvariable=self.search_var, width=40, bootstyle="info")
        self.search_entry.pack(side="left", padx=(8,0))
        self.search_var.trace_add("write", lambda *a: self.apply_search())


        tb.Button(top, text="Export Visible to CSV", bootstyle="success", command=lambda: self.export_visible_csv()).pack(side="right")


        frame = tk.Frame(self.tab_search, bg=BG_COLOR)
        frame.pack(fill="both", expand=True, padx=12, pady=6)
        cols = ("timestamp", "key")
        self.tree_search = ttk.Treeview(frame, columns=cols, show="headings")
        self.tree_search.heading("timestamp", text="Timestamp")
        self.tree_search.heading("key", text="Key Pressed")
        self.tree_search.pack(fill="both", expand=True, side="left")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree_search.yview)
        self.tree_search.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")

    def _build_settings_tab(self):
        f = tk.Frame(self.tab_settings, bg=BG_COLOR)
        f.pack(fill="both", expand=True, padx=12, pady=12)


        tk.Label(f, text="Change Dashboard Password", fg=CYAN, bg=BG_COLOR, font=("Segoe UI",12,"bold")).pack(anchor="w")
        pw_frame = tk.Frame(f, bg=BG_COLOR)
        pw_frame.pack(anchor="w", pady=6)
        tk.Label(pw_frame, text="Current Password:", fg="#cfcfcf", bg=BG_COLOR).grid(row=0,column=0, sticky="w")
        self.curr_pw = tb.Entry(pw_frame, show="*", width=20, bootstyle="dark")
        self.curr_pw.grid(row=0,column=1, padx=8)
        tk.Label(pw_frame, text="New Password:", fg="#cfcfcf", bg=BG_COLOR).grid(row=1,column=0, sticky="w")
        self.new_pw = tb.Entry(pw_frame, show="*", width=20, bootstyle="dark")
        self.new_pw.grid(row=1,column=1, padx=8)
        tb.Button(pw_frame, text="Change Password", bootstyle="warning", command=self.change_password).grid(row=2,column=0, columnspan=2, pady=8)

   
        tk.Label(f, text="Log Rotation (raw file)", fg=CYAN, bg=BG_COLOR, font=("Segoe UI",12,"bold")).pack(anchor="w", pady=(12,0))
        rot_frame = tk.Frame(f, bg=BG_COLOR)
        rot_frame.pack(anchor="w", pady=6)
        tk.Label(rot_frame, text="Max Raw File Size (MB):", fg="#cfcfcf", bg=BG_COLOR).grid(row=0,column=0, sticky="w")
        self.rotate_var = tk.DoubleVar(value=self.max_raw_size / (1024*1024))
        tb.Entry(rot_frame, textvariable=self.rotate_var, width=10, bootstyle="dark").grid(row=0,column=1, padx=8)
        tb.Button(rot_frame, text="Set Rotation Size", bootstyle="info", command=self.set_rotation_size).grid(row=0,column=2, padx=6)

     
        tb.Button(f, text="Clear All Logs (password)", bootstyle="danger", command=self.clear_logs).pack(anchor="w", pady=12)

    def _build_footer_ticker(self):
        foot = tk.Frame(self.root, height=28, bg="#020202")
        foot.pack(side="bottom", fill="x")
        self.ticker_canvas = tk.Canvas(foot, height=28, bg="#020202", highlightthickness=0)
        self.ticker_canvas.pack(fill="both", expand=True)
        self.ticker_text = "Welcome to ASK Suite."
        self._ticker_x = None
        self._ticker_speed = 2
        self._ticker_running = True
        self._start_ticker_thread()

    def _build_system_stats(self):
      
        frame = tk.Frame(self.root, bg=BG_COLOR)
        frame.place(relx=0.78, rely=0.01, width=250, height=80)
        self.sys_cpu = tk.Label(frame, text="CPU: --%", fg=CYAN, bg="#080808", font=FONT_MONO)
        self.sys_cpu.pack(anchor="nw", fill="x")
        self.sys_mem = tk.Label(frame, text="RAM: --%", fg=CYAN, bg="#080808", font=FONT_MONO)
        self.sys_mem.pack(anchor="nw", fill="x")
        self.sys_uptime = tk.Label(frame, text="Uptime: --:--:--", fg=CYAN, bg="#080808", font=FONT_MONO)
        self.sys_uptime.pack(anchor="nw", fill="x")
        self._sys_start = time.time()
        self._update_sys_stats()

    # -------------------------
    # Actions & behavior
    # -------------------------
    def start_recording(self):
        if self.is_recording:
            messagebox.showinfo("Info", "Already recording.")
            return
     
        ok = messagebox.askokcancel("Confirm", "You are about to START recording keystrokes.\n\nOnly proceed if you have explicit permission to record on this machine.\n\nProceed?")
        if not ok:
            return
        try:
            capture.start()
        except Exception as e:
            messagebox.showerror("Error", f"Could not start capture:\n{e}")
            return
        self.is_recording = True
        self.is_paused = False
        self.start_btn.config(text="Recording...", bootstyle=(MAROON, "solid"), state="disabled")
        self.pause_btn.config(state="normal", text="Pause Logging")
        self._set_status("Recording active")
        self._ticker_push("Logging active…")

    def toggle_pause(self):
        if not self.is_recording:
            return
        if not self.is_paused:
        
            capture.stop()
            self.is_paused = True
            self.pause_btn.config(text="Resume Logging", bootstyle="warning-outline")
            self._set_status("Paused")
            self._ticker_push("Logging paused")
        else:
           
            try:
                capture.start()
            except Exception as e:
                messagebox.showerror("Error", f"Could not resume:\n{e}")
                return
            self.is_paused = False
            self.pause_btn.config(text="Pause Logging", bootstyle="info")
            self._set_status("Recording active")
            self._ticker_push("Logging resumed")

    def clear_logs(self):

        pw = simpledialog.askstring("Password", "Enter password to CLEAR logs:", show="*")
        if pw != self.password:
            messagebox.showwarning("Wrong", "Incorrect password. Action cancelled.")
            return
        if not messagebox.askyesno("Confirm", "Are you sure you want to DELETE all logs? This cannot be undone."):
            return
 
        try:
            if RAW_LOG.exists():
                RAW_LOG.unlink()
            for f in DAILY_DIR.glob("log_*.csv"):
                f.unlink()
            
            self.logs.clear()
            self._refresh_trees()
            self._ticker_push("All logs cleared by user")
            messagebox.showinfo("Cleared", "All logs deleted.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not clear logs: {e}")

    def export_dialog(self):

        if not self.logs:
            messagebox.showinfo("No logs", "No captured logs to export.")
            return
        choice = messagebox.askquestion("Export", "Export logs as CSV? (No -> TXT)", icon='question')
        if choice == 'yes':
            path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files","*.csv"),("All files","*.*")],
                                                initialfile=f"key_log_ASK_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            if path:
                try:
                    df = pd.DataFrame(self.logs, columns=["Timestamp","Key Pressed"])
                    df.to_csv(path, index=False)
                    messagebox.showinfo("Exported", f"Exported to {path}")
                    self._ticker_push("Export completed successfully")
                except Exception as e:
                    messagebox.showerror("Error", f"Could not export: {e}")
        else:
            path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files","*.txt"),("All files","*.*")],
                                                initialfile=f"key_log_ASK_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        for ts,k in self.logs:
                            f.write(f"{ts}: {k}\n")
                    messagebox.showinfo("Exported", f"Exported to {path}")
                    self._ticker_push("Export completed successfully")
                except Exception as e:
                    messagebox.showerror("Error", f"Could not export: {e}")

    def export_visible_csv(self):
   
        rows = [self.tree_search.item(i)["values"] for i in self.tree_search.get_children()]
        if not rows:
            messagebox.showinfo("No rows", "No visible rows to export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files","*.csv")],
                                            initialfile=f"visible_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        if path:
            try:
                df = pd.DataFrame(rows, columns=["Timestamp","Key Pressed"])
                df.to_csv(path, index=False)
                messagebox.showinfo("Exported", f"Exported to {path}")
                self._ticker_push("Visible export completed")
            except Exception as e:
                messagebox.showerror("Error", f"Could not export: {e}")

    def change_password(self):
        curr = self.curr_pw.get().strip()
        new = self.new_pw.get().strip()
        if not curr or not new:
            messagebox.showwarning("Input", "Both fields required.")
            return
        if curr != self.password:
            messagebox.showerror("Wrong", "Current password incorrect.")
            return
        self.password = new
        self.curr_pw.delete(0, tk.END)
        self.new_pw.delete(0, tk.END)
        messagebox.showinfo("Changed", "Password changed successfully.")
        self._ticker_push("Password changed")

    def set_rotation_size(self):
        try:
            mb = float(self.rotate_var.get())
            self.max_raw_size = int(mb * 1024 * 1024)
            global MAX_RAW_SIZE_BYTES
            MAX_RAW_SIZE_BYTES = self.max_raw_size
            messagebox.showinfo("Set", f"Rotation size set to {mb} MB")
            self._ticker_push(f"Rotation size set to {mb} MB")
        except Exception:
            messagebox.showerror("Error", "Invalid size")

    # -------------------------
    # Poll queue from capture & update UI
    # -------------------------
    def _schedule_poll(self):
   
        updated = False
        while True:
            try:
                ts, k = q.get_nowait()
                self.logs.append((ts, k))
               
                self.tree.insert("", "end", values=(ts, k))
              
                if self._matches_search(ts, k):
                    self.tree_search.insert("", "end", values=(ts, k))
                updated = True
            except queue.Empty:
                break
        if updated:
   
            try:
                children = self.tree.get_children()
                if children:
                    self.tree.see(children[-1])
            except Exception:
                pass
   
        self.root.after(300, self._schedule_poll)

    def _refresh_trees(self):
    
        for tr in (self.tree, self.tree_search):
            tr.delete(*tr.get_children())
        for ts,k in self.logs:
            self.tree.insert("", "end", values=(ts,k))
            if self._matches_search(ts,k):
                self.tree_search.insert("", "end", values=(ts,k))

    def apply_search(self):
        self.tree_search.delete(*self.tree_search.get_children())
        s = self.search_var.get().strip().lower()
        for ts,k in self.logs:
            if not s or s in ts.lower() or s in k.lower():
                self.tree_search.insert("", "end", values=(ts,k))

    def _matches_search(self, ts, k):
        s = self.search_var.get().strip().lower()
        if not s:
            return True
        return s in ts.lower() or s in k.lower()

    # -------------------------
    # System stats & ticker
    # -------------------------
    def _update_sys_stats(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        up = int(time.time() - self._sys_start)
        hrs, rem = divmod(up, 3600)
        mins, secs = divmod(rem, 60)
        uptime_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
        self.sys_cpu.config(text=f"CPU: {cpu:.0f}%")
        self.sys_mem.config(text=f"RAM: {mem:.0f}%")
        self.sys_uptime.config(text=f"Uptime: {uptime_str}")
     
        if cpu > 80 or mem > 80:
            self.sys_cpu.config(fg=MAROON)
            self.sys_mem.config(fg=MAROON)
            self._ticker_push(f"⚠ High resource usage: CPU {cpu:.0f}%, RAM {mem:.0f}%")
        else:
            self.sys_cpu.config(fg=CYAN)
            self.sys_mem.config(fg=CYAN)
        self.root.after(1000, self._update_sys_stats)

    def _start_ticker_thread(self):
      
        self._draw_ticker()

    def _draw_ticker(self):
        c = self.ticker_canvas
        c.delete("all")
        w = c.winfo_width() or 800
        h = 28
        text = self.ticker_text
       
        if self._ticker_x is None:
            self._ticker_x = w
       
        c.create_text(self._ticker_x, h/2, text=text, fill=CYAN, font=FONT_MONO, anchor="w", tags="ticker")
        self._ticker_x -= self._ticker_speed
        bbox = c.bbox("ticker")
        if bbox and bbox[2] < 0:
         
            self._ticker_x = w
        c.after(30, self._draw_ticker)

    def _ticker_push(self, msg):
        self.ticker_text = msg
        self._ticker_x = self.ticker_canvas.winfo_width() or 800

    # -------------------------
    #  status
    # -------------------------
    def _set_status(self, text):
        self.status_var.set("Status: " + text)

    def _status_message(self, text):
        self._set_status(text)
        self._ticker_push(text)

# -------------------------
# Entrypoint
# -------------------------
def main():
    root = tb.Window(themename="darkly", title=APP_NAME)
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", lambda: on_closing(root, app))
    root.mainloop()

def on_closing(root, app):
    if messagebox.askokcancel("Quit", "Exit application? Recording will stop."):
 
        try:
            capture.stop()
        except:
            pass
        root.destroy()

if __name__ == "__main__":
    main()
