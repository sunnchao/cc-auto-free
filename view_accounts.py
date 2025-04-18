import asyncio
import os
from tabulate import tabulate
from src.utils.db_handler import DatabaseHandler
from src.utils.logger import logging

async def view_accounts():
    """Display all accounts stored in the database"""
    try:
        handler = DatabaseHandler()
        accounts = await handler.get_all_accounts()
        
        if not accounts:
            print("No accounts found in the database.")
            return
        
        # Prepare data for tabulate
        headers = ["ID", "Email", "Password", "Token", "Usage Info", "Created At"]
        table_data = []
        
        for account in accounts:
            row = [
                account['id'],
                account['email'],
                account['password'],
                account['token'][:20] + "..." if account['token'] and len(account['token']) > 20 else account['token'],
                account['usage_info'],
                account['created_at']
            ]
            table_data.append(row)
        
        # Print the table
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"Total accounts: {len(accounts)}")
        
    except Exception as e:
        logging.error(f"Error viewing accounts: {str(e)}")
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    try:
        print("Cursor Accounts Database Viewer")
        print("=" * 50)
        
        # Check if database file exists
        db_path = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./accounts.db").split("://")[-1]
        if not os.path.exists(db_path):
            print(f"Database file not found: {db_path}")
            print("No accounts have been registered yet.")
        else:
            asyncio.run(view_accounts())
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    
    input("\nPress Enter to exit...") 