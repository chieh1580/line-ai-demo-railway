from flask import Flask, request, jsonify, render_template_string, make_response, redirect
import anthropic
import requests
import os
from datetime import datetime

app = Flask(__name__)

CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
LINE_TOKEN = os.environ.get("LINE_TOKEN")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ys2024")

paused_users = set()
user_profiles = {}

TRIGGER_WORDS = ["找真人","找人工","找客服","找老師","真人","人工","我想了解","我想購買"]

SYSTEM_PROMPT = """你是「YS小幫手」，YS療癒美學SPA的專屬AI客服。個性親切溫柔、說話像朋友，讓客人感覺被重視、被照顧。只回答與YS療癒美學相關的問題，不回答無關話題。

【店家資訊】
店名：YS療癒美學 SPA
地址：桃園市桃園區國豐三街76號
營業時間：每天 10:00 - 22:00
LINE：@y.s1314
預約方式：LINE私訊人工確認 / EZpretty預約連結 / 電話預約

【師資】
淇淇老師（國際講師）、GINA老師、雪蓮老師、星辭老師，都是專業撥經師。

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

【禁用詞規則】
絕對不可說：治療、療效、醫療、診斷、治癒、改善疾病、消除、根治
改說：舒緩、放鬆、調理、養護、舒壓、讓身體更有活力

【回答原則】
1. 語氣親切溫柔像朋友
2. 回答簡潔不要一次丟太多資訊
3. 問效果時說「很多客人體驗後都說感覺輕鬆許多，每個人感受不同，歡迎來體驗看看！」
4. 客人想預約時引導詢問：服務項目、日期時段、偏好老師
5. 不確定的問題說「讓我幫您轉給專人確認」"""

ADMIN_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>YS 療癒美學 後台</title>
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
  <div class="online">
    <div class="pulse"></div>
    <span>系統運作中</span>
  </div>
</div>

<div class="stats">
  <div class="stat"><div class="stat-n">{{ total }}</div><div class="stat-l">今日對話</div></div>
  <div class="stat"><div class="stat-n green">{{ active }}</div><div class="stat-l">AI 回覆中</div></div>
  <div class="stat"><div class="stat-n orange">{{ paused_count }}</div><div class="stat-l">待人工處理</div></div>
  <div class="stat"><div class="stat-n">{{ ai_rate }}<span style="font-size:13px;color:#bbb;">%</span></div><div class="stat-l">AI 回覆率</div></div>
</div>

{% if pending_users %}
<div class="notify">
  <div class="notify-dot"></div>
  <div class="notify-txt">{{ pending_users[0].name }} 需要您回覆，共 {{ paused_count }} 位客人等待中</div>
</div>
{% endif %}

<div class="main">
  {% if paused_users_list %}
  <div class="sec-label">待處理</div>
  {% for u in paused_users_list %}
  <div class="card paused">
    <div class="ava">
      {% if u.picture %}<img src="{{ u.picture }}" onerror="this.style.display='none'">{% else %}{{ u.name[0] }}{% endif %}
    </div>
    <div class="uinfo">
      <div class="uname">{{ u.name }}</div>
      <div class="umsg">{{ u.lastMessage }}</div>
      <div class="utime">{{ u.lastTime }}</div>
    </div>
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
    <div class="ava">
      {% if u.picture %}<img src="{{ u.picture }}" onerror="this.style.display='none'">{% else %}{{ u.name[0] }}{% endif %}
    </div>
    <div class="uinfo">
      <div class="uname">{{ u.name }}</div>
      <div class="umsg">{{ u.lastMessage }}</div>
      <div class="utime">{{ u.lastTime }}</div>
    </div>
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
  fetch('/admin/toggle', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({userId: uid, action: action})
  }).then(r => r.json()).then(() => {
    const t = document.getElementById('toast')
    t.textContent = action === 'pause' ? '已暫停 AI，換您回覆' : '已恢復 AI 自動回覆'
    t.style.display = 'block'
    setTimeout(() => { t.style.display = 'none'; location.reload() }, 1000)
  })
}
setTimeout(() => location.reload(), 30000)
</script>
{% endif %}
</body>
</html>"""


def get_line_profile(user_id):
    try:
        r = requests.get(
            f"https://api.line.me/v2/bot/profile/{user_id}",
            headers={"Authorization": f"Bearer {LINE_TOKEN}"},
            timeout=5
        )
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return {"displayName": "用戶" + user_id[-4:], "pictureUrl": ""}


def reply_to_user(reply_token, message):
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"},
        json={"replyToken": reply_token, "messages": [{"type": "text", "text": message}]},
        timeout=10
    )


def ask_claude(user_message):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )
    return msg.content[0].text


@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json()
    if not body or "events" not in body:
        return jsonify({"status": "ok"})

    for event in body["events"]:
        if event.get("type") != "message":
            continue
        if event["message"].get("type") != "text":
            continue

        user_id = event["source"]["userId"]
        reply_token = event["replyToken"]
        user_message = event["message"]["text"]

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

        if user_id in paused_users:
            continue

        if any(word in user_message for word in TRIGGER_WORDS):
            paused_users.add(user_id)
            reply_to_user(reply_token, "好的！我馬上幫您通知專人，請稍候片刻，我們會盡快與您聯繫 🙏")
            continue

        try:
            ai_response = ask_claude(user_message)
            reply_to_user(reply_token, ai_response)
        except:
            reply_to_user(reply_token, "抱歉，系統暫時忙碌中，請稍後再試或直接聯繫我們 🙏")

    return jsonify({"status": "ok"})


@app.route("/admin")
def admin():
    authenticated = request.cookies.get("admin_auth") == ADMIN_PASSWORD
    brand_name = os.environ.get("BRAND_NAME", "YS 療癒美學")

    all_users = []
    for uid, p in user_profiles.items():
        all_users.append({
            "id": uid,
            "name": p["name"],
            "picture": p.get("picture", ""),
            "lastMessage": p.get("lastMessage", ""),
            "lastTime": p.get("lastTime", ""),
            "paused": uid in paused_users
        })
    all_users.sort(key=lambda x: x["lastTime"], reverse=True)

    paused_list = [u for u in all_users if u["paused"]]
    active_list = [u for u in all_users if not u["paused"]]
    total = len(all_users)
    paused_count = len(paused_list)
    active_count = len(active_list)
    ai_rate = round((active_count / total * 100) if total > 0 else 100)

    return render_template_string(
        ADMIN_HTML,
        authenticated=authenticated,
        brand_name=brand_name,
        paused_users_list=paused_list,
        active_users=active_list,
        pending_users=paused_list,
        total=total,
        active=active_count,
        paused_count=paused_count,
        ai_rate=ai_rate,
        error=False
    )


@app.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("password")
    if password == ADMIN_PASSWORD:
        resp = make_response(redirect("/admin"))
        resp.set_cookie("admin_auth", ADMIN_PASSWORD, max_age=86400 * 7)
        return resp
    brand_name = os.environ.get("BRAND_NAME", "YS 療癒美學")
    return render_template_string(
        ADMIN_HTML, authenticated=False, brand_name=brand_name,
        paused_users_list=[], active_users=[], pending_users=[],
        total=0, active=0, paused_count=0, ai_rate=100, error=True
    )


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


@app.route("/")
def health():
    return "LINE AI 客服系統運作中 ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
