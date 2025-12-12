#define _WINSOCK_DEPRECATED_NO_WARNINGS
#define _CRT_SECURE_NO_WARNINGS
#include <iostream>
#include <winsock2.h>
#include <map>
#include <string>
#include <sstream>
#include <fstream>
#include <vector>
#include <windows.h>
#include <regex>
#include <random>
#include <ctime>
#include <memory>
#include <clocale>
#include "sqlite3.h"

#pragma comment(lib, "ws2_32.lib")

// UTF-8 console print helper using WriteConsoleW
static void printUtf(const std::string& s) {
    HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    if (hOut == INVALID_HANDLE_VALUE) {
        std::cout << s << std::endl;
        return;
    }
    int wideLen = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, nullptr, 0);
    if (wideLen > 0) {
        std::wstring wbuf(wideLen, L'\0');
        MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, &wbuf[0], wideLen);
        if (!wbuf.empty() && wbuf.back() == L'\0') wbuf.pop_back();
        DWORD written = 0;
        WriteConsoleW(hOut, wbuf.c_str(), (DWORD)wbuf.size(), &written, nullptr);
        WriteConsoleW(hOut, L"\n", 1, &written, nullptr);
    } else {
        std::cout << s << std::endl;
    }
}

// ============================================================================
// Helper: remove HTML/XML tags from dictionary entries
// ============================================================================
std::string removeTags(const std::string& text) {
    std::string result = text;

    std::regex brTag("<br\\s*/?>");
    result = std::regex_replace(result, brTag, "\n");

    std::regex htmlTags("<[^>]*>");
    result = std::regex_replace(result, htmlTags, "");

    std::regex dictTags("\\[[^\\]]*\\]");
    result = std::regex_replace(result, dictTags, "");

    std::regex nbspEntity("&nbsp;");
    result = std::regex_replace(result, nbspEntity, " ");

    std::regex ampEntity("&amp;");
    result = std::regex_replace(result, ampEntity, "&");

    std::regex ltEntity("&lt;");
    result = std::regex_replace(result, ltEntity, "<");

    std::regex gtEntity("&gt;");
    result = std::regex_replace(result, gtEntity, ">");

    std::regex quotEntity("&quot;");
    result = std::regex_replace(result, quotEntity, "\"");

    std::regex multipleNewlines("\n{3,}");
    result = std::regex_replace(result, multipleNewlines, "\n\n");

    std::regex multipleSpaces(" {2,}");
    result = std::regex_replace(result, multipleSpaces, " ");

    size_t start = result.find_first_not_of(" \t\n\r");
    size_t end = result.find_last_not_of(" \t\n\r");

    if (start == std::string::npos) {
        return "";
    }

    return result.substr(start, end - start + 1);
}

// ============================================================================
// CLASS: Language
// ============================================================================
class Language {
private:
    std::string code;
    std::string name;
    std::string nativeName;
public:
    Language() : code(""), name(""), nativeName("") {}
    Language(const std::string& code, const std::string& name, const std::string& nativeName = "")
        : code(code), name(name), nativeName(nativeName.empty() ? name : nativeName) {
    }
    Language(const Language& other) : code(other.code), name(other.name), nativeName(other.nativeName) {}
    Language& operator=(const Language& other) { if (this != &other) { code = other.code; name = other.name; nativeName = other.nativeName; } return *this; }
    std::string getCode() const { return code; }
    std::string getName() const { return name; }
    std::string getNativeName() const { return nativeName; }
    void setCode(const std::string& newCode) { code = newCode; }
    void setName(const std::string& newName) { name = newName; }
    void setNativeName(const std::string& newNativeName) { nativeName = newNativeName; }
    std::string toString() const { return code + " (" + name + ")"; }
    bool operator==(const Language& other) const { return code == other.code; }
    bool operator!=(const Language& other) const { return !(*this == other); }
};

// ============================================================================
// INTERFACE: IDictionarySource
// ============================================================================
class IDictionarySource {
public:
    virtual ~IDictionarySource() = default;
    virtual std::string search(const std::string& word) = 0;
    virtual void addWord(const std::string& word, const std::string& translation) = 0;
    virtual bool wordExists(const std::string& word) = 0;
    virtual bool updateWord(const std::string& word, const std::string& newTranslation) = 0;
    virtual bool deleteWord(const std::string& word) = 0;
    virtual size_t getSize() const = 0;
    virtual std::string getRandomWord() = 0;
    virtual std::string getSourceName() const {
        return "Unknown dictionary source";
    }
};

// ============================================================================
// CLASS: Logger
// ============================================================================
class Logger {
private:
    std::ofstream logFile;
    std::string filename;
    bool enabled;
public:
    Logger(const std::string& logFilename = "server_log.txt") : filename(logFilename), enabled(true) {
        logFile.open(filename, std::ios::app);
        if (!logFile.is_open()) {
            std::cerr << "[WARNING] Failed to open log file: " << filename << std::endl;
            enabled = false;
        }
    }
    ~Logger() { if (logFile.is_open()) logFile.close(); }
    void log(const std::string& message) {
        if (enabled && logFile.is_open()) {
            time_t now = time(nullptr);
            char timestamp[64];
            strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S", localtime(&now));
            logFile << "[" << timestamp << "] " << message << std::endl;
            logFile.flush();
        }
    }
    void setEnabled(bool value) { enabled = value; }
    bool isEnabled() const { return enabled; }
};

// ============================================================================
// CLASS: SQLiteDictionary
// ============================================================================
class SQLiteDictionary : public IDictionarySource {
private:
    sqlite3* db;
    std::string dbPath;
    Logger& logger;
    mutable std::mt19937 rng;

    bool isWordBoundary(const std::string& str, size_t pos) const {
        if (pos >= str.length()) return true;
        unsigned char c = static_cast<unsigned char>(str[pos]);
        if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z')) return false;
        if (c == 0xD0 || c == 0xD1) return false;
        if ((c & 0xC0) == 0x80) return false;
        return true;
    }

    bool isWholeWordMatch(const std::string& text, const std::string& query, size_t pos) const {
        if (pos > 0) {
            size_t prevPos = pos - 1;
            while (prevPos > 0 && (static_cast<unsigned char>(text[prevPos]) & 0xC0) == 0x80) prevPos--;
            if (!isWordBoundary(text, prevPos)) return false;
        }
        size_t afterPos = pos + query.length();
        if (afterPos < text.length()) { if (!isWordBoundary(text, afterPos)) return false; }
        return true;
    }

    size_t findWholeWord(const std::string& text, const std::string& query) const {
        size_t pos = 0;
        while ((pos = text.find(query, pos)) != std::string::npos) {
            if (isWholeWordMatch(text, query, pos)) return pos;
            pos++;
        }
        return std::string::npos;
    }

    std::string extractRedirectWord(const std::string& definition) const {
        size_t startPos = definition.find("<<");
        if (startPos == std::string::npos) return "";
        size_t endPos = definition.find(">>", startPos);
        if (endPos == std::string::npos) return "";
        std::string redirectWord = definition.substr(startPos + 2, endPos - startPos - 2);
        size_t first = redirectWord.find_first_not_of(" \t\n\r");
        size_t last = redirectWord.find_last_not_of(" \t\n\r");
        if (first == std::string::npos) return "";
        return redirectWord.substr(first, last - first + 1);
    }

    bool isRedirectDefinition(const std::string& definition) const {
        if (definition.find("<<") != std::string::npos && definition.find(">>") != std::string::npos) {
            if (definition.find("\xD0\xB4\xD0\xB8\xD0\xB2.") != std::string::npos ||
                definition.find("\xD0\x94\xD0\xB8\xD0\xB2.") != std::string::npos ||
                definition.find("\xD0\x94\xD0\x98\xD0\x92.") != std::string::npos) {
                return true;
            }
            size_t start = definition.find("<<");
            size_t end = definition.find(">>") + 2;
            std::string remaining = definition.substr(0, start) + definition.substr(end);
            size_t first = remaining.find_first_not_of(" \t\n\r.,;:");
            if (first == std::string::npos || remaining.length() - first < 10) return true;
        }
        return false;
    }

    std::string searchInternal(const std::string& query, int depth) {
        if (depth > 2) {
            logger.log("WARNING: Max redirect depth reached for: " + query);
            return "MAX_REDIRECT_DEPTH";
        }
        if (!db) return "DATABASE_ERROR";

        sqlite3_stmt* stmt;
        const char* sql = "SELECT m FROM word WHERE w = ? COLLATE NOCASE LIMIT 1;";
        int rc = sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);
        if (rc != SQLITE_OK) return "";
        sqlite3_bind_text(stmt, 1, query.c_str(), -1, SQLITE_STATIC);
        std::string result = "";
        rc = sqlite3_step(stmt);
        if (rc == SQLITE_ROW) {
            const unsigned char* rawDef = sqlite3_column_text(stmt, 0);
            if (rawDef) result = reinterpret_cast<const char*>(rawDef);
        }
        sqlite3_finalize(stmt);
        return result;
    }

public:
    SQLiteDictionary(const std::string& databasePath, Logger& log) : db(nullptr), dbPath(databasePath), logger(log) {
        std::random_device rd;
        std::seed_seq seed{ rd(), rd(), rd(), rd(), rd(), rd(), rd(), rd() };
        rng.seed(seed);
        int rc = sqlite3_open(dbPath.c_str(), &db);
        if (rc != SQLITE_OK) {
            std::cerr << "[ERROR] Cannot open database: " << sqlite3_errmsg(db) << std::endl;
            logger.log("ERROR: Cannot open database - " + std::string(sqlite3_errmsg(db)));
            db = nullptr;
        }
        else {
            std::cout << "[INFO] Database connected: " << dbPath << std::endl;
            logger.log("INFO: Database connected");
        }
    }

    ~SQLiteDictionary() override { if (db) { sqlite3_close(db); logger.log("INFO: Database connection closed"); } }
    SQLiteDictionary(const SQLiteDictionary&) = delete;
    SQLiteDictionary& operator=(const SQLiteDictionary&) = delete;

    std::string search(const std::string& word) override {
        std::cout << "[SEARCH] Looking for: \"" << word << "\"" << std::endl;
        if (!db) {
            std::cerr << "[ERROR] Database not connected!" << std::endl;
            logger.log("ERROR: Database not connected for query: " + word);
            return "DATABASE_ERROR";
        }

        sqlite3_stmt* stmt;
        std::cout << "[SEARCH] Step 1: Direct (EN->UK) search..." << std::endl;
        const char* sql = "SELECT m FROM word WHERE w = ? COLLATE NOCASE LIMIT 1;";
        int rc = sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);
        if (rc != SQLITE_OK) {
            std::cerr << "[ERROR] SQL prepare error: " << sqlite3_errmsg(db) << std::endl;
            logger.log("ERROR: SQL prepare failed for: " + word);
            return "DATABASE_ERROR";
        }
        sqlite3_bind_text(stmt, 1, word.c_str(), -1, SQLITE_STATIC);

        std::string result = "";
        std::string rawResult = "";
        rc = sqlite3_step(stmt);
        if (rc == SQLITE_ROW) {
            const unsigned char* rawDef = sqlite3_column_text(stmt, 0);
            if (rawDef) {
                rawResult = reinterpret_cast<const char*>(rawDef);
                result = removeTags(rawResult);
                std::cout << "[FOUND] English headword found!" << std::endl;
                logger.log("SEARCH: '" + word + "' -> FOUND (english key)");
            }
        }
        sqlite3_finalize(stmt);

        if (!result.empty()) {
            if (isRedirectDefinition(rawResult)) {
                std::string redirectWord = extractRedirectWord(rawResult);
                if (!redirectWord.empty() && redirectWord != word) {
                    std::cout << "[REDIRECT] Found redirect to: \"" << redirectWord << "\"" << std::endl;
                    logger.log("REDIRECT: '" + word + "' -> '" + redirectWord + "'");
                    std::string redirectRaw = searchInternal(redirectWord, 1);
                    if (!redirectRaw.empty() && redirectRaw != "DATABASE_ERROR" && redirectRaw != "MAX_REDIRECT_DEPTH") {
                        std::string redirectResult = removeTags(redirectRaw);
                        if (isRedirectDefinition(redirectRaw)) {
                            std::string secondRedirect = extractRedirectWord(redirectRaw);
                            if (!secondRedirect.empty() && secondRedirect != redirectWord) {
                                std::string secondRaw = searchInternal(secondRedirect, 2);
                                if (!secondRaw.empty() && secondRaw != "DATABASE_ERROR" && secondRaw != "MAX_REDIRECT_DEPTH") {
                                    redirectResult = removeTags(secondRaw);
                                    redirectWord = secondRedirect;
                                }
                            }
                        }
                        result = redirectResult + "\n\n(See: " + redirectWord + ")";
                        std::cout << "[RESOLVED] Redirect resolved" << std::endl;
                        logger.log("RESOLVED: '" + word + "' -> '" + redirectWord + "'");
                    }
                }
            }
            return result;
        }

        // Step 2: Reverse search (UK->EN)
        std::cout << "[SEARCH] Step 2: Reverse search (whole word matching)..." << std::endl;
        logger.log("SEARCH: '" + word + "' -> Reverse search attempt");

        const char* reverseSql = "SELECT w, m FROM word WHERE m LIKE ? LIMIT 100;";
        rc = sqlite3_prepare_v2(db, reverseSql, -1, &stmt, nullptr);
        if (rc != SQLITE_OK) {
            logger.log("ERROR: SQL prepare failed for reverse search: " + word);
            return "NOT_FOUND";
        }

        std::string searchPattern = "%" + word + "%";
        sqlite3_bind_text(stmt, 1, searchPattern.c_str(), -1, SQLITE_STATIC);

        std::string bestMatch = "";
        std::string bestEngWord = "";
        size_t bestPosition = std::string::npos;

        while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
            const unsigned char* engWord = sqlite3_column_text(stmt, 0);
            const unsigned char* rawDef = sqlite3_column_text(stmt, 1);
            if (engWord && rawDef) {
                std::string engWordStr = reinterpret_cast<const char*>(engWord);
                std::string rawStr = reinterpret_cast<const char*>(rawDef);
                if (isRedirectDefinition(rawStr)) continue;
                size_t matchPos = findWholeWord(rawStr, word);
                if (matchPos != std::string::npos) {
                    std::string cleanDef = removeTags(rawStr);
                    if (bestMatch.empty() || matchPos < bestPosition) {
                        bestMatch = cleanDef;
                        bestEngWord = engWordStr;
                        bestPosition = matchPos;
                        if (matchPos == 0) break;
                    }
                }
            }
        }
        sqlite3_finalize(stmt);

        if (!bestMatch.empty()) {
            result = bestEngWord + "|" + bestMatch;
            std::cout << "[FOUND] Whole-word match! English: \"" << bestEngWord << "\"" << std::endl;
            logger.log("SEARCH: '" + word + "' -> FOUND (reverse: " + bestEngWord + ")");
        }
        else {
            std::cout << "[NOT_FOUND] No matches found" << std::endl;
            logger.log("SEARCH: '" + word + "' -> NOT_FOUND");
            result = "NOT_FOUND";
        }

        return result;
    }

    void addWord(const std::string& word, const std::string& translation) override {
        if (!db) { logger.log("ERROR: DB not connected for ADD"); return; }
        sqlite3_stmt* stmt;
        const char* sql = "INSERT INTO word (w, m) VALUES (?, ?);";
        int rc = sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);
        if (rc != SQLITE_OK) { std::cerr << "[ERROR] SQL prepare error: " << sqlite3_errmsg(db) << std::endl; logger.log("ERROR: Failed to add word: " + word); return; }
        sqlite3_bind_text(stmt, 1, word.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 2, translation.c_str(), -1, SQLITE_STATIC);
        rc = sqlite3_step(stmt);
        if (rc != SQLITE_DONE) { std::cerr << "[ERROR] Insert error: " << sqlite3_errmsg(db) << std::endl; logger.log("ERROR: Insert failed for: " + word); }
        else { std::cout << "[LOG] Word added: " << word << std::endl; logger.log("ADD: '" + word + "' added"); }
        sqlite3_finalize(stmt);
    }

    bool wordExists(const std::string& word) override {
        if (!db) return false;
        sqlite3_stmt* stmt;
        const char* sql = "SELECT 1 FROM word WHERE w = ? COLLATE NOCASE LIMIT 1;";
        int rc = sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);
        if (rc != SQLITE_OK) return false;
        sqlite3_bind_text(stmt, 1, word.c_str(), -1, SQLITE_STATIC);
        bool exists = (sqlite3_step(stmt) == SQLITE_ROW);
        sqlite3_finalize(stmt);
        logger.log(std::string("EXISTS: '") + word + "' -> " + (exists ? "YES" : "NO"));
        return exists;
    }

    bool updateWord(const std::string& word, const std::string& newTranslation) override {
        if (!db) { logger.log("ERROR: DB not connected for UPDATE"); return false; }
        if (!wordExists(word)) { logger.log("UPDATE: Word '" + word + "' not found"); return false; }
        sqlite3_stmt* stmt;
        const char* sql = "UPDATE word SET m = ? WHERE w = ? COLLATE NOCASE;";
        int rc = sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);
        if (rc != SQLITE_OK) { logger.log("ERROR: Failed to prepare UPDATE for: " + word); return false; }
        sqlite3_bind_text(stmt, 1, newTranslation.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 2, word.c_str(), -1, SQLITE_STATIC);
        rc = sqlite3_step(stmt);
        sqlite3_finalize(stmt);
        if (rc != SQLITE_DONE) { logger.log("ERROR: Update failed for: " + word); return false; }
        int changes = sqlite3_changes(db);
        if (changes > 0) { std::cout << "[LOG] Word updated: " << word << std::endl; logger.log("UPDATE: '" + word + "' updated"); return true; }
        return false;
    }

    bool deleteWord(const std::string& word) override {
        if (!db) { logger.log("ERROR: DB not connected for DELETE"); return false; }
        if (!wordExists(word)) { logger.log("DELETE: Word '" + word + "' not found"); return false; }
        sqlite3_stmt* stmt;
        const char* sql = "DELETE FROM word WHERE w = ? COLLATE NOCASE;";
        int rc = sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);
        if (rc != SQLITE_OK) { logger.log("ERROR: Failed to prepare DELETE for: " + word); return false; }
        sqlite3_bind_text(stmt, 1, word.c_str(), -1, SQLITE_STATIC);
        rc = sqlite3_step(stmt);
        sqlite3_finalize(stmt);
        if (rc != SQLITE_DONE) { logger.log("ERROR: Delete failed for: " + word); return false; }
        int changes = sqlite3_changes(db);
        if (changes > 0) { std::cout << "[LOG] Word deleted: " << word << std::endl; logger.log("DELETE: '" + word + "' deleted"); return true; }
        return false;
    }

    size_t getSize() const override {
        if (!db) return 0;
        sqlite3_stmt* stmt;
        const char* sql = "SELECT COUNT(*) FROM word;";
        if (sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) != SQLITE_OK) return 0;
        size_t count = 0;
        if (sqlite3_step(stmt) == SQLITE_ROW) count = static_cast<size_t>(sqlite3_column_int64(stmt, 0));
        sqlite3_finalize(stmt);
        return count;
    }

    std::string getRandomWord() override {
        if (!db) { logger.log("ERROR: DB not connected for GET_RANDOM"); return "DATABASE_ERROR"; }
        size_t totalWords = getSize();
        if (totalWords == 0) { logger.log("ERROR: Dictionary empty"); return "EMPTY_DICTIONARY"; }
        const int MAX_ATTEMPTS = 5;
        for (int attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
            std::uniform_int_distribution<size_t> dist(0, totalWords - 1);
            size_t randomOffset = dist(rng);
            std::cout << "[RANDOM] Attempt " << (attempt + 1) << ": offset " << randomOffset << " of " << totalWords << std::endl;
            sqlite3_stmt* stmt = nullptr;
            std::string sql = "SELECT w, m FROM word LIMIT 1 OFFSET " + std::to_string(randomOffset) + ";";
            int rc = sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr);
            if (rc != SQLITE_OK) { logger.log("ERROR: SQL prepare error for random word"); return "DATABASE_ERROR"; }
            rc = sqlite3_step(stmt);
            if (rc != SQLITE_ROW) { sqlite3_finalize(stmt); continue; }
            const unsigned char* word = sqlite3_column_text(stmt, 0);
            const unsigned char* definition = sqlite3_column_text(stmt, 1);
            if (!word || !definition) { sqlite3_finalize(stmt); continue; }
            std::string wordStr = reinterpret_cast<const char*>(word);
            std::string rawDefStr = reinterpret_cast<const char*>(definition);
            sqlite3_finalize(stmt);
            if (isRedirectDefinition(rawDefStr)) {
                std::string redirectWord = extractRedirectWord(rawDefStr);
                if (!redirectWord.empty()) {
                    std::string redirectDef = searchInternal(redirectWord, 1);
                    if (!redirectDef.empty() && redirectDef != "DATABASE_ERROR" && redirectDef != "MAX_REDIRECT_DEPTH" && !isRedirectDefinition(redirectDef)) {
                        std::string cleanDef = removeTags(redirectDef);
                        std::string result = wordStr + "|" + cleanDef + "\n\n(See: " + redirectWord + ")";
                        std::cout << "[RANDOM] Word of the day (via redirect): " << wordStr << std::endl;
                        logger.log("RANDOM_WORD: '" + wordStr + "' selected (redirect to " + redirectWord + ")");
                        return result;
                    }
                }
                continue;
            }
            std::string defStr = removeTags(rawDefStr);
            if (defStr.empty()) continue;
            std::string result = wordStr + "|" + defStr;
            std::cout << "[RANDOM] Word of the day: " << wordStr << std::endl;
            logger.log("RANDOM_WORD: '" + wordStr + "' selected");
            return result;
        }
        logger.log("ERROR: Random word selection failed after max attempts");
        return "NOT_FOUND";
    }

    std::string getSourceName() const override { return "SQLite Dictionary: " + dbPath; }
    bool isConnected() const { return db != nullptr; }
};

// ============================================================================
// CLASS: Translator
// ============================================================================
class Translator {
private:
    IDictionarySource* dictionary;
    Language sourceLanguage;
    Language targetLanguage;
public:
    Translator(IDictionarySource* dict, const Language& source, const Language& target)
        : dictionary(dict), sourceLanguage(source), targetLanguage(target) {
        std::cout << "[INFO] Translator initialized: " << sourceLanguage.toString() << " -> " << targetLanguage.toString() << std::endl;
    }
    Translator(const Translator&) = delete;
    Translator& operator=(const Translator&) = delete;
    std::string translate(const std::string& query) { return dictionary->search(query); }

    // In-memory dictionary cache stored as word -> definition
    static std::map<std::string, std::string> memoryDictionary;
    static const std::string memoryDictionaryPath;

    // Load dictionary from file into memoryDictionary (best-effort, non-fatal)
    static void loadDictionaryFromFile() {
        try {
            std::ifstream ifs(memoryDictionaryPath);
            if (!ifs.is_open()) return;
            std::string line;
            while (std::getline(ifs, line)) {
                if (line.empty()) continue;
                size_t sep = line.find('|');
                if (sep == std::string::npos) continue;
                std::string word = line.substr(0, sep);
                std::string def = line.substr(sep + 1);
                memoryDictionary[word] = def;
            }
            ifs.close();
        } catch (const std::exception& ex) {
            std::cerr << "[WARNING] Failed to load memory dictionary: " << ex.what() << std::endl;
        }
    }

    // Save memoryDictionary to file (overwrite/truncate) using safe replace.
    // Non-fatal on error.
    static void saveDictionaryToFile() {
        try {
            std::string tempPath = memoryDictionaryPath + ".tmp";
            std::ofstream ofs(tempPath, std::ios::out | std::ios::trunc);
            if (!ofs.is_open()) {
                std::cerr << "[ERROR] Could not open " << tempPath << " for writing" << std::endl;
                return;
            }
            for (const auto& kv : memoryDictionary) {
                ofs << kv.first << '|' << kv.second << '\n';
            }
            ofs.close();

            // Atomically replace the original file (Windows API)
            // Uses MOVEFILE_REPLACE_EXISTING to overwrite if present.
            if (!MoveFileExA(tempPath.c_str(), memoryDictionaryPath.c_str(), MOVEFILE_REPLACE_EXISTING)) {
                std::cerr << "[ERROR] Failed to replace " << memoryDictionaryPath << " with " << tempPath << " (MoveFileExA error: " << GetLastError() << ")" << std::endl;
                // attempt cleanup
                ::DeleteFileA(tempPath.c_str());
            }
        } catch (const std::exception& ex) {
            std::cerr << "[ERROR] Failed to save memory dictionary: " << ex.what() << std::endl;
        }
    }

    // Append a single word to the dictionary file immediately (safe append).
    static void appendWordToFile(const std::string& word, const std::string& def) {
        try {
            std::ofstream ofs(memoryDictionaryPath, std::ios::out | std::ios::app);
            if (!ofs.is_open()) {
                std::cerr << "[ERROR] Could not open " << memoryDictionaryPath << " for appending" << std::endl;
                return;
            }
            ofs << word << '|' << def << '\n';
            ofs.close();
        } catch (const std::exception& ex) {
            std::cerr << "[ERROR] Failed to append to memory dictionary: " << ex.what() << std::endl;
        }
    }

    std::string processCommand(const std::string& command) {
        std::istringstream iss(command);
        std::string cmd, arg1, arg2;

        std::getline(iss, cmd, '|');
        std::getline(iss, arg1, '|');
        std::getline(iss, arg2, '|');

        if (cmd == "TRANSLATE") return translate(arg1);
        else if (cmd == "ADD" || cmd == "ADD_WORD") {
            if (arg1.empty()) return "Error|Headword cannot be empty";
            if (arg2.empty()) return "Error|Definition cannot be empty";

            // 1) Check in-memory dictionary first
            auto it = memoryDictionary.find(arg1);
            if (it != memoryDictionary.end()) return "Error|Word already exists";

            // 2) Check persistent backend BEFORE adding to avoid duplicates
            std::string backendSearch = dictionary->search(arg1);
            if (!backendSearch.empty() && backendSearch != "NOT_FOUND" && backendSearch != "DATABASE_ERROR" && backendSearch != "MAX_REDIRECT_DEPTH") {
                return "Error|Word already exists";
            }
            if (dictionary->wordExists(arg1)) return "Error|Word already exists";

            // 3) Update Memory (RAM) for instant search
            memoryDictionary[arg1] = arg2;

            // 4) FORCE WRITE TO SQLITE DB (direct raw sqlite3 usage)
            sqlite3* db = nullptr;
            int rc = sqlite3_open("eng_ukr_dictionary.db", &db);

            bool dbOk = false;
            if (rc == SQLITE_OK && db) {
                const char* sql = "INSERT INTO word (w, m) VALUES (?, ?);";
                sqlite3_stmt* stmt = nullptr;

                if (sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) == SQLITE_OK) {
                    // Bind parameters to prevent SQL injection issues
                    sqlite3_bind_text(stmt, 1, arg1.c_str(), -1, SQLITE_STATIC);
                    sqlite3_bind_text(stmt, 2, arg2.c_str(), -1, SQLITE_STATIC);

                    if (sqlite3_step(stmt) == SQLITE_DONE) {
                        std::cout << "[SUCCESS] Word written to DB: " << arg1 << std::endl;
                        dbOk = true;
                    } else {
                        std::cerr << "[ERROR] DB Insert failed: " << sqlite3_errmsg(db) << std::endl;
                    }
                    sqlite3_finalize(stmt);
                } else {
                    std::cerr << "[ERROR] SQL Prepare failed: " << sqlite3_errmsg(db) << std::endl;
                }
                sqlite3_close(db);
            } else {
                std::cerr << "[CRITICAL] Cannot open eng_ukr_dictionary.db: " << (db ? sqlite3_errmsg(db) : "open failed") << std::endl;
                if (db) sqlite3_close(db);
            }

            // If DB write failed, rollback in-memory change to avoid divergence
            if (!dbOk) {
                memoryDictionary.erase(arg1);
                return "Error|Failed to persist to database";
            }

            // Success
            return "Success|Word added";
        }
        else if (cmd == "UPDATE_WORD") {
            // New behaviour: update in-memory map and persist to dictionary.txt
            if (arg1.empty() || arg2.empty()) return "Error|Headword and definition required";
            auto it = memoryDictionary.find(arg1);
            if (it != memoryDictionary.end()) {
                it->second = arg2;
                saveDictionaryToFile();
                return "Success|Word updated.";
            }
            // Fallback: try updating persistent dictionary via IDataSource
            if (dictionary->updateWord(arg1, arg2)) return "Success|Word updated: " + arg1;
            return "Error|Word not found.";
        }
        else if (cmd == "DELETE_WORD") {
            if (arg1.empty()) return "Error|Headword required";
            auto it = memoryDictionary.find(arg1);
            if (it != memoryDictionary.end()) {
                memoryDictionary.erase(it);
                saveDictionaryToFile();
                return "Success|Word deleted.";
            }
            // Fallback to persistent backend
            if (dictionary->deleteWord(arg1)) return "Success|Word deleted: " + arg1;
            return "Error|Word not found.";
        }
        else if (cmd == "EXISTS") return dictionary->wordExists(arg1) ? "YES" : "NO";
        else if (cmd == "PING") return "PONG";
        else if (cmd == "GET_RANDOM") return dictionary->getRandomWord();
        else if (cmd == "GET_SIZE") return std::to_string(dictionary->getSize());
        else if (cmd == "GET_LANGUAGES") return sourceLanguage.getCode() + "|" + targetLanguage.getCode();
        return "UNKNOWN_COMMAND";
    }

    Language getSourceLanguage() const { return sourceLanguage; }
    Language getTargetLanguage() const { return targetLanguage; }
    void setSourceLanguage(const Language& lang) { sourceLanguage = lang; }
    void setTargetLanguage(const Language& lang) { targetLanguage = lang; }
    void swapLanguages() { std::swap(sourceLanguage, targetLanguage); std::cout << "[INFO] Languages swapped: " << sourceLanguage.toString() << " -> " << targetLanguage.toString() << std::endl; }
    IDictionarySource* getDictionary() const { return dictionary; }
};

// ============================================================================
// CLASS: Server
// ============================================================================
class Server {
private:
    SOCKET listenSocket;
    std::string ipAddress;
    int port;
    bool running;
    Translator& translator;
public:
    Server(Translator& trans, const std::string& ip = "127.0.0.1", int p = 8080) : listenSocket(INVALID_SOCKET), ipAddress(ip), port(p), running(false), translator(trans) {}
    ~Server() { stop(); }
    bool start() {
        WSADATA wsaData; int iResult = WSAStartup(MAKEWORD(2, 2), &wsaData); if (iResult != 0) { std::cerr << "[ERROR] WSAStartup failed: " << iResult << std::endl; return false; }
        std::cout << "[OK] WinSock initialized" << std::endl;
        listenSocket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP); if (listenSocket == INVALID_SOCKET) { std::cerr << "[ERROR] Socket creation failed: " << WSAGetLastError() << std::endl; WSACleanup(); return false; }
        std::cout << "[OK] Socket created" << std::endl;
        struct sockaddr_in serverAddr; serverAddr.sin_family = AF_INET; serverAddr.sin_addr.s_addr = inet_addr(ipAddress.c_str()); serverAddr.sin_port = htons(port);
        if (bind(listenSocket, (struct sockaddr*)&serverAddr, sizeof(serverAddr)) == SOCKET_ERROR) { std::cerr << "[ERROR] Bind failed: " << WSAGetLastError() << std::endl; std::cerr << "[HINT] Port " << port << " may be in use" << std::endl; closesocket(listenSocket); WSACleanup(); return false; }
        std::cout << "[OK] Bound to " << ipAddress << ":" << port << std::endl;
        if (listen(listenSocket, SOMAXCONN) == SOCKET_ERROR) { std::cerr << "[ERROR] Listen failed: " << WSAGetLastError() << std::endl; closesocket(listenSocket); WSACleanup(); return false; }
        std::cout << "[OK] Server listening" << std::endl; running = true; return true;
    }
    void run() {
        std::cout << std::endl;
        std::cout << "========================================" << std::endl;
        std::cout << "=== Electronic Dictionary Server ===" << std::endl;
        std::cout << "========================================" << std::endl;
        std::cout << "Address: " << ipAddress << ":" << port << std::endl;
        std::cout << "Languages: " << translator.getSourceLanguage().toString() << " <-> " << translator.getTargetLanguage().toString() << std::endl;
        std::cout << std::endl;
        while (running) {
            std::cout << "[WAIT] Waiting for client connection..." << std::endl;
            SOCKET clientSocket = accept(listenSocket, NULL, NULL);
            if (clientSocket == INVALID_SOCKET) { if (running) std::cerr << "[ERROR] Accept failed: " << WSAGetLastError() << std::endl; continue; }
            handleClient(clientSocket);
        }
    }
    void stop() { running = false; if (listenSocket != INVALID_SOCKET) { closesocket(listenSocket); listenSocket = INVALID_SOCKET; } WSACleanup(); }
private:
    void handleClient(SOCKET clientSocket) {
        std::cout << std::endl;
        std::cout << "========================================" << std::endl;
        std::cout << "[CONNECTED] Client connected!" << std::endl;
        std::cout << "========================================" << std::endl;
        char recvbuf[4096]; int recvbuflen = sizeof(recvbuf) - 1;
        while (true) {
            std::cout << "[WAIT] Waiting for data from client..." << std::endl;
            int iResult = recv(clientSocket, recvbuf, recvbuflen, 0);
            if (iResult > 0) {
                recvbuf[iResult] = '\0'; std::string receivedData(recvbuf, iResult);
                std::cout << "[RECEIVED] Command: \"";
                printUtf(receivedData);
                std::cout << " (" << iResult << " bytes)" << std::endl;
                std::cout << "[PROCESS] Processing command..." << std::endl;
                std::string response = translator.processCommand(receivedData);
				// Переконуємося, що відповідь закінчується новим рядком, щоб клієнт міг коректно її прочитати
                if (response.empty() || response.back() != '\n') response += '\n';
                std::string displayResponse = response; if (displayResponse.length() > 100) displayResponse = displayResponse.substr(0, 100) + "... [trimmed]";
                std::cout << "[RESPONSE] ";
                printUtf(displayResponse);
                int sendLen = static_cast<int>(response.length()); int iSendResult = send(clientSocket, response.c_str(), sendLen, 0);
                if (iSendResult == SOCKET_ERROR) { std::cerr << "[ERROR] Send failed: " << WSAGetLastError() << std::endl; break; }
                std::cout << "[OK] Sent " << iSendResult << " bytes" << std::endl; std::cout << "----------------------------------------" << std::endl;
            }
            else if (iResult == 0) { std::cout << "[DISCONNECTED] Client closed connection" << std::endl; break; }
            else { int error = WSAGetLastError(); if (error == WSAECONNRESET) std::cout << "[DISCONNECTED] Connection reset by client" << std::endl; else std::cerr << "[ERROR] recv failed: " << error << std::endl; break; }
        }
        closesocket(clientSocket);
        std::cout << "[CLOSED] Client socket closed" << std::endl;
        std::cout << std::endl;
    }
};

// ============================================================================
// MAIN
// ============================================================================
int main() {
    // Ensure console CP is set to UTF-8 as early as possible (Windows only)
    #ifdef _WIN32
    SetConsoleOutputCP(65001); // Force console output to UTF-8
    SetConsoleCP(65001);       // Force console input to UTF-8
    #endif

    // set locale to system (fallback)
    std::setlocale(LC_ALL, "");

    // Enable ANSI escape sequences
    HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD dwMode = 0; GetConsoleMode(hOut, &dwMode); SetConsoleMode(hOut, dwMode | ENABLE_VIRTUAL_TERMINAL_PROCESSING);

    std::cout << "========================================" << std::endl;
    std::cout << "[START] Server initializing..." << std::endl;
    std::cout << "========================================" << std::endl;

    Language english("EN", "English", "English");
    Language ukrainian("UK", "Ukrainian", "Ukrainian");

    std::cout << "[OK] Languages created: " << english.toString() << ", " << ukrainian.toString() << std::endl;

    Logger logger("server_log.txt");
    std::cout << "[OK] Logger initialized" << std::endl;

    std::cout << "[INFO] Loading dictionary..." << std::endl;
    SQLiteDictionary dictionary("eng_ukr_dictionary.db", logger);
    if (!dictionary.isConnected()) { std::cerr << "[ERROR] Failed to connect to database!" << std::endl; std::cout << "Press Enter to exit..." << std::endl; std::cin.get(); return 1; }
    size_t dictSize = dictionary.getSize();
    std::cout << "[OK] Dictionary loaded: " << dictSize << " entries" << std::endl;
    std::cout << "[OK] Dictionary source: " << dictionary.getSourceName() << std::endl;
    if (dictSize == 0) std::cerr << "[WARNING] Dictionary is empty! Check the database file." << std::endl;

    Translator translator(&dictionary, english, ukrainian);
    std::cout << "[OK] Translator initialized" << std::endl;

    Server server(translator, "127.0.0.1", 8080);
    if (!server.start()) { std::cerr << "[ERROR] Failed to start server!" << std::endl; std::cout << "Press Enter to exit..." << std::endl; std::cin.get(); return 1; }

    // Load in-memory dictionary from file (if it exists)
    Translator::loadDictionaryFromFile();

    std::cout << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << "[DONE] Server started successfully!" << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << std::endl;

    server.run();
    // Save in-memory dictionary to file on exit
    Translator::saveDictionaryToFile();
    return 0;
}

std::map<std::string, std::string> Translator::memoryDictionary;
const std::string Translator::memoryDictionaryPath = "dictionary.txt";