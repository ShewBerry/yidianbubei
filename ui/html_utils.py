# ui/html_utils.py
"""轻量富文本 HTML 工具：HTML ↔ tkinter Text tag 互转、纯文本提取。

支持的 HTML 子集（向后兼容纯文本）：
- <b>...</b> 粗体
- <i>...</i> 斜体
- <u>...</u> 下划线
- <span style="color:#RRGGBB">...</span> 文字颜色
- <span style="font-size:N">...</span> 字号
- <br> 换行

标记系统偏移基于"渲染后的可见纯文本"，HTML 标签不计入偏移。
"""
import html as _html
import re
from html.parser import HTMLParser


# ============ 纯文本提取 ============
def html_to_plain_text(html_str: str) -> str:
    """把 HTML 转为纯文本（去掉所有标签）。
    用于 _shift_marks 计算旧/新长度。
    """
    if not _looks_like_html(html_str):
        return html_str
    return _HtmlToPlain().feed_text(html_str)


def _looks_like_html(s: str) -> bool:
    """包含常见 HTML 标签的视为 HTML。
    支持编辑器生成的 b/i/u/span，以及外部导入的 p/div/strong/em/font/h1-h6 等。"""
    return bool(re.search(r"<(b|i|u|span|br|p|div|strong|em|font|h[1-6])(\s|>|/)", s, re.IGNORECASE))


# ============ HTML → 段列表（带 tag）============
def html_to_segments(html_str: str):
    """把 HTML 解析为 [(text, frozenset(tags)), ...] 段列表。

    tags 是字符串集合，可能值：
    - 'b' 'i' 'u'
    - 'color:#RRGGBB'
    - 'size:N'

    纯文本输入返回 [(text, frozenset())]。
    """
    if not _looks_like_html(html_str):
        return [(html_str, frozenset())]
    parser = _HtmlToSegments()
    parser.feed(html_str)
    parser.close()
    return parser.segments


class _HtmlToPlain(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def feed_text(self, s):
        self._parts = []
        self.feed(s)
        self.close()
        return "".join(self._parts)

    def handle_data(self, data):
        self._parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "br":
            self._parts.append("\n")

    def handle_entityref(self, name):
        import html.entities
        self._parts.append(html.entities.html5.get(name + ";", f"&{name};"))


class _HtmlToSegments(HTMLParser):
    """把 HTML 转为段列表。每个段 = (text, frozenset(tags))。"""

    def __init__(self):
        super().__init__()
        self.segments = []
        self._tag_stack = []
        self._buf = []
        self._buf_tags = frozenset()

    def _flush(self):
        if self._buf:
            self.segments.append(("".join(self._buf), self._buf_tags))
            self._buf = []

    def _push(self, tag_str):
        self._flush()
        self._tag_stack.append(self._buf_tags)
        self._buf_tags = self._buf_tags | {tag_str}

    def _pop(self):
        self._flush()
        if self._tag_stack:
            self._buf_tags = self._tag_stack.pop()

    def handle_data(self, data):
        self._buf.append(data)

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t == "b":
            self._push("b")
        elif t == "i":
            self._push("i")
        elif t == "u":
            self._push("u")
        elif t == "span":
            style = dict(attrs).get("style", "")
            for kv in style.split(";"):
                kv = kv.strip()
                if kv.startswith("color:"):
                    self._push(f"color:{kv[6:].strip()}")
                elif kv.startswith("font-size:"):
                    self._push(f"size:{kv[10:].strip()}")
        elif t == "br":
            self._flush()
            self.segments.append(("\n", frozenset()))
        elif t == "p":
            pass

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in ("b", "i", "u", "span"):
            self._pop()

    def handle_entityref(self, name):
        import html.entities
        ch = html.entities.html5.get(name + ";", f"&{name};")
        self._buf.append(ch)

    def close(self):
        self._flush()
        super().close()


# ============ Text widget dump → HTML ============
def text_widget_to_html(text_widget) -> str:
    """从 tkinter Text/CTkTextbox 的 dump() 提取内容并序列化为 HTML。

    dump() 返回 [(kind, value, index), ...]，kind 为 'text'/'tagon'/'tagoff'/'mark'。
    约定的 tag 名：b, i, u, color_#RRGGBB, size_N
    """
    parts = []
    open_tags = []

    for kind, value, _index in text_widget.dump("1.0", "end-1c"):
        if kind == "text":
            parts.append(_escape(value))
        elif kind == "tagon":
            _open_html_tag(value, parts)
            open_tags.append(value)
        elif kind == "tagoff":
            if value in open_tags:
                while open_tags:
                    t = open_tags.pop()
                    parts.append(_close_html_tag(t))
                    if t == value:
                        break
    # 关闭所有未关闭标签
    for t in reversed(open_tags):
        parts.append(_close_html_tag(t))
    return "".join(parts)


def _open_html_tag(tag_name: str, parts: list):
    if tag_name in ("b", "i", "u"):
        parts.append(f"<{tag_name}>")
    elif tag_name.startswith("color_"):
        color = tag_name[6:]
        parts.append(f'<span style="color:{color}">')
    elif tag_name.startswith("size_"):
        n = tag_name[5:]
        parts.append(f'<span style="font-size:{n}">')


def _close_html_tag(tag_name: str) -> str:
    if tag_name in ("b", "i", "u"):
        return f"</{tag_name}>"
    if tag_name.startswith("color_") or tag_name.startswith("size_"):
        return "</span>"
    return ""


# ============ HTML 转义 ============
def _escape(text: str) -> str:
    return (text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _escape_attr(text: str) -> str:
    return (text.replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def unescape(s: str) -> str:
    """HTML 反转义"""
    import html
    return html.unescape(s)


# ============ 简单检测 ============
def is_html_content(s: str) -> bool:
    return _looks_like_html(s)
