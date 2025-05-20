from flask import Flask, jsonify, render_template_string
from threading import Thread
import os
import time
from datetime import datetime, timezone
import logging
import json
from website_monitor import WebsiteChangeMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global variables to track state
monitor_thread = None
monitor_status = {
    "is_running": False,
    "last_check_time": None,
    "target_url": None,
    "check_interval": None,
    "changes_detected": 0
}

# Simple HTML template for the dashboard
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Website Monitor Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
        }
        h1 {
            color: #2c3e50;
            border-bottom: 1px solid #eee;
            padding-bottom: 10px;
        }
        .status-card {
            background-color: #f9f9f9;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-active {
            background-color: #2ecc71;
        }
        .status-inactive {
            background-color: #e74c3c;
        }
        .refresh-button {
            background-color: #3498db;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }
        .refresh-button:hover {
            background-color: #2980b9;
        }
    </style>
</head>
<body>
    <h1>Website Monitor Dashboard</h1>
    
    <div class="status-card">
        <h2>Monitor Status</h2>
        <p>
            <span class="status-indicator {{ 'status-active' if status.is_running else 'status-inactive' }}"></span>
            <strong>Status:</strong> {{ "Running" if status.is_running else "Not Running" }}
        </p>
        <p><strong>Target URL:</strong> {{ status.target_url or "Not configured" }}</p>
        <p><strong>Check Interval:</strong> {{ status.check_interval or "Not configured" }} seconds</p>
        <p><strong>Last Check:</strong> {{ status.last_check_time or "No checks yet" }}</p>
        <p><strong>Changes Detected:</strong> {{ status.changes_detected }}</p>
    </div>
    
    <button class="refresh-button" onclick="window.location.reload()">Refresh Dashboard</button>
    
    <script>
        // Auto-refresh the page every 60 seconds
        setTimeout(() => {
            window.location.reload();
        }, 60000);
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    """Homepage shows status dashboard."""
    # Format the last check time nicely if it exists
    if monitor_status["last_check_time"]:
        last_check = monitor_status["last_check_time"].strftime('%Y-%m-%d %H:%M:%S UTC')
    else:
        last_check = None
    
    # Prepare status data for the template
    status_data = {
        "is_running": monitor_status["is_running"],
        "target_url": monitor_status["target_url"],
        "check_interval": monitor_status["check_interval"],
        "last_check_time": last_check,
        "changes_detected": monitor_status["changes_detected"]
    }
    
    return render_template_string(DASHBOARD_HTML, status=status_data)

@app.route('/api/status')
def api_status():
    """API endpoint for status information."""
    status_copy = monitor_status.copy()
    
    # Convert datetime to string for JSON serialization
    if status_copy["last_check_time"]:
        status_copy["last_check_time"] = status_copy["last_check_time"].isoformat()
    
    return jsonify(status_copy)

@app.route('/health')
def health():
    """Health check endpoint for uptime monitoring."""
    return jsonify({"status": "OK"})

@app.route('/keep-alive')
def keep_alive():
    """Endpoint to keep the service running."""
    return "Service is alive!", 200

def update_monitor_status(url=None, interval=None):
    """Update the monitor status information."""
    monitor_status["last_check_time"] = datetime.now(timezone.utc)
    
    if url:
        monitor_status["target_url"] = url
    
    if interval:
        monitor_status["check_interval"] = interval

def monitor_website():
    """Function to run the website monitor in a loop."""
    global monitor_status
    
    url_to_monitor = os.environ.get('WEBSITE_URL')
    if not url_to_monitor:
        logger.error("WEBSITE_URL environment variable not set. Cannot start monitoring.")
        return
    
    try:
        check_interval = int(os.environ.get('CHECK_INTERVAL', '3600'))
    except ValueError:
        logger.error("Invalid CHECK_INTERVAL. Using default 3600 seconds.")
        check_interval = 3600
    
    # Configure email if all required variables are present
    email_config = None
    if all(os.environ.get(var) for var in ['EMAIL_SENDER', 'EMAIL_RECIPIENT', 'SMTP_SERVER']):
        email_config = {
            'sender': os.environ.get('EMAIL_SENDER'),
            'recipient': os.environ.get('EMAIL_RECIPIENT'),
            'smtp_server': os.environ.get('SMTP_SERVER'),
            'smtp_port': int(os.environ.get('SMTP_PORT', '587')),
            'use_tls': os.environ.get('USE_TLS', 'True').lower() == 'true',
            'username': os.environ.get('EMAIL_USERNAME'),
            'password': os.environ.get('EMAIL_PASSWORD')
        }
        logger.info("Email notifications are configured.")
    else:
        logger.warning("Email notifications are not configured. Set EMAIL_SENDER, EMAIL_RECIPIENT, and SMTP_SERVER environment variables.")
    
    # Create the monitor
    monitor = WebsiteChangeMonitor(
        url=url_to_monitor,
        check_interval=check_interval,
        email_config=email_config
    )
    
    # Update status
    monitor_status["is_running"] = True
    monitor_status["target_url"] = url_to_monitor
    monitor_status["check_interval"] = check_interval
    
    logger.info(f"Starting website monitor for {url_to_monitor}")
    
    # Run the monitoring loop
    while True:
        try:
            result = monitor.check_for_changes()
            update_monitor_status()
            
            # Increment the changes counter if a change was detected
            if result:
                monitor_status["changes_detected"] += 1
            
            # Sleep until next check
            logger.info(f"Sleeping for {check_interval} seconds until next check...")
            time.sleep(check_interval)
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            time.sleep(60)  # Wait a bit before retrying in case of error

def start_monitor_thread():
    """Start the monitoring thread if not already running."""
    global monitor_thread, monitor_status
    
    if monitor_thread is None or not monitor_thread.is_alive():
        monitor_thread = Thread(target=monitor_website)
        monitor_thread.daemon = True
        monitor_thread.start()
        logger.info("Monitor thread started")
    else:
        logger.info("Monitor thread already running")

if __name__ == '__main__':
    # Start the monitor in a separate thread
    start_monitor_thread()
    
    # Start the web server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
else:
    # For gunicorn and other WSGI servers
    start_monitor_thread()
