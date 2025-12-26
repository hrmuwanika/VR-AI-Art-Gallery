#!/usr/bin/env python3
"""
RAG System for Art Gallery - Optimized for Ubuntu
"""

import json
import numpy as np
import os
import pickle
import hashlib
import faiss
from typing import List, Dict
import logging
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
import time

logger = logging.getLogger(__name__)

@dataclass
class ArtworkChunk:
    """Data class for artwork chunks"""
    artwork_id: int
    chunk_type: str
    text: str
    metadata: Dict

class UbuntuRAGSystem:
    """RAG System with FAISS vector search"""
    
    def __init__(self, data_file: str = "artworks.json"):
        self.data_file = data_file
        self.artworks = self._load_artworks()
        self.chunks = []
        self.index = None
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.dimension = 384
        
        self._init_vector_index()
        logger.info(f"RAG system initialized with {len(self.artworks)} artworks")
    
    def _load_artworks(self) -> List[Dict]:
        """Load artwork data"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Artwork file {self.data_file} not found")
            return []
    
    def _create_chunks(self) -> List[ArtworkChunk]:
        """Create searchable chunks"""
        chunks = []
        
        for artwork in self.artworks:
            chunks.extend([
                ArtworkChunk(
                    artwork_id=artwork['id'],
                    chunk_type='title_artist',
                    text=f"{artwork['title']} by {artwork['artist']}",
                    metadata={'year': artwork.get('year', 'Unknown')}
                ),
                ArtworkChunk(
                    artwork_id=artwork['id'],
                    chunk_type='description',
                    text=artwork['description'],
                    metadata={}
                ),
                ArtworkChunk(
                    artwork_id=artwork['id'],
                    chunk_type='details',
                    text=f"Style: {artwork.get('style', 'Unknown')}. Year: {artwork.get('year', 'Unknown')}.",
                    metadata={}
                )
            ])
        
        return chunks
    
    def _init_vector_index(self):
        """Initialize or load FAISS index"""
        cache_dir = "vector_cache"
        os.makedirs(cache_dir, exist_ok=True)
        
        index_file = os.path.join(cache_dir, "faiss_index.bin")
        chunks_file = os.path.join(cache_dir, "chunks.pkl")
        
        # Calculate data hash
        current_hash = hashlib.sha256(
            json.dumps(self.artworks, sort_keys=True).encode()
        ).hexdigest()[:16]
        
        # Check cache
        if os.path.exists(index_file) and os.path.exists(chunks_file):
            try:
                with open(os.path.join(cache_dir, "metadata.pkl"), 'rb') as f:
                    metadata = pickle.load(f)
                
                if metadata.get('data_hash') == current_hash:
                    logger.info("Loading vector index from cache...")
                    self.index = faiss.read_index(index_file)
                    with open(chunks_file, 'rb') as f:
                        self.chunks = pickle.load(f)
                    logger.info(f"Index loaded: {self.index.ntotal} vectors")
                    return
                    
            except Exception as e:
                logger.warning(f"Cache load failed: {e}")
        
        # Create new index
        logger.info("Creating new vector index...")
        self.chunks = self._create_chunks()
        
        # Generate embeddings
        texts = [chunk.text for chunk in self.chunks]
        embeddings = self.embedding_model.encode(
            texts, 
            show_progress_bar=True,
            convert_to_numpy=True
        )
        
        # Create FAISS index
        self.index = faiss.IndexFlatIP(self.dimension)
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings)
        
        # Save to cache
        faiss.write_index(self.index, index_file)
        with open(chunks_file, 'wb') as f:
            pickle.dump(self.chunks, f)
        
        metadata = {
            'data_hash': current_hash,
            'dimension': self.dimension,
            'chunk_count': len(self.chunks),
            'timestamp': time.time()
        }
        
        with open(os.path.join(cache_dir, "metadata.pkl"), 'wb') as f:
            pickle.dump(metadata, f)
        
        logger.info(f"Index created: {self.index.ntotal} vectors")
    
    def search(self, query: str, top_k: int = 5, threshold: float = 0.3) -> List[Dict]:
        """Search for similar artworks"""
        # Generate query embedding
        query_embedding = self.embedding_model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_embedding)
        
        # Search the index
        distances, indices = self.index.search(query_embedding, top_k * 3)
        
        # Process results
        results = []
        seen_artwork_ids = set()
        
        for distance, idx in zip(distances[0], indices[0]):
            if idx == -1:
                break
            
            chunk = self.chunks[idx]
            artwork_id = chunk.artwork_id
            
            if artwork_id in seen_artwork_ids:
                continue
            
            similarity = float(distance)
            if similarity < threshold:
                continue
            
            # Find artwork
            artwork = next((a for a in self.artworks if a['id'] == artwork_id), None)
            if not artwork:
                continue
            
            result = artwork.copy()
            result['similarity_score'] = similarity
            result['matched_chunk'] = chunk.text[:100]
            results.append(result)
            
            seen_artwork_ids.add(artwork_id)
            
            if len(results) >= top_k:
                break
        
        # Sort by similarity
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        return results
    
    def get_artwork_by_id(self, artwork_id: int) -> Dict:
        """Get artwork by ID"""
        for artwork in self.artworks:
            if artwork['id'] == artwork_id:
                return artwork
        return None
    
    def get_all_artworks(self) -> List[Dict]:
        """Get all artworks"""
        return self.artworks
    
    def get_artworks_by_artist(self, artist: str) -> List[Dict]:
        """Get artworks by artist"""
        artist_lower = artist.lower()
        return [art for art in self.artworks if artist_lower in art['artist'].lower()]
