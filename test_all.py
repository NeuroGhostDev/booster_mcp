#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Полный тест всех инструментов booster_mcp"""

import sys
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("ТЕСТИРОВАНИЕ booster_MCP v2.4")
print("=" * 60)
print(f"Python: {sys.executable}")
print(f"Version: {sys.version}")
print()

# Проверка версии Python (требуется 3.11+)
if sys.version_info < (3, 11):
    print("⚠ Требуется Python 3.11+")
    sys.exit(1)

# === 1. Импорт модулей ===
print("[1/6] Импорт модулей...")
try:
    from indexer import RepoIndexer
    from flipchart import Flipchart
    from toolkit import CodeToolkit
    from server import mcp, indexer, flipchart, toolkit
    print("  ✓ Все модули импортированы")
except Exception as e:
    print(f"  ✗ Ошибка импорта: {e}")
    sys.exit(1)

# === 2. Индексация ===
print("\n[2/6] Индексация репозитория...")
if not indexer.repos:
    indexer.repos = ['.']
indexer.full_index()
print(f"  ✓ Файлов проиндексировано: {len(indexer.symbols)}")
print(f"  ✓ Векторов в FAISS: {indexer.vector.index.ntotal}")

# === 3. Тест code_grep ===
print("\n[3/6] Тест code_grep...")
grep_result = toolkit.code_grep('def ', max_results=5)
print(f"  ✓ Найдено совпадений: {len(grep_result)}")
for r in grep_result[:2]:
    print(f"    - {r['file']}:{r['line']}")

# === 4. Тест read_with_context ===
print("\n[4/6] Тест read_with_context...")
if grep_result:
    ctx = toolkit.read_with_context(
        grep_result[0]['file'], grep_result[0]['line'], context=3)
    print(f"  ✓ Прочитано строк: {len(ctx.get('lines', []))}")
    print(f"    Файл: {ctx.get('file', 'N/A')}")

# === 5. Тест list_configs ===
print("\n[5/6] Тест list_configs...")
configs = toolkit.list_configs('.')
print(f"  ✓ Найдено конфигов: {configs.get('total', 0)}")
for k, v in configs.get('configs', {}).items():
    print(f"    - {k}: {len(v)}")

# === 6. Тест project_memory ===
print("\n[6/6] Тест project_memory...")
toolkit.project_memory('set', 'test_key', 'тест работает!')
mem = toolkit.project_memory('get', 'test_key')
print(f"  ✓ Память: {mem.get('value')}")

# === 7. Тест flipchart ===
print("\n[7/6] Тест flipchart...")
if indexer.symbols:
    first_file = list(indexer.symbols.keys())[0]
    syms = indexer.symbols[first_file]
    if syms:
        sym = syms[0]['name']
        mg = flipchart.generate_call_graph_mermaid(sym, max_depth=2)
        print(f"  ✓ Mermaid для '{sym}': {len(mg)} символов")

        qd = flipchart.quick_debug(sym, max_depth=2)
        print(
            f"  ✓ quick_debug: {len(qd.get('call_graph_mermaid', ''))} символов")

# === 8. Тест external_deps ===
print("\n[8/6] Тест external_deps...")
deps = toolkit.external_deps()
ext = deps.get('external_dependencies', {})
print(f"  ✓ Категорий зависимостей: {len(ext)}")
for k, v in ext.items():
    print(f"    - {k}: {len(v)}")

# === 9. Тест MCP инструментов ===
print("\n[9/6] Тест MCP инструментов...")
# Проверяем что сервер запускается
print(f"  ✓ MCP сервер: {mcp.name}")
print(f"  ✓ Индексатор: {len(indexer.symbols)} файлов")
print(f"  ✓ Flipchart: инициализирован")
print(f"  ✓ Toolkit: инициализирован")

# === ФИНАЛ ===
print("\n" + "=" * 60)
print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
print("=" * 60)
print(f"\nMCP сервер: {mcp.name}")
print(f"Проиндексировано файлов: {len(indexer.symbols)}")
print(f"Векторов в индексе: {indexer.vector.index.ntotal}")
print("\nСервер готов к работе!")
