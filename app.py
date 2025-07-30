from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, PostbackEvent,
    TemplateSendMessage, ButtonsTemplate, PostbackAction,
    MessageAction, URIAction, CarouselTemplate, CarouselColumn,
    FlexSendMessage, BubbleContainer, BoxComponent, TextComponent,
    ButtonComponent, SeparatorComponent, FollowEvent
)
import logging
import requests
import urllib.parse
import json
import re
from datetime import datetime, timedelta

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# LINE Bot 配置
CHANNEL_ACCESS_TOKEN = 'n3dIAErhnUGmlsBXDy/N2SLqd9bj98BxU/Yl+hRa3Wa4i17+kZY5szmn6aj2DKH0InFwUljSFdl83VWeFNcv4DW90zry+7ZpeeNhnhMe2F1dWgA6dSDQl3XXIguGQbf1iUavmx+Si5SFxJh84r4ScgdB04t89/1O/w1cDnyilFU='
CHANNEL_SECRET = 'aa49542cb806c9bf0870cc61a2b21a4c'

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# 用戶檢測狀態存儲
user_surveys = {}

# 作業管理系統
user_homework = {}

# 作業管理功能
def add_homework(user_id, homework_info):
    """新增作業到用戶的作業列表"""
    if user_id not in user_homework:
        user_homework[user_id] = []
    
    homework = {
        "id": len(user_homework[user_id]) + 1,
        "name": homework_info["task_name"],
        "type": homework_info["task_type"],
        "estimated_time": homework_info["estimated_time"],
        "due_date": homework_info["due_date"],
        "status": "pending",  # pending, completed
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    user_homework[user_id].append(homework)
    return homework

def complete_homework(user_id, task_name):
    """完成作業"""
    if user_id in user_homework:
        for homework in user_homework[user_id]:
            if homework["name"] == task_name and homework["status"] == "pending":
                homework["status"] = "completed"
                homework["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                return homework
    return None

def get_user_homework_summary(user_id):
    """獲取用戶作業摘要"""
    if user_id not in user_homework:
        return {"total": 0, "pending": 0, "completed": 0, "tasks": []}
    
    tasks = user_homework[user_id]
    total = len(tasks)
    pending = len([t for t in tasks if t["status"] == "pending"])
    completed = len([t for t in tasks if t["status"] == "completed"])
    
    return {
        "total": total,
        "pending": pending,
        "completed": completed,
        "tasks": tasks
    }

# 情緒檢測問題
EMOTION_QUESTIONS = [
    {
        "id": 1,
        "question": "在過去14天內，做事時提不起勁或沒有樂趣",
        "options": [
            {"label": "完全不會", "value": 0},
            {"label": "幾天", "value": 1},
            {"label": "一半以上的天數", "value": 2},
            {"label": "幾乎每天", "value": 3}
        ]
    },
    {
        "id": 2,
        "question": "在過去14天內，感到心情低落、沮喪或絕望",
        "options": [
            {"label": "完全不會", "value": 0},
            {"label": "幾天", "value": 1},
            {"label": "一半以上的天數", "value": 2},
            {"label": "幾乎每天", "value": 3}
        ]
    },
    {
        "id": 3,
        "question": "在過去14天內，感到緊張、焦慮或煩躁",
        "options": [
            {"label": "完全不會", "value": 0},
            {"label": "幾天", "value": 1},
            {"label": "一半以上的天數", "value": 2},
            {"label": "幾乎每天", "value": 3}
        ]
    },
    {
        "id": 4,
        "question": "在過去14天內，無法停止或控制擔憂",
        "options": [
            {"label": "完全不會", "value": 0},
            {"label": "幾天", "value": 1},
            {"label": "一半以上的天數", "value": 2},
            {"label": "幾乎每天", "value": 3}
        ]
    }
]

# 🌤️ 城市對應的觀測站 ID
station_map = {
    "臺北": "466920",
    "台北": "466920",
    "花蓮": "466990",
    "台中": "467490",
    "高雄": "467440",
    "台南": "467410"
}

# 天氣查詢函式
def get_weather(city="臺北"):
    CWA_API_KEY = 'CWA-C22E63D8-5AE9-4D2B-AF01-86D9257076CC'
    station_id = station_map.get(city)
    if not station_id:
        return f"找不到「{city}」的觀測站，請輸入例如「台北」、「花蓮」、「高雄」等城市名稱。"

    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001"
    params = {
        "Authorization": CWA_API_KEY,
        "StationId": station_id,
        "StationName": city
    }

    try:
        res = requests.get(url, params=params)
        data = res.json()
        logger.info(f"API 回傳內容: {data}")  # ✅ 印出 debug log

        stations = data.get("records", {}).get("Station", [])
        if not stations:
            return f"⚠️ {city} 目前查無觀測資料，可能是氣象局暫無即時更新"

        station = stations[0]
        elements = station.get("WeatherElement", {})
        obs_time = station.get("ObsTime", {}).get("DateTime", "未知")

        weather = elements.get("Weather", "無資料")
        temp = elements.get("AirTemperature", "無資料")
        humi = elements.get("RelativeHumidity", "無資料")
        uv = elements.get("UVIndex", "無資料")
        rain = elements.get("Now", {}).get("Precipitation", "無資料")

        return (
            f"📍 {city} 即時天氣資訊\n"
            f"🕒 時間：{obs_time}\n"
            f"🌤 天氣狀況：{weather}\n"
            f"🌡️ 溫度：{temp} °C\n"
            f"💧 溼度：{humi} %\n"
            f"🌧️ 降雨量：{rain} mm\n"
            f"🔆 紫外線指數：{uv}"
        )

    except Exception as e:
        logger.error(f"{city} 天氣查詢錯誤：{e}")
        return f"{city} 天氣查詢失敗，請稍後再試。"

# 創建粉紅色邊框樣式的文字選項
def create_pink_border_options(options):
    border_text = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    options_text = ""
    
    for i, option in enumerate(options):
        options_text += f"💖 {option['label']}\n"
        if i < len(options) - 1:
            options_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    return border_text + options_text + border_text

# 創建情緒檢測問題按鈕
def create_emotion_survey_question(user_id, question_index=0):
    if question_index >= len(EMOTION_QUESTIONS):
        return None
    
    question = EMOTION_QUESTIONS[question_index]
    progress = f"{int((question_index + 1) / len(EMOTION_QUESTIONS) * 100)}% ({question_index + 1}/{len(EMOTION_QUESTIONS)})"
    
    buttons_template = TemplateSendMessage(
        alt_text='情緒自我檢測',
        template=ButtonsTemplate(
            title=f'📋 情緒自我檢測 - {progress}',
            text=f"💭 {question['question']}",
            actions=[
                PostbackAction(
                    label=f"🌱 {option['label']}",
                    data=f'survey_{question_index}_{option["value"]}'
                ) for i, option in enumerate(question["options"])
            ]
        )
    )
    return buttons_template

# 創建淺綠色圓角按鈕的 Flex Message
def create_emotion_survey_flex(user_id, question_index=0):
    if question_index >= len(EMOTION_QUESTIONS):
        return None
    
    question = EMOTION_QUESTIONS[question_index]
    progress = f"{int((question_index + 1) / len(EMOTION_QUESTIONS) * 100)}% ({question_index + 1}/{len(EMOTION_QUESTIONS)})"
    
    # 創建選項按鈕
    option_buttons = []
    for i, option in enumerate(question["options"]):
        button = {
            "type": "button",
            "style": "primary",
            "color": "#90EE90",  # 淺綠色
            "height": "sm",
            "action": {
                "type": "message",
                "label": option["label"],
                "text": option["label"]  # 直接發送選項文字作為用戶訊息
            }
        }
        option_buttons.append(button)
    
    # 創建 Flex Message
    flex_message = {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": f"📋 情緒自我檢測 - {progress}",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#27AE60"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": f"💭 {question['question']}",
                    "wrap": True,
                    "size": "sm"
                },
                {
                    "type": "separator"
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": option_buttons
        }
    }
    
    return FlexSendMessage(alt_text="情緒自我檢測", contents=BubbleContainer.new_from_json_dict(flex_message))

# 分析情緒檢測結果
def analyze_emotion_results(answers):
    if len(answers) != len(EMOTION_QUESTIONS):
        return "檢測未完成，請重新開始。"
    
    total_score = sum(answers)
    
    # 分析憂鬱傾向（前2題）
    depression_score = answers[0] + answers[1]
    # 分析焦慮傾向（後2題）
    anxiety_score = answers[2] + answers[3]
    
    result = "📊 情緒檢測結果\n\n"
    
    # 憂鬱分析
    if depression_score <= 1:
        result += "• 憂鬱方面：你的情緒狀態良好，沒有明顯的憂鬱傾向 😊\n"
    elif depression_score <= 3:
        result += "• 憂鬱方面：雖然還沒到憂鬱傾向，但該提醒自己要留意了 ⚠️\n"
    else:
        result += "• 憂鬱方面：建議尋求專業心理諮商協助 💙\n"
    
    # 焦慮分析
    if anxiety_score <= 1:
        result += "• 焦慮方面：你的焦慮感應該極低，代表你很好地掌握了生活和工作節奏 🌟\n"
    elif anxiety_score <= 3:
        result += "• 焦慮方面：有些許焦慮，建議學習放鬆技巧 🧘‍♀️\n"
    else:
        result += "• 焦慮方面：焦慮程度較高，建議尋求專業協助 🆘\n"
    
    result += "\n💡 建議行動：\n"
    result += "努力讓自己的生活作息規律、適當運動、增加 Omega-3 或維生素B群、D攝取、充足睡眠，或是與好友一起踏青等等，都可以讓自己的心情轉向晴天喔 ☀️\n\n"
    result += "建議你可以多多利用還道舒心，每天調理讓你更輕鬆掌握自己 💝"
    
    return result

# 創建情緒按鈕模板
def create_emotion_buttons():
    buttons_template = TemplateSendMessage(
        alt_text='紀錄我的情緒',
        template=ButtonsTemplate(
            title='📝 紀錄我的情緒',
            text='經過剛才的舒心，你有感受到情緒的變化嗎？',
            actions=[
                PostbackAction(
                    label='🌱 感覺有變好',
                    data='emotion_better'
                ),
                PostbackAction(
                    label='🌱 沒有感覺到變化',
                    data='emotion_no_change'
                ),
                PostbackAction(
                    label='🌱 感覺變差',
                    data='emotion_worse'
                ),
                PostbackAction(
                    label='🌱 原本沒有情緒困擾',
                    data='emotion_no_issue'
                )
            ]
        )
    )
    return buttons_template

# 創建天氣查詢按鈕
def create_weather_buttons():
    buttons_template = TemplateSendMessage(
        alt_text='天氣查詢',
        template=ButtonsTemplate(
            title='🌤️ 天氣查詢',
            text='請選擇要查詢的城市：',
            actions=[
                PostbackAction(
                    label='🌱 台北天氣',
                    data='weather_台北'
                ),
                PostbackAction(
                    label='🌱 高雄天氣',
                    data='weather_高雄'
                ),
                PostbackAction(
                    label='🌱 台中天氣',
                    data='weather_台中'
                ),
                PostbackAction(
                    label='🌱 花蓮天氣',
                    data='weather_花蓮'
                )
            ]
        )
    )
    return buttons_template

# 創建淺綠色圓角按鈕
def create_green_button(label, data):
    button = ButtonComponent(
        style="primary",
        color="primary",
        height="sm",
        action=URIAction(
            label=label,
            uri=f"https://line.me/R/action/message?text={urllib.parse.quote(label)}"
        )
    )
    return button

# 解析作業資訊
def parse_homework_info(text):
    """解析用戶輸入的作業資訊"""
    info = {
        "task_name": "",
        "estimated_time": "",
        "task_type": "",
        "due_date": ""
    }
    
    # 解析作業名稱 - 支援更多類型
    if "行銷問卷" in text or "問卷" in text:
        info["task_name"] = "行銷問卷報告"
        info["task_type"] = "報告"
    elif "AI agent" in text or "agent" in text:
        info["task_name"] = "AI agent 報告"
        info["task_type"] = "報告"
    elif "作業系統" in text:
        info["task_name"] = "作業系統"
        info["task_type"] = "作業"
    elif "專題" in text:
        info["task_name"] = "專題報告"
        info["task_type"] = "報告"
    elif "簡報" in text or "ppt" in text:
        info["task_name"] = "簡報製作"
        info["task_type"] = "簡報"
    elif "程式" in text or "coding" in text:
        info["task_name"] = "程式作業"
        info["task_type"] = "作業"
    elif "報告" in text:
        # 提取報告前的關鍵詞作為作業名稱
        report_match = re.search(r'([^，。！？\s]+)報告', text)
        if report_match:
            info["task_name"] = f"{report_match.group(1)}報告"
        else:
            info["task_name"] = "報告"
        info["task_type"] = "報告"
    elif "作業" in text:
        # 提取作業前的關鍵詞作為作業名稱
        homework_match = re.search(r'([^，。！？\s]+)作業', text)
        if homework_match:
            info["task_name"] = f"{homework_match.group(1)}作業"
        else:
            info["task_name"] = "作業"
        info["task_type"] = "作業"
    else:
        # 如果沒有特定關鍵詞，嘗試提取第一個名詞作為作業名稱
        words = text.split()
        if len(words) > 0:
            info["task_name"] = words[0] + "作業"
        else:
            info["task_name"] = "新作業"
        info["task_type"] = "其他"
    
    # 解析時間 - 支援中文數字和阿拉伯數字
    time_patterns = [
        r'(\d+)\s*小時',  # 3小時
        r'(\d+)\s*個小時',  # 3個小時
        r'(\d+)\s*個鐘頭',  # 3個鐘頭
        r'大概\s*(\d+)\s*小時',  # 大概3小時
        r'預計\s*(\d+)\s*小時',  # 預計3小時
        r'(\d+)\s*個小時',  # 四個小時
        r'(\d+)\s*小時',  # 四小時
    ]
    
    # 中文數字轉換
    chinese_numbers = {
        '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
        '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'
    }
    
    time_found = False
    for pattern in time_patterns:
        time_match = re.search(pattern, text)
        if time_match:
            hours = time_match.group(1)
            # 檢查是否為中文數字
            if hours in chinese_numbers:
                hours = chinese_numbers[hours]
            info["estimated_time"] = f"{hours} 小時"
            time_found = True
            break
    
    # 如果沒有找到時間，使用預設值
    if not time_found:
        info["estimated_time"] = "2 小時"
    
    # 解析截止日期
    # 支援具體日期格式
    date_patterns = [
        r'(\d+)月(\d+)號',  # 8月1號
        r'(\d+)月(\d+)日',  # 8月1日
        r'(\d+)/(\d+)',     # 8/1
        r'(\d+)-(\d+)',     # 8-1
        r'明天',
        r'後天',
        r'大後天'
    ]
    
    date_found = False
    for pattern in date_patterns:
        date_match = re.search(pattern, text)
        if date_match:
            if pattern == r'明天':
                target_date = datetime.now() + timedelta(days=1)
                info["due_date"] = f"{target_date.year}年{target_date.month:02d}月{target_date.day:02d}日(明天)"
                date_found = True
                break
            elif pattern == r'後天':
                target_date = datetime.now() + timedelta(days=2)
                info["due_date"] = f"{target_date.year}年{target_date.month:02d}月{target_date.day:02d}日(後天)"
                date_found = True
                break
            elif pattern == r'大後天':
                target_date = datetime.now() + timedelta(days=3)
                info["due_date"] = f"{target_date.year}年{target_date.month:02d}月{target_date.day:02d}日(大後天)"
                date_found = True
                break
            else:
                # 處理具體日期
                month = int(date_match.group(1))
                day = int(date_match.group(2))
                current_year = datetime.now().year
                
                # 如果月份小於當前月份，假設是明年
                if month < datetime.now().month:
                    current_year += 1
                
                target_date = datetime(current_year, month, day)
                
                # 計算相對日期描述
                days_diff = (target_date - datetime.now()).days
                if days_diff == 0:
                    relative_date = "今天"
                elif days_diff == 1:
                    relative_date = "明天"
                elif days_diff == 2:
                    relative_date = "後天"
                elif days_diff == 3:
                    relative_date = "大後天"
                elif days_diff > 0:
                    relative_date = f"{days_diff}天後"
                else:
                    relative_date = f"{abs(days_diff)}天前"
                
                info["due_date"] = f"{target_date.year}年{target_date.month:02d}月{target_date.day:02d}日({relative_date})"
                date_found = True
                break
    
    # 如果沒有找到日期，使用預設值
    if not date_found:
        tomorrow = datetime.now() + timedelta(days=1)
        info["due_date"] = f"{tomorrow.year}年{tomorrow.month:02d}月{tomorrow.day:02d}日(明天)"
    
    return info

# 創建作業確認畫面
def create_homework_confirmation(info):
    """創建作業確認的 Flex Message"""
    
    flex_message = {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#6A5ACD",
            "contents": [
                {
                    "type": "text",
                    "text": "🍎 AI 智慧解析",
                    "color": "#FFFFFF",
                    "size": "sm",
                    "weight": "bold"
                },
                {
                    "type": "text",
                    "text": "請確認以下資訊是否正確",
                    "color": "#FFFFFF",
                    "size": "xs",
                    "margin": "sm"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "✏️",
                            "size": "sm",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": "作業名稱",
                            "size": "sm",
                            "color": "#666666",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": info["task_name"],
                            "size": "sm",
                            "color": "#333333",
                            "align": "end"
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "🕒",
                            "size": "sm",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": "預估時間",
                            "size": "sm",
                            "color": "#666666",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": info["estimated_time"],
                            "size": "sm",
                            "color": "#333333",
                            "align": "end"
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📊",
                            "size": "sm",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": "作業類型",
                            "size": "sm",
                            "color": "#666666",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": info["task_type"],
                            "size": "sm",
                            "color": "#333333",
                            "align": "end"
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📅",
                            "size": "sm",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": "截止日期",
                            "size": "sm",
                            "color": "#666666",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": info["due_date"],
                            "size": "sm",
                            "color": "#333333",
                            "align": "end"
                        }
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#4CAF50",
                    "action": {
                        "type": "postback",
                        "label": "✅ 確認新增",
                        "data": f"confirm_homework_{info['task_name']}_{info['estimated_time']}_{info['task_type']}_{info['due_date']}"
                    }
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "postback",
                                "label": "✏️ 修改",
                                "data": "modify_homework"
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "postback",
                                "label": "❌ 取消",
                                "data": "cancel_homework"
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    return FlexSendMessage(alt_text="作業確認", contents=BubbleContainer.new_from_json_dict(flex_message))

# 創建作業完成辨識畫面
def create_homework_completion_recognition(task_info):
    """創建作業完成辨識的 Flex Message"""
    
    flex_message = {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#6A5ACD",
            "contents": [
                {
                    "type": "text",
                    "text": "🍎 AI智慧辨識",
                    "color": "#FFFFFF",
                    "size": "sm",
                    "weight": "bold"
                },
                {
                    "type": "text",
                    "text": "信心度: 90%",
                    "color": "#FFFFFF",
                    "size": "xs",
                    "margin": "sm"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "找到符合的作業:",
                    "size": "xs",
                    "color": "#666666"
                },
                {
                    "type": "text",
                    "text": task_info["task_name"],
                    "size": "lg",
                    "weight": "bold",
                    "color": "#333333"
                },
                {
                    "type": "separator"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "類型",
                            "size": "sm",
                            "color": "#666666",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": task_info["task_type"],
                            "size": "sm",
                            "color": "#333333",
                            "align": "end"
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "預估時間",
                            "size": "sm",
                            "color": "#666666",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": task_info["estimated_time"],
                            "size": "sm",
                            "color": "#333333",
                            "align": "end"
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "截止日期",
                            "size": "sm",
                            "color": "#666666",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": task_info["due_date"],
                            "size": "sm",
                            "color": "#333333",
                            "align": "end"
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "完成狀態",
                            "size": "sm",
                            "color": "#666666",
                            "flex": 0
                        },
                        {
                            "type": "text",
                            "text": "提前 1 天完成",
                            "size": "sm",
                            "color": "#4CAF50",
                            "align": "end"
                        }
                    ]
                },
                {
                    "type": "separator"
                },
                {
                    "type": "text",
                    "text": "AI判斷理由",
                    "size": "xs",
                    "color": "#666666"
                },
                {
                    "type": "text",
                    "text": f"使用者輸入包含關鍵字「{task_info['keyword']}」，與作業名稱「{task_info['task_name']}」高度匹配。",
                    "size": "xs",
                    "color": "#333333",
                    "wrap": True
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#4CAF50",
                    "action": {
                        "type": "postback",
                        "label": "確認完成",
                        "data": f"confirm_completion_{task_info['task_name']}"
                    }
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "color": "#F44336",
                    "action": {
                        "type": "postback",
                        "label": "× 不是這個",
                        "data": "not_this_task"
                    }
                }
            ]
        }
    }
    
    return FlexSendMessage(alt_text="作業完成辨識", contents=BubbleContainer.new_from_json_dict(flex_message))

# 創建作業完成確認和列表畫面
def create_homework_completion_summary(user_id):
    """創建作業完成確認和列表的 Flex Message"""
    
    summary = get_user_homework_summary(user_id)
    completed_count = summary["completed"]
    pending_count = summary["pending"]
    total_count = summary["total"]
    
    # 獲取最近完成的作業
    completed_tasks = [t for t in summary["tasks"] if t["status"] == "completed"]
    latest_completed = completed_tasks[-1] if completed_tasks else None
    
    # 獲取待完成作業
    pending_tasks = [t for t in summary["tasks"] if t["status"] == "pending"]
    
    flex_message = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#4CAF50",
            "contents": [
                {
                    "type": "text",
                    "text": "🎉 太棒了!",
                    "color": "#FFFFFF",
                    "size": "lg",
                    "weight": "bold"
                },
                {
                    "type": "text",
                    "text": f"已完成: {latest_completed['name'] if latest_completed else '作業'}",
                    "color": "#FFFFFF",
                    "size": "sm",
                    "margin": "sm"
                },
                {
                    "type": "text",
                    "text": f"剩餘 {pending_count} 項作業待完成",
                    "color": "#FFFFFF",
                    "size": "xs",
                    "margin": "sm"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#4CAF50",
                            "action": {
                                "type": "postback",
                                "label": "✅ 繼續完成其他作業",
                                "data": "continue_tasks"
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "postback",
                                "label": "📄 查看所有作業",
                                "data": "view_all_tasks"
                            }
                        }
                    ]
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "text",
                    "text": "📄 作業列表",
                    "weight": "bold",
                    "size": "md",
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"總計: {total_count}",
                            "size": "xs",
                            "color": "#666666"
                        },
                        {
                            "type": "text",
                            "text": f"待完成: {pending_count}",
                            "size": "xs",
                            "color": "#F44336"
                        },
                        {
                            "type": "text",
                            "text": f"已完成: {completed_count}",
                            "size": "xs",
                            "color": "#4CAF50"
                        }
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#4CAF50",
                    "action": {
                        "type": "postback",
                        "label": "✅ 完成作業",
                        "data": "complete_task"
                    }
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "action": {
                        "type": "postback",
                        "label": "➕ 新增作業",
                        "data": "add_new_task"
                    }
                }
            ]
        }
    }
    
    # 添加作業列表
    if pending_tasks:
        task_list = []
        for task in pending_tasks[:5]:  # 最多顯示5個作業
            task_list.append({
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "text",
                        "text": task["name"],
                        "size": "sm",
                        "flex": 2
                    },
                    {
                        "type": "text",
                        "text": task["type"],
                        "size": "sm",
                        "flex": 1
                    },
                    {
                        "type": "text",
                        "text": task["estimated_time"],
                        "size": "sm",
                        "flex": 1
                    },
                    {
                        "type": "text",
                        "text": task["due_date"],
                        "size": "sm",
                        "flex": 1
                    },
                    {
                        "type": "text",
                        "text": "⏳",
                        "size": "sm",
                        "flex": 0
                    }
                ]
            })
        
        flex_message["body"]["contents"].extend(task_list)
    
    # 添加已完成的作業
    if completed_tasks:
        for task in completed_tasks[-3:]:  # 顯示最近3個完成的作業
            flex_message["body"]["contents"].append({
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "text",
                        "text": task["name"],
                        "size": "sm",
                        "flex": 2
                    },
                    {
                        "type": "text",
                        "text": task["type"],
                        "size": "sm",
                        "flex": 1
                    },
                    {
                        "type": "text",
                        "text": task["estimated_time"],
                        "size": "sm",
                        "flex": 1
                    },
                    {
                        "type": "text",
                        "text": task["due_date"],
                        "size": "sm",
                        "flex": 1
                    },
                    {
                        "type": "text",
                        "text": "✅",
                        "size": "sm",
                        "flex": 0
                    }
                ]
            })
    
    return FlexSendMessage(alt_text="作業完成摘要", contents=BubbleContainer.new_from_json_dict(flex_message))

@app.route("/")
def hello():
    logger.info("收到 GET 請求到根路徑")
    return "LINE Bot 正在運行！"

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    logger.info(f"收到 {request.method} 請求到 webhook")
    if request.method == 'GET':
        return "Webhook 正常運行"

    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    logger.info(f"收到 POST 請求，簽名: {signature[:20]}...")
    logger.info(f"請求體: {body[:200]}...")

    try:
        handler.handle(body, signature)
        return 'OK'
    except InvalidSignatureError as e:
        logger.error(f"簽名驗證失敗: {e}")
        abort(400)
    except Exception as e:
        logger.error(f"處理 webhook 時發生錯誤: {e}")
        abort(500)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.strip()
    user_id = event.source.user_id
    logger.info(f"收到用戶訊息: {user_message}")

    if user_message == "你好":
        # 發送歡迎訊息和主選單
        welcome_text = TextSendMessage(text="你好！我是你的情緒小助手 😊\n\n請選擇以下功能：")
        main_menu = TemplateSendMessage(
            alt_text='主選單',
            template=ButtonsTemplate(
                title='🧠 情緒小助手',
                text='請選擇您需要的服務：',
                actions=[
                    PostbackAction(
                        label='📋 填寫情緒自我檢測',
                        data='start_survey'
                    ),
                    PostbackAction(
                        label='📝 紀錄我的情緒',
                        data='emotion_record'
                    ),
                    PostbackAction(
                        label='🌤️ 天氣查詢',
                        data='weather_menu'
                    )
                ]
            )
        )
        
        line_bot_api.reply_message(
            event.reply_token,
            [welcome_text, main_menu]
        )
    elif user_message.endswith("天氣"):
        city = user_message.replace("天氣", "").strip()
        if not city:
            city = "臺北"
        bot_response = get_weather(city)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=bot_response)
        )
    elif user_message in ["完全不會", "幾天", "一半以上的天數", "幾乎每天"]:
        # 處理情緒檢測的選項選擇
        if user_id in user_surveys:
            # 找到對應的選項值
            option_value = None
            if user_message == "完全不會":
                option_value = 0
            elif user_message == "幾天":
                option_value = 1
            elif user_message == "一半以上的天數":
                option_value = 2
            elif user_message == "幾乎每天":
                option_value = 3
            
            if option_value is not None:
                question_index = user_surveys[user_id]["current_question"]
                user_surveys[user_id]["answers"].append(option_value)
                user_surveys[user_id]["current_question"] = question_index + 1
                
                # 檢查是否完成所有問題
                if user_surveys[user_id]["current_question"] >= len(EMOTION_QUESTIONS):
                    # 完成檢測，顯示結果
                    result = analyze_emotion_results(user_surveys[user_id]["answers"])
                    result_message = TextSendMessage(text=result)
                    
                    # 創建回到主選單的按鈕
                    back_to_menu = TemplateSendMessage(
                        alt_text='回到主選單',
                        template=ButtonsTemplate(
                            title='🧠 情緒小助手',
                            text='請選擇您需要的服務：',
                            actions=[
                                PostbackAction(
                                    label='📋 填寫情緒自我檢測',
                                    data='start_survey'
                                ),
                                PostbackAction(
                                    label='📝 紀錄我的情緒',
                                    data='emotion_record'
                                ),
                                PostbackAction(
                                    label='🌤️ 天氣查詢',
                                    data='weather_menu'
                                )
                            ]
                        )
                    )
                    
                    line_bot_api.reply_message(
                        event.reply_token,
                        [result_message, back_to_menu]
                    )
                    # 清除檢測狀態
                    del user_surveys[user_id]
                else:
                    # 顯示下一題
                    next_question = create_emotion_survey_flex(user_id, user_surveys[user_id]["current_question"])
                    line_bot_api.reply_message(
                        event.reply_token,
                        next_question
                    )
    elif any(keyword in user_message for keyword in ["要交", "要完成", "需要做", "作業", "報告", "小時"]):
        # 處理作業相關的輸入
        homework_info = parse_homework_info(user_message)
        logger.info(f"解析的作業資訊: {homework_info}")  # 添加調試信息
        confirmation = create_homework_confirmation(homework_info)
        line_bot_api.reply_message(
            event.reply_token,
            confirmation
        )
    elif any(keyword in user_message for keyword in ["完成了", "完成", "做完了", "交完了"]):
        # 處理作業完成相關的輸入
        if "agent" in user_message.lower() or "ai" in user_message.lower():
            task_info = {
                "task_name": "AI agent 報告",
                "task_type": "報告",
                "estimated_time": "3 小時",
                "due_date": "2025-05-28",
                "keyword": "AI agent"
            }
        elif "作業" in user_message:
            task_info = {
                "task_name": "作業系統",
                "task_type": "作業",
                "estimated_time": "2 小時",
                "due_date": "2025-05-28",
                "keyword": "作業"
            }
        else:
            task_info = {
                "task_name": "新作業",
                "task_type": "其他",
                "estimated_time": "2 小時",
                "due_date": "2025-05-28",
                "keyword": "完成"
            }
        
        # 先發送確認訊息
        confirm_message = TextSendMessage(text="作業已成功新增!")
        
        # 再發送 AI 智慧辨識畫面
        recognition = create_homework_completion_recognition(task_info)
        
        line_bot_api.reply_message(
            event.reply_token,
            [confirm_message, recognition]
        )
    else:
        bot_response = f"您說的是：{user_message}\n\n試試輸入「你好」來開始互動！"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=bot_response)
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    user_id = event.source.user_id
    logger.info(f"收到 postback: {data}")
    
    if data == 'start_survey':
        # 開始情緒檢測
        user_surveys[user_id] = {"answers": [], "current_question": 0}
        question_template = create_emotion_survey_flex(user_id, 0)
        line_bot_api.reply_message(
            event.reply_token,
            question_template
        )
    
    elif data.startswith('survey_'):
        # 處理檢測答案
        parts = data.split('_')
        question_index = int(parts[1])
        answer_value = int(parts[2])
        
        if user_id not in user_surveys:
            user_surveys[user_id] = {"answers": [], "current_question": 0}
        
        # 獲取用戶選擇的選項文字
        question = EMOTION_QUESTIONS[question_index]
        selected_option = None
        for option in question["options"]:
            if option["value"] == answer_value:
                selected_option = option["label"]
                break
        
        user_surveys[user_id]["answers"].append(answer_value)
        user_surveys[user_id]["current_question"] = question_index + 1
        
        # 檢查是否完成所有問題
        if user_surveys[user_id]["current_question"] >= len(EMOTION_QUESTIONS):
            # 完成檢測，顯示結果
            result = analyze_emotion_results(user_surveys[user_id]["answers"])
            result_message = TextSendMessage(text=result)
            
            # 創建回到主選單的按鈕
            back_to_menu = TemplateSendMessage(
                alt_text='回到主選單',
                template=ButtonsTemplate(
                    title='🧠 情緒小助手',
                    text='請選擇您需要的服務：',
                    actions=[
                        PostbackAction(
                            label='📋 填寫情緒自我檢測',
                            data='start_survey'
                        ),
                        PostbackAction(
                            label='📝 紀錄我的情緒',
                            data='emotion_record'
                        ),
                        PostbackAction(
                            label='🌤️ 天氣查詢',
                            data='weather_menu'
                        )
                    ]
                )
            )
            
            line_bot_api.reply_message(
                event.reply_token,
                [result_message, back_to_menu]
            )
            # 清除檢測狀態
            del user_surveys[user_id]
        else:
            # 顯示下一題
            next_question = create_emotion_survey_flex(user_id, user_surveys[user_id]["current_question"])
            
            line_bot_api.reply_message(
                event.reply_token,
                next_question
            )
    
    elif data == 'emotion_record':
        # 顯示情緒紀錄按鈕
        emotion_buttons = create_emotion_buttons()
        line_bot_api.reply_message(
            event.reply_token,
            emotion_buttons
        )
    
    elif data == 'weather_menu':
        # 顯示天氣查詢按鈕
        weather_buttons = create_weather_buttons()
        line_bot_api.reply_message(
            event.reply_token,
            weather_buttons
        )
    
    elif data.startswith('emotion_'):
        if data == 'emotion_better':
            response = "很開心能為你帶來心情上的平靜，維持每日舒心的習慣，有助於長期情緒的舒緩和穩定 😌"
        elif data == 'emotion_no_change':
            response = "沒關係，情緒的變化需要時間。持續的關懷和陪伴會慢慢產生效果 💪"
        elif data == 'emotion_worse':
            response = "我理解你的感受。如果情緒持續低落，建議尋求專業的心理諮商協助 🤗"
        else:  # emotion_no_issue
            response = "很好！保持正向的心態，繼續享受生活的美好 ✨"
        
        # 創建回到主選單的按鈕
        back_to_menu = TemplateSendMessage(
            alt_text='回到主選單',
            template=ButtonsTemplate(
                title='🧠 情緒小助手',
                text='請選擇您需要的服務：',
                actions=[
                    PostbackAction(
                        label='📋 填寫情緒自我檢測',
                        data='start_survey'
                    ),
                    PostbackAction(
                        label='📝 紀錄我的情緒',
                        data='emotion_record'
                    ),
                    PostbackAction(
                        label='🌤️ 天氣查詢',
                        data='weather_menu'
                    )
                ]
            )
        )
        
        line_bot_api.reply_message(
            event.reply_token,
            [TextSendMessage(text=response), back_to_menu]
        )
    
    elif data.startswith('weather_'):
        city = data.replace('weather_', '')
        weather_info = get_weather(city)
        
        # 創建回到主選單的按鈕
        back_to_menu = TemplateSendMessage(
            alt_text='回到主選單',
            template=ButtonsTemplate(
                title='🧠 情緒小助手',
                text='請選擇您需要的服務：',
                actions=[
                    PostbackAction(
                        label='📋 填寫情緒自我檢測',
                        data='start_survey'
                    ),
                    PostbackAction(
                        label='📝 紀錄我的情緒',
                        data='emotion_record'
                    ),
                    PostbackAction(
                        label='🌤️ 天氣查詢',
                        data='weather_menu'
                    )
                ]
            )
        )
        
        line_bot_api.reply_message(
            event.reply_token,
            [TextSendMessage(text=weather_info), back_to_menu]
        )
    
    elif data.startswith('confirm_homework_'):
        # 處理作業確認
        parts = data.split('_')
        task_name = parts[2]
        estimated_time = parts[3]
        task_type = parts[4]
        due_date = parts[5]
        
        # 保存作業到系統
        homework_info = {
            "task_name": task_name,
            "task_type": task_type,
            "estimated_time": estimated_time,
            "due_date": due_date
        }
        
        add_homework(user_id, homework_info)
        
        success_message = f"✅ 作業已成功新增！\n\n📋 作業名稱：{task_name}\n⏰ 預估時間：{estimated_time}\n📊 作業類型：{task_type}\n📅 截止日期：{due_date}\n\n您的作業已加入行程管理系統！"
        
        # 創建回到主選單的按鈕
        back_to_menu = TemplateSendMessage(
            alt_text='回到主選單',
            template=ButtonsTemplate(
                title='🧠 情緒小助手',
                text='請選擇您需要的服務：',
                actions=[
                    PostbackAction(
                        label='📋 填寫情緒自我檢測',
                        data='start_survey'
                    ),
                    PostbackAction(
                        label='📝 紀錄我的情緒',
                        data='emotion_record'
                    ),
                    PostbackAction(
                        label='🌤️ 天氣查詢',
                        data='weather_menu'
                    )
                ]
            )
        )
        
        line_bot_api.reply_message(
            event.reply_token,
            [TextSendMessage(text=success_message), back_to_menu]
        )
    
    elif data == 'modify_homework':
        # 處理作業修改
        modify_message = "請重新輸入您的作業資訊，例如：\n\n• 我明天要交AI報告，大概3小時\n• 後天要完成作業系統，預計2小時\n• 我需要做一份報告，明天截止"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=modify_message)
        )
    
    elif data == 'cancel_homework':
        # 處理作業取消
        cancel_message = "已取消新增作業。您可以重新輸入作業資訊，或選擇其他功能。"
        
        # 創建回到主選單的按鈕
        back_to_menu = TemplateSendMessage(
            alt_text='回到主選單',
            template=ButtonsTemplate(
                title='🧠 情緒小助手',
                text='請選擇您需要的服務：',
                actions=[
                    PostbackAction(
                        label='📋 填寫情緒自我檢測',
                        data='start_survey'
                    ),
                    PostbackAction(
                        label='📝 紀錄我的情緒',
                        data='emotion_record'
                    ),
                    PostbackAction(
                        label='🌤️ 天氣查詢',
                        data='weather_menu'
                    )
                ]
            )
        )
        
        line_bot_api.reply_message(
            event.reply_token,
            [TextSendMessage(text=cancel_message), back_to_menu]
        )
    
    elif data.startswith('confirm_completion_'):
        # 處理作業完成確認
        task_name = data.replace('confirm_completion_', '')
        
        # 完成作業
        completed_homework = complete_homework(user_id, task_name)
        
        if completed_homework:
            # 顯示作業完成摘要畫面
            summary = create_homework_completion_summary(user_id)
            
            line_bot_api.reply_message(
                event.reply_token,
                summary
            )
        else:
            # 如果找不到作業，顯示錯誤訊息
            error_message = f"❌ 找不到作業「{task_name}」，請確認作業名稱是否正確。"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=error_message)
            )
    
    elif data == 'not_this_task':
        # 處理不是這個作業的回應
        not_this_message = "抱歉，我可能辨識錯誤了。請重新輸入您完成的作業名稱，例如：\n\n• 我完成了 AI agent 報告\n• 作業系統做完了\n• 我交完了報告"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=not_this_message)
        )
    
    elif data == 'continue_tasks':
        # 處理繼續完成其他作業
        continue_message = "請選擇您要完成的作業，或直接輸入作業名稱，例如：\n\n• 我完成了專題\n• 作業系統做完了\n• 國文作業完成了"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=continue_message)
        )
    
    elif data == 'view_all_tasks':
        # 處理查看所有作業
        summary = get_user_homework_summary(user_id)
        
        if summary["total"] == 0:
            all_tasks_message = "📄 您目前沒有任何作業。\n\n請使用「新增作業」功能來添加您的第一個作業！"
        else:
            all_tasks_message = f"📄 您的所有作業：\n\n"
            
            # 顯示待完成作業
            pending_tasks = [t for t in summary["tasks"] if t["status"] == "pending"]
            if pending_tasks:
                all_tasks_message += f"⏳ 待完成 ({len(pending_tasks)}項)：\n"
                for task in pending_tasks:
                    all_tasks_message += f"• {task['name']} ({task['type']}) - {task['estimated_time']} - {task['due_date']}\n"
                all_tasks_message += "\n"
            
            # 顯示已完成作業
            completed_tasks = [t for t in summary["tasks"] if t["status"] == "completed"]
            if completed_tasks:
                all_tasks_message += f"✅ 已完成 ({len(completed_tasks)}項)：\n"
                for task in completed_tasks:
                    all_tasks_message += f"• {task['name']} ({task['type']}) - {task['estimated_time']} - {task['due_date']}\n"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=all_tasks_message)
        )
    
    elif data == 'complete_task':
        # 處理完成作業按鈕
        complete_message = "請輸入您要完成的作業名稱，例如：\n\n• 我完成了專題\n• 作業系統做完了\n• 國文作業完成了"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=complete_message)
        )
    
    elif data == 'add_new_task':
        # 處理新增作業按鈕
        add_task_message = "請輸入您要新增的作業資訊，例如：\n\n• 我明天要交專題報告，大概5小時\n• 後天要完成程式作業，預計3小時\n• 我需要做一份簡報，下週截止"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=add_task_message)
        )

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    logger.info(f"收到用戶加入好友事件: {user_id}")
    
    # 發送歡迎訊息和主選單
    welcome_text = TextSendMessage(text="你好！我是你的情緒小助手 😊\n\n請選擇以下功能：")
    main_menu = TemplateSendMessage(
        alt_text='主選單',
        template=ButtonsTemplate(
            title='🧠 情緒小助手',
            text='請選擇您需要的服務：',
            actions=[
                PostbackAction(
                    label='📋 填寫情緒自我檢測',
                    data='start_survey'
                ),
                PostbackAction(
                    label='📝 紀錄我的情緒',
                    data='emotion_record'
                ),
                PostbackAction(
                    label='🌤️ 天氣查詢',
                    data='weather_menu'
                )
            ]
        )
    )
    
    line_bot_api.reply_message(
        event.reply_token,
        [welcome_text, main_menu]
    )

if __name__ == "__main__":
    logger.info("LINE Bot 伺服器正在運行，端口: 5000")
    logger.info("Webhook URL: http://localhost:5000/webhook")
    logger.info("當用戶輸入「你好」時，Bot 會顯示主選單")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
