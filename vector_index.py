import faiss
import numpy as np

class VectorIndex:
    def __init__(self, dim=384):
        self.base_index = faiss.IndexFlatL2(dim)
        self.index = faiss.IndexIDMap(self.base_index)
        self.meta = {}
        self.file_ids = {}
        self.next_id = 0

    def remove_file(self, file):
        if file in self.file_ids:
            ids_to_remove = self.file_ids[file]
            if ids_to_remove:
                self.index.remove_ids(np.array(ids_to_remove, dtype=np.int64))
                for i in ids_to_remove:
                    self.meta.pop(i, None)
            del self.file_ids[file]

    def add(self, vector, meta):
        file = meta["file"]
        vec_id = self.next_id
        self.next_id += 1

        self.index.add_with_ids(
            np.array([vector], dtype=np.float32),
            np.array([vec_id], dtype=np.int64)
        )

        self.meta[vec_id] = meta
        self.file_ids.setdefault(file,[]).append(vec_id)

    def search(self, vector, k=5):
        if self.index.ntotal == 0:
            return[]
            
        D, I = self.index.search(np.array([vector], dtype=np.float32), k)
        res = []
        
        for idx in I[0]:
            if idx != -1 and idx in self.meta:
                res.append(self.meta[idx])
                
        return res
