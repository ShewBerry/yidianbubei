# ui/errors.py
"""UI 层写操作失败提示工具。

数据库写操作失败必须显式告知用户——静默失败等价于悄悄丢数据。
全局兜底见 main.py 的 _install_global_exception_hook；这里用于在写路径上
给出带上下文的中文提示，并允许调用方在失败后 return 中止后续状态变更
（避免"库里没写成、界面却以为成功了"的半写状态）。
"""
from tkinter import messagebox


def show_write_error(parent, exc, action: str = "操作"):
    """写库失败提示。action 示例："保存修改"、"记录评分"、"删除条目"。"""
    messagebox.showerror(
        "操作失败",
        f"{action}失败，数据未保存：\n{exc}",
        parent=parent)
