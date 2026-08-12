# ui/theme.py
"""统一配色与字体常量。

美学方向：柔和编辑风（Soft Editorial）
- 墨绿主色：专注、自然，适合长时间背诵，不刺眼
- 琥珀强调：温暖提醒，用于补签/部分正确等需注意的场景
- 砖红错误：柔和而非刺眼的警示色
- 慷慨留白，清晰的卡片层级
"""
import customtkinter as ctk

# === 主色调 ===
PRIMARY = "#2d6a4f"        # 墨绿 - 主操作、标题强调
PRIMARY_HOVER = "#1b4332"  # 深墨绿

# === 评分结果色（4级，由好到差）===
# 注意：以下 HOVER 色与功能色存在同值别名（如 COLOR_PERFECT_HOVER == PRIMARY、
# COLOR_DANGER == COLOR_WRONG、COLOR_WARN == COLOR_PARTIAL），
# 语义相互独立，调色时可按各自场景分开调整，不必保持同值。
COLOR_PERFECT = "#40916c"       # 翠绿 - 完全正确
COLOR_PERFECT_HOVER = "#2d6a4f"
COLOR_MOSTLY = "#1b6ca8"        # 青蓝 - 基本正确（与主色区分但同属冷色）
COLOR_MOSTLY_HOVER = "#145985"
COLOR_PARTIAL = "#e09f3e"       # 琥珀 - 部分正确
COLOR_PARTIAL_HOVER = "#c68428"
COLOR_FORGOTTEN = "#cd6e4a"     # 红橙 - 较多遗忘
COLOR_FORGOTTEN_HOVER = "#b35a3a"
COLOR_WRONG = "#c1554b"         # 砖红 - 记错了
COLOR_WRONG_HOVER = "#a23e36"

# === 功能色 ===
# COLOR_DANGER/COLOR_WARN 与评分色当前同值（砖红/琥珀），语义不同：
# 危险操作（删除）用 DANGER，提醒操作（补签）用 WARN。
COLOR_DANGER = "#c1554b"
COLOR_DANGER_HOVER = "#a23e36"
COLOR_NEUTRAL = "#6c757d"       # 中性灰 - 次要按钮（展开/收起/历史/编辑）
COLOR_NEUTRAL_HOVER = "#5a6268"
COLOR_WARN = "#e09f3e"          # 补签
COLOR_WARN_HOVER = "#c68428"
COLOR_ROUND2 = "#8e44ad"        # 二轮巩固 - 紫
COLOR_ROUND2_HOVER = "#7d3c98"

# === 描边按钮（outline 风格）===
# 值均为 [浅色模式, 深色模式]，customtkinter 会按当前外观模式自动选择，
# 保证两种模式下文字与背景均保持高对比度。
# 描边次要按钮（如顶栏辅助操作）：墨绿描边 + 同色系文字，与 PRIMARY 主按钮呼应
BTN_OUTLINE_BORDER = ["#2d6a4f", "#74c69d"]
BTN_OUTLINE_TEXT = ["#1b4332", "#d8f3dc"]
BTN_OUTLINE_HOVER = ["#d8f3dc", "#1b4332"]
# 加入重点（⭐ 星标语义）：琥珀描边 + 同色系文字，呼应 COLOR_WARN
BTN_OUTLINE_WARN_BORDER = ["#c68428", "#e0a94e"]
BTN_OUTLINE_WARN_TEXT = ["#8a5a00", "#ffe8b3"]
BTN_OUTLINE_WARN_HOVER = ["#fdeecb", "#8a6109"]

# === 文字 ===
COLOR_TEXT_PRIMARY = "#212529"
COLOR_TEXT_SECONDARY = "#6c757d"

# === 字体（Windows 微软雅黑，比默认 TkFont 更清爽）===
FONT_FAMILY = "微软雅黑"


def title_font():
    return ctk.CTkFont(family=FONT_FAMILY, size=20, weight="bold")


def heading_font():
    return ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold")


def card_title_font():
    return ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold")


def review_title_font():
    return ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold")


def body_font():
    return ctk.CTkFont(family=FONT_FAMILY, size=13)


def small_font():
    return ctk.CTkFont(family=FONT_FAMILY, size=12)


def big_font():
    return ctk.CTkFont(family=FONT_FAMILY, size=18)
