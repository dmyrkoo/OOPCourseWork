"""
main.py
Точка входу для електронного українсько-англійського словника.

Запускає GUI застосунок з налаштованим клієнтом.

Автор: Dmytro Petruniv
Версія: 2.0
Дата: 2025

Використання:
    python main.py
"""

import os
import sys
import ctypes
import logging

# --- Підтримка кирилиці в консолі Windows ---
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    os.system("chcp 65001 >nul 2>&1")

    # High DPI Awareness для Windows
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

# --- Налаштування логування ---
LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, "client_log.txt")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("DictionaryClient")

# --- Налаштування CustomTkinter ---
import customtkinter as ctk
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# --- Імпорт модулів застосунку ---
from network_manager import DictionaryClient
from ui_components import ModernDictionaryApp


def main():
    """
    Головна функція запуску застосунку.

    Створює клієнт, передає його в GUI та запускає головний цикл.
    Забезпечує безпечне завершення з очищенням ресурсів.
    """
    client = None
    app = None
    
    try:
        # Створюємо клієнт для мережевих операцій
        client = DictionaryClient(
            host='127.0.0.1',
            port=8080,
            timeout=10.0
        )

        # Створюємо та запускаємо GUI з клієнтом
        app = ModernDictionaryApp(client=client)

        # Запускаємо головний цикл
        app.mainloop()
        
    except KeyboardInterrupt:
        logger.info("Застосунок зупинено користувачем (Ctrl+C)")
    except Exception as e:
        # Ловимо всі неочікувані винятки для безпеки
        logger.error(f"Критична помилка: {e}", exc_info=True)
    finally:
        # Безпечне очищення ресурсів
        try:
            if client:
                if client.connected:
                    try:
                        client.disconnect()
                    except Exception as e:
                        logger.warning(f"Помилка відключення клієнта: {e}")
        except Exception as e:
            logger.warning(f"Помилка очищення клієнта: {e}")
        
        try:
            if app and hasattr(app, 'db') and app.db:
                try:
                    app.db.close()
                except Exception as e:
                    logger.warning(f"Помилка закриття БД: {e}")
        except Exception as e:
            logger.warning(f"Помилка очищення БД: {e}")
        
        logger.info("Застосунок завершено")


if __name__ == "__main__":
    main()

