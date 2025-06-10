import queue
import threading
import os
from .config import Config
from .sensors import BMP390Sensor, TMP117Sensor, RP2040, BNOSensor, IOTDataReceiver, MechFilterServer, SerialManager
from .server import DataTransmitter, CommandReceiver, app
from .camera import CameraService

# Global queues
PRESSURE_QUEUE = queue.Queue()
ALTITUDE_QUEUE = queue.Queue()
TEMPERATURE_QUEUE = queue.Queue()
RP2040_QUEUE = queue.Queue()
BNO_LOG = queue.Queue()
IOT_DATA_QUEUE = queue.Queue()
MECH_FILTER_QUEUE = queue.Queue()

def create_index_html():
    """Create index.html file if it doesn't exist."""
    Config.TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    if not Config.INDEX_HTML_PATH.exists():
        content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Model Satellite Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { text-align: center; }
        #media-list a { display: block; margin: 5px 0; }
        #camera-feed { display: block; margin: 20px auto; }
    </style>
</head>
<body>
    <h1>Model Satellite Dashboard - Teknofest 2024</h1>
    <h2>Live Camera Feed</h2>
    <img id="camera-feed" src="http://localhost:8000/stream.mjpg" width="640" height="480" alt="Camera Feed">
    <h2>Media Files</h2>
    <div id="media-list"></div>
    <script>
        async function fetchMedia() {
            const response = await fetch('/media_list');
            const files = await response.json();
            const mediaList = document.getElementById('media-list');
            files.forEach(file => {
                const link = document.createElement('a');
                link.href = file.url;
                link.textContent = file.name;
                link.target = '_blank';
                mediaList.appendChild(link);
            });
        }
        window.onload = fetchMedia;
    </script>
</body>
</html>
"""
        with open(Config.INDEX_HTML_PATH, 'w') as f:
            f.write(content)

def main():
    """Initialize and run the telemetry and camera streaming system."""
    create_index_html()
    serial_manager = SerialManager()
    serial_manager.connect()
    
    camera_service = CameraService()
    
    sensors = [
        BMP390Sensor("Pressure1 and Altitude2"),
        TMP117Sensor("Temperature"),
        RP2040("RP2040", serial_manager),
        BNOSensor("BNO"),
        IOTDataReceiver("IOT_Data", serial_manager),
        MechFilterServer("Mech_Filter"),
        DataTransmitter("Data_Transmitter", Config.USE_TEST, Config.DELAY_TIME, 
                        PRESSURE_QUEUE, ALTITUDE_QUEUE, TEMPERATURE_QUEUE, 
                        RP2040_QUEUE, BNO_QUEUE, IOT_DATA_QUEUE, MECH_FILTER_QUEUE)
    ]
    
    command_receiver = CommandReceiver(sensors[:4], name="CommandReceiver")
    
    threads = [threading.Thread(target=sensor.start) for sensor in sensors[4:]] + \
             [threading.Thread(target=command_receiver.worker)] + \
             [threading.Thread(target=app.run, kwargs={'host': Config.FLASK_HOST, 'port': Config.FLASK_PORT})] + \
             [threading.Thread(target=camera_service.start)]
    
    for thread in threads:
        thread.start()
    
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        camera_service.stop()
        command_receiver.stop_sensors()
        for sensor in sensors[4:]:
            sensor.stop()

if __name__ == "__main__":
    main()