# ui/review_panel.py
import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
from datetime import date, timedelta
from scheduler import Scheduler
from ui.theme import (
    title_font, heading_font, review_title_font, body_font, small_font,
    COLOR_PERFECT, COLOR_PERFECT_HOVER,
    COLOR_MOSTLY, COLOR_MOSTLY_HOVER,
    COLOR_PARTIAL, COLOR_PARTIAL_HOVER,
    COLOR_FORGOTTEN, COLOR_FORGOTTEN_HOVER,
    COLOR_WRONG, COLOR_WRONG_HOVER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, PRIMARY, FONT_FAMILY,
    BTN_OUTLINE_WARN_BORDER, BTN_OUTLINE_WARN_TEXT, BTN_OUTLINE_WARN_HOVER,
)
from ui.errors import show_write_error
from ui.markable_textbox import MarkableTextbox
from ui.notes_box import NotesBox


class ReviewPanel(ctk.CTkFrame):
    """今日待背诵面板：卡片式单张展示，4级评分交互"""
    # 背诵区最小高度：保证窗口模式下至少能显示两行正文（含标记工具栏约30px）。
    # 以正文 16-18px 计，两行 ≈ 40-45px，加工具栏后取 90px 更稳妥。
    MIN_CONTENT_H = 90

    def __init__(self, parent, db, scheduler: Scheduler, on_data_changed=None):
        super().__init__(parent)
        self.db = db
        self.scheduler = scheduler
        self.on_data_changed = on_data_changed
        self.queue = []  # 今日队列 [{item, is_retest}]
        self.completed_count = 0
        self.total_count = 0

        self.title_label = ctk.CTkLabel(self, text="今日待背诵", font=title_font())
        self.title_label.pack(anchor="w", padx=15, pady=(15, 5))

        self.progress_label = ctk.CTkLabel(self, text="", text_color=COLOR_TEXT_SECONDARY,
                                           font=body_font())
        self.progress_label.pack(pady=(0, 5))

        # 进度条
        self.progress_bar = ctk.CTkProgressBar(self, progress_color=PRIMARY, height=6)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=60, pady=(0, 10))

        # 明日待背诵数量提示（随进度刷新同步更新）
        self.tomorrow_label = ctk.CTkLabel(
            self, text="明日待背诵：0 条", text_color=COLOR_TEXT_SECONDARY,
            font=small_font())
        self.tomorrow_label.pack(pady=(0, 5))

        self.card_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.card_frame.pack(fill="both", expand=True, padx=30, pady=(0, 15))
        # 不在构造时 refresh——由 MainWindow 在 mainloop 启动后用 after 触发，
        # 避免启动时 DB 查询阻塞窗口显示

    def refresh(self):
        """刷新今日队列。

        - 队列非空时（背诵进行中）：先同步队列状态（移除已删除条目、刷新已编辑条目数据），
          再追加新出现的 due 条目到末尾。保留 is_retest/show_content 等运行时状态。
        - 队列为空时：从数据库完整重建队列。
        """
        today = date.today()
        due_items = self.db.get_due_items(today)
        reviewed_ids = self.db.get_today_reviewed_item_ids(today)

        if self.queue:
            # 背诵进行中：同步队列（移除已删除/已不在 due 的条目，刷新已编辑的条目数据）
            due_map = {i["id"]: i for i in due_items}
            new_queue = []
            for q in self.queue:
                item_id = q["item"]["id"]
                if item_id in due_map:
                    # 仍在 due 中：刷新 item 数据（标题/内容等可能已被编辑），保留运行时状态
                    q["item"] = due_map[item_id]
                    new_queue.append(q)
                # else: 已软删除或已不在 due（如被改到未来），从队列丢弃
            self.queue = new_queue
            # 追加新出现的 due 条目（不在队列中的）
            existing_ids = {q["item"]["id"] for q in self.queue}
            for item in due_items:
                if item["id"] not in existing_ids:
                    is_retest = item["id"] in reviewed_ids
                    self.queue.append({"item": item, "is_retest": is_retest})
            # 重新计算 completed_count（其他操作可能新增了今日 perfect 评分）
            today_perfect = self.db.get_perfect_count_in_range(today, today)
            due_perfect_in_logs = 0
            if due_items:
                due_ids = [i["id"] for i in due_items]
                due_perfect_in_logs = self._count_perfect_in_logs(today, due_ids)
            self.completed_count = today_perfect - due_perfect_in_logs
            self.total_count = len(self.queue) + self.completed_count
            self._update_progress()
            self._render_current_card()
        else:
            # 队列为空：完整重建
            # 循环型队列：未评分条目优先，已评分的重背条目排后。
            # 这样关闭软件重开后，会从第一个未处理的条目开始，而不是从已评过分的重背条目重新开始。
            for widget in self.card_frame.winfo_children():
                widget.destroy()
            unscheduled = []
            rescheduled = []
            for item in due_items:
                if item["id"] in reviewed_ids:
                    rescheduled.append({"item": item, "is_retest": True})
                else:
                    unscheduled.append({"item": item, "is_retest": False})
            self.queue = unscheduled + rescheduled
            # 从数据库恢复今日已完成数（perfect 评分且不再 due 的条目）
            # = 今日 perfect 评分总数 - 仍在 due 中的 perfect（重背后又 perfect 的情况极少，忽略）
            today_perfect = self.db.get_perfect_count_in_range(today, today)
            # 今日 due 中的 perfect 次数（重背后又 perfect 的条目，这些已在队列中）
            due_perfect_in_logs = 0
            if due_items:
                due_ids = [i["id"] for i in due_items]
                due_perfect_in_logs = self._count_perfect_in_logs(today, due_ids)
            self.completed_count = today_perfect - due_perfect_in_logs
            self.total_count = self.completed_count + len(self.queue)
            self._update_progress()
            self._render_current_card()

    def _count_perfect_in_logs(self, today, item_ids):
        """统计今日这些条目的 perfect 评分次数（用于避免重复计数）"""
        today_str = today.isoformat() if hasattr(today, "isoformat") else today
        placeholders = ",".join("?" * len(item_ids))
        cursor = self.db.conn.execute(
            f"SELECT COUNT(*) FROM review_logs WHERE review_date=? AND result='perfect' AND item_id IN ({placeholders})",
            [today_str] + item_ids)
        return cursor.fetchone()[0]

    def _update_progress(self):
        if self.total_count == 0:
            self.progress_label.configure(text="")
            self.progress_bar.set(0)
        else:
            self.progress_label.configure(
                text=f"{self.completed_count} / {self.total_count} 已完成")
            self.progress_bar.set(self.completed_count / self.total_count)
        self._update_tomorrow_count()

    def _update_tomorrow_count(self):
        """刷新明日待背诵条目数（评分可能把条目排到明天，需同步更新）。"""
        try:
            tomorrow = date.today() + timedelta(days=1)
            count = self.db.count_items_due_on(tomorrow)
            self.tomorrow_label.configure(text=f"明日待背诵：{count} 条")
        except Exception:
            pass

    def _render_current_card(self):
        for widget in self.card_frame.winfo_children():
            widget.destroy()

        if not self.queue:
            self._render_complete_state()
            return

        current = self.queue[0]
        item = current["item"]
        stage_desc = self.scheduler.stage_description(
            item["consecutive_correct"], item["round"])

        card = ctk.CTkFrame(self.card_frame, corner_radius=10)
        card.pack(fill="both", expand=True, pady=10)

        header = ctk.CTkFrame(card, fg_color="transparent")
        # header 的 pack/grid 布局在下方分支内完成（card 同一容器不能混用 pack/grid）
        ctk.CTkLabel(header, text=item['title'],
                     font=review_title_font()).pack(side="left")
        ctk.CTkLabel(header, text=stage_desc, text_color=COLOR_TEXT_SECONDARY,
                     font=body_font()).pack(side="right")
        ctk.CTkButton(header, text="⭐ 加入重点", width=90, height=28,
                      fg_color="transparent", border_width=2,
                      border_color=BTN_OUTLINE_WARN_BORDER, text_color=BTN_OUTLINE_WARN_TEXT,
                      hover_color=BTN_OUTLINE_WARN_HOVER, font=body_font(),
                      command=lambda: self._mark_key(item)).pack(side="right", padx=(6, 0))

        if current.get("show_content"):
            # 卡片内部改用 grid 布局（card 内不能用 pack：pack 在窗口较小时会把
            # expand 的背诵区压缩到不足两行，无法设最小高度；grid 的 rowconfigure
            # minsize 可保证背诵区最小高度）。
            # 行布局：row0 header → row1 背诵区(weight=1, minsize=MIN_CONTENT_H)
            #          → row2 分隔条 → row3 笔记区 → row4 评分按钮
            card.grid_columnconfigure(0, weight=1)
            card.grid_rowconfigure(0, weight=0)   # header
            card.grid_rowconfigure(1, weight=1, minsize=self.MIN_CONTENT_H)  # 背诵区
            card.grid_rowconfigure(2, weight=0)   # 分隔条
            card.grid_rowconfigure(3, weight=0)   # 笔记区
            card.grid_rowconfigure(4, weight=0)   # 评分按钮

            header.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 5))

            # 评分按钮固定底部
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.grid(row=4, column=0, sticky="ew", padx=20, pady=(5, 15))

            ctk.CTkButton(btn_frame, text="✓ 完全正确", height=42,
                          fg_color=COLOR_PERFECT, hover_color=COLOR_PERFECT_HOVER,
                          font=heading_font(),
                          command=lambda: self._handle_review("perfect")).pack(side="left", padx=4, expand=True)
            ctk.CTkButton(btn_frame, text="👍 基本正确", height=42,
                          fg_color=COLOR_MOSTLY, hover_color=COLOR_MOSTLY_HOVER,
                          font=heading_font(),
                          command=lambda: self._handle_review("mostly_correct")).pack(side="left", padx=4, expand=True)
            ctk.CTkButton(btn_frame, text="🤔 部分正确", height=42,
                          fg_color=COLOR_PARTIAL, hover_color=COLOR_PARTIAL_HOVER,
                          text_color=COLOR_TEXT_PRIMARY,
                          font=heading_font(),
                          command=lambda: self._handle_review("partial")).pack(side="left", padx=3, expand=True)
            ctk.CTkButton(btn_frame, text="😕 较多遗忘", height=42,
                          fg_color=COLOR_FORGOTTEN, hover_color=COLOR_FORGOTTEN_HOVER,
                          font=heading_font(),
                          command=lambda: self._handle_review("mostly_forgotten")).pack(side="left", padx=3, expand=True)
            ctk.CTkButton(btn_frame, text="✗ 记错了", height=42,
                          fg_color=COLOR_WRONG, hover_color=COLOR_WRONG_HOVER,
                          font=heading_font(),
                          command=lambda: self._handle_review("wrong")).pack(side="left", padx=3, expand=True)

            # 自定义布局（不用 tk.PanedWindow：其 sash_place 在 CTkFrame pane 下
            # 实测失效，窗口放大后 sash 不重排，导致全屏下半部分空白）。
            # 笔记区高度用 grid 固定行 + pack_propagate(False) + configure(height) 精确控制，
            # 分隔条为自绘 Frame，bind 鼠标事件实现拖拽。

            # 笔记区（row3：位于评分按钮上方，可折叠；默认收起 24px 只显示标题行）
            self._notes_expanded = False
            self._dragging = False
            self.notes_section = ctk.CTkFrame(card, fg_color="transparent")
            self.notes_section.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 2))
            self.notes_section.pack_propagate(False)

            # 笔记标题行：纯文字「笔记」+ 展开/收起箭头，无灰框背景
            notes_header = ctk.CTkFrame(self.notes_section, fg_color="transparent")
            notes_header.pack(side="top", fill="x")
            ctk.CTkLabel(notes_header, text="📝 笔记", font=small_font(),
                         text_color=COLOR_TEXT_SECONDARY).pack(side="left", padx=2)
            self.notes_toggle = ctk.CTkButton(
                notes_header, text="▲", width=26, height=18,
                fg_color="transparent", border_width=1,
                border_color=BTN_OUTLINE_WARN_BORDER, text_color=BTN_OUTLINE_WARN_TEXT,
                hover_color=BTN_OUTLINE_WARN_HOVER, font=small_font(),
                command=self._toggle_notes)
            self.notes_toggle.pack(side="right", padx=2)

            # 笔记文本框（展开时显示，fill both+expand 填满笔记区，可滚动）
            self.notes_box = NotesBox(self.notes_section, self.db, item["id"],
                                      current_notes=item.get("notes", ""), height=70,
                                      show_label=False)

            # 分隔条（row2：可拖拽调节背诵区与笔记区高度）
            self.sash = tk.Frame(card, height=8, bg="gray60", cursor="sb_v_double_arrow")
            self.sash.grid(row=2, column=0, sticky="ew", padx=20, pady=(2, 0))
            self.sash.bind("<ButtonPress-1>", self._on_sash_press)
            self.sash.bind("<B1-Motion>", self._on_sash_drag)
            self.sash.bind("<ButtonRelease-1>", self._on_sash_release)

            # 背诵区（row1：占剩余全部高度，grid minsize 保证最小高度可显示两行正文）
            self.markable_box = MarkableTextbox(card, self.db, item, read_only_marks=False)
            self.markable_box.grid(row=1, column=0, sticky="nsew", padx=20, pady=(5, 0))

            # 初始高度：收起态 24px；展开态按保存比例（默认 25%，背诵:笔记=3:1）
            self._apply_notes_height()
            # 窗口尺寸变化（拉大/全屏）时按比例重算笔记高度，避免下方留白
            card.bind("<Configure>", self._on_card_resize, add="+")
        else:
            header.pack(fill="x", padx=20, pady=(15, 5))
            ctk.CTkLabel(card, text="先回忆内容，再点下方按钮查看正文",
                         text_color=COLOR_TEXT_SECONDARY, font=body_font()).pack(pady=40)
            ctk.CTkButton(card, text="📖 展示内容", width=160, height=38,
                          fg_color=PRIMARY, hover_color=COLOR_PERFECT_HOVER,
                          font=heading_font(),
                          command=self._show_content).pack(pady=10)

    def _apply_notes_height(self):
        """按当前状态设置笔记区高度（pack 布局 + pack_propagate(False) 精确控制）。

        - 笔记收起：24px（仅标题行：笔记文字 + 箭头）；
        - 笔记展开：可用高度 × 保存比例（默认 25%，即背诵:笔记 = 3:1）。
        全屏/拉大窗口时 card <Configure> 触发 _on_card_resize → 本方法按比例重算，
        背诵区（markable_box, fill both+expand）自动占满剩余高度，底部无留白。
        拖拽分隔条期间（_dragging=True）不执行，避免覆盖用户拖到的位置。
        """
        try:
            if getattr(self, "_dragging", False):
                return
            card = self.notes_section.master
            card_h = card.winfo_height()
            if card_h <= 1:
                # 窗口未渲染完成，稍后重试
                self.after(60, self._apply_notes_height)
                return
            if not getattr(self, "_notes_expanded", False):
                self.notes_section.configure(height=24)
                return
            ratio = float(self.db.get_setting("notes_section_ratio", "0.25"))
            # 可用高度 = 卡片高度 - 固定开销（标题/评分按钮/分隔条，约 160px）
            avail = max(200, card_h - 160)
            h = int(avail * ratio)
            h = max(30, min(h, avail - self.MIN_CONTENT_H))  # 背诵区至少 MIN_CONTENT_H
            self.notes_section.configure(height=h)
        except Exception:
            pass

    def _on_card_resize(self, event=None):
        """卡片（背诵+笔记容器）尺寸变化（窗口拉大/全屏）时按比例重算笔记高度。
        防抖避免连续 Configure 反复设置；拖拽分隔条不改变卡片总高，不触发此回调。"""
        if event is None:
            return
        try:
            if hasattr(self, "_resize_id") and self._resize_id is not None:
                self.after_cancel(self._resize_id)
            self._resize_id = self.after(120, self._apply_notes_height)
        except Exception:
            pass

    def _on_sash_press(self, event=None):
        """分隔条按下：标记拖拽开始，记录起点。"""
        try:
            if event is None:
                return
            self._dragging = True
            self._drag_y0 = event.y_root
            self._notes_h0 = self.notes_section.winfo_height()
        except Exception:
            pass

    def _on_sash_drag(self, event=None):
        """分隔条拖拽：实时调整笔记区高度（向上拖增大笔记，向下拖减小）。"""
        try:
            if not getattr(self, "_dragging", False) or event is None:
                return
            delta = self._drag_y0 - event.y_root  # 向上拖为正
            new_h = self._notes_h0 + delta
            card = self.notes_section.master
            max_h = max(30, card.winfo_height() - 160 - self.MIN_CONTENT_H)  # 背诵区至少两行
            new_h = max(24, min(new_h, max_h))
            self.notes_section.configure(height=new_h)
        except Exception:
            pass

    def _on_sash_release(self, event=None):
        """分隔条释放：结束拖拽；展开态保存新比例，收起态复位。"""
        try:
            if not getattr(self, "_dragging", False):
                return
            self._dragging = False
            if getattr(self, "_notes_expanded", False):
                self._save_notes_ratio()
            else:
                self._apply_notes_height()  # 收起态拖拽无意义，复位
        except Exception:
            pass

    def _save_notes_ratio(self):
        """保存当前笔记区高度比例（笔记占可用高度的比例）到 settings。"""
        try:
            card = self.notes_section.master
            card_h = card.winfo_height()
            avail = max(200, card_h - 160)
            h = self.notes_section.winfo_height()
            ratio = max(0.1, min(0.6, h / avail))
            self.db.set_setting("notes_section_ratio", str(round(ratio, 3)))
        except Exception:
            pass

    def _toggle_notes(self):
        """展开/收起笔记区。收起时只显示标题行（笔记 + ▲），展开时显示文本框（▼）。"""
        try:
            self._notes_expanded = not self._notes_expanded
            if self._notes_expanded:
                self.notes_box.pack(fill="both", expand=True, pady=(2, 0))
                self.notes_toggle.configure(text="▼")  # 展开状态：点击收起
            else:
                self.notes_box.pack_forget()
                self.notes_toggle.configure(text="▲")  # 收起状态：点击展开
            self._apply_notes_height()
        except Exception:
            pass

    def _render_complete_state(self):
        """今日背诵完成的庆祝态"""
        card = ctk.CTkFrame(self.card_frame, corner_radius=10)
        card.pack(fill="both", expand=True, pady=10)

        ctk.CTkLabel(card, text="🎉", font=ctk.CTkFont(size=48)).pack(pady=(50, 10))
        ctk.CTkLabel(card, text="今日背诵完成", font=ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold")).pack(pady=5)

        # 显示今日统计
        today = date.today()
        completed = self.db.get_perfect_count_in_range(today, today)
        if completed > 0:
            ctk.CTkLabel(card, text=f"今天完成了 {completed} 条背诵",
                         text_color=COLOR_TEXT_SECONDARY, font=body_font()).pack(pady=(5, 30))
        else:
            ctk.CTkLabel(card, text="休息一下，明天继续加油",
                         text_color=COLOR_TEXT_SECONDARY, font=body_font()).pack(pady=(5, 30))

    def _show_content(self):
        if self.queue:
            self.queue[0]["show_content"] = True
            self._render_current_card()

    def _mark_key(self, item):
        from ui.key_folder_dialog import KeyFolderDialog

        def on_confirm(folder_id):
            try:
                self.db.add_item_to_key_folder(folder_id, item["id"])
            except Exception as e:
                show_write_error(self, e, "加入重点")
                return
            messagebox.showinfo("提示", "已加入重点条目", parent=self)
            # 与列表面板入口保持一致：触发全局刷新
            if self.on_data_changed:
                self.on_data_changed()

        KeyFolderDialog(self, self.db, item["id"], on_confirm=on_confirm)

    def _handle_review(self, result: str):
        if not self.queue:
            return
        current = self.queue[0]
        item = current["item"]
        today = date.today()

        # 评分前先保存笔记（NotesBox 失焦保存可能未触发）
        if hasattr(self, "notes_box"):
            try:
                self.notes_box._on_focus_out()
            except Exception:
                pass

        # 记录本轮评分历史（用于结束时的最终效力计算）
        current.setdefault("session_results", [])
        current["session_results"].append(result)

        # 调度评分并写库（失败时提示并中止，避免队列状态与库不一致）
        try:
            sched_result = self.scheduler.apply(
                self.db, item, today, result,
                is_retest=current["is_retest"],
                session_results=current["session_results"])
        except Exception as e:
            show_write_error(self, e, "记录评分")
            return

        if sched_result["requeue_today"]:
            # 延续类：移到队列末尾重背，调度状态保持不变（效力在结束时才确定）
            current["is_retest"] = True
            current["show_content"] = False
            self.queue.pop(0)
            self.queue.append(current)
        else:
            # 完成或移出队列
            self.queue.pop(0)
            self.completed_count += 1

        self._update_progress()
        self._render_current_card()

        if self.on_data_changed and not sched_result["requeue_today"]:
            self.on_data_changed()
