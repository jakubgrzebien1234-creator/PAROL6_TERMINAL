import flet
import numpy as np
import threading
import time
from ikpy.chain import Chain
from scipy.spatial.transform import Rotation as R

# ==============================================================================
# 1. KINEMATICS ENGINE (BEZ ZMIAN - OPTYMALIZOWANY)
# ==============================================================================
class KinematicsEngine:
    def __init__(self, urdf_path):
        self.chain = None
        # Maska dla robota 6-osiowego (przykładowa, dostosuj do swojego URDF jeśli trzeba)
        self.hardcoded_mask = [False, True, True, True, True, True, True, False, False] 
        try:
            self.chain = Chain.from_urdf_file(urdf_path)
            if len(self.chain.links) != len(self.hardcoded_mask):
                self.hardcoded_mask = [True] * len(self.chain.links)
                self.hardcoded_mask[0] = False 
            self.chain.active_links_mask = self.hardcoded_mask

            # Szybki solver
            self.chain.max_iterations = 15   
            self.chain.convergence_limit = 1e-2 
            
            self.n_active_joints = sum(1 for x in self.hardcoded_mask if x)
            print(f"[IK] Active joints: {self.n_active_joints}")
        except Exception as e:
            print(f"[IK ERROR] {e}")
            self.chain = None
            self.n_active_joints = 6

    def _active_to_full(self, active_joints):
        active_arr = np.array(active_joints, dtype=float)
        if len(active_arr) != self.n_active_joints:
            active_arr = np.resize(active_arr, self.n_active_joints)
        full = np.zeros(len(self.chain.links))
        np.place(full, self.chain.active_links_mask, active_arr)
        return full

    def _full_to_active(self, full_vector):
        return np.compress(self.chain.active_links_mask, full_vector)

    def forward_kinematics(self, active_joints):
        full = self._active_to_full(active_joints)
        return self.chain.forward_kinematics(full)

    def inverse_kinematics(self, target_pos, target_orient, prev_joints):
        full_prev = self._active_to_full(prev_joints)
        full_sol = self.chain.inverse_kinematics(
            target_position=target_pos, 
            target_orientation=target_orient,
            orientation_mode='all', 
            initial_position=full_prev
        )
        return self._full_to_active(full_sol)

# ==============================================================================
# 2. CARTESIAN VIEW (MINIMALISTYCZNY)
# ==============================================================================
class CartesianView(flet.Container):
    def __init__(self, uart_communicator, urdf_path, active_links_mask=None):
        super().__init__()
        self.uart = uart_communicator
        self.ik = KinematicsEngine(urdf_path)
        
        # Reszta bez zmian...
        self.is_jogging = False
        self.alive = True 
        
        # Pozycje (startowe zera)
        self.commanded_joints = [0.0] * self.ik.n_active_joints 
        self.tool_offset = np.array([0.0, 0.0, 0.18])

        self._setup_ui()
        
        threading.Thread(target=self._ui_updater_loop, daemon=True).start()

    def did_unmount(self):
        self.alive = False
        self.is_jogging = False

    def _setup_ui(self):
        # Style
        dark_panel = {
            "bgcolor": "#2D2D2D",
            "border_radius": 10,
            "border": flet.border.all(1, "#555555"),
            "padding": 15
        }
        
        # --- SEKCJA 1: PRZYCISKI JOG (XYZ + ABC) ---
        # Definicja osi: Label, kod_osi
        axes_config = [
            ("X (Przód/Tył)", "x"), 
            ("Y (Lewo/Prawo)", "y"), 
            ("Z (Góra/Dół)", "z"),
            ("A (Rot X)", "rx"), 
            ("B (Rot Y)", "ry"), 
            ("C (Rot Z)", "rz")
        ]
        
        jog_rows = flet.Column(spacing=10, expand=True)
        
        for label, code in axes_config:
            # Tworzymy przyciski +/-
            btn_minus = self._create_jog_btn("-", code, "minus")
            btn_plus = self._create_jog_btn("+", code, "plus")
            
            row = flet.Row([
                flet.Container(content=flet.Text(label, weight="bold", size=14, color="#AAAAAA"), width=120),
                btn_minus,
                btn_plus
            ], spacing=10)
            jog_rows.controls.append(row)

        jog_panel = flet.Container(
            content=flet.Column([
                flet.Text("MANUAL CONTROL", size=16, weight="bold", color="white", text_align="center"),
                flet.Divider(color="#555"),
                jog_rows
            ]), 
            **dark_panel, 
            expand=60 # 60% szerokości
        )

        # --- SEKCJA 2: ODCZYTY (XYZ + JOINTS) ---
        
        # Kontrolki do wyświetlania Kartezjańskiego
        self.lbl_cart = {}
        cart_col = flet.Column(spacing=2)
        cart_col.controls.append(flet.Text("CARTESIAN [mm/deg]", color="cyan", weight="bold"))
        for ax in ["X", "Y", "Z", "A", "B", "C"]:
            self.lbl_cart[ax] = flet.Text("0.00", size=16, weight="bold", color="white")
            cart_col.controls.append(flet.Row([
                flet.Text(f"{ax}:", width=30, color="#888"), 
                self.lbl_cart[ax]
            ]))

        # Kontrolki do wyświetlania Przegubów
        self.lbl_joints = []
        joint_col = flet.Column(spacing=2)
        joint_col.controls.append(flet.Text("JOINTS [deg]", color="orange", weight="bold"))
        for i in range(self.ik.n_active_joints):
            lbl = flet.Text("0.00", size=16, weight="bold", color="white")
            self.lbl_joints.append(lbl)
            joint_col.controls.append(flet.Row([
                flet.Text(f"J{i+1}:", width=30, color="#888"), 
                lbl
            ]))

        readout_panel = flet.Container(
            content=flet.Column([
                cart_col,
                flet.Divider(color="#555"),
                joint_col
            ], scroll=flet.ScrollMode.AUTO),
            **dark_panel,
            expand=40 # 40% szerokości
        )

        # Główny układ
        self.content = flet.Row([jog_panel, readout_panel], spacing=10, expand=True)

    def _create_jog_btn(self, txt, code, direction):
        btn_visual = flet.Container(
            content=flet.Text(txt, size=24, weight="bold", color="white"),
            bgcolor="#444444", 
            border_radius=5,
            alignment=flet.alignment.center,
            border=flet.border.all(1, "#666666"),
            height=50,
            expand=True
        )
        return flet.GestureDetector(
            content=btn_visual, 
            on_tap_down=lambda e: self.on_jog_start(e, code, direction), 
            on_tap_up=lambda e: self.on_jog_stop(e), 
            on_pan_end=lambda e: self.on_jog_stop(e), 
            expand=True
        )

    # --- WĄTEK ODŚWIEŻANIA UI ---
    def _ui_updater_loop(self):
        while self.alive:
            try:
                if self.page:
                    self._update_labels_logic()
                    self.page.update()
            except: pass 
            time.sleep(0.15) 

    def _update_labels_logic(self):
        if not self.ik.chain: return
        
        # 1. Oblicz pozycję TCP (Forward Kinematics)
        mat = self.ik.forward_kinematics(self.commanded_joints)
        pos = mat[:3, 3]
        rot = mat[:3, :3]
        tcp = pos + rot @ self.tool_offset
        
        # Konwersja na mm i stopnie (Euler XYZ)
        euler = R.from_matrix(rot).as_euler('xyz', degrees=True)
        
        # Aktualizacja Kartezjańska
        # X, Y, Z (w mm, konwersja osi robota na użytkownika)
        self.lbl_cart["X"].value = f"{-tcp[1]*1000:.1f}"
        self.lbl_cart["Y"].value = f"{tcp[0]*1000:.1f}"
        self.lbl_cart["Z"].value = f"{tcp[2]*1000:.1f}"
        # A, B, C (w stopniach)
        self.lbl_cart["A"].value = f"{euler[0]:.1f}"
        self.lbl_cart["B"].value = f"{euler[1]:.1f}"
        self.lbl_cart["C"].value = f"{euler[2]:.1f}"

        # 2. Aktualizacja Przegubów (Joints)
        for i, rad_val in enumerate(self.commanded_joints):
            if i < len(self.lbl_joints):
                deg_val = np.degrees(rad_val)
                self.lbl_joints[i].value = f"{deg_val:.2f}"

    # --- LOGIKA RUCHU (BEZ LAGÓW) ---
    def _jog_thread(self, axis, direction):
        step_mm = 2.0  
        step_rad = 0.05
        sign = 1 if direction == "plus" else -1
        
        while self.is_jogging:
            start_t = time.time()
            
            if self.ik.chain:
                current_joints = list(self.commanded_joints)
                
                # FK
                mat = self.ik.forward_kinematics(current_joints)
                pos_flange = mat[:3, 3]
                rot_flange = mat[:3, :3]
                curr_pos_tcp = pos_flange + rot_flange @ self.tool_offset
                
                dx, dy, dz = 0, 0, 0
                drx, dry, drz = 0, 0, 0
                
                if axis == 'x': dx = step_mm * sign
                elif axis == 'y': dy = step_mm * sign
                elif axis == 'z': dz = step_mm * sign
                elif axis == 'rx': drx = step_rad * sign
                elif axis == 'ry': dry = step_rad * sign
                elif axis == 'rz': drz = step_rad * sign
                
                # Konwersja układu User -> Robot
                dx_r, dy_r, dz_r = dy, -dx, dz
                
                target_pos_tcp = curr_pos_tcp + np.array([dx_r, dy_r, dz_r]) / 1000.0
                
                if axis in ['rx','ry','rz']:
                    target_rot = R.from_euler('xyz', [drx, dry, drz]).as_matrix() @ rot_flange
                else:
                    target_rot = rot_flange

                target_pos_flange = target_pos_tcp - target_rot @ self.tool_offset

                try:
                    # SZYBKIE IK (1 przebieg)
                    nj = self.ik.inverse_kinematics(target_pos_flange, target_rot, current_joints)
                    nj = [(q + np.pi) % (2*np.pi) - np.pi for q in nj]
                    self.commanded_joints = nj
                except: pass

            # Wysyłanie UART
            self.send_current_pose()
            
            # Pauza dla odciążenia GUI (80ms)
            elapsed = time.time() - start_t
            time.sleep(max(0.01, 0.08 - elapsed))

    def send_current_pose(self):
        if self.uart and self.uart.is_open():
            vals_deg = [np.degrees(r) for r in self.commanded_joints]
            data_str = ",".join([f"{v:.2f}" for v in vals_deg])
            self.uart.send_message(f"J_{data_str}")

    def on_jog_start(self, e, joint_code, direction): 
        # Efekt wizualny
        btn = e.control.content
        btn.bgcolor = "#0088cc" # Niebieski po wciśnięciu
        btn.update()
        
        if self.is_jogging: return
        self.is_jogging = True
        threading.Thread(target=self._jog_thread, args=(joint_code, direction), daemon=True).start()

    def on_jog_stop(self, e): 
        self.is_jogging = False
        # Reset koloru
        btn = e.control.content
        btn.bgcolor = "#444444"
        btn.update()