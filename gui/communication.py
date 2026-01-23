import serial
import serial.tools.list_ports
import threading
import time

class UARTCommunicator:
    def __init__(self, baudrate=115200, timeout=0.1):
        self.port = None
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_connection = None
        self.is_running = False
        self.read_thread = None
        self.on_data_received = None 

    def find_port(self):
        ports = serial.tools.list_ports.comports()
        available_ports = [p.device for p in ports]
       
        if available_ports:
            self.port = available_ports[0]
         
            return self.port
        return None

    def connect(self, port=None, baudrate=None):
        if port: self.port = port
        if baudrate: self.baudrate = baudrate
            
        if not self.port:
            self.find_port()
            
        if not self.port:
            return False

        try:
            self.serial_connection = serial.Serial(
                self.port, self.baudrate, timeout=self.timeout
            )
            self.is_running = True
            
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            
            return True
        except serial.SerialException as e:
            self.serial_connection = None
            return False

    def disconnect(self):
        self.is_running = False
        if self.serial_connection:
            try:
                self.serial_connection.close()
            except:
                pass
        self.serial_connection = None

    def is_open(self):
        return self.serial_connection is not None and self.serial_connection.is_open

    def _read_loop(self):
        """
        Reads data in a loop. Changed to more reliable reading.
        """
        while self.is_running:
            if not self.is_open():
                time.sleep(0.5)
                continue
                
            try:
              
                if self.serial_connection.in_waiting > 0:
                
                    raw_data = self.serial_connection.read(self.serial_connection.in_waiting)
                    
                    if raw_data:
                        try:
                            decoded_chunk = raw_data.decode('utf-8', errors='ignore')
                            
                            lines = decoded_chunk.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and self.on_data_received:
                                    self.on_data_received(line)
                                    
                        except Exception as decode_error:
                            pass

            except Exception as e:
                time.sleep(0.1)
            
            time.sleep(0.01)

    def send_message(self, message):
        if not self.is_open(): return False
        try:
            clean_message = message.strip() + '\n'
            self.serial_connection.write(clean_message.encode('utf-8'))
            return True
        except Exception as e:
            return False