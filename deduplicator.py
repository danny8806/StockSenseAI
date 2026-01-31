import chromadb
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
chroma = chromadb.Client()
collection = chroma.get_or_create_collection("news")

def is_duplicate(text, threshold=0.92):
    emb = model.encode(text).tolist()
    res = collection.query(query_embeddings=[emb], n_results=1)
    if res["distances"] and res["distances"][0]:
        return res["distances"][0][0] < (1 - threshold)
    return False

def add_vector(news_id, text):
    collection.add(
        ids=[news_id],
        documents=[text],
        embeddings=[model.encode(text).tolist()]
    )
