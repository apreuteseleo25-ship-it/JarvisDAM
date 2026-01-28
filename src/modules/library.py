from telegram import Update
from telegram.ext import ContextTypes
from src.services.chroma_service import ChromaService
from src.services.ollama_service import OllamaService
from src.utils.logger import get_logger
from PyPDF2 import PdfReader
import io
import re
import requests
from typing import Optional, List, Dict, Any
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

logger = get_logger("library")


class LibraryModule:
    def __init__(self, chroma_service: ChromaService, ollama_service: OllamaService):
        self.chroma_service = chroma_service
        self.ollama_service = ollama_service
    
    async def ingest_pdf(self, user_id: int, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        try:
            pdf_reader = PdfReader(io.BytesIO(file_bytes))
            
            total_pages = len(pdf_reader.pages)
            full_text = ""
            
            for page_num, page in enumerate(pdf_reader.pages):
                text = page.extract_text()
                full_text += f"\n--- Page {page_num + 1} ---\n{text}"
            
            chunks = self._chunk_text(full_text, chunk_size=1000, overlap=200)
            
            doc_ids = []
            for i, chunk in enumerate(chunks):
                # Extraer el número de página del chunk si está presente
                page_match = chunk.split('\n')[0] if '\n' in chunk else ""
                page_num = None
                if "Page" in page_match:
                    try:
                        page_num = int(page_match.split("Page")[1].split("---")[0].strip())
                    except:
                        pass
                
                metadata = {
                    "filename": filename,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "source": "pdf",
                    "page": page_num if page_num is not None else 0
                }
                
                doc_id = self.chroma_service.add_document(
                    user_id=user_id,
                    content=chunk,
                    metadata=metadata,
                    doc_type="document"
                )
                doc_ids.append(doc_id)
            
            return {
                "success": True,
                "filename": filename,
                "pages": total_pages,
                "chunks": len(chunks),
                "doc_ids": doc_ids
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = start + chunk_size
            chunk = text[start:end]
            
            if chunk.strip():
                chunks.append(chunk)
            
            start = end - overlap
        
        return chunks
    
    async def search(self, user_id: int, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Busca documentos relevantes en ChromaDB"""
        # No filtrar por doc_type para buscar en todos los documentos del usuario
        results = self.chroma_service.query_documents(
            user_id=user_id,
            query_text=query,
            n_results=top_k,
            doc_type=None  # Buscar en todos los tipos de documentos
        )
        
        if not results or not results.get("documents") or not results["documents"][0]:
            return []
        
        # Convertir resultados a formato de lista de diccionarios
        search_results = []
        for i, doc in enumerate(results["documents"][0]):
            result = {
                "text": doc,
                "metadata": results["metadatas"][0][i] if results.get("metadatas") and results["metadatas"][0] else {}
            }
            search_results.append(result)
        
        return search_results
    
    async def ask(self, user_id: int, question: str, n_results: int = 5) -> str:
        results = self.chroma_service.query_documents(
            user_id=user_id,
            query_text=question,
            n_results=n_results,
            doc_type="document"
        )
        
        if not results or not results.get("documents") or not results["documents"][0]:
            return "No encontré información relevante en tus documentos."
        
        context = "\n\n".join(results["documents"][0])
        
        answer = await self.ollama_service.answer_question(question, context)
        
        # Extraer fuentes con información de página
        sources_dict = {}
        if results.get("metadatas") and results["metadatas"][0]:
            for metadata in results["metadatas"][0]:
                if "filename" in metadata:
                    filename = metadata["filename"]
                    page = metadata.get("page")
                    
                    if filename not in sources_dict:
                        sources_dict[filename] = set()
                    
                    if page is not None:
                        sources_dict[filename].add(page)
        
        # Formatear fuentes con estilo JARVIS
        if sources_dict:
            sources_formatted = []
            for filename, pages in sources_dict.items():
                if pages:
                    # Ordenar páginas y formatear
                    sorted_pages = sorted(pages)
                    if len(sorted_pages) == 1:
                        sources_formatted.append(f"• {filename} (Pág. {sorted_pages[0]})")
                    else:
                        pages_str = ", ".join(map(str, sorted_pages))
                        sources_formatted.append(f"• {filename} (Págs. {pages_str})")
                else:
                    sources_formatted.append(f"• {filename}")
            
            response = f"{answer}\n\n📚 **Fuentes:**\n" + "\n".join(sources_formatted)
        else:
            response = answer
        
        return response
    
    async def generate_quiz(self, user_id: int, num_questions: int = 5) -> str:
        docs = self.chroma_service.get_user_documents(
            user_id=user_id,
            doc_type="document",
            limit=10
        )
        
        if not docs or not docs.get("documents"):
            return "No tienes documentos indexados para generar un quiz."
        
        context = "\n\n".join(docs["documents"][:5])
        
        quiz = await self.ollama_service.generate_quiz(context, num_questions)
        
        return quiz
    
    def get_library_stats(self, user_id: int) -> Dict[str, int]:
        total_docs = self.chroma_service.count_user_documents(user_id, doc_type="document")
        
        return {
            "documents": total_docs,
            "total": total_docs
        }
    
    def _extract_youtube_id(self, url: str) -> Optional[str]:
        """Extrae el ID del video de una URL de YouTube"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)',
            r'youtube\.com\/embed\/([^&\n?#]+)',
            r'youtube\.com\/v\/([^&\n?#]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def _get_youtube_title(self, video_id: str) -> str:
        """Obtiene el título del video de YouTube usando oEmbed API"""
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            response = requests.get(oembed_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get('title', f'YouTube_{video_id}')
        except:
            pass
        
        return f'YouTube_{video_id}'
    
    async def ingest_youtube_video(self, user_id: int, url: str) -> Dict[str, Any]:
        """
        Ingesta un video de YouTube extrayendo su transcripción y guardándola en ChromaDB.
        
        Args:
            user_id: ID del usuario
            url: URL del video de YouTube
        
        Returns:
            Dict con success, message, y detalles del video
        """
        try:
            # Extraer ID del video
            video_id = self._extract_youtube_id(url)
            if not video_id:
                return {
                    "success": False,
                    "error": "invalid_url",
                    "message": "No pude extraer el ID del video de la URL proporcionada."
                }
            
            # Intentar obtener transcripción (incluye auto-generadas)
            # Usar la API correcta de youtube-transcript-api v1.2.3
            transcript = None
            try:
                # Crear instancia de la API
                ytt_api = YouTubeTranscriptApi()
                
                # Obtener lista de transcripciones disponibles
                transcript_list = ytt_api.list(video_id)
                
                # Intentar encontrar transcripción en orden de preferencia: español, inglés, cualquier otro
                transcript_obj = None
                
                try:
                    # Buscar español primero (manual o auto-generado)
                    transcript_obj = transcript_list.find_transcript(['es'])
                    logger.info(f"Transcripción en español encontrada para video {video_id}")
                except:
                    try:
                        # Si no hay español, buscar inglés
                        transcript_obj = transcript_list.find_transcript(['en'])
                        logger.info(f"Transcripción en inglés encontrada para video {video_id}")
                    except:
                        # Si no hay ni español ni inglés, usar la primera disponible
                        try:
                            transcript_obj = next(iter(transcript_list))
                            logger.info(f"Transcripción en {transcript_obj.language_code} encontrada para video {video_id}")
                        except:
                            pass
                
                # Obtener el contenido de la transcripción
                if transcript_obj:
                    transcript = transcript_obj.fetch()
                    logger.info(f"Transcripción obtenida exitosamente: {len(transcript)} fragmentos")
                
            except Exception as e:
                logger.error(f"Error al obtener transcripción de YouTube: {e}", exc_info=True)
            
            # Si no se pudo obtener ninguna transcripción
            if not transcript:
                return {
                    "success": False,
                    "error": "no_transcript",
                    "message": "No pude obtener la transcripción del video.\n\n"
                               "Posibles causas:\n"
                               "• Video sin subtítulos (ni manuales ni auto-generados)\n"
                               "• Restricciones geográficas o de edad\n"
                               "• Video privado o eliminado\n"
                               "• Subtítulos deshabilitados por el creador"
                }
            
            # Concatenar todo el texto de la transcripción
            # La API devuelve objetos FetchedTranscriptSnippet con atributo .text
            full_text = " ".join([entry.text for entry in transcript])
            
            # Limpiar el texto (eliminar saltos de línea innecesarios, etc.)
            full_text = full_text.replace('\n', ' ').strip()
            
            # Obtener título del video
            title = self._get_youtube_title(video_id)
            
            # Reutilizar la función de chunking existente (1000 chars, 200 overlap)
            chunks = self._chunk_text(full_text, chunk_size=1000, overlap=200)
            
            # Guardar chunks en ChromaDB con metadata completa
            doc_ids = []
            for i, chunk in enumerate(chunks):
                metadata = {
                    "filename": title,
                    "title": title,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "source": url,
                    "type": "youtube_transcript",
                    "video_id": video_id
                }
                
                doc_id = self.chroma_service.add_document(
                    user_id=user_id,
                    content=chunk,
                    metadata=metadata,
                    doc_type="document"
                )
                doc_ids.append(doc_id)
            
            return {
                "success": True,
                "video_id": video_id,
                "title": title,
                "chunks": len(chunks),
                "is_long": len(chunks) > 10,  # Considerar "largo" si tiene más de 10 chunks
                "message": f"Video transcrito y añadido a la base de conocimiento ({len(chunks)} fragmentos)."
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Error al procesar el video: {str(e)}"
            }
