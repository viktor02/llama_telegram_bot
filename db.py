import logging
import sqlite3


class ChatHistoryDB:
    def __init__(self, database_name):
        self.db_name = database_name
        self.logger = logging.getLogger(__name__)
        self.create_tables()

    def create_tables(self):
        conn = sqlite3.connect(self.db_name)
        self.logger.info(f"Database {self.db_name} opened")
        cursor = conn.cursor()

        # Create the message table
        cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_prompt TEXT NOT NULL,
            answer TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted INTEGER DEFAULT 0
        );''')

        conn.commit()
        conn.close()

    def insert_message(self, chat_id, user_prompt, answer):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages (chat_id, user_prompt, answer) VALUES (?, ?, ?)",
                       (chat_id, user_prompt, answer))
        conn.commit()
        conn.close()

    def get_chat_messages(self, chat_id, limit=5):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT user_prompt, answer FROM messages WHERE chat_id = ? AND deleted = 0 LIMIT ?",
                       (chat_id, limit))
        results = cursor.fetchall()
        conn.close()
        return results

    def delete_all_history(self, chat_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute("UPDATE messages SET deleted = 1 WHERE chat_id = ?", (chat_id,))
        conn.commit()
        conn.close()
