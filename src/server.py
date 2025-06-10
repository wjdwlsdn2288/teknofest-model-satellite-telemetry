import asyncio
import json
import time
import queue
import threading
import websockets
from flask import Flask, Response, send_from_directory, jsonify, render_template
from adafruit_ds3231 import DS3231
import busio
import board
import RPi.GPIO as GPIO
from .config import Config
from .utils import BlackboxCSV, setup_logger
from .sensors import Sensor

class DataTransmitter(Sensor):
    """Transmits sensor data via WebSocket."""
    def __init__(self, name: str, use_test: bool = Config.USE_TEST, delay_time: float = Config.DELAY_TIME, *queues):
        super().__init__(name, use_test, delay_time)
        self.rtc = time.localtime() if use_test else DS3231(busio.I2C(board.SCL, board.SDA))
        self.queues = queues
        self.websocket_clients = set()
        self.current_state = Config.FSW_STATE['READY_TO_FLIGHT']
        self.csv_data = BlackboxCSV(self.rtc)
        self.packet_count = 0
        self.previous_roll = None
        self.alarm_codes = None
        self.Recovery_Time = None
        self.load_packet_count()

    def load_packet_count(self) -> None:
        """Load packet count from file."""
        try:
            if Config.PACKET_COUNT_FILE.exists():
                with open(Config.PACKET_COUNT_FILE, "r") as f:
                    data = f.read().strip().split(",")
                    if len(data) >= 4:
                        self.current_state = int(data[3])
                        self.packet_count = int(data[0])
                        self.log(f"Loaded Packet Count: {self.packet_count}", "info")
            else:
                self.log("Packet count file not found.", "info")
        except Exception as e:
            self.log(f"Error loading packet count: {e}", "error")

    async def handle_connection(self, websocket) -> None:
        """Handle WebSocket client connections."""
        self.websocket_clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            self.websocket_clients.remove(websocket)

    async def transmit_data(self) -> None:
        """Transmit sensor data to connected clients."""
        while not self.stop_event.is_set():
            try:
                data = {"Packet": self.packet_count}
                for sensor_name, sensor_queue in zip(Config.SENSOR_NAMES, self.queues):
                    try:
                        data[sensor_name] = sensor_queue.get_nowait()
                    except queue.Empty:
                        self.log(f"No data in queue for {sensor_name}", "warning")
                
                if self.packet_count == 0:
                    self.save_to_file([data.get("Packet"), data.get("Pressure1"),
                                       data.get("RP2040_Data", {}).get("Pressure2"), self.current_state])
                
                self.alarm_codes, descent_rate = update_alarm_code(data, self.current_state)
                data["Descent_Rate"] = round(descent_rate, 2) if descent_rate else None
                t = self.rtc.datetime if hasattr(self.rtc, 'datetime') else self.rtc
                data["Mission_Time"] = f"{t.tm_mday}/{t.tm_mon}/{t.tm_year}; {t.tm_hour}:{t.tm_min}:{t.tm_sec}"
                data["Altitude_Difference"] = round(abs(data.get("Altitude1", 0) - data.get("RP2040_Data", {}).get("Altitude2", 0)), 2)
                data["Error_Codes"] = ''.join(map(str, self.alarm_codes)) if self.alarm_codes else ""
                
                current_roll = data.get("BNO", {}).get("Roll")
                roll_diff = abs(self.previous_roll - current_roll) if self.previous_roll is not None and current_roll is not None else None
                self.previous_roll = current_roll
                
                data["Satellite_Status"] = update_state(self.current_state, data.get("Altitude1"), data.get("Descent_Rate"),
                                                       int(data["Altitude_Difference"] or 0), roll_diff)
                if data["Satellite_Status"] != self.current_state:
                    self.current_state = data["Satellite_Status"]
                
                raw_data_packet_for_csv = [
                    data.get('Packet'), data.get('Satellite_Status'), data.get('Error_Codes'),
                    data.get('Mission_Time'), data.get('Pressure1'), data.get('RP2040_Data', {}).get('Pressure2'),
                    data.get('Altitude1'), data.get('RP2040_Data', {}).get('Altitude2'), data.get('Altitude_Difference'),
                    data.get('Descent_Rate'), data.get('Temperature'), data.get('RP2040_Data', {}).get('Battery_Voltage'),
                    data.get('RP2040_Data', {}).get('GPS', {}).get('Latitude'), data.get('RP2040_Data', {}).get('GPS', {}).get('Longitude'),
                    data.get('RP2040_Data', {}).get('GPS', {}).get('Altitude'), data.get('BNO', {}).get('Pitch'),
                    data.get('BNO', {}).get('Roll'), data.get('BNO', {}).get('Yaw'), data.get("Mech_Filter"), data.get('IOT_Data'), 335592
                ]
                self.csv_data.write_csv(','.join(map(str, raw_data_packet_for_csv)))
                
                if self.current_state == Config.FSW_STATE["RECOVERY"] and not self.Recovery_Time:
                    self.Recovery_Time = time.time() + 30
                if self.Recovery_Time and time.time() >= self.Recovery_Time:
                    await self.send_stop_command()
                
                self.log(f"Data sent: {data}")
                await asyncio.gather(*[self.send_data_to_client(ws, data) for ws in self.websocket_clients])
                self.packet_count += 1
                self.save_to_file([self.packet_count])
                await asyncio.sleep(self.delay_time)
            except Exception as e:
                self.log(f"Error in transmit_data: {e}", "error")

    async def send_data_to_client(self, websocket, data: Dict) -> None:
        """Send data to a WebSocket client."""
        try:
            await websocket.send(json.dumps(data))
        except Exception as e:
            self.log(f"Error sending data to websocket: {e}", "error")
            self.websocket_clients.discard(websocket)

    async def send_stop_command(self) -> None:
        """Send stop command to command receiver."""
        try:
            async with websockets.connect(f"ws://{Config.FLASK_HOST}:{Config.COMMAND_RECEIVER_PORT}") as websocket:
                await websocket.send("stop")
                self.log(f"Sent stop command to ws://{Config.FLASK_HOST}:{Config.COMMAND_RECEIVER_PORT}")
        except Exception as e:
            self.log(f"Error sending stop command: {e}", "error")

    def save_to_file(self, data: List) -> None:
        """Save packet count and initial data to file."""
        try:
            if len(data) == 4:
                with open(Config.PACKET_COUNT_FILE, "w") as f:
                    f.write(','.join(map(str, data)))
            else:
                with open(Config.PACKET_COUNT_FILE, "r") as f:
                    _data = f.read().strip().split(",")
                if len(_data) == 4:
                    _data[0] = str(data[0])
                    with open(Config.PACKET_COUNT_FILE, "w") as f:
                        f.write(','.join(_data))
        except Exception as e:
            self.log(f"Error saving to file: {e}", "error")

    def worker(self) -> None:
        """Run WebSocket server for data transmission."""
        async def serve():
            async with websockets.serve(self.handle_connection, Config.FLASK_HOST, Config.DATA_TRANSMITTER_PORT):
                self.log(f"DataTransmitter WebSocket started at {Config.FLASK_HOST}:{Config.DATA_TRANSMITTER_PORT}")
                await self.transmit_data()
        asyncio.run(serve())

class CommandReceiver(Sensor):
    """Receives and processes commands via WebSocket."""
    def __init__(self, sensors: List[Sensor], buzzer_pin: int = Config.BUZZER_PIN, name: str = "CommandReceiver", use_test: bool = Config.USE_TEST, delay_time: float = Config.DELAY_TIME):
        super().__init__(name, use_test, delay_time)
        self.sensors = sensors
        self.buzzer_pin = buzzer_pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.buzzer_pin, GPIO.OUT)
        self.buzzer_off()
        Config.BASE_DIR.mkdir(parents=True, exist_ok=True)
        (Config.BASE_DIR / "Packet Count Files").mkdir(parents=True, exist_ok=True)
        self.buzzer_blink(1)
        if Config.PACKET_COUNT_FILE.exists():
            self.start_sensors()

    def start_sensors(self) -> None:
        """Start all sensors."""
        self.log("Starting Sensors")
        for sensor in self.sensors:
            sensor.start()

    def stop_sensors(self) -> None:
        """Stop all sensors."""
        self.log("Stopping Sensors")
        for sensor in self.sensors:
            sensor.stop()

    async def process_command(self, websocket, path) -> None:
        """Process incoming WebSocket commands."""
        try:
            async for message in websocket:
                await self.handle_command(message.strip())
        except Exception as e:
            self.log(f"Error in WebSocket: {e}", "error")

    async def handle_command(self, command: str) -> None:
        """Handle received commands."""
        if command == "start":
            self.buzzer_blink(4)
            self.start_sensors()
        elif command == "stop":
            self.stop_sensors()
            self.buzzer_on_indefinitely()
        else:
            self.log(f"Unknown command: {command}", "warning")
            self.buzzer_off()

    def buzzer_blink(self, duration: float) -> None:
        """Blink buzzer for specified duration."""
        end_time = time.time() + duration
        while time.time() < end_time:
            GPIO.output(self.buzzer_pin, GPIO.HIGH)
            time.sleep(0.25)
            GPIO.output(self.buzzer_pin, GPIO.LOW)
            time.sleep(0.25)
        self.log(f"Buzzer blinked for {duration} seconds")

    def buzzer_on_indefinitely(self) -> None:
        """Turn buzzer on indefinitely."""
        GPIO.output(self.buzzer_pin, GPIO.HIGH)
        self.log("Buzzer is ON indefinitely")

    def buzzer_off(self) -> None:
        """Turn buzzer off."""
        GPIO.output(self.buzzer_pin, GPIO.LOW)
        self.log("Buzzer is OFF")

    def worker(self) -> None:
        """Run WebSocket server for command reception."""
        async def run():
            while not self.stop_event.is_set():
                try:
                    async with websockets.serve(self.process_command, Config.FLASK_HOST, Config.COMMAND_RECEIVER_PORT):
                        self.log(f"CommandReceiver WebSocket started at {Config.FLASK_HOST}:{Config.COMMAND_RECEIVER_PORT}")
                        await asyncio.Event().wait()
                except Exception as e:
                    self.log(f"Error in WebSocket server: {e}", "error")
                    await asyncio.sleep(5)
        asyncio.run(run())

def update_state(current_state: int, altitude: float, velocity: float, alt_diff: int, roll_diff: Optional[float]) -> int:
    """Update satellite state based on sensor data."""
    if current_state == Config.FSW_STATE['READY_TO_FLIGHT'] and 10 < int(altitude or 0) < 700:
        return Config.FSW_STATE['ASCENT']
    elif current_state == Config.FSW_STATE['ASCENT'] and int(velocity or 0) < -5 and int(altitude or 0) > 450:
        return Config.FSW_STATE['MODEL_SATELLITE_DESCENT']
    elif current_state == Config.FSW_STATE['MODEL_SATELLITE_DESCENT'] and int(altitude or 0) < 450 and int(alt_diff) > 25:
        return Config.FSW_STATE['RELEASE']
    elif current_state == Config.FSW_STATE['RELEASE'] and int(altitude or 0) < 400 and int(velocity or 0) < -3:
        return Config.FSW_STATE['SCIENCE_PAYLOAD_DESCENT']
    elif current_state == Config.FSW_STATE['SCIENCE_PAYLOAD_DESCENT'] and float(abs(roll_diff or 0)) < 0.2 and int(altitude or 0) < 20:
        return Config.FSW_STATE['RECOVERY']
    return current_state

def update_alarm_code(data: Dict, state: int) -> tuple[List[int], Optional[float]]:
    """Update alarm codes based on sensor data."""
    alarm_codes = [0] * 5
    rp2040_data = data.get("RP2040_Data", {})
    container_altitude = rp2040_data.get("Altitude2")
    container_pressure = rp2040_data.get("Pressure2")
    gps_data = rp2040_data.get("GPS", {})
    science_payload_altitude = data.get("Altitude1")
    altitude_difference = abs(science_payload_altitude - container_altitude) if science_payload_altitude and container_altitude else None
    current_time = time.time()

    if not hasattr(update_alarm_code, "previous_data"):
        update_alarm_code.previous_data = {
            "container_altitude": None, "container_time": None,
            "science_payload_altitude": None, "science_payload_time": None,
            "science_payload_landing_rate": None, "container_landing_rate": None,
            "altitude_difference_checked": False
        }
    previous_data = update_alarm_code.previous_data

    def update_landing_rate(payload_type: str, current_altitude: float, min_rate: float, max_rate: float, alarm_index: int) -> None:
        """Update landing rate and set alarm if out of range."""
        if current_altitude is None:
            return
        prev_altitude = previous_data.get(f"{payload_type}_altitude")
        prev_time = previous_data.get(f"{payload_type}_time")
        if prev_altitude is not None and prev_time is not None:
            time_diff = current_time - prev_time
            if time_diff > 0:
                landing_rate = (current_altitude - prev_altitude) / time_diff
                previous_data[f"{payload_type}_landing_rate"] = landing_rate
                if not (min_rate <= landing_rate <= max_rate):
                    alarm_codes[alarm_index] = 1
        previous_data[f"{payload_type}_altitude"] = current_altitude
        previous_data[f"{payload_type}_time"] = current_time

    update_landing_rate('container', container_altitude, -14, -12, 0)
    update_landing_rate('science_payload', science_payload_altitude, -8, -6, 1)
    if not isinstance(container_pressure, (float, int)) or int(container_pressure or 0) == 0:
        alarm_codes[2] = 1
    if any(gps_data.get(k) in ["0.0000000", None] for k in ["Latitude", "Longitude"]) or gps_data.get("Altitude") in ["0.00", None]:
        alarm_codes[3] = 1
    if not previous_data["altitude_difference_checked"]:
        if state < 3 or (altitude_difference is None or int(altitude_difference) < 25):
            alarm_codes[4] = 1
        else:
            previous_data["altitude_difference_checked"] = True

    return alarm_codes, previous_data.get('science_payload_landing_rate')

app = Flask(__name__)

def generate_log(file_path: str) -> Response:
    """Stream file content for Flask routes."""
    with open(file_path, 'r') as f:
        while True:
            yield f.read()

@app.route('/telemetry.log')
def stream_telemetry_log() -> Response:
    """Stream telemetry log file."""
    return Response(generate_log(Config.LOG_FILE), content_type='text/event-stream')

@app.route('/telemetry.csv')
def stream_telemetry_csv() -> Response:
    """Stream telemetry CSV file."""
    return Response(generate_log(str(Config.CSV_FILE)), content_type='text/event-stream')

@app.route('/packet_count')
def stream_packet_count() -> Response:
    """Stream packet count file."""
    return Response(generate_log(str(Config.PACKET_COUNT_FILE)), content_type='text/event-stream')

@app.route('/media_list')
def list_media() -> Response:
    """List media files in the media directory."""
    files = Config.MEDIA_DIR.glob('*')
    file_list = [{"name": file.name, "url": f"/media/{file.name}"} for file in files]
    return jsonify(file_list)

@app.route('/media/<filename>')
def serve_media(filename: str) -> Response:
    """Serve media files."""
    return send_from_directory(str(Config.MEDIA_DIR), filename)

@app.route('/')
def index() -> Response:
    """Serve the index HTML page."""
    return render_template('index.html')