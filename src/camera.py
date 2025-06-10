import asyncio
import io
import logging
import socketserver
from http import server
from threading import Condition, Thread
import picamera
from .config import Config
from .utils import setup_logger

PAGE = """\
<html>
<head>
<title>Raspberry Pi - Surveillance Camera</title>
</head>
<body>
<center><h1>Raspberry Pi - Surveillance Camera</h1></center>
<center><img src="stream.mjpg" width="640" height="480"></center>
</body>
</html>
"""

class StreamingOutput:
    """Handles MJPEG frame buffering for streaming."""
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()
        self.logger = setup_logger()

    def write(self, buf):
        """Write frame data to buffer and notify clients."""
        try:
            if buf.startswith(b'\xff\xd8'):
                self.buffer.truncate()
                with self.condition:
                    self.frame = self.buffer.getvalue()
                    self.condition.notify_all()
                self.buffer.seek(0)
            return self.buffer.write(buf)
        except Exception as e:
            self.logger.error(f"Error writing to buffer: {e}")
            return 0

class StreamingHandler(server.BaseHTTPRequestHandler):
    """Handles HTTP requests for camera streaming."""
    def do_GET(self):
        output = self.server.output
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/stream.mjpg')
            self.end_headers()
        elif self.path == '/index.html':
            content = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                output.logger.warning(f"Removed streaming client {self.client_address}: {e}")
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    """HTTP server for MJPEG streaming."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler_class, output):
        super().__init__(server_address, handler_class)
        self.output = output

class CameraService:
    """Manages Raspberry Pi camera streaming."""
    def __init__(self):
        self.logger = setup_logger()
        self.output = StreamingOutput()
        self.server = None
        self.server_thread = None
        self.camera = None
        self.running = False

    def start(self):
        """Start the camera streaming service."""
        if not self.running:
            self.running = True
            self.server_thread = Thread(target=self._run)
            self.server_thread.start()
            self.logger.info("Camera streaming started")

    def stop(self):
        """Stop the camera streaming service."""
        if self.running:
            self.running = False
            if hasattr(self.camera, 'recording'):
                self.camera.stop_recording()
            if self.server:
                self.server.shutdown()
            if self.server_thread:
                self.server_thread.join()
            self.logger.info("Camera streaming stopped")

    def _run(self):
        """Run the camera streaming logic."""
        try:
            with picamera.PiCamera(resolution=Config.CAMERA_RESOLUTION, framerate=Config.CAMERA_FRAMERATE) as camera:
                self.camera = camera
                camera.start_recording(self.output, format='mjpeg')
                address = ('', Config.CAMERA_PORT)
                self.server = StreamingServer(address, StreamingHandler, self.output)
                self.logger.info(f"Camera server started at http://{Config.FLASK_HOST}:{Config.CAMERA_PORT}")
                self.server.serve_forever()
        except Exception as e:
            self.logger.error(f"Error in camera streaming: {e}")
        finally:
            if self.camera and hasattr(self.camera, 'recording'):
                self.camera.stop_recording()
            if self.server:
                self.server.server_close()