from typing import Optional, Tuple

from langchain_core.embeddings.embeddings import Embeddings
from langchain_community.embeddings import InfinityEmbeddings
import requests


INFINITY_API_URL = "http://127.0.0.1:7997"

def load_embedding_model(model_name: Optional[str] = None, dimension: Optional[int] = None) -> Tuple[Embeddings, int]:
    embeddings = InfinityEmbeddings(
        model="mixedbread-ai/mxbai-embed-large-v1",
        infinity_api_url=INFINITY_API_URL,
    )
    if dimension is None:
        results = requests.post(
            f"{INFINITY_API_URL}/embeddings",
            json={
                "model": "mixedbread-ai/mxbai-embed-large-v1",
                "input": ["A sentence to encode."],
            },
        )
        dimension = len(results.json()["data"][0]["embedding"])  # Expecting 512
    return embeddings, dimension
