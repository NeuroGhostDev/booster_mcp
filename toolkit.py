"""
Toolkit MCP — расширенные инструменты для работы со сложными проектами
Grep, чтение с контекстом, git diff, запуск команд, анализ ошибок, конфиги, память, дубликаты
"""
import re
import os
import json
import subprocess
import hashlib
from pathlib import Path
from typing import Optional
from collections import defaultdict
from difflib import unified_diff


class CodeToolkit:
    """Набор инструментов для продуктивной работы с кодом"""

    def __init__(self, indexer, repos: list[str]):
        self.indexer = indexer
        self.repos = repos
        self.memory_file = Path.home() / ".booster_memory.json"
        self._load_memory()

    def _load_memory(self):
        """Загружает долгосрочную память из файла"""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    self.memory = json.load(f)
            except:
                self.memory = {}
        else:
            self.memory = {}

    def _save_memory(self):
        """Сохраняет память на диск"""
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, indent=2, ensure_ascii=False)

    # === 1. Grep-поиск ===

    def code_grep(self, pattern: str, file_pattern: str = "*",
                  ignore_case: bool = True, max_results: int = 100) -> list[dict]:
        """Регулярный поиск по всем файлам проектов"""
        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return [{"error": f"Невалидный regex: {e}"}]

        results = []
        for repo in self.repos:
            repo_path = Path(repo)
            if not repo_path.exists():
                continue

            for file in repo_path.rglob(file_pattern):
                if not file.is_file():
                    continue
                if file.suffix in [".pyc", ".bin", ".exe", ".dll", ".so"]:
                    continue

                try:
                    content = file.read_text(encoding="utf-8", errors="ignore")
                    lines = content.split("\n")

                    for line_num, line in enumerate(lines, 1):
                        matches = regex.findall(line)
                        if matches:
                            results.append({
                                "file": str(file),
                                "line": line_num,
                                "content": line.strip()[:200],
                                "matches": matches[:5]
                            })
                            if len(results) >= max_results:
                                return results
                except Exception:
                    continue

        return results

    # === 2. Чтение с контекстом ===

    def read_with_context(self, file: str, line: int,
                          context: int = 20) -> dict:
        """Читает файл с ±N строк вокруг указанной"""
        file_path = Path(file)
        if not file_path.exists():
            return {"error": f"Файл не найден: {file}"}

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            start = max(0, line - context - 1)
            end = min(len(lines), line + context)

            context_lines = lines[start:end]

            # Подсветка целевой строки
            target_line = lines[line - 1] if 0 < line <= len(lines) else ""

            return {
                "file": str(file_path),
                "target_line": line,
                "target_content": target_line,
                "context_start": start + 1,
                "context_end": end,
                "lines": [
                    {"num": i + start + 1, "content": l}
                    for i, l in enumerate(context_lines)
                ],
                "total_lines": len(lines)
            }
        except Exception as e:
            return {"error": f"Ошибка чтения: {e}"}

    def read_file(self, file: str, start: int = 0, end: int = 100) -> dict:
        """Читает диапазон строк из файла"""
        file_path = Path(file)
        if not file_path.exists():
            return {"error": f"Файл не найден: {file}"}

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            selected = lines[start:end]

            return {
                "file": str(file_path),
                "start": start,
                "end": min(end, len(lines)),
                "total_lines": len(lines),
                "lines": [
                    {"num": i + start, "content": l}
                    for i, l in enumerate(selected)
                ]
            }
        except Exception as e:
            return {"error": f"Ошибка чтения: {e}"}

    # === 3. Git diff ===

    def git_diff(self, path: str, commit: str = "HEAD",
                 staged: bool = False) -> dict:
        """Показывает изменения в файле/репозитории"""
        path_obj = Path(path)
        if not path_obj.exists():
            return {"error": f"Путь не найден: {path}"}

        # Находим корень git
        git_root = path_obj
        while git_root != git_root.parent and not (git_root / ".git").exists():
            git_root = git_root.parent

        if not (git_root / ".git").exists():
            return {"error": "Не git репозиторий"}

        try:
            # Определяем команду
            if staged:
                cmd = ["git", "-C", str(git_root), "diff", "--cached", commit]
            else:
                cmd = ["git", "-C", str(git_root), "diff", commit]

            if path_obj.is_file():
                rel_path = path_obj.relative_to(git_root)
                cmd.append("--", str(rel_path))
            elif path_obj.is_dir():
                rel_path = path_obj.relative_to(git_root)
                cmd.append("--", str(rel_path))

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30)

            return {
                "path": str(path),
                "commit": commit,
                "staged": staged,
                "diff": result.stdout,
                "error": result.stderr if result.returncode != 0 else None
            }
        except subprocess.TimeoutExpired:
            return {"error": "Таймаут git diff"}
        except Exception as e:
            return {"error": f"Ошибка git: {e}"}

    def git_log(self, path: str, limit: int = 10) -> dict:
        """История коммитов для файла/репозитория"""
        path_obj = Path(path)
        if not path_obj.exists():
            return {"error": f"Путь не найден: {path}"}

        git_root = path_obj
        while git_root != git_root.parent and not (git_root / ".git").exists():
            git_root = git_root.parent

        if not (git_root / ".git").exists():
            return {"error": "Не git репозиторий"}

        try:
            cmd = ["git", "-C", str(git_root), "log", f"-{limit}", "--oneline"]
            if path_obj.exists():
                rel_path = path_obj.relative_to(git_root)
                cmd.append("--", str(rel_path))

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30)

            commits = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split(" ", 1)
                    commits.append({
                        "hash": parts[0] if parts else "",
                        "message": parts[1] if len(parts) > 1 else ""
                    })

            return {"commits": commits}
        except Exception as e:
            return {"error": f"Ошибка git: {e}"}

    # === 4. Запуск команд ===

    def run_command(self, cmd: str, cwd: str = None,
                    timeout: int = 30000, shell: bool = True) -> dict:
        """Выполняет команду в песочнице"""
        work_dir = Path(cwd) if cwd else Path(
            self.repos[0]) if self.repos else Path.home()

        if not work_dir.exists():
            return {"error": f"Директория не найдена: {work_dir}"}

        try:
            result = subprocess.run(
                cmd,
                shell=shell,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}
            )

            return {
                "command": cmd,
                "cwd": str(work_dir),
                "returncode": result.returncode,
                "stdout": result.stdout[:50000],  # Ограничение вывода
                "stderr": result.stderr[:50000]
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Таймаут команды ({timeout}мс)"}
        except Exception as e:
            return {"error": f"Ошибка выполнения: {e}"}

    # === 5. Анализ ошибок ===

    def analyze_error(self, error_text: str,
                      symbols: Optional[list[str]] = None) -> dict:
        """Ищет в коде потенциальные причины ошибки"""
        # Извлекаем ключевые слова из ошибки
        keywords = re.findall(r'\b[A-Za-z_][A-Za-z0-9_]+\b', error_text)
        keywords = [k for k in keywords if len(k) > 2 and k.lower() not in
                    ['the', 'and', 'for', 'not', 'with', 'from', 'import', 'error', 'exception']]

        # Ищем совпадения в символах
        matching_symbols = []
        for file_path, syms in self.indexer.symbols.items():
            for sym in syms:
                sym_name = sym.get("name", "")
                for kw in keywords:
                    if kw.lower() in sym_name.lower():
                        matching_symbols.append({
                            "symbol": sym_name,
                            "file": file_path,
                            "line": sym.get("start", 0)
                        })

        # Ищем текст ошибки в коде
        grep_results = []
        for kw in keywords[:5]:  # Ограничиваем количество запросов
            grep = self.code_grep(re.escape(kw), max_results=10)
            grep_results.extend(grep)

        # Семантический поиск
        semantic_results = []
        if self.indexer.embedder:
            try:
                vec = self.indexer.embedder.embed(error_text[:500])
                semantic_results = self.indexer.search(vec)
            except:
                pass

        return {
            "error_text": error_text[:1000],
            "keywords": keywords[:10],
            "matching_symbols": matching_symbols[:20],
            "code_matches": grep_results[:20],
            "semantic_matches": semantic_results[:10]
        }

    # === 6. Поиск конфигов ===

    def list_configs(self, repo: str = None) -> dict:
        """Находит все конфиги в репозитории"""
        if not repo and self.repos:
            repo = self.repos[0]

        if not repo:
            return {"error": "Нет репозиториев"}

        repo_path = Path(repo)
        if not repo_path.exists():
            return {"error": f"Репозиторий не найден: {repo}"}

        config_patterns = [
            # Файлы
            ".env", ".env.local", ".env.production", ".env.development",
            ".envrc", ".dockerenv",
            "config.json", "config.yaml", "config.yml", "config.toml",
            "settings.json", "settings.yaml", "settings.toml",
            "settings.py", "config.py", "local_settings.py",
            "docker-compose.yml", "docker-compose.yaml",
            "Dockerfile", "Containerfile",
            "pyproject.toml", "setup.py", "setup.cfg",
            "package.json", "tsconfig.json", "webpack.config.js",
            "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
            ".gitignore", ".dockerignore",
            # Расширения
            "*.env", "*.ini", "*.cfg", "*.conf", "*.properties"
        ]

        configs = []
        for pattern in config_patterns:
            if "*" in pattern:
                for file in repo_path.rglob(pattern):
                    if file.is_file():
                        configs.append(str(file))
            else:
                for file in repo_path.rglob(pattern):
                    if file.is_file():
                        configs.append(str(file))

        # Группировка по типу
        grouped = defaultdict(list)
        for cfg in configs:
            cfg_path = Path(cfg)
            ext = cfg_path.suffix.lower()
            name = cfg_path.name.lower()

            if name.startswith(".env"):
                grouped["env"].append(cfg)
            elif ext in [".yaml", ".yml"]:
                grouped["yaml"].append(cfg)
            elif ext == ".json":
                grouped["json"].append(cfg)
            elif ext == ".toml":
                grouped["toml"].append(cfg)
            elif ext == ".py" and ("config" in name or "setting" in name):
                grouped["python"].append(cfg)
            elif name == "dockerfile" or name.startswith("dockerfile"):
                grouped["docker"].append(cfg)
            elif "docker-compose" in name:
                grouped["docker-compose"].append(cfg)
            else:
                grouped["other"].append(cfg)

        return {
            "repo": str(repo),
            "total": len(configs),
            "configs": dict(grouped)
        }

    # === 7. Долгосрочная память ===

    def project_memory(self, action: str, key: str,
                       value: str = None, repo: str = None) -> dict:
        """Сохраняет/читает инсайты о проекте между сессиями"""
        if not repo and self.repos:
            repo = self.repos[0]

        repo_key = hashlib.md5(repo.encode()).hexdigest()[
            :8] if repo else "global"

        if repo_key not in self.memory:
            self.memory[repo_key] = {}

        repo_memory = self.memory[repo_key]

        if action == "get":
            return {
                "key": key,
                "value": repo_memory.get(key),
                "repo": repo
            }
        elif action == "set":
            if value is None:
                return {"error": "Требуется value для set"}
            repo_memory[key] = {
                "value": value,
                "updated": str(Path.home())
            }
            self._save_memory()
            return {"key": key, "value": value, "repo": repo}
        elif action == "delete":
            if key in repo_memory:
                del repo_memory[key]
                self._save_memory()
            return {"deleted": key, "repo": repo}
        elif action == "list":
            return {
                "repo": repo,
                "keys": list(repo_memory.keys()),
                "count": len(repo_memory)
            }
        elif action == "clear":
            self.memory[repo_key] = {}
            self._save_memory()
            return {"cleared": repo}
        else:
            return {"error": f"Неизвестное действие: {action}"}

    # === 8. Сравнение символов ===

    def compare_symbols(self, symbol: str, file1: str, file2: str) -> dict:
        """Сравнивает реализацию символа в двух файлах"""
        def extract_symbol_content(file_path: str, sym_name: str) -> Optional[str]:
            path = Path(file_path)
            if not path.exists():
                return None

            content = path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            # Ищем символ в файле
            for i, syms in self.indexer.symbols.items():
                if Path(i).resolve() == path.resolve():
                    for sym in syms:
                        if sym.get("name") == sym_name:
                            start = sym.get("start", 0)
                            end = sym.get("end", len(lines))
                            return "\n".join(lines[start:end])

            return None

        content1 = extract_symbol_content(file1, symbol)
        content2 = extract_symbol_content(file2, symbol)

        if not content1:
            return {"error": f"Символ '{symbol}' не найден в {file1}"}
        if not content2:
            return {"error": f"Символ '{symbol}' не найден в {file2}"}

        diff = list(unified_diff(
            content1.split("\n"),
            content2.split("\n"),
            fromfile=file1,
            tofile=file2,
            lineterm=""
        ))

        return {
            "symbol": symbol,
            "file1": file1,
            "file2": file2,
            "diff": "\n".join(diff),
            "lines1": len(content1.split("\n")),
            "lines2": len(content2.split("\n"))
        }

    # === 9. Поиск дубликатов ===

    def find_duplicates(self, min_lines: int = 5,
                        max_results: int = 50) -> list[dict]:
        """Ищет похожие блоки кода"""
        # Хэш для каждого блока N строк
        block_hashes = defaultdict(list)

        for file_path, syms in self.indexer.symbols.items():
            try:
                content = Path(file_path).read_text(
                    encoding="utf-8", errors="ignore")
                lines = content.split("\n")

                for i in range(len(lines) - min_lines + 1):
                    block = "\n".join(lines[i:i + min_lines])
                    # Нормализация: убираем лишние пробелы
                    normalized = "\n".join(l.strip()
                                           for l in block.split("\n") if l.strip())

                    if len(normalized) < 50:  # Пропускаем слишком короткие
                        continue

                    block_hash = hashlib.md5(normalized.encode()).hexdigest()
                    block_hashes[block_hash].append({
                        "file": file_path,
                        "start_line": i,
                        "content": block[:200]
                    })
            except:
                continue

        # Находим дубликаты
        duplicates = []
        for hash_val, blocks in block_hashes.items():
            if len(blocks) > 1:
                # Проверяем, что блоки из разных файлов или разных мест
                unique_files = set(b["file"] for b in blocks)
                if len(unique_files) > 1 or len(blocks) > 1:
                    duplicates.append({
                        "hash": hash_val,
                        "min_lines": min_lines,
                        "occurrences": blocks[:10]
                    })

                    if len(duplicates) >= max_results:
                        break

        return duplicates

    # === 10. Внешние зависимости ===

    def external_deps(self, symbol: str = None,
                      file: str = None) -> dict:
        """Находит внешние API, БД, очереди, которые использует код"""
        external_patterns = {
            "http_calls": [
                r'requests\.(get|post|put|delete|patch)\s*\(',
                r'httpx\.(get|post|put|delete|patch)\s*\(',
                r'urllib\.request\.',
                r'fetch\s*\(',
                r'axios\.(get|post|put|delete)\s*\(',
            ],
            "database": [
                r'\.execute\s*\(',
                r'\.query\s*\(',
                r'\.find\s*\(',
                r'\.insert\s*\(',
                r'\.update\s*\(',
                r'\.delete\s*\(',
                r'SELECT|INSERT|UPDATE|DELETE|CREATE|DROP',
            ],
            "redis": [
                r'redis\.',
                r'\.set\s*\(',
                r'\.get\s*\(',
                r'\.expire\s*\(',
            ],
            "kafka_rabbit": [
                r'kafka\.',
                r'pika\.',
                r'rabbitmq\.',
                r'\.publish\s*\(',
                r'\.consume\s*\(',
            ],
            "file_io": [
                r'open\s*\([^)]+,\s*["\'][wb]+\s*["\']',
                r'\.write\s*\(',
                r'\.read\s*\(',
                r'os\.path\.',
                r'Path\s*\(',
            ],
            "subprocess": [
                r'subprocess\.',
                r'os\.system\s*\(',
                r'os\.popen\s*\(',
            ],
            "logging": [
                r'logger\.(info|debug|warning|error|critical)\s*\(',
                r'logging\.(info|debug|warning|error|critical)\s*\(',
                r'print\s*\(',
            ],
        }

        results = {k: [] for k in external_patterns.keys()}

        # Если указан файл — ищем только в нём
        files_to_search = []
        if file:
            files_to_search = [file]
        elif symbol:
            # Ищем файлы с этим символом
            for file_path, syms in self.indexer.symbols.items():
                for sym in syms:
                    if sym.get("name") == symbol:
                        files_to_search.append(file_path)
                        break
        else:
            # Все файлы
            files_to_search = list(self.indexer.symbols.keys())

        for file_path in files_to_search[:100]:  # Ограничение
            try:
                content = Path(file_path).read_text(
                    encoding="utf-8", errors="ignore")

                for category, patterns in external_patterns.items():
                    for pattern in patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            results[category].append({
                                "file": file_path,
                                "pattern": pattern,
                                "matches": len(matches)
                            })
            except:
                continue

        # Фильтруем пустые категории
        results = {k: v for k, v in results.items() if v}

        return {
            "symbol": symbol,
            "file": file,
            "external_dependencies": results
        }


def setup_toolkit_tools(mcp, indexer, repos: list[str]):
    """Регистрирует инструменты toolkit в MCP сервере"""
    toolkit = CodeToolkit(indexer, repos)

    @mcp.tool()
    def code_grep(pattern: str, file_pattern: str = "*",
                  ignore_case: bool = True, max_results: int = 100):
        """Регулярный поиск по всем файлам проектов"""
        return toolkit.code_grep(pattern, file_pattern, ignore_case, max_results)

    @mcp.tool()
    def read_with_context(file: str, line: int, context: int = 20):
        """Читает файл с ±N строк вокруг указанной линии"""
        return toolkit.read_with_context(file, line, context)

    @mcp.tool()
    def read_file(file: str, start: int = 0, end: int = 100):
        """Читает диапазон строк из файла (0-indexed)"""
        return toolkit.read_file(file, start, end)

    @mcp.tool()
    def git_diff(path: str, commit: str = "HEAD", staged: bool = False):
        """Показывает изменения в файле/репозитории"""
        return toolkit.git_diff(path, commit, staged)

    @mcp.tool()
    def git_log(path: str, limit: int = 10):
        """История коммитов для файла/репозитория"""
        return toolkit.git_log(path, limit)

    @mcp.tool()
    def run_command(cmd: str, cwd: str = None, timeout: int = 30000):
        """Выполняет команду в shell. timeout в миллисекундах"""
        return toolkit.run_command(cmd, cwd, timeout)

    @mcp.tool()
    def analyze_error(error_text: str, symbols: Optional[list[str]] = None):
        """Ищет в коде потенциальные причины ошибки по тексту stacktrace"""
        return toolkit.analyze_error(error_text, symbols)

    @mcp.tool()
    def list_configs(repo: str = None):
        """Находит все конфигурационные файлы в репозитории"""
        return toolkit.list_configs(repo)

    @mcp.tool()
    def project_memory(action: str, key: str, value: str = None, repo: str = None):
        """
        Управление долгосрочной памятью проекта.
        action: get, set, delete, list, clear
        """
        return toolkit.project_memory(action, key, value, repo)

    @mcp.tool()
    def compare_symbols(symbol: str, file1: str, file2: str):
        """Сравнивает реализацию символа в двух файлах через diff"""
        return toolkit.compare_symbols(symbol, file1, file2)

    @mcp.tool()
    def find_duplicates(min_lines: int = 5, max_results: int = 50):
        """Ищет дублирующиеся блоки кода (copy-paste)"""
        return toolkit.find_duplicates(min_lines, max_results)

    @mcp.tool()
    def external_deps(symbol: str = None, file: str = None):
        """Находит внешние зависимости: HTTP, БД, Redis, Kafka, файлы, subprocess"""
        return toolkit.external_deps(symbol, file)

    return toolkit
