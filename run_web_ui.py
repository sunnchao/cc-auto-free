#!/usr/bin/env python3
"""
Cursor Accounts Web UI 启动器
"""

import os
import sys
from src.utils.logger import logging

def check_dependencies():
    """检查依赖是否安装"""
    try:
        import flask
        import aiosqlite
        return True
    except ImportError as e:
        print(f"错误: 缺少必要的依赖: {e}")
        print("请先安装依赖: pip install flask aiosqlite")
        return False

def setup_directories():
    """确保必须的目录结构存在"""
    directories = ['templates', 'static/js']
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

def check_files():
    """检查必要的文件是否存在"""
    files_to_check = [
        {'path': 'app.py', 'desc': '主应用程序文件'},
        {'path': 'templates/index.html', 'desc': 'HTML模板文件'},
        {'path': 'static/js/main.js', 'desc': 'JavaScript文件'},
    ]
    
    all_exist = True
    for file in files_to_check:
        if not os.path.exists(file['path']):
            print(f"错误: 找不到{file['desc']}: {file['path']}")
            all_exist = False
    
    return all_exist

def main():
    """主函数"""
    print("=" * 50)
    print("Cursor Accounts 可视化界面启动器")
    print("=" * 50)
    
    # 检查依赖
    if not check_dependencies():
        return 1
    
    # 设置目录
    setup_directories()
    
    # 检查文件
    if not check_files():
        print("\n缺少必要文件，无法启动应用。")
        return 1
    
    # 检查数据库
    db_path = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./accounts.db").split("://")[-1]
    if not os.path.exists(db_path):
        print(f"警告: 数据库文件不存在: {db_path}")
        print("应用将会创建一个新的空数据库。")
    
    print("\n所有检查通过，正在启动 Web UI...")
    
    # 启动Flask应用
    os.system("python app.py")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 