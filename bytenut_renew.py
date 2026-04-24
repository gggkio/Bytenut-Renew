import os
import json
import time
import re
import requests
from datetime import datetime
from seleniumbase import SB

# ================= 配置与环境变量解析 =================

BYTENUT_ACCOUNTS = os.environ.get('BYTENUT_ACCOUNTS', '[]')
try:
    ACCOUNTS = json.loads(BYTENUT_ACCOUNTS)
except json.JSONDecodeError:
    print("❌ BYTENUT_ACCOUNTS 解析失败！")
    ACCOUNTS = []

TG_BOT = os.environ.get('TG_BOT', '')
USE_PROXY = os.environ.get('GOST_PROXY') != ''
PROXY_STR = "http://127.0.0.1:8080" if USE_PROXY else None

def send_telegram_message(message):
    print("\n📣 准备发送 Telegram 汇总通知...")
    print(message.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', ''))
    if not TG_BOT or ',' not in TG_BOT:
        return
    try:
        token, chat_id = TG_BOT.split(',', 1)
        url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
        payload = {"chat_id": chat_id.strip(), "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
        print("✅ Telegram 通知发送成功！")
    except Exception as e:
        print(f"⚠️ Telegram 消息发送失败: {e}")

def get_remaining_time(sb):
    """提取页面上的剩余时间"""
    try:
        page_text = sb.get_text("body")
        # 正则匹配寻找类似 "01:58 REMAINING" 或 "01:58\nREMAINING" 的时间格式
        match = re.search(r'(\d{2}:\d{2})\s*REMAINING', page_text, re.IGNORECASE)
        if match:
            return match.group(1)
    except:
        pass
    return "未知"

# ================= 核心自动化逻辑 =================

def login_and_renew(sb, account_info):
    username = account_info.get('username')
    password = account_info.get('password')
    panel_url = account_info.get('panel_url')
    
    print(f"\n======================================")
    print(f"🔄 开始处理账号: {username}")
    print(f"======================================")

    try:
        # 0. 🛑 核心修复：彻底清空上一个账号的缓存，防止会话污染串号！
        print("🧹 清理浏览器会话缓存...")
        sb.open("https://bytenut.com/404") # 打开一个轻量页面以注入清除指令
        sb.delete_all_cookies()
        sb.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
        sb.sleep(1)

        # 1. 登录
        print("🔑 使用账号密码全新登录...")
        sb.open("https://bytenut.com/auth/login")
        sb.sleep(3)
        sb.type('input[placeholder="Username"]', username)
        sb.type('input[placeholder="Password"]', password)
        sb.click('button:contains("Sign In")')
        sb.sleep(8) 

        if "/auth/login" in sb.get_current_url():
            print(f"❌ 账号 {username} 密码登录失败。")
            sb.save_screenshot(f"login_failed_{username}.png")
            return f"❌ {username}: 登录失败 (账号密码错误)"

        if not panel_url:
            return f"⚠️ {username}: 缺少面板配置"

        # 2. 打开面板页面
        print(f"🎯 跳转至目标面板: {panel_url}")
        sb.open(panel_url)
        sb.sleep(4)

        js_remove_banner = """
        var btns = document.querySelectorAll('button');
        for(var i=0; i<btns.length; i++) {
            if(btns[i].innerText.includes('Consent')) {
                btns[i].click();
                break;
            }
        }
        """
        sb.execute_script(js_remove_banner)
        sb.sleep(1)

        # 3. 🛡️ 优先处理 CF 验证码
        response_field = 'input[name="cf-turnstile-response"]'
        try:
            sb.wait_for_element_present(response_field, timeout=15)
        except:
            pass

        cf_passed = False
        if sb.is_element_present(response_field):
            initial_token = sb.get_attribute(response_field, "value")
            if initial_token and len(initial_token) > 10:
                print("✅ 隐形验证自动秒过。")
                cf_passed = True
            else:
                print("🛡️ 需要点击验证，正在居中...")
                sb.execute_script(f"""
                    var ele = document.querySelector('{response_field}');
                    if(ele && ele.parentElement) {{ ele.parentElement.scrollIntoView({{block: 'center'}}); }}
                """)
                sb.sleep(2) 

                cf_iframe = "iframe[src*='cloudflare'], iframe[title*='Cloudflare'], iframe[src*='turnstile'], iframe"
                if sb.is_element_present(cf_iframe):
                    try:
                        sb.uc_gui_click_captcha()
                    except:
                        try:
                            sb.uc_click(cf_iframe)
                        except:
                            pass

                print("⏳ 正在死守人机验证 Token...")
                for _ in range(15):
                    sb.sleep(2)
                    token = sb.get_attribute(response_field, "value")
                    if token and len(token) > 10:
                        cf_passed = True
                        break

        if sb.is_element_present(response_field) and not cf_passed:
            time_str = get_remaining_time(sb)
            return f"❌ {username}: 人机验证超时 (剩余 {time_str})"

        # 4. 🎯 验证通关后，寻找并点击按钮
        extend_button_xpath = "//button[contains(., 'Extend Time')]"
        print("🔍 寻找续期按钮...")

        try:
            sb.wait_for_element_present(extend_button_xpath, timeout=10)
        except Exception:
            # 如果没找到按钮，说明刚才续期过，正在冷却中，这是好消息！
            time_str = get_remaining_time(sb)
            print(f"ℹ️ 未找到续期按钮，处于冷却健康状态。剩余时间: {time_str}")
            return f"✅ {username}: 状态健康 (剩余 {time_str}, 冷却中)"

        print("🖱️ 对续期按钮执行终极点击...")
        sb.execute_script(f"""
            var ele = document.evaluate("{extend_button_xpath}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if(ele) {{ ele.scrollIntoView({{block: 'center'}}); }}
        """)
        sb.sleep(1)
        sb.js_click(extend_button_xpath)
        
        # 等待页面刷新加载出新的时间
        print("⏳ 等待页面刷新获取最新时间...")
        sb.sleep(8) 
        time_str = get_remaining_time(sb)
        
        print(f"✅ 完美！续期请求已发送！当前剩余时间: {time_str}")
        sb.save_screenshot(f"success_final_{username}.png")
        return f"✅ <b>{username}</b>: 续期成功 (剩余 {time_str}, 120 分钟后可再续)"

    except Exception as e:
        error_screenshot = f"error_{username}_{int(time.time())}.png"
        sb.save_screenshot(error_screenshot)
        return f"❌ {username}: 执行异常 ({str(e)[:15]}...)"

def main():
    if not ACCOUNTS:
        print("未配置账号。")
        return

    report_lines = [
        "======================================",
        "📊 <b>续期结果汇总:</b>"
    ]

    with SB(uc=True, headless=False, proxy=PROXY_STR) as sb:
        for account in ACCOUNTS:
            status_line = login_and_renew(sb, account)
            # 为了美观，增加一点缩进
            report_lines.append(f"    {status_line}")
            sb.sleep(3)

    report_lines.append("======================================")
    report_lines.append("🤖 <i>所有账号处理完成！</i>")

    final_message = "\n".join(report_lines)
    send_telegram_message(final_message)

if __name__ == "__main__":
    main()
