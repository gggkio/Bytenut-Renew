import os
import json
import time
import requests
from seleniumbase import SB

# ================= 配置与环境变量解析 =================

BYTENUT_ACCOUNTS = os.environ.get('BYTENUT_ACCOUNTS', '[]')
try:
    ACCOUNTS = json.loads(BYTENUT_ACCOUNTS)
except json.JSONDecodeError:
    print("❌ BYTENUT_ACCOUNTS 解析失败！")
    ACCOUNTS = []

BYTENUT_COOKIES_ENV = os.environ.get('BYTENUT_COOKIES', '[]')
try:
    COOKIES = json.loads(BYTENUT_COOKIES_ENV)
except json.JSONDecodeError:
    print("⚠️ BYTENUT_COOKIES 解析失败或为空，将仅使用账号密码。")
    COOKIES = []

TG_BOT = os.environ.get('TG_BOT', '')
USE_PROXY = os.environ.get('GOST_PROXY') != ''
PROXY_STR = "http://127.0.0.1:8080" if USE_PROXY else None

def send_telegram_message(message):
    print(message)
    if not TG_BOT or ',' not in TG_BOT:
        return
    try:
        token, chat_id = TG_BOT.split(',', 1)
        url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
        payload = {"chat_id": chat_id.strip(), "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️ Telegram 消息发送失败: {e}")

# ================= 核心自动化逻辑 =================

def login_and_renew(sb, account_info):
    username = account_info.get('username')
    password = account_info.get('password')
    panel_url = account_info.get('panel_url') # 获取直接指定的面板URL
    
    send_telegram_message(f"🔄 开始处理账号: <b>{username}</b>")

    try:
        is_logged_in = False
        sb.open("https://bytenut.com/404") 
        sb.sleep(2)
        
        # 1. 尝试 Cookie 登录
        if COOKIES:
            print("🍪 尝试使用 Cookie 登录...")
            for cookie in COOKIES:
                clean_cookie = {
                    'name': cookie.get('name'),
                    'value': cookie.get('value'),
                    'domain': cookie.get('domain', '.bytenut.com'),
                    'path': cookie.get('path', '/')
                }
                try:
                    sb.add_cookie(clean_cookie)
                except Exception:
                    pass
            
            sb.open("https://bytenut.com/free-server")
            sb.sleep(5)
            
            # 放宽 Cookie 验证条件：只要没被跳回登录页，就算成功
            if "/auth/login" not in sb.get_current_url():
                print("✅ Cookie 登录成功！")
                is_logged_in = True
            else:
                print("⚠️ Cookie 失效或验证失败。")
                sb.delete_all_cookies() 

        # 2. 回退到密码登录
        if not is_logged_in:
            print("🔑 使用账号密码登录...")
            sb.open("https://bytenut.com/auth/login")
            sb.sleep(3)
            sb.type('input[placeholder="Username"]', username)
            sb.type('input[placeholder="Password"]', password)
            sb.click('button:contains("Sign In")')
            sb.sleep(8) # 加长等待时间，防止被 Cloudflare 盾拦截
            
            sb.open("https://bytenut.com/free-server")
            sb.sleep(5)
            
            if "/auth/login" in sb.get_current_url():
                send_telegram_message(f"❌ 账号 {username} 密码登录失败。")
                sb.save_screenshot(f"login_failed_{username}.png") # 截图留证
                return

        # 3. 确定面板 URL 列表
        panel_urls = []
        if panel_url:
            print("🎯 发现预设的面板地址，跳过抓取步骤。")
            panel_urls = [panel_url]
        else:
            print("🔍 尝试抓取面板列表...")
            panel_links = sb.find_elements('a[href*="/free-gamepanel/"]')
            panel_urls = [link.get_attribute("href") for link in panel_links]

        if not panel_urls:
            send_telegram_message(f"⚠️ 账号 {username} 未找到可续期的免费服务器。")
            sb.save_screenshot(f"no_servers_found_{username}.png") # 截图留证，方便看页面状态
            return

        # 4. 遍历并续期
        for url in panel_urls:
            server_id = url.split('/')[-1]
            sb.open(url)
            sb.sleep(6)

            if sb.is_element_visible('iframe[src*="cloudflare"]'):
                print(f"🛡️ 发现 Cloudflare 验证，尝试自动点击...")
                sb.uc_gui_click_captcha()
                sb.sleep(6)

            extend_button_selector = 'button:contains("Extend Time")'
            if sb.is_element_visible(extend_button_selector):
                sb.click(extend_button_selector)
                sb.sleep(5)
                send_telegram_message(f"✅ 账号 {username} | 服务器 <code>{server_id}</code> 续期请求已发送！")
                sb.save_screenshot(f"success_{server_id}.png") # 成功也截个图
            else:
                send_telegram_message(f"ℹ️ 账号 {username} | 服务器 <code>{server_id}</code> 暂无需续期或按钮未找到。")
                sb.save_screenshot(f"no_button_{server_id}.png")
                
    except Exception as e:
        error_screenshot = f"error_{username}_{int(time.time())}.png"
        sb.save_screenshot(error_screenshot)
        send_telegram_message(f"❌ 账号 {username} 发生异常: {str(e)[:100]}")

def main():
    if not ACCOUNTS and not COOKIES:
        print("停止运行：没有配置账号。")
        return

    with SB(uc=True, headless=False, proxy=PROXY_STR) as sb:
        for account in ACCOUNTS:
            login_and_renew(sb, account)
            sb.sleep(3)

if __name__ == "__main__":
    main()
