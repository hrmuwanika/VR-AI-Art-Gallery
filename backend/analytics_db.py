#!/usr/bin/env python3
"""
Analytics Database for Art Gallery Demand Tracking
"""

import sqlite3
import json
import time
import hashlib
import csv
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import threading

logger = logging.getLogger(__name__)

@dataclass
class QueryLog:
    """Query log data class"""
    query_id: str
    query_text: str
    timestamp: float
    session_id: str
    visitor_id: str
    response_time: float
    artworks_found: int
    ai_generated: bool
    language: str = 'en'
    device_type: Optional[str] = None
    location: Optional[str] = None

@dataclass
class ArtworkInteraction:
    """Artwork interaction data class"""
    interaction_id: str
    query_id: str
    artwork_id: int
    artwork_title: str
    artwork_artist: str
    similarity_score: float
    was_clicked: bool = False
    click_duration: float = 0.0
    feedback_score: Optional[int] = None

@dataclass
class VisitorSession:
    """Visitor session data class"""
    session_id: str
    visitor_id: str
    start_time: float
    end_time: Optional[float] = None
    total_queries: int = 0
    total_artworks_viewed: int = 0
    total_time_spent: float = 0.0
    device_type: Optional[str] = None
    location: Optional[str] = None

class AnalyticsDB:
    """Analytics database manager"""
    
    def __init__(self, db_path: str = "analytics.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()
        self._cleanup_old_data()
    
    @contextmanager
    def get_connection(self):
        """Thread-safe database connection"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
    
    def _init_db(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Query logs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS query_logs (
                    query_id TEXT PRIMARY KEY,
                    query_text TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    session_id TEXT NOT NULL,
                    visitor_id TEXT NOT NULL,
                    response_time REAL NOT NULL,
                    artworks_found INTEGER NOT NULL,
                    ai_generated BOOLEAN NOT NULL,
                    language TEXT DEFAULT 'en',
                    device_type TEXT,
                    location TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Artwork interactions
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS artwork_interactions (
                    interaction_id TEXT PRIMARY KEY,
                    query_id TEXT NOT NULL,
                    artwork_id INTEGER NOT NULL,
                    artwork_title TEXT NOT NULL,
                    artwork_artist TEXT NOT NULL,
                    similarity_score REAL NOT NULL,
                    was_clicked BOOLEAN DEFAULT 0,
                    click_duration REAL DEFAULT 0,
                    feedback_score INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (query_id) REFERENCES query_logs(query_id)
                )
            ''')
            
            # Visitor sessions
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS visitor_sessions (
                    session_id TEXT PRIMARY KEY,
                    visitor_id TEXT NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL,
                    total_queries INTEGER DEFAULT 0,
                    total_artworks_viewed INTEGER DEFAULT 0,
                    total_time_spent REAL DEFAULT 0.0,
                    device_type TEXT,
                    location TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Artwork demand metrics
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS artwork_demand (
                    artwork_id INTEGER PRIMARY KEY,
                    artwork_title TEXT NOT NULL,
                    artwork_artist TEXT NOT NULL,
                    total_queries INTEGER DEFAULT 0,
                    total_clicks INTEGER DEFAULT 0,
                    avg_similarity REAL DEFAULT 0.0,
                    total_time_viewed REAL DEFAULT 0.0,
                    positive_feedback INTEGER DEFAULT 0,
                    negative_feedback INTEGER DEFAULT 0,
                    last_queried TIMESTAMP,
                    demand_score REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Hourly metrics
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS hourly_metrics (
                    hour_timestamp TEXT PRIMARY KEY,
                    total_queries INTEGER DEFAULT 0,
                    unique_visitors INTEGER DEFAULT 0,
                    avg_response_time REAL DEFAULT 0.0,
                    top_artwork_id INTEGER,
                    top_artwork_title TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Feedback
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id TEXT PRIMARY KEY,
                    query_id TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    comment TEXT,
                    timestamp REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (query_id) REFERENCES query_logs(query_id)
                )
            ''')
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_query_time ON query_logs(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_interaction_artwork ON artwork_interactions(artwork_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_demand_score ON artwork_demand(demand_score DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_hourly_time ON hourly_metrics(hour_timestamp)')
            
            logger.info("Analytics database initialized")
    
    def _cleanup_old_data(self, days_to_keep: int = 90):
        """Clean up old data"""
        cutoff = time.time() - (days_to_keep * 86400)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM query_logs WHERE timestamp < ?', (cutoff,))
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old query logs")
    
    def session_exists(self, session_id: str) -> bool:
        """Check if session exists"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM visitor_sessions WHERE session_id = ?', (session_id,))
            return cursor.fetchone() is not None
    
    def start_session(self, session: VisitorSession):
        """Start new session"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO visitor_sessions 
                (session_id, visitor_id, start_time, device_type, location)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                session.session_id,
                session.visitor_id,
                session.start_time,
                session.device_type,
                session.location
            ))
    
    def update_session(self, session_id: str, updates: Dict):
        """Update session data"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if 'total_queries' in updates:
                cursor.execute('''
                    UPDATE visitor_sessions 
                    SET total_queries = total_queries + ?,
                        total_time_spent = total_time_spent + ?
                    WHERE session_id = ?
                ''', (updates['total_queries'], updates.get('total_time', 0), session_id))
            
            if 'total_artworks' in updates:
                cursor.execute('''
                    UPDATE visitor_sessions 
                    SET total_artworks_viewed = total_artworks_viewed + ?
                    WHERE session_id = ?
                ''', (updates['total_artworks'], session_id))
    
    def log_query(self, query_log: QueryLog):
        """Log a query"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO query_logs 
                (query_id, query_text, timestamp, session_id, visitor_id,
                 response_time, artworks_found, ai_generated, language,
                 device_type, location)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', asdict(query_log).values())
            
            # Update hourly metrics
            self._update_hourly_metrics(query_log.timestamp)
    
    def log_artwork_interaction(self, interaction: ArtworkInteraction):
        """Log artwork interaction"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO artwork_interactions
                (interaction_id, query_id, artwork_id, artwork_title,
                 artwork_artist, similarity_score, was_clicked,
                 click_duration, feedback_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', asdict(interaction).values())
            
            # Update artwork demand
            self._update_artwork_demand(interaction)
    
    def record_click(self, query_id: str, artwork_id: int, duration: float):
        """Record artwork click"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Update interaction
            cursor.execute('''
                UPDATE artwork_interactions 
                SET was_clicked = 1, click_duration = ?
                WHERE query_id = ? AND artwork_id = ?
            ''', (duration, query_id, artwork_id))
            
            # Update artwork demand
            cursor.execute('''
                UPDATE artwork_demand 
                SET total_clicks = total_clicks + 1,
                    total_time_viewed = total_time_viewed + ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE artwork_id = ?
            ''', (duration, artwork_id))
            
            # Update session
            cursor.execute('''
                UPDATE visitor_sessions 
                SET total_artworks_viewed = total_artworks_viewed + 1,
                    total_time_spent = total_time_spent + ?
                WHERE session_id = (
                    SELECT session_id FROM query_logs WHERE query_id = ?
                )
            ''', (duration, query_id))
    
    def record_feedback(self, query_id: str, score: int, comment: str = ""):
        """Record feedback"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Save feedback
            feedback_id = hashlib.md5(f"{query_id}_{time.time()}".encode()).hexdigest()
            cursor.execute('''
                INSERT INTO feedback (feedback_id, query_id, score, comment, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (feedback_id, query_id, score, comment, time.time()))
            
            # Update interactions
            cursor.execute('''
                UPDATE artwork_interactions 
                SET feedback_score = ?
                WHERE query_id = ?
            ''', (score, query_id))
            
            # Update artwork demand
            if score >= 4:
                cursor.execute('''
                    UPDATE artwork_demand 
                    SET positive_feedback = positive_feedback + 1
                    WHERE artwork_id IN (
                        SELECT artwork_id FROM artwork_interactions 
                        WHERE query_id = ?
                    )
                ''', (query_id,))
            elif score <= 2:
                cursor.execute('''
                    UPDATE artwork_demand 
                    SET negative_feedback = negative_feedback + 1
                    WHERE artwork_id IN (
                        SELECT artwork_id FROM artwork_interactions 
                        WHERE query_id = ?
                    )
                ''', (query_id,))
            
            # Recalculate demand scores
            cursor.execute('''
                SELECT artwork_id FROM artwork_interactions WHERE query_id = ?
            ''', (query_id,))
            
            for row in cursor.fetchall():
                self._recalculate_demand_score(row['artwork_id'])
    
    def _update_hourly_metrics(self, timestamp: float):
        """Update hourly metrics"""
        hour_ts = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:00:00')
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get stats for this hour
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_queries,
                    COUNT(DISTINCT visitor_id) as unique_visitors,
                    AVG(response_time) as avg_response_time
                FROM query_logs
                WHERE timestamp >= ? AND timestamp < ?
            ''', (timestamp - 3600, timestamp))
            
            stats = cursor.fetchone()
            
            # Get top artwork for this hour
            cursor.execute('''
                SELECT ai.artwork_id, ad.artwork_title, COUNT(*) as query_count
                FROM artwork_interactions ai
                JOIN artwork_demand ad ON ai.artwork_id = ad.artwork_id
                WHERE ai.created_at >= datetime(?, '-1 hour')
                GROUP BY ai.artwork_id
                ORDER BY query_count DESC
                LIMIT 1
            ''', (hour_ts,))
            
            top_artwork = cursor.fetchone()
            
            # Update hourly metrics
            cursor.execute('''
                INSERT OR REPLACE INTO hourly_metrics
                (hour_timestamp, total_queries, unique_visitors,
                 avg_response_time, top_artwork_id, top_artwork_title)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                hour_ts,
                stats['total_queries'] if stats else 0,
                stats['unique_visitors'] if stats else 0,
                stats['avg_response_time'] if stats else 0,
                top_artwork['artwork_id'] if top_artwork else None,
                top_artwork['artwork_title'] if top_work else None
            ))
    
    def _update_artwork_demand(self, interaction: ArtworkInteraction):
        """Update artwork demand metrics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if artwork exists in demand table
            cursor.execute('SELECT * FROM artwork_demand WHERE artwork_id = ?', 
                          (interaction.artwork_id,))
            
            artwork = cursor.fetchone()
            
            if artwork:
                # Update existing
                total_queries = artwork['total_queries'] + 1
                total_clicks = artwork['total_clicks'] + (1 if interaction.was_clicked else 0)
                total_time = artwork['total_time_viewed'] + interaction.click_duration
                
                # Update similarity average
                new_avg = ((artwork['avg_similarity'] * artwork['total_queries']) + 
                          interaction.similarity_score) / total_queries
                
                # Calculate new demand score
                demand_score = self._calculate_demand_score(
                    total_queries, total_clicks, new_avg,
                    artwork['positive_feedback'], artwork['negative_feedback']
                )
                
                cursor.execute('''
                    UPDATE artwork_demand 
                    SET total_queries = ?,
                        total_clicks = ?,
                        avg_similarity = ?,
                        total_time_viewed = ?,
                        last_queried = CURRENT_TIMESTAMP,
                        demand_score = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE artwork_id = ?
                ''', (total_queries, total_clicks, new_avg, total_time, 
                     demand_score, interaction.artwork_id))
            else:
                # Insert new artwork
                demand_score = self._calculate_demand_score(
                    1, 1 if interaction.was_clicked else 0,
                    interaction.similarity_score, 0, 0
                )
                
                cursor.execute('''
                    INSERT INTO artwork_demand 
                    (artwork_id, artwork_title, artwork_artist,
                     total_queries, total_clicks, avg_similarity,
                     total_time_viewed, demand_score, last_queried)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    interaction.artwork_id,
                    interaction.artwork_title,
                    interaction.artwork_artist,
                    1,
                    1 if interaction.was_clicked else 0,
                    interaction.similarity_score,
                    interaction.click_duration,
                    demand_score
                ))
    
    def _recalculate_demand_score(self, artwork_id: int):
        """Recalculate demand score for artwork"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM artwork_demand WHERE artwork_id = ?
            ''', (artwork_id,))
            
            artwork = cursor.fetchone()
            if not artwork:
                return
            
            demand_score = self._calculate_demand_score(
                artwork['total_queries'],
                artwork['total_clicks'],
                artwork['avg_similarity'],
                artwork['positive_feedback'],
                artwork['negative_feedback']
            )
            
            cursor.execute('''
                UPDATE artwork_demand 
                SET demand_score = ?, updated_at = CURRENT_TIMESTAMP
                WHERE artwork_id = ?
            ''', (demand_score, artwork_id))
    
    def _calculate_demand_score(self, queries: int, clicks: int, similarity: float,
                               positive: int, negative: int) -> float:
        """Calculate demand score (0-100)"""
        if queries == 0:
            return 0.0
        
        click_rate = clicks / queries if queries > 0 else 0
        feedback_rate = positive / (positive + negative) if (positive + negative) > 0 else 0.5
        
        # Weighted formula
        score = (
            min(queries / 50, 1.0) * 0.4 +        # Query volume (40%)
            click_rate * 0.3 +                    # Click-through rate (30%)
            similarity * 0.2 +                    # Relevance (20%)
            feedback_rate * 0.1                   # Feedback (10%)
        ) * 100
        
        return round(score, 2)
    
    # ==================== QUERY METHODS ====================
    
    def get_system_stats(self, period: str = '24h') -> Dict:
        """Get system statistics"""
        time_filter = self._get_time_filter(period)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Overall stats
            cursor.execute(f'''
                SELECT 
                    COUNT(*) as total_queries,
                    COUNT(DISTINCT visitor_id) as unique_visitors,
                    AVG(response_time) as avg_response_time,
                    COUNT(CASE WHEN ai_generated = 1 THEN 1 END) as ai_queries
                FROM query_logs
                WHERE 1=1 {time_filter}
            ''')
            
            stats = cursor.fetchone()
            
            # Top artwork
            cursor.execute(f'''
                SELECT artwork_title, COUNT(*) as query_count
                FROM artwork_interactions ai
                JOIN query_logs ql ON ai.query_id = ql.query_id
                WHERE 1=1 {time_filter}
                GROUP BY ai.artwork_id, ai.artwork_title
                ORDER BY query_count DESC
                LIMIT 1
            ''')
            
            top_artwork = cursor.fetchone()
            
            # Hourly data for chart
            cursor.execute('''
                SELECT 
                    hour_timestamp as hour,
                    total_queries as queries,
                    unique_visitors as visitors
                FROM hourly_metrics
                ORDER BY hour_timestamp DESC
                LIMIT 24
            ''')
            
            hourly = cursor.fetchall()
            
            return {
                'total_queries': stats['total_queries'] if stats else 0,
                'unique_visitors': stats['unique_visitors'] if stats else 0,
                'avg_response_time': stats['avg_response_time'] if stats else 0,
                'ai_queries': stats['ai_queries'] if stats else 0,
                'top_artwork': top_artwork['artwork_title'] if top_artwork else None,
                'hourly_data': [dict(h) for h in reversed(hourly)]
            }
    
    def get_top_artworks(self, period: str = '24h', limit: int = 10) -> List[Dict]:
        """Get top artworks by demand"""
        time_filter = self._get_time_filter(period)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(f'''
                SELECT 
                    ad.artwork_id,
                    ad.artwork_title,
                    ad.artwork_artist,
                    ad.total_queries,
                    ad.total_clicks,
                    ad.avg_similarity,
                    ad.demand_score,
                    ad.positive_feedback,
                    ad.negative_feedback,
                    (ad.total_clicks * 1.0 / ad.total_queries) as click_through_rate
                FROM artwork_demand ad
                WHERE 1=1 {time_filter}
                ORDER BY ad.demand_score DESC
                LIMIT ?
            ''', (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_recent_queries(self, limit: int = 20) -> List[Dict]:
        """Get recent queries"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    query_text,
                    timestamp,
                    artworks_found,
                    response_time,
                    ai_generated,
                    visitor_id
                FROM query_logs
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_total_records(self) -> Dict:
        """Get total record counts"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) as count FROM query_logs')
            queries = cursor.fetchone()['count']
            
            cursor.execute('SELECT COUNT(*) as count FROM artwork_interactions')
            interactions = cursor.fetchone()['count']
            
            cursor.execute('SELECT COUNT(DISTINCT visitor_id) as count FROM visitor_sessions')
            visitors = cursor.fetchone()['count']
            
            return {
                'queries': queries,
                'interactions': interactions,
                'visitors': visitors
            }
    
    def export_data(self, period: str = '24h', format: str = 'json') -> Any:
        """Export analytics data"""
        time_filter = self._get_time_filter(period)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get artwork demand
            cursor.execute(f'''
                SELECT * FROM artwork_demand 
                WHERE 1=1 {time_filter}
                ORDER BY demand_score DESC
            ''')
            
            artworks = [dict(row) for row in cursor.fetchall()]
            
            # Get recent queries
            cursor.execute(f'''
                SELECT * FROM query_logs 
                WHERE 1=1 {time_filter}
                ORDER BY timestamp DESC 
                LIMIT 1000
            ''')
            
            queries = [dict(row) for row in cursor.fetchall()]
            
            # Get hourly metrics
            cursor.execute(f'''
                SELECT * FROM hourly_metrics 
                WHERE 1=1 {time_filter}
                ORDER BY hour_timestamp DESC 
                LIMIT 168
            ''')
            
            hourly = [dict(row) for row in cursor.fetchall()]
            
            data = {
                'artworks': artworks,
                'queries': queries,
                'hourly_metrics': hourly,
                'exported_at': datetime.now().isoformat(),
                'period': period,
                'total_records': len(artworks) + len(queries) + len(hourly)
            }
            
            if format == 'csv':
                return self._convert_to_csv(data)
            
            return data
    
    def _convert_to_csv(self, data: Dict) -> str:
        """Convert data to CSV format"""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write artwork data
        writer.writerow(['Artwork Analytics'])
        writer.writerow(['ID', 'Title', 'Artist', 'Demand Score', 'Queries', 'Clicks', 'CTR'])
        
        for art in data['artworks']:
            ctr = (art.get('total_clicks', 0) / art.get('total_queries', 1)) * 100
            writer.writerow([
                art.get('artwork_id', ''),
                art.get('artwork_title', ''),
                art.get('artwork_artist', ''),
                art.get('demand_score', 0),
                art.get('total_queries', 0),
                art.get('total_clicks', 0),
                f"{ctr:.1f}%"
            ])
        
        writer.writerow([])
        writer.writerow(['Recent Queries'])
        writer.writerow(['Time', 'Query', 'Artworks Found', 'Response Time', 'AI Generated'])
        
        for query in data['queries'][:50]:
            time_str = datetime.fromtimestamp(query.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M')
            writer.writerow([
                time_str,
                query.get('query_text', '')[:50],
                query.get('artworks_found', 0),
                f"{query.get('response_time', 0):.2f}s",
                'Yes' if query.get('ai_generated') else 'No'
            ])
        
        return output.getvalue()
    
    def _get_time_filter(self, period: str) -> str:
        """Convert period to SQL filter"""
        if period == '24h':
            cutoff = time.time() - 86400
            return f"AND timestamp >= {cutoff}"
        elif period == '7d':
            cutoff = time.time() - 604800
            return f"AND timestamp >= {cutoff}"
        elif period == '30d':
            cutoff = time.time() - 2592000
            return f"AND timestamp >= {cutoff}"
        else:
            return ""
