# KennyBot - LINE Bot 專案

這是一個簡單的 LINE Bot 專案，當用戶輸入「你好」時，Bot 會回答「我今天好嗎？」

## 功能

- 當用戶輸入「你好」時，Bot 回覆「我今天好嗎？」
- 其他輸入會回覆「您說的是：[用戶輸入]」
- 基本的 Echo 功能

## 安裝

1. 安裝依賴：
```bash
npm install
```

## 運行

### 開發模式
```bash
npm run dev
```

### 生產模式
```bash
npm start
```

## 配置

Bot 已經配置了您的 LINE Channel Token 和 Secret。伺服器將在端口 5000 上運行。

## Webhook 設置

1. 啟動 ngrok：
```bash
cd C:\Users\x\ngrok-v3-stable-windows-amd64
.\ngrok.exe http 5000
```

2. 在 LINE Developers Console 中設置 Webhook URL：
```
https://your-ngrok-url.ngrok.io/webhook
```

## 測試

1. 啟動 Bot 伺服器
2. 啟動 ngrok
3. 在 LINE 中向 Bot 發送「你好」
4. Bot 應該回覆「我今天好嗎？」

## 專案結構

```
kennybot/
├── index.js          # 主要應用程式
├── config.js         # 配置文件
├── package.json      # 專案依賴
├── .gitignore       # Git 忽略文件
└── README.md        # 說明文件
```

## 安全注意事項

- 請確保不要將 token 和 secret 提交到版本控制系統
- 建議使用環境變數來存儲敏感資訊
- 在生產環境中使用 HTTPS 