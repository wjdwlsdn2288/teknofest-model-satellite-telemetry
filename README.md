# Model Satellite Telemetry and Camera Streaming System

This project is the backend for a GUI developed for the **Model Satellite Competition at Teknofest 2024**. It provides a robust telemetry system for collecting and transmitting sensor data from a Raspberry Pi-based model satellite, along with live video streaming using a Raspberry Pi Camera Module. The system supports multiple sensors (pressure, temperature, orientation, GPS), a mechanical filter servo, and WebSocket communication for real-time data transmission. It was designed to meet the requirements of the Teknofest 2024 competition, ensuring reliable data logging, state management, and video feed for mission monitoring.

## Table of Contents
- [Features](#features)
- [Project Structure](#project-structure)
- [Hardware Requirements](#hardware-requirements)
- [Software Requirements](#software-requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Accessing the System](#accessing-the-system)
- [Contributing](#contributing)
- [License](#license)
- [Links to Frameworks and Boards](#links-to-frameworks-and-boards)
- [Thank You](#thank-you)

## Features
- **Sensor Data Collection**:
  - BMP390 for pressure and altitude
  - TMP117 for temperature
  - BNO055 for orientation (roll, pitch, yaw)
  - RP2040 for secondary pressure, GPS, and battery voltage
- **State Management**: Tracks satellite states (Ready to Flight, Ascent, Descent, Release, Recovery) with alarm codes.
- **WebSocket Servers**: Real-time data transmission and command reception on ports 9001–9004.
- **Flask Server**: Serves media files, telemetry logs, and a dashboard (port 5000).
- **Camera Streaming**: Live MJPEG video feed from Raspberry Pi Camera Module (port 8000).
- **Data Logging**: Stores telemetry data in CSV files with backup functionality.
- **Concurrency**: Uses threading and asyncio for non-blocking operation of sensors, servers, and camera.
- **Test Mode**: Supports simulated sensor data for development and testing.

## Project Structure
```
model-satellite-telemetry/
├── src/
│   ├── __init__.py
│   ├── config.py          # Configuration settings
│   ├── utils.py           # Utility functions (logging, CSV)
│   ├── sensors.py         # Sensor classes
│   ├── server.py          # Flask and WebSocket servers
│   ├── camera.py          # Camera streaming logic
│   └── main.py            # Main execution logic
├── templates/
│   └── index.html         # HTML dashboard with Tailwind CSS
├── install_setup_libraries.sh # Bash script for dependency installation
├── README.md              # Project documentation
├── requirements.txt       # Python dependencies
├── LICENSE                # MIT License
└── .gitignore             # Git ignore file
```

## Hardware Requirements
- **Raspberry Pi**: Raspberry Pi Zero 2W
  - [Raspberry Pi Zero 2W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)
- **Raspberry Pi Camera Module**: For video streaming
  - [Camera Module V2](https://www.raspberrypi.com/products/camera-module-v2/)
- **Sensors**:
  - BMP390 Pressure Sensor ([Adafruit BMP390](https://www.adafruit.com/product/4816))
  - TMP117 Temperature Sensor ([Adafruit TMP117](https://www.adafruit.com/product/4821))
  - BNO055 Orientation Sensor ([Adafruit BNO055](https://www.adafruit.com/product/2472))
  - DS3231 RTC ([Adafruit DS3231](https://www.adafruit.com/product/3013))
- **RP2040 Microcontroller**: For secondary sensor data
  - [Raspberry Pi RP2040](https://www.raspberrypi.com/products/raspberry-pi-pico/)
- **Servo Motor**: For mechanical filter control
  - [Parallax Feedback 360° High Speed Servo](https://www.parallax.com/product/parallax-feedback-360-high-speed-servo/)
- **Buzzer**: Connected to GPIO pin 5
- **SD Card**: 16GB or larger with Raspberry Pi OS
- **Power Supply**: Stable 5V supply for Raspberry Pi and peripherals

## Software Requirements
- **Raspberry Pi OS**: Latest version (Bookworm recommended)
  - [Download](https://www.raspberrypi.com/software/)
- **Python**: 3.9 or later
- **pigpio Daemon**: For servo control
  - [pigpio](http://abyz.me.uk/rpi/pigpio/)
- **Dependencies**: Listed in `requirements.txt`

## Installation
1. **Set Up Raspberry Pi**:
   - Flash Raspberry Pi OS to an SD card using [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
   - Boot the Raspberry Pi and configure Wi-Fi, SSH, and I2C via `raspi-config`.
   - Enable the camera module: `sudo raspi-config` → Interface Options → Camera → Enable.

2. **Install pigpio**:
   ```bash
   sudo apt update
   sudo apt install pigpio
   sudo systemctl enable pigpiod
   sudo systemctl start pigpiod
   ```

3. **Clone the Repository**:
   ```bash
   git clone https://github.com/WhoIsJayD/teknofest-model-satellite-telemetry.git
   cd teknofest-model-satellite-telemetry
   ```

4. **Set Up Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

5. **Install Dependencies**:
   - Option 1: Use the provided Bash script to automate dependency installation:
     ```bash
     chmod +x install_setup_libraries.sh
     ./install_setup_libraries.sh
     ```
   - Option 2: Install manually:
     ```bash
     pip install -r requirements.txt
     ```

6. **Connect Hardware**:
   - Connect sensors to I2C pins (SCL, SDA).
   - Connect RP2040 to serial port (`/dev/serial0`).
   - Connect Parallax Feedback 360° Servo to GPIO pins 13 (control) and 6 (feedback).
   - Connect buzzer to GPIO pin 5.
   - Attach the Raspberry Pi Camera Module.

7. **Configure Permissions**:
   ```bash
   sudo mkdir -p /home/dyaus/335592_BlackBox_RPI
   sudo mkdir -p /var/www/335592_Flight/media
   sudo chown -R pi:pi /home/dyaus /var/www
   sudo chmod -R 755 /home/dyaus /var/www
   ```

8. **Alternative Video Feed Options**:
   - For additional video streaming solutions, consider:
     - [RPi_Cam_Web_Interface](https://github.com/silvanmelchior/RPi_Cam_Web_Interface)
     - [raspi-cam-srv](https://github.com/signag/raspi-cam-srv)

## Usage
1. **Run the System**:
   ```bash
   source venv/bin/activate
   python src/main.py
   ```
   - Sensors start collecting data if `packet_count.txt` exists.
   - WebSocket servers run on ports 9001–9004.
   - Flask server runs on `http://[RPi-IP]:5000`.
   - Camera streaming runs on `http://[RPi-IP]:8000/stream.mjpg`.

2. **Stop the System**:
   - Press `Ctrl+C` to gracefully shut down sensors, camera, and servers.

## Accessing the System
- **Dashboard**: `http://[RPi-IP]:5000`
  - Displays live camera feed and media files using a responsive Tailwind CSS interface.
- **Camera Feed**: `http://[RPi-IP]:8000/stream.mjpg`
- **Telemetry Logs**: `http://[RPi-IP]:5000/telemetry.log`
- **CSV Data**: `http://[RPi-IP]:5000/telemetry.csv`
- **Packet Count**: `http://[RPi-IP]:5000/packet_count`
- **WebSocket Endpoints**:
  - IoT Data: `ws://[RPi-IP]:9001`
  - Mech Filter: `ws://[RPi-IP]:9002`
  - Data Transmitter: `ws://[RPi-IP]:9003`
  - Command Receiver: `ws://[RPi-IP]:9004` (send `start` or `stop`)

## Contributing
Contributions are welcome! Please follow these steps:
1. Fork the repository.
2. Create a feature branch: `git checkout -b feature-name`.
3. Commit changes: `git commit -m "Add feature"`.
4. Push to the branch: `git push origin feature-name`.
5. Open a pull request.

## License
This project is licensed under the MIT License with an additional requirement to acknowledge the source when using the code or its parts. See [LICENSE](LICENSE) for details.

## Links to Frameworks and Boards
- **Raspberry Pi Zero 2W**: [Official Website](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)
- **Raspberry Pi Camera Module**: [Camera Module V2](https://www.raspberrypi.com/products/camera-module-v2/)
- **Adafruit Sensors**:
  - [BMP390](https://www.adafruit.com/product/4816)
  - [TMP117](https://www.adafruit.com/product/4821)
  - [BNO055](https://www.adafruit.com/product/2472)
  - [DS3231](https://www.adafruit.com/product/3013)
- **Raspberry Pi Pico (RP2040)**: [RP2040](https://www.raspberrypi.com/products/rp2040/)
- **Servo Motor**: [Parallax Feedback 360° High Speed Servo](https://www.parallax.com/product/parallax-feedback-360-high-speed-servo/)
- **Python Libraries**:
  - [RPi.GPIO](https://pypi.org/project/RPi.GPIO/)
  - [picamera](https://picamera.readthedocs.io/)
  - [pigpio](http://abyz.me.uk/rpi/pigpio/)
  - [websockets](https://websockets.readthedocs.io/)
  - [Flask](https://flask.palletsprojects.com/)
  - [Adafruit CircuitPython](https://circuitpython.org/)
- **Teknofest**: [Official Website](https://www.teknofest.org/en/)

## Thank You
Thank you to the Teknofest 2024 organizers for providing an incredible platform to showcase innovation. Gratitude to my team for their collaboration and to the open-source community for the tools that made this project possible. Special thanks to my mentors and teammates for their guidance and support throughout the competition.

---

*Developed by Jaydeep Solanki as part of the Teknofest 2024 Model Satellite Competition.*