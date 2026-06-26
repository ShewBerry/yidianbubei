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
COLOR_PERFECT = "#40916c"       # 翠绿 - 完全正确
COLOR_PERFECT_HOVER = "#2d6a4f"
COLOR_MOSTLY = "#1b6ca8"        # 青蓝 - 基本正确（与主色区分但同属冷色）
COLOR_MOSTLY_HOVER = "#145985"
COLOR_PARTIAL = "#e09f3e"       # 琥珀 - 部分正确
COLOR_PARTIAL_HOVER = "#c68428"
COLOR_WRONG = "#c1554b"         # 砖红 - 记错了
COLOR_WRONG_HOVER = "#a23e36"

# === 功能色 ===
COLOR_DANGER = "#c1554b"
COLOR_DANGER_HOVER = "#a23e36"
COLOR_NEUTRAL = "#6c757d"       # 中性灰 - 次要按钮（展开/收起/历史/编辑）
COLOR_NEUTRAL_HOVER = "#5a6268"
COLOR_WARN = "#e09f3e"          # 补签
COLOR_WARN_HOVER = "#c68428"
COLOR_ROUND2 = "#8e44ad"        # 二轮巩固 - 紫
COLOR_ROUND2_HOVER = "#7d3c98"

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
