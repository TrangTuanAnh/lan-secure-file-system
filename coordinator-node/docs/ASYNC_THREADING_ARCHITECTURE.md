"""
Async Architecture & Threading Guide for Python GUI Frontend

Designing responsive GUI with background network I/O.
"""

# ============================================================================
# ARCHITECTURE OVERVIEW
# ============================================================================

"""
┌─────────────────────────────────────────────────────────────────┐
│                        GUI Thread (Main)                        │
│  - Event loop (Tkinter/PyQt/PySide)                             │
│  - User input handling                                          │
│  - UI rendering & updates                                       │
│  - MUST NOT block on network operations                         │
└─────────────────┬───────────────────────────────────────────────┘
                  │
        Queue.put() │ (thread-safe)
                  │
    ┌─────────────▼────────────────────────────────────────────┐
    │         Worker Threads (Background)                      │
    │  - Network I/O (socket requests)                         │
    │  - Heavy computation                                     │
    │  - File I/O                                              │
    │  - CAN block without freezing GUI                        │
    └─────────────┬─────────────────────────────────────────────┘
                  │
        Queue.put() │ (results/events)
                  │
    ┌─────────────▼────────────────────────────────────────────┐
    │       Event Bus / Signal Handlers                        │
    │  - Queue of results from workers                         │
    │  - GUI polls queue periodically                          │
    │  - Calls callbacks in GUI thread context                 │
    └───────────────────────────────────────────────────────────┘
"""

# ============================================================================
# THREADING STRATEGY
# ============================================================================

"""
1. GUI THREAD (Main Thread)
   - Tkinter event loop runs here
   - User clicks buttons, types in fields
   - Handles events from worker threads via Queue
   - NEVER BLOCKS on I/O

2. WORKER THREADS (Background)
   - Each request gets its own worker (or thread pool)
   - Calls backend_client_sdk methods
   - Handles timeouts, retries, errors
   - Puts results in queue

3. SYNCHRONIZATION
   - Use Queue (thread-safe, no locks needed in simple cases)
   - Or use threading.Event, threading.Lock if needed
   - Avoid GUI callbacks directly from worker threads

WRONG (Don't do this):
    def on_login_click():
        result = client.login(user, pass)  # BLOCKS GUI!
        update_ui(result)

RIGHT (Do this):
    def on_login_click():
        thread = Thread(target=do_login)
        thread.start()
    
    def do_login():
        result = client.login(user, pass)  # Runs in background
        queue.put(("login_result", result))
    
    # In GUI: periodically check queue
    def check_queue():
        while not queue.empty():
            event, data = queue.get()
            handle_event(event, data)
"""

# ============================================================================
# IMPLEMENTATION PATTERN 1: Queue-Based
# ============================================================================

import threading
import queue
from typing import Callable, Any, Dict

class AsyncWorker:
    """
    Worker thread that executes tasks and returns results via queue.
    
    Usage:
        worker = AsyncWorker()
        worker.start()
        worker.queue_task(lambda: client.login("user", "pass"), 
                         on_success=lambda r: print(f"Logged in: {r}"))
        # In GUI event loop:
        worker.poll_results()
    """
    
    def __init__(self):
        self._task_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._running = False
        self._thread = None
    
    def start(self):
        """Start worker thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop worker thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def queue_task(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        on_success: Callable = None,
        on_error: Callable = None
    ):
        """
        Queue a task to run in background.
        
        Args:
            func: Function to execute
            args: Positional arguments
            kwargs: Keyword arguments
            on_success: Callback if successful
            on_error: Callback if error
        """
        task = {
            "func": func,
            "args": args,
            "kwargs": kwargs or {},
            "on_success": on_success,
            "on_error": on_error
        }
        self._task_queue.put(task)
    
    def _worker_loop(self):
        """Main worker loop (runs in background thread)."""
        while self._running:
            try:
                task = self._task_queue.get(timeout=1)
            except queue.Empty:
                continue
            
            try:
                result = task["func"](*task["args"], **task["kwargs"])
                self._result_queue.put({
                    "type": "success",
                    "result": result,
                    "callback": task["on_success"]
                })
            except Exception as e:
                self._result_queue.put({
                    "type": "error",
                    "error": e,
                    "callback": task["on_error"]
                })
    
    def poll_results(self):
        """
        Poll for completed tasks (call from GUI thread).
        
        Executes callbacks in GUI thread context.
        """
        while True:
            try:
                result = self._result_queue.get_nowait()
            except queue.Empty:
                break
            
            if result["type"] == "success":
                if result["callback"]:
                    result["callback"](result["result"])
            else:
                if result["callback"]:
                    result["callback"](result["error"])


# ============================================================================
# IMPLEMENTATION PATTERN 2: Signal/Slot Style (PyQt/PySide)
# ============================================================================

"""
If using PyQt/PySide, leverage their signal/slot mechanism:

from PyQt5.QtCore import QObject, QThread, pyqtSignal

class LoginWorker(QObject):
    finished = pyqtSignal(dict)  # Signal with result
    error = pyqtSignal(str)      # Signal with error message
    
    def __init__(self, client, username, password):
        super().__init__()
        self.client = client
        self.username = username
        self.password = password
    
    def run(self):
        try:
            result = self.client.login(self.username, self.password)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class LoginDialog(QDialog):
    def on_login_click(self):
        worker = LoginWorker(self.client, user, pass)
        thread = QThread()
        
        worker.moveToThread(thread)
        worker.finished.connect(self.on_login_success)
        worker.error.connect(self.on_login_error)
        
        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        
        thread.start()
    
    def on_login_success(self, result):
        # This runs in GUI thread!
        self.token = result["token"]
        self.close()
    
    def on_login_error(self, error_msg):
        # This runs in GUI thread!
        QMessageBox.critical(self, "Error", error_msg)
"""


# ============================================================================
# IMPLEMENTATION PATTERN 3: Tkinter with Threading
# ============================================================================

import tkinter as tk
from tkinter import messagebox
import queue
import threading

class TkinterBackendApp:
    """
    Tkinter app that uses background threads for network I/O.
    """
    
    def __init__(self, root):
        self.root = root
        self.root.title("File Sharing App")
        
        # Initialize backend service
        from services import BackendService
        self.service = BackendService()
        
        # Create worker
        self.worker = AsyncWorker()
        self.worker.start()
        
        # Create UI
        self._create_widgets()
        
        # Start polling for results
        self._poll_worker()
    
    def _create_widgets(self):
        """Create UI widgets."""
        # Login frame
        frame = tk.Frame(self.root)
        frame.pack(padx=20, pady=20)
        
        tk.Label(frame, text="Username:").grid(row=0, column=0)
        self.username_entry = tk.Entry(frame)
        self.username_entry.grid(row=0, column=1)
        
        tk.Label(frame, text="Password:").grid(row=1, column=0)
        self.password_entry = tk.Entry(frame, show="*")
        self.password_entry.grid(row=1, column=1)
        
        tk.Button(
            frame,
            text="Login",
            command=self.on_login_click
        ).grid(row=2, columnspan=2)
        
        self.status_label = tk.Label(self.root, text="Ready")
        self.status_label.pack()
    
    def on_login_click(self):
        """Handle login button click."""
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not username or not password:
            messagebox.showerror("Error", "Enter username and password")
            return
        
        # Queue login task (runs in background)
        self.worker.queue_task(
            func=self.service.auth.login,
            args=(username, password),
            on_success=self.on_login_success,
            on_error=self.on_login_error
        )
        
        self.status_label.config(text="Logging in...")
    
    def on_login_success(self, result):
        """Callback when login succeeds (runs in GUI thread)."""
        self.status_label.config(text="Logged in!")
        messagebox.showinfo("Success", f"Token: {result.get('token')[:8]}...")
    
    def on_login_error(self, error):
        """Callback when login fails (runs in GUI thread)."""
        self.status_label.config(text="Login failed")
        messagebox.showerror("Error", str(error))
    
    def _poll_worker(self):
        """Poll worker for results (call periodically from GUI)."""
        self.worker.poll_results()
        self.root.after(100, self._poll_worker)  # Poll every 100ms
    
    def on_closing(self):
        """Cleanup when app closes."""
        self.worker.stop()
        if self.service.is_connected():
            self.service.disconnect()
        self.root.destroy()


# ============================================================================
# IMPLEMENTATION PATTERN 4: Async Context (Advanced)
# ============================================================================

"""
For more complex scenarios, consider using asyncio with threading bridge:

import asyncio
from threading import Thread

class AsyncBackend:
    def __init__(self, service):
        self.service = service
        self.loop = asyncio.new_event_loop()
        self.thread = Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
    
    def call_async(self, func, *args, on_result=None):
        '''Schedule function in async loop, call callback when done'''
        future = asyncio.run_coroutine_threadsafe(
            self._run_func(func, args, on_result),
            self.loop
        )
        return future
    
    async def _run_func(self, func, args, on_result):
        try:
            result = await self.loop.run_in_executor(
                None, func, *args
            )
            if on_result:
                on_result(None, result)
        except Exception as e:
            if on_result:
                on_result(e, None)
"""


# ============================================================================
# BEST PRACTICES
# ============================================================================

"""
1. NEVER BLOCK THE GUI THREAD
   ❌ result = client.login(user, pass)  # BLOCKS
   ✅ worker.queue_task(client.login, args=(user, pass))

2. USE CALLBACKS FOR RESULTS
   - Worker threads put results in queue
   - GUI thread polls queue and updates UI
   - Callbacks run in GUI thread context

3. HANDLE ERRORS GRACEFULLY
   - Try-except in worker threads
   - Display error messages to user
   - Never let exceptions crash the app

4. USE TIMEOUTS
   - Network requests should timeout
   - Don't let user think app is frozen
   - BackendClient has configurable timeout

5. SHOW PROGRESS/STATUS
   - Update status label while loading
   - Show spinner/progress bar
   - Give user feedback that something is happening

6. IMPLEMENT RETRY LOGIC
   - Network can be flaky
   - Retry failed requests automatically
   - But don't retry indefinitely

7. MANAGE THREADS CAREFULLY
   - Create thread pool if many concurrent operations
   - Don't create unlimited threads
   - Clean up threads on exit

8. TEST THREADING BEHAVIOR
   - Simulate slow network (add delays)
   - Test rapid clicks (multiple concurrent requests)
   - Test app shutdown while requests pending
   - Test network failures/disconnects
"""


# ============================================================================
# COMPLETE EXAMPLE: Tkinter App with Room Listing
# ============================================================================

if __name__ == "__main__":
    root = tk.Tk()
    
    app = TkinterBackendApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    root.mainloop()


# ============================================================================
# TESTING CHECKLIST
# ============================================================================

"""
[ ] Can click button multiple times without freezing
[ ] Callbacks execute in GUI thread (can update widgets)
[ ] Error messages display when requests fail
[ ] Timeout handling works (doesn't hang forever)
[ ] Closing app while request pending doesn't crash
[ ] Rapid requests don't cause out-of-order responses
[ ] Memory doesn't leak (check thread cleanup)
[ ] Long-running app doesn't degrade performance
[ ] UI remains responsive even with slow network
"""

