import os
import json
import time
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
    print(message.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')) # 控制台打印去标签版
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

# ================= 核心自动化逻辑 =================

def login_and_renew(sb, account_info):
    username = account_info.get('username')
    password = account_info.get('password')
    panel_url = account_info.get('panel_url')
    
    print(f"\n======================================")
    print(f"🔄 开始处理账号: {username}")
    print(f"======================================")

    try:
        # 1. 登录
        print("🔑 使用账号密码登录...")
        sb.open("https://bytenut.com/auth/login")
        sb.sleep(3)
        sb.type('input[placeholder="Username"]', username)
        sb.type('input[placeholder="Password"]', password)
        sb.click('button:contains("Sign In")')
        sb.sleep(8) 

        if "/auth/login" in sb.get_current_url():
            print(f"❌ 账号 {username} 密码登录失败。")
            sb.save_screenshot(f"login_failed_{username}.png")
            return f"❌ <b>{username}</b> : 登录失败 (账号密码错误或被拦截)"

        if not panel_url:
            print("⚠️ 缺少 panel_url 配置。")
            return f"⚠️ <b>{username}</b> : 缺少面板配置"

        # 2. 打开面板页面
        print(f"🎯 跳转至目标面板: {panel_url}")
        sb.open(panel_url)
        sb.sleep(4)

        print("🧹 尝试清理底部隐私横幅...")
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
        print("🔍 等待页面加载 CF 验证码底层组件...")
        response_field = 'input[name="cf-turnstile-response"]'

        try:
            sb.wait_for_element_present(response_field, timeout=20)
        except Exception:
            print("⚠️ 20秒内未发现 CF 底层组件。")

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
                    print("🖱️ 对 CF 验证框执行模拟点击...")
                    try:
                        sb.uc_gui_click_captcha()
                    except:
                        try:
                            sb.uc_click(cf_iframe)
                        except Exception as e:
                            print(f"⚠️ 点击异常: {e}")

                print("⏳ 正在死守人机验证 Token (最多 30 秒)...")
                for i in range(15):
                    sb.sleep(2)
                    token = sb.get_attribute(response_field, "value")
                    if token and len(token) > 10:
                        cf_passed = True
                        print(f"✅ 第 {i*2 + 2} 秒，验证通关！")
                        break

        if sb.is_element_present(response_field) and not cf_passed:
            print(f"❌ 人机验证超时。")
            sb.save_screenshot(f"cf_fail_{username}.png")
            return f"❌ <b>{username}</b> : CF人机验证失败/超时"

        # 4. 🎯 验证通关后，寻找并点击按钮
        extend_button_xpath = "//button[contains(., 'Extend Time')]"
        print("🔍 验证已完成，寻找续期按钮...")

        try:
            sb.wait_for_element_present(extend_button_xpath, timeout=10)
        except Exception:
            print(f"❌ 验证已过，未找到续期按钮。")
            sb.save_screenshot(f"no_btn_{username}.png")
            return f"❌ <b>{username}</b> : 未找到续期按钮 (可能冷却中)"

        print("🖱️ 对续期按钮执行终极点击...")
        sb.execute_script(f"""
            var ele = document.evaluate("{extend_button_xpath}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if(ele) {{ ele.scrollIntoView({{block: 'center'}}); }}
        """)
        sb.sleep(1)
        sb.js_click(extend_button_xpath)
        sb.sleep(6)
        
        print(f"✅ 完美！续期请求已发送！")
        sb.save_screenshot(f"success_final_{username}.png")
        return f"✅ <b>{username}</b> : 续期成功！"

    except Exception as e:
        error_screenshot = f"error_{username}_{int(time.time())}.png"
        sb.save_screenshot(error_screenshot)
        print(f"❌ 异常: {str(e)[:100]}")
        return f"❌ <b>{username}</b> : 执行异常 ({str(e)[:20]}...)"

def main():
    if not ACCOUNTS:
        print("未配置账号。")
        return

    # 初始化汇总报告的头部
    report_lines = [
        "<b>🤖 Bytenut 批量续期报告</b>",
        "━━━━━━━━━━━━━━━━━━"
    ]

    with SB(uc=True, headless=False, proxy=PROXY_STR) as sb:
        for account in ACCOUNTS:
            # 拿到每个账号的单行状态字符串
            status_line = login_and_renew(sb, account)
            report_lines.append(status_line)
            sb.sleep(3) # 账号间缓冲

    # 报告尾部追加当前 UTC 时间
    report_lines.append("━━━━━━━━━━━━━━━━━━")
    now_utc = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    report_lines.append(f"⏱ <i>执行时间: {now_utc}</i>")

    # 拼接并发送最终报告
    final_message = "\n".join(report_lines)
    send_telegram_message(final_message)

if __name__ == "__main__":
    main()
