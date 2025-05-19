import os
import aiosqlite
import asyncio
from datetime import datetime
from src.utils.logger import logging
from src.utils.config import Config

class DatabaseHandler:
    def __init__(self):
        config = Config()
        self.db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./accounts.db")
        # Extract the SQLite path from the URL
        self.db_path = self.db_url.split("://")[-1]
        
    async def initialize_db(self):
        """Initialize the database with required tables"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    password TEXT NOT NULL,
                    token TEXT,
                    usage_info TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.commit()
            logging.info("Database initialized successfully")
            
    async def save_account_info(self, email, password, token, usage_info):
        """Save account information to the database"""
        try:
            await self.initialize_db()
            async with aiosqlite.connect(self.db_path) as db:
                query = '''
                    INSERT INTO accounts (email, password, token, usage_info)
                    VALUES (?, ?, ?, ?)
                '''
                await db.execute(query, (email, password, token, usage_info))
                await db.commit()
                logging.info(f"Account information saved to database: {email}")
                return True
        except Exception as e:
            logging.error(f"Failed to save account information: {str(e)}")
            return False
            
    async def get_all_accounts(self):
        """Get all accounts from the database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute('SELECT * FROM accounts ORDER BY id DESC')
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logging.error(f"Failed to retrieve accounts: {str(e)}")
            return []

# Helper for synchronous contexts
def save_account_info_sync(email, password, token, usage_info):
    """Synchronous wrapper for saving account info"""
    handler = DatabaseHandler()
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # Create a new event loop if one is already running
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(handler.save_account_info(email, password, token, usage_info)) 