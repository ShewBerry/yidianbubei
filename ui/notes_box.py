# ui/notes_box.py
import customtkinter as ctk
from ui.theme import small_font, body_font, COLOR_TEXT_SECONDARY
from ui.errors import show_write_error


class NotesBox(ctk.CTkFrame):
    """条目级笔记框：失焦时自动保存到数据库。
    在今日背诵展开内容和全部条目展开时复用。
    """
    def __init__(self, parent, db, item_id: int, current_notes: str = "",
                 height: int = 80):
        super().__init__(parent, fg_color="transparent")
        self.db = db
        self.item_id = item_id
        self._initial_notes = current_notes or ""

        ctk.CTkLabel(self, text="📝 笔记", font=small_font(),
                     text_color=COLOR_TEXT_SECONDARY).pack(anchor="w", padx=2, pady=(0, 2))

        self.textbox = ctk.CTkTextbox(self, height=height, font=body_font())
        self.textbox.pack(fill="x")
        if current_notes:
            self.textbox.insert("1.0", current_notes)
        # 失焦时自动保存
        self.textbox.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_out(self, event=None):
        try:
            new_notes = self.textbox.get("1.0", "end").rstrip("\n")
            if new_notes != self._initial_notes:
                self.db.update_item(self.item_id, notes=new_notes)
                self._initial_notes = new_notes
        except Exception as e:
            show_write_error(self, e, "保存笔记")

    def destroy(self):
        # 组件销毁前再保存一次，避免遗漏
        try:
            self._on_focus_out()
        except Exception:
            pass
        super().destroy()
