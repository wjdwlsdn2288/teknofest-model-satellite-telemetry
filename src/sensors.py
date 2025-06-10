import asyncio
import queue
import random
import threading
import time
from typing import Any, Dict, Optional
import serial
import pigpio
import websockets
import RPi.GPIO as GPIO
import busio
import board
import adafruit_bmp3xx
import adafruit_bno055
import adafruit_tmp117
from adafruit_ds3231 import DS3231
from .config import Config
from .utils import setup_logger

class Sensor:
    """Base class for all sensors."""
    def __init__(self, name: str, use_test: bool = Config.USE_TEST, delay_time: float = Config.DELAY_TIME):
        self.name = name
        self.use_test = use_test
        self.delay_time = delay_time
        self.queue = queue.Queue()
        self.active = False
        self.thread = None
        self.stop_event = threading.Event()
        self.logger = setup_logger()

    def log(self, message: str, level: str = "info") -> None:
        """Log a message with the specified level."""
        log_function = getattr(self.logger, level.lower(), self.logger.info)
        log_entry = f"{self.name} | {message}"
        log_function(log_entry)

    @staticmethod
    def put_data_in_queue(data_queue: queue.Queue, data: Any) -> None:
        """Clear and put data into the queue."""
        with data_queue.mutex:
            data_queue.queue.clear()
        data_queue.put(data)

    def worker(self) -> None:
        """Abstract method for sensor data collection."""
        raise NotImplementedError("Sensor subclass must implement the worker method.")

    def start(self) -> None:
        """Start the sensor thread."""
        if not self.active:
            self.active = True
            self.stop_event.clear()
            self.thread = threading.Thread(target=self.worker)
            self.thread.start()
            self.log("Sensor started", "info")

    def stop(self) -> None:
        """Stop the sensor thread."""
        self.log("Stopping Sensor", "info")
        if self.active:
            self.active = False
            self.queue.queue.clear()
            self.stop_event.set()
            if self.thread:
                self.thread.join()
            self.log("Sensor stopped", "info")

class BMP390Sensor(Sensor):
    """Sensor for BMP390 pressure and altitude data."""
    def __init__(self, name: str, use_test: bool = Config.USE_TEST, delay_time: float = Config.DELAY_TIME):
        super().__init__(name, use_test, delay_time)
        self.initial_pressure = None
        self.initial_altitude = 0
        if not use_test:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            self.bmp = adafruit_bmp3xx.BMP3XX_I2C(self.i2c)
        self.load_initial_pressure()

    def load_initial_pressure(self) -> None:
        """Load initial pressure from file."""
        try:
            if Config.PACKET_COUNT_FILE.exists():
                with open(Config.PACKET_COUNT_FILE, "r") as f:
                    content = f.read().strip().split(",")
                    if len(content) > 1 and float(content[1]) != 0:
                        self.initial_pressure = float(content[1])
                        self.log(f"Loaded initial pressure: {self.initial_pressure}", "info")
                    else:
                        self.log("Initial pressure is 0, using default behavior.", "info")
            else:
                self.log("Initial pressure file not found.", "info")
        except Exception as e:
            self.log(f"Error loading initial pressure: {e}", "error")

    def get_pressure(self) -> Optional[float]:
        """Get pressure reading from BMP390."""
        try:
            return self.bmp.pressure * 100
        except Exception as e:
            self.log(f"Error getting pressure: {e}", "error")
            return None

    def get_pressure_test(self) -> Optional[float]:
        """Generate random pressure for testing."""
        try:
            return random.uniform(900, 1100)
        except Exception as e:
            self.log(f"Error generating random pressure: {e}", "error")
            return None

    def get_altitude(self, pressure: float) -> Optional[float]:
        """Calculate altitude based on pressure."""
        try:
            if self.initial_pressure is None:
                self.initial_pressure = pressure
            return 44307.7 * (1 - (pressure / self.initial_pressure) ** 0.190284)
        except Exception as e:
            self.log(f"Error calculating altitude: {e}", "error")
            return None

    def get_altitude_test(self) -> float:
        """Generate random altitude for testing."""
        if not hasattr(self, 'pressure_passed'):
            self.pressure_passed = self.initial_pressure >= 600
        self.initial_altitude += random.uniform(-40, 40) if not self.pressure_passed else max(0, self.initial_altitude - random.uniform(30, 40))
        return round(self.initial_altitude, 2)

    def worker(self) -> None:
        """Collect pressure and altitude data."""
        while not self.stop_event.is_set():
            try:
                pressure = self.get_pressure_test() if self.use_test else self.get_pressure()
                altitude = self.get_altitude_test() if self.use_test else self.get_altitude(pressure)
                if pressure is not None:
                    self.put_data_in_queue(PRESSURE_QUEUE, round(pressure, 2))
                if altitude is not None:
                    self.put_data_in_queue(ALTITUDE_QUEUE, round(altitude, 2))
                time.sleep(self.delay_time)
            except Exception as e:
                self.log(f"Error in worker: {e}", "error")

class TMP117Sensor(Sensor):
    """Sensor for TMP117 temperature data."""
    def __init__(self, name: str, use_test: bool = Config.USE_TEST, delay_time: float = Config.DELAY_TIME):
        super().__init__(name, use_test, delay_time)
        self.tmp117 = None
        if not use_test:
            try:
                self.i2c = busio.I2C(board.SCL, board.SDA)
                self.tmp117 = adafruit_tmp117.TMP117(self.i2c, address=0x48)
            except Exception as e:
                self.log(f"Error initializing TMP117: {e}", "error")

    def get_temperature(self) -> Optional[float]:
        """Get temperature reading from TMP117."""
        if self.tmp117 is None:
            self.log("TMP117 not initialized.", "error")
            return None
        try:
            return self.tmp117.temperature
        except Exception as e:
            self.log(f"Error getting temperature: {e}", "error")
            return None

    def get_temperature_test(self) -> Optional[float]:
        """Generate random temperature for testing."""
        try:
            return random.uniform(-20, 40)
        except Exception as e:
            self.log(f"Error generating random temperature: {e}", "error")
            return None

    def worker(self) -> None:
        """Collect temperature data."""
        while not self.stop_event.is_set():
            try:
                temperature = self.get_temperature_test() if self.use_test else self.get_temperature()
                if temperature is not None:
                    self.put_data_in_queue(TEMPERATURE_QUEUE, round(temperature, 2))
                time.sleep(self.delay_time)
            except Exception as e:
                self.log(f"Error in worker: {e}", "error")

class RP2040(Sensor):
    """Sensor for RP2040 data including pressure, GPS, and battery voltage."""
    def __init__(self, name: str, serial_manager: 'SerialManager', use_test: bool = Config.USE_TEST, delay_time: float = Config.DELAY_TIME):
        super().__init__(name, use_test, delay_time)
        self.serial_manager = serial_manager
        self.initial_pressure = None
        self.initial_altitude = 0
        self.load_initial_pressure()

    def load_initial_pressure(self) -> None:
        """Load initial pressure from file."""
        try:
            if Config.PACKET_COUNT_FILE.exists():
                with open(Config.PACKET_COUNT_FILE, "r") as f:
                    content = f.read().strip().split(",")
                    if len(content) > 2 and float(content[2]) != 0:
                        self.initial_pressure = float(content[2])
                        self.log(f"Loaded initial pressure: {self.initial_pressure}", "info")
                    else:
                        self.log("Initial pressure is 0, using default behavior.", "info")
            else:
                self.log("Initial pressure file not found.", "info")
        except Exception as e:
            self.log(f"Error loading initial pressure: {e}", "error")

    def get_rp2040_data(self) -> Optional[Dict]:
        """Get data from RP2040 via serial."""
        try:
            data = self.serial_manager.read_data()
            if not data:
                return None
            data = data.split(",")
            pressure = float(data[0]) if data[0] else 0
            if self.initial_pressure is None and pressure > 0:
                self.initial_pressure = pressure
            altitude = 44307.7 * (1 - (pressure / self.initial_pressure) ** 0.190284) if self.initial_pressure else 0
            return {
                "Pressure2": round(pressure, 2),
                "GPS": {"Latitude": data[1], "Longitude": data[2], "Altitude": data[3]},
                "Battery_Voltage": data[4],
                "Altitude2": round(altitude, 2)
            }
        except Exception as e:
            self.log(f"Error getting RP2040 data: {e}", "error")
            return None

    def get_rp2040_data_test(self) -> Dict:
        """Generate test data for RP2040."""
        try:
            self.pressure_passed = self.initial_pressure >= 600
            self.initial_altitude += random.uniform(-40, 40) if not self.pressure_passed else max(0, self.initial_altitude - random.uniform(30, 40))
            return {
                "Pressure2": round(random.uniform(900, 1100), 2),
                "GPS": {
                    "Latitude": round(random.uniform(-90, 90), 6),
                    "Longitude": round(random.uniform(-180, 180), 6),
                    "Altitude": random.uniform(-100, 1000),
                    "Satellite_Status": 0
                },
                "Battery_Voltage": round(random.uniform(3.0, 4.2), 2),
                "Altitude2": round(self.initial_altitude, 2)
            }
        except Exception as e:
            self.log(f"Error generating test data: {e}", "error")
            return {}

    def worker(self) -> None:
        """Collect RP2040 data."""
        while not self.stop_event.is_set():
            try:
                data = self.get_rp2040_data_test() if self.use_test else self.get_rp2040_data()
                if data:
                    self.put_data_in_queue(RP2040_QUEUE, data)
                time.sleep(self.delay_time)
            except Exception as e:
                self.log(f"Error in worker: {e}", "error")

class BNOSensor(Sensor):
    """Sensor for BNO055 orientation data."""
    def __init__(self, name: str, use_test: bool = Config.USE_TEST, delay_time: float = Config.DELAY_TIME):
        super().__init__(name, use_test, delay_time)
        self.bno_sensor = None
        if not use_test:
            try:
                self.i2c = busio.I2C(board.SCL, board.SDA)
                self.bno_sensor = adafruit_bno055.BNO055_I2C(self.i2c, address=0x28)
                self.bno_sensor.mode = 0x0C
                self.log("BNO055 initialized in NDOF mode.", "info")
            except Exception as e:
                self.log(f"Error initializing BNO055: {e}", "error")

    def get_bno(self) -> Optional[Dict]:
        """Get orientation data from BNO055."""
        if self.bno_sensor is None:
            self.log("BNO055 not initialized.", "error")
            return None
        try:
            euler_angles = self.bno_sensor.euler
            if euler_angles is None:
                raise ValueError("No data from BNO055 sensor.")
            return {
                "Roll": round(euler_angles[0], 2),
                "Pitch": round(euler_angles[1], 2),
                "Yaw": round(euler_angles[2], 2)
            }
        except Exception as e:
            self.log(f"Error getting BNO data: {e}", "error")
            return None

    def get_bno_test(self) -> Dict:
        """Generate test orientation data."""
        try:
            return {
                "Roll": round(random.uniform(0, 360), 2),
                "Pitch": round(random.uniform(-90, 90), 2),
                "Yaw": round(random.uniform(-180, 180), 2)
            }
        except Exception as e:
            self.log(f"Error generating test BNO data: {e}", "error")
            return {}

    def worker(self) -> None:
        """Collect BNO055 data."""
        while not self.stop_event.is_set():
            try:
                data = self.get_bno_test() if self.use_test else self.get_bno()
                if data:
                    self.put_data_in_queue(BNO_QUEUE, data)
                time.sleep(self.delay_time)
            except Exception as e:
                self.log(f"Error in worker: {e}", "error")

class IOTDataReceiver(Sensor):
    """Handles IoT data reception via WebSocket."""
    def __init__(self, name: str, serial_manager: 'SerialManager', use_test: bool = Config.USE_TEST, delay_time: float = Config.DELAY_TIME):
        super().__init__(name, use_test, delay_time)
        self.serial_manager = serial_manager
        self.previous_pressure_data = 0

    async def process_command(self, websocket) -> None:
        """Process incoming WebSocket commands."""
        try:
            async for message in websocket:
                iot_data, trigger_burnwire = message.strip().split(",")
                self.log(f"Received: {iot_data}, {trigger_burnwire}")
                if trigger_burnwire.lower() == "true":
                    self.log("Burning!")
                    self.serial_manager.write_data("a")
                    self.log("Burnt Manually!")
                await self.handle_command(iot_data)
        except Exception as e:
            self.log(f"Error in WebSocket: {e}", "error")

    async def handle_command(self, message: str) -> None:
        """Handle IoT command and update queue."""
        self.put_data_in_queue(IOT_DATA_QUEUE, message)
        self.previous_pressure_data = message

    async def periodic_check(self) -> None:
        """Periodically update queue with previous data if empty."""
        while not self.stop_event.is_set():
            await asyncio.sleep(1)
            if IOT_DATA_QUEUE.empty():
                self.put_data_in_queue(IOT_DATA_QUEUE, self.previous_pressure_data)

    async def serve(self) -> None:
        """Start WebSocket server for IoT data."""
        try:
            async with websockets.serve(self.process_command, Config.FLASK_HOST, Config.IOT_PORT):
                self.log(f"IOTDataReceiver WebSocket server started at {Config.FLASK_HOST}:{Config.IOT_PORT}")
                await asyncio.Event().wait()
        except Exception as e:
            self.log(f"Error in WebSocket server: {e}", "error")

    def worker(self) -> None:
        """Run IoT WebSocket server and periodic check."""
        asyncio.run(asyncio.gather(self.serve(), self.periodic_check()))

class MechFilterServer(Sensor):
    """Manages mechanical filter servo control."""
    def __init__(self, name: str, use_test: bool = Config.USE_TEST, delay_time: float = Config.DELAY_TIME):
        super().__init__(name, use_test, delay_time)
        self.dyaus = pigpio.pi()
        if not self.dyaus.connected:
            raise RuntimeError("Failed to connect to pigpio daemon.")
        self.angle = 0
        self.target_angle = 0
        self.returning_to_neutral = False
        self.neutral_reached = False
        self.last_error = 0
        self.integral = 0
        self.t_high = 0
        self.t_low = 0
        self.last_tick = 0
        self.direction = 1
        self.setup_servo()
        self.feedback_thread = threading.Thread(target=self.feedback360)
        self.control_thread = threading.Thread(target=self.control360)
        self.feedback_thread.start()
        self.control_thread.start()

    def setup_servo(self) -> None:
        """Initialize servo pins and settings."""
        self.dyaus.set_mode(Config.CONTROL_PIN, pigpio.OUTPUT)
        self.dyaus.set_mode(Config.FEEDBACK_PIN, pigpio.INPUT)
        self.dyaus.set_PWM_range(Config.CONTROL_PIN, 3000)
        self.dyaus.callback(Config.FEEDBACK_PIN, pigpio.EITHER_EDGE, self.cbf)

    def cbf(self, gpio: int, level: int, tick: int) -> None:
        """Callback for servo feedback."""
        if level == 1:
            self.t_low = pigpio.tickDiff(self.last_tick, tick)
            self.last_tick = tick
        elif level == 0:
            self.t_high = pigpio.tickDiff(self.last_tick, tick)
            self.last_tick = tick

    def feedback360(self) -> None:
        """Read servo feedback for angle calculation."""
        turns = 0
        theta_p = 0
        while not self.stop_event.is_set():
            t_cycle = self.t_high + self.t_low
            if 1000 < t_cycle < 1200:
                dc = (Config.DUTY_SCALE * self.t_high) / t_cycle
                theta = (Config.UNITS_FULL_CIRCLE - 1) - ((dc - Config.DC_MIN) * Config.UNITS_FULL_CIRCLE) / (
                        Config.DC_MAX - Config.DC_MIN + 1)
                theta = max(0, min(Config.UNITS_FULL_CIRCLE - 1, theta))
                if theta < Config.Q2_MIN and theta_p > Config.Q3_MAX:
                    turns += 1
                elif theta_p < Config.Q2_MIN and theta > Config.Q3_MAX:
                    turns -= 1
                self.angle = turns * Config.UNITS_FULL_CIRCLE + theta if turns >= 0 else ((turns + 1) * Config.UNITS_FULL_CIRCLE) - (Config.UNITS_FULL_CIRCLE - theta)
                theta_p = theta
            time.sleep(0.01)

    def control360(self) -> None:
        """Control servo movement."""
        while not self.stop_event.is_set():
            if self.neutral_reached:
                continue
            error = self.target_angle - self.angle
            if abs(error) < Config.DEADBAND:
                if self.returning_to_neutral:
                    self.returning_to_neutral = False
                    self.neutral_reached = True
                    self.dyaus.set_servo_pulsewidth(Config.CONTROL_PIN, 1500)
                    continue
            proportional = 0.75 * error
            self.integral = max(-200, min(200, self.integral + 0 * error))
            servo_pulse = max(1000, min(2000, 1500 + int(proportional + self.integral)))
            self.dyaus.set_servo_pulsewidth(Config.CONTROL_PIN, servo_pulse)
            time.sleep(0.02)

    def move_servo_90_degrees(self) -> None:
        """Move servo by 90 degrees."""
        self.neutral_reached = False
        self.target_angle += 90 if self.direction == 1 else -90

    def return_to_neutral(self) -> None:
        """Return servo to neutral position."""
        self.neutral_reached = False
        current_angle = self.angle % Config.UNITS_FULL_CIRCLE
        self.target_angle = self.angle + (360 - current_angle) if self.direction == 1 else self.angle - current_angle
        self.returning_to_neutral = True

    async def process_command(self, websocket) -> None:
        """Process WebSocket commands for servo control."""
        try:
            async for message in websocket:
                await self.handle_command(message.strip())
        except Exception as e:
            self.log(f"Error in WebSocket: {e}", "error")

    async def handle_command(self, command: str) -> None:
        """Handle servo control commands."""
        if len(command) != 4:
            return
        duration1, filter_color_1, duration2, filter_color_2 = command[0], command[1], command[2], command[3]
        self.put_data_in_queue(MECH_FILTER_QUEUE, command)
        if not self.use_test:
            await self.rotate_servo(int(duration1), filter_color_1)
            self.return_to_neutral()
            await self.rotate_servo(int(duration2), filter_color_2)
            self.return_to_neutral()
        else:
            self.log(f"Test mode: Data received - {command}")

    async def rotate_servo(self, duration: float, filter_color: str) -> None:
        """Rotate servo based on filter color."""
        rotations = {'R': 1, 'G': 2, 'B': 3}
        for _ in range(rotations.get(filter_color, 0)):
            self.move_servo_90_degrees()
        await asyncio.sleep(duration)

    async def serve(self) -> None:
        """Start WebSocket server for servo control."""
        try:
            async with websockets.serve(self.process_command, Config.FLASK_HOST, Config.MECH_FILTER_PORT):
                self.log(f"MechFilterServer WebSocket started at {Config.FLASK_HOST}:{Config.MECH_FILTER_PORT}")
                await asyncio.Event().wait()
        except Exception as e:
            self.log(f"Error in WebSocket server: {e}", "error")

    @staticmethod
    async def periodic_check() -> None:
        """Periodically update queue with default data if empty."""
        while True:
            await asyncio.sleep(1)
            if MECH_FILTER_QUEUE.empty():
                MECH_FILTER_QUEUE.put("0N0N")

    def worker(self) -> None:
        """Run servo WebSocket server and periodic check."""
        asyncio.run(asyncio.gather(self.serve(), self.periodic_check()))

class SerialManager:
    """Manages serial communication."""
    def __init__(self, port: str = Config.SERIAL_PORT, baudrate: int = Config.BAUDRATE, timeout: int = Config.TIMEOUT):
        self.serial_port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.connection = None
        self.logger = setup_logger()

    def connect(self) -> None:
        """Establish serial connection."""
        if self.connection is None or not self.connection.is_open:
            try:
                self.connection = serial.Serial(self.serial_port, baudrate=self.baudrate, timeout=self.timeout)
                self.logger.info(f"Connected to {self.serial_port} at {self.baudrate} baud.")
            except serial.SerialException as e:
                self.logger.error(f"Failed to connect to {self.serial_port}: {e}")
                self.connection = None

    def disconnect(self) -> None:
        """Close serial connection."""
        if self.connection and self.connection.is_open:
            self.connection.close()
            self.logger.info(f"Disconnected from {self.serial_port}")
            self.connection = None

    def read_data(self) -> Optional[str]:
        """Read data from serial port."""
        if self.connection and self.connection.is_open:
            try:
                data = self.connection.readline().decode('utf-8', errors='ignore').strip()
                if not data:
                    self.logger.warning("No data received from serial.")
                return data
            except serial.SerialException as e:
                self.logger.error(f"Error reading from {self.serial_port}: {e}")
                return None
        raise ConnectionError("Serial connection is not established.")

    def write_data(self, data: str) -> None:
        """Write data to serial port."""
        if self.connection and self.connection.is_open:
            try:
                self.connection.write(data.encode('utf-8'))
                self.logger.info(f"Writing data: {data}")
            except serial.SerialException as e:
                self.logger.error(f"Error writing to {self.serial_port}: {e}")
        else:
            raise ConnectionError("Serial connection is not established.")