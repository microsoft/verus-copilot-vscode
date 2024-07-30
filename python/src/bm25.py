from rank_bm25 import BM25Okapi
import numpy as np
import json

class BM25:
    def __init__(self, corpus_path):
        corpus = [json.loads(x) for x in open(corpus_path).readlines()]
        self.corpus = corpus
        self.tokenized_corpus = [self.process_doc(doc).split(" ") for doc in corpus]
        self.bm25 = BM25Okapi(self.tokenized_corpus)
    
    def process_doc(self, doc):
        msg = doc["error"]
        msg = "\n".join(msg.splitlines()[:-1])
        return msg

    def split_query(self, query):
        if query.splitlines()[-1].startswith("verification results"):
            query = "\n".join(query.splitlines()[:-1])
        split_query = ["error:" + q for q in query.split("error:") if q.strip() != ""]
        group_query = []
        error_types = []
        for q in split_query:
            et = q.splitlines()[0].split("error:")[1].strip()
            if et not in error_types:
                error_types.append(et)
                group_query.append([q])
            else:
                group_query[error_types.index(et)].append(q)
        return sorted(group_query, key=lambda x: len(x), reverse=True)

    def score(self, query):
        tokenized_query = query.split(" ")
        doc_scores = self.bm25.get_scores(tokenized_query)
        return doc_scores

    def _search_topk_single(self, query, k=5):
        tokenized_query = query.split(" ")
        doc_scores = self.bm25.get_scores(tokenized_query)
        topk_idx = np.argsort(doc_scores)[::-1][:k]
        return [self.corpus[idx] for idx in topk_idx]
    
    def search_topk(self, query, k=5, split=False):
        if not split:
            return self._search_topk_single(query, k)
        else:
            group_query = self.split_query(query)
            results = []
            for qs in group_query:
                q = "".join(qs)
                results.append(self._search_topk_single(q, k))
            ret = []
            idx = [0] * len(results)
            while len(ret) < k:
                for i in range(len(results)):
                    if idx[i] >= len(results[i]):
                        continue
                    while idx[i] < len(results[i]):
                        if results[i][idx[i]] not in ret:
                            ret.append(results[i][idx[i]])
                            idx[i] += 1
                            break
                        idx[i] += 1
                    if len(ret) == k:
                        break
            return ret
            
