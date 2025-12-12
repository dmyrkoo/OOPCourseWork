"""
database_manager.py
Модуль менеджера бази даних для електронного словника.

Містить клас DatabaseManager для роботи з SQLite базою даних.
Обробляє збереження історії пошуку та налаштувань користувача.

Автор: Dmytro Petruniv
Версія: 1.1
Дата: 2025
"""

import sqlite3
import logging
import datetime
from typing import List, Optional, Tuple

# Отримуємо логер
logger = logging.getLogger("DictionaryClient")


class DatabaseManager:
    """
    Менеджер бази даних SQLite для словника.

    Забезпечує збереження історії пошуку, улюблених слів
    та налаштувань користувача.

    Attributes:
        db_path (str): Шлях до файлу бази даних.
        connection (sqlite3.Connection): З'єднання з базою.

    Example:
        >>> db = DatabaseManager('dictionary.db')
        >>> db.add_to_history('hello', 'привіт')
        >>> db.get_history()
        [('hello', 'привіт', '2025-12-11 10:30:00')]
    """

    def __init__(self, db_path: str = 'dictionary_history.db'):
        """
        Ініціалізація менеджера бази даних.

        Args:
            db_path (str): Шлях до файлу бази даних. За замовчуванням 'dictionary_history.db'.
        """
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None
        self._initialize_database()

    def _initialize_database(self):
        """
        Створення таблиць якщо вони не існують.

        Створює:
        - search_history: Історія пошуку
        - favorites: Улюблені слова
        - settings: Налаштування користувача
        """
        try:
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = self.connection.cursor()

            # Таблиця історії пошуку
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL,
                    translation TEXT,
                    searched_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблиця улюблених слів
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL UNIQUE,
                    translation TEXT,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблиця налаштувань
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            self.connection.commit()
            logger.info("База даних ініціалізована успішно")

        except sqlite3.Error as e:
            logger.error(f"Помилка ініціалізації бази даних: {e}")
            print(f"[БД] ❌ Помилка ініціалізації: {e}")

    def add_to_history(self, word: str, translation: str = "") -> bool:
        """
        Додає слово до історії пошуку.

        Args:
            word (str): Слово що було знайдено.
            translation (str): Переклад слова (опціонально).

        Returns:
            bool: True якщо успішно додано, False інакше.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                timestamp = datetime.datetime.now()

                # 1. Insert or Replace (оновлює timestamp, якщо слово вже є)
                cursor.execute("""
                    INSERT OR REPLACE INTO search_history (id, word, translation, searched_at)
                    VALUES (
                        (SELECT id FROM search_history WHERE word = ?),
                        ?, ?, ?
                    )
                """, (word, word, translation, timestamp))

                # 2. Keep only last 50 items (Виправлений SQL запит)
                cursor.execute("""
                    DELETE FROM search_history 
                    WHERE id NOT IN (
                        SELECT id FROM search_history 
                        ORDER BY searched_at DESC 
                        LIMIT 50
                    )
                """)
                conn.commit()
                logger.info(f"Додано до історії: '{word}'")
                return True
        except sqlite3.Error as e:
            logger.error(f"Помилка додавання до історії: {e}")
            return False

    def get_history(self, limit: int = 10) -> List[Tuple[str, str, str]]:
        """
        Отримує останні записи з історії пошуку.

        Args:
            limit (int): Максимальна кількість записів. За замовчуванням 10.

        Returns:
            List[Tuple[str, str, str]]: Список кортежів (слово, переклад, час).
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT word, translation, searched_at 
                    FROM search_history 
                    ORDER BY searched_at DESC 
                    LIMIT ?
                ''', (limit,))
                return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Помилка отримання історії: {e}")
            return []

    def get_history_words(self, limit: int = 10) -> List[str]:
        """
        Отримує тільки слова з історії (без дублікатів).

        Args:
            limit (int): Максимальна кількість слів.

        Returns:
            List[str]: Список унікальних слів.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT word 
                    FROM search_history 
                    ORDER BY searched_at DESC 
                    LIMIT ?
                ''', (limit,))
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Помилка отримання слів історії: {e}")
            return []

    def clear_history(self) -> bool:
        """
        Очищає всю історію пошуку.

        Returns:
            bool: True якщо успішно очищено, False інакше.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM search_history")
                conn.commit()
                logger.info("Історію пошуку очищено")
                return True
        except sqlite3.Error as e:
            logger.error(f"Помилка очищення історії: {e}")
            return False

    def remove_from_history(self, word: str) -> bool:
        """
        Видаляє конкретне слово з історії пошуку.

        Args:
            word (str): Слово для видалення.

        Returns:
            bool: True якщо успішно видалено, False інакше.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM search_history WHERE word = ?', (word,))
                conn.commit()
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.info(f"Видалено з історії: '{word}'")
                return deleted
        except sqlite3.Error as e:
            logger.error(f"Помилка видалення з історії: {e}")
            return False

    def add_to_favorites(self, word: str, translation: str = "") -> bool:
        """
        Додає слово до улюблених.

        Args:
            word (str): Слово для збереження.
            translation (str): Переклад слова.

        Returns:
            bool: True якщо успішно додано, False якщо вже існує або помилка.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT OR IGNORE INTO favorites (word, translation, added_at) VALUES (?, ?, ?)',
                    (word, translation, datetime.datetime.now())
                )
                conn.commit()
                if cursor.rowcount > 0:
                    logger.info(f"Додано до улюблених: '{word}'")
                    return True
                return False  # Вже існує
        except sqlite3.Error as e:
            logger.error(f"Помилка додавання до улюблених: {e}")
            return False

    def get_favorites(self) -> List[Tuple[str, str]]:
        """
        Отримує всі улюблені слова.

        Returns:
            List[Tuple[str, str]]: Список кортежів (слово, переклад).
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT word, translation FROM favorites ORDER BY added_at DESC')
                return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Помилка отримання улюблених: {e}")
            return []

    def remove_from_favorites(self, word: str) -> bool:
        """
        Видаляє слово з улюблених.

        Args:
            word (str): Слово для видалення.

        Returns:
            bool: True якщо успішно видалено, False інакше.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM favorites WHERE word = ?', (word,))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Помилка видалення з улюблених: {e}")
            return False

    def is_favorite(self, word: str) -> bool:
        """
        Перевіряє чи слово є улюбленим.

        Args:
            word (str): Слово для перевірки.

        Returns:
            bool: True якщо слово в улюблених, False інакше.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM favorites WHERE word = ?', (word,))
                result = cursor.fetchone()
                return result[0] > 0 if result else False
        except sqlite3.Error as e:
            logger.error(f"Помилка перевірки улюбленого: {e}")
            return False

    # Alias methods for compatibility with user's requested naming
    def add_favorite(self, word: str, definition: str = "") -> bool:
        """
        Alias for add_to_favorites for compatibility.

        Args:
            word (str): Слово для збереження.
            definition (str): Переклад слова.

        Returns:
            bool: True якщо успішно додано, False інакше.
        """
        return self.add_to_favorites(word, definition)

    def remove_favorite(self, word: str) -> bool:
        """
        Alias for remove_from_favorites for compatibility.

        Args:
            word (str): Слово для видалення.

        Returns:
            bool: True якщо успішно видалено, False інакше.
        """
        return self.remove_from_favorites(word)

    def get_setting(self, key: str, default: str = "") -> str:
        """
        Отримує налаштування за ключем.

        Args:
            key (str): Ключ налаштування.
            default (str): Значення за замовчуванням.

        Returns:
            str: Значення налаштування або default.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
                row = cursor.fetchone()
                return row[0] if row else default
        except sqlite3.Error as e:
            logger.error(f"Помилка отримання налаштування: {e}")
            return default

    def set_setting(self, key: str, value: str) -> bool:
        """
        Зберігає налаштування.

        Args:
            key (str): Ключ налаштування.
            value (str): Значення для збереження.

        Returns:
            bool: True якщо успішно збережено, False інакше.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                    (key, value)
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Помилка збереження налаштування: {e}")
            return False

    def close(self):
        """
        Закриває з'єднання з базою даних.
        """
        if self.connection:
            self.connection.close()
            logger.info("З'єднання з базою даних закрито")

    def __del__(self):
        """Деструктор - закриває з'єднання."""
        self.close()
