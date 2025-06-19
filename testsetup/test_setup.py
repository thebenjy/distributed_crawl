#!/usr/bin/env python3
"""
Test Website Setup for Hybrid Crawler
Creates mock websites to test local crawling vs Lambda fallback
"""

import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import os
from pathlib import Path


class MockWebsiteHandler(BaseHTTPRequestHandler):
    """HTTP handler for mock websites"""
    
    def log_message(self, format, *args):
        """Override to reduce log noise"""
        pass
    
    def do_GET(self):
        """Handle GET requests"""
        path = self.path
        
        # Determine which site we're serving based on port
        server_port = self.server.server_address[1]
        
        if server_port == 8001:
            self.serve_normal_site(path)
        elif server_port == 8002:
            self.serve_geo_blocked_site(path)
        else:
            self.send_error(404, "Unknown server")
    
    def serve_normal_site(self, path):
        """Serve the normal website (port 8001)"""
        
        if path == "/" or path == "/index.html":
            content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Normal Website - Home</title>
                <meta charset="utf-8">
            </head>
            <body>
                <h1>Welcome to Normal Website</h1>
                <p>This is a normal website that can be crawled locally.</p>
                <p>It contains useful content about web development and technology.</p>
                
                <h2>Navigation</h2>
                <ul>
                    <li><a href="/about">About Us</a></li>
                    <li><a href="/services">Our Services</a></li>
                    <li><a href="/contact">Contact</a></li>
                    <li><a href="http://localhost:8002/">External Link (Geo-blocked site)</a></li>
                </ul>
                
                <h2>Content Sections</h2>
                <p>We provide comprehensive web development services including:</p>
                <ul>
                    <li>Frontend development with modern frameworks</li>
                    <li>Backend API development</li>
                    <li>Database design and optimization</li>
                    <li>Cloud deployment and scaling</li>
                </ul>
                
                <p>Last updated: 2025-06-08</p>
            </body>
            </html>
            """
            
        elif path == "/about":
            content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>About Us - Normal Website</title>
            </head>
            <body>
                <h1>About Normal Website</h1>
                <p>We are a technology company focused on web development.</p>
                <p>Founded in 2020, we have grown to serve clients worldwide.</p>
                
                <h2>Our Mission</h2>
                <p>To provide high-quality web development services that help businesses succeed online.</p>
                
                <h2>Our Team</h2>
                <p>We have experienced developers, designers, and project managers.</p>
                
                <nav>
                    <a href="/">Home</a> | 
                    <a href="/services">Services</a> | 
                    <a href="/contact">Contact</a>
                </nav>
            </body>
            </html>
            """
            
        elif path == "/services":
            content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Services - Normal Website</title>
            </head>
            <body>
                <h1>Our Services</h1>
                
                <h2>Web Development</h2>
                <p>Custom web applications built with modern technologies.</p>
                
                <h2>API Development</h2>
                <p>RESTful APIs and microservices architecture.</p>
                
                <h2>Cloud Services</h2>
                <p>AWS, Azure, and Google Cloud deployment and management.</p>
                
                <h2>Consultation</h2>
                <p>Technical consultation and architecture review.</p>
                
                <nav>
                    <a href="/">Home</a> | 
                    <a href="/about">About</a> | 
                    <a href="/contact">Contact</a>
                </nav>
            </body>
            </html>
            """
            
        elif path == "/contact":
            content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Contact - Normal Website</title>
            </head>
            <body>
                <h1>Contact Us</h1>
                
                <h2>Get in Touch</h2>
                <p>We'd love to hear from you!</p>
                
                <h3>Email</h3>
                <p>contact@normalwebsite.com</p>
                
                <h3>Phone</h3>
                <p>+1 (555) 123-4567</p>
                
                <h3>Office</h3>
                <p>123 Tech Street<br>
                San Francisco, CA 94105</p>
                
                <nav>
                    <a href="/">Home</a> | 
                    <a href="/about">About</a> | 
                    <a href="/services">Services</a>
                </nav>
            </body>
            </html>
            """
            
        else:
            self.send_error(404, f"Page not found: {path}")
            return
        
        # Send response
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_header('Content-Length', str(len(content.encode('utf-8'))))
        self.send_header('Last-Modified', 'Wed, 08 Jun 2025 12:00:00 GMT')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))
    
    def serve_geo_blocked_site(self, path):
        """Serve the geo-blocked website (port 8002)"""
        
        if path == "/" or path == "/index.html":
            content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Geo-Blocked Website</title>
            </head>
            <body>
                <h1>Access Restricted</h1>
                <div style="background-color: #ffebee; padding: 20px; border: 1px solid #f44336; border-radius: 5px;">
                    <h2>Your location not permitted</h2>
                    <p>We're sorry, but access to this content is not available in your region due to licensing restrictions.</p>
                    <p>This service is only available to users in certain geographic locations.</p>
                </div>
                
                <h3>Why am I seeing this message?</h3>
                <p>Content availability varies by region due to licensing agreements and local regulations.</p>
                
                <p>Error Code: GEO_BLOCK_001</p>
                <p>Timestamp: 2025-06-08 12:00:00 UTC</p>
            </body>
            </html>
            """
            
        elif path == "/about":
            content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>About - Geo-Blocked Website</title>
            </head>
            <body>
                <h1>About Our Service</h1>
                <p>This is a premium content service with geographic restrictions.</p>
                
                <div style="background-color: #fff3e0; padding: 15px; border-left: 4px solid #ff9800;">
                    <strong>Notice:</strong> Content not available in your country due to licensing agreements.
                </div>
                
                <p>We provide exclusive content to users in select regions.</p>
                <p>Your location not permitted for this content.</p>
                
                <nav>
                    <a href="/">Home</a> | 
                    <a href="/premium">Premium Content</a>
                </nav>
            </body>
            </html>
            """
            
        elif path == "/premium":
            content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Premium Content - Geo-Blocked Website</title>
            </head>
            <body>
                <h1>Premium Content Area</h1>
                
                <div style="background-color: #ffebee; padding: 20px; border: 2px solid #f44336;">
                    <h2>⛔ Access Denied</h2>
                    <p><strong>Your location not permitted</strong> to access this premium content.</p>
                    <p>This content is geo-blocked and only available in certain regions.</p>
                </div>
                
                <h3>Available Regions</h3>
                <ul>
                    <li>United States</li>
                    <li>Canada</li>
                    <li>United Kingdom</li>
                </ul>
                
                <p>Please contact support if you believe this is an error.</p>
                
                <nav>
                    <a href="/">Home</a> | 
                    <a href="/about">About</a>
                </nav>
            </body>
            </html>
            """
            
        else:
            # Default geo-blocked response for unknown paths
            content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Access Restricted</title>
            </head>
            <body>
                <h1>Content Not Available</h1>
                <p>Your location not permitted to access this resource.</p>
                <p>This content is restricted in your geographic region.</p>
            </body>
            </html>
            """
        
        # Send response
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_header('Content-Length', str(len(content.encode('utf-8'))))
        self.send_header('Last-Modified', 'Wed, 08 Jun 2025 12:00:00 GMT')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))


class TestServerManager:
    """Manages test web servers"""
    
    def __init__(self):
        self.servers = []
        self.threads = []
        
    def start_servers(self):
        """Start both test servers"""
        print("🚀 Starting test web servers...")
        
        # Start normal website on port 8001
        normal_server = HTTPServer(('localhost', 8001), MockWebsiteHandler)
        normal_thread = threading.Thread(target=normal_server.serve_forever)
        normal_thread.daemon = True
        normal_thread.start()
        
        self.servers.append(normal_server)
        self.threads.append(normal_thread)
        
        # Start geo-blocked website on port 8002
        geo_server = HTTPServer(('localhost', 8002), MockWebsiteHandler)
        geo_thread = threading.Thread(target=geo_server.serve_forever)
        geo_thread.daemon = True
        geo_thread.start()
        
        self.servers.append(geo_server)
        self.threads.append(geo_thread)
        
        print("✅ Normal website running on: http://localhost:8001")
        print("✅ Geo-blocked website running on: http://localhost:8002")
        print()
        
        # Wait a moment for servers to start
        time.sleep(1)
        
        # Test server connectivity
        self.test_server_connectivity()
        
    def test_server_connectivity(self):
        """Test that servers are responding"""
        import requests
        
        try:
            # Test normal site
            response = requests.get('http://localhost:8001/', timeout=5)
            if response.status_code == 200:
                print("✅ Normal website responding correctly")
            else:
                print(f"⚠️ Normal website returned status {response.status_code}")
                
            # Test geo-blocked site
            response = requests.get('http://localhost:8002/', timeout=5)
            if response.status_code == 200 and 'location not permitted' in response.text.lower():
                print("✅ Geo-blocked website responding with geo-block message")
            else:
                print(f"⚠️ Geo-blocked website not responding as expected")
                
        except Exception as e:
            print(f"❌ Server connectivity test failed: {e}")
    
    def stop_servers(self):
        """Stop all test servers"""
        print("\n🛑 Stopping test servers...")
        for server in self.servers:
            server.shutdown()
            server.server_close()
        print("✅ Test servers stopped")
    
    def get_test_urls(self):
        """Get list of URLs for testing"""
        return [
            # Normal website URLs
            'http://localhost:8001/',
            'http://localhost:8001/about',
            'http://localhost:8001/services',
            'http://localhost:8001/contact',
            
            # Geo-blocked website URLs
            'http://localhost:8002/',
            'http://localhost:8002/about',
            'http://localhost:8002/premium'
        ]


def create_test_urls_file():
    """Create a test URLs file"""
    manager = TestServerManager()
    urls = manager.get_test_urls()
    
    test_urls_file = Path('test_urls.txt')
    with open(test_urls_file, 'w') as f:
        for url in urls:
            f.write(f"{url}\n")
    
    print(f"📝 Created test URLs file: {test_urls_file}")
    print(f"   Contains {len(urls)} test URLs")
    return test_urls_file


def main():
    """Main function to run test setup"""
    print("🧪 Test Website Setup for Hybrid Crawler")
    print("=" * 50)
    
    try:
        # Create test server manager
        manager = TestServerManager()
        
        # Start servers
        manager.start_servers()
        
        # Create test URLs file
        test_urls_file = create_test_urls_file()
        
        print("\n📋 Test Setup Complete!")
        print("=" * 30)
        print("Normal Website (Local crawling should work):")
        print("  - http://localhost:8001/ (Home page)")
        print("  - http://localhost:8001/about (About page)")
        print("  - http://localhost:8001/services (Services page)")
        print("  - http://localhost:8001/contact (Contact page)")
        print()
        print("Geo-blocked Website (Should trigger Lambda fallback):")
        print("  - http://localhost:8002/ (Geo-blocked home)")
        print("  - http://localhost:8002/about (Geo-blocked about)")
        print("  - http://localhost:8002/premium (Geo-blocked premium)")
        print()
        print("🚀 Ready to test hybrid crawler!")
        print("Run this command to test:")
        print(f"   python3 hybrid_crawler.py --urls {test_urls_file} --workers 3")
        print()
        print("Expected behavior:")
        print("  ✅ localhost:8001 URLs → Local crawling (fast)")
        print("  🔄 localhost:8002 URLs → Lambda fallback (geo-blocked detected)")
        print()
        print("Press Ctrl+C to stop servers...")
        
        # Keep servers running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'manager' in locals():
            manager.stop_servers()


if __name__ == "__main__":
    main()