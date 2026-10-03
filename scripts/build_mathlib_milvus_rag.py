import os
import re
import logging
from typing import List, Dict

try:
    from pymilvus import MilvusClient, DataType
    from sentence_transformers import SentenceTransformer
except ImportError:
    logging.warning("Please install dependencies: uv pip install pymilvus sentence-transformers")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Mathlib-Milvus-RAG")

# Setup local Milvus Lite for rapid prototyping
MILVUS_DB_PATH = "./mathlib4_rag.db"
COLLECTION_NAME = "mathlib4_lemmas"
EMBEDDING_DIM = 384 # Default for all-MiniLM-L6-v2

def setup_milvus_collection(client: 'MilvusClient'):
    if client.has_collection(collection_name=COLLECTION_NAME):
        client.drop_collection(collection_name=COLLECTION_NAME)
        
    schema = MilvusClient.create_schema(
        auto_id=True,
        enable_dynamic_field=True,
    )
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
    schema.add_field(field_name="lemma_name", datatype=DataType.VARCHAR, max_length=255)
    schema.add_field(field_name="signature", datatype=DataType.VARCHAR, max_length=2048)
    schema.add_field(field_name="filepath", datatype=DataType.VARCHAR, max_length=512)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        metric_type="COSINE",
        index_type="FLAT",
        index_name="vector_index"
    )

    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=schema,
        index_params=index_params
    )
    logger.info(f"Milvus collection '{COLLECTION_NAME}' created.")

def extract_lemmas_from_lean_file(filepath: str) -> List[Dict]:
    """
    Crude regex-based extraction of Mathlib4 theorems and lemmas.
    In production, this should use Lean's actual AST/DocGen4.
    """
    lemmas = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Match 'theorem foo (args) : signature :=' or 'lemma foo...'
        pattern = r'(?:theorem|lemma)\s+([a-zA-Z0-9_]+)\s*(.*?):='
        matches = re.finditer(pattern, content, re.DOTALL)
        
        for match in matches:
            name = match.group(1).strip()
            signature = match.group(2).strip()
            # Clean up newlines in signature
            signature = re.sub(r'\s+', ' ', signature)
            lemmas.append({
                "lemma_name": name,
                "signature": signature,
                "filepath": filepath
            })
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
    return lemmas

def ingest_mathlib():
    logger.info("Initializing Mathlib4 RAG Ingestion Pipeline (Milvus)")
    
    # Initialize Embedding Model
    logger.info("Loading Embedding Model: all-MiniLM-L6-v2")
    try:
        model = SentenceTransformer('all-MiniLM-L6-v2')
        client = MilvusClient(MILVUS_DB_PATH)
    except NameError:
        logger.error("pymilvus or sentence_transformers not installed.")
        return

    setup_milvus_collection(client)

    mathlib_dir = "./vendor/mathlib4"
    if not os.path.exists(mathlib_dir):
        logger.warning(f"Mathlib4 not found at {mathlib_dir}. Run: git clone https://github.com/leanprover-community/mathlib4 vendor/mathlib4")
        return

    logger.info(f"Scanning Mathlib4 directory: {mathlib_dir}...")
    lean_files = glob.glob(os.path.join(mathlib_dir, "**/*.lean"), recursive=True)
    
    total_lemmas = []
    # Scaffold: Process only the first 100 files to avoid massive runtime during testing
    for file in lean_files[:100]:
        total_lemmas.extend(extract_lemmas_from_lean_file(file))
        
    logger.info(f"Extracted {len(total_lemmas)} lemmas. Embedding...")
    
    if not total_lemmas:
        return

    # Create semantic representations (Name + Signature)
    texts = [f"{l['lemma_name']}: {l['signature']}" for l in total_lemmas]
    vectors = model.encode(texts, convert_to_numpy=True)
    
    data = []
    for i, lemma in enumerate(total_lemmas):
        data.append({
            "vector": vectors[i].tolist(),
            "lemma_name": lemma["lemma_name"],
            "signature": lemma["signature"],
            "filepath": lemma["filepath"]
        })
        
    res = client.insert(collection_name=COLLECTION_NAME, data=data)
    logger.info(f"Inserted {res['insert_count']} vectors into Milvus.")

if __name__ == "__main__":
    ingest_mathlib()
