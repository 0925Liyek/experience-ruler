# -*- coding: utf-8 -*-
"""经验尺 · 展示层：把诊断 JSON 渲染成 HTML 卡片。

只负责"怎么显示"，不含任何业务判断。
维护：B
"""

from html import escape as _e

MATCH = {
    "满足": ("ok", "✅ 满足"),
    "不满足": ("bad", "❌ 不满足"),
    "未知": ("warn", "❓ 未知"),
}

QUADRANTS = [
    ("reference", "可参考", "ok", "✅"),
    ("caution", "需警惕", "warn", "⚠️"),
    ("invalid", "不适用", "bad", "❌"),
    ("verify", "必须验证", "info", "🔍"),
]

_CSS = """
<style>
/* 统一 .yj 作用域 + !important，避免被 Gradio 的 .prose 默认样式覆盖 */
.yj{background:#fff!important;border:1px solid #e8eaed;border-radius:16px;padding:20px 22px;
    font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
    color:#1a1a1a!important;line-height:1.65;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.yj *{box-sizing:border-box}
.yj .yj-head{display:flex;align-items:center;gap:20px;padding:18px 20px;border-radius:12px;
    background:linear-gradient(135deg,#12314f,#1f4e79)!important;margin-bottom:6px}
.yj .yj-score{display:flex;align-items:baseline;gap:4px;white-space:nowrap}
.yj .yj-num{font-size:46px;font-weight:800;line-height:1;color:#ffffff!important;
    text-shadow:0 1px 3px rgba(0,0,0,.35)}
.yj .yj-den{font-size:15px;color:rgba(255,255,255,.82)!important}
.yj .yj-right{flex:1;min-width:0}
.yj .yj-bar{height:10px;border-radius:6px;background:rgba(255,255,255,.22)!important;
    overflow:hidden;margin-bottom:10px}
.yj .yj-bar i{display:block;height:100%;border-radius:6px}
.yj .yj-verdict{font-size:15px;font-weight:600;line-height:1.5;color:#ffffff!important}
.yj .yj-pill{display:inline-block;font-size:12px;padding:2px 9px;border-radius:99px;
    margin-left:10px;background:rgba(255,255,255,.22)!important;color:#ffffff!important;
    font-weight:500;vertical-align:2px}
.yj .yj-h{font-size:14px;font-weight:700;color:#12314f!important;margin:22px 0 10px;
    padding-left:9px;border-left:4px solid #1f4e79!important}
.yj .yj-p{border:1px solid #e8eaed;border-left:4px solid #9aa4ae;border-radius:10px;
    padding:12px 14px;margin-bottom:10px;background:#fbfcfd!important}
.yj .yj-p.ok{border-left-color:#16a34a!important;background:#f6fdf8!important}
.yj .yj-p.bad{border-left-color:#dc2626!important;background:#fff7f7!important}
.yj .yj-p.warn{border-left-color:#d97706!important;background:#fffbf3!important}
.yj .yj-p-top{display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap}
.yj .yj-tag{font-size:12px;padding:1px 8px;border-radius:6px;background:#eef2f6!important;
    color:#3a4b5c!important;font-weight:600}
.yj .yj-match{font-size:12px;font-weight:700;padding:1px 8px;border-radius:6px}
.yj .yj-match.ok{background:#e7f7ed!important;color:#15803d!important}
.yj .yj-match.bad{background:#fdeaea!important;color:#b91c1c!important}
.yj .yj-match.warn{background:#fdf3e2!important;color:#b45309!important}
.yj .yj-claim{font-size:15px;font-weight:600;margin-bottom:8px;color:#1a1a1a!important}
.yj .yj-row{font-size:13px;color:#4a5560!important;margin:3px 0}
.yj .yj-row b{color:#2c3a47!important;font-weight:600;margin-right:6px}
.yj .yj-miss{color:#b91c1c!important}
.yj .yj-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.yj .yj-q{border:1px solid #e8eaed;border-radius:10px;padding:12px 14px;background:#fbfcfd!important}
.yj .yj-q.ok{border-top:3px solid #16a34a!important}
.yj .yj-q.warn{border-top:3px solid #d97706!important}
.yj .yj-q.bad{border-top:3px solid #dc2626!important}
.yj .yj-q.info{border-top:3px solid #2563eb!important}
.yj .yj-q h5{margin:0 0 8px;font-size:13.5px;font-weight:700;color:#1a1a1a!important}
.yj .yj-q ul{margin:0;padding-left:18px;font-size:13px;color:#3d4a56!important;list-style:disc!important}
.yj .yj-q li{margin:3px 0;color:#3d4a56!important;list-style:disc!important}
.yj .yj-verify{margin-top:18px;padding:14px 16px;border-radius:12px;
    background:linear-gradient(135deg,#fff8e6,#fffdf5)!important;border:1px solid #f3d9a4!important}
.yj .yj-verify .t{font-size:12.5px;font-weight:700;color:#92400e!important;margin-bottom:5px}
.yj .yj-verify .b{font-size:15px;font-weight:600;color:#78350f!important}
.yj .yj-foot{margin-top:14px;font-size:12px;color:#8a94a0!important;display:flex;gap:12px;flex-wrap:wrap}
@media (max-width:720px){
  .yj .yj-grid{grid-template-columns:1fr}
  .yj .yj-head{flex-direction:column;align-items:flex-start;gap:10px}
}
</style>
"""


def score_color(n):
    if n >= 70:
        return "#22c55e"
    if n >= 40:
        return "#f59e0b"
    return "#ef4444"


def html_report(d, source="", truncated=False, demo=False):
    """把一份诊断 JSON 渲染成完整 HTML 卡片。"""
    if not isinstance(d, dict):
        return html_error("诊断结果格式异常")

    try:
        score = int(d.get("score") or 0)
    except Exception:
        score = 0
    score = max(0, min(100, score))
    color = score_color(score)

    verdict = _e(str(d.get("verdict") or "（模型未给出结论）"))
    pill = '<span class="yj-pill">演示数据</span>' if demo else ""

    parts = [_CSS, '<div class="yj">']

    # ---- 顶部：分数 + 条形 + 一句话结论 ----
    parts.append(
        '<div class="yj-head">'
        f'<div class="yj-score"><span class="yj-num">{score}</span>'
        '<span class="yj-den">/100</span></div>'
        '<div class="yj-right">'
        f'<div class="yj-bar"><i style="width:{score}%;background:{color}"></i></div>'
        f'<div class="yj-verdict">{verdict}{pill}</div>'
        "</div></div>"
    )

    # ---- 隐性前提清单 ----
    premises = d.get("premises") or []
    parts.append('<div class="yj-h">🔍 隐性前提清单 · 这条经验没写出来的部分</div>')
    if not premises:
        parts.append('<div class="yj-row">（模型未返回前提条目）</div>')
    for i, p in enumerate(premises, 1):
        if not isinstance(p, dict):
            continue
        cls, label = MATCH.get(p.get("match") or "未知", MATCH["未知"])
        parts.append(f'<div class="yj-p {cls}">')
        parts.append(
            '<div class="yj-p-top">'
            f'<span class="yj-tag">{_e(str(p.get("type") or "其他"))}</span>'
            f'<span class="yj-match {cls}">{label}</span>'
            "</div>"
        )
        parts.append(f'<div class="yj-claim">{i}. {_e(str(p.get("claim") or ""))}</div>')
        if p.get("evidence"):
            parts.append(f'<div class="yj-row"><b>原文依据</b>{_e(str(p["evidence"]))}</div>')
        if p.get("why"):
            parts.append(f'<div class="yj-row"><b>判断理由</b>{_e(str(p["why"]))}</div>')
        if p.get("if_miss"):
            miss_cls = "yj-row yj-miss" if cls != "ok" else "yj-row"
            parts.append(f'<div class="{miss_cls}"><b>若不满足</b>{_e(str(p["if_miss"]))}</div>')
        parts.append("</div>")

    # ---- 四象限 ----
    q = d.get("quadrants") or {}
    parts.append('<div class="yj-h">📋 适用性四象限</div><div class="yj-grid">')
    for key, title, cls, icon in QUADRANTS:
        items = q.get(key) or []
        lis = "".join(f"<li>{_e(str(x))}</li>" for x in items) or "<li>（无）</li>"
        parts.append(
            f'<div class="yj-q {cls}"><h5>{icon} {title}</h5><ul>{lis}</ul></div>'
        )
    parts.append("</div>")

    # ---- 必须验证 ----
    if d.get("must_verify"):
        parts.append(
            '<div class="yj-verify">'
            '<div class="t">🎯 你现在就能去查的一件事</div>'
            f'<div class="b">{_e(str(d["must_verify"]))}</div>'
            "</div>"
        )

    # ---- 页脚 ----
    foot = []
    if truncated:
        foot.append("⚠️ 原文过长，仅诊断了前一部分")
    if source:
        foot.append(_e(str(source)))
    if foot:
        parts.append('<div class="yj-foot">' + "　·　".join(foot) + "</div>")
    if demo:
        parts.append('<div class="yj-foot">本结果为本地演示数据，用于保证现场演示稳定。</div>')

    parts.append("</div>")
    return "".join(parts)


def html_loading():
    return (
        '<div class="yj" style="text-align:center;padding:34px 20px">'
        '<div style="font-size:24px;margin-bottom:8px">⏳</div>'
        '<div style="font-size:15px;font-weight:600;color:#12314f">'
        "正在提取隐性前提，并逐条比对你的处境……</div>"
        '<div style="font-size:13px;color:#7a8794;margin-top:6px">'
        "通常 5–10 秒，请不要重复点击</div></div>"
    )


def html_error(msg):
    return (
        '<div class="yj" style="border-left:4px solid #dc2626;background:#fff7f7">'
        f'<div style="font-size:14px;color:#b91c1c;font-weight:600">⚠️ {_e(str(msg))}</div>'
        "</div>"
    )


def html_placeholder():
    """右侧还没出结果时的空态。"""
    return (
        '<div class="yj" style="text-align:center;padding:56px 24px;border-style:dashed">'
        '<div style="font-size:34px;margin-bottom:10px">📏</div>'
        '<div style="font-size:15px;font-weight:600;color:#12314f">'
        "左侧填好处境、取一条经验帖，然后点「诊断」</div>"
        '<div style="font-size:13px;color:#8a94a0;margin-top:8px">'
        "这里会出现：隐性前提清单 · 适用性四象限 · 你该去查证的那件事</div>"
        "</div>"
    )
