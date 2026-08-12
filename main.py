# main.py
import os
import sys
import tkinter
from pathlib import Path
import customtkinter as ctk
from customtkinter.windows.widgets.ctk_button import CTkButton
from database import Database
from scheduler import Scheduler
from ui.main_window import MainWindow

APP_NAME = "一点不背"


def _patch_ctk_button_release():
    """全局改造 CTkButton：左键按下只做点击动画不触发命令，
    释放时若鼠标仍在按钮上才触发命令；若按下后拖出按钮再松开则取消（不触发）。
    这样误触可以按住不放拖出去松开来撤销。"""

    _original_create_bindings = CTkButton._create_bindings

    def _create_bindings_release(self, sequence=None):
        _original_create_bindings(self, sequence)
        _ensure_release_binding(self)

    def _ensure_release_binding(self):
        """确保 ButtonRelease-1 已绑定到 _released。
        CTkButton._draw() 重建 text_label/image_label 时只重新绑 <Button-1>，
        不绑 <ButtonRelease-1>，所以这里需要在多个时机主动绑。"""
        if self._canvas is not None:
            self._canvas.bind("<ButtonRelease-1>", self._released)
        if self._text_label is not None:
            self._text_label.bind("<ButtonRelease-1>", self._released)
        if self._image_label is not None:
            self._image_label.bind("<ButtonRelease-1>", self._released)

    def _clicked_press_only(self, event=None):
        """按下时：只做点击动画，不调用 command；同时主动补绑 ButtonRelease-1，
        防止 _draw() 重建 label 后释放事件丢失导致按钮没反应"""
        if self._state != tkinter.DISABLED:
            self._on_leave()
            self._click_animation_running = True
            self.after(100, self._click_animation)
            # 按下时主动补绑，覆盖 _draw 重建 label 后丢失绑定的情况
            _ensure_release_binding(self)
            # 故意不调用 self._command() —— 改由 _released 触发

    def _released(self, event=None):
        """释放时：若鼠标仍在按钮范围内，才调用 command"""
        if self._state != tkinter.DISABLED and _pointer_in_button(self, event):
            if self._command is not None:
                self._command()

    def _pointer_in_button(self, event=None):
        """判断释放瞬间鼠标是否仍在按钮范围内（用屏幕坐标边界框判断，最可靠）"""
        if event is None:
            return False
        try:
            x, y = event.x_root, event.y_root
            left = self.winfo_rootx()
            top = self.winfo_rooty()
            right = left + self.winfo_width()
            bottom = top + self.winfo_height()
            return left <= x <= right and top <= y <= bottom
        except Exception:
            return False

    CTkButton._create_bindings = _create_bindings_release
    CTkButton._clicked = _clicked_press_only
    CTkButton._released = _released
    CTkButton._pointer_in_button = _pointer_in_button
    CTkButton._ensure_release_binding = _ensure_release_binding


def get_app_root() -> Path:
    """软件根目录：打包后为 exe 所在目录，开发模式为项目根目录"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent

def get_db_path() -> str:
    """数据库路径：软件根目录下 data/ebbinghaus.db

    与 exe 同放在软件根目录下，便于统一备份和管理。
    重新打包/更新 exe 不会影响 data/ 文件夹里的数据。
    """
    data_dir = get_app_root() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "ebbinghaus.db")

def _optimize_ctk_performance():
    """优化 customtkinter 在 Windows 上的性能，减轻窗口拖动卡顿。
    根因：customtkinter 内部有多个高频 after 轮询占用主线程，导致拖动窗口时
    事件队列积压、鼠标不跟手。下面逐一停掉或降频。"""

    # 1. 停止 AppearanceModeTracker 的 30ms 注册表轮询（最大元凶：每秒 33 次读注册表）
    #    把 appearance_mode_set_by 设为 "user" 后，轮询里跳过 darkdetect.theme() 调用；
    #    同时把间隔拉到很大，基本不再占用主线程。
    from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
    AppearanceModeTracker.appearance_mode_set_by = "user"
    AppearanceModeTracker.update_loop_interval = 600000  # 10 分钟

    # 2. 彻底停止 ScalingTracker 的 DPI 轮询（默认 100ms 一次 ctypes 系统调用）
    #    deactivate 后 get_window_dpi_scaling 直接返回 1，跳过 ctypes；
    #    间隔拉到很大，基本停止轮询。
    from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker
    ScalingTracker.deactivate_automatic_dpi_awareness = True
    ScalingTracker.update_loop_interval = 600000  # 10 分钟

    # 3. 禁用 customtkinter 对原生标题栏的干预（withdraw/deiconify 改色），
    #    避免切换外观/调用 resizable 时闪窗并阻塞主线程
    ctk.CTk._deactivate_windows_window_header_manipulation = True

    # 4. 让 CTk 主窗口的 <Configure> 回调变轻：原实现每次都调 winfo_width()/winfo_height()
    #    （同步 Tcl 往返调用），改为直接用 event.width/height（已现成），避免主线程开销。
    #    拖动窗口时 <Configure> 会被高频触发，这一步直接降低每次回调成本。
    def _light_update_dimensions_event(self, event=None):
        if not self._block_update_dimensions_event:
            detected_width = event.width if event else super(ctk.CTk, self).winfo_width()
            detected_height = event.height if event else super(ctk.CTk, self).winfo_height()
            if (self._current_width != self._reverse_window_scaling(detected_width) or
                    self._current_height != self._reverse_window_scaling(detected_height)):
                self._current_width = self._reverse_window_scaling(detected_width)
                self._current_height = self._reverse_window_scaling(detected_height)

    ctk.CTk._update_dimensions_event = _light_update_dimensions_event


def _return_foreground(prev_hwnd):
    """启动后将前台焦点返回给之前的活动窗口（如浏览器）。
    避免 customtkinter 窗口创建时 iconbitmap 调用触发任务栏更新，
    导致全屏看视频时任务栏不自动隐藏。"""
    import ctypes
    user32 = ctypes.windll.user32
    # 检查 prev_hwnd 是否有效且不是桌面/任务栏
    if not (prev_hwnd and user32.IsWindow(prev_hwnd)):
        return
    desktop = user32.GetDesktopWindow()
    shell_tray = user32.FindWindowW("Shell_TrayWnd", None)
    if prev_hwnd in (desktop, shell_tray, 0):
        return
    # 模拟 Alt 键按下/释放，绕过 Windows 的前台窗口限制
    user32.keybd_event(0x12, 0, 0, 0)   # Alt down
    user32.keybd_event(0x12, 0, 2, 0)   # Alt up
    user32.SetForegroundWindow(prev_hwnd)


def _install_global_exception_hook():
    """全局异常兜底：Tk 回调中任何未捕获异常都记录日志并弹窗提示。

    现状：数据库写操作（评分/编辑/笔记/删除等）几乎都没有 try/except，
    出错时异常直接抛进 Tk 回调；打包为 --noconsole 后用户零感知，
    等价于"数据悄悄丢"。此钩子保证至少能看到错误并留下日志。
    """
    import traceback
    from datetime import datetime

    log_dir = get_app_root() / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "error.log"

    def _report(self, exc_type, exc_val, exc_tb):
        """Tk 回调异常兜底：记录日志 + 弹窗。

        作为实例方法挂到 Tk.report_callback_exception，self 即 Tk 窗口，
        可作 messagebox 的父窗口。
        """
        # 1) 落盘日志（尽力而为，失败不阻断弹窗）
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n===== {datetime.now().isoformat(timespec='seconds')} =====\n")
                traceback.print_exception(exc_type, exc_val, exc_tb, file=f)
        except Exception:
            pass
        # 2) 弹窗提示（可能处于窗口销毁流程，兜底 try）
        try:
            from tkinter import messagebox
            parent = self if isinstance(self, tkinter.Misc) else None
            messagebox.showerror(
                "程序出错",
                f"操作未完成，错误信息：\n{exc_val}\n\n详细信息已写入：\n{log_path}",
                parent=parent)
        except Exception:
            pass

    tkinter.Tk.report_callback_exception = _report


def _get_default_theme() -> str:
    """品牌绿主题（Soft Editorial）json 路径；文件缺失时回退内置 blue。
    打包时需把 ui/soft_editorial.json 一并加入。"""
    theme_file = Path(__file__).parent / "ui" / "soft_editorial.json"
    return str(theme_file) if theme_file.exists() else "blue"


def _patch_iconbitmap_missing_resources():
    """PyInstaller 打包后，customtkinter 的 assets/icons 资源可能未被收集进
    临时解压目录（_MEIxxxxx），CTk/CTkToplevel 延迟设置窗口图标的回调
    （after → iconbitmap/wm_iconbitmap）会抛 TclError: bitmap ... not defined，
    导致每次打开对话框都报错。这里在图标路径不存在时静默跳过。"""

    _original_wm_iconbitmap = tkinter.Wm.wm_iconbitmap
    _original_iconbitmap = tkinter.Wm.iconbitmap

    def _is_missing_path(value):
        return (isinstance(value, str)
                and (os.sep in value or "/" in value)  # 是路径而非 bitmap 名
                and not os.path.exists(value))

    def _safe_wm_iconbitmap(self, bitmap=None, default=None):
        if _is_missing_path(bitmap):
            return
        return _original_wm_iconbitmap(self, bitmap, default)

    def _safe_iconbitmap(self, bitmap=None, default=None):
        if _is_missing_path(bitmap):
            return
        return _original_iconbitmap(self, bitmap, default)

    tkinter.Wm.wm_iconbitmap = _safe_wm_iconbitmap
    tkinter.Wm.iconbitmap = _safe_iconbitmap


def main():
    # 必须在创建任何 CTkButton 之前打补丁
    _patch_ctk_button_release()
    # 打包后 customtkinter 图标资源可能缺失，提前兜底避免 TclError
    _patch_iconbitmap_missing_resources()

    # 全局异常兜底：任何 Tk 回调异常都可见、可查
    _install_global_exception_hook()

    # 先设外观/主题（set_appearance_mode 可能重置内部轮询状态）
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme(_get_default_theme())

    # 再优化性能参数（必须在 CTk() 创建前；放在 set_appearance_mode 之后，
    # 避免被 set_appearance_mode 重置 appearance_mode_set_by）
    _optimize_ctk_performance()

    db = Database(get_db_path())
    db.init()
    # 启动时清理回收站中超过 30 天的条目（物理删除，不可恢复）
    db.purge_expired_deleted()
    scheduler = Scheduler()

    # 记录当前前台窗口（可能是浏览器等），用于启动后将焦点返回
    import ctypes
    prev_hwnd = ctypes.windll.user32.GetForegroundWindow()

    app = MainWindow(db, scheduler)
    app.protocol("WM_DELETE_WINDOW", lambda: (db.close(), app.destroy()))

    # 启动后将焦点返回给之前的活动窗口，避免本软件干扰任务栏自动隐藏。
    # customtkinter 在 200ms 后调用 iconbitmap 触发任务栏更新，
    # 所以我们在 300ms 后将焦点返回，覆盖 iconbitmap 的影响。
    app.after(300, lambda: _return_foreground(prev_hwnd))

    app.mainloop()

if __name__ == "__main__":
    main()
