import re
import random
import string
import time
import logging
import requests
import subprocess
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://ai.opendoor.cn"
AFF_CODE = "GnSy"
TARGET_URL = f"{BASE_URL}/register?aff={AFF_CODE}"

# ==========================================
# 工具函数
# ==========================================
def random_str(length, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choices(chars, k=length))

def gen_password(length=12):
    chars = string.ascii_letters + string.digits + "!@#$%"
    while True:
        pwd = ''.join(random.choices(chars, k=length))
        if (re.search(r'[A-Z]', pwd) and re.search(r'[a-z]', pwd)
                and re.search(r'\d', pwd) and re.search(r'[!@#$%]', pwd)):
            return pwd

# ==========================================
# 浏览器驱动 (优化 GitHub Actions 兼容性)
# ==========================================
def create_options():
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-setuid-sandbox') 
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--lang=zh-CN,zh;q=0.9')
    return options

def get_chrome_major_version():
    """⚡ 自动获取系统安装的 Chrome 真实主版本号"""
    try:
        result = subprocess.run(['google-chrome', '--version'], capture_output=True, text=True)
        version_str = result.stdout.strip().split()[-1]
        major_version = int(version_str.split('.')[0])
        logger.info(f"[Driver] ✅ 侦测到系统真实 Chrome 版本: {major_version}")
        return major_version
    except Exception as e:
        logger.warning(f"[Driver] ⚠️ 版本侦测失败，将使用默认行为: {e}")
        return None

def setup_driver():
    driver = None
    logger.info("[Driver] 尝试启动浏览器...")
    try:
        chrome_ver = get_chrome_major_version()
        driver = uc.Chrome(options=create_options(), version_main=chrome_ver)
        driver.implicitly_wait(5)
        logger.info("[Driver] ✅ 浏览器启动成功")
    except Exception as e:
        logger.error(f"[Driver] ❌ 启动失败: {e}")
    return driver

# ==========================================
# 邮箱 API 类 (精准匹配 4c74f4 格式)
# ==========================================
class MailTM:
    def __init__(self):
        self.base_url = "https://api.mail.tm"
        self.token = None
        self.email = None
        self.password = gen_password(10)

    def get_account(self):
        logger.info("[MailAPI] 申请邮箱中...")
        try:
            domain_res = requests.get(f"{self.base_url}/domains", timeout=15)
            domains = domain_res.json().get('hydra:member', [])
            if not domains: return None
            
            domain = domains[0]['domain']
            self.email = f"{random_str(10)}@{domain}"
            payload = {"address": self.email, "password": self.password}
            
            requests.post(f"{self.base_url}/accounts", json=payload, timeout=15)
            token_res = requests.post(f"{self.base_url}/token", json=payload, timeout=15)
            
            if token_res.status_code == 200:
                self.token = token_res.json()['token']
                logger.info(f"[MailAPI] ✅ 成功: {self.email}")
                return self.email
        except Exception as e:
            logger.error(f"[MailAPI] ❌ 错误: {e}")
        return None

    def wait_for_code(self, retry=25):
        logger.info("[MailAPI] 📅 等待 OpenDoor 验证码...")
        headers = {"Authorization": f"Bearer {self.token}"}
        
        for i in range(retry):
            try:
                r = requests.get(f"{self.base_url}/messages", headers=headers, timeout=10)
                messages = r.json().get('hydra:member', [])
                
                if messages:
                    msg = messages[0]
                    msg_id = msg['id']
                    
                    r_detail = requests.get(f"{self.base_url}/messages/{msg_id}", headers=headers, timeout=10)
                    data = r_detail.json()
                    
                    html_body = "".join(data.get('html', []))
                    text_body = data.get('text', '') or data.get('intro', '') or ""
                    full_content = html_body + text_body

                    match = re.search(r'<strong>([a-zA-Z0-9]{6})</strong>', full_content)
                    if match:
                        code = match.group(1)
                        logger.info(f"[MailAPI] 🎯 从Strong标签提取验证码: {code}")
                        return code

                    if not match:
                        match = re.search(r'验证码.*[:：]\s*([a-zA-Z0-9]{6})', text_body)
                        if match:
                            code = match.group(1)
                            if not code.startswith("202"):
                                logger.info(f"[MailAPI] 🎯 文本提取验证码: {code}")
                                return code

            except Exception as e:
                pass 
            
            time.sleep(3)
        return None

# ==========================================
# 核心：确保 URL 正确的加载逻辑
# ==========================================
def load_correct_page(driver, wait):
    max_retries = 3
    
    for i in range(max_retries):
        logger.info(f"[页面] 加载第 {i+1} 次，强制访问: {TARGET_URL}")
        
        driver.get(TARGET_URL)
        time.sleep(4)
        
        current_url = driver.current_url
        if AFF_CODE not in current_url:
            logger.warning(f"[警告] 邀请码丢失！当前: {current_url}")
            logger.warning("[修正] 正在强制重载带参链接...")
            continue 

        try:
            wait_short = WebDriverWait(driver, 5)
            wait_short.until(EC.visibility_of_element_located((By.ID, "email")))
            logger.info("[页面] ✅ 邮箱框就绪，且URL正确")
            return True
        except TimeoutException:
            logger.warning(f"[页面] 邮箱框未显示，准备重载...")
    
    return False

# ==========================================
# 主程序
# ==========================================
def main():
    username = random_str(8)
    password = gen_password()
    
    mail_bot = MailTM()
    email = mail_bot.get_account()
    if not email: return

    logger.info(f"========== 注册任务 ==========")
    logger.info(f"用户: {username}")
    logger.info(f"密码: {password}")
    logger.info(f"邮箱: {email}")

    driver = setup_driver()
    if not driver:
        logger.error("❌ WebDriver 初始化彻底失败，任务终止")
        return

    wait = WebDriverWait(driver, 20)

    try:
        if not load_correct_page(driver, wait):
            logger.error("[致命] ❌ 无法加载正确的注册页面或邮箱框")
            driver.save_screenshot("error_url_check.png")
            return

        if AFF_CODE not in driver.current_url:
            logger.error(f"[失败] ❌ 最终URL不包含邀请码: {driver.current_url}")
            return

        logger.info("[表单] 填写信息...")
        wait.until(EC.visibility_of_element_located((By.ID, "username"))).send_keys(username)
        driver.find_element(By.ID, "password").send_keys(password)
        driver.find_element(By.ID, "password2").send_keys(password)
        driver.find_element(By.ID, "email").send_keys(email)

        try:
            btn_xpath = "//div[contains(@class, 'semi-form-field-email')]//button"
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, btn_xpath)))
            driver.execute_script("arguments[0].click();", btn)
            logger.info("[交互] ⚡ 已点击发送")
        except:
            logger.error("❌ 找不到发送按钮")
            driver.save_screenshot("error_btn.png")
            return

        code = mail_bot.wait_for_code()
        if not code:
            logger.error("❌ 验证码获取超时")
            return

        driver.find_element(By.ID, "verification_code").send_keys(code)
        time.sleep(1.5) 
        
        logger.info("[交互] ⚡ 点击注册")
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        
        try:
            submit_btn.click()
        except:
            driver.execute_script("arguments[0].click();", submit_btn)
        
        time.sleep(10)
        
        if "register" not in driver.current_url:
            logger.info("🎉🎉🎉 注册成功！页面已跳转 🎉🎉🎉")
            with open("accounts.txt", "a") as f:
                f.write(f"{username}|{password}|{email}\n")
        else:
            logger.warning("❌ 页面未跳转，可能失败")
            driver.save_screenshot("final_fail.png")

    except Exception as e:
        logger.error(f"异常: {e}")
        try:
            driver.save_screenshot("error_crash.png")
        except:
            pass
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
