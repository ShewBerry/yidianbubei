import customtkinter as ctk
from tkinter import ttk, messagebox, simpledialog
from datetime import date


class CategoryPanel(ctk.CTkFrame):
    """分类管理面板：树形展示分类，支持增删改查；点击分类时联动过滤条目"""
    def __init__(self, parent, db, on_category_selected=None):
        super().__init__(parent)
        self.db = db
        self.on_category_selected = on_category_selected
        self.selected_category_id = None  # None 表示"全部"

        ctk.CTkLabel(self, text="分类管理", font=title_font()).pack(pady=(15, 10))

        # 工具栏
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=15, pady=(0, 5))
        ctk.CTkButton(toolbar, text="＋ 新建", width=80, font=body_font(),
                      command=self._add_category).pack(side="left", padx=(0, 5))
        ctk.CTkButton(toolbar, text="✎ 重命名", width=90, font=body_font(),
                      command=self._rename_category).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="🗑 删除", width=80, fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_HOVER,
                      font=body_font(), command=self._delete_category).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="⟲ 刷新", width=80, fg_color=COLOR_NEUTRAL, hover_color=COLOR_NEUTRAL_HOVER,
                      font=body_font(), command=self.refresh).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="🔁 二轮巩固", width=110, fg_color=COLOR_ROUND2, hover_color=COLOR_ROUND2_HOVER,
                      font=body_font(), command=self._start_round2).pack(side="left", padx=5)

        # 树形视图容器
        tree_container = ctk.CTkFrame(self)
        tree_container.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.tree = ttk.Treeview(tree_container, columns=("id",), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="分类")
        self.tree.column("#0", width=300)
        self.tree.column("id", width=0, stretch=False)  # 隐藏 id 列
        self.tree.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.refresh()

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        # "全部" 虚拟节点
        all_node = self.tree.insert("", "end", text="📂 全部条目", values=(None,), open=True)
        # 递归插入分类
        self._insert_children(all_node, None)
        # 默认选中"全部"
        self.tree.selection_set(all_node)

    def _insert_children(self, parent_node, parent_id):
        children = self.db.get_category_children(parent_id)
        for cat in children:
            node = self.tree.insert(parent_node, "end", text=f"📁 {cat['name']}", values=(cat["id"],), open=True)
            self._insert_children(node, cat["id"])

    def _on_select(self, event):
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        raw = values[0] if values else None
        # Treeview values 存的是字符串，需转换：None/"None"/"" -> None（全部），否则转 int
        if raw in (None, "None", "", "None"):
            cat_id = None
        else:
            try:
                cat_id = int(raw)
            except (ValueError, TypeError):
                cat_id = None
        self.selected_category_id = cat_id
        if self.on_category_selected:
            self.on_category_selected(cat_id)

    def _add_category(self):
        # 确定父分类：选中"全部"或未选中则顶层，否则以选中节点为父
        selection = self.tree.selection()
        parent_id = None
        if selection:
            values = self.tree.item(selection[0], "values")
            if values and values[0] not in (None, "None", ""):
                parent_id = int(values[0])

        name = simpledialog.askstring("新建分类", "请输入分类名称：", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        self.db.create_category(name, parent_id=parent_id)
        self.refresh()

    def _rename_category(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中要重命名的分类", parent=self)
            return
        values = self.tree.item(selection[0], "values")
        if not values or values[0] in (None, "None", ""):
            messagebox.showwarning("提示", "不能重命名“全部条目”", parent=self)
            return
        cat_id = int(values[0])
        old_name = self.tree.item(selection[0], "text").replace("📁 ", "")
        new_name = simpledialog.askstring("重命名分类", "请输入新名称：", initialvalue=old_name, parent=self)
        if not new_name or not new_name.strip():
            return
        self.db.rename_category(cat_id, new_name.strip())
        self.refresh()

    def _delete_category(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中要删除的分类", parent=self)
            return
        values = self.tree.item(selection[0], "values")
        if not values or values[0] in (None, "None", ""):
            messagebox.showwarning("提示", "不能删除“全部条目”", parent=self)
            return
        cat_id = int(values[0])
        name = self.tree.item(selection[0], "text").replace("📁 ", "")
        if not messagebox.askyesno("确认删除",
                                    f"确定删除分类“{name}”吗？\n\n子分类会被一起删除，该分类下的条目会变成“未分类”。",
                                    parent=self):
            return
        self.db.delete_category(cat_id)
        self.refresh()

    def _start_round2(self):
        """二轮巩固：将选中分类下全部mastered的条目重置为二轮状态"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中要启动二轮巩固的分类", parent=self)
            return
        values = self.tree.item(selection[0], "values")
        if not values or values[0] in (None, "None", ""):
            messagebox.showwarning("提示", "请在具体分类上启动二轮巩固（不支持“全部条目”）", parent=self)
            return
        cat_id = int(values[0])

        # 获取该分类及所有子孙分类下的条目
        items = self.db.get_items_by_category(cat_id, include_descendants=True)
        if not items:
            messagebox.showinfo("提示", "该分类下没有条目", parent=self)
            return

        # 检查是否全部 mastered（一轮完成）
        not_mastered = [i for i in items if i["status"] != "mastered"]
        if not_mastered:
            messagebox.showwarning("提示",
                f"还有 {len(not_mastered)} 条目未完成一轮，无法开始二轮", parent=self)
            return

        # 全部完成，弹确认框
        name = self.tree.item(selection[0], "text").replace("📁 ", "")
        if not messagebox.askyesno("确认二轮巩固",
            f"确认对分类“{name}”下 {len(items)} 条目启动二轮巩固？\n\n"
            f"这些条目将重置为二轮状态，间隔为 3/7/14 天。",
            parent=self):
            return

        # 批量重置
        item_ids = [i["id"] for i in items]
        self.db.batch_update_round2(item_ids, date.today())
        messagebox.showinfo("完成", f"已对 {len(items)} 条目启动二轮巩固", parent=self)
        self.refresh()
