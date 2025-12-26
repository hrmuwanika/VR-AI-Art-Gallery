#!/usr/bin/env python3
"""
AI Art Gallery Server with Complete Analytics System
"""

import os
import sys
import json
import time
import uuid
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_file, render_template_string
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import whisper
from gtts import gTTS
import requests

# Import local modules
from rag_system import UbuntuRAGSystem
from analytics_db import AnalyticsDB, QueryLog, ArtworkInteraction, VisitorSession

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Configuration
class Config:
    UPLOAD_FOLDER = 'uploads'
    AUDIO_FOLDER = 'audio_responses'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    HOST = '0.0.0.0'
    PORT = 5000
    DEBUG = False

# Create directories
for folder in [Config.UPLOAD_FOLDER, Config.AUDIO_FOLDER, 'logs', 'analytics_cache']:
    os.makedirs(folder, exist_ok=True)

app.config.from_object(Config)

# Global instances
rag_system = None
analytics_db = None
whisper_model = None

class AIGuideSystem:
    """Main AI Guide System with Analytics"""
    
    def __init__(self):
        logger.info("🚀 Initializing AI Guide System with Analytics...")
        
        # Initialize systems
        self.rag = UbuntuRAGSystem()
        self.analytics = AnalyticsDB()
        
        # Initialize AI models
        self.whisper_model = whisper.load_model("base")
        self.ollama_available = self._check_ollama()
        
        logger.info(f"✅ System initialized: {len(self.rag.artworks)} artworks loaded")
        logger.info(f"📊 Analytics DB ready | Ollama: {self.ollama_available}")
    
    def _check_ollama(self):
        """Check if Ollama is available"""
        try:
            response = requests.get('http://localhost:11434/api/tags', timeout=3)
            return response.status_code == 200
        except:
            return False
    
    def process_query(self, query_text: str, metadata: Dict = None) -> Dict:
        """Process query with full analytics tracking"""
        query_id = str(uuid.uuid4())
        start_time = time.time()
        
        # Get or create session
        metadata = metadata or {}
        session_id = metadata.get('session_id') or str(uuid.uuid4())
        visitor_id = self._get_visitor_id(metadata)
        
        # Start session if new
        if not self.analytics.session_exists(session_id):
            session = VisitorSession(
                session_id=session_id,
                visitor_id=visitor_id,
                start_time=start_time,
                device_type=metadata.get('device_type'),
                location=metadata.get('location')
            )
            self.analytics.start_session(session)
        
        # Perform RAG search
        relevant_artworks = self.rag.search(query_text, top_k=3)
        
        # Generate response
        if self.ollama_available and relevant_artworks:
            response_text = self._generate_ai_response(query_text, relevant_artworks)
            ai_generated = True
        else:
            response_text = self._generate_simple_response(query_text, relevant_artworks)
            ai_generated = False
        
        response_time = time.time() - start_time
        
        # Generate audio
        audio_filename = self._text_to_speech(response_text)
        
        # Log analytics
        self._log_query_analytics(
            query_id=query_id,
            query_text=query_text,
            session_id=session_id,
            visitor_id=visitor_id,
            response_time=response_time,
            artworks=relevant_artworks,
            ai_generated=ai_generated,
            metadata=metadata
        )
        
        # Send real-time update
        socketio.emit('analytics_update', {
            'type': 'new_query',
            'query': query_text,
            'artwork_count': len(relevant_artworks),
            'timestamp': time.time()
        }, room='analytics')
        
        # Prepare response
        result = {
            'success': True,
            'query_id': query_id,
            'session_id': session_id,
            'query': query_text,
            'response': response_text,
            'audio_url': f'/api/audio/{audio_filename}' if audio_filename else None,
            'artworks': [
                {
                    'id': art['id'],
                    'title': art['title'],
                    'artist': art['artist'],
                    'similarity': art.get('similarity_score', 0),
                    'location': art.get('gallery_location', 'Gallery')
                }
                for art in relevant_artworks[:3]
            ],
            'metadata': {
                'response_time': round(response_time, 2),
                'ai_generated': ai_generated,
                'artworks_found': len(relevant_artworks)
            }
        }
        
        return result
    
    def _generate_ai_response(self, query: str, artworks: List[Dict]) -> str:
        """Generate AI response using Ollama"""
        try:
            context = "\n\n".join([
                f"Artwork: {art['title']} by {art['artist']}\n"
                f"Description: {art['description'][:200]}"
                for art in artworks[:2]
            ])
            
            prompt = f"""As an art gallery guide, answer this question: {query}

Available context:
{context}

Please provide a helpful, concise answer (2-3 sentences)."""
            
            response = requests.post(
                'http://localhost:11434/api/chat',
                json={
                    "model": "gemma:2b",
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()['message']['content']
            else:
                raise Exception("Ollama API error")
                
        except Exception as e:
            logger.error(f"AI generation failed: {e}")
            return self._generate_simple_response(query, artworks)
    
    def _generate_simple_response(self, query: str, artworks: List[Dict]) -> str:
        """Generate simple response without AI"""
        if not artworks:
            return "I'm not sure about that. Would you like to explore our gallery?"
        
        artwork = artworks[0]
        return f"{artwork['title']} by {artwork['artist']} is a fascinating piece. {artwork['description'][:150]}..."
    
    def _text_to_speech(self, text: str) -> Optional[str]:
        """Convert text to speech"""
        try:
            filename = f"response_{int(time.time())}.mp3"
            filepath = os.path.join(Config.AUDIO_FOLDER, filename)
            
            tts = gTTS(text=text, lang='en', slow=False)
            tts.save(filepath)
            
            return filename
        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return None
    
    def _get_visitor_id(self, metadata: Dict) -> str:
        """Generate consistent visitor ID"""
        if metadata and 'visitor_id' in metadata:
            return metadata['visitor_id']
        
        ip = metadata.get('ip_address', 'anonymous') if metadata else 'anonymous'
        return hashlib.md5(ip.encode()).hexdigest()[:8]
    
    def _log_query_analytics(self, query_id: str, query_text: str, session_id: str,
                           visitor_id: str, response_time: float, artworks: List[Dict],
                           ai_generated: bool, metadata: Dict):
        """Log complete query analytics"""
        try:
            # Log query
            query_log = QueryLog(
                query_id=query_id,
                query_text=query_text,
                timestamp=time.time(),
                session_id=session_id,
                visitor_id=visitor_id,
                response_time=response_time,
                artworks_found=len(artworks),
                ai_generated=ai_generated,
                language=metadata.get('language', 'en'),
                device_type=metadata.get('device_type'),
                location=metadata.get('location')
            )
            
            self.analytics.log_query(query_log)
            
            # Log artwork interactions
            for i, artwork in enumerate(artworks):
                interaction = ArtworkInteraction(
                    interaction_id=f"{query_id}_{i}",
                    query_id=query_id,
                    artwork_id=artwork['id'],
                    artwork_title=artwork['title'],
                    artwork_artist=artwork['artist'],
                    similarity_score=artwork.get('similarity_score', 0.5)
                )
                
                self.analytics.log_artwork_interaction(interaction)
            
            # Update session
            self.analytics.update_session(session_id, {
                'total_queries': 1,
                'total_time': response_time
            })
            
        except Exception as e:
            logger.error(f"Analytics logging failed: {e}")
    
    def record_artwork_click(self, query_id: str, artwork_id: int, duration: float = 0):
        """Record artwork click"""
        try:
            self.analytics.record_click(query_id, artwork_id, duration)
            
            # Send real-time update
            socketio.emit('analytics_update', {
                'type': 'artwork_click',
                'artwork_id': artwork_id,
                'duration': duration,
                'timestamp': time.time()
            }, room='analytics')
            
        except Exception as e:
            logger.error(f"Click recording failed: {e}")
    
    def record_feedback(self, query_id: str, score: int, comment: str = ""):
        """Record visitor feedback"""
        try:
            self.analytics.record_feedback(query_id, score, comment)
            
            # Send real-time update
            socketio.emit('analytics_update', {
                'type': 'feedback',
                'score': score,
                'timestamp': time.time()
            }, room='analytics')
            
        except Exception as e:
            logger.error(f"Feedback recording failed: {e}")

# Initialize system
system = AIGuideSystem()

# ==================== WEB SOCKET HANDLERS ====================

@socketio.on('connect')
def handle_connect():
    logger.info('Client connected to WebSocket')
    emit('connected', {'status': 'connected'})

@socketio.on('subscribe_analytics')
def handle_subscribe(data):
    """Subscribe to analytics updates"""
    join_room('analytics')
    emit('subscribed', {'room': 'analytics'})

# ==================== API ENDPOINTS ====================

@app.route('/')
def index():
    """Main dashboard"""
    stats = system.analytics.get_system_stats('24h')
    
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>🎨 AI Art Gallery</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { background: linear-gradient(135deg, #667eea, #764ba2); 
                     color: white; padding: 30px; border-radius: 15px; margin-bottom: 30px; }
            .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }
            .stat-card { background: white; padding: 20px; border-radius: 10px; 
                        box-shadow: 0 5px 15px rgba(0,0,0,0.1); border-left: 4px solid #667eea; }
            .stat-value { font-size: 28px; font-weight: bold; color: #667eea; }
            .stat-label { color: #666; margin-top: 5px; }
            .query-box { margin: 30px 0; }
            textarea { width: 100%; padding: 15px; border: 2px solid #ddd; 
                      border-radius: 10px; font-size: 16px; min-height: 100px; }
            button { background: #667eea; color: white; border: none; padding: 15px 30px; 
                    border-radius: 10px; font-size: 16px; cursor: pointer; margin-top: 10px; }
            .response { background: #f8f9fa; padding: 20px; border-radius: 10px; 
                       margin-top: 20px; border-left: 4px solid #28a745; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎨 AI Art Gallery Guide</h1>
                <p>Ask questions about artworks and explore with AI</p>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value">''' + str(stats.get('total_queries', 0)) + '''</div>
                    <div class="stat-label">Total Queries</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">''' + str(stats.get('unique_visitors', 0)) + '''</div>
                    <div class="stat-label">Unique Visitors</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">''' + str(stats.get('artwork_count', 0)) + '''</div>
                    <div class="stat-label">Artworks</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">''' + str(round(stats.get('avg_response_time', 0), 2)) + '''s</div>
                    <div class="stat-label">Avg Response Time</div>
                </div>
            </div>
            
            <div class="query-box">
                <h2>Ask a Question</h2>
                <textarea id="queryInput" placeholder="Ask about artworks, artists, or styles..."></textarea>
                <button onclick="askQuestion()">Ask Question</button>
            </div>
            
            <div id="responseArea"></div>
            
            <div style="margin-top: 40px;">
                <h3>📊 Analytics Dashboard</h3>
                <p><a href="/analytics" style="color: #667eea; text-decoration: none;">
                    → View detailed analytics and reports
                </a></p>
            </div>
        </div>
        
        <script>
            async function askQuestion() {
                const query = document.getElementById('queryInput').value.trim();
                if (!query) return;
                
                const responseArea = document.getElementById('responseArea');
                responseArea.innerHTML = '<div class="response">Thinking...</div>';
                
                try {
                    const response = await fetch('/api/query', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({question: query})
                    });
                    
                    const result = await response.json();
                    
                    let html = '<div class="response">';
                    html += '<h4>Response:</h4>';
                    html += '<p>' + result.response + '</p>';
                    
                    if (result.audio_url) {
                        html += '<audio controls style="margin-top: 15px;">';
                        html += '<source src="' + result.audio_url + '" type="audio/mpeg">';
                        html += '</audio>';
                    }
                    
                    if (result.artworks && result.artworks.length > 0) {
                        html += '<h5 style="margin-top: 20px;">Relevant Artworks:</h5>';
                        html += '<ul>';
                        result.artworks.forEach(art => {
                            html += '<li><strong>' + art.title + '</strong> by ' + art.artist;
                            html += ' (Similarity: ' + Math.round(art.similarity * 100) + '%)</li>';
                        });
                        html += '</ul>';
                    }
                    
                    html += '</div>';
                    responseArea.innerHTML = html;
                    
                } catch (error) {
                    responseArea.innerHTML = '<div class="response">Error: ' + error.message + '</div>';
                }
            }
        </script>
    </body>
    </html>
    '''
    return html

@app.route('/analytics')
def analytics_dashboard():
    """Analytics dashboard"""
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>📊 Art Gallery Analytics</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                   background: #f5f7fb; color: #333; }
            .header { background: linear-gradient(135deg, #4361ee 0%, #3a0ca3 100%); 
                     color: white; padding: 2rem; border-radius: 0 0 20px 20px; 
                     box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
            .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
                         gap: 20px; margin: 2rem 0; }
            .stat-card { background: white; padding: 1.5rem; border-radius: 15px; 
                        box-shadow: 0 5px 15px rgba(0,0,0,0.05); border-left: 5px solid #4361ee; }
            .stat-value { font-size: 2.5rem; font-weight: bold; color: #4361ee; }
            .stat-label { color: #6c757d; font-size: 0.9rem; text-transform: uppercase; 
                         letter-spacing: 1px; margin-top: 0.5rem; }
            .chart-container { background: white; border-radius: 15px; padding: 1.5rem; 
                              margin-bottom: 2rem; box-shadow: 0 5px 15px rgba(0,0,0,0.05); }
            .tab-container { background: white; border-radius: 15px; padding: 1.5rem; 
                            box-shadow: 0 5px 15px rgba(0,0,0,0.05); }
            .tabs { display: flex; border-bottom: 2px solid #e9ecef; margin-bottom: 1.5rem; }
            .tab { padding: 1rem 2rem; border: none; background: none; cursor: pointer; 
                   font-weight: 500; color: #6c757d; transition: all 0.3s; }
            .tab.active { color: #4361ee; border-bottom: 3px solid #4361ee; }
            .tab-content { display: none; }
            .tab-content.active { display: block; }
            .time-filter { display: flex; gap: 10px; margin-bottom: 1.5rem; }
            .time-btn { padding: 0.5rem 1rem; border: 2px solid #4361ee; background: white; 
                       color: #4361ee; border-radius: 8px; cursor: pointer; transition: all 0.3s; }
            .time-btn.active { background: #4361ee; color: white; }
            .artwork-list { max-height: 500px; overflow-y: auto; }
            .artwork-item { display: flex; align-items: center; padding: 1rem; 
                           border-bottom: 1px solid #e9ecef; transition: background 0.3s; }
            .artwork-item:hover { background: #f8f9fa; }
            .demand-score { width: 50px; height: 50px; border-radius: 50%; 
                           background: #4361ee; color: white; display: flex; 
                           align-items: center; justify-content: center; 
                           font-weight: bold; margin-right: 1rem; }
            .demand-score.high { background: linear-gradient(135deg, #4cc9f0, #4361ee); }
            .demand-score.medium { background: linear-gradient(135deg, #ff9e00, #ff5400); }
            .demand-score.low { background: linear-gradient(135deg, #adb5bd, #6c757d); }
            table { width: 100%; border-collapse: collapse; }
            th { background: #f8f9fa; padding: 1rem; text-align: left; font-weight: 600; }
            td { padding: 1rem; border-bottom: 1px solid #e9ecef; }
            .realtime-update { background: #e8f4fd; padding: 1rem; border-radius: 8px; 
                              margin: 1rem 0; border-left: 4px solid #4361ee; 
                              animation: fadeIn 0.5s; }
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(-10px); }
                to { opacity: 1; transform: translateY(0); }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1><i class="bi bi-bar-chart-fill"></i> Art Gallery Analytics Dashboard</h1>
            <p>Real-time insights into visitor interactions and artwork demand</p>
        </div>
        
        <div class="container">
            <!-- Time Filter -->
            <div class="time-filter">
                <button class="time-btn active" onclick="filterData('24h')">24 Hours</button>
                <button class="time-btn" onclick="filterData('7d')">7 Days</button>
                <button class="time-btn" onclick="filterData('30d')">30 Days</button>
                <button class="time-btn" onclick="filterData('all')">All Time</button>
            </div>
            
            <!-- Stats Overview -->
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" id="totalQueries">0</div>
                    <div class="stat-label">Total Queries</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="uniqueVisitors">0</div>
                    <div class="stat-label">Unique Visitors</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="avgResponse">0s</div>
                    <div class="stat-label">Avg Response Time</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="topArtwork">--</div>
                    <div class="stat-label">Top Artwork</div>
                </div>
            </div>
            
            <!-- Charts -->
            <div class="chart-container">
                <h3>Query Volume (Last 24 Hours)</h3>
                <canvas id="queryChart" height="150"></canvas>
            </div>
            
            <div class="tab-container">
                <div class="tabs">
                    <button class="tab active" onclick="switchTab('top-artworks')">Top Artworks</button>
                    <button class="tab" onclick="switchTab('recent-queries')">Recent Queries</button>
                    <button class="tab" onclick="switchTab('realtime')">Real-time Updates</button>
                    <button class="tab" onclick="switchTab('export')">Export Data</button>
                </div>
                
                <!-- Top Artworks Tab -->
                <div id="top-artworks" class="tab-content active">
                    <div class="artwork-list" id="artworkList">
                        <!-- Filled by JavaScript -->
                    </div>
                </div>
                
                <!-- Recent Queries Tab -->
                <div id="recent-queries" class="tab-content">
                    <table>
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Query</th>
                                <th>Artworks</th>
                                <th>Response Time</th>
                                <th>Visitor</th>
                            </tr>
                        </thead>
                        <tbody id="recentQueriesTable">
                            <!-- Filled by JavaScript -->
                        </tbody>
                    </table>
                </div>
                
                <!-- Real-time Tab -->
                <div id="realtime" class="tab-content">
                    <div id="realtimeUpdates">
                        <p>Connecting to real-time updates...</p>
                    </div>
                </div>
                
                <!-- Export Tab -->
                <div id="export" class="tab-content">
                    <h4>Export Analytics Data</h4>
                    <div style="margin: 2rem 0;">
                        <select id="exportPeriod" style="padding: 0.5rem; margin-right: 1rem;">
                            <option value="24h">Last 24 Hours</option>
                            <option value="7d">Last 7 Days</option>
                            <option value="30d">Last 30 Days</option>
                            <option value="all">All Time</option>
                        </select>
                        <select id="exportFormat" style="padding: 0.5rem; margin-right: 1rem;">
                            <option value="json">JSON</option>
                            <option value="csv">CSV</option>
                        </select>
                        <button onclick="exportData()" style="padding: 0.5rem 1.5rem; background: #4361ee; 
                                color: white; border: none; border-radius: 8px; cursor: pointer;">
                            Export
                        </button>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            let currentFilter = '24h';
            let queryChart = null;
            let socket = null;
            
            // Initialize
            document.addEventListener('DOMContentLoaded', function() {
                loadAnalyticsData();
                connectWebSocket();
                setInterval(loadAnalyticsData, 30000); // Refresh every 30 seconds
            });
            
            function filterData(period) {
                currentFilter = period;
                document.querySelectorAll('.time-btn').forEach(btn => btn.classList.remove('active'));
                event.target.classList.add('active');
                loadAnalyticsData();
            }
            
            function switchTab(tabId) {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                event.target.classList.add('active');
                document.getElementById(tabId).classList.add('active');
            }
            
            async function loadAnalyticsData() {
                try {
                    // Load system stats
                    const statsRes = await fetch(`/api/analytics/stats?period=${currentFilter}`);
                    const stats = await statsRes.json();
                    
                    // Load top artworks
                    const artworksRes = await fetch(`/api/analytics/top-artworks?period=${currentFilter}&limit=10`);
                    const artworks = await artworksRes.json();
                    
                    // Load recent queries
                    const queriesRes = await fetch(`/api/analytics/recent-queries?limit=20`);
                    const queries = await queriesRes.json();
                    
                    // Update UI
                    updateStats(stats);
                    updateTopArtworks(artworks.artworks);
                    updateRecentQueries(queries.queries);
                    updateChart(stats.hourly_data);
                    
                } catch (error) {
                    console.error('Error loading analytics:', error);
                }
            }
            
            function updateStats(data) {
                document.getElementById('totalQueries').textContent = data.total_queries || 0;
                document.getElementById('uniqueVisitors').textContent = data.unique_visitors || 0;
                document.getElementById('avgResponse').textContent = (data.avg_response_time || 0).toFixed(2) + 's';
                document.getElementById('topArtwork').textContent = data.top_artwork || '--';
            }
            
            function updateTopArtworks(artworks) {
                const container = document.getElementById('artworkList');
                container.innerHTML = '';
                
                artworks.forEach((art, index) => {
                    const score = art.demand_score || 0;
                    const scoreClass = score >= 70 ? 'high' : score >= 40 ? 'medium' : 'low';
                    const ctr = art.click_through_rate ? (art.click_through_rate * 100).toFixed(1) : '0.0';
                    
                    const html = `
                    <div class="artwork-item">
                        <div class="demand-score ${scoreClass}">${score}</div>
                        <div style="flex: 1;">
                            <strong>${art.artwork_title}</strong><br>
                            <small style="color: #6c757d;">${art.artwork_artist}</small>
                        </div>
                        <div style="text-align: right;">
                            <div>${art.total_queries || 0} queries</div>
                            <small style="color: #6c757d;">${ctr}% CTR</small>
                        </div>
                    </div>
                    `;
                    container.innerHTML += html;
                });
            }
            
            function updateRecentQueries(queries) {
                const tbody = document.getElementById('recentQueriesTable');
                tbody.innerHTML = '';
                
                queries.forEach(query => {
                    const time = new Date(query.timestamp * 1000).toLocaleTimeString();
                    const html = `
                    <tr>
                        <td>${time}</td>
                        <td>${(query.query_text || '').substring(0, 50)}...</td>
                        <td>${query.artworks_found || 0}</td>
                        <td>${(query.response_time || 0).toFixed(2)}s</td>
                        <td>${(query.visitor_id || '').substring(0, 8)}</td>
                    </tr>
                    `;
                    tbody.innerHTML += html;
                });
            }
            
            function updateChart(hourlyData) {
                const ctx = document.getElementById('queryChart').getContext('2d');
                
                if (queryChart) {
                    queryChart.destroy();
                }
                
                const labels = hourlyData.map(h => h.hour.substring(11, 16));
                const data = hourlyData.map(h => h.queries);
                
                queryChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Queries',
                            data: data,
                            borderColor: '#4361ee',
                            backgroundColor: 'rgba(67, 97, 238, 0.1)',
                            tension: 0.4,
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: { display: false }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: { stepSize: 1 }
                            }
                        }
                    }
                });
            }
            
            function connectWebSocket() {
                socket = new WebSocket(`ws://${window.location.host}`);
                
                socket.onopen = function() {
                    console.log('WebSocket connected');
                    socket.send(JSON.stringify({type: 'subscribe_analytics'}));
                };
                
                socket.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'analytics_update') {
                        const container = document.getElementById('realtimeUpdates');
                        const update = data.data;
                        
                        let message = '';
                        if (update.type === 'new_query') {
                            message = `New query: "${update.query.substring(0, 30)}..." (${update.artwork_count} artworks found)`;
                        } else if (update.type === 'artwork_click') {
                            message = `Artwork clicked: ID ${update.artwork_id} (${update.duration}s)`;
                        } else if (update.type === 'feedback') {
                            message = `Feedback received: ${update.score}/5 stars`;
                        }
                        
                        const html = `
                        <div class="realtime-update">
                            <strong>${new Date().toLocaleTimeString()}</strong><br>
                            ${message}
                        </div>
                        `;
                        
                        container.innerHTML = html + container.innerHTML;
                        
                        // Limit to 10 updates
                        const updates = container.querySelectorAll('.realtime-update');
                        if (updates.length > 10) {
                            updates[10].remove();
                        }
                    }
                };
            }
            
            function exportData() {
                const period = document.getElementById('exportPeriod').value;
                const format = document.getElementById('exportFormat').value;
                
                window.open(`/api/analytics/export?period=${period}&format=${format}`, '_blank');
            }
        </script>
    </body>
    </html>
    '''
    return html

# ==================== API ENDPOINTS ====================

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'artworks': len(system.rag.artworks),
        'analytics_records': system.analytics.get_total_records(),
        'ollama_available': system.ollama_available,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/artworks')
def get_artworks():
    """Get all artworks"""
    artworks = system.rag.get_all_artworks()
    return jsonify(artworks)

@app.route('/api/query', methods=['POST'])
def handle_query():
    """Handle text queries"""
    data = request.json
    if not data or 'question' not in data:
        return jsonify({'error': 'No question provided'}), 400
    
    question = data['question'].strip()
    if not question:
        return jsonify({'error': 'Empty question'}), 400
    
    metadata = {
        'session_id': data.get('session_id'),
        'visitor_id': data.get('visitor_id'),
        'device_type': data.get('device_type'),
        'location': data.get('location'),
        'ip_address': request.remote_addr
    }
    
    result = system.process_query(question, metadata)
    return jsonify(result)

@app.route('/api/audio/<filename>')
def get_audio(filename):
    """Serve audio files"""
    filepath = os.path.join(Config.AUDIO_FOLDER, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'Audio file not found'}), 404
    
    if '..' in filename or filename.startswith('/'):
        return jsonify({'error': 'Invalid filename'}), 400
    
    return send_file(filepath, mimetype='audio/mpeg')

@app.route('/api/analytics/stats')
def get_analytics_stats():
    """Get analytics statistics"""
    period = request.args.get('period', '24h')
    
    stats = system.analytics.get_system_stats(period)
    return jsonify(stats)

@app.route('/api/analytics/top-artworks')
def get_analytics_top_artworks():
    """Get top artworks by demand"""
    period = request.args.get('period', '24h')
    limit = request.args.get('limit', 10, type=int)
    
    artworks = system.analytics.get_top_artworks(period, limit)
    return jsonify({'artworks': artworks})

@app.route('/api/analytics/recent-queries')
def get_recent_queries():
    """Get recent queries"""
    limit = request.args.get('limit', 20, type=int)
    
    queries = system.analytics.get_recent_queries(limit)
    return jsonify({'queries': queries})

@app.route('/api/analytics/record-click', methods=['POST'])
def record_click():
    """Record artwork click"""
    data = request.json
    
    if not data or 'query_id' not in data or 'artwork_id' not in data:
        return jsonify({'error': 'Missing query_id or artwork_id'}), 400
    
    system.record_artwork_click(
        data['query_id'],
        data['artwork_id'],
        data.get('duration', 0)
    )
    
    return jsonify({'success': True})

@app.route('/api/analytics/feedback', methods=['POST'])
def record_feedback():
    """Record feedback"""
    data = request.json
    
    if not data or 'query_id' not in data or 'score' not in data:
        return jsonify({'error': 'Missing query_id or score'}), 400
    
    system.record_feedback(
        data['query_id'],
        data['score'],
        data.get('comment', '')
    )
    
    return jsonify({'success': True})

@app.route('/api/analytics/export')
def export_analytics():
    """Export analytics data"""
    period = request.args.get('period', '24h')
    format_type = request.args.get('format', 'json')
    
    data = system.analytics.export_data(period, format_type)
    
    if format_type == 'csv':
        return data, 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': f'attachment; filename=analytics_{period}.csv'
        }
    
    return jsonify(data)

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"Server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

# ==================== MAIN ENTRY ====================

def main():
    """Main entry point"""
    logger.info("🚀 Starting AI Art Gallery Server with Analytics...")
    logger.info(f"🌐 Server: http://{Config.HOST}:{Config.PORT}")
    logger.info(f"📊 Dashboard: http://{Config.HOST}:{Config.PORT}/analytics")
    
    socketio.run(
        app,
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
        allow_unsafe_werkzeug=True
    )

if __name__ == '__main__':
    main()
