#!/usr/bin/env python3
"""
Simple OsmoJS Keeper - Just keeps the damn service running
No fancy features, no complicated monitoring - just works.
"""

import subprocess
import time
import requests
import os
import signal
import sys

SERVICE_DIR = os.path.join(os.path.dirname(__file__), '..', 'services', 'osmjs-service')
SERVICE_URL = "http://localhost:3001/health"
CHECK_INTERVAL = 10  # seconds

class SimpleOsmoJSKeeper:
    def __init__(self):
        self.process = None
        self.restart_count = 0
        
    def is_service_healthy(self):
        """Check if service responds to health check"""
        try:
            response = requests.get(SERVICE_URL, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def start_service(self):
        """Start the OsmoJS service"""
        try:
            print(f"🚀 Starting OsmoJS service (restart #{self.restart_count})")
            
            self.process = subprocess.Popen(
                ['npm', 'start'],
                cwd=SERVICE_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Wait a bit for startup
            time.sleep(5)
            
            # Check if it started successfully
            if self.is_service_healthy():
                print(f"✅ Service started successfully (PID: {self.process.pid})")
                self.restart_count += 1
                return True
            else:
                print("❌ Service failed to start properly")
                return False
                
        except Exception as e:
            print(f"❌ Failed to start service: {e}")
            return False
    
    def stop_service(self):
        """Stop the service"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
                print("🛑 Service stopped")
            except:
                try:
                    self.process.kill()
                    print("🔪 Service force killed")
                except:
                    pass
            self.process = None
    
    def is_process_running(self):
        """Check if our process is still alive"""
        if self.process is None:
            return False
        return self.process.poll() is None
    
    def run(self):
        """Main loop - just keep the service alive"""
        print("🎯 Simple OsmoJS Keeper Started")
        print(f"📍 Service directory: {SERVICE_DIR}")
        print(f"🔍 Health check URL: {SERVICE_URL}")
        print(f"⏰ Check interval: {CHECK_INTERVAL} seconds")
        print("-" * 50)
        
        # Initial startup
        if not self.start_service():
            print("❌ Failed to start service initially")
            return
        
        try:
            while True:
                # Check if process died
                if not self.is_process_running():
                    print("💀 Process died, restarting...")
                    self.start_service()
                
                # Check if service is responding
                elif not self.is_service_healthy():
                    print("🔴 Service not responding, restarting...")
                    self.stop_service()
                    time.sleep(2)
                    self.start_service()
                
                else:
                    # Service is healthy
                    print("🟢 Service healthy")
                
                time.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n🛑 Shutting down...")
            self.stop_service()
        except Exception as e:
            print(f"❌ Keeper error: {e}")
            self.stop_service()

def signal_handler(signum, frame):
    """Handle shutdown gracefully"""
    print(f"\n📡 Received signal {signum}, shutting down...")
    sys.exit(0)

if __name__ == "__main__":
    # Handle shutdown signals
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Check if requests is available
    try:
        import requests
    except ImportError:
        print("❌ 'requests' library not found. Install with: pip install requests")
        sys.exit(1)
    
    # Check if service directory exists
    if not os.path.exists(SERVICE_DIR):
        print(f"❌ Service directory not found: {SERVICE_DIR}")
        sys.exit(1)
    
    # Run the keeper
    keeper = SimpleOsmoJSKeeper()
    keeper.run()