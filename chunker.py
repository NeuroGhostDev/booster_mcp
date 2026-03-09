def semantic_chunks(symbols, code_str):
    lines = code_str.splitlines()
    chunks =[]
    
    for s in symbols:
        # +1 чтобы не отрезать последнюю строку (например, '}')
        chunk = "\n".join(lines[s["start"]:s["end"] + 1])
        if chunk.strip():
            chunks.append(chunk)
            
    return chunks
