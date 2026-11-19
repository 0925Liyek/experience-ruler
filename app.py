import gradio as gr
import os
import time
import requests
from dotenv import load_dotenv

# 加载 .env 文件里的密钥
load_dotenv()
zhihu_secret = os.getenv("ZHIHU_ACCESS_SECRET")
deepseek_key = os.getenv("DEEPSEEK_API_KEY")

# 1. 抓知乎内容（方便演示时自动化）
def fetch_zhihu_post(query):
    url = "https://developer.zhihu.com/api/v1/content/zhihu_search"
    headers = {
        "Authorization": f"Bearer {zhihu_secret}",
        "X-Request-Timestamp": str(int(time.time())),
        "Content-Type": "application/json"
    }
    params = {"Query": query, "Count": 1}
    try:
        resp = requests.get(url, headers=headers, params=params)
        items = resp.json().get("Data", {}).get("Items", [])
        if items:
            return items[0].get('ContentText', '')
    except:
        pass
    return ""

# 2. 核心诊断逻辑
def diagnose(identity, constraint, goal, post_text):
    if not post_text.strip():
        return "⚠️ 请先粘贴一条知乎经验帖正文！"
        
    system_prompt = """你是一个“经验适用性诊断器”。请对比用户情况和经验帖，输出四个区块：
【✅ 可参考】：说明理由。
【⚠️ 需警惕】：说明在什么条件下会失效。
【❌ 不适用】：说明照搬会出什么问题。
【🔍 必须验证】：用户需要去查证的一个具体问题。
格式要求：使用 Markdown 输出，带清晰的段落。语气要客观、理性。"""
    
    user_message = f"用户身份：{identity}\n目标：{goal}\n约束：{constraint}\n\n帖子正文：\n{post_text}"
    
    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"}
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.2
    }
    
    try:
        resp = requests.post(url, headers=headers, json=data)
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"诊断失败，请检查网络或 Key：{e}"

# 3. Gradio 界面
with gr.Blocks(title="经验尺") as demo:
    gr.Markdown("## 📏 经验尺：这条经验，适合你的处境吗？")
    gr.Markdown("帮你判断一条知乎经验帖里未写明的“隐性条件”，是否匹配你当下的处境。")
    
    with gr.Row():
        identity = gr.Dropdown(["大三", "大四", "毕业1-3年", "在职"], label="当前身份", value="在职")
        goal = gr.Dropdown(["考公", "考研", "转行", "求职"], label="目标", value="考公")
        
    constraint = gr.Textbox(label="核心约束", placeholder="例如：只能在职备考 / 本科双非 / 必须自己赚生活费", value="每天只能下班后学3小时，没有经济支持")
    post_text = gr.Textbox(label="粘贴一条知乎经验帖正文（或点击下方按钮自动抓取）", lines=8)
    
    with gr.Row():
        fetch_btn = gr.Button("🔍 自动抓取一篇“在职考公上岸”的帖子")
        btn = gr.Button("🚀 诊断这条经验适不适合我", variant="primary")
        
    output = gr.Markdown(label="适用性诊断卡片")
    
    # 按钮绑定事件
    fetch_btn.click(fn=lambda: fetch_zhihu_post("考公在职上岸"), inputs=[], outputs=post_text)
    btn.click(diagnose, inputs=[identity, constraint, goal, post_text], outputs=output)

if __name__ == "__main__":
    demo.launch()