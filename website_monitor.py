import requests
import time
import hashlib
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import os
import logging
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class WebsiteChangeMonitor:
    def __init__(self, url, check_interval=3600, email_config=None):
        """
        Initialize the website monitor.
        
        Args:
            url: URL of the website to monitor
            check_interval: Time between checks in seconds (default 1 hour)
            email_config: Dictionary with email configuration
        """
        self.url = url
        self.check_interval = check_interval
        self.email_config = email_config
        self.url_hash = hashlib.md5(url.encode()).hexdigest()
        
        # Use a file in the /tmp directory for persistence
        # This is more reliable than env vars on Render
        self.hash_file = f"/tmp/website_hash_{self.url_hash}.json"
        self.previous_hash = self._get_saved_hash()
        logger.info(f"Monitoring initialized for {url}")
        logger.info(f"Previous hash: {self.previous_hash or 'None (first run)'}")
    
    def _get_saved_hash(self):
        """Read the previous hash from file if it exists."""
        try:
            if os.path.exists(self.hash_file):
                with open(self.hash_file, 'r') as f:
                    data = json.load(f)
                    return data.get('hash')
        except Exception as e:
            logger.error(f"Error reading hash file: {e}")
        return None
    
    def _save_hash(self, hash_value):
        """Save the current hash to a file."""
        try:
            with open(self.hash_file, 'w') as f:
                json.dump({
                    'hash': hash_value,
                    'url': self.url,
                    'timestamp': datetime.now().isoformat()
                }, f)
        except Exception as e:
            logger.error(f"Error saving hash file: {e}")
    
    def _get_page_content(self):
        """Fetch the website content."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching the website: {e}")
            return None
    
    def _calculate_hash(self, content):
        """Calculate the SHA-256 hash of the website content."""
        if content:
            return hashlib.sha256(content.encode()).hexdigest()
        return None
    
    def _send_email_notification(self):
        """Send an email notification about the change."""
        if not self.email_config:
            logger.info("Email configuration not provided. Skipping notification.")
            return
        
        try:
            config = self.email_config
            msg = MIMEText(f"Change detected on {self.url} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            msg['Subject'] = f"Website Change Notification: {self.url}"
            msg['From'] = config['sender']
            msg['To'] = config['recipient']
            
            server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
            if config.get('use_tls', False):
                server.starttls()
            
            if 'username' in config and 'password' in config:
                server.login(config['username'], config['password'])
                
            server.send_message(msg)
            server.quit()
            logger.info("Email notification sent successfully!")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
    
    def _log_change(self):
        """Log the change."""
        logger.info(f"Change detected on {self.url} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    def check_for_changes(self):
        """Check if the website has changed since the last check."""
        logger.info(f"Checking for changes on {self.url}")
        content = self._get_page_content()
        if not content:
            logger.warning("Failed to get content, skipping this check")
            return False
        
        current_hash = self._calculate_hash(content)
        
        if not self.previous_hash:
            # First run, save the hash and exit
            logger.info(f"First run. Saving hash for {self.url}")
            self._save_hash(current_hash)
            self.previous_hash = current_hash
            return False
        
        if current_hash != self.previous_hash:
            logger.info(f"Change detected on {self.url}")
            self._save_hash(current_hash)
            self.previous_hash = current_hash
            self._log_change()
            if self.email_config:
                self._send_email_notification()
            return True
        
        logger.info(f"No changes detected on {self.url}")
        return False
    
    def start_monitoring(self):
        """Start the monitoring loop."""
        logger.info(f"Starting to monitor {self.url} every {self.check_interval} seconds.")
        try:
            while True:
                self.check_for_changes()
                logger.info(f"Sleeping for {self.check_interval} seconds...")
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user.")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise
