import os
import psycopg2
import psycopg2.extras  # Добавлено
from psycopg2 import sql
import time
import logging

logger = logging.getLogger(__name__)

DB_NAME = os.getenv('POSTGRES_DB', 'testdb')
DB_USER = os.getenv('POSTGRES_USER', 'testuser')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'testpass')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')

class Database:
    def __init__(self):
        self.connection = self.connect_db()
        self.cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)  # Изменено
        self.create_table()

    def connect_db(self):
        """Устанавливает соединение с базой данных."""
        retries = 0
        max_retries = 30
        delay = 2
        while retries < max_retries:
            try:
                conn = psycopg2.connect(
                    dbname=DB_NAME,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    host=DB_HOST,
                    port=DB_PORT,
                    cursor_factory=psycopg2.extras.RealDictCursor  # Добавлено
                )
                logger.info("Успешное подключение к базе данных.")
                return conn
            except psycopg2.OperationalError:
                retries += 1
                logger.warning(f"База данных не готова. Попытка {retries}/{max_retries}. Ждём {delay} секунд...")
                time.sleep(delay)
        raise Exception("Не удалось подключиться к базе данных после нескольких попыток.")

    def create_table(self):
        """Создаёт таблицу videos, если она не существует."""
        create_table_query = """
            CREATE TABLE IF NOT EXISTS videos (
                id SERIAL PRIMARY KEY,
                media_id VARCHAR(255),
                url TEXT NOT NULL UNIQUE,
                keywords TEXT,
                original_url TEXT,
                cut_version TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        self.cursor.execute(create_table_query)
        self.connection.commit()
        logger.info("Таблица videos готова.")

    def get_video_by_key(self, key: str):
        """Получает видео из базы данных по ключу."""
        cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)  # Добавлено
        cursor.execute("SELECT * FROM videos WHERE url = %s", (key,))
        return cursor.fetchone()

    def add_video(self, media_id: str, url: str, keywords: list, original_url: str = None):
        """Добавляет видео в базу данных."""
        try:
            with self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:  # Добавлено
                cursor.execute("""
                    INSERT INTO videos (media_id, url, keywords, original_url)
                    VALUES (%s, %s, %s, %s)
                """, (media_id, url, ','.join(keywords), original_url))
            self.connection.commit()
            logger.info(f"Добавлено видео: url={url}")
        except psycopg2.errors.UniqueViolation:
            logger.warning(f"Видео с URL {url} уже существует в базе данных.")
            self.connection.rollback()
        except Exception as e:
            logger.error(f"Ошибка при добавлении видео: {e}")
            self.connection.rollback()

    def update_video_file_id(self, url: str, file_id: str):
        """Обновляет поле media_id для существующего видео."""
        try:
            with self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:  # Добавлено
                cursor.execute("""
                    UPDATE videos SET media_id = %s WHERE url = %s
                """, (file_id, url))
            self.connection.commit()
            logger.info(f"Обновлен file_id для видео: url={url}")
        except Exception as e:
            logger.error(f"Ошибка при обновлении file_id: {e}")
            self.connection.rollback()

    def get_video_by_url(self, url: str):
        """Получает видео из базы данных по очищенному URL."""
        with self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:  # Добавлено
            cursor.execute("SELECT * FROM videos WHERE url = %s", (url,))
            return cursor.fetchone()

    def search_videos(self, keyword: str):
        """Ищет видео по ключевому слову."""
        with self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:  # Добавлено
            search_query = """
                SELECT id, media_id, url, keywords, cut_version, created_at 
                FROM videos 
                WHERE %s = ANY(string_to_array(keywords, ','))
            """
            cursor.execute(search_query, (keyword,))
            results = cursor.fetchall()
        videos = []
        for row in results:
            videos.append({
                'id': row['id'],
                'file_id': row['media_id'],
                'url': row['url'],
                'keywords': row['keywords'].split(',') if row['keywords'] else [],
                'cut_version': row['cut_version'],
                'created_at': row['created_at']
            })
        return videos

    def video_exists(self, url: str) -> bool:
        """Проверяет, существует ли видео по URL и имеет ли оно file_id."""
        check_query = "SELECT 1 FROM videos WHERE url = %s AND media_id IS NOT NULL"
        self.cursor.execute(check_query, (url,))
        return self.cursor.fetchone() is not None

    def close(self):
        """Закрывает соединение с базой данных."""
        self.cursor.close()
        self.connection.close()
        logger.info("Соединение с базой данных закрыто.")
