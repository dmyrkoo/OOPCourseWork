"""
ui_components.py
UI компоненти для електронного словника.

Містить всі CustomTkinter класи та логіку інтерфейсу:
- ModernDictionaryApp: Головне вікно застосунку
- StatusIndicator: Індикатор статусу з'єднання
- ResultCard: Картка результату перекладу
- HistoryItem: Елемент історії пошуку

Автор: Dmytro Petruniv
Версія: 2.0
Дата: 2025
"""

import customtkinter as ctk
from tkinter import messagebox
import logging
import re
import html
from datetime import datetime
import threading

from network_manager import DictionaryClient
from database_manager import DatabaseManager

# Отримуємо логер
logger = logging.getLogger("DictionaryClient")

# --- Іконки частин мови (Unicode Emoji) ---
POS_ICONS = {
    "noun": "📦",       # Іменник
    "verb": "⚙️",       # Дієслово
    "adj": "🎨",        # Прикметник
    "adv": "🚀",        # Прислівник
    "prep": "🔗",       # Прийменник
    "conj": "🔀",       # Сполучник
    "pron": "👤",       # Займенник
    "num": "🔢",        # Числівник
    "default": "📖"     # За замовчуванням
}

# --- Палітра кольорів (Світла тема - Light Mode Only) ---
COLORS = {
    "bg_main": "#F5F5F5",           # Світло-сірий фон
    "bg_card": "#FFFFFF",           # Білий для карток
    "bg_sidebar": "#E8E8E8",        # Сірий для бокових панелей
    "accent": "#007AFF",            # Azure Blue акцент
    "accent_hover": "#0056B3",      # Темніший синій при наведенні
    "success": "#28A745",           # Зелений для успіху
    "warning": "#FFC107",           # Жовтий для попереджень
    "danger": "#DC3545",            # Червоний для помилок
    "text_primary": "#000000",      # Чорний основний текст
    "text_secondary": "#333333",    # Темно-сірий вторинний текст
    "text_muted": "#6C757D",        # Сірий для тегів/підказок
    "border": "#DEE2E6",            # Світла рамка
    "title_color": "#1A365D"        # Темно-синій для заголовків
}

# --- Заголовки частин мови для форматування (чисті, без emoji) ---
POS_HEADERS = {
    'n': 'NOUN',
    'noun': 'NOUN',
    'v': 'VERB',
    'verb': 'VERB',
    'adj': 'ADJECTIVE',
    'adjective': 'ADJECTIVE',
    'adv': 'ADVERB',
    'adverb': 'ADVERB',
    'prep': 'PREPOSITION',
    'preposition': 'PREPOSITION',
    'conj': 'CONJUNCTION',
    'conjunction': 'CONJUNCTION',
    'pron': 'PRONOUN',
    'pronoun': 'PRONOUN',
    'int': 'INTERJECTION',
    'interjection': 'INTERJECTION',
    'num': 'NUMERAL',
    'numeral': 'NUMERAL',
    'phrasal v': 'PHRASAL VERB',
    'ph v': 'PHRASAL VERB',
    'ph.v': 'PHRASAL VERB',
}


def insert_formatted_text(textbox, text: str, tag_color: str = "#10B981"):
    """
    Вставляє відформатований текст у CTkTextbox з кольоровими тегами.
    
    Парсить текст та виділяє:
    - POS headers (наприклад, [ NOUN ], [ VERB ]) - жирним та кольором
    - Абревіатури (наприклад, [розм.], [книжк.]) - кольором
    
    Args:
        textbox: CTkTextbox віджет для вставки тексту
        text: Текст для форматування та вставки
        tag_color: Колір для тегів (POS headers та абревіатури). За замовчуванням зелений.
    """
    if not text:
        return
    
    # Очищаємо textbox
    textbox.delete("1.0", "end")
    
    # Створюємо теги для кольорових міток
    tag_name = "colored_tag"
    bold_tag_name = "bold_tag"
    
    # Налаштовуємо теги (CTkTextbox базується на tkinter Text widget)
    # Отримуємо доступ до внутрішнього Text widget
    inner_text = None
    try:
        # CTkTextbox має атрибут textbox для доступу до tkinter Text
        inner_text = getattr(textbox, 'textbox', None)
        if not inner_text:
            # Спробуємо інші можливі атрибути
            inner_text = getattr(textbox, '_textbox', None)
    except AttributeError:
        pass
    
    if inner_text:
        # Налаштовуємо теги через внутрішній Text widget
        try:
            import tkinter.font as tkfont
            # Звичайний тег для абревіатур
            inner_text.tag_config(tag_name, foreground=tag_color)
            # Жирний тег для POS headers (POS_TAG: [NOUN], [VERB] etc.)
            bold_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")
            inner_text.tag_config(bold_tag_name, font=bold_font, foreground=tag_color)
        except Exception as e:
            logger.warning(f"Не вдалося налаштувати теги: {e}")
            # Fallback: використовуємо тільки колір без жирного шрифту
            try:
                inner_text.tag_config(tag_name, foreground=tag_color)
                inner_text.tag_config(bold_tag_name, foreground=tag_color)
            except Exception:
                pass
    
    # Розбиваємо текст на рядки
    lines = text.split('\n')
    
    for line in lines:
        if not line.strip():
            # Порожній рядок
            textbox.insert("end", "\n")
            continue
        
        # Перевіряємо чи це POS header (формат: [ NOUN ], [ VERB ], [ PHRASAL VERB ] тощо)
        # Може бути з пробілами: [ NOUN ] або без: [NOUN]
        pos_match = re.match(r'^(\s*)(\[)\s*([A-Z][A-Z\s]*[A-Z]|[A-Z]+)\s*(\])(\s*)$', line)
        if pos_match:
            # Це POS header - виділяємо його жирним та кольором
            prefix = pos_match.group(1)
            bracket_open = pos_match.group(2)
            pos_text = pos_match.group(3).strip()
            bracket_close = pos_match.group(4)
            suffix = pos_match.group(5)
            
            if prefix:
                textbox.insert("end", prefix)
            textbox.insert("end", bracket_open, bold_tag_name)
            textbox.insert("end", f" {pos_text} ", bold_tag_name)
            textbox.insert("end", bracket_close, bold_tag_name)
            if suffix:
                textbox.insert("end", suffix)
            textbox.insert("end", "\n")
            continue
        
        # Обробляємо рядок з можливими абревіатурами
        remaining_line = line
        last_end = 0
        
        # Regex для знаходження всіх квадратних дужок (абревіатури)
        abbr_pattern = r'(\[[^\]]+\])'
        matches = list(re.finditer(abbr_pattern, remaining_line))
        
        if matches:
            # Є теги - вставляємо по частинах
            for match in matches:
                # Текст до тегу
                before = remaining_line[last_end:match.start()]
                if before:
                    textbox.insert("end", before)
                
                # Перевіряємо чи це POS header (великі літери) чи абревіатура
                tag_text = match.group(1)
                tag_content = tag_text.strip('[]').strip()
                
                # Якщо це POS header (тільки великі літери та пробіли)
                if re.match(r'^[A-Z\s]+$', tag_content):
                    # Використовуємо жирний тег
                    textbox.insert("end", tag_text, bold_tag_name)
                else:
                    # Це абревіатура - звичайний кольоровий тег
                    textbox.insert("end", tag_text, tag_name)
                
                last_end = match.end()
            
            # Залишок рядка після останнього тегу
            if last_end < len(remaining_line):
                textbox.insert("end", remaining_line[last_end:])
        else:
            # Немає тегів - вставляємо як звичайний текст
            textbox.insert("end", line)
        
        textbox.insert("end", "\n")
    
    # Налаштовуємо базовий шрифт для всього тексту (DEF: Definition text)
    textbox.configure(font=("Segoe UI", 16))


def format_and_display(raw_text: str, headword: str | None = None) -> str:
    """
    Парсинг та форматування тексту визначення зі словника.

    Args:
        raw_text (str): Сирий текст визначення з сервера.
        headword (str|None): Якщо вказано, використовується для підстановки '~'.

    Returns:
        str: Відформатований текст з заголовками частин мови, тегами та відступами.
    """
    if not raw_text or raw_text == "NOT_FOUND":
        return raw_text

    text = raw_text

    # Декодування HTML entities (&#x27; -> ', &quot; -> ")
    text = html.unescape(text)

    # --- NEW: розкриваємо посилання <<word>> -> word, прибираємо стрічки початкові '>' та обробляємо (a|b) групи ---
    # Заміна посилань виду <<word>> на просто word
    text = re.sub(r'<<\s*([^<>]+?)\s*>>', r'\1', text)

    # Прибрати початкові '>' в цитатах
    text = re.sub(r'(?m)^\s*>+\s*', '', text)

    def _pipe_group_repl(m):
        inner = m.group(1)
        parts = [p.strip() for p in inner.split('|') if p.strip()]
        # prefer alphabetic token if present (likely a headword), otherwise join
        alpha = [p for p in parts if re.match(r'^[A-Za-z\- ]+$', p)]
        if alpha:
            return ' (' + ' / '.join(alpha) + ')'
        return ' (' + ' / '.join(parts) + ')'

    text = re.sub(r'\(([^()]*\|[^()]*)\)', _pipe_group_repl, text)

    # Якщо є headword - підставляємо тильду (~) на його нижній регістр
    if headword:
        hw = headword.strip().lower()
        # Замінимо всі варіанти: '~', ' ~', '~ ', ' ~ ' - просто заміна символьна
        text = text.replace('~', hw)

    # Очищення від HTML тегів
    text = re.sub(r'<[^>]+>', '', text)
    # Видаляємо DSL/технічні блоки типу [m1], [c], але НЕ заголовки POS типу [ NOUN ]
    text = re.sub(r'\[(?![ ]*(NOUN|VERB|ADJECTIVE|ADVERB|PREPOSITION|CONJUNCTION|PRONOUN|INTERJECTION|NUMERAL|PHRASAL VERB)[ ]*\])[^]]*\]', '', text)
    text = text.replace('\\n', '\n').replace('\r\n', '\n').replace('\r', '\n')

    # --- Нові правила очищення / тегування ---
    # Повний список абревіатур, які зустрічаються в словниках
    # ВАЖЛИВО: \b не працює з кирилицею, тому використовуємо (?:^|[^а-яіїєґА-ЯІЇЄҐ])
    # Формат: (regex_pattern, display_text)

    # Функція для створення regex-патерну для кирилічних абревіатур
    def _cyrillic_word_pattern(abbr: str) -> str:
        """Створює regex для кирилічної абревіатури з правильними межами слів."""
        # Екрануємо крапку якщо є
        escaped = re.escape(abbr)
        # Межа: початок рядка або не-кирилічний символ
        return r'(?:^|(?<=[^а-яіїєґА-ЯІЇЄҐA-Za-z]))' + escaped + r'(?=[^а-яіїєґА-ЯІЇЄҐA-Za-z]|$)'

    ABBREVIATIONS = [
        # Стилістичні позначки
        (_cyrillic_word_pattern('розм.'), 'розм.'),       # розмовне
        (_cyrillic_word_pattern('книжк.'), 'книжк.'),     # книжне
        (_cyrillic_word_pattern('поет.'), 'поет.'),       # поетичне
        (_cyrillic_word_pattern('жарт.'), 'жарт.'),       # жартівливе
        (_cyrillic_word_pattern('ірон.'), 'ірон.'),       # іронічне
        (_cyrillic_word_pattern('зневажл.'), 'зневажл.'), # зневажливе
        (_cyrillic_word_pattern('вульг.'), 'вульг.'),     # вульгарне
        (_cyrillic_word_pattern('прост.'), 'прост.'),     # просторічне
        (_cyrillic_word_pattern('діал.'), 'діал.'),       # діалектне
        (_cyrillic_word_pattern('застар.'), 'застар.'),   # застаріле
        (_cyrillic_word_pattern('рідко'), 'рідко'),        # рідковживане

        # Галузеві позначки
        (_cyrillic_word_pattern('мор.'), 'мор.'),         # морський термін
        (_cyrillic_word_pattern('військ.'), 'військ.'),   # військовий
        (_cyrillic_word_pattern('зоол.'), 'зоол.'),       # зоологія
        (_cyrillic_word_pattern('бот.'), 'бот.'),         # ботаніка
        (_cyrillic_word_pattern('мед.'), 'мед.'),         # медицина
        (_cyrillic_word_pattern('юр.'), 'юр.'),           # юридичний
        (_cyrillic_word_pattern('тех.'), 'тех.'),         # технічний
        (_cyrillic_word_pattern('фіз.'), 'фіз.'),         # фізика
        (_cyrillic_word_pattern('хім.'), 'хім.'),         # хімія
        (_cyrillic_word_pattern('матем.'), 'матем.'),     # математика
        (_cyrillic_word_pattern('муз.'), 'муз.'),         # музика
        (_cyrillic_word_pattern('спорт.'), 'спорт.'),     # спорт
        (_cyrillic_word_pattern('авіа.'), 'авіа.'),       # авіація
        (_cyrillic_word_pattern('ел.'), 'ел.'),           # електрика
        (_cyrillic_word_pattern('рел.'), 'рел.'),         # релігія
        (_cyrillic_word_pattern('біол.'), 'біол.'),       # біологія
        (_cyrillic_word_pattern('геол.'), 'геол.'),       # геологія
        (_cyrillic_word_pattern('екон.'), 'екон.'),       # економіка
        (_cyrillic_word_pattern('політ.'), 'політ.'),     # політика

        # Географічні позначки
        (_cyrillic_word_pattern('амер.'), 'амер.'),       # американізм
        (_cyrillic_word_pattern('брит.'), 'брит.'),       # британізм
        (_cyrillic_word_pattern('шотл.'), 'шотл.'),       # шотландізм
        (_cyrillic_word_pattern('австрал.'), 'австрал.'), # австралійський

        # Граматичні позначки (латинські - використовують \b)
        (r'\bpl\b', 'мн.'),             # множина (plural)
        (r'\bsg\b', 'одн.'),            # однина (singular)
        (_cyrillic_word_pattern('перен.'), 'перен.'),     # переносне значення
        (_cyrillic_word_pattern('букв.'), 'букв.'),       # буквально
        (_cyrillic_word_pattern('збірн.'), 'збірн.'),     # збірне
        (_cyrillic_word_pattern('скор.'), 'скор.'),       # скорочення
        (r'\battr\b', 'означ.'),        # attributive / означальне
        (r'\bpred\b', 'присуд.'),       # predicative / присудкове
    ]

    # Заміна 'тж' на 'також' перед тегуванням (з правильними межами для кирилиці)
    text = re.sub(r'(?:^|(?<=[^а-яіїєґА-ЯІЇЄҐ]))тж(?=[^а-яіїєґА-ЯІЇЄҐ]|$)', 'також', text, flags=re.IGNORECASE)

    # Заміна 'напр.' на 'наприклад'
    text = re.sub(r'(?:^|(?<=[^а-яіїєґА-ЯІЇЄҐ]))напр\.(?=[^а-яіїєґА-ЯІЇЄҐ]|$)', 'наприклад', text, flags=re.IGNORECASE)

    # Заміна 'і т.п.' / 'і т.д.' / 'etc.' на повні форми
    text = re.sub(r'і т\.п\.', 'і тому подібне', text, flags=re.IGNORECASE)
    text = re.sub(r'і т\.д\.', 'і так далі', text, flags=re.IGNORECASE)
    text = re.sub(r'\betc\.\b', 'тощо', text, flags=re.IGNORECASE)

    # Обернемо знайдені абревіатури в [аббр.] для візуального виділення
    def _tag_abbr(abbr_text: str) -> str:
        """Обгортає абревіатуру в квадратні дужки для візуального виділення."""
        return f'[{abbr_text}]'

    # Застосуємо для всіх абревіатур зі списку
    for pattern, display_text in ABBREVIATIONS:
        text = re.sub(pattern, _tag_abbr(display_text), text, flags=re.IGNORECASE)

    # Заміна phrasal verbs
    text = re.sub(
        r'(\d+\.\s*)?(phrasal\s+v|ph\.?\s*v)\b\s*',
        lambda m: f'\n\n{POS_HEADERS.get("phrasal v", "PHRASAL VERB")}\n   ',
        text,
        flags=re.IGNORECASE
    )

    # Заміна частин мови
    pos_pattern = r'(\d+\.\s*)?\b(noun|verb|adj(?:ective)?|adv(?:erb)?|prep(?:osition)?|conj(?:unction)?|pron(?:oun)?|int(?:erjection)?|num(?:eral)?|n|v)\b(?:\s+|(?=\s))'

    def replace_pos(match):
        pos = match.group(2).lower()
        if pos in ['n', 'noun']:
            key = 'n'
        elif pos in ['v', 'verb']:
            key = 'v'
        elif pos.startswith('adj'):
            key = 'adj'
        elif pos.startswith('adv'):
            key = 'adv'
        elif pos.startswith('prep'):
            key = 'prep'
        elif pos.startswith('conj'):
            key = 'conj'
        elif pos.startswith('pron'):
            key = 'pron'
        elif pos.startswith('int'):
            key = 'int'
        elif pos.startswith('num'):
            key = 'num'
        else:
            key = pos
        header = POS_HEADERS.get(key, pos.upper())
        return f'\n\n[ {header} ]\n   '

    text = re.sub(pos_pattern, replace_pos, text, flags=re.IGNORECASE)
    text = re.sub(r'^\s*\d+\.\s*', '', text, flags=re.MULTILINE)

    # Форматування відступів
    lines = text.split('\n')
    formatted_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if formatted_lines and formatted_lines[-1] != '':
                formatted_lines.append('')
            continue
        # Перевіряємо чи це заголовок частини мови (формат: [ NOUN ])
        is_header = stripped.startswith('[') and stripped.endswith(']')
        if is_header:
            formatted_lines.append(stripped)
        else:
            if not stripped.startswith('   '):
                formatted_lines.append(f'   {stripped}')
            else:
                formatted_lines.append(stripped)

    # Повертаємо готовий текст
    return '\n'.join(formatted_lines)


class StatusIndicator(ctk.CTkFrame):
    """Індикатор статусу з'єднання з кольоровою точкою."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.dot = ctk.CTkLabel(
            self,
            text="●",
            font=("Segoe UI", 16),
            text_color=COLORS["danger"]
        )
        self.dot.pack(side="left", padx=(0, 5))

        self.label = ctk.CTkLabel(
            self,
            text="Offline",
            font=("Segoe UI", 12),
            text_color=COLORS["text_secondary"]
        )
        self.label.pack(side="left")

    def set_online(self):
        self.dot.configure(text_color=COLORS["success"])
        self.label.configure(text="Online", text_color=COLORS["success"])

    def set_offline(self):
        self.dot.configure(text_color=COLORS["danger"])
        self.label.configure(text="Offline", text_color=COLORS["danger"])

    def set_connecting(self):
        self.dot.configure(text_color=COLORS["warning"])
        self.label.configure(text="Connecting...", text_color=COLORS["warning"])


# --- Відомі скорочення для badge ---
KNOWN_ABBREVIATIONS = {
    'юр.': 'Legal',
    'біол.': 'Biology',
    'мед.': 'Medicine',
    'тех.': 'Tech',
    'рел.': 'Religion',
    'іст.': 'History',
    'муз.': 'Music',
    'арх.': 'Architecture',
    'хім.': 'Chemistry',
    'фіз.': 'Physics',
    'мат.': 'Math',
    'бот.': 'Botany',
    'зоол.': 'Zoology',
    'авіа.': 'Aviation',
    'воєн.': 'Military',
    'мор.': 'Maritime',
    'комп.': 'Computing',
    'розм.': 'Colloquial',
    'книжн.': 'Literary',
    'заст.': 'Obsolete',
    'діал.': 'Dialect',
    'pl': 'Plural',
    'sg': 'Singular',
    'attr': 'Attributive',
    'predic': 'Predicative',
    'амер.': 'American',
    'брит.': 'British',
}



class ResultCard(ctk.CTkFrame):
    """
    Картка результату перекладу (English → Ukrainian).
    Спрощена версія без reverse search.
    """

    def __init__(self, master, headword: str, definition: str, favorite_callback=None, is_favorite=False, **kwargs):
        """
        Args:
            master: Батьківський віджет
            headword: Англійське слово (заголовок)
            definition: Українське визначення
            favorite_callback: Callback function(word, definition, is_favorite) для toggle favorites
            is_favorite: Початковий стан улюбленого
        """
        # Видаляємо search_query якщо передано (для сумісності)
        kwargs.pop('search_query', None)
        
        self.favorite_callback = favorite_callback
        self.is_favorite = is_favorite

        super().__init__(
            master,
            fg_color=COLORS["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border"],
            **kwargs
        )

        self.headword = html.unescape(headword).strip()
        self.definition = html.unescape(definition)

        # Debug logging
        logger.debug(f"ResultCard: headword='{self.headword}'")

        # Головний контейнер
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=24, pady=12)

        # === HEADER: Слово (великий, bold, білий) + Copy ===
        header_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 5))  # Minimal bottom padding

        # Заголовок - англійське слово
        display_word = self.headword.title() if self.headword else "Result"

        self.word_label = ctk.CTkLabel(
            header_frame,
            text=display_word,
            font=("Segoe UI", 32, "bold"),
            text_color=COLORS["title_color"],  # Темно-синій для Light Mode
            anchor="w"
        )
        self.word_label.pack(side="left", anchor="w", pady=(20, 5))  # Top padding okay, bottom minimal

        # Spacer
        spacer = ctk.CTkFrame(header_frame, fg_color="transparent", width=20)
        spacer.pack(side="left", fill="x", expand=True)

        # Star button for favorites (if callback provided)
        if self.favorite_callback:
            star_text = "⭐" if self.is_favorite else "☆"
            self.star_btn = ctk.CTkButton(
                header_frame,
                text=star_text,
                width=40,
                height=36,
                font=("Segoe UI", 16),
                fg_color="transparent",
                hover_color=COLORS["border"],
                text_color="#FFD700" if self.is_favorite else COLORS["text_muted"],
                corner_radius=8,
                command=self._toggle_favorite
            )
            self.star_btn.pack(side="right", padx=(0, 10))

        # Copy button
        self.copy_btn = ctk.CTkButton(
            header_frame,
            text="📋 Copy",
            width=100,
            height=36,
            font=("Segoe UI", 12),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#FFFFFF",
            corner_radius=8,
            command=self._copy_to_clipboard
        )
        self.copy_btn.pack(side="right")


        # Розділювач
        separator = ctk.CTkFrame(main_container, fg_color=COLORS["border"], height=1)
        separator.pack(fill="x", pady=(0, 0))  # Minimal padding

        # === CONTENT: Regular Frame для визначень ===
        self.content_frame = ctk.CTkFrame(
            main_container,
            fg_color="transparent",
            corner_radius=0
        )
        self.content_frame.pack(fill="both", expand=True, pady=(0, 20))  # Start immediately below title

        # Парсимо та відображаємо
        self._parse_and_render(self.definition)

    def _parse_and_render(self, text):
        """Smart Parser: розбирає текст та створює структуровані віджети."""
        lines = text.split('\n')

        for line in lines:
            stripped = line.strip()
            if not stripped:
                spacer = ctk.CTkFrame(self.content_frame, fg_color="transparent", height=8)
                spacer.pack(fill="x")
                continue

            line_type = self._classify_line(stripped)

            if line_type == "pos_header":
                self._render_pos_header(stripped)
            elif line_type == "definition":
                self._render_definition(stripped)
            elif line_type == "example":
                self._render_example(stripped)
            else:
                self._render_regular(stripped)

    def _classify_line(self, line):
        """Класифікує рядок за типом."""
        if line.startswith('[') and line.endswith(']'):
            return "pos_header"
        if re.match(r'^\d+[.)]\s', line):
            return "definition"
        if line.startswith('~') or line.startswith('-') or ' — ' in line or line.startswith('   '):
            return "example"
        return "regular"

    def _render_pos_header(self, text):
        """Рендеринг заголовка частини мови."""
        pos_text = text.strip('[]').strip()

        header_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(12, 6))

        accent_line = ctk.CTkFrame(header_frame, fg_color="#10B981", width=4, height=20)
        accent_line.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            header_frame,
            text=pos_text,
            font=("Segoe UI", 14, "bold"),
            text_color="#10B981",
            anchor="w"
        ).pack(side="left")

    def _render_definition(self, text):
        """Рендеринг визначення з номером."""
        def_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        def_frame.pack(fill="x", pady=4)

        match = re.match(r'^(\d+[.)])\s*(.*)$', text)
        if match:
            number = match.group(1)
            rest = match.group(2)
        else:
            number = ""
            rest = text

        if number:
            ctk.CTkLabel(
                def_frame,
                text=number,
                font=("Segoe UI", 14, "bold"),
                text_color="#3B82F6",
                width=35,
                anchor="w"
            ).pack(side="left")

        ctk.CTkLabel(
            def_frame,
            text=rest,
            font=("Segoe UI", 16),
            text_color=COLORS["text_primary"],
            anchor="w",
            wraplength=550,
            justify="left"
        ).pack(side="left", fill="x", expand=True)

    def _render_example(self, text):
        """Рендеринг прикладу (indented, italic)."""
        example_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        example_frame.pack(fill="x", pady=2, padx=(35, 0))

        if ' — ' in text:
            parts = text.split(' — ', 1)
            english_part = parts[0].strip().lstrip('~- ')
            ukr_part = parts[1].strip() if len(parts) > 1 else ""

            ctk.CTkLabel(
                example_frame,
                text=english_part,
                font=("Segoe UI", 12, "italic"),
                text_color="#60A5FA",
                anchor="w"
            ).pack(side="left")

            ctk.CTkLabel(
                example_frame,
                text=" — ",
                font=("Segoe UI", 12),
                text_color=COLORS["text_muted"],
                anchor="w"
            ).pack(side="left")

            ctk.CTkLabel(
                example_frame,
                text=ukr_part,
                font=("Segoe UI", 15),  # EX: Example text (Ukrainian part)
                text_color=COLORS["text_secondary"],
                anchor="w",
                wraplength=450,
                justify="left"
            ).pack(side="left", fill="x", expand=True)
        else:
            display_text = text.lstrip('~- ').strip()
            ctk.CTkLabel(
                example_frame,
                text=f"→ {display_text}",
                font=("Segoe UI", 15, "italic"),  # EX: Example text
                text_color=COLORS["text_secondary"],
                anchor="w",
                wraplength=500,
                justify="left"
            ).pack(side="left", fill="x", expand=True)

    def _render_regular(self, text):
        """Рендеринг звичайного тексту."""
        ctk.CTkLabel(
            self.content_frame,
            text=text,
            font=("Segoe UI", 12),
            text_color=COLORS["text_secondary"],
            anchor="w",
            wraplength=550,
            justify="left"
        ).pack(fill="x", pady=2)

    def _copy_to_clipboard(self):
        """Копіювання ТІЛЬКИ тексту перекладу (без headword та заголовків POS)."""
        try:
            # Очищаємо текст від заголовків та форматування
            clean_text = self._get_clean_translation()

            self.clipboard_clear()
            self.clipboard_append(clean_text)
            self.copy_btn.configure(text="✓ Copied")
            self.after(1500, lambda: self.copy_btn.configure(text="📋 Copy"))
            logger.info(f"Скопійовано переклад для: '{self.headword}'")
        except Exception as e:
            logger.error(f"Помилка копіювання: {e}")

    def _get_clean_translation(self) -> str:
        """
        Отримати чистий текст перекладу без заголовків POS та headword.

        Returns:
            str: Чистий текст перекладу для копіювання.
        """
        text = self.definition

        # Видаляємо заголовки частин мови типу [ NOUN ], [ VERB ] тощо
        text = re.sub(r'\[\s*(NOUN|VERB|ADJECTIVE|ADVERB|PREPOSITION|CONJUNCTION|PRONOUN|INTERJECTION|NUMERAL|PHRASAL VERB)\s*\]', '', text)

        # Видаляємо headword якщо він на початку рядка
        if self.headword:
            # Видаляємо headword на початку (можливо з пробілами та переносами)
            pattern = rf'^\s*{re.escape(self.headword)}\s*\n?'
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # Очищаємо зайві переноси рядків та пробіли
        text = re.sub(r'\n{3,}', '\n\n', text)  # Макс 2 переноси
        text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)  # Видаляємо пробіли на початку рядків
        text = text.strip()

        return text

    def _toggle_favorite(self):
        """Toggle favorite status for this word."""
        if not self.favorite_callback:
            return
        
        # Toggle the state
        self.is_favorite = not self.is_favorite
        
        # Update visual state immediately
        star_text = "⭐" if self.is_favorite else "☆"
        self.star_btn.configure(
            text=star_text,
            text_color="#FFD700" if self.is_favorite else COLORS["text_muted"]
        )
        
        # Call the callback with word, definition, and new favorite status
        # This will update the database
        self.favorite_callback(self.headword, self.definition, self.is_favorite)


class HistoryItem(ctk.CTkButton):
    """Клікабельний елемент історії пошуку."""

    def __init__(self, master, word, callback, **kwargs):
        super().__init__(
            master,
            text=f"🕒 {word}",
            font=("Segoe UI", 12),
            fg_color="transparent",
            text_color=COLORS["text_secondary"],
            hover_color=COLORS["border"],
            anchor="w",
            command=lambda: callback(word),
            **kwargs
        )


class ModernDictionaryApp(ctk.CTk):
    """
    Головне вікно застосунку з принципом "70% Golden Mean".

    Args:
        client (DictionaryClient): Клієнт для мережевих операцій.
    """

    def __init__(self, client: DictionaryClient = None):
        super().__init__()

        # === Примусово Light Mode ===
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        # Window Configuration
        self.title("🐦 E-Dictionary Pro")
        self.geometry("1100x700")
        self.minsize(900, 600)
        self.configure(fg_color=COLORS["bg_main"])

        # Для drag вікна
        self._drag_data = {"x": 0, "y": 0}

        # Network client (можна передати ззовні або створити новий)
        self.network = client if client else DictionaryClient()
        # Keep self.client for backward compatibility
        self.client = self.network
        # Database Manager для історії та налаштувань (OOP Композиція)
        # Змушуємо використовувати файлову базу для збереження історії
        self.db = DatabaseManager("dictionary_history.db")
        self._auto_connect_attempted = False
        
        # Store current word for favorites toggle
        self.current_headword = None
        self.current_definition = None
        
        # Thread tracking for network operations
        self._network_threads = []  # Список активних мережевих потоків

        # Create UI
        self._create_custom_title_bar()
        self._create_layout()
        self._bind_shortcuts()

        # Автоматична спроба підключення при старті
        # (не ставимо фокус одразу - поле disabled до підключення)
        self.after(500, self._try_auto_connect)
        
        # Налаштування обробника закриття вікна для безпечного завершення
        self.protocol("WM_DELETE_WINDOW", self._close_window)

        logger.info("Застосунок успішно запущено")

    def _try_auto_connect(self):
        """Автоматична спроба підключення при запуску (в фоновому потоці)."""
        if self._auto_connect_attempted:
            return

        self._auto_connect_attempted = True

        # Показуємо що намагаємось підключитись
        self.status_indicator.set_connecting()
        self.connect_btn.configure(text="...", state="disabled")
        self.update()

        host = self.host_entry.get().strip() or "127.0.0.1"
        try:
            port = int(self.port_entry.get().strip() or "8080")
        except ValueError:
            port = 8080

        self.network.host = host
        self.network.port = port

        # Запускаємо підключення в фоновому потоці
        def connect_thread():
            try:
                connected = self.network.connect()
                # Оновлюємо UI в головному потоці
                self.after(0, lambda: self._on_auto_connect_result(connected, host, port))
            except Exception as e:
                logger.error(f"[UI] Помилка автопідключення: {e}")
                self.after(0, lambda: self._on_auto_connect_result(False, host, port))
        
        thread = threading.Thread(target=connect_thread, daemon=True)
        thread.start()
        self._network_threads.append(thread)
    
    def _on_auto_connect_result(self, connected: bool, host: str, port: int):
        """Обробка результату автопідключення (викликається в UI потоці)."""
        if connected:
            # Успішно підключено
            self.status_indicator.set_online()
            self.connect_btn.configure(text="Disconnect", state="normal", fg_color="#EF4444", hover_color="#DC2626")
            self._update_ui_state(True)
            self._add_to_log_panel(f"✅ Автопідключення до {host}:{port}")
            # Оновлюємо start screen
            self._show_start_screen()
            self._refresh_word_of_the_day()
        else:
            # Не вдалося підключитися
            self.status_indicator.set_offline()
            self.connect_btn.configure(text="Connect", state="normal", fg_color="#007AFF")
            self._update_ui_state(False)
            self._add_to_log_panel(f"❌ Сервер недоступний: {host}:{port}")
            # Показуємо popup з попередженням
            self.after(100, self._show_connection_warning)

    def _create_custom_title_bar(self):
        """Створення кастомного title bar з навігацією."""
        self.title_bar = ctk.CTkFrame(
            self,
            fg_color="#1E1E1E",
            height=40,
            corner_radius=0
        )
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)

        # Bind для перетягування вікна
        self.title_bar.bind("<Button-1>", self._start_drag)
        self.title_bar.bind("<B1-Motion>", self._on_drag)

        # === ЛІВА ЧАСТИНА: Логотип ===
        title_left = ctk.CTkFrame(self.title_bar, fg_color="transparent")
        title_left.pack(side="left", padx=15)

        ctk.CTkLabel(
            title_left,
            text="🐦",
            font=("Segoe UI", 16),
            text_color="#FFFFFF"
        ).pack(side="left", padx=(0, 8))

        title_label = ctk.CTkLabel(
            title_left,
            text="E-Dictionary Pro",
            font=("Segoe UI", 12, "bold"),
            text_color="#FFFFFF"
        )
        title_label.pack(side="left")
        title_label.bind("<Button-1>", self._start_drag)
        title_label.bind("<B1-Motion>", self._on_drag)

        # === ПРАВА ЧАСТИНА: Кнопки керування ===
        btn_frame = ctk.CTkFrame(self.title_bar, fg_color="transparent")
        btn_frame.pack(side="right", padx=5)

        # Minimize
        ctk.CTkButton(
            btn_frame, text="─", width=40, height=30,
            font=("Segoe UI", 14), fg_color="transparent",
            hover_color="#3a3a3a", text_color="#FFFFFF",
            corner_radius=0, command=self._minimize_window
        ).pack(side="left", padx=2)

        # Maximize
        self.maximize_btn = ctk.CTkButton(
            btn_frame, text="□", width=40, height=30,
            font=("Segoe UI", 12), fg_color="transparent",
            hover_color="#3a3a3a", text_color="#FFFFFF",
            corner_radius=0, command=self._toggle_maximize
        )
        self.maximize_btn.pack(side="left", padx=2)

        # Close
        ctk.CTkButton(
            btn_frame, text="✕", width=40, height=30,
            font=("Segoe UI", 12), fg_color="transparent",
            hover_color="#e81123", text_color="#FFFFFF",
            corner_radius=0, command=self._close_window
        ).pack(side="left", padx=2)

        # === ЦЕНТРАЛЬНА ЧАСТИНА: Навігаційні кнопки ===
        nav_frame = ctk.CTkFrame(self.title_bar, fg_color="transparent")
        nav_frame.pack(side="right", padx=20)


        # Add Word Button (+) - Square icon-only
        self.add_word_btn = ctk.CTkButton(
            nav_frame,
            text="+",
            width=40,
            height=40,
            font=("Segoe UI", 20, "bold"),
            fg_color="transparent",
            hover_color="#3a3a3a",
            text_color="#FFFFFF",
            corner_radius=6,
            command=self._show_add_word_dialog
        )
        self.add_word_btn.pack(side="right", padx=5)

        # History & Favorites Button (🕒) - Square icon-only
        self.history_btn = ctk.CTkButton(
            nav_frame,
            text="🕒",
            width=40,
            height=40,
            font=("Segoe UI", 16),
            fg_color="transparent",
            hover_color="#3a3a3a",
            text_color="#FFFFFF",
            corner_radius=6,
            command=self._show_history_favorites_popup
        )
        self.history_btn.pack(side="right", padx=5)

        # Help Button - Square icon-only
        ctk.CTkButton(
            nav_frame,
            text="❓",
            width=40,
            height=40,
            font=("Segoe UI", 16),
            fg_color="transparent",
            hover_color="#3a3a3a",
            text_color="#FFFFFF",
            corner_radius=6,
            command=self._show_about
        ).pack(side="right", padx=5)

    def _start_drag(self, event):
        """Початок перетягування вікна."""
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag(self, event):
        """Перетягування вікна."""
        x = self.winfo_x() - self._drag_data["x"] + event.x
        y = self.winfo_y() - self._drag_data["y"] + event.y
        self.geometry(f"+{x}+{y}")

    def _minimize_window(self):
        """Згортання вікна."""
        self.iconify()

    def _toggle_maximize(self):
        """Максимізація/відновлення вікна."""
        if self.state() == 'zoomed':
            self.state('normal')
            self.maximize_btn.configure(text="□")
        else:
            self.state('zoomed')
            self.maximize_btn.configure(text="❐")

    def _close_window(self):
        """Безпечне закриття вікна з очищенням ресурсів."""
        try:
            # Відключаємося від сервера
            if self.network.connected:
                try:
                    self.network.disconnect()
                except Exception as e:
                    logger.warning(f"[UI] Помилка відключення: {e}")
            
            # Очищаємо базу даних
            if hasattr(self, 'db') and self.db:
                try:
                    self.db.close()
                except Exception as e:
                    logger.warning(f"[UI] Помилка закриття БД: {e}")
            
            # Очікуємо завершення активних мережевих потоків (з таймаутом)
            for thread in self._network_threads[:]:  # Копіюємо список
                if thread.is_alive():
                    thread.join(timeout=0.5)  # Максимум 0.5 секунди на потік
                    if thread.is_alive():
                        logger.warning(f"[UI] Мережевий потік не завершився вчасно")
            
            logger.info("[UI] Застосунок закривається")
        except Exception as e:
            logger.error(f"[UI] Помилка при закритті: {e}")
        finally:
            # Завжди закриваємо вікно
            try:
                self.destroy()
            except Exception:
                pass

    def _create_layout(self):
        """Створення Single Column layout."""
        self._create_top_bar()

        # Головний контейнер - одна колонка по центру
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=40, pady=(0, 20))

        # Контейнер для контенту (центрований)
        self.content_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True)

        # Показуємо start screen з Word of the Day
        self._show_start_screen()

    def _create_top_bar(self):
        """Створення компактної верхньої панелі з пошуком."""
        top_bar = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=0, height=80)
        top_bar.pack(fill="x", padx=0, pady=0)
        top_bar.pack_propagate(False)

        inner = ctk.CTkFrame(top_bar, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=40, pady=15)

        # === ЛІВА ЧАСТИНА: Пошук ===
        search_frame = ctk.CTkFrame(inner, fg_color="transparent")
        search_frame.pack(side="left", fill="x", expand=True)

        # Search Entry - ЧИСТА ініціалізація без StringVar
        self.search_var = ctk.StringVar(value="")
        self.search_entry = ctk.CTkEntry(
            search_frame,
            height=50,
            width=400,
            font=("Segoe UI", 16),
            placeholder_text="",
            placeholder_text_color=COLORS["text_muted"],
            text_color=COLORS["text_primary"],
            fg_color=COLORS["bg_card"],
            border_color=COLORS["border"],
            border_width=2,
            corner_radius=12,
            textvariable=self.search_var
            # НЕ ставимо state="disabled" тут - зробимо це окремо
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 15))
        self.search_entry.bind('<Return>', lambda e: self._translate())

        # Блокуємо ПІСЛЯ створення щоб placeholder працював коректно
        self.search_entry.configure(state="disabled")

        # Translate Button - з відступом
        self.search_btn = ctk.CTkButton(
            search_frame,
            text="🔍 Translate",
            width=150,
            height=50,
            font=("Segoe UI", 14, "bold"),
            fg_color=COLORS["text_muted"],  # Сірий коли offline
            hover_color=COLORS["text_muted"],
            corner_radius=12,
            command=self._translate,
            state="disabled"  # Заблоковано до підключення
        )
        self.search_btn.pack(side="left", padx=(0, 20))

        # === ПРАВА ЧАСТИНА: Connection ===
        conn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        conn_frame.pack(side="right")

        self.status_indicator = StatusIndicator(conn_frame)
        self.status_indicator.pack(side="right", padx=(15, 0))

        self.connect_btn = ctk.CTkButton(
            conn_frame,
            text="Connect",
            width=90,
            height=40,
            font=("Segoe UI", 11, "bold"),
            fg_color="#007AFF",
            hover_color="#0056B3",
            corner_radius=8,
            command=self._toggle_connection
        )
        self.connect_btn.pack(side="right", padx=(10, 0))

        self.port_entry = ctk.CTkEntry(
            conn_frame,
            width=55,
            height=40,
            font=("Segoe UI", 11),
            text_color=COLORS["text_primary"],
            fg_color=COLORS["bg_card"],
            border_color=COLORS["border"]
        )
        self.port_entry.insert(0, "8080")
        self.port_entry.pack(side="right", padx=(5, 0))

        ctk.CTkLabel(conn_frame, text=":", font=("Segoe UI", 11), text_color=COLORS["text_secondary"]).pack(side="right")

        self.host_entry = ctk.CTkEntry(
            conn_frame,
            width=100,
            height=40,
            font=("Segoe UI", 11),
            text_color=COLORS["text_primary"],
            fg_color=COLORS["bg_card"],
            border_color=COLORS["border"]
        )
        self.host_entry.insert(0, "127.0.0.1")
        self.host_entry.pack(side="right")

    def _show_start_screen(self):
        """Показати стартовий екран з Word of the Day."""
        # Очищаємо контент
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        # Центрований контейнер
        center_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        center_frame.place(relx=0.5, rely=0.4, anchor="center")

        # Привітання
        ctk.CTkLabel(
            center_frame,
            text="👋 Вітаємо в E-Dictionary Pro",
            font=("Segoe UI", 24, "bold"),
            text_color=COLORS["text_primary"]
        ).pack(pady=(80, 10))

        # Підказка залежно від статусу підключення
        if self.network.connected:
            hint_text = "Введіть слово вище для перекладу"
            hint_color = COLORS["text_secondary"]
        else:
            hint_text = "⚠️ Натисніть 'Connect' щоб підключитися до сервера"
            hint_color = "#F59E0B"  # Warning yellow

        ctk.CTkLabel(
            center_frame,
            text=hint_text,
            font=("Segoe UI", 14),
            text_color=hint_color
        ).pack(pady=(0, 40))

        # === WORD OF THE DAY CARD ===
        wotd_card = ctk.CTkFrame(
            center_frame,
            fg_color=COLORS["bg_card"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"]
        )
        wotd_card.pack(pady=20, ipadx=40, ipady=20)

        # Header
        wotd_header = ctk.CTkFrame(wotd_card, fg_color="transparent")
        wotd_header.pack(fill="x", padx=30, pady=(20, 10))

        ctk.CTkLabel(
            wotd_header,
            text="✨ Слово дня",
            font=("Segoe UI", 14, "bold"),
            text_color=COLORS["text_secondary"]
        ).pack(side="left")

        # Copy button
        self.wotd_copy_btn = ctk.CTkButton(
            wotd_header,
            text="📋",
            width=30,
            height=30,
            font=("Segoe UI", 14),
            fg_color="transparent",
            hover_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            corner_radius=6,
            command=self._copy_wotd
        )
        self.wotd_copy_btn.pack(side="right", padx=(5, 0))

        # Refresh button
        ctk.CTkButton(
            wotd_header,
            text="🔄",
            width=30,
            height=30,
            font=("Segoe UI", 14),
            fg_color="transparent",
            hover_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            corner_radius=6,
            command=self._refresh_word_of_the_day
        ).pack(side="right")

        # Word
        self.wotd_word_label = ctk.CTkLabel(
            wotd_card,
            text="Hello",
            font=("Segoe UI", 28, "bold"),
            text_color="#10B981"  # Emerald - добре виглядає на білому
        )
        self.wotd_word_label.pack(padx=30, pady=(10, 5))

        # Definition - CTkTextbox для скролінгу довгих визначень
        # Wrap in frame for internal padding
        textbox_frame = ctk.CTkFrame(wotd_card, fg_color="transparent")
        textbox_frame.pack(padx=30, pady=(0, 20), fill="x")
        
        self.wotd_definition_textbox = ctk.CTkTextbox(
            textbox_frame,
            font=("Segoe UI", 14),
            text_color=COLORS["text_primary"],  # Чорний для Light Mode
            fg_color="transparent",
            wrap="word",
            height=100,  # Збільшено для кращого відображення
            width=450,
            activate_scrollbars=True,
            border_width=0
        )
        self.wotd_definition_textbox.pack(padx=20, pady=20, fill="both", expand=True)
        self.wotd_definition_textbox.insert("1.0", "Привіт! Вітаємо вас у E-Dictionary Pro!'")
        self.wotd_definition_textbox.configure(state="disabled")

        # Hint
        ctk.CTkLabel(
            center_frame,
            text="💡 Натисніть 🕒 для перегляду історії пошуку та збережених слів",
            font=("Segoe UI", 11),
            text_color=COLORS["text_muted"]
        ).pack(pady=(30, 0))

        # Спробуємо завантажити слово дня
        self.after(500, self._refresh_word_of_the_day)

    def _show_results_screen(self):
        """Показати екран результатів (SCROLLABLE FIX)."""
        # Очищаємо контент
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        # Results Container
        self.results_container = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.results_container.pack(fill="both", expand=True, padx=20, pady=10)

        # Results Header
        results_header = ctk.CTkFrame(self.results_container, fg_color="transparent")
        results_header.pack(fill="x", pady=(0, 10)) # Менший відступ знизу

        ctk.CTkLabel(
            results_header,
            text="📋 Результати",
            font=("Segoe UI", 18, "bold"),
            text_color=COLORS["text_secondary"]
        ).pack(side="left")

        # Back to home button
        ctk.CTkButton(
            results_header,
            text="🏠 На головну",
            width=140,
            height=36,
            font=("Segoe UI", 12),
            fg_color=COLORS["border"],
            hover_color="#4a4a4a",
            text_color=COLORS["text_secondary"],
            corner_radius=8,
            command=self._show_start_screen
        ).pack(side="right", padx=(10, 0))

        # === CRITICAL FIX: SCROLLABLE FRAME ===
        # Використовуємо CTkScrollableFrame замість звичайного Frame
        self.results_frame = ctk.CTkScrollableFrame(
            self.results_container,
            fg_color="transparent",
            corner_radius=8,
            orientation="vertical" # Вертикальна прокрутка
        )
        self.results_frame.pack(fill="both", expand=True, pady=(10, 0))


    def save_new_word(self, word: str, definition: str, window, error_label=None):
        """
        Зберегти нове слово до словника.
        
        Args:
            word: Слово для додавання
            definition: Визначення слова
            window: Вікно popup для закриття після збереження
            error_label: Label для відображення помилок (опціонально)
        """
        # Clear any previous error message
        if error_label:
            error_label.configure(text="")
        
        # Validate input
        if not word or not definition:
            messagebox.showwarning("Validation Error", "Please fill in both Headword and Definition fields!")
            return
        
        # Send ADD_WORD command via network
        if self.network.connected:
            response = self.network.send_command(f"ADD_WORD|{word}|{definition}")
            
            if response and response.startswith("Success"):
                # Show success message
                messagebox.showinfo("Success", f"Word '{word}' has been successfully added to the dictionary!")
                # Close window and show success log
                window.destroy()
                self._add_to_log_panel(f"✅ Saved: {word}")
                logger.info(f"Додано слово: '{word}'")
                # Immediately display the added word with the same renderer as searched words
                # First show results screen, then display translation
                self._show_results_screen()
                # Format: "word|definition" for _display_translation
                self._display_translation(word, f"{word}|{definition}")
            elif response and response.startswith("Error"):
                # Handle error response - show red error label and keep popup open
                error_message = "This word already exists!"
                if error_label:
                    error_label.configure(text=error_message)
                else:
                    # Fallback to messagebox if error_label not provided
                    messagebox.showerror("Error", error_message)
                logger.warning(f"Спроба додати існуюче слово: '{word}'")
            else:
                # Other errors - show messagebox
                messagebox.showerror("Error", f"Failed to add word: {response or 'Unknown error'}")
        else:
            # If offline, show warning
            messagebox.showwarning("Offline", 
                "Cannot save word: not connected to server.\n\n"
                "Please connect first.")
    
    def _show_add_word_dialog(self):
        """
        Показати професійний popup діалог для додавання нового слова.

        Відкриває CTkToplevel вікно з полями для введення слова
        та його перекладу. Виглядає як нативний діалог.
        """
        # Створюємо popup вікно
        popup = ctk.CTkToplevel(self)
        popup.title("Add to Dictionary")
        popup.geometry("480x540")  # Збільшено для tag chips
        popup.resizable(False, False)

        # Центруємо відносно головного вікна
        popup.transient(self)
        popup.grab_set()

        # Налаштовуємо колір фону
        popup.configure(fg_color=COLORS["bg_main"])

        # Головний контейнер
        container = ctk.CTkFrame(popup, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=25, pady=25)

        # Заголовок
        ctk.CTkLabel(
            container,
            text="Add to Dictionary",
            font=("Segoe UI", 20, "bold"),
            text_color=COLORS["text_primary"]
        ).pack(pady=(0, 25))

        # Поле: Headword
        headword_label = ctk.CTkLabel(
            container,
            text="Headword:",
            font=("Segoe UI", 13),
            text_color=COLORS["text_secondary"],
            anchor="w"
        )
        headword_label.pack(fill="x", pady=(0, 5))

        word_entry = ctk.CTkEntry(
            container,
            height=38,
            font=("Segoe UI", 14),
            placeholder_text="Enter word...",
            placeholder_text_color=COLORS["text_muted"],
            corner_radius=8,
            border_width=1,
            border_color=COLORS["border"]
        )
        word_entry.pack(fill="x", pady=(0, 15))

        # Поле: Definition
        definition_label = ctk.CTkLabel(
            container,
            text="Definition:",
            font=("Segoe UI", 13),
            text_color=COLORS["text_secondary"],
            anchor="w"
        )
        definition_label.pack(fill="x", pady=(0, 5))

        # Use Textbox for definition (multi-line, scrollable)
        definition_textbox = ctk.CTkTextbox(
            container,
            height=90,
            font=("Segoe UI", 13),
            corner_radius=8,
            wrap="word",
            border_width=1,
            border_color=COLORS["border"],
            activate_scrollbars=True
        )
        definition_textbox.pack(fill="x", pady=(0, 10))

        # Error label (initially hidden)
        error_label = ctk.CTkLabel(
            container,
            text="",
            font=("Segoe UI", 12),
            text_color=COLORS["danger"],
            anchor="w",
            height=20
        )
        error_label.pack(fill="x", pady=(0, 5))

        # === FORMATTING HELPERS ===
        # Instruction label
        instruction_label = ctk.CTkLabel(
            container,
            text="Formatting Tips: Use tags to colorize parts of speech.",
            font=("Segoe UI", 11),
            text_color=COLORS["text_muted"],
            anchor="w"
        )
        instruction_label.pack(fill="x", pady=(0, 8))

        # Helper function to insert tag at cursor position
        def insert_tag(tag_text: str):
            """Insert tag text at current cursor position in definition textbox."""
            try:
                # Get current cursor position
                cursor_pos = definition_textbox.index("insert")
                # Insert the tag text
                definition_textbox.insert(cursor_pos, tag_text)
                # Move cursor after inserted text
                new_pos = definition_textbox.index(f"{cursor_pos}+{len(tag_text)}c")
                definition_textbox.mark_set("insert", new_pos)
                definition_textbox.see("insert")
                # Focus back to textbox
                definition_textbox.focus()
            except Exception as e:
                logger.warning(f"Error inserting tag: {e}")
                # Fallback: append to end
                definition_textbox.insert("end", tag_text)
                definition_textbox.focus()

        # Chips frame for tag buttons - scrollable row
        chips_frame = ctk.CTkFrame(container, fg_color="transparent")
        chips_frame.pack(fill="x", pady=(0, 20))

        # Inner frame for buttons (will be scrollable if needed)
        chips_inner = ctk.CTkFrame(chips_frame, fg_color="transparent")
        chips_inner.pack(fill="x")

        # Tag buttons (chips) - all 7 tags
        tag_buttons = [
            ("[NOUN]", "[NOUN] "),
            ("[VERB]", "[VERB] "),
            ("[ADJ]", "[ADJ] "),
            ("[ADV]", "[ADV] "),
            ("[PHRASE]", "[PHRASE] "),
            ("[IT]", "[IT] "),
            ("[SCI]", "[SCI] ")
        ]

        for tag_label, tag_text in tag_buttons:
            chip_btn = ctk.CTkButton(
                chips_inner,
                text=tag_label,
                width=60,
                height=26,
                font=("Segoe UI", 10),
                fg_color="#87CEEB",  # Light blue (Sky Blue)
                hover_color="#6BB6FF",  # Slightly darker on hover
                text_color="#FFFFFF",
                corner_radius=12,
                command=lambda t=tag_text: insert_tag(t)
            )
            chip_btn.pack(side="left", padx=(0, 5))

        # Кнопки - Frame для правильного розташування
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 0))  # Додано явний padding

        def cancel():
            """Закрити popup."""
            popup.destroy()

        # Кнопка Cancel (Grey) - явно упакована
        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            height=38,
            font=("Segoe UI", 13),
            fg_color=COLORS["text_muted"],
            hover_color="#5A6268",
            text_color="#FFFFFF",
            corner_radius=8,
            command=cancel
        )
        cancel_btn.pack(side="left", padx=(0, 10))  # Додано явний padding

        # Spacer для відступу між кнопками
        spacer = ctk.CTkFrame(btn_frame, fg_color="transparent", width=20)
        spacer.pack(side="left", fill="x", expand=True)  # Розтягується для вирівнювання

        # Кнопка Save (Green) - явно упакована з правильними параметрами
        save_btn = ctk.CTkButton(
            btn_frame,
            text="Save",
            width=100,
            height=38,
            font=("Segoe UI", 13, "bold"),
            fg_color=COLORS["success"],
            hover_color="#218838",
            text_color="#FFFFFF",
            corner_radius=8,
            command=lambda: self.save_new_word(
                word_entry.get().strip(),
                definition_textbox.get("1.0", "end-1c").strip(),
                popup,
                error_label
            )
        )
        save_btn.pack(side="right", padx=(10, 0))  # Додано явний padding для видимості

        # Bind Enter для збереження (Ctrl+Enter for textbox)
        definition_textbox.bind('<Control-Return>',
            lambda e: self.save_new_word(
                word_entry.get().strip(),
                definition_textbox.get("1.0", "end-1c").strip(),
                popup,
                error_label
            )
        )
        word_entry.bind('<Return>',
            lambda e: definition_textbox.focus()
        )

        # Фокус на перше поле
        word_entry.focus()

    def _show_history_favorites_popup(self):
        """Показати професійний popup з історією та улюбленими словами (CTkTabview)."""
        popup = ctk.CTkToplevel(self)
        popup.title("Saved & History")
        popup.geometry("500x600")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()
        popup.configure(fg_color=COLORS["bg_main"])

        # Header
        header = ctk.CTkFrame(popup, fg_color=COLORS["bg_card"], corner_radius=0)
        header.pack(fill="x")

        ctk.CTkLabel(
            header,
            text="🕒 Saved & History",
            font=("Segoe UI", 18, "bold"),
            text_color=COLORS["text_primary"]
        ).pack(side="left", padx=20, pady=15)

        # Close button
        ctk.CTkButton(
            header,
            text="✕",
            width=32,
            height=32,
            font=("Segoe UI", 13),
            fg_color="transparent",
            text_color=COLORS["text_secondary"],
            hover_color=COLORS["border"],
            corner_radius=6,
            command=popup.destroy
        ).pack(side="right", padx=20, pady=15)

        # Tabview with History and Favorites tabs
        tabview = ctk.CTkTabview(popup, fg_color=COLORS["bg_card"])
        tabview.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Tab 1: History
        history_tab = tabview.add("History")
        history_tab.configure(fg_color=COLORS["bg_main"])

        # Clear history button in History tab
        history_header = ctk.CTkFrame(history_tab, fg_color="transparent")
        history_header.pack(fill="x", padx=12, pady=(12, 8))

        ctk.CTkButton(
            history_header,
            text="Clear History",
            width=110,
            height=32,
            font=("Segoe UI", 11),
            fg_color="transparent",
            text_color=COLORS["text_secondary"],
            hover_color=COLORS["border"],
            corner_radius=6,
            command=lambda: self._clear_history_and_refresh(history_scroll_frame, popup)
        ).pack(side="right")

        # Scrollable frame for history
        history_scroll_frame = ctk.CTkScrollableFrame(history_tab, fg_color="transparent")
        history_scroll_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Tab 2: Favorites
        favorites_tab = tabview.add("Favorites")
        favorites_tab.configure(fg_color=COLORS["bg_main"])

        # Scrollable frame for favorites
        favorites_scroll_frame = ctk.CTkScrollableFrame(favorites_tab, fg_color="transparent")
        favorites_scroll_frame.pack(fill="both", expand=True, padx=12, pady=12)

        # Function to handle word click (closes popup, sets search, triggers translation)
        def search_word(word):
            popup.destroy()
            self.search_entry.delete(0, 'end')
            self.search_entry.insert(0, word)
            # Trigger translation if connected
            if self.network.connected:
                self._translate()
            else:
                messagebox.showwarning("No Connection", "Please connect to the server first!")

        # Load and display History
        self._load_history_tab(history_scroll_frame, search_word, popup)

        # Load and display Favorites
        self._load_favorites_tab(favorites_scroll_frame, search_word, popup)

    def _load_history_tab(self, frame, search_callback, popup):
        """Завантажити та відобразити історію в frame з кнопками видалення."""
        # Clear existing widgets
        for widget in frame.winfo_children():
            widget.destroy()

        # Отримуємо історію з бази даних
        history_words = self.db.get_history_words(limit=50)

        if not history_words:
            ctk.CTkLabel(
                frame,
                text="No recent searches",
                font=("Segoe UI", 13),
                text_color=COLORS["text_muted"]
            ).pack(pady=50)
        else:
            for word in history_words:
                # Item frame with word button and delete button
                item_frame = ctk.CTkFrame(frame, fg_color="transparent")
                item_frame.pack(fill="x", pady=3)

                # Word button (clickable)
                word_btn = ctk.CTkButton(
                    item_frame,
                    text=f"🕒 {word}",
                    font=("Segoe UI", 13),
                    fg_color="transparent",
                    text_color=COLORS["text_primary"],
                    hover_color=COLORS["border"],
                    anchor="w",
                    height=38,
                    corner_radius=8,
                    command=lambda w=word: search_callback(w)
                )
                word_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

                # Delete button (X icon)
                delete_btn = ctk.CTkButton(
                    item_frame,
                    text="✕",
                    width=36,
                    height=38,
                    font=("Segoe UI", 12),
                    fg_color="transparent",
                    text_color=COLORS["text_muted"],
                    hover_color=COLORS["danger"],
                    corner_radius=8,
                    command=lambda w=word: self._delete_history_word(w, frame, search_callback, popup)
                )
                delete_btn.pack(side="right")

    def _load_favorites_tab(self, frame, search_callback, popup):
        """Завантажити та відобразити улюблені слова в frame з кнопками видалення."""
        # Clear existing widgets
        for widget in frame.winfo_children():
            widget.destroy()

        # Отримуємо улюблені з бази даних
        favorites = self.db.get_favorites()

        if not favorites:
            ctk.CTkLabel(
                frame,
                text="No favorite words",
                font=("Segoe UI", 13),
                text_color=COLORS["text_muted"]
            ).pack(pady=50)
        else:
            for word, translation in favorites:
                # Item frame with word button and delete button
                item_frame = ctk.CTkFrame(frame, fg_color="transparent")
                item_frame.pack(fill="x", pady=3)

                # Word button (clickable)
                word_btn = ctk.CTkButton(
                    item_frame,
                    text=f"⭐ {word}",
                    font=("Segoe UI", 13),
                    fg_color="transparent",
                    text_color=COLORS["text_primary"],
                    hover_color=COLORS["border"],
                    anchor="w",
                    height=38,
                    corner_radius=8,
                    command=lambda w=word: search_callback(w)
                )
                word_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

                # Delete button (X icon)
                delete_btn = ctk.CTkButton(
                    item_frame,
                    text="✕",
                    width=36,
                    height=38,
                    font=("Segoe UI", 12),
                    fg_color="transparent",
                    text_color=COLORS["text_muted"],
                    hover_color=COLORS["danger"],
                    corner_radius=8,
                    command=lambda w=word: self._delete_favorite_word(w, frame, search_callback, popup)
                )
                delete_btn.pack(side="right")

    def _delete_history_word(self, word: str, frame, search_callback, popup):
        """Видалити конкретне слово з історії."""
        success = self.db.remove_from_history(word)
        if success:
            # Reload the tab
            self._load_history_tab(frame, search_callback, popup)
            self._add_to_log_panel(f"🗑️ Removed '{word}' from history")
            logger.info(f"Видалено з історії: '{word}'")
        else:
            logger.warning(f"Не вдалося видалити з історії: '{word}'")

    def _delete_favorite_word(self, word: str, frame, search_callback, popup):
        """Видалити слово з улюблених."""
        success = self.db.remove_favorite(word)
        if success:
            # Reload the tab
            self._load_favorites_tab(frame, search_callback, popup)
            self._add_to_log_panel(f"🗑️ Removed '{word}' from favorites")
            logger.info(f"Видалено з улюблених: '{word}'")
        else:
            logger.warning(f"Не вдалося видалити з улюблених: '{word}'")

    def _clear_history_and_refresh(self, frame, popup):
        """Очистити історію та оновити відображення."""
        self._clear_history()
        # Reload history tab
        def search_callback(word):
            popup.destroy()
            self.search_entry.delete(0, 'end')
            self.search_entry.insert(0, word)
            if self.network.connected:
                self._translate()
        self._load_history_tab(frame, search_callback, popup)

    def _bind_shortcuts(self):
        """Прив'язка клавіатурних скорочень."""
        self.bind('<Control-h>', lambda e: self._show_about())
        self.bind('<Control-H>', lambda e: self._show_about())
        self.bind('<Escape>', lambda e: self._focus_search())

    def _focus_search(self):
        """Встановлення фокусу на поле пошуку."""
        try:
            if hasattr(self, 'search_entry') and self.search_entry.winfo_exists():
                self.search_entry.focus()
        except Exception:
            pass

    # === FUNCTIONALITY ===

    def _show_connection_warning(self):
        """Показати попередження про відсутність з'єднання."""
        # Створюємо модальне вікно попередження
        warning = ctk.CTkToplevel(self)
        warning.title("⚠️ Сервер недоступний")
        warning.geometry("450x280")
        warning.resizable(False, False)
        warning.transient(self)
        warning.grab_set()
        warning.configure(fg_color=COLORS["bg_main"])

        # Контейнер
        container = ctk.CTkFrame(warning, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=30, pady=30)

        # Іконка та заголовок
        ctk.CTkLabel(
            container,
            text="🔴",
            font=("Segoe UI", 48)
        ).pack(pady=(0, 10))

        ctk.CTkLabel(
            container,
            text="Сервер недоступний",
            font=("Segoe UI", 18, "bold"),
            text_color=COLORS["text_primary"]
        ).pack()

        ctk.CTkLabel(
            container,
            text=f"Не вдалося підключитися до {self.network.host}:{self.network.port}\n\n"
                 "Переконайтесь, що сервер запущено,\n"
                 "або натисніть 'Connect' для повторної спроби.",
            font=("Segoe UI", 12),
            text_color=COLORS["text_secondary"],
            justify="center"
        ).pack(pady=15)

        # Кнопки
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 0))

        ctk.CTkButton(
            btn_frame,
            text="OK",
            width=120,
            height=40,
            font=("Segoe UI", 12, "bold"),
            fg_color="#007AFF",
            hover_color="#0056B3",
            corner_radius=8,
            command=warning.destroy
        ).pack()

    def _update_ui_state(self, connected: bool):
        """
        Оновлює стан UI елементів залежно від статусу з'єднання.

        Args:
            connected: True якщо підключено, False якщо ні.
        """
        if connected:
            # Розблоковуємо UI
            self.search_entry.configure(
                state="normal",
                placeholder_text=""
            )
            self.search_btn.configure(
                state="normal",
                fg_color="#10B981",
                hover_color="#059669"
            )
            # Ставимо фокус на пошуковий рядок після підключення
            self.after(100, lambda: self.search_entry.focus_set())
            self._add_to_log_panel("✅ UI розблоковано")
        else:
            # Блокуємо UI
            self.search_entry.configure(
                state="disabled",
                placeholder_text=""
            )
            self.search_btn.configure(
                state="disabled",
                fg_color="#6B7280",
                hover_color="#6B7280"
            )

    def _toggle_connection(self):
        """Перемикання з'єднання з сервером (відключення синхронне, підключення в фоновому потоці)."""
        if self.network.connected:
            # Відключення - синхронне, оскільки швидке
            try:
                self.network.disconnect()
                self.status_indicator.set_offline()
                self.connect_btn.configure(text="Connect", fg_color="#007AFF")
                self._update_ui_state(False)
                self._add_to_log_panel("Від'єднано від сервера")
            except Exception as e:
                logger.error(f"[UI] Помилка відключення: {e}")
                self.status_indicator.set_offline()
                self.connect_btn.configure(text="Connect", fg_color="#007AFF")
                self._update_ui_state(False)
        else:
            self.status_indicator.set_connecting()
            self.connect_btn.configure(text="...", state="disabled")
            self.update()

            host = self.host_entry.get().strip() or "127.0.0.1"
            try:
                port = int(self.port_entry.get().strip() or "8080")
            except ValueError:
                port = 8080

            self.network.host = host
            self.network.port = port

            # Запускаємо підключення в фоновому потоці
            def connect_thread():
                try:
                    connected = self.network.connect()
                    # Оновлюємо UI в головному потоці
                    self.after(0, lambda: self._on_connect_result(connected, host, port))
                except Exception as e:
                    logger.error(f"[UI] Помилка підключення: {e}")
                    self.after(0, lambda: self._on_connect_result(False, host, port))
            
            thread = threading.Thread(target=connect_thread, daemon=True)
            thread.start()
            self._network_threads.append(thread)
    
    def _on_connect_result(self, connected: bool, host: str, port: int):
        """Обробка результату підключення (викликається в UI потоці)."""
        if connected:
            self.status_indicator.set_online()
            self.connect_btn.configure(text="Disconnect", state="normal", fg_color="#EF4444", hover_color="#DC2626")
            self._update_ui_state(True)
            self._add_to_log_panel(f"Підключено до {host}:{port}")
            # Оновлюємо Word of the Day
            self.after(200, self._refresh_word_of_the_day)
        else:
            self.status_indicator.set_offline()
            self.connect_btn.configure(text="Connect", state="normal", fg_color="#007AFF")
            self._update_ui_state(False)
            self._add_to_log_panel(f"Помилка підключення: {host}:{port}")
            messagebox.showerror("Помилка з'єднання",
                f"Не вдалося підключитися до сервера!\n\n"
                f"Адреса: {host}:{port}\n\n"
                f"Переконайтесь, що сервер запущено."
            )

    def _translate(self):
        """Виконання перекладу слова (в фоновому потоці)."""
        # Empty input protection - do nothing if input is empty
        search_term = self.search_entry.get().strip()
        if not search_term:
            return
        
        word = search_term.lower()

        if not self.network.connected:
            messagebox.showwarning("Немає з'єднання", "Спочатку підключіться до сервера!")
            return

        self.search_btn.configure(text="🔍 Думаю...", state="disabled")
        self.update()

        # Показуємо results screen одразу
        self._show_results_screen()

        # Запускаємо переклад в фоновому потоці
        def translate_thread():
            try:
                response = self.network.translate(word)
                # Оновлюємо UI в головному потоці
                self.after(0, lambda: self._on_translate_result(word, response))
            except Exception as e:
                logger.error(f"[UI] Помилка перекладу: {e}")
                self.after(0, lambda: self._on_translate_result(word, None))
        
        thread = threading.Thread(target=translate_thread, daemon=True)
        thread.start()
        self._network_threads.append(thread)
    
    def _on_translate_result(self, word: str, response: str | None):
        """Обробка результату перекладу (викликається в UI потоці)."""
        self.search_btn.configure(text="🔍 Translate", state="normal")

        if response is None or response == "":
            self.status_indicator.set_offline()
            self.connect_btn.configure(text="Connect")
            self._add_to_log_panel(f"Втрачено з'єднання: '{word}'")
            messagebox.showerror("Помилка", "З'єднання з сервером втрачено!")
        elif response == "NOT_FOUND" or (isinstance(response, str) and response.strip().lower() in ["not found", "error", "notfound"]):
            self._show_not_found(word)
            self._add_to_log_panel(f"Не знайдено: '{word}'")
            # DO NOT save "Not found" to History!
        else:
            self._display_translation(word, response)
            self._add_to_log_panel(f"{word} → ...")
            # Note: History is now saved in _display_translation() immediately after parsing

    def _add_word(self, ukr: str, eng: str) -> bool:
        """
        Додавання нового слова до словника (в фоновому потоці).
        
        Returns:
            bool: False одразу (результат буде показано через callback)
        """
        if not ukr or not eng:
            messagebox.showwarning("Відсутні дані", "Введіть обидва слова!")
            return False

        if not self.network.connected:
            messagebox.showwarning("Немає з'єднання", "Спочатку підключіться!")
            return False

        # Запускаємо додавання в фоновому потоці
        def add_word_thread():
            try:
                response = self.network.add_word(ukr, eng)
                # Оновлюємо UI в головному потоці
                self.after(0, lambda: self._on_add_word_result(ukr, eng, response))
            except Exception as e:
                logger.error(f"[UI] Помилка додавання слова: {e}")
                self.after(0, lambda: self._on_add_word_result(ukr, eng, None))
        
        thread = threading.Thread(target=add_word_thread, daemon=True)
        thread.start()
        self._network_threads.append(thread)
        return False  # Результат буде показано через callback
    
    def _on_add_word_result(self, ukr: str, eng: str, response: str | None):
        """Обробка результату додавання слова (викликається в UI потоці)."""
        if response == "ADDED":
            self._add_to_log_panel(f"Додано: {ukr} = {eng}")
            messagebox.showinfo("Успішно", f"Слово '{ukr}' додано!")
        elif response == "EXIST":
            self._add_to_log_panel(f"Дублікат: '{ukr}'")
            messagebox.showwarning("Дублікат", f"Слово '{ukr}' вже існує!")
        else:
            self._add_to_log_panel(f"Помилка: '{ukr}'")
            messagebox.showerror("Помилка", "Не вдалося додати слово.")

    def _display_translation(self, search_query, raw_response):
        """
        Відображення результатів перекладу (English → Ukrainian).

        Формат відповіді сервера: "Word|Definition"

        Args:
            search_query: Запит користувача (англійське слово)
            raw_response: Відповідь сервера
        """
        logger.info(f"Переклад: '{search_query}'")

        # === CRASH PROTECTION: Handle plain text responses without "|" separator ===
        if "|" in raw_response:
            # Normal response format: "Word|Definition"
            headword, definition_body = raw_response.split("|", 1)
            headword = headword.strip()
            definition_body = definition_body.strip()
            
            # === CRITICAL: Force save to history immediately after successful parsing ===
            clean_headword = headword.strip()
            if clean_headword and definition_body:
                self.db.add_to_history(clean_headword, definition_body)
            
            # Store current word for favorites toggle
            self.current_headword = clean_headword
            self.current_definition = definition_body
            
            # Check if word is favorite
            is_favorite = self.db.is_favorite(clean_headword)
        else:
            # Handle plain text response (e.g. "Not found", "Error")
            # Use the user's search query as headword instead of "System Message"
            headword = self.search_var.get().strip() if self.search_var.get() else search_query.strip()
            definition_body = raw_response.strip()
            clean_headword = headword
            
            # Store current word for favorites toggle (even if it's an error)
            self.current_headword = clean_headword
            self.current_definition = definition_body
            
            is_favorite = False
            
            # Check if it's an error/not found message
            response_lower = raw_response.strip().lower()
            if response_lower in ["not found", "error", "notfound"]:
                # Don't save error messages to history
                logger.warning(f"Server returned error message: '{raw_response}'")
            else:
                # If it's some other plain text (unexpected), save to history if valid
                if clean_headword and definition_body:
                    self.db.add_to_history(clean_headword, definition_body)
                logger.warning(f"Unexpected response format: '{raw_response}'")

        # === Форматуємо визначення ===
        formatted_definition = format_and_display(definition_body, headword=headword)

        # === Створюємо картку результату ===
        result_card = ResultCard(
            self.results_frame,
            headword=headword,
            definition=formatted_definition,
            favorite_callback=self._handle_favorite_toggle,
            is_favorite=is_favorite
        )
        result_card.pack(fill="x", pady=10)

    def _show_not_found(self, word):
        """Показати повідомлення про ненайдене слово."""
        frame = ctk.CTkFrame(self.results_frame, fg_color=COLORS["bg_card"], corner_radius=12)
        frame.pack(fill="x", pady=10)

        ctk.CTkLabel(frame, text="😕", font=("Segoe UI Emoji", 40)).pack(pady=(20, 10))
        ctk.CTkLabel(
            frame,
            text=f"'{word}' не знайдено",
            font=("Segoe UI", 16, "bold"),
            text_color=COLORS["warning"]
        ).pack()
        ctk.CTkLabel(
            frame,
            text="Спробуйте інше слово або додайте до словника.",
            font=("Segoe UI", 12),
            text_color=COLORS["text_secondary"]
        ).pack(pady=(5, 20))

    def _show_placeholder(self, message):
        """Показати placeholder в області результатів."""
        ctk.CTkLabel(
            self.results_frame,
            text="📖",
            font=("Segoe UI Emoji", 48),
            text_color=COLORS["text_muted"]
        ).pack(pady=(50, 10))

        ctk.CTkLabel(
            self.results_frame,
            text=message,
            font=("Segoe UI", 14),
            text_color=COLORS["text_muted"]
        ).pack()

    def _clear_results(self):
        """Очищення області результатів."""
        for widget in self.results_frame.winfo_children():
            widget.destroy()

    def _clear_history(self):
        """Очищення історії пошуку."""
        self.db.clear_history()
        self._add_to_log_panel("Історію очищено")

    def _add_to_log_panel(self, message):
        """Виводить повідомлення в консоль та логер."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        logger.info(message)

    def _copy_wotd(self):
        """Копіювання Word of the Day в буфер обміну (тільки переклад)."""
        try:
            word = self.wotd_word_label.cget("text")
            # Отримуємо текст з textbox (не label)
            raw_definition = self.wotd_definition_textbox.get("1.0", "end").strip()

            # Очищаємо від заголовків POS
            clean_definition = self._clean_definition_for_copy(raw_definition, word)

            self.clipboard_clear()
            self.clipboard_append(clean_definition)

            # Показуємо галочку на 1.5 сек
            self.wotd_copy_btn.configure(text="✓")
            self.after(1500, lambda: self.wotd_copy_btn.configure(text="📋"))

            logger.info(f"Скопійовано Word of the Day (переклад)")
        except Exception as e:
            logger.error(f"Помилка копіювання WOTD: {e}")

    def _clean_definition_for_copy(self, text: str, headword: str = None) -> str:
        """
        Очистити текст визначення для копіювання.
        Видаляє заголовки POS, headword та зайве форматування.

        Args:
            text: Сирий текст визначення
            headword: Слово-заголовок для видалення

        Returns:
            Чистий текст перекладу
        """
        # Видаляємо заголовки частин мови типу [ NOUN ], [ VERB ] тощо
        text = re.sub(r'\[\s*(NOUN|VERB|ADJECTIVE|ADVERB|PREPOSITION|CONJUNCTION|PRONOUN|INTERJECTION|NUMERAL|PHRASAL VERB)\s*\]', '', text)

        # Видаляємо headword якщо він на початку
        if headword:
            pattern = rf'^\s*{re.escape(headword)}\s*\n?'
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # Очищаємо зайві переноси рядків та пробіли
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)
        text = text.strip()

        return text

    def _refresh_word_of_the_day(self):
        """Оновити слово дня з сервера."""
        if not self.network.connected:
            self.wotd_word_label.configure(text="Offline")
            self._update_wotd_textbox("Підключіться для слова дня")
            return

        try:
            # Запитуємо випадкове слово через network
            response = self.network.send_command("GET_RANDOM|")

            if response and response != "NOT_FOUND" and '|' in response:
                parts = response.split('|', 1)
                word = parts[0].strip()
                definition = parts[1].strip() if len(parts) > 1 else ""

                # Форматуємо визначення через наш Human-Readable Formatter
                formatted_definition = format_and_display(definition, headword=word)

                self.wotd_word_label.configure(text=word.title())
                self._update_wotd_textbox(formatted_definition)
                logger.info(f"Слово дня: {word}")
            else:
                # Якщо сервер не підтримує GET_RANDOM - показуємо заглушку
                self.wotd_word_label.configure(text="Hello")
                self._update_wotd_textbox("Привіт! Вітання, формальне або неформальне.")
        except Exception as e:
            logger.error(f"Помилка отримання слова дня: {e}")
            self.wotd_word_label.configure(text="—")
            self._update_wotd_textbox("Недоступно")

    def _update_wotd_textbox(self, text: str):
        """Оновити текстове поле слова дня з форматуванням та кольоровими тегами."""
        try:
            if hasattr(self, 'wotd_definition_textbox') and self.wotd_definition_textbox.winfo_exists():
                self.wotd_definition_textbox.configure(state="normal")
                # Використовуємо Deep Sky Blue для тегів у WotD (щоб відрізнятися від зеленого headword)
                insert_formatted_text(self.wotd_definition_textbox, text, tag_color="#00BFFF")
                self.wotd_definition_textbox.configure(state="disabled")
        except Exception as e:
            logger.error(f"Помилка оновлення WOTD textbox: {e}")

    def _safe_focus_search(self):
        """Безпечне встановлення фокусу з захистом від TclError."""
        import tkinter as tk
        try:
            if hasattr(self, 'search_entry') and self.search_entry.winfo_exists():
                self.search_entry.focus_set()
        except (tk.TclError, AttributeError):
            pass  # Ігноруємо помилки фокусу

    def _handle_favorite_toggle(self, word: str, definition: str, is_favorite: bool):
        """
        Обробка toggle улюблених слів.
        
        Оновлює базу даних та забезпечує синхронізацію стану зірки.
        """
        # Use stored current values if available, otherwise use passed parameters
        clean_word = (self.current_headword or word).strip()
        clean_definition = (self.current_definition or definition).strip()
        
        if is_favorite:
            # Додаємо до улюблених
            success = self.db.add_favorite(clean_word, clean_definition)
            if success:
                logger.info(f"Додано до улюблених: '{clean_word}'")
                self._add_to_log_panel(f"⭐ Додано до улюблених: '{clean_word}'")
            else:
                # Word might already be in favorites - verify and sync
                if self.db.is_favorite(clean_word):
                    logger.info(f"Слово вже в улюблених: '{clean_word}'")
                else:
                    logger.warning(f"Не вдалося додати до улюблених: '{clean_word}'")
        else:
            # Видаляємо з улюблених
            success = self.db.remove_favorite(clean_word)
            if success:
                logger.info(f"Видалено з улюблених: '{clean_word}'")
                self._add_to_log_panel(f"☆ Видалено з улюблених: '{clean_word}'")
            else:
                # Word might not be in favorites - verify and sync
                if not self.db.is_favorite(clean_word):
                    logger.info(f"Слово не в улюблених: '{clean_word}'")
                else:
                    logger.warning(f"Не вдалося видалити з улюблених: '{clean_word}'")

    def _show_about(self):
        """Показати діалог 'Про програму'."""
        messagebox.showinfo(
            "Про E-Dictionary Pro",
            "🐦 Електронний словник v2.0\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Курсова робота 2025\n\n"
            "Розробник: Дмитро Петрунів\n"
            "Бекенд: C++ (Winsock2)\n"
            "Фронтенд: Python (CustomTkinter)\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Натисніть Ctrl+H щоб побачити це."
        )

