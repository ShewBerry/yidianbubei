# ui/sync_dialog.py
"""云端同步设置对话框：登录/注册/登出/启用同步/手动同步。

不侵入现有代码，只在 MainWindow 加一个入口按钮。
所有同步操作在后台线程执行，不阻塞 UI。
"""
import threading
import customtkinter as ctk
from tkinter import messagebox

from sync.config import load_config, save_config, is_sync_enabled
from sync.auth import sign_in, sign_up, sign_out, get_email, AuthError
from sync.client import SyncError, AuthExpiredError
from sync.synchronizer import Synchronizer
from ui.theme import title_font, body_font, small_font, COLOR_TEXT_SECONDARY,\
    COLOR_DANGER, COLOR_DANGER_HOVER


class SyncDialog(ctk.CTkToplevel):
    """云端同步设置对话框"""

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.title("云端同步设置")
        self.geometry("480x560")
        self.resizable(False, False)

        self._build_ui()
        self._refresh_status()

        self.transient(parent)
        self.grab_set()

    def _build_ui(self):
        # 标题
        ctk.CTkLabel(self, text="☁️ 云端同步",
                     font=title_font()).pack(pady=(20, 5))

        ctk.CTkLabel(self,
                     text="云端作为电脑端的备份，数据只上传、不覆盖本地",
                     text_color=COLOR_TEXT_SECONDARY,
                     font=small_font()).pack(pady=(0, 15))

        # 状态卡片
        self.status_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.status_frame.pack(fill="x", padx=20, pady=5)
        self.status_label = ctk.CTkLabel(self.status_frame, text="",
                                          font=body_font())
        self.status_label.pack()
        self.last_sync_label = ctk.CTkLabel(self.status_frame, text="",
                                             text_color=COLOR_TEXT_SECONDARY,
                                             font=small_font())
        self.last_sync_label.pack(pady=(2, 0))

        # 分隔线
        ctk.CTkFrame(self, height=1, fg_color="gray50").pack(fill="x", padx=20, pady=10)

        # 操作区（动态切换：未登录显示登录表单，已登录显示同步控制）
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.pack(fill="both", expand=True, padx=20, pady=5)

        # 进度标签（同步过程中显示）
        self.progress_label = ctk.CTkLabel(self, text="", text_color=COLOR_TEXT_SECONDARY,
                                            font=small_font())
        self.progress_label.pack(pady=(0, 10))

    def _refresh_status(self):
        """刷新状态显示和操作区"""
        email = get_email()
        cfg = load_config()
        sync_on = cfg.get("sync_enabled", False)

        if email:
            self.status_label.configure(
                text=f"已登录：{email}",
                text_color="#2e7d32")
            sync = Synchronizer(self.db)
            last_upload = sync.get_last_sync_time()
            if last_upload:
                self.last_sync_label.configure(
                    text=f"上次上传：{last_upload[:19].replace('T', ' ')}")
            else:
                self.last_sync_label.configure(text="尚未同步")
        else:
            self.status_label.configure(text="未登录", text_color=COLOR_TEXT_SECONDARY)
            self.last_sync_label.configure(text="")

        # 重建操作区
        for widget in self.action_frame.winfo_children():
            widget.destroy()

        if not email:
            self._build_login_form()
        else:
            self._build_sync_controls(sync_on)

    def _build_login_form(self):
        """未登录：显示登录/注册表单"""
        frame = self.action_frame

        ctk.CTkLabel(frame, text="邮箱：").pack(anchor="w", pady=(5, 0))
        email_entry = ctk.CTkEntry(frame, width=400, placeholder_text="your@email.com")
        email_entry.pack(fill="x", pady=(2, 8))

        ctk.CTkLabel(frame, text="密码：").pack(anchor="w")
        pwd_entry = ctk.CTkEntry(frame, width=400, show="•", placeholder_text="至少 6 位")
        pwd_entry.pack(fill="x", pady=(2, 8))

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(5, 0))

        def do_login():
            email = email_entry.get().strip()
            pwd = pwd_entry.get()
            if not email or not pwd:
                messagebox.showwarning("提示", "请输入邮箱和密码", parent=self)
                return
            self._run_async(
                lambda: sign_in(email, pwd),
                on_success=lambda _: self._refresh_status(),
                action_name="登录"
            )

        def do_signup():
            email = email_entry.get().strip()
            pwd = pwd_entry.get()
            if not email or not pwd:
                messagebox.showwarning("提示", "请输入邮箱和密码", parent=self)
                return
            if len(pwd) < 6:
                messagebox.showwarning("提示", "密码至少 6 位", parent=self)
                return
            self._run_async(
                lambda: sign_up(email, pwd),
                on_success=lambda _: self._refresh_status(),
                action_name="注册"
            )

        ctk.CTkButton(btn_frame, text="登录", width=120, height=34,
                      command=do_login).pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="注册", width=120, height=34,
                      fg_color="transparent", border_width=1,
                      command=do_signup).pack(side="left")

        ctk.CTkLabel(frame,
                     text="提示：首次使用请先注册。",
                     text_color=COLOR_TEXT_SECONDARY, font=small_font()
                     ).pack(pady=(15, 0))

    def _build_sync_controls(self, sync_on: bool):
        """已登录：显示同步开关 + 操作按钮"""
        frame = self.action_frame

        # 同步开关
        switch_frame = ctk.CTkFrame(frame, fg_color="transparent")
        switch_frame.pack(fill="x", pady=(5, 10))

        def on_switch_change():
            cfg = load_config()
            cfg["sync_enabled"] = switch_var.get()
            save_config(cfg)
            self._refresh_status()

        switch_var = ctk.BooleanVar(value=sync_on)
        ctk.CTkSwitch(switch_frame, text="启用实时同步",
                      variable=switch_var, command=on_switch_change).pack(side="left")

        # 操作按钮
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=5)

        ctk.CTkButton(btn_frame, text="⬆ 立即全量上传", width=180, height=34,
                      command=self._do_full_upload).pack(fill="x", pady=(0, 5))
        ctk.CTkButton(btn_frame, text="↻ 增量上传", width=180, height=34,
                      fg_color="transparent", border_width=1,
                      command=self._do_incremental).pack(fill="x", pady=(0, 5))

        # 登出按钮
        ctk.CTkButton(btn_frame, text="登出", width=180, height=34,
                      fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_HOVER,
                      command=self._do_logout).pack(fill="x", pady=(15, 0))

        # 说明
        ctk.CTkLabel(frame,
                     text="云端作为电脑端的备份：点「立即全量上传」把本地数据传到云端。\n"
                          "启用「实时同步」会在每次数据变动后自动上传。\n"
                          "云端数据不会覆盖电脑端。",
                     text_color=COLOR_TEXT_SECONDARY, font=small_font(),
                     justify="left").pack(pady=(15, 0), anchor="w")

    def _do_full_upload(self):
        """全量上传"""
        self._run_async(
            lambda: Synchronizer(self.db).full_upload(
                on_progress=lambda t, c, total: self._set_progress(f"上传 {t}... ({c+1}/{total})")
            ),
            on_success=lambda stats: self._show_stats("全量上传完成", stats),
            action_name="全量上传"
        )

    def _do_incremental(self):
        """增量同步"""
        self._run_async(
            lambda: Synchronizer(self.db).incremental_upload_all(
                on_progress=lambda t, c, total: self._set_progress(f"同步 {t}... ({c+1}/{total})")
            ),
            on_success=lambda stats: self._show_stats("增量同步完成", stats),
            action_name="增量同步"
        )

    def _do_logout(self):
        if not messagebox.askyesno("确认登出", "登出后将无法同步。确定登出吗？", parent=self):
            return
        sign_out()
        # 登出后自动关闭同步开关
        cfg = load_config()
        cfg["sync_enabled"] = False
        save_config(cfg)
        self._refresh_status()

    def _show_stats(self, title: str, stats: dict):
        """显示同步统计"""
        self._refresh_status()
        self._set_progress("")
        lines = [title, ""]
        for table, count in stats.items():
            lines.append(f"  {table}: {count}")
        messagebox.showinfo("同步结果", "\n".join(lines), parent=self)

    def _set_progress(self, text: str):
        """更新进度文本（线程安全）"""
        self.after(0, lambda: self.progress_label.configure(text=text))

    def _run_async(self, task, on_success=None, action_name: str = ""):
        """在后台线程执行 task，成功后回调 on_success。
        task: 无参函数，返回结果或抛异常
        on_success: 接收 task 的返回值
        """
        def worker():
            try:
                result = task()
                if on_success:
                    self.after(0, lambda: on_success(result))
            except AuthExpiredError as e:
                msg = f"登录已过期：{e}\n请重新登录"
                self.after(0, lambda: messagebox.showerror(f"{action_name}失败", msg, parent=self))
                self.after(0, lambda: self._refresh_status())
            except SyncError as e:
                msg = str(e)
                self.after(0, lambda: messagebox.showerror(f"{action_name}失败", msg, parent=self))
            except Exception as e:
                msg = f"未知错误：{type(e).__name__}: {e}"
                self.after(0, lambda: messagebox.showerror(f"{action_name}失败", msg, parent=self))
            finally:
                self.after(0, lambda: self._set_progress(""))

        threading.Thread(target=worker, daemon=True).start()
