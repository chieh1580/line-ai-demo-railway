from flask import Flask, request, jsonify, render_template_string, make_response, redirect
import anthropic
import requests
import os
from datetime import datetime
import sys
import threading
import json

app = Flask(__name__)
app.logger.setLevel("INFO")
app.logger.addHandler(logging_handler := __import__('logging').StreamHandler(sys.stdout))
logging_handler.setLevel("INFO")

CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
LINE_TOKEN = os.environ.get("LINE_TOKEN")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ys2024")
BOSS_USER_ID = "Ubfb649a185011fd5ef24fe1c92f2fe4e"
ADMIN_URL = "https://line-ai-demo-railway-production.up.railway.app/admin"
DEMO_ADMIN_URL = "https://line-ai-demo-railway-production.up.railway.app/demo-admin"

# ===== 狀態管理 =====
paused_users = set()
user_profiles = {}
user_industry = {}        # userId -> "spa"/"nail"/"beauty"/"hair"
user_state = {}           # userId -> {"flow": "collecting_interest", "step": "shop_name", ...}
user_interest_data = {}   # userId -> {"shop_name": ..., "industry": ..., "daily_messages": ...}
user_message_count = {}   # userId -> int (追蹤互動次數，用於觸發見證卡片)
testimonial_sent = set()  # 已發送見證卡片的用戶
app_logs = []

TRIGGER_WORDS = ["找真人", "找人工", "找客服", "找老師", "真人", "人工"]

INTEREST_KEYWORDS = ["我有興趣", "我有興趣，想了解更多", "我也想導入", "想了解更多"]

# ===== 四大產業知識庫 =====
INDUSTRY_PROMPTS = {
    "spa": """【體驗角色：YS療癒美學SPA 的 AI 客服「YS小幫手」】
個性親切溫柔、說話像朋友，讓客人感覺被重視、被照顧。

【店家資訊】
店名：YS療癒美學 SPA
地址：桃園市桃園區國豐三街76號
營業時間：每天 10:00 - 22:00
LINE：@y.s1314
預約方式：LINE私訊人工確認 / 電話預約

【師資】淇淇老師（國際講師）、GINA老師、雪蓮老師、星辭老師，都是專業撥經師。

【套餐價格】體驗價僅限第一次
A小蠻腰 胸腹撥經 90mins 體驗價2,300
B紙片人 背腹撥經 130mins 體驗價2,800
C幼態V臉 臉部撥經 100mins 體驗價2,800
D極致放鬆 身體撥經 150mins 體驗價2,800
E完美女神 臉胸腹撥經 150mins 體驗價3,900
F背影殺手 背部撥經 90mins 體驗價1,800
G漫畫腿 腿部撥經 90mins 體驗價1,800
H身型調整 整復撥經全身 150mins 體驗價3,500
會員9折，儲值VIP 8折

【禁用詞】絕對不可說：治療、療效、醫療、診斷、治癒、改善疾病、消除、根治
改說：舒緩、放鬆、調理、養護、舒壓、讓身體更有活力""",

    "nail": """【體驗角色：Nana Nail Studio 的 AI 客服「Nana小幫手」】
個性活潑可愛、用字輕鬆有少女感。

【店家資訊】
店名：Nana Nail Studio
地址：台北市大安區忠孝東路四段120號3樓
營業時間：週一～六 11:00 - 21:00（週日公休）
LINE：@nana.nail
預約方式：LINE 私訊預約

【美甲師】Nana老師（日式美甲認證）、小涵老師、Mia老師

【價目表】
基礎手部保養 $500
單色凝膠（手） $800
單色凝膠（足） $1,000
基礎款式設計（手） $1,200
進階手繪設計（手） $1,500~2,500
卸甲+基礎保養 $400
美睫自然款 $800 / 濃密款 $1,200
首次體驗享 9 折

【注意事項】
- 請提前 10 分鐘到場
- 卸甲建議預約時一起處理
- 如需改時間請提前 24 小時通知""",

    "beauty": """【體驗角色：光澤美學 Beauty Clinic 的 AI 客服「小光」】
個性專業溫暖、語氣讓人安心信賴。

【店家資訊】
店名：光澤美學 Beauty Clinic
地址：台中市西屯區文心路三段218號
營業時間：每天 10:00 - 21:00
LINE：@glow.beauty
預約方式：LINE 私訊 / 電話預約

【美容師】Emily老師（國際CIDESCO認證）、小雯老師、Annie老師

【價目表】
基礎保濕護膚 60mins $1,200
深層清潔護理 75mins $1,500
抗老緊緻護膚 90mins $2,200
美白淡斑療程 90mins $2,500
痘痘肌調理 75mins $1,800
韓式皮膚管理 60mins $1,600
眼部抗皺護理 45mins $1,200
首次體驗享 85 折

【注意事項】
- 療程前請先卸妝（店內有提供）
- 敏感肌請提前告知，我們會調整產品
- 建議穿著寬鬆舒適的衣服""",

    "hair": """【體驗角色：MOOD Hair Salon 的 AI 客服「MOOD小幫手」】
個性時尚俐落、用字簡潔有個性。

【店家資訊】
店名：MOOD Hair Salon
地址：高雄市前鎮區中山二路260號
營業時間：週二～日 11:00 - 20:30（週一公休）
LINE：@mood.hair
預約方式：LINE 私訊預約

【設計師】Kevin（資深總監）、Amber、小傑、Yuki

【價目表】
女生洗剪 $600~800
男生洗剪 $450
燙髮（含洗剪） $2,500 起
染髮（含洗剪） $2,000 起
護髮 $800~2,000
頭皮養護 $1,200
燙+染套餐 $4,000 起
學生憑證享 9 折
首次指定 Kevin 總監享 85 折

【注意事項】
- 燙染建議預留 3 小時
- 如需特殊色請先私訊討論
- 可提供髮型照片參考"""
}

INDUSTRY_NAMES = {
    "spa": "SPA 按摩",
    "nail": "美甲美睫",
    "beauty": "美容護膚",
    "hair": "美髮沙龍"
}

INDUSTRY_SELECTION_MAP = {
    "我想體驗SPA按摩的AI客服": "spa",
    "我想體驗美甲美睫的AI客服": "nail",
    "我想體驗美容護膚的AI客服": "beauty",
    "我想體驗美髮沙龍的AI客服": "hair",
}

BASE_SYSTEM_PROMPT = """你是「LINE AI 客服」的產品展示機器人。你有兩種模式，根據對方問的問題自動切換：

═══════════════════════════
【模式一：體驗模式】
當對方在問店家相關問題（價格、預約、服務、營業時間等）→ 用下面的店家角色回覆
目的：讓對方體驗 AI 客服的真實回覆品質

{industry_prompt}

═══════════════════════════
【模式二：產品諮詢模式】
當對方問到以下類型問題 → 切換為「產品顧問」身份回覆：

■ 收費/方案相關：
產品名稱：LINE AI 智能客服
適用產業：SPA、美甲、美睫、美容、美髮、整復推拿等美業店家
方案內容：導入費用依客製化程度報價，包含 AI 客服建置 + 管理後台 + 教學 + 後續維護
上線時間：資料備齊後最快 1 天上線

■ 功能介紹：
1. 24小時 AI 自動回覆（價格、服務、預約全部自動回）
2. 關鍵字觸發真人轉接（客人說「找真人」立即通知老闆手機）
3. 專屬管理後台（一個頁面管所有對話，一鍵切 AI/人工）
4. 100% 客製化（你的品牌、你的服務、你的價格、你的語氣）

■ 常見疑慮：
Q: AI 會不會回答錯？
A: 我們根據您的資料建立專屬知識庫，AI 只回答裡面的內容，不會亂講。而且隨時一鍵切真人接手！

Q: 客人會不會覺得在跟機器人講話？
A: 您自己剛剛體驗的對話，是不是很自然？我們用最頂尖的 AI，對話品質非常接近真人。

Q: 我不太會用電腦怎麼辦？
A: 後台超簡單，手機就能操作。一個頁面看誰在聊天、要不要接手，一目了然。

Q: 跟請工讀生比呢？
A: AI 24小時不休息、不請假、不會亂回。一天不到一杯咖啡的錢，比請人便宜太多。

Q: 適合我的店嗎？/ 我是做XX的
A: 只要你的店有 LINE 官方帳號、客人會傳訊息問問題，就超適合！不管是 SPA、美甲、美容、美髮、整復、美睫，我們都能做。每家店的內容都是完全客製化的。

═══════════════════════════
【回答原則】
1. 語氣親切自然，像朋友聊天
2. 回答簡潔不要一次丟太多
3. 體驗模式時，每 2-3 次對話自然穿插一句產品價值，例如：
   「像這種問題，AI 都能秒回，老闆完全不用盯手機哦～」
   「這就是 AI 客服的威力，24小時都能這樣回覆客人 ✨」
4. 不確定的事情說「讓我幫您轉給專人確認」
5. 當對方表達興趣想購買時，引導他說「我有興趣」來啟動諮詢流程"""


def get_system_prompt(user_id):
    industry = user_industry.get(user_id, "spa")
    industry_prompt = INDUSTRY_PROMPTS.get(industry, INDUSTRY_PROMPTS["spa"])
    return BASE_SYSTEM_PROMPT.format(industry_prompt=industry_prompt)


# ===== LINE API 工具函式 =====
def get_line_profile(user_id):
    try:
        r = requests.get(
            f"https://api.line.me/v2/bot/profile/{user_id}",
            headers={"Authorization": f"Bearer {LINE_TOKEN}"},
            timeout=5
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {"displayName": "用戶" + user_id[-4:], "pictureUrl": ""}


def reply_messages(reply_token, messages):
    """回覆訊息（支援多則、Flex Message）"""
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"},
        json={"replyToken": reply_token, "messages": messages},
        timeout=10
    )


def reply_text(reply_token, text):
    reply_messages(reply_token, [{"type": "text", "text": text}])


def push_messages(user_id, messages):
    """主動推送訊息"""
    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"},
        json={"to": user_id, "messages": messages},
        timeout=10
    )
    log_msg = f"[PUSH] to={user_id[-6:]} status={r.status_code}"
    print(log_msg, flush=True)
    app_logs.append({"time": datetime.now().strftime("%m/%d %H:%M:%S"), "msg": log_msg})
    return r


def push_text(user_id, text):
    push_messages(user_id, [{"type": "text", "text": text}])


def push_flex(user_id, flex):
    push_messages(user_id, [flex])


# ===== Flex Message 建構 =====
def build_welcome_flex():
    return {
        "type": "flex",
        "altText": "歡迎體驗 LINE AI 智能客服！",
        "contents": {
            "type": "bubble",
            "size": "giga",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "做臉做到一半還要回 LINE？", "weight": "bold", "size": "lg", "color": "#c8401a"},
                    {"type": "text", "text": "讓 AI 幫你 24 小時自動接客 💬", "size": "md", "margin": "sm", "color": "#555555"}
                ],
                "paddingAll": "20px",
                "backgroundColor": "#FFF8F4"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "這是一台 AI 客服展示機 🤖\n選一個產業來體驗，感受 AI 如何自動回覆客人問題！", "wrap": True, "size": "sm", "color": "#666666"},
                    {"type": "separator", "margin": "lg"},
                    {"type": "text", "text": "👇 選擇產業開始體驗", "weight": "bold", "size": "md", "margin": "lg", "color": "#2d1f14"},
                    {
                        "type": "box", "layout": "horizontal", "spacing": "sm", "margin": "md",
                        "contents": [
                            {"type": "button", "action": {"type": "message", "label": "💆 SPA 按摩", "text": "我想體驗SPA按摩的AI客服"}, "style": "primary", "color": "#c8401a", "height": "sm"},
                            {"type": "button", "action": {"type": "message", "label": "💅 美甲美睫", "text": "我想體驗美甲美睫的AI客服"}, "style": "primary", "color": "#d4766a", "height": "sm"}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "spacing": "sm", "margin": "sm",
                        "contents": [
                            {"type": "button", "action": {"type": "message", "label": "✨ 美容護膚", "text": "我想體驗美容護膚的AI客服"}, "style": "primary", "color": "#8b6f5e", "height": "sm"},
                            {"type": "button", "action": {"type": "message", "label": "💇 美髮沙龍", "text": "我想體驗美髮沙龍的AI客服"}, "style": "primary", "color": "#5a7d6e", "height": "sm"}
                        ]
                    },
                    {"type": "separator", "margin": "lg"},
                    {"type": "text", "text": "💡 選好後試著問：「你們有什麼服務？」「多少錢？」", "wrap": True, "size": "xs", "color": "#999999", "margin": "lg"}
                ],
                "paddingAll": "20px"
            }
        }
    }


def build_industry_switched_flex(industry_key):
    name = INDUSTRY_NAMES.get(industry_key, "SPA 按摩")
    return {
        "type": "flex",
        "altText": f"已切換到{name}體驗模式",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": f"✅ 已切換到「{name}」模式", "weight": "bold", "size": "md", "color": "#2d1f14"},
                    {"type": "text", "text": f"現在我是{name}店的 AI 客服，你可以假裝自己是客人來問問題！", "wrap": True, "size": "sm", "color": "#666666", "margin": "md"},
                    {"type": "separator", "margin": "lg"},
                    {"type": "text", "text": "試試看這樣問：", "size": "sm", "color": "#999999", "margin": "lg"},
                    {
                        "type": "box", "layout": "vertical", "margin": "sm", "spacing": "sm",
                        "contents": [
                            {"type": "button", "action": {"type": "message", "label": "你們有什麼服務？", "text": "你們有什麼服務？"}, "style": "secondary", "height": "sm"},
                            {"type": "button", "action": {"type": "message", "label": "價格怎麼算？", "text": "價格怎麼算？"}, "style": "secondary", "height": "sm"},
                            {"type": "button", "action": {"type": "message", "label": "我想預約", "text": "我想預約"}, "style": "secondary", "height": "sm"}
                        ]
                    }
                ],
                "paddingAll": "20px"
            }
        }
    }


def build_testimonial_flex():
    return {
        "type": "flex",
        "altText": "🏆 看看其他店家怎麼說",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "🏆 店家導入心得", "weight": "bold", "size": "md", "color": "#2d1f14"}],
                "paddingAll": "16px", "backgroundColor": "#FFF8F4"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "「自從用了 AI 客服，晚上不用再盯手機，隔天醒來客人都已經預約好了！」", "wrap": True, "size": "sm", "color": "#555555", "style": "italic"},
                    {"type": "text", "text": "— SPA 店家老闆", "size": "xs", "color": "#999999", "margin": "md", "align": "end"},
                    {"type": "separator", "margin": "lg"},
                    {
                        "type": "box", "layout": "horizontal", "margin": "lg",
                        "contents": [
                            {"type": "box", "layout": "vertical", "flex": 1, "contents": [
                                {"type": "text", "text": "回覆率", "size": "xs", "color": "#999999", "align": "center"},
                                {"type": "text", "text": "98%", "size": "xl", "weight": "bold", "color": "#c8401a", "align": "center"}
                            ]},
                            {"type": "box", "layout": "vertical", "flex": 1, "contents": [
                                {"type": "text", "text": "平均回覆", "size": "xs", "color": "#999999", "align": "center"},
                                {"type": "text", "text": "3秒", "size": "xl", "weight": "bold", "color": "#3b6d11", "align": "center"}
                            ]},
                            {"type": "box", "layout": "vertical", "flex": 1, "contents": [
                                {"type": "text", "text": "老闆省下", "size": "xs", "color": "#999999", "align": "center"},
                                {"type": "text", "text": "3hr/天", "size": "xl", "weight": "bold", "color": "#1a6bc8", "align": "center"}
                            ]}
                        ]
                    },
                    {"type": "separator", "margin": "lg"},
                    {"type": "button", "action": {"type": "message", "label": "我也想導入 👋", "text": "我有興趣，想了解更多"}, "style": "primary", "color": "#c8401a", "margin": "lg", "height": "sm"},
                    {"type": "button", "action": {"type": "uri", "label": "👀 看看管理後台", "uri": DEMO_ADMIN_URL}, "style": "secondary", "margin": "sm", "height": "sm"}
                ],
                "paddingAll": "16px"
            }
        }
    }


def build_interest_start_flex():
    return {
        "type": "flex",
        "altText": "太好了！讓我了解您的店",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "太好了！🎉", "weight": "bold", "size": "lg", "color": "#c8401a"},
                    {"type": "text", "text": "讓我先了解一下您的店，方便專人為您服務：", "wrap": True, "size": "sm", "color": "#666666", "margin": "md"},
                    {"type": "separator", "margin": "lg"},
                    {"type": "text", "text": "① 請問您的店名是？", "weight": "bold", "size": "md", "margin": "lg", "color": "#2d1f14"},
                    {"type": "text", "text": "直接打字回覆就好囉 ✏️", "size": "xs", "color": "#999999", "margin": "sm"}
                ],
                "paddingAll": "20px"
            }
        }
    }


def build_notify_boss_flex(customer_name, shop_name, industry, daily_messages, time_str):
    return {
        "type": "flex",
        "altText": f"🔔 新的潛在客戶：{customer_name}",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "🔔 新的潛在客戶！", "weight": "bold", "size": "lg", "color": "#c8401a"}],
                "paddingAll": "16px", "backgroundColor": "#FFF8F4"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                        {"type": "text", "text": "LINE 名稱", "size": "sm", "color": "#999999", "flex": 3},
                        {"type": "text", "text": customer_name, "size": "sm", "weight": "bold", "flex": 5}
                    ]},
                    {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                        {"type": "text", "text": "店名", "size": "sm", "color": "#999999", "flex": 3},
                        {"type": "text", "text": shop_name or "未提供", "size": "sm", "weight": "bold", "flex": 5}
                    ]},
                    {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                        {"type": "text", "text": "產業", "size": "sm", "color": "#999999", "flex": 3},
                        {"type": "text", "text": industry or "未提供", "size": "sm", "weight": "bold", "flex": 5}
                    ]},
                    {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                        {"type": "text", "text": "每日訊息量", "size": "sm", "color": "#999999", "flex": 3},
                        {"type": "text", "text": daily_messages or "未提供", "size": "sm", "weight": "bold", "flex": 5}
                    ]},
                    {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                        {"type": "text", "text": "時間", "size": "sm", "color": "#999999", "flex": 3},
                        {"type": "text", "text": time_str, "size": "sm", "flex": 5}
                    ]},
                    {"type": "separator", "margin": "lg"},
                    {"type": "button", "action": {"type": "uri", "label": "👉 查看後台", "uri": ADMIN_URL}, "style": "primary", "color": "#c8401a", "margin": "lg", "height": "sm"}
                ],
                "paddingAll": "16px"
            }
        }
    }


# ===== 延遲推播跟進 =====
def schedule_followups(user_id):
    """加好友後排程 24hr / 48hr / 7天 自動跟進"""
    followup_configs = [
        (86400, "24hr"),      # 24 小時
        (172800, "48hr"),     # 48 小時
        (604800, "7day"),     # 7 天
    ]
    for delay, msg_type in followup_configs:
        timer = threading.Timer(delay, send_followup, args=[user_id, msg_type])
        timer.daemon = True
        timer.start()


def send_followup(user_id, msg_type):
    # 如果已經表達興趣，不再跟進
    if user_id in user_interest_data:
        return

    messages = {
        "24hr": {
            "type": "flex", "altText": "還沒體驗嗎？試試看！",
            "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": [
                {"type": "text", "text": "嗨～還沒來得及體驗嗎？👋", "weight": "bold", "size": "md", "color": "#2d1f14"},
                {"type": "text", "text": "試著打「你們有什麼服務？」看看 AI 怎麼回覆，3 秒就有答案！", "wrap": True, "size": "sm", "color": "#666666", "margin": "md"},
                {"type": "button", "action": {"type": "message", "label": "開始體驗 💬", "text": "你們有什麼服務？"}, "style": "primary", "color": "#c8401a", "margin": "lg", "height": "sm"}
            ]}}
        },
        "48hr": {
            "type": "flex", "altText": "很多老闆最好奇的問題",
            "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": [
                {"type": "text", "text": "很多老闆最好奇的是… 🤔", "weight": "bold", "size": "md", "color": "#2d1f14"},
                {"type": "text", "text": "「AI 會不會回答錯？」\n「客人分得出來嗎？」", "wrap": True, "size": "sm", "color": "#666666", "margin": "md"},
                {"type": "text", "text": "答案是：不會！AI 只回答你提供的內容，而且對話超自然 ✨", "wrap": True, "size": "sm", "color": "#555555", "margin": "md"},
                {"type": "button", "action": {"type": "message", "label": "我想了解更多", "text": "我有興趣，想了解更多"}, "style": "primary", "color": "#c8401a", "margin": "lg", "height": "sm"}
            ]}}
        },
        "7day": {
            "type": "flex", "altText": "早鳥優惠提醒",
            "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": [
                {"type": "text", "text": "🎁 本月早鳥優惠", "weight": "bold", "size": "md", "color": "#c8401a"},
                {"type": "text", "text": "本月導入享早鳥優惠！\n越早開始，越早讓 AI 幫你 24 小時接客 💪", "wrap": True, "size": "sm", "color": "#666666", "margin": "md"},
                {"type": "button", "action": {"type": "message", "label": "了解優惠方案", "text": "我有興趣，想了解更多"}, "style": "primary", "color": "#c8401a", "margin": "lg", "height": "sm"}
            ]}}
        }
    }

    msg = messages.get(msg_type)
    if msg:
        push_flex(user_id, msg)
        log_msg = f"[FOLLOWUP] {msg_type} sent to {user_id[-6:]}"
        print(log_msg, flush=True)
        app_logs.append({"time": datetime.now().strftime("%m/%d %H:%M:%S"), "msg": log_msg})


# ===== 通知老闆 =====
def notify_boss(customer_name, message, time_str):
    """舊版純文字通知（用於找真人轉接）"""
    text = (
        f"🔔 有客人需要您回覆！\n"
        f"客人：{customer_name}\n"
        f"訊息：{message}\n"
        f"時間：{time_str}\n"
        f"👉 後台：{ADMIN_URL}"
    )
    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"},
        json={"to": BOSS_USER_ID, "messages": [{"type": "text", "text": text}]},
        timeout=10
    )
    log_msg = f"[NOTIFY_BOSS] status={r.status_code}"
    print(log_msg, flush=True)
    app_logs.append({"time": datetime.now().strftime("%m/%d %H:%M:%S"), "msg": log_msg})


def notify_boss_interest(customer_name, shop_name, industry, daily_messages):
    """新版 Flex 通知（潛在客戶表達興趣）"""
    time_str = datetime.now().strftime("%m/%d %H:%M")
    flex = build_notify_boss_flex(customer_name, shop_name, industry, daily_messages, time_str)
    push_flex(BOSS_USER_ID, flex)


# ===== Claude AI =====
def ask_claude(user_id, user_message):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=get_system_prompt(user_id),
        messages=[{"role": "user", "content": user_message}]
    )
    return msg.content[0].text


# ===== Webhook 主邏輯 =====
@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    if not body or "events" not in body:
        return jsonify({"status": "ok"})

    for event in body["events"]:
        event_type = event.get("type")

        # ===== Follow Event：加好友歡迎訊息 =====
        if event_type == "follow":
            user_id = event["source"]["userId"]
            reply_token = event["replyToken"]
            log_msg = f"[FOLLOW] new follower: {user_id[-6:]}"
            print(log_msg, flush=True)
            app_logs.append({"time": datetime.now().strftime("%m/%d %H:%M:%S"), "msg": log_msg})

            # 取得用戶資料
            profile = get_line_profile(user_id)
            user_profiles[user_id] = {
                "name": profile.get("displayName", "用戶"),
                "picture": profile.get("pictureUrl", ""),
                "lastMessage": "（剛加好友）",
                "lastTime": datetime.now().strftime("%m/%d %H:%M")
            }

            # 發送歡迎訊息
            reply_messages(reply_token, [build_welcome_flex()])

            # 排程延遲跟進推播
            schedule_followups(user_id)
            continue

        # ===== Message Event =====
        if event_type != "message":
            continue
        if event["message"].get("type") != "text":
            continue

        user_id = event["source"]["userId"]
        reply_token = event["replyToken"]
        user_message = event["message"]["text"].strip()
        log_msg = f"[MSG] {user_id[-6:]}: {user_message[:50]}"
        print(log_msg, flush=True)
        app_logs.append({"time": datetime.now().strftime("%m/%d %H:%M:%S"), "msg": log_msg})

        # 更新用戶資料
        if user_id not in user_profiles:
            profile = get_line_profile(user_id)
            user_profiles[user_id] = {
                "name": profile.get("displayName", "用戶"),
                "picture": profile.get("pictureUrl", ""),
                "lastMessage": user_message,
                "lastTime": datetime.now().strftime("%m/%d %H:%M")
            }
        else:
            user_profiles[user_id]["lastMessage"] = user_message
            user_profiles[user_id]["lastTime"] = datetime.now().strftime("%m/%d %H:%M")

        # ----- 1. 檢查：是否在資料收集流程中 -----
        if user_id in user_state and user_state[user_id].get("flow") == "collecting_interest":
            step = user_state[user_id].get("step")

            if step == "shop_name":
                user_interest_data.setdefault(user_id, {})
                user_interest_data[user_id]["shop_name"] = user_message
                user_state[user_id]["step"] = "industry"
                reply_messages(reply_token, [
                    {"type": "flex", "altText": "請選擇產業",
                     "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": [
                         {"type": "text", "text": f"收到！「{user_message}」👍", "weight": "bold", "size": "md", "color": "#2d1f14"},
                         {"type": "text", "text": "② 請問是哪個產業呢？", "weight": "bold", "size": "md", "margin": "lg", "color": "#2d1f14"},
                         {"type": "box", "layout": "vertical", "margin": "md", "spacing": "sm", "contents": [
                             {"type": "button", "action": {"type": "message", "label": "SPA / 按摩 / 整復", "text": "SPA按摩"}, "style": "secondary", "height": "sm"},
                             {"type": "button", "action": {"type": "message", "label": "美甲 / 美睫", "text": "美甲美睫"}, "style": "secondary", "height": "sm"},
                             {"type": "button", "action": {"type": "message", "label": "美容 / 護膚", "text": "美容護膚"}, "style": "secondary", "height": "sm"},
                             {"type": "button", "action": {"type": "message", "label": "美髮沙龍", "text": "美髮沙龍"}, "style": "secondary", "height": "sm"},
                             {"type": "button", "action": {"type": "message", "label": "其他", "text": "其他美業"}, "style": "secondary", "height": "sm"}
                         ]}
                     ]}}}
                ])
                continue

            elif step == "industry":
                user_interest_data.setdefault(user_id, {})
                user_interest_data[user_id]["industry"] = user_message
                user_state[user_id]["step"] = "daily_messages"
                reply_text(reply_token, "③ 最後一題！你的 LINE 官方帳號一天大概會收到幾則客人訊息呢？\n\n（大概的數字就好，例如：10則、30則、不確定）")
                continue

            elif step == "daily_messages":
                user_interest_data.setdefault(user_id, {})
                user_interest_data[user_id]["daily_messages"] = user_message
                # 收集完成！
                del user_state[user_id]
                customer_name = user_profiles.get(user_id, {}).get("name", "用戶")
                data = user_interest_data[user_id]

                # 通知老闆
                notify_boss_interest(
                    customer_name,
                    data.get("shop_name", ""),
                    data.get("industry", ""),
                    data.get("daily_messages", "")
                )

                reply_messages(reply_token, [
                    {"type": "flex", "altText": "資料收到囉！",
                     "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": [
                         {"type": "text", "text": "資料收到囉！✅", "weight": "bold", "size": "lg", "color": "#3b6d11"},
                         {"type": "separator", "margin": "lg"},
                         {"type": "box", "layout": "horizontal", "margin": "lg", "contents": [
                             {"type": "text", "text": "店名", "size": "sm", "color": "#999999", "flex": 2},
                             {"type": "text", "text": data.get("shop_name", ""), "size": "sm", "weight": "bold", "flex": 4}
                         ]},
                         {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                             {"type": "text", "text": "產業", "size": "sm", "color": "#999999", "flex": 2},
                             {"type": "text", "text": data.get("industry", ""), "size": "sm", "weight": "bold", "flex": 4}
                         ]},
                         {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                             {"type": "text", "text": "訊息量", "size": "sm", "color": "#999999", "flex": 2},
                             {"type": "text", "text": data.get("daily_messages", ""), "size": "sm", "weight": "bold", "flex": 4}
                         ]},
                         {"type": "separator", "margin": "lg"},
                         {"type": "text", "text": "我們的專人會盡快透過 LINE 跟您聯繫，請留意訊息通知 📱", "wrap": True, "size": "sm", "color": "#666666", "margin": "lg"}
                     ]}}}
                ])
                continue

        # ----- 2. 檢查：體驗 AI 客服（Rich Menu 入口）-----
        if user_message == "我想體驗AI客服":
            reply_messages(reply_token, [build_welcome_flex()])
            continue

        # ----- 2b. 檢查：「哪些店家適合用」 -----
        if user_message == "哪些店家適合用":
            reply_messages(reply_token, [{
                "type": "flex", "altText": "適合哪些店家？",
                "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": [
                    {"type": "text", "text": "哪些店家適合用 AI 客服？", "weight": "bold", "size": "lg", "color": "#2d1f14"},
                    {"type": "text", "text": "只要你的店有 LINE 官方帳號，客人會傳訊息問問題，就超適合！", "wrap": True, "size": "sm", "color": "#666666", "margin": "md"},
                    {"type": "separator", "margin": "lg"},
                    {"type": "text", "text": "目前適用產業", "weight": "bold", "size": "sm", "margin": "lg", "color": "#2d1f14"},
                    {"type": "box", "layout": "vertical", "margin": "md", "spacing": "sm", "contents": [
                        {"type": "text", "text": "💆 SPA / 按摩 / 整復推拿", "size": "sm", "color": "#555555"},
                        {"type": "text", "text": "💅 美甲 / 美睫", "size": "sm", "color": "#555555"},
                        {"type": "text", "text": "✨ 美容 / 護膚 / 皮膚管理", "size": "sm", "color": "#555555"},
                        {"type": "text", "text": "💇 美髮沙龍", "size": "sm", "color": "#555555"},
                        {"type": "text", "text": "🏥 醫美 / 牙科 / 診所", "size": "sm", "color": "#555555"},
                        {"type": "text", "text": "🧘 瑜珈 / 健身工作室", "size": "sm", "color": "#555555"},
                    ]},
                    {"type": "separator", "margin": "lg"},
                    {"type": "text", "text": "AI 能幫你自動回覆：服務項目、價格查詢、預約引導、營業時間、常見問題…", "wrap": True, "size": "xs", "color": "#999999", "margin": "lg"},
                    {"type": "button", "action": {"type": "message", "label": "我想體驗看看", "text": "我想體驗SPA按摩的AI客服"}, "style": "primary", "color": "#c8401a", "margin": "lg", "height": "sm"},
                    {"type": "button", "action": {"type": "message", "label": "我有興趣導入", "text": "我有興趣，想了解更多"}, "style": "secondary", "margin": "sm", "height": "sm"}
                ]}}
            }])
            continue

        # ----- 2c. 檢查：「怎麼收費」 -----
        if user_message == "怎麼收費":
            reply_messages(reply_token, [{
                "type": "flex", "altText": "方案與價格",
                "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "paddingAll": "20px", "contents": [
                    {"type": "text", "text": "方案與價格", "weight": "bold", "size": "lg", "color": "#2d1f14"},
                    {"type": "separator", "margin": "lg"},
                    {"type": "text", "text": "LINE AI 智能客服方案", "weight": "bold", "size": "md", "margin": "lg", "color": "#c8401a"},
                    {"type": "box", "layout": "vertical", "margin": "md", "spacing": "md", "contents": [
                        {"type": "text", "text": "✅ AI 客服建置（100% 客製化）", "size": "sm", "color": "#555555"},
                        {"type": "text", "text": "✅ 專屬管理後台（手機可用）", "size": "sm", "color": "#555555"},
                        {"type": "text", "text": "✅ 真人轉接通知系統", "size": "sm", "color": "#555555"},
                        {"type": "text", "text": "✅ 教學 + 後續維護", "size": "sm", "color": "#555555"},
                        {"type": "text", "text": "✅ 資料備齊最快 1 天上線", "size": "sm", "color": "#555555"},
                    ]},
                    {"type": "separator", "margin": "lg"},
                    {"type": "text", "text": "費用依客製化程度而定，歡迎聊聊了解最適合你的方案！", "wrap": True, "size": "sm", "color": "#666666", "margin": "lg"},
                    {"type": "button", "action": {"type": "message", "label": "我想了解，請專人聯繫", "text": "我有興趣，想了解更多"}, "style": "primary", "color": "#c8401a", "margin": "lg", "height": "sm"}
                ]}}
            }])
            continue

        # ----- 3. 檢查：產業切換 -----
        if user_message in INDUSTRY_SELECTION_MAP:
            industry_key = INDUSTRY_SELECTION_MAP[user_message]
            user_industry[user_id] = industry_key
            user_message_count[user_id] = 0  # 重置互動計數
            reply_messages(reply_token, [build_industry_switched_flex(industry_key)])
            continue

        # ----- 3. 檢查：表達興趣 -----
        if any(kw in user_message for kw in INTEREST_KEYWORDS):
            user_state[user_id] = {"flow": "collecting_interest", "step": "shop_name"}
            user_interest_data[user_id] = {}
            reply_messages(reply_token, [build_interest_start_flex()])
            continue

        # ----- 4. 檢查：找真人（暫停 AI） -----
        if user_id in paused_users:
            continue

        if any(word in user_message for word in TRIGGER_WORDS):
            paused_users.add(user_id)
            reply_text(reply_token, "好的！我馬上幫您通知專人，請稍候片刻，我們會盡快與您聯繫 🙏")
            customer_name = user_profiles[user_id]["name"]
            time_str = user_profiles[user_id]["lastTime"]
            notify_boss(customer_name, user_message, time_str)
            continue

        # ----- 5. 檢查：看後台 -----
        if "看後台" in user_message or "後台" in user_message and "看" in user_message:
            reply_messages(reply_token, [
                {"type": "text", "text": f"這是我們的管理後台 Demo，老闆用手機就能輕鬆管理所有對話 👇\n\n👉 {DEMO_ADMIN_URL}"}
            ])
            continue

        # ----- 6. AI 回覆 -----
        try:
            ai_response = ask_claude(user_id, user_message)
            reply_text(reply_token, ai_response)

            # 追蹤互動次數，第 3 次後推送見證卡片
            user_message_count[user_id] = user_message_count.get(user_id, 0) + 1
            if user_message_count[user_id] == 3 and user_id not in testimonial_sent:
                testimonial_sent.add(user_id)
                # 延遲 3 秒推送，避免跟 AI 回覆擠在一起
                timer = threading.Timer(3.0, push_flex, args=[user_id, build_testimonial_flex()])
                timer.daemon = True
                timer.start()

        except Exception as e:
            log_msg = f"[ERROR] Claude API: {str(e)}"
            print(log_msg, flush=True)
            app_logs.append({"time": datetime.now().strftime("%m/%d %H:%M:%S"), "msg": log_msg})
            reply_text(reply_token, "抱歉，系統暫時忙碌中，請稍後再試 🙏")

    return jsonify({"status": "ok"})


# ===== 後台管理（原版，需密碼） =====
ADMIN_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ brand_name }} 後台</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#f7f5f2;color:#2d1f14}
.topbar{background:#f0ebe3;border-bottom:0.5px solid #e0d8ce;padding:16px 22px;display:flex;align-items:center;justify-content:space-between}
.topbar-brand{display:flex;align-items:center;gap:12px}
.topbar-logo{width:32px;height:32px;background:#c8401a;border-radius:7px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff}
.topbar-name{font-size:15px;font-weight:600;color:#2d1f14}
.topbar-sub{font-size:11px;color:#b0a090;margin-top:2px}
.online{display:flex;align-items:center;gap:6px}
.pulse{width:7px;height:7px;border-radius:50%;background:#6abf69}
.online span{font-size:12px;color:#b0a090}
.stats{display:flex;gap:10px;padding:18px 20px 8px}
.stat{background:#fff;border-radius:10px;padding:14px 16px;flex:1;border:0.5px solid #e8e2d8}
.stat-n{font-size:26px;font-weight:600;color:#2d1f14}
.stat-n.orange{color:#c8401a}
.stat-n.green{color:#3b6d11}
.stat-l{font-size:11px;color:#b0a090;margin-top:2px}
.notify{margin:8px 20px 4px;background:#fff8f4;border:0.5px solid #f0c8b0;border-radius:8px;padding:11px 14px;display:flex;align-items:center;gap:10px}
.notify-dot{width:7px;height:7px;border-radius:50%;background:#c8401a;flex-shrink:0}
.notify-txt{font-size:12px;color:#8b3a1a}
.main{padding:14px 20px 24px}
.sec-label{font-size:11px;font-weight:600;color:#c8b8a8;letter-spacing:2px;margin-bottom:10px;margin-top:4px}
.card{background:#fff;border-radius:10px;padding:13px 15px;margin-bottom:8px;border:0.5px solid #e8e2d8;display:flex;align-items:center;gap:12px}
.card.paused{border-left:3px solid #c8401a;border-radius:0 10px 10px 0;background:#fffaf7}
.card.active{border-left:3px solid #6abf69;border-radius:0 10px 10px 0}
.ava{width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:600;flex-shrink:0;background:#f0ebe3;color:#8b3a1a;overflow:hidden}
.ava img{width:100%;height:100%;object-fit:cover}
.uinfo{flex:1;min-width:0}
.uname{font-size:13px;font-weight:600;color:#2d1f14}
.umsg{font-size:12px;color:#b0a090;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px}
.utime{font-size:11px;color:#ccc;margin-top:2px}
.badge{font-size:11px;padding:3px 9px;border-radius:10px;font-weight:500;flex-shrink:0}
.badge-ai{background:#d4e8d0;color:#27500a}
.badge-human{background:#f5d5c8;color:#712b13}
.btn{border:0.5px solid;border-radius:6px;padding:6px 12px;font-size:12px;font-weight:500;cursor:pointer;flex-shrink:0;transition:0.15s}
.btn-stop{background:#fff0ec;color:#712b13;border-color:#e8c0b0}
.btn-stop:hover{background:#f5d5c8}
.btn-go{background:#d4e8d0;color:#27500a;border-color:#b0d0a8}
.btn-go:hover{background:#c0ddb8}
.divider{height:0.5px;background:#e8e2d8;margin:14px 0}
.empty{text-align:center;padding:40px;color:#c8b8a8;font-size:14px}
.login-wrap{display:flex;align-items:center;justify-content:center;min-height:100vh;background:#f7f5f2}
.login-box{background:#fff;border-radius:12px;padding:32px;width:300px;border:0.5px solid #e8e2d8;text-align:center}
.login-logo{width:48px;height:48px;background:#c8401a;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:700;color:#fff;margin:0 auto 16px}
.login-box h2{font-size:16px;font-weight:600;margin-bottom:20px;color:#2d1f14}
.login-box input{width:100%;padding:10px 14px;border:0.5px solid #e0d8ce;border-radius:6px;font-size:14px;margin-bottom:12px;text-align:center;background:#f7f5f2}
.login-box button{width:100%;padding:10px;background:#c8401a;color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer}
.err{color:#c8401a;font-size:12px;margin-top:8px}
.toast{position:fixed;bottom:20px;right:20px;background:#2d1f14;color:#f5ede0;padding:10px 18px;border-radius:6px;font-size:13px;display:none;z-index:999}
</style>
</head>
<body>
{% if not authenticated %}
<div class="login-wrap">
  <div class="login-box">
    <div class="login-logo">AI</div>
    <h2>後台管理登入</h2>
    <form method="POST" action="/admin/login">
      <input type="password" name="password" placeholder="請輸入密碼" required>
      <button type="submit">登入</button>
    </form>
    {% if error %}<p class="err">密碼錯誤，請再試一次</p>{% endif %}
  </div>
</div>
{% else %}
<div class="topbar">
  <div class="topbar-brand">
    <div class="topbar-logo">AI</div>
    <div>
      <div class="topbar-name">{{ brand_name }} 後台</div>
      <div class="topbar-sub">LINE AI 客服管理系統</div>
    </div>
  </div>
  <div class="online"><div class="pulse"></div><span>系統運作中</span></div>
</div>
<div class="stats">
  <div class="stat"><div class="stat-n">{{ total }}</div><div class="stat-l">今日對話</div></div>
  <div class="stat"><div class="stat-n green">{{ active }}</div><div class="stat-l">AI 回覆中</div></div>
  <div class="stat"><div class="stat-n orange">{{ paused_count }}</div><div class="stat-l">待人工處理</div></div>
  <div class="stat"><div class="stat-n">{{ ai_rate }}<span style="font-size:13px;color:#bbb;">%</span></div><div class="stat-l">AI 回覆率</div></div>
</div>
{% if pending_users %}
<div class="notify"><div class="notify-dot"></div><div class="notify-txt">{{ pending_users[0].name }} 需要您回覆，共 {{ paused_count }} 位客人等待中</div></div>
{% endif %}
<div class="main">
  {% if paused_users_list %}
  <div class="sec-label">待處理</div>
  {% for u in paused_users_list %}
  <div class="card paused">
    <div class="ava">{% if u.picture %}<img src="{{ u.picture }}" onerror="this.style.display='none'">{% else %}{{ u.name[0] }}{% endif %}</div>
    <div class="uinfo"><div class="uname">{{ u.name }}</div><div class="umsg">{{ u.lastMessage }}</div><div class="utime">{{ u.lastTime }}</div></div>
    <span class="badge badge-human">人工中</span>
    <button class="btn btn-go" onclick="toggle('{{ u.id }}','resume')">恢復 AI</button>
  </div>
  {% endfor %}
  <div class="divider"></div>
  {% endif %}
  {% if active_users %}
  <div class="sec-label">AI 回覆中</div>
  {% for u in active_users %}
  <div class="card active">
    <div class="ava">{% if u.picture %}<img src="{{ u.picture }}" onerror="this.style.display='none'">{% else %}{{ u.name[0] }}{% endif %}</div>
    <div class="uinfo"><div class="uname">{{ u.name }}</div><div class="umsg">{{ u.lastMessage }}</div><div class="utime">{{ u.lastTime }}</div></div>
    <span class="badge badge-ai">AI 中</span>
    <button class="btn btn-stop" onclick="toggle('{{ u.id }}','pause')">暫停 AI</button>
  </div>
  {% endfor %}
  {% endif %}
  {% if not paused_users_list and not active_users %}
  <div class="empty">還沒有客人傳訊息進來</div>
  {% endif %}
</div>
<div class="toast" id="toast"></div>
<script>
function toggle(uid, action) {
  fetch('/admin/toggle', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({userId:uid,action:action})})
  .then(r=>r.json()).then(()=>{
    const t=document.getElementById('toast');t.textContent=action==='pause'?'已暫停 AI，換您回覆':'已恢復 AI 自動回覆';
    t.style.display='block';setTimeout(()=>{t.style.display='none';location.reload()},1000)
  })
}
setTimeout(()=>location.reload(),30000)
</script>
{% endif %}
</body></html>"""


# ===== Demo 後台（唯讀，假資料，不需密碼） =====
DEMO_ADMIN_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 客服後台 Demo</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#f7f5f2;color:#2d1f14}
.topbar{background:#f0ebe3;border-bottom:0.5px solid #e0d8ce;padding:16px 22px;display:flex;align-items:center;justify-content:space-between}
.topbar-brand{display:flex;align-items:center;gap:12px}
.topbar-logo{width:32px;height:32px;background:#c8401a;border-radius:7px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff}
.topbar-name{font-size:15px;font-weight:600;color:#2d1f14}
.topbar-sub{font-size:11px;color:#b0a090;margin-top:2px}
.online{display:flex;align-items:center;gap:6px}
.pulse{width:7px;height:7px;border-radius:50%;background:#6abf69;animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}
.online span{font-size:12px;color:#b0a090}
.demo-badge{background:#c8401a;color:#fff;font-size:10px;padding:2px 8px;border-radius:10px;font-weight:600;margin-left:8px}
.stats{display:flex;gap:10px;padding:18px 20px 8px}
.stat{background:#fff;border-radius:10px;padding:14px 16px;flex:1;border:0.5px solid #e8e2d8}
.stat-n{font-size:26px;font-weight:600;color:#2d1f14}
.stat-n.orange{color:#c8401a}
.stat-n.green{color:#3b6d11}
.stat-l{font-size:11px;color:#b0a090;margin-top:2px}
.notify{margin:8px 20px 4px;background:#fff8f4;border:0.5px solid #f0c8b0;border-radius:8px;padding:11px 14px;display:flex;align-items:center;gap:10px}
.notify-dot{width:7px;height:7px;border-radius:50%;background:#c8401a;flex-shrink:0}
.notify-txt{font-size:12px;color:#8b3a1a}
.main{padding:14px 20px 24px}
.sec-label{font-size:11px;font-weight:600;color:#c8b8a8;letter-spacing:2px;margin-bottom:10px;margin-top:4px}
.card{background:#fff;border-radius:10px;padding:13px 15px;margin-bottom:8px;border:0.5px solid #e8e2d8;display:flex;align-items:center;gap:12px}
.card.paused{border-left:3px solid #c8401a;border-radius:0 10px 10px 0;background:#fffaf7}
.card.active{border-left:3px solid #6abf69;border-radius:0 10px 10px 0}
.ava{width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:600;flex-shrink:0;background:#f0ebe3;color:#8b3a1a}
.uinfo{flex:1;min-width:0}
.uname{font-size:13px;font-weight:600;color:#2d1f14}
.umsg{font-size:12px;color:#b0a090;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px}
.utime{font-size:11px;color:#ccc;margin-top:2px}
.badge{font-size:11px;padding:3px 9px;border-radius:10px;font-weight:500;flex-shrink:0}
.badge-ai{background:#d4e8d0;color:#27500a}
.badge-human{background:#f5d5c8;color:#712b13}
.btn-demo{border:0.5px solid #e0d8ce;border-radius:6px;padding:6px 12px;font-size:12px;font-weight:500;flex-shrink:0;background:#f7f5f2;color:#b0a090;cursor:not-allowed}
.divider{height:0.5px;background:#e8e2d8;margin:14px 0}
.cta{margin:20px;background:#fff;border-radius:12px;padding:24px;border:0.5px solid #e8e2d8;text-align:center}
.cta h3{font-size:16px;font-weight:600;color:#2d1f14;margin-bottom:8px}
.cta p{font-size:13px;color:#888;margin-bottom:16px}
.cta-btn{display:inline-block;background:#c8401a;color:#fff;padding:12px 32px;border-radius:8px;font-size:14px;font-weight:600;text-decoration:none}
.footer{text-align:center;padding:16px;font-size:11px;color:#ccc}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-brand">
    <div class="topbar-logo">AI</div>
    <div>
      <div class="topbar-name">您的品牌 後台 <span class="demo-badge">DEMO</span></div>
      <div class="topbar-sub">LINE AI 客服管理系統</div>
    </div>
  </div>
  <div class="online"><div class="pulse"></div><span>系統運作中</span></div>
</div>

<div class="stats">
  <div class="stat"><div class="stat-n">18</div><div class="stat-l">今日對話</div></div>
  <div class="stat"><div class="stat-n green">15</div><div class="stat-l">AI 回覆中</div></div>
  <div class="stat"><div class="stat-n orange">3</div><div class="stat-l">待人工處理</div></div>
  <div class="stat"><div class="stat-n">83<span style="font-size:13px;color:#bbb;">%</span></div><div class="stat-l">AI 回覆率</div></div>
</div>

<div class="notify"><div class="notify-dot"></div><div class="notify-txt">小美 需要您回覆，共 3 位客人等待中</div></div>

<div class="main">
  <div class="sec-label">待處理</div>
  <div class="card paused">
    <div class="ava">美</div>
    <div class="uinfo"><div class="uname">小美</div><div class="umsg">我想預約明天下午，還有空檔嗎？</div><div class="utime">04/01 14:32</div></div>
    <span class="badge badge-human">人工中</span>
    <button class="btn-demo">恢復 AI</button>
  </div>
  <div class="card paused">
    <div class="ava">琪</div>
    <div class="uinfo"><div class="uname">Angela琪琪</div><div class="umsg">找真人客服</div><div class="utime">04/01 13:50</div></div>
    <span class="badge badge-human">人工中</span>
    <button class="btn-demo">恢復 AI</button>
  </div>
  <div class="card paused">
    <div class="ava">J</div>
    <div class="uinfo"><div class="uname">Jennifer</div><div class="umsg">我想了解你們的價格</div><div class="utime">04/01 12:15</div></div>
    <span class="badge badge-human">人工中</span>
    <button class="btn-demo">恢復 AI</button>
  </div>

  <div class="divider"></div>
  <div class="sec-label">AI 回覆中</div>
  <div class="card active">
    <div class="ava">雅</div>
    <div class="uinfo"><div class="uname">雅婷</div><div class="umsg">你們營業到幾點？</div><div class="utime">04/01 15:01</div></div>
    <span class="badge badge-ai">AI 中</span>
    <button class="btn-demo">暫停 AI</button>
  </div>
  <div class="card active">
    <div class="ava">M</div>
    <div class="uinfo"><div class="uname">Mia♡</div><div class="umsg">請問有停車場嗎</div><div class="utime">04/01 14:55</div></div>
    <span class="badge badge-ai">AI 中</span>
    <button class="btn-demo">暫停 AI</button>
  </div>
  <div class="card active">
    <div class="ava">芳</div>
    <div class="uinfo"><div class="uname">王芳如</div><div class="umsg">第一次去需要注意什麼嗎</div><div class="utime">04/01 14:40</div></div>
    <span class="badge badge-ai">AI 中</span>
    <button class="btn-demo">暫停 AI</button>
  </div>
  <div class="card active">
    <div class="ava">S</div>
    <div class="uinfo"><div class="uname">Sandy</div><div class="umsg">有什麼推薦的課程嗎？</div><div class="utime">04/01 14:22</div></div>
    <span class="badge badge-ai">AI 中</span>
    <button class="btn-demo">暫停 AI</button>
  </div>
  <div class="card active">
    <div class="ava">佳</div>
    <div class="uinfo"><div class="uname">佳佳</div><div class="umsg">我想問一下護膚的內容</div><div class="utime">04/01 13:58</div></div>
    <span class="badge badge-ai">AI 中</span>
    <button class="btn-demo">暫停 AI</button>
  </div>
</div>

<div class="cta">
  <h3>想讓你的店也有這個後台？</h3>
  <p>AI 自動接客 + 一鍵切換真人，手機就能管理</p>
  <a class="cta-btn" href="https://line.me/R/ti/p/@YOUR_LINE_ID">我有興趣，立即諮詢</a>
</div>

<div class="footer">LINE AI 智能客服 — Powered by AI</div>
</body></html>"""


@app.route("/admin")
def admin():
    authenticated = request.cookies.get("admin_auth") == ADMIN_PASSWORD
    brand_name = "YS 療癒美學"
    all_users = []
    for uid, p in user_profiles.items():
        all_users.append({
            "id": uid, "name": p["name"], "picture": p.get("picture", ""),
            "lastMessage": p.get("lastMessage", ""), "lastTime": p.get("lastTime", ""),
            "paused": uid in paused_users
        })
    all_users.sort(key=lambda x: x["lastTime"], reverse=True)
    paused_list = [u for u in all_users if u["paused"]]
    active_list = [u for u in all_users if not u["paused"]]
    total = len(all_users)
    paused_count = len(paused_list)
    active_count = len(active_list)
    ai_rate = round((active_count / total * 100) if total > 0 else 100)
    html = render_template_string(
        ADMIN_HTML, authenticated=authenticated, brand_name=brand_name,
        paused_users_list=paused_list, active_users=active_list, pending_users=paused_list,
        total=total, active=active_count, paused_count=paused_count, ai_rate=ai_rate, error=False
    )
    resp = make_response(html)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp


@app.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("password")
    if password == ADMIN_PASSWORD:
        resp = make_response(redirect("/admin"))
        resp.set_cookie("admin_auth", ADMIN_PASSWORD, max_age=86400 * 7)
        return resp
    html = render_template_string(
        ADMIN_HTML, authenticated=False, brand_name="YS 療癒美學",
        paused_users_list=[], active_users=[], pending_users=[],
        total=0, active=0, paused_count=0, ai_rate=100, error=True
    )
    resp = make_response(html)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp


@app.route("/admin/toggle", methods=["POST"])
def admin_toggle():
    if request.cookies.get("admin_auth") != ADMIN_PASSWORD:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json()
    uid = data.get("userId")
    action = data.get("action")
    if action == "pause":
        paused_users.add(uid)
    elif action == "resume":
        paused_users.discard(uid)
    return jsonify({"status": "ok"})


@app.route("/demo-admin")
def demo_admin():
    resp = make_response(DEMO_ADMIN_HTML)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp


@app.route("/debug/logs")
def debug_logs():
    if request.cookies.get("admin_auth") != ADMIN_PASSWORD:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(app_logs[-50:])


# ===== Rich Menu 建立 =====
@app.route("/setup-richmenu")
def setup_richmenu():
    """一次性設定：建立 Rich Menu + 產生底圖 + 上傳 + 設為預設"""
    if request.cookies.get("admin_auth") != ADMIN_PASSWORD:
        return jsonify({"error": "unauthorized"}), 401

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return jsonify({"error": "Pillow not installed"}), 500

    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}

    # Step 1: 刪除舊的預設 Rich Menu
    try:
        old = requests.get("https://api.line.me/v2/bot/user/all/richmenu", headers=headers, timeout=10)
        if old.status_code == 200:
            old_id = old.json().get("richMenuId")
            if old_id:
                requests.delete(f"https://api.line.me/v2/bot/richmenu/{old_id}", headers=headers, timeout=10)
    except Exception:
        pass

    # Step 2: 建立 Rich Menu 物件
    richmenu_data = {
        "size": {"width": 2500, "height": 1686},
        "selected": True,
        "name": "LINE AI Demo Menu",
        "chatBarText": "點我展開選單",
        "areas": [
            {"bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
             "action": {"type": "message", "text": "我想體驗AI客服"}},
            {"bounds": {"x": 833, "y": 0, "width": 834, "height": 843},
             "action": {"type": "message", "text": "找真人"}},
            {"bounds": {"x": 1667, "y": 0, "width": 833, "height": 843},
             "action": {"type": "uri", "uri": DEMO_ADMIN_URL}},
            {"bounds": {"x": 0, "y": 843, "width": 833, "height": 843},
             "action": {"type": "message", "text": "哪些店家適合用"}},
            {"bounds": {"x": 833, "y": 843, "width": 834, "height": 843},
             "action": {"type": "message", "text": "怎麼收費"}},
            {"bounds": {"x": 1667, "y": 843, "width": 833, "height": 843},
             "action": {"type": "message", "text": "我有興趣，想了解更多"}}
        ]
    }

    r = requests.post("https://api.line.me/v2/bot/richmenu", headers=headers, json=richmenu_data, timeout=10)
    if r.status_code != 200:
        return jsonify({"error": "create richmenu failed", "detail": r.text}), 500
    richmenu_id = r.json()["richMenuId"]

    # Step 3: 用 PIL 產生底圖
    W, H = 2500, 1686
    cell_w, cell_h = 833, 843
    img = Image.new("RGB", (W, H), "#2d1f14")
    draw = ImageDraw.Draw(img)

    # 載入中文字體（先嘗試本機，再從網路下載靜態字體）
    font_large = None
    font_small = None
    FONT_PATH = "/tmp/NotoSansTC-Regular.otf"

    # 下載靜態中文字體（非 variable font，確保 Pillow 相容）
    if not os.path.exists(FONT_PATH):
        font_urls = [
            "https://raw.githubusercontent.com/googlefonts/noto-cjk/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf",
            "https://cdn.jsdelivr.net/gh/googlefonts/noto-cjk@main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf",
        ]
        for font_url in font_urls:
            try:
                print(f"[RICHMENU] Downloading font from {font_url[:60]}...", flush=True)
                fr = requests.get(font_url, timeout=60, allow_redirects=True)
                if fr.status_code == 200 and len(fr.content) > 1000000:
                    with open(FONT_PATH, "wb") as f:
                        f.write(fr.content)
                    print(f"[RICHMENU] Font downloaded: {len(fr.content)} bytes", flush=True)
                    break
                else:
                    print(f"[RICHMENU] Font download got status={fr.status_code} size={len(fr.content)}", flush=True)
            except Exception as e:
                print(f"[RICHMENU] Font download failed: {e}", flush=True)

    font_candidates = [
        FONT_PATH,
        "C:/Windows/Fonts/msjh.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for fp in font_candidates:
        try:
            font_large = ImageFont.truetype(fp, 64)
            font_small = ImageFont.truetype(fp, 36)
            print(f"[RICHMENU] Using font: {fp}", flush=True)
            break
        except Exception as e:
            print(f"[RICHMENU] Font {fp} failed: {e}", flush=True)
    if not font_large:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()
        print("[RICHMENU] WARNING: fallback to default font", flush=True)

    # 六格設定
    cells = [
        {"bg": "#c8401a", "icon": "AI", "title": "體驗 AI 客服", "sub": "問它任何問題"},
        {"bg": "#a03315", "icon": ">>", "title": "模擬真人轉接", "sub": "看轉接怎麼運作"},
        {"bg": "#8b6f5e", "icon": "PC", "title": "看後台 Demo", "sub": "管理介面搶先看"},
        {"bg": "#5a7d6e", "icon": "OK", "title": "適合哪些店家", "sub": "美甲美容美髮SPA"},
        {"bg": "#d4766a", "icon": "$$", "title": "方案 & 價格", "sub": "怎麼收費"},
        {"bg": "#b8860b", "icon": "GO", "title": "我有興趣", "sub": "聯繫專人諮詢"},
    ]

    for i, cell in enumerate(cells):
        col = i % 3
        row = i // 3
        x = col * cell_w + (1 if col == 1 else 0)
        y = row * cell_h
        w = cell_w + (1 if col == 1 else 0)

        # 背景色
        draw.rectangle([x + 2, y + 2, x + w - 2, y + cell_h - 2], fill=cell["bg"])

        # 圓形圖標
        cx, cy = x + w // 2, y + cell_h // 2 - 80
        r_size = 60
        draw.ellipse([cx - r_size, cy - r_size, cx + r_size, cy + r_size], fill="#ffffff30", outline="#ffffff")
        # 圖標文字
        icon_bbox = draw.textbbox((0, 0), cell["icon"], font=font_small)
        icon_w = icon_bbox[2] - icon_bbox[0]
        icon_h = icon_bbox[3] - icon_bbox[1]
        draw.text((cx - icon_w // 2, cy - icon_h // 2), cell["icon"], fill="#ffffff", font=font_small)

        # 標題
        title_bbox = draw.textbbox((0, 0), cell["title"], font=font_large)
        tw = title_bbox[2] - title_bbox[0]
        draw.text((x + (w - tw) // 2, y + cell_h // 2 + 20), cell["title"], fill="#ffffff", font=font_large)

        # 副標
        sub_bbox = draw.textbbox((0, 0), cell["sub"], font=font_small)
        sw = sub_bbox[2] - sub_bbox[0]
        draw.text((x + (w - sw) // 2, y + cell_h // 2 + 100), cell["sub"], fill="#ffffffbb", font=font_small)

    # 格線
    for col in range(1, 3):
        x = col * cell_w + (1 if col == 2 else 0)
        draw.line([(x, 0), (x, H)], fill="#1a1108", width=3)
    draw.line([(0, cell_h), (W, cell_h)], fill="#1a1108", width=3)

    # 儲存到暫存
    import io
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    # Step 4: 上傳圖片
    upload_headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "image/png"
    }
    r2 = requests.post(
        f"https://api-data.line.me/v2/bot/richmenu/{richmenu_id}/content",
        headers=upload_headers, data=img_bytes.read(), timeout=30
    )
    if r2.status_code != 200:
        return jsonify({"error": "upload image failed", "detail": r2.text}), 500

    # Step 5: 設為預設
    r3 = requests.post(
        f"https://api.line.me/v2/bot/user/all/richmenu/{richmenu_id}",
        headers={"Authorization": f"Bearer {LINE_TOKEN}"},
        timeout=10
    )
    if r3.status_code != 200:
        return jsonify({"error": "set default failed", "detail": r3.text}), 500

    return jsonify({"status": "ok", "richMenuId": richmenu_id, "message": "Rich Menu 建立完成！"})


# ===== 體驗 AI 客服的快捷入口 =====
@app.route("/webhook-test")
def webhook_test():
    return "Webhook 測試頁面 — 請透過 LINE 傳訊息測試"


@app.route("/test-font")
def test_font():
    """測試字體是否能正確渲染中文"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io
        FONT_PATH = "/tmp/NotoSansTC-Regular.otf"
        exists = os.path.exists(FONT_PATH)
        size = os.path.getsize(FONT_PATH) if exists else 0
        img = Image.new("RGB", (600, 200), "#2d1f14")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(FONT_PATH, 48)
            draw.text((20, 20), "體驗 AI 客服", fill="#ffffff", font=font)
            draw.text((20, 100), "美甲美容美髮SPA", fill="#ffffff", font=font)
            font_status = f"OK: {FONT_PATH} ({size} bytes)"
        except Exception as e:
            draw.text((20, 20), f"Font error: {e}", fill="#ff0000")
            font_status = f"ERROR: {e}"
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        resp = make_response(buf.read())
        resp.headers['Content-Type'] = 'image/png'
        return resp
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def health():
    return "LINE AI 客服系統運作中 ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
