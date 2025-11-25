import flet
import numpy as np
import math
import threading
import time
from ikpy.chain import Chain
from gui.communication import UARTCommunicator

class CartesianView(flet.Container):
    """
    Widok Cartesian Mode z obsługą:
    - Ruchu liniowego XYZ -> Tłumaczenie na kąty J1-J6 (Inverse Kinematics)
    - Wysyłania obliczonych kątów przez UART do STM32
    """

    def __init__(self, uart_communicator, urdf_path, active_links_mask=None):
        super().__init__()
        
        # Przechowujemy referencję do komunikatora
        self.uart = uart_communicator
        
        # --- 1. KONFIGURACJA IKPY ---
        self.urdf_path = urdf_path
        self.active_links_mask = active_links_mask 
        
        # Flaga do sterowania ciągłym ruchem
        self.is_jogging = False

        try:
            self.chain = Chain.from_urdf_file(
                self.urdf_path,
                active_links_mask=self.active_links_mask
            )
            print(f"Załadowano URDF: {self.chain.name}")
        except Exception as e:
            print(f"Błąd ładowania URDF: {e}")
            self.chain = None

        # Pozycja startowa (wszystkie silniki na 0)
        self.current_joints = [0] * len(self.chain.links) if self.chain else [0]*8

        # --- 2. KONFIGURACJA GUI ---
        self.padding = 10
        
        left_column_items = [
            ("Oś X", "x"), ("Oś Y", "y"), ("Oś Z", "z"),
            ("Chwytak Elektryczny", "gripper_e")
        ]
        
        right_column_items = [
            ("Rotacja A (Rx)", "rx"), ("Rotacja B (Ry)", "ry"), ("Rotacja C (Rz)", "rz"),
            ("Chwytak Pneumatyczny", "gripper_p")
        ]

        # --- 3. BUDOWA SIATKI PRZYCISKÓW ---
        jog_grid_layout = flet.Column(spacing=10, expand=True)

        for i in range(4):
            l_name, l_code = left_column_items[i]
            r_name, r_code = right_column_items[i]

            panel_left = self._create_control(l_name, l_code)
            panel_right = self._create_control(r_name, r_code)

            row = flet.Row(
                controls=[panel_left, panel_right],
                spacing=10,
                expand=True
            )
            jog_grid_layout.controls.append(row)

        jog_buttons_container = flet.Container(
            content=jog_grid_layout,
            expand=8 # Duża część ekranu dla przycisków
        )

        # --- 4. PRAWA STRONA (WYŚWIETLACZ POZYCJI) ---
        position_frame_style = {
            "bgcolor": "#2D2D2D",
            "border_radius": 10,
            "border": flet.border.all(1, "#555555"),
            "padding": 15
        }

        position_rows = [
            flet.Text("POZYCJA TCP", size=18, weight="bold", color="white", text_align="center")
        ]

        self.position_labels = {}
        display_axes = ["X", "Y", "Z", "Rx", "Ry", "Rz"]
        
        for axis in display_axes:
            value_label = flet.Text("0.00", size=16, color="white", text_align="right", expand=True)
            self.position_labels[axis] = value_label
            unit = "mm" if axis in ["X", "Y", "Z"] else "rad"
            position_rows.append(
                flet.Row(
                    controls=[
                        flet.Text(f"{axis} [{unit}]:", size=16, weight="bold", color="white"),
                        value_label
                    ],
                    alignment=flet.MainAxisAlignment.SPACE_BETWEEN
                )
            )
        
        position_rows.append(flet.Divider(color="#555555"))
        
        # Etykiety stanów chwytaków
        self.lbl_gripper_e = flet.Text("OTWARTY", color="white", size=14)
        self.lbl_gripper_p = flet.Text("WYŁĄCZONY", color="white", size=14)
        
        position_rows.append(flet.Row([flet.Text("Chwytak E:", weight="bold"), self.lbl_gripper_e], alignment="spaceBetween"))
        position_rows.append(flet.Row([flet.Text("Chwytak P:", weight="bold"), self.lbl_gripper_p], alignment="spaceBetween"))

        position_frame = flet.Container(
            content=flet.Column(
                controls=position_rows,
                spacing=10,
                horizontal_alignment=flet.CrossAxisAlignment.CENTER
            ),
            **position_frame_style,
            expand=2 # ZMNIEJSZONO: Było 3, teraz 2 -> Pasek będzie węższy
        )

        # --- 5. GŁÓWNY LAYOUT ---
        self.content = flet.Row(
            controls=[jog_buttons_container, position_frame],
            spacing=10
        )
        
        self.update_display_positions()


    # --- LOGIKA MATEMATYCZNA I UART ---

    def _get_rotation_matrix(self, axis, angle):
        c = np.cos(angle)
        s = np.sin(angle)
        if axis == 'rx': return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
        elif axis == 'ry': return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        elif axis == 'rz': return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        return np.eye(3)

    def update_display_positions(self):
        if not self.chain: return
        
        transformation_matrix = self.chain.forward_kinematics(self.current_joints)
        x, y, z = transformation_matrix[:3, 3]
        r_mat = transformation_matrix[:3, :3]
        
        sy = math.sqrt(r_mat[0, 0] * r_mat[0, 0] +  r_mat[1, 0] * r_mat[1, 0])
        if not sy < 1e-6:
            rx = math.atan2(r_mat[2, 1], r_mat[2, 2])
            ry = math.atan2(-r_mat[2, 0], sy)
            rz = math.atan2(r_mat[1, 0], r_mat[0, 0])
        else:
            rx = math.atan2(-r_mat[1, 2], r_mat[1, 1])
            ry = math.atan2(-r_mat[2, 0], sy)
            rz = 0

        self.position_labels["X"].value = f"{x * 1000:.2f}"
        self.position_labels["Y"].value = f"{y * 1000:.2f}"
        self.position_labels["Z"].value = f"{z * 1000:.2f}"
        self.position_labels["Rx"].value = f"{rx:.3f}"
        self.position_labels["Ry"].value = f"{ry:.3f}"
        self.position_labels["Rz"].value = f"{rz:.3f}"
        
        if self.page: self.page.update()

    def calculate_ik_step(self, axis: str, direction: str):
        if not self.chain: return

        step_linear = 0.0005  
        step_angle = 0.005    
        sign = 1 if direction == "plus" else -1

        current_matrix = self.chain.forward_kinematics(self.current_joints)
        target_matrix = current_matrix.copy()

        if axis == 'x': target_matrix[0, 3] += step_linear * sign
        elif axis == 'y': target_matrix[1, 3] += step_linear * sign
        elif axis == 'z': target_matrix[2, 3] += step_linear * sign
        elif axis in ['rx', 'ry', 'rz']:
            rot_step = self._get_rotation_matrix(axis, step_angle * sign)
            target_matrix[:3, :3] = target_matrix[:3, :3] @ rot_step

        target_position = target_matrix[:3, 3]
        target_orientation = target_matrix[:3, :3]

        try:
            new_joints = self.chain.inverse_kinematics(
                target_position=target_position,
                target_orientation=target_orientation,
                orientation_mode="all",
                initial_position=self.current_joints
            )
            
            # Aktualizuj model wewnętrzny
            self.current_joints = new_joints
            
            # --- NOWOŚĆ: WYSYŁANIE DO UART ---
            if self.uart and self.uart.is_open():
                # Iterujemy przez silniki 1-6
                # new_joints[0] to zazwyczaj baza/link wirtualny, silniki są od indeksu 1
                for i in range(1, 7):
                    try:
                        angle_rad = new_joints[i]
                        angle_deg = np.degrees(angle_rad)
                        
                        # Format: J1_12.34
                        cmd = f"J{i}_{angle_deg:.2f}"
                        self.uart.send_message(cmd)
                        
                        # Małe opóźnienie, żeby nie zapchać bufora STM32 przy wysyłaniu 6 komend naraz
                        # Przy 115200 baud to trwa ułamek sekundy
                        # time.sleep(0.002) 
                    except IndexError:
                        pass

            # Odśwież GUI
            self.update_display_positions()

        except Exception as e:
            print(f"IK Error: {e}")


    # --- OBSŁUGA WĄTKÓW I ZDARZEŃ ---

    def _jog_thread(self, axis, direction):
        while self.is_jogging:
            self.calculate_ik_step(axis, direction)
            time.sleep(0.1)

    def on_cartesian_jog_start(self, e, axis: str, direction: str, btn):
        btn.style.bgcolor = "#666666"
        btn.update()
        
        if not self.is_jogging:
            self.is_jogging = True
            t = threading.Thread(target=self._jog_thread, args=(axis, direction), daemon=True)
            t.start()

    def on_cartesian_jog_stop(self, e, axis: str, direction: str, btn):
        self.is_jogging = False
        btn.style.bgcolor = "#444444"
        btn.update()

    def on_gripper_click(self, e):
        code = e.control.data['code']
        action = e.control.data['action']
        
        print(f"GRIPPER: {code} -> {action}")
        
        command_to_send = ""
        
        if code == "gripper_p":
            self.lbl_gripper_p.value = "WŁĄCZONY" if action == "ON" else "WYŁĄCZONY"
            command_to_send = "VAC_ON" if action == "ON" else "VAC_OFF"
            
        elif code == "gripper_e":
            self.lbl_gripper_e.value = "ZAMKNIĘTY" if action == "CLOSE" else "OTWARTY"
            command_to_send = "VALVEON" if action == "CLOSE" else "VALVEOFF"
            
        if self.page: self.page.update()
        
        # Wysyłanie UART
        if self.uart and self.uart.is_open() and command_to_send:
            self.uart.send_message(command_to_send)

    def _create_control(self, label_text: str, axis_code: str) -> flet.Container:
        def get_style():
            return flet.ButtonStyle(
                bgcolor="#444444", 
                shape=flet.RoundedRectangleBorder(radius=8),
                padding=15,
                color="white"
            )

        if axis_code == "gripper_p":
            t1, t2 = "WYŁĄCZ", "WŁĄCZ"
            btn1 = flet.ElevatedButton(t1, style=get_style(), expand=True, 
                                     data={'code': axis_code, 'action': 'OFF'}, on_click=self.on_gripper_click)
            btn2 = flet.ElevatedButton(t2, style=get_style(), expand=True, 
                                     data={'code': axis_code, 'action': 'ON'}, on_click=self.on_gripper_click)

        elif axis_code == "gripper_e":
            t1, t2 = "OTWÓRZ", "ZAMKNIJ"
            btn1 = flet.ElevatedButton(t1, style=get_style(), expand=True, 
                                     data={'code': axis_code, 'action': 'OPEN'}, on_click=self.on_gripper_click)
            btn2 = flet.ElevatedButton(t2, style=get_style(), expand=True, 
                                     data={'code': axis_code, 'action': 'CLOSE'}, on_click=self.on_gripper_click)

        else:
            t1, t2 = "-", "+"
            dir1, dir2 = "minus", "plus"
            v1 = flet.ElevatedButton(t1, style=get_style(), expand=True, disabled=True, content=flet.Text(t1, size=20, weight="bold"))
            v2 = flet.ElevatedButton(t2, style=get_style(), expand=True, disabled=True, content=flet.Text(t2, size=20, weight="bold"))
            btn1 = flet.GestureDetector(
                content=v1, expand=True,
                on_tap_down=lambda e, a=axis_code, d=dir1, v=v1: self.on_cartesian_jog_start(e, a, d, v),
                on_tap_up=lambda e, a=axis_code, d=dir1, v=v1: self.on_cartesian_jog_stop(e, a, d, v)
            )
            btn2 = flet.GestureDetector(
                content=v2, expand=True,
                on_tap_down=lambda e, a=axis_code, d=dir2, v=v2: self.on_cartesian_jog_start(e, a, d, v),
                on_tap_up=lambda e, a=axis_code, d=dir2, v=v2: self.on_cartesian_jog_stop(e, a, d, v)
            )

        return flet.Container(
            content=flet.Column(
                controls=[
                    flet.Text(label_text, size=16, weight="bold", color="white"),
                    flet.Row(controls=[btn1, btn2], spacing=10)
                ],
                spacing=5,
                horizontal_alignment=flet.CrossAxisAlignment.CENTER 
            ),
            bgcolor="#2D2D2D",
            border_radius=10,
            border=flet.border.all(1, "#555555"),
            padding=10,
            expand=True
        )