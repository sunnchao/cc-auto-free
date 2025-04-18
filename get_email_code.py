from datetime import datetime
import logging
import time
import re
from src.utils.config import Config
import requests
import email
import imaplib
import poplib
import base64
import json
from email.parser import Parser


class EmailVerificationHandler:
    def __init__(self,account):
        self.imap = Config().get_imap()
        self.username = Config().get_temp_mail()
        self.epin = Config().get_temp_mail_epin()
        self.session = requests.Session()
        self.emailExtension = Config().get_temp_mail_ext()
        # 获取协议类型，默认为 POP3
        self.protocol = Config().get_protocol() or 'POP3'
        self.account = account

    def get_verification_code(self, max_retries=5, retry_interval=60):
        """
        获取验证码，带有重试机制。

        Args:
            max_retries: 最大重试次数。
            retry_interval: 重试间隔时间（秒）。

        Returns:
            验证码 (字符串或 None)。
        """

        for attempt in range(max_retries):
            try:
                logging.info(f"尝试获取验证码 (第 {attempt + 1}/{max_retries} 次)...")

                if not self.imap:
                    verify_code, first_id = self._get_latest_mail_code()
                    if verify_code is not None and first_id is not None:
                        self._cleanup_mail(first_id)
                        return verify_code
                else:
                    if self.protocol.upper() == 'IMAP':
                        verify_code = self._get_mail_code_by_imap()
                    else:
                        verify_code = self._get_mail_code_by_pop3()
                    if verify_code is not None:
                        return verify_code

                if attempt < max_retries - 1:  # 除了最后一次尝试，都等待
                    logging.warning(f"未获取到验证码，{retry_interval} 秒后重试...")
                    time.sleep(retry_interval)

            except Exception as e:
                logging.error(f"获取验证码失败: {e}")  # 记录更一般的异常
                if attempt < max_retries - 1:
                    logging.error(f"发生错误，{retry_interval} 秒后重试...")
                    time.sleep(retry_interval)
                else:
                    raise Exception(f"获取验证码失败且已达最大重试次数: {e}") from e

        raise Exception(f"经过 {max_retries} 次尝试后仍未获取到验证码。")

    # 使用OAuth2获取访问令牌
    def _get_oauth2_access_token(self, imap_client_id, imap_refresh_token, imap_client_secret=None):
        """
        使用刷新令牌获取OAuth2访问令牌
        
        Args:
            imap_client_id: OAuth2客户端ID
            imap_refresh_token: OAuth2刷新令牌
            imap_client_secret: OAuth2客户端密钥(可选)
            
        Returns:
            access_token: 访问令牌或None
        """
        try:
            # 根据邮箱类型确定OAuth2端点
            token_url = self.imap.get('imap_oauth2_token_url', "")
            auth_url = self.imap.get('imap_oauth2_auth_url', "")
            redirect_uri = self.imap.get('imap_oauth2_redirect_uri', "")

            # 权限范围
            scopes = self.imap.get('imap_oauth2_scopes', "")
            # 如果没有指定OAuth2端点，根据邮箱域名尝试判断
            if token_url == "" and 'imap_user' in self.imap:
                email_domain = self.imap['imap_user'].split('@')[-1].lower()
                
                # Microsoft Outlook/Office 365端点
                if email_domain in ['outlook.com', 'hotmail.com', 'live.com', 'office365.com', 'microsoft.com']:
                    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
                    auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
                    redirect_uri = "http://localhost:8000"
                    scopes = [
                        'offline_access',
                        'https://graph.microsoft.com/Mail.ReadWrite',
                        'https://graph.microsoft.com/Mail.Send',
                        'https://graph.microsoft.com/User.Read'
                    ]
                # Yahoo端点
                elif email_domain in ['yahoo.com', 'ymail.com']:
                    token_url = "https://api.login.yahoo.com/oauth2/get_token"
                    auth_url = "https://api.login.yahoo.com/oauth2/request_auth"
                    redirect_uri = "https://tempmail.plus/imap"
                    scopes = [
                        'mail-rws',
                        'mail-rw'
                    ]
            logging.info(f"使用OAuth2端点: {token_url}")
            
            payload = {
                "client_id": imap_client_id,
                "refresh_token": imap_refresh_token,
                "grant_type": "refresh_token"
            }
            
            # 如果提供了客户端密钥，则添加到请求中
            if imap_client_secret:
                payload["client_secret"] = imap_client_secret
            
            response = requests.post(token_url, data=payload)
            # 打印 response
            if response.status_code == 200:
                token_data = response.json()
                return token_data["access_token"]
            else:
                logging.error(f"获取访问令牌失败: HTTP {response.status_code}, 响应: {response.text}")
                return None
                
        except Exception as e:
            logging.error(f"获取OAuth2访问令牌时出错: {e}")
            return None
    
    # 生成IMAP OAuth2身份验证字符串
    def _generate_oauth2_string(self, username, access_token):
        """
        生成IMAP OAuth2认证字符串
        
        Args:
            username: 邮箱用户名
            access_token: OAuth2访问令牌
            
        Returns:
            auth_string: base64编码的认证字符串
        """
        auth_string = 'user=%s\1auth=Bearer %s\1\1' % (username, access_token)
        # auth_string = base64.b64encode(auth_string.encode('utf-8'))
        return auth_string

    # 使用imap获取邮件
    def _get_mail_code_by_imap(self, retry = 0):
        """
        通过IMAP协议获取邮件并提取验证码。
        支持两种身份验证方式：
        1. 传统的用户名/密码认证
        2. OAuth2认证（需要提供imap_client_id和imap_refresh_token）
        
        OAuth2认证配置示例:
        {
            "imap_server": "imap.gmail.com",
            "imap_port": 993,
            "imap_user": "user@gmail.com",
            "imap_dir": "INBOX",
            "imap_client_id": "your-client-id.apps.googleusercontent.com",
            "imap_refresh_token": "your-refresh-token",
            "imap_client_secret": "your-client-secret"  # 可选
        }
        
        也可以指定 oauth2_token_url 来自定义OAuth2令牌端点：
        "oauth2_token_url": "https://your-custom-token-endpoint.com/token"
        
        Args:
            retry: 当前重试次数
            
        Returns:
            验证码字符串或None
            
        Raises:
            Exception: 如果重试次数超过最大限制或认证失败
        """
        if retry > 0:
            time.sleep(3)
        if retry >= 20:
            raise Exception("获取验证码超时")
        
        mail = None
        try:
            # 连接到IMAP服务器
            logging.info(f"连接到IMAP服务器: {self.imap['imap_server']}:{self.imap['imap_port']}")
            mail = imaplib.IMAP4_SSL(self.imap['imap_server'], self.imap['imap_port'])
            
            # 检查是否提供了OAuth2认证信息
            if self.imap['imap_client_id'] != "" and self.imap["imap_refresh_token"] != "":
                # 使用OAuth2认证
                logging.info("使用OAuth2认证方式")
                imap_client_secret = self.imap.get('imap_client_secret')  # 获取客户端密钥，如果存在
                if self.imap.get('imap_access_token') != "":
                    access_token = self.imap['imap_access_token']
                else:
                    access_token = self._get_oauth2_access_token(
                        self.imap['imap_client_id'], 
                        self.imap['imap_refresh_token'],
                        imap_client_secret
                    )

                if access_token == None:
                    logging.error("OAuth2认证失败: 无法获取访问令牌")
                    # 如果配置了备用密码认证，则尝试使用密码认证
                    if 'imap_pass' in self.imap:
                        logging.info("尝试使用备用密码认证")
                        mail.login(self.imap['imap_user'], self.imap['imap_pass'])
                        logging.info("使用备用密码认证成功")
                    else:
                        raise Exception("OAuth2认证失败，且没有配置备用密码")
                else:
                    # 使用OAuth2认证
                    auth_string = self._generate_oauth2_string(self.imap['imap_user'], access_token)
                    try:
                        # 使用现有连接进行认证，不要创建新连接
                        mail.authenticate('XOAUTH2', lambda x: auth_string)

                        logging.info("OAuth2认证成功")
                    except imaplib.IMAP4.error as e:
                        logging.error(f"OAuth2认证失败: {e}")
                        # 如果配置了备用密码认证，则尝试使用密码认证
                        if 'imap_pass' in self.imap:
                            logging.info("尝试使用备用密码认证")
                            mail.login(self.imap['imap_user'], self.imap['imap_pass'])
                            logging.info("使用备用密码认证成功")
                        else:
                            raise Exception(f"OAuth2认证失败: {e}")
            else:
                # 使用传统用户名密码认证
                logging.info("使用传统用户名密码认证")
                mail.login(self.imap['imap_user'], self.imap['imap_pass'])
                logging.info("密码认证成功")
            
            search_by_date=False
            # 针对网易系邮箱，imap登录后需要附带联系信息，且后续邮件搜索逻辑更改为获取当天的未读邮件
            if self.imap['imap_user'].endswith(('@163.com', '@126.com', '@yeah.net')):                
                imap_id = ("name", self.imap['imap_user'].split('@')[0], "contact", self.imap['imap_user'], "version", "1.0.0", "vendor", "imaplib")
                mail.xatom('ID', '("' + '" "'.join(imap_id) + '")')
                search_by_date=True
            
            mail.select(self.imap['imap_dir'])
            if search_by_date:
                date = datetime.now().strftime("%d-%b-%Y")
                status, messages = mail.search(None, f'ON {date} UNSEEN')
            else:
                status, messages = mail.search(None, 'TO', '"'+self.account+'"')
            if status != 'OK':
                logging.error("邮件搜索失败")
                mail.logout()
                return None

            mail_ids = messages[0].split()
            if not mail_ids:
                # 没有获取到，就在获取一次
                logging.info("未找到邮件，准备重试")
                mail.logout()
                return self._get_mail_code_by_imap(retry=retry + 1)
            else:
                logging.info("找到邮件，准备提取验证码")

            # 遍历邮件，从最新到最旧
            for mail_id in reversed(mail_ids):
                status, msg_data = mail.fetch(mail_id, '(RFC822)')
                if status != 'OK':
                    continue
                raw_email = msg_data[0][1]
                email_message = email.message_from_bytes(raw_email)

                # 如果是按日期搜索的邮件，需要进一步核对收件人地址是否对应
                if search_by_date and email_message['to'] !=self.account:
                    continue
                body = self._extract_imap_body(email_message)
                if body:
                    # 避免 6 位数字的域名被误识别成验证码
                    body = body.replace(self.account, '')
                    code_match = re.search(r"\b\d{6}\b", body)
                    if code_match:
                        code = code_match.group()
                        logging.info(f"找到验证码: {code}")
                        # 删除找到验证码的邮件
                        mail.store(mail_id, '+FLAGS', '\\Deleted')
                        mail.expunge()
                        mail.logout()
                        return code
            
            logging.info("已检查所有邮件，但未找到验证码")
            mail.logout()
            return None
            
        except Exception as e:
            logging.error(f"IMAP获取邮件时发生错误: {e}")
            if mail:
                try:
                    mail.logout()
                except:
                    pass
            return None

    def _extract_imap_body(self, email_message):
        # 提取邮件正文
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    charset = part.get_content_charset() or 'utf-8'
                    try:
                        body = part.get_payload(decode=True).decode(charset, errors='ignore')
                        return body
                    except Exception as e:
                        logging.error(f"解码邮件正文失败: {e}")
        else:
            content_type = email_message.get_content_type()
            if content_type == "text/plain":
                charset = email_message.get_content_charset() or 'utf-8'
                try:
                    body = email_message.get_payload(decode=True).decode(charset, errors='ignore')
                    return body
                except Exception as e:
                    logging.error(f"解码邮件正文失败: {e}")
        return ""

    # 使用 POP3 获取邮件
    def _get_mail_code_by_pop3(self, retry = 0):
        if retry > 0:
            time.sleep(3)
        if retry >= 20:
            raise Exception("获取验证码超时")
        
        pop3 = None
        try:
            # 连接到服务器
            pop3 = poplib.POP3_SSL(self.imap['imap_server'], int(self.imap['imap_port']))
            pop3.user(self.imap['imap_user'])
            pop3.pass_(self.imap['imap_pass'])
            
            # 获取最新的10封邮件
            num_messages = len(pop3.list()[1])
            for i in range(num_messages, max(1, num_messages-9), -1):
                response, lines, octets = pop3.retr(i)
                msg_content = b'\r\n'.join(lines).decode('utf-8')
                msg = Parser().parsestr(msg_content)
                
                # 检查发件人
                if 'no-reply@cursor.sh' in msg.get('From', ''):
                    # 提取邮件正文
                    body = self._extract_pop3_body(msg)
                    if body:
                        # 查找验证码
                        code_match = re.search(r"\b\d{6}\b", body)
                        if code_match:
                            code = code_match.group()
                            pop3.quit()
                            return code
            
            pop3.quit()
            return self._get_mail_code_by_pop3(retry=retry + 1)
            
        except Exception as e:
            print(f"发生错误: {e}")
            if pop3:
                try:
                    pop3.quit()
                except:
                    pass
            return None

    def _extract_pop3_body(self, email_message):
        # 提取邮件正文
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        return body
                    except Exception as e:
                        logging.error(f"解码邮件正文失败: {e}")
        else:
            try:
                body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
                return body
            except Exception as e:
                logging.error(f"解码邮件正文失败: {e}")
        return ""

    # 手动输入验证码
    def _get_latest_mail_code(self):
        # 获取邮件列表
        mail_list_url = f"https://tempmail.plus/api/mails?email={self.username}{self.emailExtension}&limit=20&epin={self.epin}"
        mail_list_response = self.session.get(mail_list_url)
        mail_list_data = mail_list_response.json()
        time.sleep(0.5)
        if not mail_list_data.get("result"):
            return None, None

        # 获取最新邮件的ID
        first_id = mail_list_data.get("first_id")
        if not first_id:
            return None, None

        # 获取具体邮件内容
        mail_detail_url = f"https://tempmail.plus/api/mails/{first_id}?email={self.username}{self.emailExtension}&epin={self.epin}"
        mail_detail_response = self.session.get(mail_detail_url)
        mail_detail_data = mail_detail_response.json()
        time.sleep(0.5)
        if not mail_detail_data.get("result"):
            return None, None

        # 从邮件文本中提取6位数字验证码
        mail_text = mail_detail_data.get("text", "")
        mail_subject = mail_detail_data.get("subject", "")
        logging.info(f"找到邮件主题: {mail_subject}")
        # 修改正则表达式，确保 6 位数字不紧跟在字母或域名相关符号后面
        code_match = re.search(r"(?<![a-zA-Z@.])\b\d{6}\b", mail_text)

        if code_match:
            return code_match.group(), first_id
        return None, None

    def _cleanup_mail(self, first_id):
        # 构造删除请求的URL和数据
        delete_url = "https://tempmail.plus/api/mails/"
        payload = {
            "email": f"{self.username}{self.emailExtension}",
            "first_id": first_id,
            "epin": f"{self.epin}",
        }

        # 最多尝试5次
        for _ in range(5):
            response = self.session.delete(delete_url, data=payload)
            try:
                result = response.json().get("result")
                if result is True:
                    return True
            except:
                pass

            # 如果失败,等待0.5秒后重试
            time.sleep(0.5)

        return False


if __name__ == "__main__":
    # 从 Config 获取邮箱账号，或者使用默认值
    config = Config()
    test_account = config.get_temp_mail() + config.get_temp_mail_ext() 
    if config.get_temp_mail() == "":
        test_account = "test@example.com"
    
    email_handler = EmailVerificationHandler(test_account)
    code = email_handler.get_verification_code()
    print(f"验证码: {code}")
