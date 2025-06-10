import logging
import csv
import shutil
import time
from pathlib import Path
from typing import Any, List, Optional
from .config import Config

def setup_logger(log_file: str = Config.LOG_FILE) -> logging.Logger:
    """Set up and configure the logger."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger

class BlackboxCSV:
    """Manages CSV file operations for telemetry data."""
    def __init__(self, rtc_time: Any = None):
        self.folder_path = Config.BASE_DIR
        self.folder_path.mkdir(parents=True, exist_ok=True)
        (self.folder_path / "Packet Count Files").mkdir(parents=True, exist_ok=True)
        self.logger = setup_logger()
        timestamp = self._get_timestamp(rtc_time)
        
        if Config.PACKET_COUNT_FILE.exists():
            with open(Config.PACKET_COUNT_FILE, "r") as f:
                check_contents = f.read().strip().split(",")
            if len(check_contents) == 4:
                self.logger.info("Skipping CSV backup due to detected restart.")
                return
        self.backup_file(Config.CSV_FILE.name, Config.BACKUP_DIR.name, timestamp)

    def write_csv(self, raw_data: str, filename: str = Config.CSV_FILE.name) -> None:
        """Write telemetry data to CSV file."""
        file_path = self.folder_path / filename
        header = [
            'Packet_Count', 'Satellite_Status', 'Error_Code', 'Mission_Time', 'Pressure1', 'Pressure2',
            'Altitude1', 'Altitude2', 'Altitude_Difference', 'Descent_Rate', 'Temperature', 'Battery_Voltage',
            'Gps_Latitude', 'Gps_Longitude', 'Gps_Altitude', 'Pitch', 'Roll', 'Yaw', 'LNLN', 'IOT_Data',
            'Team_Number'
        ]

        try:
            with file_path.open("a", newline="") as f:
                writer = csv.writer(f, delimiter=",")
                if not file_path.exists():
                    writer.writerow(header)
                writer.writerow(raw_data.split(','))
        except OSError as e:
            self.logger.error(f"OS error writing to CSV: {e}")
        except Exception as e:
            self.logger.error(f"Error writing to CSV: {e}")

    def backup_file(self, filename: str, backup_folder_name: str, timestamp: str) -> None:
        """Create a backup of the specified file."""
        file_path = self.folder_path / filename
        if not file_path.exists():
            self.logger.info(f"File {filename} does not exist. Skipping backup.")
            return

        backup_folder = self.folder_path / backup_folder_name
        backup_folder.mkdir(parents=True, exist_ok=True)
        new_file_name = f"{timestamp}_{filename}"
        
        try:
            shutil.copy(file_path, backup_folder / new_file_name)
            file_path.unlink()
            self.logger.info(f"Backup created: {backup_folder / new_file_name}")
        except Exception as e:
            self.logger.error(f"Error creating backup for {filename}: {e}")

    @staticmethod
    def _get_timestamp(rtc_time: Any) -> str:
        """Generate a timestamp string from RTC or local time."""
        try:
            t = rtc_time.datetime if hasattr(rtc_time, 'datetime') else rtc_time or time.localtime()
            return f"{t.tm_mday}_{t.tm_mon}_{t.tm_year}_{t.tm_hour}_{t.tm_min}_{t.tm_sec}"
        except Exception as e:
            logger = setup_logger()
            logger.error(f"Error generating timestamp: {e}")
            return time.strftime("%d_%m_%Y_%H_%M_%S")