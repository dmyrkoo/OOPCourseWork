"""
network_manager.py
Модуль мережевого менеджера для електронного словника.

Містить клас DictionaryClient для TCP з'єднання з C++ сервером.
Обробляє тільки сокетні з'єднання, відправку запитів та отримання даних.

Автор: Dmytro Petruniv
Версія: 2.1
Дата: 2025
"""

import socket
import time
import logging
import threading

# Отримуємо логер
logger = logging.getLogger("DictionaryClient")


class DictionaryClient:
    """
    TCP Клієнт для зв'язку з C++ сервером словника.

    Забезпечує підключення, відправку команд та отримання відповідей
    від сервера через TCP сокети.

    Attributes:
        host (str): IP-адреса сервера.
        port (int): Порт сервера.
        socket (socket.socket): TCP сокет для з'єднання.
        connected (bool): Статус з'єднання.
        timeout (float): Таймаут з'єднання в секундах.

    Example:
        >>> client = DictionaryClient('127.0.0.1', 8080)
        >>> client.connect()
        True
        >>> client.send_command('TRANSLATE|hello|')
        'привіт'
        >>> client.disconnect()
    """

    def __init__(self, host: str = '127.0.0.1', port: int = 8080, timeout: float = 2.0):
        """
        Ініціалізація клієнта словника.

        Args:
            host (str): IP-адреса сервера. За замовчуванням '127.0.0.1'.
            port (int): Порт сервера. За замовчуванням 8080.
            timeout (float): Таймаут з'єднання в секундах. За замовчуванням 2.0.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket = None
        self.connected = False
        self._socket_lock = threading.Lock()  # Захист доступу до сокета з різних потоків

    def connect(self) -> bool:
        """
        Встановлює з'єднання з сервером. Захищено від помилок та ідемпотентно.
        
        Returns:
            bool: True якщо підключення успішне, False інакше.
        """
        with self._socket_lock:
            # Закриваємо старий сокет якщо є (ідемпотентність)
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
            self.connected = False

            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(self.timeout)
                self.socket.connect((self.host, self.port))
                self.connected = True
                logger.info(f"[КЛІЄНТ] ✅ Підключено до {self.host}:{self.port}")
                return True
            except (ConnectionRefusedError, socket.timeout, OSError) as e:
                logger.error(f"[КЛІЄНТ] ❌ Помилка підключення: {e}")
                self.connected = False
                # Безпечне закриття сокета при помилці
                if self.socket:
                    try:
                        self.socket.close()
                    except Exception:
                        pass
                    self.socket = None
                return False
            except Exception as e:
                # Ловимо всі інші винятки для безпеки
                logger.error(f"[КЛІЄНТ] ❌ Неочікувана помилка підключення: {e}")
                self.connected = False
                if self.socket:
                    try:
                        self.socket.close()
                    except Exception:
                        pass
                    self.socket = None
                return False

    def send_command(self, command: str, recv_chunk: int = 4096) -> str:
        """
        Відправляє команду з надійною обробкою помилок, часткових UTF-8 кадрів та таймаутів.
        
        Особливості:
        - Використовує settimeout для send/recv операцій
        - Накопичує байти в список parts та намагається декодувати після кожного чанка
        - Обробляє UnicodeDecodeError для неповних байтів UTF-8
        - Використовує deadline на основі timeout для переривання циклу
        - Безпечно обробляє помилки сокетів та завжди відновлює попередній timeout
        
        Args:
            command (str): Команда для відправки
            recv_chunk (int): Розмір буфера для recv. За замовчуванням 4096.
            
        Returns:
            str: Відповідь сервера (може бути порожнім рядком при помилках)
        """
        max_retries = 3
        base_backoff = 0.5  # Початкова затримка в секундах
        max_backoff = 8.0   # Максимальна затримка
        
        for attempt in range(max_retries):
            sock = None
            old_timeout = None
            
            try:
                with self._socket_lock:
                    # Перевіряємо чи є активне з'єднання
                    if not self.connected or not self.socket:
                        if attempt == 0:
                            logger.info(f"[КЛІЄНТ] Спроба підключення {attempt + 1}/{max_retries}...")
                        else:
                            # Експоненціальний backoff для повторних спроб
                            backoff = min(base_backoff * (2 ** (attempt - 1)), max_backoff)
                            logger.info(f"[КЛІЄНТ] Retry #{attempt}: спроба перепідключення (backoff {backoff:.1f}s)...")
                            time.sleep(backoff)
                        
                        if not self.connect():
                            continue
                    
                    sock = self.socket
                    # Зберігаємо поточний timeout для відновлення
                    old_timeout = sock.gettimeout()
                    sock.settimeout(self.timeout)
                
                # Підготовка команди
                if not command.endswith('\n'):
                    command = command + '\n'
                full_cmd = command.encode('utf-8')
                
                # Відправка команди
                try:
                    sock.sendall(full_cmd)
                    logger.debug(f"[КЛІЄНТ] Відправлено команду: {command.strip()}")
                except (BrokenPipeError, ConnectionResetError, OSError) as e:
                    logger.warning(f"[КЛІЄНТ] ⚠️ Помилка відправки: {e}")
                    with self._socket_lock:
                        self.connected = False
                        if self.socket:
                            try:
                                self.socket.close()
                            except Exception:
                                pass
                            self.socket = None
                    continue
                
                # Отримання відповіді з обробкою часткових UTF-8 кадрів
                parts = []  # Список байтів для накопичення
                deadline = time.time() + self.timeout
                
                while time.time() < deadline:
                    try:
                        chunk = sock.recv(recv_chunk)
                        if not chunk:
                            # Порожній чанк означає закриття з'єднання
                            logger.debug("[КЛІЄНТ] Отримано порожній чанк (з'єднання закрито)")
                            break
                        
                        parts.append(chunk)
                        
                        # Спробуємо декодувати накопичені дані
                        raw = b"".join(parts)
                        try:
                            text = raw.decode('utf-8')
                            # Якщо декодування успішне і отримали менше ніж recv_chunk байт,
                            # або знайдено термінатор протоколу (якщо є), повертаємо результат
                            if len(chunk) < recv_chunk:
                                # Останній чанк - повертаємо результат
                                result = text.strip()
                                logger.debug(f"[КЛІЄНТ] Отримано відповідь ({len(raw)} байт)")
                                return result
                        except UnicodeDecodeError:
                            # Неповний UTF-8 символ - продовжуємо отримувати дані
                            logger.debug(f"[КЛІЄНТ] Неповний UTF-8 кадр, продовжуємо отримання...")
                            continue
                            
                    except socket.timeout:
                        # Таймаут при отриманні
                        logger.warning(f"[КЛІЄНТ] ⚠️ Таймаут отримання даних")
                        break
                    except (ConnectionResetError, BrokenPipeError, OSError) as e:
                        logger.warning(f"[КЛІЄНТ] ⚠️ Помилка отримання: {e}")
                        with self._socket_lock:
                            self.connected = False
                            if self.socket:
                                try:
                                    self.socket.close()
                                except Exception:
                                    pass
                                self.socket = None
                        # Виходимо з циклу отримання, спробуємо перепідключитися
                        break
                
                # Якщо вийшли з циклу, намагаємося декодувати те, що отримали
                if parts:
                    raw = b"".join(parts)
                    try:
                        # Толерантне декодування з заміною помилкових символів
                        result = raw.decode('utf-8', errors='replace').strip()
                        logger.debug(f"[КЛІЄНТ] Повертаємо часткову відповідь після таймауту/помилки")
                        return result
                    except Exception as e:
                        logger.warning(f"[КЛІЄНТ] ⚠️ Помилка декодування: {e}")
                        return ""
                else:
                    # Нічого не отримано
                    logger.warning(f"[КЛІЄНТ] ⚠️ Порожня відповідь від сервера")
                    with self._socket_lock:
                        self.connected = False
                        if self.socket:
                            try:
                                self.socket.close()
                            except Exception:
                                pass
                            self.socket = None
                    continue
                
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                logger.warning(f"[КЛІЄНТ] ⚠️ Втрачено з'єднання ({e}). Перепідключення...")
                with self._socket_lock:
                    self.connected = False
                    if self.socket:
                        try:
                            self.socket.close()
                        except Exception:
                            pass
                        self.socket = None
                continue
            except Exception as e:
                # Ловимо всі інші винятки для безпеки
                logger.error(f"[КЛІЄНТ] ❌ Неочікувана помилка: {e}")
                with self._socket_lock:
                    self.connected = False
                    if self.socket:
                        try:
                            self.socket.close()
                        except Exception:
                            pass
                        self.socket = None
                continue
            finally:
                # Завжди відновлюємо попередній timeout
                if sock and old_timeout is not None:
                    try:
                        sock.settimeout(old_timeout)
                    except Exception:
                        pass
        
        # Всі спроби вичерпано
        logger.error("[КЛІЄНТ] ❌ Не вдалося відправити запит після всіх спроб.")
        return ""

    def disconnect(self) -> None:
        """
        Безпечно від'єднується від сервера. Ідемпотентна операція.
        """
        with self._socket_lock:
            if self.socket:
                try:
                    self.socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
            self.connected = False
            logger.info("[КЛІЄНТ] Від'єднано від сервера")

    # Зручні обгортки
    def translate(self, word: str) -> str | None:
        """
        Переклад слова через сервер.

        Args:
            word (str): Слово для перекладу.

        Returns:
            str or None: Переклад або None при помилці.
        """
        return self.send_command(f"TRANSLATE|{word}|")

    def add_word(self, ukrainian: str, english: str) -> str | None:
        """
        Додавання нового слова до словника.

        Args:
            ukrainian (str): Українське слово.
            english (str): Англійський переклад.

        Returns:
            str or None: Відповідь сервера ('ADDED', 'EXIST') або None.
        """
        return self.send_command(f"ADD|{ukrainian}|{english}")

    def delete_word(self, headword: str) -> str | None:
        """
        Видалення слова зі словника.

        Args:
            headword (str): Англійське слово для видалення.

        Returns:
            str or None: Відповідь сервера ('Success' або 'Error') або None.
        """
        return self.send_command(f"DELETE|{headword}|")

    def update_word(self, headword: str, new_definition: str) -> str | None:
        """
        Оновлення визначення слова в словнику.

        Args:
            headword (str): Англійське слово для оновлення.
            new_definition (str): Нове визначення.

        Returns:
            str or None: Відповідь сервера ('Success' або 'Error') або None.
        """
        return self.send_command(f"UPDATE|{headword}|{new_definition}")

    def close(self):
        self.disconnect()

    def is_connected(self) -> bool:
        """
        Перевірка статусу з'єднання.

        Returns:
            bool: True якщо підключено, False інакше.
        """
        return self.connected

    def set_host(self, host: str) -> None:
        """
        Зміна адреси сервера.

        Args:
            host (str): Нова IP-адреса сервера.
        """
        self.host = host

    def set_port(self, port: int) -> None:
        """
        Зміна порту сервера.

        Args:
            port (int): Новий порт сервера.
        """
        self.port = port

    def __repr__(self) -> str:
        status = "connected" if self.connected else "disconnected"
        return f"DictionaryClient({self.host}:{self.port}, {status})"
