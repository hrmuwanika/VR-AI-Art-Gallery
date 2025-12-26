#!/usr/bin/env python3
"""
Automated Reporting System for Art Gallery Analytics
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import logging
from analytics_db import AnalyticsDB

logger = logging.getLogger(__name__)

class ReportGenerator:
    """Generate automated analytics reports"""
    
    def __init__(self, db_path: str = "analytics.db"):
        self.db = AnalyticsDB(db_path)
    
    def generate_daily_report(self, date: datetime = None) -> str:
        """Generate daily report HTML"""
        if date is None:
            date = datetime.now() - timedelta(days=1)
        
        date_str = date.strftime('%Y-%m-%d')
        
        # Get data
        stats = self.db.get_system_stats('24h')
        top_artworks = self.db.get_top_artworks('24h', 5)
        
        # Generate HTML
        html = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #4361ee; color: white; padding: 20px; border-radius: 10px; }}
                .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
                .stat {{ background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; }}
                .stat-value {{ font-size: 24px; font-weight: bold; color: #4361ee; }}
                .stat-label {{ color: #6c757d; font-size: 14px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th {{ background: #f1f3f5; padding: 12px; text-align: left; }}
                td {{ padding: 12px; border-bottom: 1px solid #e9ecef; }}
                .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #dee2e6; 
                         color: #6c757d; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🎨 Art Gallery Daily Analytics Report</h1>
                <p>Date: {date_str}</p>
            </div>
            
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{stats.get('total_queries', 0)}</div>
                    <div class="stat-label">Total Queries</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{stats.get('unique_visitors', 0)}</div>
                    <div class="stat-label">Unique Visitors</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{stats.get('avg_response_time', 0):.2f}s</div>
                    <div class="stat-label">Avg Response Time</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{stats.get('ai_queries', 0)}</div>
                    <div class="stat-label">AI Responses</div>
                </div>
            </div>
            
            <h2>🏆 Top 5 Artworks</h2>
            <table>
                <tr>
                    <th>Artwork</th>
                    <th>Artist</th>
                    <th>Demand Score</th>
                    <th>Queries</th>
                    <th>Clicks</th>
                </tr>
        '''
        
        for art in top_artworks:
            html += f'''
                <tr>
                    <td>{art.get('artwork_title', 'N/A')}</td>
                    <td>{art.get('artwork_artist', 'N/A')}</td>
                    <td>{art.get('demand_score', 0)}</td>
                    <td>{art.get('total_queries', 0)}</td>
                    <td>{art.get('total_clicks', 0)}</td>
                </tr>
            '''
        
        html += '''
            </table>
            
            <div class="footer">
                <p>Generated automatically by Art Gallery Analytics System</p>
                <p>Dashboard: http://localhost:5000/analytics</p>
            </div>
        </body>
        </html>
        '''
        
        return html
    
    def generate_weekly_report(self) -> str:
        """Generate weekly report"""
        # Similar structure with weekly data
        return self.generate_daily_report()

class EmailSender:
    """Send reports via email"""
    
    def __init__(self, smtp_server: str, smtp_port: int, 
                 username: str, password: str):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
    
    def send_report(self, to_email: str, subject: str, html_content: str) -> bool:
        """Send email report"""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.username
            msg['To'] = to_email
            
            msg.attach(MIMEText(html_content, 'html'))
            
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.username, self.password)
                server.send_message(msg)
            
            logger.info(f"Report sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

# Example usage:
# report_gen = ReportGenerator()
# html = report_gen.generate_daily_report()
# sender = EmailSender('smtp.gmail.com', 465, 'your@gmail.com', 'password')
# sender.send_report('curator@museum.com', 'Daily Analytics Report', html)
