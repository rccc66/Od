import re
import random
import string
import time
import logging
import requests
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
# 浏览器驱动 (Chrome 145 兼容)
# ==========================================
def create_options():
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--lang=zh-CN,zh;q=0.9')
    return options

def setup_driver():
    driver = None
    try:
        logger.info("[Driver] 尝试启动浏览器 (Target: Chrome 145)...")
        driver = uc.Chrome(options=create_options(), version_main=145)
    except Exception:
        logger.info("[Driver] 尝试自动版本启动...")
        driver = uc.Chrome(options=create_options())
    if driver:
        driver.implicitly_wait(5)
        logger.info("[Driver] 浏览器启动成功")
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
                logger.info(f"[MailAPI] 成功: {self.email}")
                return self.email
        except Exception as e:
            logger.error(f"[MailAPI] 错误: {e}")
        return None

    def wait_for_code(self, retry=25):
        logger.info("[MailAPI] 等待 OpenDoor 验证码...")
        headers = {"Authorization": f"Bearer {self.token}"}
        
        for i in range(retry):
            try:
                r = requests.get(f"{self.base_url}/messages", headers=headers, timeout=10)
                messages = r.json().get('hydra:member', [])
                
                if messages:
                    # 获取第一封信
                    msg = messages[0]
                    msg_id = msg['id']
                    
                    # 获取详情
                    r_detail = requests.get(f"{self.base_url}/messages/{msg_id}", headers=headers, timeout=10)
                    data = r_detail.json()
                    
                    # 拼接所有内容以防遗漏
                    html_body = "".join(data.get('html', []))
                    text_body = data.get('text', '') or data.get('intro', '') or ""
                    full_content = html_body + text_body

                    # 1. 优先策略：匹配 <strong>4c74f4</strong>
                    match = re.search(r'<strong>([a-zA-Z0-9]{6})</strong>', full_content)
                    if match:
                        code = match.group(1)
                        logger.info(f"[MailAPI] 🎯 从Strong标签提取验证码: {code}")
                        return code

                    # 2. 备用策略：匹配 "验证码为: xxxxxx"
                    if not match:
                        match = re.search(r'验证码.*[:：]\s*([a-zA-Z0-9]{6})', text_body)
                        if match:
                            code = match.group(1)
                            # 排除年份误判
                            if not code.startswith("202"):
                                logger.info(f"[MailAPI] 🎯 文本提取验证码: {code}")
                                return code

            except Exception as e:
                pass # 忽略网络错误继续重试
            
            time.sleep(3)
        return None

# ==========================================
# 核心：确保 URL 正确的加载逻辑
# ==========================================
def load_correct_page(driver, wait):
    """循环加载，确保URL正确且邮箱框出现"""
    max_retries = 3
    
    for i in range(max_retries):
        logger.info(f"[页面] 加载第 {i+1} 次，强制访问: {TARGET_URL}")
        
        # 关键修改：每次都用 .get() 强制带参数访问，绝不使用 .refresh()
        driver.get(TARGET_URL)
        
        # 等待页面基础加载
        time.sleep(4)
        
        # 检查 URL 是否丢失了 aff 参数 (防止网站自动跳转洗掉了参数)
        current_url = driver.current_url
        if AFF_CODE not in current_url:
            logger.warning(f"[警告] 邀请码丢失！当前: {current_url}")
            logger.warning("[修正] 正在强制重载带参链接...")
            continue # 跳过本次检查，直接下一轮循环重新加载

        # 检查邮箱框
        try:
            # 5秒内没出来就认为加载不全，重新来
            wait_short = WebDriverWait(driver, 5)
            wait_short.until(EC.visibility_of_element_located((By.ID, "email")))
            logger.info("[页面] 邮箱框就绪，且URL正确")
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

    try:
        driver = setup_driver()
    except:
        return

    wait = WebDriverWait(driver, 20)

    try:
        # 1. 严格模式加载页面
        if not load_correct_page(driver, wait):
            logger.error("[致命] 无法加载正确的注册页面或邮箱框")
            driver.save_screenshot("error_url_check.png")
            return

        # 再次确认一下 URL (双保险)
        if AFF_CODE not in driver.current_url:
            logger.error(f"[失败] 最终URL不包含邀请码: {driver.current_url}")
            return

        # 2. 填写表单
        logger.info("[表单] 填写信息...")
        wait.until(EC.visibility_of_element_located((By.ID, "username"))).send_keys(username)
        driver.find_element(By.ID, "password").send_keys(password)
        driver.find_element(By.ID, "password2").send_keys(password)
        driver.find_element(By.ID, "email").send_keys(email)

        # 3. 点击发送验证码
        try:
            # 精准定位
            btn_xpath = "//div[contains(@class, 'semi-form-field-email')]//button"
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, btn_xpath)))
            driver.execute_script("arguments[0].click();", btn)
            logger.info("[交互] 已点击发送")
        except:
            logger.error("找不到发送按钮")
            driver.save_screenshot("error_btn.png")
            return

        # 4. 接收验证码
        code = mail_bot.wait_for_code()
        if not code:
            logger.error("验证码获取超时")
            return

        # 5. 提交注册
        driver.find_element(By.ID, "verification_code").send_keys(code)
        time.sleep(1.5) # 给前端JS校验留时间
        
        logger.info("[交互] 点击注册")
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        
        try:
            submit_btn.click()
        except:
            driver.execute_script("arguments[0].click();", submit_btn)
        
        # 6. 等待跳转成功
        time.sleep(10)
        
        if "register" not in driver.current_url:
            logger.info("🎉🎉🎉 注册成功！页面已跳转 🎉🎉🎉")
            with open("accounts.txt", "a") as f:
                f.write(f"{username}|{password}|{email}\n")
        else:
            logger.warning("页面未跳转，可能失败")
            driver.save_screenshot("final_fail.png")

    except Exception as e:
        logger.error(f"异常: {e}")
        driver.save_screenshot("error_crash.png")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
