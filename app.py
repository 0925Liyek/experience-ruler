# -*- coding: utf-8 -*-
"""经验尺 · MVP（Gradio 6 适配版）
运行：py app.py
配置：复制 .env.example 为 .env，填入两个 Key
"""

import json
import os
import re
import time

import gradio as gr
import requests
from dotenv import load_dotenv

from ui_cards import (
    html_error,
    html_loading,
    html_placeholder,
    html_report,
)
from prompt import SYSTEM_PROMPT, build_user_message

load_dotenv()

ZHIHU_SECRET = os.getenv("ZHIHU_ACCESS_SECRET", "")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")

ZHIHU_HOST = "https://developer.zhihu.com"
ZHIHU_SEARCH_PATH = "/api/v1/content/zhihu_search"

# ---- 大模型：任何 OpenAI 兼容接口都能用（默认 DeepSeek）----
LLM_BASE_URL = (os.getenv("LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL") or "deepseek-chat"
LLM_KEY = os.getenv("LLM_API_KEY") or DEEPSEEK_KEY
LLM_JSON_MODE = os.getenv("LLM_JSON_MODE", "1") == "1"
DEEPSEEK_URL = LLM_BASE_URL + "/chat/completions"

CONNECT_TIMEOUT = 5       # 连接超时（秒）
READ_TIMEOUT = 45         # 读取超时（秒）—— 现场卡死的第一元凶就是不设它
MAX_POST_CHARS = 8000     # 送进模型的正文上限
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"   # 1 = 跳过真实调用，走缓存/内置样例
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".demo_cache.json")


# ============================================================
# 0. 小工具
# ============================================================
def _first(d, keys, default=""):
    """防御式取字段：不确定 API 到底给哪个键名时用。"""
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return default


def _bar(score):
    score = max(0, min(100, int(score or 0)))
    filled = int(round(score / 10))
    return "█" * filled + "░" * (10 - filled)


def _parse_json(text):
    """模型偶尔会套 ```json 代码块或多写解释，这里容错。"""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(t[start:end + 1])
        except Exception:
            return None
    return None


def _cache_save(data):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _cache_load():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ============================================================
# 1. 抓知乎：先返回候选列表，再挑一条
# ============================================================
def _zhihu_headers():
    return {
        "Authorization": f"Bearer {ZHIHU_SECRET}",
        "X-Request-Timestamp": str(int(time.time())),
        "Content-Type": "application/json",
    }


def zhihu_candidates(query, count=5):
    """返回 [{title, text}, ...]，按正文长度降序。"""
    resp = requests.get(
        ZHIHU_HOST + ZHIHU_SEARCH_PATH,
        headers=_zhihu_headers(),
        params={"Query": f"{query} 经验", "Count": count},
        timeout=(CONNECT_TIMEOUT, 20),
    )
    if resp.status_code != 200:
        raise RuntimeError(f"知乎接口 HTTP {resp.status_code}：{resp.text[:150]}")

    payload = resp.json()
    data = payload.get("Data")
    if data is None:
        code = payload.get("Code")
        msg = payload.get("Message") or payload.get("Msg") or "接口未返回数据"
        if not ZHIHU_SECRET:
            raise RuntimeError(
                "没读到 ZHIHU_ACCESS_SECRET：项目根目录缺少 .env，或文件里没填值。"
                f"（接口原话：{msg}）"
            )
        raise RuntimeError(
            f"知乎接口拒绝访问：{msg}（Code={code}）。"
            "请确认密钥是否有效、是否已过期、额度是否用完。"
        )
    items = (data or {}).get("Items") or []
    if not items:
        raise RuntimeError("接口连上了，但这条关键词返回 0 条。换个更宽泛的词试试。")

    out = []
    for it in items:
        out.append({
            "title": _first(it, ("Title", "TitleText", "QuestionTitle", "Name")),
            "text": _first(it, ("ContentText", "Content", "Text", "Excerpt")),
        })
    out.sort(key=lambda x: len(x["text"]), reverse=True)
    return out


# ============================================================
# 2. 诊断：两段式 Prompt → JSON → 卡片
# ============================================================
def call_deepseek(system_prompt, user_message, retries=1):
    if not LLM_KEY:
        raise RuntimeError("没读到模型 Key（检查 .env 里的 DEEPSEEK_API_KEY 或 LLM_API_KEY）")

    data = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.2,
    }
    if LLM_JSON_MODE:
        data["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"}

    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(DEEPSEEK_URL, headers=headers, json=data,
                                 timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            if resp.status_code == 400 and "response_format" in data:
                # 部分供应商不支持 json_object，自动去掉再试一次
                data.pop("response_format", None)
                resp = requests.post(DEEPSEEK_URL, headers=headers, json=data,
                                     timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            if resp.status_code != 200:
                raise RuntimeError(f"模型接口 HTTP {resp.status_code}：{resp.text[:150]}")
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.5)
    raise last_err


MATCH_ICON = {"满足": "✅ 满足", "不满足": "❌ 不满足", "未知": "❓ 未知"}


def render_report(d, truncated=False, source=""):
    lines = []
    score = int(d.get("score") or 0)
    lines.append(f"### 匹配度 {score}/100　`{_bar(score)}`")
    if d.get("verdict"):
        lines.append(f"> **{d['verdict']}**")
    lines.append("")
    lines.append("#### 🔍 隐性前提清单（这条经验没写出来的部分）")

    premises = d.get("premises") or []
    if not premises:
        lines.append("_模型未返回前提条目_")
    for i, p in enumerate(premises, 1):
        icon = MATCH_ICON.get(p.get("match") or "未知", "❓ 未知")
        lines.append(f"**{i}. [{p.get('type', '其他')}] {p.get('claim', '')}**　{icon}")
        if p.get("evidence"):
            lines.append(f"- 原文依据：{p['evidence']}")
        if p.get("why"):
            lines.append(f"- 判断理由：{p['why']}")
        if p.get("if_miss"):
            lines.append(f"- 若不满足：{p['if_miss']}")
        lines.append("")

    q = d.get("quadrants") or {}
    for key, title in (
        ("reference", "✅ 可参考"),
        ("caution", "⚠️ 需警惕"),
        ("invalid", "❌ 不适用"),
        ("verify", "🔍 必须验证"),
    ):
        items = q.get(key) or []
        lines.append(f"#### {title}")
        lines.extend([f"- {x}" for x in items] or ["- （无）"])
        lines.append("")

    if d.get("must_verify"):
        lines.append("#### 🎯 你现在该去查的一件事")
        lines.append(d["must_verify"])

    foot = []
    if truncated:
        foot.append(f"⚠️ 原文超 {MAX_POST_CHARS} 字，只诊断了前 {MAX_POST_CHARS} 字")
    if source:
        foot.append(f"来源：{source}")
    if foot:
        lines.append("\n---\n" + "　·　".join(foot))
    return "\n".join(lines)


# ---------- 演示案例库（B 维护） ----------
CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "cases.json")


def load_cases():
    try:
        with open(CASES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


CASES = load_cases()


def pick_case(goal):
    """按目标挑演示案例；找不到就退回第一个。"""
    for _, v in CASES.items():
        if goal and (v.get("goal") == goal or v.get("label") == goal):
            return v
    return next(iter(CASES.values()), None)


# 内置兜底样例（B 可以把这里替换成 3 个固定演示案例）
FALLBACK_REPORT = {
    "score": 45,
    "verdict": "不能直接照搬，这篇的核心前提你不满足",
    "premises": [
        {"type": "时间", "claim": "作者是脱产全职备考，每天能投入 10 小时以上",
         "evidence": "原文未提及，由常识推断", "if_miss": "在职每天 3 小时会被进度表直接拖垮",
         "match": "不满足", "why": "你的约束写的是下班后 3 小时"},
    ],
    "quadrants": {
        "reference": ["分阶段刷题的顺序可以照用"],
        "caution": ["月度进度表依赖全职时间投入"],
        "invalid": ["三刷真题的节奏照搬会崩"],
        "verify": ["目标岗位近三年进面分数线"],
    },
    "must_verify": "这个岗位去年进面的人，在职备考的比例是多少？",
}


def diagnose(identity, goal, constraint, post_text, demo=False):
    """生成器：先出提示，再出结果；任何异常路径都必须有输出。"""
    post = (post_text or "").strip()
    if not post:
        yield html_error("还没有帖子正文。先点「① 获取帖子」，或直接把正文粘到下面的大框里。")
        return

    truncated = len(post) > MAX_POST_CHARS
    post_for_model = post[:MAX_POST_CHARS]

    yield html_loading()

    use_demo = bool(demo) or DEMO_MODE
    try:
        if use_demo:
            raise RuntimeError("演示模式：跳过真实调用")
        raw = call_deepseek(
            SYSTEM_PROMPT, build_user_message(identity, goal, constraint, post_for_model)
        )
        data = _parse_json(raw)
        if not data:
            raise ValueError("模型没有返回合法 JSON")
        _cache_save(data)
        yield html_report(data, source="模型实时诊断 · DeepSeek", truncated=truncated)
    except Exception as e:
        case = pick_case(goal) or {}
        label = case.get("label") or "内置示例"
        report = case.get("report") or FALLBACK_REPORT
        if use_demo:
            src = f"本地演示数据 · {label}"
        else:
            src = f"⚠️ 实时诊断失败（{e}），已回退到「{label}」"
        yield html_report(report, source=src, truncated=truncated, demo=True)
# ============================================================
# 3. 界面（Gradio 6：theme 走 launch，Textbox 复制按钮用 buttons=["copy"]）
# ============================================================
def free_select(choices, value, label):
    """可自由输入的下拉框。Gradio 6 没有 Combobox，用 Dropdown + allow_custom_value。"""
    return gr.Dropdown(choices=choices, value=value, label=label, allow_custom_value=True)


with gr.Blocks(title="经验尺") as demo:
    gr.Markdown(
        "# 📏 经验尺\n"
        "**不问「这条经验好不好」，只问「它成立的前提，你符不符合」。**\n\n"
        "① 填你的处境 → ② 取一条知乎经验帖 → ③ 拿到隐性前提清单与匹配诊断"
    )

    _missing = []
    if not ZHIHU_SECRET:
        _missing.append("**ZHIHU_ACCESS_SECRET**（知乎帖子抓取不可用）")
    if not LLM_KEY:
        _missing.append("**DEEPSEEK_API_KEY / LLM_API_KEY**（实时诊断不可用）")
    if _missing:
        gr.Markdown(
            "> ⚠️ **还缺密钥**：" + "　·　".join(_missing) + "\n"
            "> 在 `.env` 里补齐后重启即可。缺哪个只影响哪一项，不影响另一项。\n"
            "> 想先看完整效果：勾选下方「演示模式」。"
        )

    with gr.Row(equal_height=False):
        # ---------------- 左栏：输入 ----------------
        with gr.Column(scale=11, min_width=380):
            with gr.Row():
                identity = free_select(
                    ["大三", "大四", "毕业1-3年", "在职"], "在职", "你的身份（可直接输入）"
                )
                goal = free_select(
                    ["考公", "考研", "转行", "求职"], "考公", "你的目标（可直接输入）"
                )

            constraint = gr.Textbox(
                label="你的核心约束",
                lines=2,
                placeholder="例如：只能在职备考 / 本科双非 / 必须自己赚生活费",
                value="每天只能下班后学 3 小时，没有经济支持",
            )

            gr.Markdown("### ② 取一条经验帖")

            with gr.Row():
                mode = gr.Radio(
                    ["关键词搜索", "直接粘贴正文"],
                    value="关键词搜索",
                    label="获取方式",
                    scale=2,
                )
                source = gr.Textbox(
                    label="关键词",
                    placeholder="例如：在职考公 上岸经验",
                    scale=3,
                )

            fetch_btn = gr.Button("① 获取帖子", variant="secondary")

            post_info = gr.Markdown("_尚未获取帖子_")
            post_text = gr.Textbox(
                label="帖子正文（可手动编辑，诊断以这里为准）",
                lines=10,
                max_lines=18,
                buttons=["copy"],
            )
            candidates_md = gr.Markdown("")

        # ---------------- 右栏：诊断结果 ----------------
        with gr.Column(scale=14, min_width=460):
            gr.Markdown("### ③ 诊断结果")

            with gr.Row():
                demo_toggle = gr.Checkbox(
                    label="演示模式",
                    info="不联网，直接用本地案例",
                    value=DEMO_MODE,
                    scale=1,
                )
                load_case_btn = gr.Button(
                    "📂 载入演示案例", variant="secondary", scale=1
                )

            btn = gr.Button("🚀 诊断这条经验适不适合我", variant="primary", size="lg")
            output = gr.HTML(value=html_placeholder())

    # 切换获取方式时，联动输入框的显隐与提示
    def on_mode(m):
        if m == "直接粘贴正文":
            return (
                gr.update(visible=False),
                gr.update(visible=False),
                "### 直接粘贴\n把帖子正文粘到下面的大框，然后点「诊断」。",
            )
        return (
            gr.update(visible=True, label="关键词", placeholder="例如：在职考公 上岸经验"),
            gr.update(visible=True),
            "_填关键词后点「获取帖子」_",
        )

    mode.change(on_mode, inputs=mode, outputs=[source, fetch_btn, post_info])

    def on_fetch(m, src, current):
        src = (src or "").strip()
        if m == "直接粘贴正文":
            return "_已切到粘贴模式：直接把正文粘到下方大框_", current, ""
        if not src:
            return "### ⚠️ 先填关键词", current, ""

        try:
            cands = zhihu_candidates(src)
            best = cands[0]
            info = (
                f"### ✅ 已获取 {len(cands)} 条候选，自动选最长的一条\n"
                f"**标题**：{best['title'] or '（该条结果无标题字段）'}　·　"
                f"**字数**：{len(best['text'])}　·　**关键词**：{src}"
            )
            rows = "\n".join(
                f"| {i + 1} | {len(c['text'])} | {c['title'] or '（无标题）'} | "
                f"{(c['text'][:40] + '…') if c['text'] else '（空）'} |"
                for i, c in enumerate(cands)
            )
            table = "#### 候选列表（点选逻辑后续可加，目前自动取最长的）\n| # | 字数 | 标题 | 开头 |\n|---|---|---|---|\n" + rows
            return info, best["text"], table
        except Exception as e:
            return (f"### ❌ 获取失败\n{e}\n\n可以切到「直接粘贴正文」手动粘贴。",
                    current, "")

    fetch_btn.click(on_fetch, inputs=[mode, source, post_text],
                    outputs=[post_info, post_text, candidates_md])

    def on_load_case(goal):
        case = pick_case(goal)
        if not case:
            return (
                gr.update(),
                gr.update(),
                "",
                "### ⚠️ 没读到 fixtures/cases.json，检查文件是否存在",
            )
        label = case.get("label", "")
        return (
            gr.update(value=case.get("identity") or ""),
            gr.update(value=case.get("constraint") or ""),
            case.get("post", ""),
            f"### ✅ 已载入演示案例：{label}",
        )

    load_case_btn.click(
        on_load_case,
        inputs=[goal],
        outputs=[identity, constraint, post_text, post_info],
    )

    btn.click(diagnose, inputs=[identity, goal, constraint, post_text, demo_toggle], outputs=output)


if __name__ == "__main__":
    demo.queue()
    demo.launch(theme=gr.themes.Soft())