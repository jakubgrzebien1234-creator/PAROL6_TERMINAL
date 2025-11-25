import serial
import serial.tools.list_ports
import threading
import time

class UARTCommunicator:
    """
    Zarządza komunikacją UART.
    Teraz obsługuje mechanizm REQUEST -> RESPONSE (Czekanie na "OK").
    """
    
    def __init__(self, baudrate=9600, timeout=1):
        self.port = None
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_connection = None
        self.is_running = False
        self.read_thread = None
        
        # Callback dla GUI
        self.on_data_received = None

        # --- NOWOŚĆ: Zdarzenie do synchronizacji "OK" ---
        # To flaga, którą wątek odczytu podniesie, gdy zobaczy "OK"
        self.response_event = threading.Event()

    def find_port(self):
        """Pomocnicza funkcja do znajdowania dostępnych portów."""
        ports = serial.tools.list_ports.comports()
        available_ports = [p.device for p in ports]
        print(f"Dostępne porty: {available_ports}")
        if available_ports:
            self.port = available_ports[0]
            print(f"Wybrano domyślny port: {self.port}")
            return self.port
        return None

    def connect(self, port=None, baudrate=None):
        if port: self.port = port
        if baudrate: self.baudrate = baudrate
            
        if not self.port:
            self.find_port()
            
        if not self.port:
            print("BŁĄD: Nie znaleziono żadnego portu szeregowego.")
            return False
            
        if self.serial_connection and self.serial_connection.is_open:
            return True

        try:
            self.serial_connection = serial.Serial(
                self.port, self.baudrate, timeout=self.timeout
            )
            self.is_running = True
            
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            
            print(f"Połączono z {self.port} przy {self.baudrate} baud.")
            return True
        except serial.SerialException as e:
            print(f"BŁĄD: Nie można otworzyć portu {self.port}. {e}")
            self.serial_connection = None
            return False

    def disconnect(self):
        self.is_running = False
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=1)
            
        if self.serial_connection and self.serial_connection.is_open:
            try:
                self.serial_connection.close()
                print("Rozłączono.")
            except Exception as e:
                print(f"Błąd podczas zamykania portu: {e}")
                
        self.serial_connection = None

    def is_open(self):
        return self.serial_connection is not None and self.serial_connection.is_open

    def _read_loop(self):
        """
        Wątek czytający. Teraz wyłapuje "OK" i daje znać funkcji send_message.
        """
        while self.is_running:
            if not self.is_open():
                time.sleep(0.1)
                continue
                
            try:
                if self.serial_connection.in_waiting > 0:
                    line = self.serial_connection.readline()
                    
                    if line:
                        decoded_line = line.decode('utf-8', errors='ignore').strip()
                        
                        # --- NOWOŚĆ: Wykrywanie potwierdzenia ---
                        if decoded_line == "OK":
                            # Sygnalizujemy, że przyszło potwierdzenie!
                            self.response_event.set()
                        
                        # Przekazujemy dalej do GUI (logi, wykresy itp.)
                        if decoded_line and self.on_data_received:
                            self.on_data_received(decoded_line)
                            
            except Exception as e:
                print(f"Błąd w pętli odczytu: {e}")
                time.sleep(0.01)

    def send_message(self, message, wait_for_ack=True, ack_timeout=1.0):
        """
        Wysyła wiadomość i czeka na "OK" od STM32.
        
        :param message: Treść komendy
        :param wait_for_ack: Czy czekać na 'OK'
        :param ack_timeout: Ile sekund czekać zanim uznamy błąd
        :return: True jeśli wysłano i (opcjonalnie) otrzymano OK. False przy błędzie.
        """
        if not self.is_open():
            print("BŁĄD: Brak połączenia.")
            return False
            
        try:
            # 1. Czyścimy flagę zdarzenia (resetujemy "stoper")
            self.response_event.clear()

            # 2. Czyścimy bufor wejściowy (usuwamy stare śmieci, żeby nie pomylić starego OK z nowym)
            self.serial_connection.reset_input_buffer()

            # 3. Wysyłanie
            clean_message = message.strip() + '\n'
            self.serial_connection.write(clean_message.encode('utf-8'))
            self.serial_connection.flush()
            
            print(f"Wysłano: {clean_message.strip()}")

            if not wait_for_ack:
                # Jeśli to jakaś komenda, która nie zwraca OK, po prostu wychodzimy
                time.sleep(0.05) # Mała pauza techniczna
                return True

            # 4. OCZEKIWANIE NA "OK"
            # wait() zablokuje ten wątek aż _read_loop zrobi set() lub minie czas ack_timeout
            # To jest dużo lepsze niż time.sleep(), bo reaguje natychmiast!
            ack_received = self.response_event.wait(timeout=ack_timeout)

            if ack_received:
                # print("Potwierdzono (OK)") # Opcjonalnie
                return True
            else:
                print(f"TIMEOUT: Nie otrzymano 'OK' dla komendy '{clean_message.strip()}' w ciągu {ack_timeout}s")
                return False

        except Exception as e:
            print(f"BŁĄD wysyłania: {e}")
            return False