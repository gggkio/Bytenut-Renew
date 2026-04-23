import os
import json
import time
import requests
from seleniumbase import SB

# ================= 配置与环境变量解析 =================

# 账号密码配置
BYTENUT_ACCOUNTS = os.environ.get('BYTENUT_ACCOUNTS', '[]')
try:
    ACCOUNTS = json.loads(BYTENUT_ACCOUNTS)
except json.JSONDecodeError:
    print("❌ BYTENUT_ACCOUNTS 解析失败！")
    ACCOUNTS = []

# Cookie 配置 (优先使用)
BYTENUT_COOKIES_ENV = os.environ.get('BYTENUT_COOKIES', '[]')
try:
    COOKIES = json.loads(BYTENUT_COOKIES_ENV)
except json.JSONDecodeError:
    print("⚠️ BYTENUT_COOKIES 解析失败或为空，将仅使用账号密码。")
    COOKIES = []

TG_BOT = os.environ.get('TG_BOT', '')
USE_PROXY = os.environ.get('GOST_PROXY') != ''
PROXY_STR = "http://127.0.0.1:8080" if USE_PROXY else None

# ================= 辅助函数 =================

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
    
    send_telegram_message(f"🔄 开始处理账号: <b>{username}</b>")

    try:
        # 1. 优先尝试 Cookie 登录
        is_logged_in = False
        
        # 必须先访问目标域名才能注入对应域名的 Cookie
        sb.open("https://bytenut.com/404") # 访问一个轻量级页面建立域名上下文
        sb.sleep(2)
        
        if COOKIES:
            print("🍪 尝试使用 Cookie 登录...")
            # 注入 Cookie
            for cookie in COOKIES:
                # Selenium 对 cookie 字典格式有严格要求，清理不必要的字段
                clean_cookie = {
                    'name': cookie.get('name'),
                    'value': cookie.get('value'),
                    'domain': cookie.get('domain', '.bytenut.com'),
                    'path': cookie.get('path', '/')
                }
                try:
                    sb.add_cookie(clean_cookie)
                except Exception as e:
                    print(f"忽略无效的 Cookie {clean_cookie.get('name')}: {e}")
            
            # 刷新或跳转到目标页验证是否登录成功
            sb.open("https://bytenut.com/free-server")
            sb.sleep(4)
            
            # 检查页面上是否存在登录框或特定的未登录标识，以此判断 Cookie 是否有效
            # 这里假设如果 URL 没跳回 /auth/login，且能看到面板链接，就是成功了
            if "/auth/login" not in sb.get_current_url() and sb.is_element_visible('a[href*="/free-gamepanel/"]'):
                print("✅ Cookie 登录成功！")
                is_logged_in = True
            else:
                print("⚠️ Cookie 失效或验证失败。")
                # 清除失效的 Cookie，准备密码登录
                sb.delete_all_cookies() 

        # 2. 如果 Cookie 无效或未配置，回退到密码登录
        if not is_logged_in:
            if not username or not password:
                send_telegram_message("❌ 无效的 Cookie 且缺少账号密码配置，无法登录。")
                return

            print("🔑 使用账号密码登录...")
            sb.open("https://bytenut.com/auth/login")
            sb.sleep(3)
            sb.type('input[placeholder="Username"]', username)
            sb.type('input[placeholder="Password"]', password)
            sb.click('button:contains("Sign In")')
            sb.sleep(6) # 等待登录和 Cloudflare 盾
            
            sb.open("https://bytenut.com/free-server")
            sb.sleep(4)

        # 3. 抓取并遍历服务器进行续期
        panel_links = sb.find_elements('a[href*="/free-gamepanel/"]')
        panel_urls = [link.get_attribute("href") for link in panel_links]

        if not panel_urls:
            send_telegram_message(f"⚠️ 账号 {username} 未找到可续期的免费服务器。")
            return

        for url in panel_urls:
            server_id = url.split('/')[-1]
            sb.open(url)
            sb.sleep(6)

            # 处理可能出现的 Cloudflare Turnstile
            if sb.is_element_visible('iframe[src*="cloudflare"]'):
                print(f"🛡️ 发现 Cloudflare 验证，尝试自动点击...")
                sb.uc_gui_click_captcha()
                sb.sleep(5)

            # 查找并点击续期按钮
            extend_button_selector = 'button:contains("Extend Time")'
            if sb.is_element_visible(extend_button_selector):
                sb.click(extend_button_selector)
                sb.sleep(4)
                send_telegram_message(f"✅ 账号 {username} | 服务器 <code>{server_id}</code> 续期请求已发送！")
            else:
                send_telegram_message(f"ℹ️ 账号 {username} | 服务器 <code>{server_id}</code> 暂无需续期。")
                
    except Exception as e:
        error_screenshot = f"error_{username.replace('@', '_')}_{int(time.time())}.png"
        sb.save_screenshot(error_screenshot)
        send_telegram_message(f"❌ 账号 {username} 发生异常: {str(e)[:100]}...\n📸 截图已保存以供排查。")

def main():
    if not ACCOUNTS and not COOKIES:
        print("停止运行：没有配置账号，也没有配置 Cookie。")
        return

    # 初始化 SeleniumBase
    with SB(uc=True, headless=False, proxy=PROXY_STR) as sb:
        # 如果你只有一个账号的 Cookie，这段逻辑默认它对应 ACCOUNTS 列表里的第一个账号
        # 如果需要多账号多 Cookie 映射，可以考虑把 Cookie 放进 ACCOUNTS 的 JSON 结构里
        for account in ACCOUNTS:
            login_and_renew(sb, account)
            sb.sleep(3)

if __name__ == "__main__":
    main()
