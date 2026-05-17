import re
from config import CHROMA_PATH, ENABLE_SEMANTIC_DEDUPE

model = None
chroma = None
collection = None
fingerprints = set()

def _fingerprint(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(w for w in words if len(w) > 3)

def _lexical_duplicate(text, threshold):
    current = _fingerprint(text)
    if not current:
        return False

    for existing in fingerprints:
        overlap = len(current & existing)
        union = len(current | existing)
        if union and overlap / union >= threshold:
            return True
    return False

def _get_model():
    global model
    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return model

def _get_collection():
    global chroma, collection
    import chromadb

    if chroma is None:
        chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    if collection is None:
        collection = chroma.get_or_create_collection("news")
    return collection

def is_duplicate(text, threshold=0.82):
    if not ENABLE_SEMANTIC_DEDUPE:
        return _lexical_duplicate(text, threshold)

    emb = _get_model().encode(text).tolist()
    res = _get_collection().query(query_embeddings=[emb], n_results=1)
    if res["distances"] and res["distances"][0]:
        return res["distances"][0][0] < (1 - threshold)
    return False

def add_vector(news_id, text):
    fingerprints.add(_fingerprint(text))
    if not ENABLE_SEMANTIC_DEDUPE:
        return

    _get_collection().upsert(
        ids=[news_id],
        documents=[text],
        embeddings=[_get_model().encode(text).tolist()]
    )

def reset_vectors():
    global collection, chroma, fingerprints
    fingerprints = set()
    if not ENABLE_SEMANTIC_DEDUPE:
        return

    import chromadb

    if chroma is None:
        chroma = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        chroma.delete_collection("news")
    except Exception:
        pass
    collection = chroma.get_or_create_collection("news")
