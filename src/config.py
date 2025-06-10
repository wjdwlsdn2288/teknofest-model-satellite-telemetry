import os
from pathlib import Path

class Config:
    """Centralized configuration for the telemetry and camera streaming system."""
    # General
    LOG_FILE = "/home/dyaus/telemetry.log"
    BASE_DIR = Path("/home/dyaus/335592_BlackBox_RPI")
    PACKET_COUNT_FILE = BASE_DIR / "packet_count.txt"
    CSV_FILE = BASE_DIR / "335592_csv_data.csv"
    BACKUP_DIR = BASE_DIR / "Backup CSV Files"
    TEMPLATES_DIR = Path("/home/dyaus/templates")
    INDEX_HTML_PATH = TEMPLATES_DIR / "index.html"
    MEDIA_DIR = Path("/var/www/335592_Flight/media")
    
    # Sensor settings
    SENSOR_NAMES = ["Pressure1", "Altitude1", "Temperature", "RP2040_Data", "BNO", "IOT_Data", "Mech_Filter"]
    FSW_STATE = {
        'READY_TO_FLIGHT': 0,
        'ASCENT': 1,
        'MODEL_SATELLITE_DESCENT': 2,
        'RELEASE': 3,
        'SCIENCE_PAYLOAD_DESCENT': 4,
        'RECOVERY': 5
    }
    USE_TEST = False
    DELAY_TIME = 0.0
    
    # Serial settings
    SERIAL_PORT = "/dev/serial0"
    BAUDRATE = 115200
    TIMEOUT = 1
    
    # WebSocket ports
    IOT_PORT = 9001
    MECH_FILTER_PORT = 9002
    DATA_TRANSMITTER_PORT = 9003
    COMMAND_RECEIVER_PORT = 9004
    
    # Servo settings
    CONTROL_PIN = 13
    FEEDBACK_PIN = 6
    UNITS_FULL_CIRCLE = 360
    DUTY_SCALE = 1000
    DC_MIN = 29
    DC_MAX = 971
    Q2_MIN = UNITS_FULL_CIRCLE // 4
    Q3_MAX = Q2_MIN * 3
    TURN_THRESHOLD = 4
    DEADBAND = 5
    
    # Buzzer pin
    BUZZER_PIN = 5
    
    # Flask server
    FLASK_HOST = "0.0.0.0"
    FLASK_PORT = 5000
    
    # Camera streaming
    CAMERA_PORT = 8000
    CAMERA_RESOLUTION = '640x480'
    CAMERA_FRAMERATE = 120