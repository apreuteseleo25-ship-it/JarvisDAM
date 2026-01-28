import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
import hashlib
from datetime import datetime


class ChromaService:
    def __init__(self, persist_directory: str = "./chroma_db", collection_name: str = "second_brain"):
        # Usar PersistentClient para guardar datos en disco
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        try:
            self.collection = self.client.get_collection(name=collection_name)
        except:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
    
    def _generate_doc_id(self, content: str, user_id: int) -> str:
        unique_string = f"{user_id}_{content}_{datetime.utcnow().isoformat()}"
        return hashlib.sha256(unique_string.encode()).hexdigest()
    
    def add_document(
        self, 
        user_id: int, 
        content: str, 
        metadata: Optional[Dict[str, Any]] = None,
        doc_type: str = "document"
    ) -> str:
        if metadata is None:
            metadata = {}
        
        metadata["user_id"] = str(user_id)
        metadata["doc_type"] = doc_type
        metadata["timestamp"] = datetime.utcnow().isoformat()
        
        doc_id = self._generate_doc_id(content, user_id)
        
        self.collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[doc_id]
        )
        
        return doc_id
    
    def add_snippet(
        self,
        user_id: int,
        code: str,
        language: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        metadata = {
            "language": language,
            "description": description or "",
            "tags": ",".join(tags) if tags else ""
        }
        
        return self.add_document(
            user_id=user_id,
            content=code,
            metadata=metadata,
            doc_type="snippet"
        )
    
    def query_documents(
        self,
        user_id: int,
        query_text: str,
        n_results: int = 5,
        doc_type: Optional[str] = None
    ) -> Dict[str, Any]:
        # ChromaDB requiere operador $and cuando hay múltiples condiciones
        if doc_type:
            where_filter = {
                "$and": [
                    {"user_id": {"$eq": str(user_id)}},
                    {"doc_type": {"$eq": doc_type}}
                ]
            }
        else:
            where_filter = {"user_id": {"$eq": str(user_id)}}
        
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where_filter
        )
        
        return results
    
    def query_snippets(
        self,
        user_id: int,
        query_text: str,
        language: Optional[str] = None,
        n_results: int = 5
    ) -> Dict[str, Any]:
        # ChromaDB requiere operador $and para múltiples condiciones
        conditions = [
            {"user_id": {"$eq": str(user_id)}},
            {"doc_type": {"$eq": "snippet"}}
        ]
        
        if language:
            conditions.append({"language": {"$eq": language}})
        
        where_filter = {"$and": conditions}
        
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where_filter
        )
        
        return results
    
    def get_user_documents(
        self,
        user_id: int,
        doc_type: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        where_filter = {"user_id": str(user_id)}
        
        if doc_type:
            where_filter["doc_type"] = doc_type
        
        results = self.collection.get(
            where=where_filter,
            limit=limit
        )
        
        return results
    
    def delete_document(self, user_id: int, doc_id: str) -> bool:
        try:
            doc = self.collection.get(ids=[doc_id])
            
            if doc and doc["metadatas"] and len(doc["metadatas"]) > 0:
                if doc["metadatas"][0].get("user_id") == str(user_id):
                    self.collection.delete(ids=[doc_id])
                    return True
            
            return False
        except Exception as e:
            print(f"Error deleting document: {e}")
            return False
    
    def count_user_documents(self, user_id: int, doc_type: Optional[str] = None) -> int:
        where_filter = {"user_id": str(user_id)}
        
        if doc_type:
            where_filter["doc_type"] = doc_type
        
        results = self.collection.get(where=where_filter)
        
        return len(results["ids"]) if results and "ids" in results else 0
