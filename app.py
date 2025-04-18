import os
import asyncio
from flask import Flask, jsonify, render_template, request
from src.utils.db_handler import DatabaseHandler, save_account_info_sync
from src.utils.logger import logging
from src.utils.browser_utils import BrowserManager
import time

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 支持中文显示

# 异步转同步的辅助函数
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route('/')
def index():
    """渲染主页"""
    return render_template('index.html')

@app.route('/api/accounts')
def get_accounts():
    """获取所有账号数据的API端点"""
    try:
        handler = DatabaseHandler()
        accounts = run_async(handler.get_all_accounts())
        
        # 格式化返回数据
        for account in accounts:
            # 处理创建时间格式
            if 'created_at' in account:
                account['created_at'] = str(account['created_at'])
        
        return jsonify({
            'status': 'success',
            'data': accounts,
            'count': len(accounts)
        })
    except Exception as e:
        logging.error(f"API错误: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/account/<int:account_id>')
def get_account(account_id):
    """获取单个账号数据的API端点"""
    try:
        handler = DatabaseHandler()
        accounts = run_async(handler.get_all_accounts())
        
        # 查找对应ID的账号
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        
        if account:
            if 'created_at' in account:
                account['created_at'] = str(account['created_at'])
            
            return jsonify({
                'status': 'success',
                'data': account
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'未找到ID为{account_id}的账号'
            }), 404
            
    except Exception as e:
        logging.error(f"API错误: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# 添加搜索API
@app.route('/api/search')
def search_accounts():
    """搜索账号的API端点"""
    try:
        query = request.args.get('q', '').lower()
        
        handler = DatabaseHandler()
        accounts = run_async(handler.get_all_accounts())
        
        if query:
            # 在邮箱和使用信息中搜索
            filtered_accounts = [
                acc for acc in accounts 
                if query in acc['email'].lower() or 
                   (acc['usage_info'] and query in acc['usage_info'].lower())
            ]
        else:
            filtered_accounts = accounts
            
        # 格式化返回数据
        for account in filtered_accounts:
            if 'created_at' in account:
                account['created_at'] = str(account['created_at'])
        
        return jsonify({
            'status': 'success',
            'data': filtered_accounts,
            'count': len(filtered_accounts)
        })
    except Exception as e:
        logging.error(f"搜索API错误: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# 添加获取Cursor会话令牌的API
@app.route('/api/get_cursor_token', methods=['POST'])
def get_cursor_token_api():
    """获取Cursor会话令牌的API端点"""
    try:
        # 检查请求数据
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': '未提供请求数据'
            }), 400
            
        # 获取必要参数
        login_url = data.get('login_url', 'https://authenticator.cursor.sh')
        email = data.get('email')
        password = data.get('password')
        
        # 参数验证
        if not email or not password:
            return jsonify({
                'status': 'error',
                'message': '邮箱和密码不能为空'
            }), 400
            
        # 初始化浏览器
        logging.info(f"API调用: 正在为用户 {email} 获取Cursor会话令牌...")
        browser_manager = BrowserManager()
        browser = browser_manager.init_browser()
        tab = browser.latest_tab
        
        try:
            # 访问登录页面
            tab.get(login_url)
            time.sleep(2)
            
            # 输入邮箱
            if tab.ele("@name=email"):
                tab.ele("@name=email").input(email)
                time.sleep(1)
                tab.ele("@type=submit").click()
                time.sleep(2)
            
            # 输入密码
            if tab.ele("@name=password"):
                tab.ele("@name=password").input(password)
                time.sleep(1)
                tab.ele("@type=submit").click()
                time.sleep(5)  # 等待登录完成
            
            # 获取令牌
            token = get_cursor_session_token(tab)
            
            if token:
                logging.info(f"成功获取会话令牌: {token[:10]}...")
                return jsonify({
                    'status': 'success',
                    'token': token
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': '未获取到会话令牌'
                }), 404
                
        finally:
            # 确保浏览器关闭
            browser_manager.quit()
            
    except Exception as e:
        logging.error(f"获取Cursor令牌API错误: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# 添加保存Token到数据库的API
@app.route('/api/save_token', methods=['POST'])
def save_token_api():
    """保存Token到数据库的API端点"""
    try:
        # 检查请求数据
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': '未提供请求数据'
            }), 400
            
        # 获取必要参数
        email = data.get('email')
        password = data.get('password')
        token = data.get('token')
        usage_info = data.get('usage_info', '未知')
        
        # 参数验证
        if not email or not password or not token:
            return jsonify({
                'status': 'error',
                'message': '邮箱、密码和Token不能为空'
            }), 400
            
        # 保存到数据库
        logging.info(f"API调用: 正在保存用户 {email} 的Token到数据库...")
        save_result = save_account_info_sync(email, password, token, usage_info)
        
        if save_result:
            logging.info(f"用户 {email} 的Token已成功保存到数据库")
            return jsonify({
                'status': 'success',
                'message': '账户信息已成功保存到数据库'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '账户信息保存到数据库失败'
            }), 500
            
    except Exception as e:
        logging.error(f"保存Token API错误: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# 从cursor_pro_keep_alive.py中提取的获取会话令牌函数
def get_cursor_session_token(tab, max_attempts=3, retry_interval=2):
    """
    获取Cursor会话token，带有重试机制
    :param tab: 浏览器标签页
    :param max_attempts: 最大尝试次数
    :param retry_interval: 重试间隔(秒)
    :return: session token 或 None
    """
    logging.info("开始获取cookie")
    attempts = 0

    while attempts < max_attempts:
        try:
            cookies = tab.cookies()
            for cookie in cookies:
                if cookie.get("name") == "WorkosCursorSessionToken":
                    return cookie["value"].split("%3A%3A")[1]

            attempts += 1
            if attempts < max_attempts:
                logging.warning(
                    f"第 {attempts} 次尝试未获取到CursorSessionToken，{retry_interval}秒后重试..."
                )
                time.sleep(retry_interval)
            else:
                logging.error(
                    f"已达到最大尝试次数({max_attempts})，获取CursorSessionToken失败"
                )

        except Exception as e:
            logging.error(f"获取cookie失败: {str(e)}")
            attempts += 1
            if attempts < max_attempts:
                logging.info(f"将在 {retry_interval} 秒后重试...")
                time.sleep(retry_interval)

    return None

if __name__ == '__main__':
    # 检查templates和static目录是否存在
    if not os.path.exists('templates'):
        os.makedirs('templates')
    if not os.path.exists('static/js'):
        os.makedirs('static/js')
    
    # 检查HTML和JS文件是否存在
    if not os.path.exists('templates/index.html'):
        logging.warning("templates/index.html不存在，请确保已创建该文件")
    if not os.path.exists('static/js/main.js'):
        logging.warning("static/js/main.js不存在，请确保已创建该文件")
    
    print("启动 Cursor Accounts 可视化服务...")
    print("访问 http://127.0.0.1:5000 查看账号数据")
    app.run(debug=True) 