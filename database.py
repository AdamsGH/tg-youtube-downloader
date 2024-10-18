import os
import psycopg2
from psycopg2 import sql
import time

DB_NAME = os.environ.get('POSTGRES_DB', 'testdb')
DB_USER = os.environ.get('POSTGRES_USER', 'testuser')
DB_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'testpass')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')

class Database:
    def __init__(self):
        self.wait_for_db()
        self.connection = self.connect_db()
        self.cursor = self.connection.cursor()
        self.create_table()

    def wait_for_db(self, max_retries=30, delay=2):
        retries = 0
        while retries < max_retries:
            try:
                self.connection = psycopg2.connect(
                    dbname=DB_NAME,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    host=DB_HOST,
                    port=DB_PORT
                )
                self.cursor = self.connection.cursor()
                print("База данных готова к подключению.")
                return
            except psycopg2.OperationalError:
                retries += 1
                print(f"База данных не готова. Попытка {retries}/{max_retries}. Ожидание {delay} секунд...")
                time.sleep(delay)
        raise Exception("Не удалось подключиться к базе данных после нескольких попыток.")

    def connect_db(self):
        return psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )

    def create_table(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id SERIAL PRIMARY KEY,
                telegram_id VARCHAR(255) NOT NULL,
                keywords TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.connection.commit()

    def add_video(self, telegram_id, keywords):
        self.cursor.execute("""
            INSERT INTO videos (telegram_id, keywords) VALUES (%s, %s)
        """, (telegram_id, keywords))
        self.connection.commit()

    def search_videos(self, keyword):
        self.cursor.execute("""
            SELECT * FROM videos WHERE keywords ILIKE %s
        """, (f'%{keyword}%',))
        return self.cursor.fetchall()

    def close(self):
        self.cursor.close()
        self.connection.close()
