import os
import time
import requests
import json
from dotenv import load_dotenv

# 加载 .env 文件里的密码
load_dotenv()
zhihu_secret = os.getenv("ZHIHU_ACCESS_SECRET")
deepseek_key = os.getenv("DEEPSEEK_API_KEY")

# ================= 1. 知乎搜索模块 =================
def fetch_zhihu_post(query="考公在职上岸"):
    if not zhihu_secret:
        print("❌ 错误：没有找到 ZHIHU_ACCESS_SECRET")
        return None

    url = "https://developer.zhihu.com/api/v1/content/zhihu_search"
    headers = {
        "Authorization": f"Bearer {zhihu_secret}",
        "X-Request-Timestamp": str(int(time.time())),
        "Content-Type": "application/json"
    }
    params = {"Query": query, "Count": 1}

    print(f"正在知乎搜索：{query}...")
    resp = requests.get(url, headers=headers, params=params)
    
    if resp.status_code == 200:
        items = resp.json().get("Data", {}).get("Items", [])
        if items:
            return items[0].get('ContentText', '')
    return None

# ================= 2. DeepSeek 提取隐性条件模块 =================
def extract_conditions(text):
    if not deepseek_key:
        print("❌ 错误：没有找到 DEEPSEEK_API_KEY")
        return

    print("\n🤖 正在呼叫 DeepSeek 提取隐性条件...")
    
    system_prompt = """你是一个“经验适用性诊断器”的条件抽取模块。
用户会给你一条知乎经验帖的正文。
你的任务：只抽取这条经验“成立所需要的前提条件”，不要总结，不要评价好坏。

输出严格的 JSON，不要任何多余文字，格式如下：
{
  "conditions": [
    {
      "type": "经济支持|时间投入|学历门槛|地域限制|家庭支持|行业周期",
      "certainty": "明说|可推断|未提及",
      "evidence": "原文中对应的句子；如果未提及，填“未提及”",
      "condition_text": "用一句话描述这个条件"
    }
  ]
}
每条经验至少抽3条，最多8条。如果某类条件确实不存在，不要硬编。"""

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {deepseek_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        "temperature": 0.1
    }

    resp = requests.post(url, headers=headers, json=data)
    
    if resp.status_code == 200:
        result_text = resp.json()["choices"][0]["message"]["content"]
        
        # 去除大模型可能自带的 markdown 代码块符号
        result_text = result_text.replace("```json", "").replace("```", "").strip()
        
        print("\n✅ 提取成功！JSON结果如下：")
        try:
            # 格式化打印 JSON，方便查看
            parsed_json = json.loads(result_text)
            print(json.dumps(parsed_json, ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            print("❌ 模型返回的不是合法的 JSON：")
            print(result_text)
    else:
        print(f"❌ DeepSeek 请求失败：{resp.status_code}")
        print(resp.text)

# ================= 3. 主程序 =================
if __name__ == "__main__":
    # 第一步：抓取知乎内容
    post_content = fetch_zhihu_post()
    
    if post_content:
        print(f"✅ 成功抓取知乎正文，长度：{len(post_content)} 字")
        # 第二步：丢给大模型提取
        extract_conditions(post_content)
    else:
        print("❌ 抓取失败，无法提取。")