import os
import platform
import json
import sys
from colorama import Fore, Style
from enum import Enum
from typing import Optional, Dict, Any, Tuple

from exit_cursor import ExitCursor
import go_cursor_help
import patch_cursor_get_machine_id
from reset_machine import MachineIDResetter

os.environ["PYTHONVERBOSE"] = "0"
os.environ["PYINSTALLER_VERBOSE"] = "0"

import time
import random
from cursor_auth_manager import CursorAuthManager
import os
from src.utils.logger import logging
from src.utils.browser_utils import BrowserManager
from get_email_code import EmailVerificationHandler
from logo import print_logo
from src.utils.config import Config
import hashlib
import uuid
import base64
import requests


# 定义 EMOJI 字典
EMOJI = {"ERROR": "❌", "WARNING": "⚠️", "INFO": "ℹ️"}


class VerificationStatus(Enum):
    """验证状态枚举"""
    SIGN_UP = "@name=first_name"
    PASSWORD_PAGE = "@name=password"
    CAPTCHA_PAGE = "@data-index=0"
    ACCOUNT_SETTINGS = "Account Settings"
    TOKEN_REFRESH = "You're currently logged in as:"


class TurnstileError(Exception):
    """Turnstile 验证相关异常"""

    pass


def save_screenshot(tab, stage: str, timestamp: bool = True) -> None:
    """
    保存页面截图

    Args:
        tab: 浏览器标签页对象
        stage: 截图阶段标识
        timestamp: 是否添加时间戳
    """
    try:
        # 创建 screenshots 目录
        screenshot_dir = "screenshots"
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)

        # 生成文件名
        if timestamp:
            filename = f"turnstile_{stage}_{int(time.time())}.png"
        else:
            filename = f"turnstile_{stage}.png"

        filepath = os.path.join(screenshot_dir, filename)

        # 保存截图
        tab.get_screenshot(filepath)
        logging.debug(f"截图已保存: {filepath}")
    except Exception as e:
        logging.warning(f"截图保存失败: {str(e)}")


def check_verification_success(tab, default_status=None) -> Optional[VerificationStatus]:
    """
    检查验证是否成功

    Returns:
        VerificationStatus: 验证成功时返回对应状态，失败返回 None
    """
    if default_status:
        if tab.ele(default_status.value):
            logging.info(f"验证成功 - 已到达{default_status.name}页面")
            return default_status
        else:
            return None
    for status in VerificationStatus:
        if tab.ele(status.value):
            logging.info(f"验证成功 - 已到达{status.name}页面")
            return status
    return None


def handle_turnstile(tab, max_retries: int = 2, retry_interval: tuple = (1, 2)) -> bool:
    """
    处理 Turnstile 验证

    Args:
        tab: 浏览器标签页对象
        max_retries: 最大重试次数
        retry_interval: 重试间隔时间范围(最小值, 最大值)

    Returns:
        bool: 验证是否成功

    Raises:
        TurnstileError: 验证过程中出现异常
    """
    logging.info("正在检测 Turnstile 验证...")
    save_screenshot(tab, "start")

    retry_count = 0

    try:
        while retry_count < max_retries:
            retry_count += 1
            logging.debug(f"第 {retry_count} 次尝试验证")

            try:
                # 定位验证框元素
                challenge_check = (
                    tab.ele("@id=cf-turnstile", timeout=2)
                    .child()
                    .shadow_root.ele("tag:iframe")
                    .ele("tag:body")
                    .sr("tag:input")
                )

                if challenge_check:
                    logging.info("检测到 Turnstile 验证框，开始处理...")
                    # 随机延时后点击验证
                    time.sleep(random.uniform(1, 3))
                    challenge_check.click()
                    time.sleep(2)

                    # 保存验证后的截图
                    save_screenshot(tab, "clicked")

                    # 检查验证结果
                    if check_verification_success(tab):
                        logging.info("Turnstile 验证通过")
                        save_screenshot(tab, "success")
                        return True

            except Exception as e:
                logging.debug(f"当前尝试未成功: {str(e)}")

            # 检查是否已经验证成功
            if check_verification_success(tab):
                return True

            # 随机延时后继续下一次尝试
            time.sleep(random.uniform(*retry_interval))

        # 超出最大重试次数
        logging.error(f"验证失败 - 已达到最大重试次数 {max_retries}")
        logging.error(
            "请前往开源项目查看更多信息：https://github.com/chengazhen/cursor-auto-free"
        )
        save_screenshot(tab, "failed")
        return False

    except Exception as e:
        error_msg = f"Turnstile 验证过程发生异常: {str(e)}"
        logging.error(error_msg)
        save_screenshot(tab, "error")
        raise TurnstileError(error_msg)


def get_cursor_session_token(tab=None, max_attempts=3, retry_interval=2) -> Tuple[Optional[str], Optional[str]]:
    """
    获取Cursor会话令牌

    Args:
        tab: 浏览器标签对象
        max_attempts: 最大尝试次数
        retry_interval: 重试间隔(秒)

    Returns:
        Tuple[Optional[str], Optional[str]]: (accessToken, refreshToken)
    """

    params = generate_auth_params()
    url = f"https://www.cursor.com/cn/loginDeepControl?challenge={params['n']}&uuid={params['r']}&mode=login"
    tab.get(url)

    attempts = 0

    while attempts < max_attempts:
        # 检查是否到达登录界面
        status = check_verification_success(tab, VerificationStatus.TOKEN_REFRESH)
        if status:
            break

        attempts += 1

        if attempts < max_attempts:
            time.sleep(retry_interval)

    time.sleep(2)

    # 使用精确的CSS选择器在Python中查找元素并点击
    tab.run_js("""
           try {
               const button = document.querySelectorAll(".min-h-screen")[1].querySelectorAll(".gap-4")[1].querySelectorAll("button")[1];
               if (button) {
                   button.click();
                   return true;
               } else {
                   return false;
               }
           } catch (e) {
               console.error("选择器错误:", e);
               return false;
           }
       """)

    _, access_token, refresh_token = poll_for_login_result(params["r"], params["s"])

    # 更新实例变量
    if access_token and refresh_token:
        return access_token, refresh_token

    return None, None


def generate_auth_params():
    # 1. 生成 code_verifier (t) - 32字节随机数
    t = os.urandom(32)  # 等效于 JS 的 crypto.getRandomValues(new Uint8Array(32))

    # 2. 生成 s: 对 t 进行 Base64 URL 安全编码
    def tb(data):
        # Base64 URL 安全编码（替换 +/ 为 -_，去除末尾的 =）
        return base64.urlsafe_b64encode(data).decode().rstrip('=')

    s = tb(t)  # 对应 JS 的 this.tb(t)

    # 3. 生成 n: 对 s 进行 SHA-256 哈希 + Base64 URL 编码
    def ub(s_str):
        # 等效于 JS 的 TextEncoder().encode(s) + SHA-256
        return hashlib.sha256(s_str.encode()).digest()

    hashed = ub(s)
    n = tb(hashed)  # 对应 JS 的 this.tb(new Uint8Array(hashed))

    # 4. 生成 r: UUID v4
    r = str(uuid.uuid4())  # 对应 JS 的 $t()

    return {
        "t": t.hex(),  # 原始字节转十六进制字符串（方便查看）
        "s": s,
        "n": n,
        "r": r
    }

def poll_for_login_result(uuid: str, challenge: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    轮询获取登录结果

    Args:
        uuid: 身份验证UUID
        challenge: 验证挑战码

    Returns:
        Tuple[Optional[str], Optional[str], Optional[str]]: (authId, accessToken, refreshToken)
    """
    poll_url = f"https://api2.cursor.sh/auth/poll?uuid={uuid}&verifier={challenge}"
    headers = {
        "Content-Type": "application/json"
    }
    max_attempts = 30
    attempt = 0

    while attempt < max_attempts:
        logging.info("polling_login_result")
        try:
            response = requests.get(poll_url, headers=headers)

            if response.status_code == 404:
                logging.info("login_not_completed")
            elif response.status_code == 200:
                data = response.json()

                if "authId" in data and "accessToken" in data and "refreshToken" in data:
                    logging.info("login_successful")
                    logging.debug(f"Auth ID: {data['authId']}")
                    logging.debug(f"Access Token: {data['accessToken'][:10]}...")
                    logging.debug(f"Refresh Token: {data['refreshToken'][:10]}...")
                    return data['authId'], data['accessToken'], data['refreshToken']

        except Exception as e:
            logging.error(f"Error during polling: {e}")

        attempt += 1
        time.sleep(2)  # 每 2 秒轮询一次

    if attempt >= max_attempts:
        logging.error("polling_timed_out")

    return None, None, None

def update_cursor_auth(email=None, access_token=None, refresh_token=None):
    """
    更新Cursor的认证信息的便捷函数
    """
    auth_manager = CursorAuthManager()
    return auth_manager.update_auth(email, access_token, refresh_token)


def sign_up_account(browser, tab):
    logging.info("=== 开始注册账号流程 ===")
    logging.info(f"正在访问注册页面: {sign_up_url}")
    tab.get(sign_up_url)

    try:
        if tab.ele("@name=first_name"):
            logging.info("正在填写个人信息...")
            tab.actions.click("@name=first_name").input(first_name)
            logging.info(f"已输入名字: {first_name}")
            time.sleep(random.uniform(1, 3))

            tab.actions.click("@name=last_name").input(last_name)
            logging.info(f"已输入姓氏: {last_name}")
            time.sleep(random.uniform(1, 3))

            tab.actions.click("@name=email").input(account)
            logging.info(f"已输入邮箱: {account}")
            time.sleep(random.uniform(1, 3))

            logging.info("提交个人信息...")
            tab.actions.click("@type=submit")

    except Exception as e:
        logging.error(f"注册页面访问失败: {str(e)}")
        return False

    handle_turnstile(tab)

    try:
        if tab.ele("@name=password"):
            logging.info("正在设置密码...")
            tab.ele("@name=password").input(password)
            time.sleep(random.uniform(1, 3))

            logging.info("提交密码...")
            tab.ele("@type=submit").click()
            logging.info("密码设置完成，等待系统响应...")

    except Exception as e:
        logging.error(f"密码设置失败: {str(e)}")
        return False

    if tab.ele("This email is not available."):
        logging.error("注册失败：邮箱已被使用")
        # 跳转到登录页 尝试登录一次
        logging.info("跳转到登录页 尝试登录一次")
        tab.get(login_url)
        if tab.ele("@name=email"):
            tab.actions.click("@name=email").input(account)
            logging.info(f"已输入邮箱: {account}")
            time.sleep(random.uniform(1, 3))
            tab.actions.click("@type=submit")
            
            handle_turnstile(tab)
            try:
                if tab.ele("@name=password"):
                    logging.info("正在设置密码...")
                    tab.ele("@name=password").input(password)
                    time.sleep(random.uniform(1, 3))

                    logging.info("提交密码...")
                    tab.ele("@type=submit").click()
                    logging.info("密码设置完成，等待系统响应...")
            except Exception as e:
                logging.error(f"密码设置失败: {str(e)}")
                return False

    handle_turnstile(tab)

    while True:
        try:
            if tab.ele("Account Settings"):
                logging.info("注册成功 - 已进入账户设置页面")
                break
            if tab.ele("@data-index=0"):
                logging.info("正在获取邮箱验证码...")
                code = email_handler.get_verification_code()
                if not code:
                    logging.error("获取验证码失败")
                    return False

                logging.info(f"成功获取验证码: {code}")
                logging.info("正在输入验证码...")
                i = 0
                for digit in code:
                    tab.ele(f"@data-index={i}").input(digit)
                    time.sleep(random.uniform(0.1, 0.3))
                    i += 1
                logging.info("验证码输入完成")
                break
        except Exception as e:
            logging.error(f"验证码处理过程出错: {str(e)}")

    handle_turnstile(tab)
    wait_time = random.randint(3, 6)
    for i in range(wait_time):
        logging.info(f"等待系统处理中... 剩余 {wait_time-i} 秒")
        time.sleep(1)

    logging.info("正在获取账户信息...")
    tab.get(settings_url)
    try:
        usage_selector = (
            "css:div.col-span-2 > div > div > div > div > "
            "div:nth-child(1) > div.flex.items-center.justify-between.gap-2 > "
            "span.font-mono.text-sm\\/\\[0\\.875rem\\]"
        )
        usage_ele = tab.ele(usage_selector)
        if usage_ele:
            usage_info = usage_ele.text
            total_usage = usage_info.split("/")[-1].strip()
            logging.info(f"账户可用额度上限: {total_usage}")
            logging.info(
                "请前往开源项目查看更多信息：https://github.com/chengazhen/cursor-auto-free"
            )
    except Exception as e:
        logging.error(f"获取账户额度信息失败: {str(e)}")

    logging.info("\n=== 注册完成 ===")
    account_info = f"Cursor 账号信息:\n邮箱: {account}\n密码: {password}"
    logging.info(account_info)
    time.sleep(5)
    return True


class EmailGenerator:
    def __init__(
        self,
        password="".join(
            random.choices(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*",
                k=12,
            )
        ),
    ):
        configInstance = Config()
        configInstance.print_config()
        self.domain = configInstance.get_domain()
        self.names = self.load_names()
        self.default_password = password
        self.default_first_name = self.generate_random_name()
        self.default_last_name = self.generate_random_name()
        if configInstance.get_imap() != False:
            self.temp_mail = "null"
            self.default_imap_user = configInstance.get_imap()['imap_user']
            self.default_imap_pass = configInstance.get_imap()['imap_pass']

    def load_names(self):
        with open("names-dataset.txt", "r") as file:
            return file.read().split()

    def generate_random_name(self):
        """生成随机用户名"""
        return random.choice(self.names)

    def generate_email(self, length=4):
        """生成随机邮箱地址"""
        if self.temp_mail == "null":
            return f"{self.default_imap_user}"  #
        length = random.randint(0, length)  # 生成0到length之间的随机整数
        timestamp = str(int(time.time()))[-length:]  # 使用时间戳后length位
        return f"{self.default_first_name}{timestamp}@{self.domain}"  #

    def generate_password(self):
        """生成随机密码"""
        if self.temp_mail == "null":
            return f"{self.default_imap_pass}"  #
        return self.default_password

    def get_account_info(self):
        """获取完整的账号信息"""
        return {
            "email": self.generate_email(),
            "password": self.generate_password(),
            "first_name": self.default_first_name,
            "last_name": self.default_last_name,
        }


def get_user_agent():
    """获取user_agent"""
    try:
        # 使用JavaScript获取user agent
        browser_manager = BrowserManager()
        browser = browser_manager.init_browser()
        user_agent = browser.latest_tab.run_js("return navigator.userAgent")
        browser_manager.quit()
        return user_agent
    except Exception as e:
        logging.error(f"获取user agent失败: {str(e)}")
        return None


def check_cursor_version():
    """检查cursor版本"""
    pkg_path, main_path = patch_cursor_get_machine_id.get_cursor_paths()
    with open(pkg_path, "r", encoding="utf-8") as f:
        version = json.load(f)["version"]
    return patch_cursor_get_machine_id.version_check(version, min_version="0.45.0")


def reset_machine_id(greater_than_0_45):
    if greater_than_0_45:
        # 提示请手动执行脚本 https://github.com/chengazhen/cursor-auto-free/blob/main/patch_cursor_get_machine_id.py
        go_cursor_help.go_cursor_help()
    else:
        MachineIDResetter().reset_machine_ids()


def print_end_message():
    logging.info("\n\n\n\n\n")
    logging.info("=" * 30)
    logging.info("所有操作已完成")
    logging.info("\n=== 获取更多信息 ===")
    logging.info("📺 B站UP主: 想回家的前端")
    logging.info("🔥 公众号: code 未来")
    logging.info("=" * 30)
    logging.info(
        "请前往开源项目查看更多信息：https://github.com/chengazhen/cursor-auto-free"
    )


if __name__ == "__main__":
    print_logo()
    greater_than_0_45 = check_cursor_version()
    browser_manager = None
    try:
        logging.info("\n=== 初始化程序 ===")
        ExitCursor()

        # 提示用户选择操作模式
        print("\n请选择操作模式:")
        print("1. 仅重置机器码")
        print("2. 完整注册流程")

        while True:
            try:
                choice = int(input("请输入选项 (1 或 2): ").strip())
                if choice in [1, 2]:
                    break
                else:
                    print("无效的选项,请重新输入")
            except ValueError:
                print("请输入有效的数字")

        if choice == 1:
            # 仅执行重置机器码
            reset_machine_id(greater_than_0_45)
            logging.info("机器码重置完成")
            print_end_message()
            sys.exit(0)

        logging.info("正在初始化浏览器...")

        # 获取user_agent
        user_agent = get_user_agent()
        if not user_agent:
            logging.error("获取user agent失败，使用默认值")
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        # 剔除user_agent中的"HeadlessChrome"
        user_agent = user_agent.replace("HeadlessChrome", "Chrome")

        browser_manager = BrowserManager()
        browser = browser_manager.init_browser(user_agent)

        # 获取并打印浏览器的user-agent
        user_agent = browser.latest_tab.run_js("return navigator.userAgent")

        logging.info(
            "请前往开源项目查看更多信息：https://github.com/chengazhen/cursor-auto-free"
        )
        logging.info("\n=== 配置信息 ===")
        login_url = "https://authenticator.cursor.sh"
        sign_up_url = "https://authenticator.cursor.sh/sign-up"
        settings_url = "https://www.cursor.com/settings"
        mail_url = "https://tempmail.plus"

        logging.info("正在生成随机账号信息...")

        email_generator = EmailGenerator()
        first_name = email_generator.default_first_name
        last_name = email_generator.default_last_name
        account = email_generator.generate_email()
        password = email_generator.generate_password()

        logging.info(f"生成的邮箱账号: {account}")

        logging.info("正在初始化邮箱验证模块...")
        email_handler = EmailVerificationHandler(account)

        auto_update_cursor_auth = True

        tab = browser.latest_tab

        tab.run_js("try { turnstile.reset() } catch(e) { }")

        logging.info("\n=== 开始注册流程 ===")
        logging.info(f"正在访问登录页面: {login_url}")
        tab.get(login_url)

        if sign_up_account(browser, tab):
            logging.info("正在获取会话令牌...")
            access_token, refresh_token = get_cursor_session_token(tab)
            if access_token and refresh_token:
                logging.info(f"更新认证信息...")
                logging.info(f"{access_token}")
                logging.info(f"更新认证信息...{refresh_token}")
                logging.info(f"{refresh_token}")
                # update_cursor_auth(
                #     email=account, access_token=token, refresh_token=token
                # )
                # logging.info(
                #     "请前往开源项目查看更多信息：https://github.com/chengazhen/cursor-auto-free"
                # )
                # logging.info("重置机器码...")
                # reset_machine_id(greater_than_0_45)
                logging.info("所有操作已完成")
                print_end_message()
            else:
                logging.error("获取会话令牌失败，注册流程未完成")

    except Exception as e:
        logging.error(f"程序执行出现错误: {str(e)}")
        import traceback

        logging.error(traceback.format_exc())
    finally:
        if browser_manager:
            browser_manager.quit()
        input("\n程序执行完毕，按回车键退出...")
