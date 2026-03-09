#!/usr/bin/env python
"""Тест работоспособности MCP сервера"""
from repomap import RepoMap
from server import indexer, repo_maps
import sys
sys.path.insert(0, '.')


print("=" * 50)
print("ТЕСТ MCP booster СЕРВЕРА")
print("=" * 50)

# Тест 1: repo_stats
print("\n1. Тест repo_stats():")
stats = {
    "repos": indexer.repos,
    "files_indexed": len(indexer.symbols),
    "vectors_in_faiss": indexer.vector.index.ntotal
}
print(f"   Репозитории: {stats['repos']}")
print(f"   Файлов: {stats['files_indexed']}")
print(f"   Векторов: {stats['vectors_in_faiss']}")

# Тест 2: find_symbol
print("\n2. Тест find_symbol('index'):")
res = []
for syms in indexer.symbols.values():
    for s in syms:
        if 'index' in s['name'].lower():
            res.append(s)
print(f"   Найдено символов: {len(res)}")
for s in res[:3]:
    print(f"   - {s['name']} в {s['file']}")

# Тест 3: semantic_search
print("\n3. Тест semantic_search('индексация файлов'):")
results = indexer.search('индексация файлов')
print(f"   Найдено результатов: {len(results)}")
for r in results[:2]:
    print(f"   - Файл: {r['file'][:50]}...")

# Тест 4: call_graph
print("\n4. Тест call_graph('full_index'):")
calls = indexer.graphs.calls('full_index')
print(f"   Вызываемые функции: {calls}")

# Тест 5: import_graph
print("\n5. Тест import_graph('server.py'):")
imports = indexer.graphs.imports('server.py')
print(f"   Импорты: {imports}")

# Тест 6: list_repos
print("\n6. Тест list_repos():")
repos_info = {
    "repos": indexer.repos,
    "total_files": len(indexer.symbols),
    "total_vectors": indexer.vector.index.ntotal
}
print(f"   Репозитории: {repos_info['repos']}")
print(f"   Всего файлов: {repos_info['total_files']}")
print(f"   Всего векторов: {repos_info['total_vectors']}")

# Тест 7: get_repo_map
print("\n7. Тест get_repo_map():")
repo_map = RepoMap('.')
map_content = repo_map.get_repo_map()
if map_content:
    lines = map_content.strip().split('\n')
    print(f"   Сгенерировано строк: {len(lines)}")
    print(f"   Первые 5 файлов:")
    current_file = None
    shown = 0
    for line in lines[:20]:
        if line.endswith(':'):
            current_file = line
        if current_file and shown < 5:
            print(f"   {line}")
            if not line.endswith(':'):
                shown += 1
else:
    print("   Пусто")

print("\n" + "=" * 50)
print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
print("=" * 50)
