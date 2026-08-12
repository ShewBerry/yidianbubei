import customtkinter as ctk
from tkinter import ttk, messagebox, simpledialog
from datetime import date
from ui.theme import (title_font, heading_font, body_font,
                      COLOR_DANGER, COLOR_DANGER_HOVER, COLOR_ROUND2, COLOR_ROUND2_HOVER,
                      COLOR_NEUTRAL, COLOR_NEUTRAL_HOVER, COLOR_TEXT_SECONDARY)
from ui.errors import show_write_error


class CategoryPanel(ctk.CTkFrame):
    """分类管理面板：树形展示分类，支持增删改查；点击分类时联动过滤条目"""
    def __init__(self, parent, db, on_category_selected=None):
        super().__init__(parent)
        self.db = db
        self.on_category_selected = on_category_selected
        self.selected_category_id = None  # None 表示"全部"

        ctk.CTkLabel(self, text="分类管理", font=title_font()).pack(anchor="w", padx=15, pady=(15, 10))

        # 工具栏：高频操作一键，低频操作（上移/下移/刷新）折叠进“更多”菜单，
        # 避免窄窗口（minsize 700）下工具栏溢出
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=15, pady=(0, 5))
        ctk.CTkButton(toolbar, text="＋ 新建", width=80, font=body_font(),
                      command=self._add_category).pack(side="left", padx=(0, 5))
        ctk.CTkButton(toolbar, text="✎ 重命名", width=90, font=body_font(),
                      command=self._rename_category).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="🗑 删除", width=80, fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_HOVER,
                      font=body_font(), command=self._delete_category).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="🔁 二轮巩固", width=110, fg_color=COLOR_ROUND2, hover_color=COLOR_ROUND2_HOVER,
                      font=body_font(), command=self._start_round2).pack(side="left", padx=5)
        self._more_var = ctk.StringVar(value="⋯ 更多")
        ctk.CTkOptionMenu(toolbar, values=["⟲ 刷新", "⬆ 上移", "⬇ 下移"],
                          variable=self._more_var, width=90, font=body_font(),
                          command=self._on_more_menu).pack(side="left", padx=5)

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

    def _on_more_menu(self, choice: str):
        """“更多”菜单：低频操作分发；选择后重置显示，避免停留在上次选择。"""
        self._more_var.set("⋯ 更多")
        if choice == "⟲ 刷新":
            self.refresh()
        elif choice == "⬆ 上移":
            self._move_category("up")
        elif choice == "⬇ 下移":
            self._move_category("down")

    def refresh(self):
        # 记录当前展开的文件夹（分类 id），重建后恢复；首次打开无记录，默认全部折叠
        expanded = self._collect_expanded_ids()
        for item in self.tree.get_children():
            self.tree.delete(item)
        # 一次性拉取所有分类，内存中建树，避免 N+1 查询
        all_cats = self.db.get_categories()
        children_map = {}
        for cat in all_cats:
            children_map.setdefault(cat["parent_id"], []).append(cat)
        # "全部" 虚拟节点
        all_node = self.tree.insert("", "end", text="📂 全部条目", values=(None,), open=True)
        # 递归插入分类
        self._insert_children(all_node, None, children_map, expanded)
        # 默认选中"全部"
        self.tree.selection_set(all_node)

    def _collect_expanded_ids(self) -> set:
        """遍历当前树，收集处于展开状态的分类 id"""
        expanded = set()

        def walk(node):
            values = self.tree.item(node, "values")
            raw = values[0] if values else None
            if raw not in (None, "None", ""):
                try:
                    cat_id = int(raw)
                except (ValueError, TypeError):
                    cat_id = None
                if cat_id is not None and self.tree.item(node, "open"):
                    expanded.add(cat_id)
            for child in self.tree.get_children(node):
                walk(child)

        for top in self.tree.get_children():
            walk(top)
        return expanded

    def _insert_children(self, parent_node, parent_id, children_map, expanded):
        for cat in children_map.get(parent_id, []):
            node = self.tree.insert(parent_node, "end", text=f"📁 {cat['name']}",
                                    values=(cat["id"],),
                                    open=(cat["id"] in expanded))
            self._insert_children(node, cat["id"], children_map, expanded)

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
        try:
            self.db.create_category(name, parent_id=parent_id)
        except Exception as e:
            show_write_error(self, e, "新建分类")
            return
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
        try:
            self.db.rename_category(cat_id, new_name.strip())
        except Exception as e:
            show_write_error(self, e, "重命名分类")
            return
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
        try:
            self.db.delete_category(cat_id)
        except Exception as e:
            show_write_error(self, e, "删除分类")
            return
        self.refresh()

    def _move_category(self, direction: str):
        """上移/下移选中分类（在同级兄弟中排序）"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中要移动的分类", parent=self)
            return
        values = self.tree.item(selection[0], "values")
        if not values or values[0] in (None, "None", ""):
            messagebox.showwarning("提示", "“全部条目”不能移动", parent=self)
            return
        cat_id = int(values[0])
        try:
            self.db.move_category(cat_id, direction)
        except Exception as e:
            show_write_error(self, e, "移动分类")
            return
        self.refresh()
        # 重新选中刚移动的分类，方便连续操作
        self._select_category_by_id(cat_id)

    def _select_category_by_id(self, cat_id: int):
        """根据分类 id 在树中找到对应节点并选中"""
        for node in self.tree.get_children():
            if self._select_recursive(node, cat_id):
                return

    def _select_recursive(self, node, cat_id: int) -> bool:
        values = self.tree.item(node, "values")
        if values and values[0] not in (None, "None", ""):
            try:
                if int(values[0]) == cat_id:
                    self.tree.selection_set(node)
                    self.tree.see(node)
                    return True
            except (ValueError, TypeError):
                pass
        for child in self.tree.get_children(node):
            if self._select_recursive(child, cat_id):
                return True
        return False

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
        try:
            self.db.batch_update_round2(item_ids, date.today())
        except Exception as e:
            show_write_error(self, e, "启动二轮巩固")
            return
        messagebox.showinfo("完成", f"已对 {len(items)} 条目启动二轮巩固", parent=self)
        self.refresh()
