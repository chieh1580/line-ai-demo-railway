# LINE AI Demo 機器人 — 部署說明

## 環境變數（Railway Variables 頁面設定）

| 變數名稱 | 說明 | 範例 |
|---|---|---|
| CLAUDE_API_KEY | Claude API 金鑰 | sk-ant-api03-... |
| LINE_TOKEN | LINE Channel Access Token | 長串 Token |
| ADMIN_PASSWORD | 後台登入密碼 | 自訂密碼 |
| BRAND_NAME | 後台顯示的品牌名稱 | YS 療癒美學 |

---

## 部署步驟

### 1. 上傳到 GitHub
建立新 repo，名稱：line-ai-demo-railway
把這個資料夾的所有檔案上傳

### 2. 部署到 Railway
1. 登入 railway.app
2. New Project → Deploy from GitHub repo
3. 選 line-ai-demo-railway
4. 等待部署完成

### 3. 設定環境變數
Railway 後台 → Variables → 加入上表所有變數

### 4. 取得 Webhook 網址
部署完成後取得網址，例如：
https://line-ai-demo-railway.up.railway.app

Webhook 網址：
https://line-ai-demo-railway.up.railway.app/webhook

後台網址：
https://line-ai-demo-railway.up.railway.app/admin

### 5. 設定 LINE Webhook
LINE Official Account Manager
→ 設定 → Messaging API → Webhook 網址
→ 貼上 Webhook 網址 → 驗證

---

## 後台功能

- 登入密碼保護
- 客人列表（頭像、名字、最後訊息）
- 一鍵暫停 / 恢復 AI 回覆
- 待處理客人置頂顯示
- 每 30 秒自動刷新

## 未來要換客戶時

只需要改環境變數：
- BRAND_NAME → 新客戶品牌名
- LINE_TOKEN → 新客戶的 Token
- System Prompt → 在 app.py 的 SYSTEM_PROMPT 變數修改
