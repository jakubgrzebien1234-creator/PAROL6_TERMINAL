import flet
import flet as ft
from flet import Column, Row, Container, ElevatedButton, Slider, Text, Image, alignment, ScrollMode, MainAxisAlignment, colors, AlertDialog, ProgressRing, IconButton, icons
import json
import time
import threading

class SettingsView(flet.Container):
    """
    Settings View - FINAL LAYOUT
    - Left Panel: Fixed width (140px)
    - Right Panel: Fixed width (240px) - FIXED (was too wide)
    - Middle Panel: Takes all remaining space (expand=True)
    """
    
    VIEW_MAPPING = {
        "render1.png": "MAIN ROBOT",
        "render2.png": "ROTARY GRIPPER",
        "render3.png": "VERTICAL GRIPPER"
    }

    def __init__(self, uart_communicator):
        super().__init__()
        # --- UI LAYOUT FIXES ---
        self.expand = True  
        self.padding = 10
        
        self.comm = uart_communicator
        
        # --- GEAR RATIOS (J1 to J6) ---
        self.gear_ratios = {
            1: 6.4, 2: 20.0, 3: 18.0952381, 
            4: 4.0, 5: 4.0, 6: 10.0
        }

        # --- STATE VARIABLES ---
        self.selected_motor_index = 1 
        self.active_slider_set_id = 1 
        self.active_view_name = "render1.png" 
        self.current_gripper_values = []      
        self.motor_names = ["MOTOR J1","MOTOR J2","MOTOR J3","MOTOR J4","MOTOR J5","MOTOR J6"]
        self.config_file_path = "motor_settings.json"
        
        self.homing_event = threading.Event()
        self.current_test_pos = 0.0

        # Tuning variables
        self.tuning_dialog = None
        self.tuning_slider = None
        self.sg_chart = None
        self.chart_data_points = []
        self.chart_threshold_points = []
        
        # Debug Data Display
        self.sg_value_text = Text("-", size=30, weight="bold", color=colors.CYAN_400)
        self.vel_value_text = Text("-", size=16, weight="bold", color=colors.YELLOW_400)
        self.mode_value_text = Text("-", size=16, weight="bold", color=colors.WHITE)
        
        # SGGRIP Tuning
        self.egrip_tuning_dialog = None
        self.egrip_sg_result_text = Text("-", size=40, weight="bold", color=colors.CYAN_300)
        self.egrip_chart = None
        self.egrip_chart_data_points = []

        # --- ROBOT SLIDER CONFIGURATION ---
        self.slider_set_definitions = {
            1: [ ("A1", 200, 10000), ("V1", 10, 20000), ("AMAX", 1000, 30000), ("VMAX", 10000, 400000), ("D1", 200, 4000) ],
            2: [ ("IHOLD", 0, 31), ("IRUN", 0, 31), ("IHOLDDELAY", 0, 15) ],
            3: [ ("VMAX - HOMING", 5000, 500000), ("AMAX - HOMING", 1000, 8000), ("OFFSET[mm]", -50, 50) ],
            4: [ ("Sensitivity (STALL_SENS)", -64, 63), ("SGT THRESHOLD", 0, 1000) ],
            5: [ ("OT TEMPERATURE [°C]", 40, 100), ("CT TEMPERATURE [°C]", 20, 60), ("SAFETY DELAY [ms]", 0, 5000) ]
        }
        
        # --- GLOBAL SETTINGS DATA ---
        self.global_settings_data = {}
        self._load_global_settings()

        # --- GRIPPER SETTINGS DATA ---
        self.gripper_settings_data = {}
        self._load_gripper_settings()

        self.motor_settings_data = {} 
        self._load_settings() 
        
        # UI init
        self.sliders_column_container = Column(controls=[], spacing=10, expand=True, scroll=ScrollMode.ADAPTIVE)
        self.sliders_labels = []        
        self.slider_controls = []       
        self.slider_value_displays = [] 

        self.content = self._create_main_view()
        self.homing_dialog = None

    # --- HOMING & DIALOGS ---
    def open_homing_window(self, e):
        self.homing_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Homing..."),
            content=ft.Column([
                ft.ProgressRing(),
                ft.Text("Please wait...")
            ], height=100),
            actions=[],
        )
        self.page.open(self.homing_dialog)

    def close_homing_dialog(self):
        if self.homing_dialog is not None:
            self.homing_dialog.open = False
            self.homing_dialog.update()
            try:
                self.page.close(self.homing_dialog)
            except:
                pass

    def set_homed_status(self, is_homed: bool):
        if hasattr(self, 'close_homing_dialog'):
            self.close_homing_dialog()
            return
        # Fallback
        if self.page and hasattr(self, 'homing_loading_dialog') and self.homing_loading_dialog:
            self.homing_loading_dialog.open = False
            self.page.update()
            try:
                self.page.close(self.homing_loading_dialog)
            except: pass
            self.homing_loading_dialog = None

    # --- PARSING & INCOMING DATA ---
    def parse_debug_line(self, data_line: str):
        clean_line = data_line.strip().replace("'", "").replace('"', "")
        expected_tag = f"J{self.selected_motor_index}_DBG"
        
        if expected_tag not in clean_line: return

        try:
            if ":" in clean_line:
                content = clean_line.split(":", 1)[1].strip()
            else: return

            parts = content.split("|")
            for part in parts:
                part = part.strip()
                if "SG=" in part:
                    val = part.split("=")[1].strip()
                    if self.sg_value_text.page:
                        self.sg_value_text.value = val
                        self.sg_value_text.update()
                elif "V=" in part:
                    val = part.split("=")[1].strip()
                    if self.vel_value_text.page:
                        self.vel_value_text.value = f"{val} st/s"
                        self.vel_value_text.update()
                elif "Mode=" in part:
                    mode_str = part.split("=")[1].strip()
                    if self.mode_value_text.page:
                        self.mode_value_text.value = mode_str
                        if "BAD" in mode_str or "STEALTH" in mode_str:
                            self.mode_value_text.color = colors.RED_ACCENT
                        else:
                            self.mode_value_text.color = colors.GREEN_ACCENT
                        self.mode_value_text.update()
        except Exception:
            pass

    def handle_stall_alert(self, data_string):
        if not data_string: return
        clean_str = data_string.strip().replace("'", "").replace('"', "")
        current_motor_tag = f"J{self.selected_motor_index}"

        # 1. Position Parsing for Tests
        if current_motor_tag in clean_str and not any(x in clean_str for x in ["DBG", "COLLISION", "SGRESULT", "Mode"]):
            try:
                normalized = clean_str.replace("_", " ").replace(":", " ").replace("=", " ")
                parts = normalized.split()
                for i, part in enumerate(parts):
                    if part == current_motor_tag:
                        if i + 1 < len(parts):
                            val_str = parts[i+1]
                            try:
                                val = float(val_str)
                                self.current_test_pos = val
                                break
                            except: pass
            except Exception:
                pass

        # 2. SG_RESULT
        if "_SGRESULT_" in clean_str:
            try:
                parts = clean_str.split("_")
                if len(parts) >= 3:
                    incoming_tag = parts[0]
                    val_str = parts[-1]
                    if incoming_tag == current_motor_tag:
                        val = int(val_str)
                        if (self.tuning_dialog and self.tuning_dialog.open and 
                            self.sg_chart and self.chart_data_points):
                            for i in range(len(self.chart_data_points) - 1):
                                self.chart_data_points[i].y = self.chart_data_points[i+1].y
                            self.chart_data_points[-1].y = val
                            self.sg_chart.update()
            except: pass
            return

        # 3. COLLISION
        if "COLLISION" in clean_str and current_motor_tag in clean_str:
            if hasattr(self, 'stall_status_text') and self.stall_status_text.page:
                self.stall_status_text.value = f"⚠️ COLLISION!"
                self.stall_status_text.color = "white"
                self.stall_status_text.update()
            if hasattr(self, 'stall_status_container') and self.stall_status_container.page:
                self.stall_status_container.bgcolor = ft.colors.RED_900
                self.stall_status_container.border = ft.border.all(2, ft.colors.RED_400)
                self.stall_status_container.update()
            return

        # 4. EGRIP
        if "EGRIP_SR_" in clean_str:
            try:
                val = int(clean_str.split("_")[2].strip())
                if (self.egrip_tuning_dialog and self.egrip_tuning_dialog.open and 
                    self.egrip_chart and self.egrip_chart_data_points):
                    for i in range(len(self.egrip_chart_data_points) - 1):
                        self.egrip_chart_data_points[i].y = self.egrip_chart_data_points[i+1].y
                    self.egrip_chart_data_points[-1].y = val
                    self.egrip_chart.update()
                if self.egrip_sg_result_text.page:
                    self.egrip_sg_result_text.value = str(val)
                    self.egrip_sg_result_text.update()
            except: pass
            return

    # --- TUNING INTERFACE ---
    def _start_tuning_procedure(self, e):
        self._show_tuning_interface()

    def _show_tuning_interface(self):
        current_sens = 0
        current_threshold = 10 
        
        try:
            if self.selected_motor_index in self.motor_settings_data:
                settings_list = self.motor_settings_data[self.selected_motor_index].get(4, [])
                if len(settings_list) > 0: current_sens = settings_list[0]
                if len(settings_list) > 1: current_threshold = settings_list[1]
                if len(settings_list) < 2: self.motor_settings_data[self.selected_motor_index][4].append(10)
        except Exception: pass

        if not self.chart_data_points:
            self.chart_data_points = [ft.LineChartDataPoint(i, 0) for i in range(50)]
        
        self.chart_threshold_points = [ft.LineChartDataPoint(i, current_threshold) for i in range(50)]

        self.sg_chart = ft.LineChart(
            data_series=[
                ft.LineChartData(data_points=self.chart_data_points, stroke_width=3, color=ft.colors.CYAN, curved=True, stroke_cap_round=True),
                ft.LineChartData(data_points=self.chart_threshold_points, stroke_width=2, color=ft.colors.RED, dash_pattern=[5, 5]),
            ],
            border=ft.border.all(1, ft.colors.GREY_800),
            left_axis=ft.ChartAxis(labels_size=40, title=ft.Text("SG"), title_size=20, 
                labels=[
                    ft.ChartAxisLabel(value=0, label=ft.Text("0", size=10)),
                    ft.ChartAxisLabel(value=500, label=ft.Text("500", size=10)),
                    ft.ChartAxisLabel(value=1024, label=ft.Text("1024", size=10, color="yellow")),
                ]),
            bottom_axis=ft.ChartAxis(labels_size=0),
            min_y=0, max_y=1050, min_x=0, max_x=49, 
            expand=True, tooltip_bgcolor=ft.colors.with_opacity(0.8, ft.colors.BLACK),
        )

        self.slider_val_text = ft.Text(f"{int(current_sens)}", size=20, weight="bold", text_align=ft.TextAlign.RIGHT)
        self.threshold_val_text = ft.Text(f"{int(current_threshold)}", size=20, weight="bold", color="orange", text_align=ft.TextAlign.RIGHT)
        self.stall_status_text = ft.Text("STATUS: OK", size=14, weight="bold", color="green", text_align=ft.TextAlign.CENTER)

        self.stall_status_container = ft.Container(
            content=self.stall_status_text, alignment=ft.alignment.center, padding=10,
            bgcolor="#1f3a1f", border=ft.border.all(1, "#2f5a2f"), border_radius=8, width=200
        )

        self.tuning_slider = ft.Slider(min=-64, max=63, value=current_sens, label="{value}", on_change=self._on_tuning_slider_change, expand=True)
        self.threshold_slider = ft.Slider(min=0, max=1023, value=current_threshold, label="{value}", divisions=1023, active_color=ft.colors.ORANGE_400, on_change=self._on_tuning_threshold_change, expand=True)

        def on_reset_click(e):
            if self.comm: self.comm.send_message("COLLISION_OK\r\n")
            self._reset_stall_status(None)
            e.control.icon = ft.icons.CHECK; e.control.icon_color = "green"; e.control.update()
            time.sleep(0.5)
            e.control.icon = ft.icons.REFRESH; e.control.icon_color = "white"; e.control.update()

        reset_button = ft.IconButton(icon=ft.icons.REFRESH, icon_color="white", bgcolor="blue", tooltip="UNLOCK", on_click=on_reset_click)

        def close_and_refresh(e):
            self.tuning_dialog.open = False
            self.page.update()
            if self.active_slider_set_id == 4: self._on_slider_set_select(4) 

        dialog_content = ft.Column([
            ft.Text("Load Chart (Live):", size=14, color="#888"),
            ft.Container(content=self.sg_chart, expand=True, padding=ft.padding.only(left=5, top=10, right=10, bottom=10), bgcolor="#222", border_radius=10),
            ft.Divider(color="#444", height=10),
            ft.Row([ft.Text("Sensitivity (SGT):", size=16, width=130), self.tuning_slider, ft.Container(content=self.slider_val_text, width=50, alignment=alignment.center_right)], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([ft.Text("Threshold (Limit):", size=16, color="orange", width=130), self.threshold_slider, ft.Container(content=self.threshold_val_text, width=50, alignment=alignment.center_right)], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(color="#444", height=10),
            ft.Row([ft.Row([self.stall_status_container, reset_button], spacing=5), ft.ElevatedButton("TEST MOTION", icon=ft.icons.SWAP_HORIZ, on_click=self._run_test_motion, style=ft.ButtonStyle(bgcolor=ft.colors.BLUE_700, color="white", shape=ft.RoundedRectangleBorder(radius=8), padding=15), expand=True)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        ], spacing=5)

        title_row = ft.Row(controls=[ft.Text(f"StallGuard Tuning - Axis J{self.selected_motor_index}", size=20, weight="bold"), ft.IconButton(icon=ft.icons.CLOSE, icon_size=24, tooltip="Close", on_click=close_and_refresh)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        self.tuning_dialog = ft.AlertDialog(title=title_row, title_padding=ft.padding.only(left=20, right=10, top=10, bottom=0), content=ft.Container(width=850, height=700, content=dialog_content), modal=True)
        self.page.dialog = self.tuning_dialog
        self.tuning_dialog.open = True
        self.page.update()

    def _reset_stall_status(self, e):
        if hasattr(self, 'stall_status_text') and self.stall_status_text.page:
            self.stall_status_text.value = "STATUS: OK (No collision)"
            self.stall_status_text.color = "green"
            self.stall_status_text.update()
        if hasattr(self, 'stall_status_container') and self.stall_status_container.page:
            self.stall_status_container.bgcolor = "#1f3a1f"
            self.stall_status_container.border = flet.border.all(1, "#2f5a2f")
            self.stall_status_container.update()

    def _on_tuning_slider_change(self, e):
        val = int(e.control.value)
        try: self.motor_settings_data[self.selected_motor_index][4][0] = val
        except: pass
        if hasattr(self, 'slider_val_text'): self.slider_val_text.value = str(val); self.slider_val_text.update()
        
        ihold_stall = 0
        try: ihold_stall = self.motor_settings_data[self.selected_motor_index][4][1]
        except: pass
        if self.comm: self.comm.send_message(f"OT,stall,J{self.selected_motor_index},{val},{ihold_stall}\r\n")

    def _on_tuning_threshold_change(self, e):
        val = int(e.control.value)
        if hasattr(self, 'threshold_val_text'): self.threshold_val_text.value = str(val); self.threshold_val_text.update()
        if self.sg_chart and self.chart_threshold_points:
            for p in self.chart_threshold_points: p.y = val 
            self.sg_chart.update()
        try:
            while len(self.motor_settings_data[self.selected_motor_index][4]) < 2: self.motor_settings_data[self.selected_motor_index][4].append(10)
            self.motor_settings_data[self.selected_motor_index][4][1] = val
        except: pass
        if self.comm: self.comm.send_message(f"OT,sgth,J{self.selected_motor_index},{val}\r\n")

    # --- STRICT TEST MOTION ---
    def _run_test_motion(self, e):
        def move_and_wait_strict(motor, target_angle):
            if self.comm: self.comm.send_message(f"J{motor}_{target_angle}\r\n")
            
            time.sleep(0.5)
            
            strict_tolerance = 0.5 
            last_position = -9999.0
            stuck_counter = 0       
            
            while True:
                current = self.current_test_pos
                diff = abs(current - target_angle)
                
                if diff <= strict_tolerance:
                    return True
                
                if abs(current - last_position) < 0.01:
                    stuck_counter += 1
                else:
                    stuck_counter = 0
                    
                last_position = current
                
                if stuck_counter > 30:
                    err_msg = f"ERROR: Robot stuck at {current}° (Target: {target_angle}°)"
                    
                    if self.page: 
                        self.page.snack_bar = ft.SnackBar(ft.Text(err_msg), bgcolor=ft.colors.RED)
                        self.page.snack_bar.open = True
                        self.page.update()
                    return False 
                
                time.sleep(0.1)

        def motion_sequence():
            motor = self.selected_motor_index
            self._reset_stall_status(None)
            
            if not move_and_wait_strict(motor, 30): return
            time.sleep(1.0)
            
            if not move_and_wait_strict(motor, -30): return
            time.sleep(1.0)
            
            if not move_and_wait_strict(motor, 0): return
            
            if self.page: 
                self.page.snack_bar = ft.SnackBar(ft.Text("Test Complete: Perfect Accuracy"), bgcolor=ft.colors.GREEN)
                self.page.snack_bar.open = True
                self.page.update()

        threading.Thread(target=motion_sequence, daemon=True).start()

    # --- GRIPPER TUNING ---
    def _open_egrip_tuning(self, e):
        vals = self.gripper_settings_data.get("SGrip", [10, 20, 5000, 0, 10])
        while len(vals) < 5:
            vals.append(10 if len(vals) == 4 else 0)
        self.current_gripper_values = vals
        
        current_force = vals[3] 
        current_thrs = vals[4] 
        
        self.egrip_sg_result_text.value = "-"
        force_label = Text(str(int(current_force)), size=18, weight="bold", color=colors.ORANGE_400)
        thrs_label = Text(str(int(current_thrs)), size=18, weight="bold", color=colors.RED_400)

        self.egrip_chart_data_points = [ft.LineChartDataPoint(i, 0) for i in range(50)]
        self.egrip_threshold_points = [ft.LineChartDataPoint(i, current_thrs) for i in range(50)]
        
        self.egrip_chart = ft.LineChart(
            data_series=[
                ft.LineChartData(
                    data_points=self.egrip_chart_data_points, 
                    stroke_width=3, 
                    color=ft.colors.CYAN, 
                    curved=True, 
                    stroke_cap_round=True
                ),
                ft.LineChartData(
                    data_points=self.egrip_threshold_points, 
                    stroke_width=2, 
                    color=ft.colors.RED, 
                    dash_pattern=[5, 5]
                ),
            ],
            border=ft.border.all(1, ft.colors.GREY_800),
            left_axis=ft.ChartAxis(
                labels_size=40, 
                title=ft.Text("SG"), 
                title_size=20,
                labels=[
                    ft.ChartAxisLabel(value=0, label=ft.Text("0", size=10)),
                    ft.ChartAxisLabel(value=500, label=ft.Text("500", size=10)),
                    ft.ChartAxisLabel(value=1024, label=ft.Text("1024", size=10, color="yellow")),
                ]
            ),
            bottom_axis=ft.ChartAxis(labels_size=0),
            min_y=0, max_y=1050, min_x=0, max_x=49,
            expand=True,
            tooltip_bgcolor=ft.colors.with_opacity(0.8, ft.colors.BLACK),
        )

        def on_force_slider_change(e):
            val = int(e.control.value)
            force_label.value = str(val); force_label.update()
            self.current_gripper_values[3] = val
            v_str = ",".join(map(str, self.current_gripper_values))
            if self.comm: self.comm.send_message(f"OT,SGrip,{v_str}\r\n")

        def on_thrs_slider_change(e):
            val = int(e.control.value)
            thrs_label.value = str(val); thrs_label.update()
            self.current_gripper_values[4] = val
            if self.egrip_chart and self.egrip_threshold_points:
                for p in self.egrip_threshold_points: p.y = val
                self.egrip_chart.update()
            v_str = ",".join(map(str, self.current_gripper_values))
            if self.comm: self.comm.send_message(f"OT,SGrip,{v_str}\r\n")

        force_slider = Slider(min=-64, max=63, value=current_force, label="{value}", 
                             active_color=colors.ORANGE_400, on_change=on_force_slider_change)
        thrs_slider = Slider(min=0, max=200, value=current_thrs, label="{value}", divisions=200,
                             active_color=colors.RED_400, on_change=on_thrs_slider_change)
        
        btn_style = flet.ButtonStyle(shape=flet.RoundedRectangleBorder(radius=8), padding=15)
        ctrl_buttons = Row([
            ElevatedButton("OPEN",  bgcolor=colors.BLUE_700, color="white", style=btn_style, on_click=lambda _: self._send_egrip_cmd("EGRIP_OPEN")),
            ElevatedButton("STOP", icon=icons.STOP_CIRCLE, bgcolor=colors.RED_700, color="white", style=btn_style, on_click=lambda _: self._send_egrip_cmd("EGRIP_STOP")),
            ElevatedButton("CLOSE", bgcolor=colors.BLUE_700, color="white", style=btn_style, on_click=lambda _: self._send_egrip_cmd("EGRIP_CLOSE")),
        ], alignment=MainAxisAlignment.CENTER, spacing=20)

        dialog_content = Column([
            Text("Load Chart (Live):", size=14, color="#888"),
            Container(
                content=self.egrip_chart, 
                height=150,
                padding=ft.padding.only(left=5, top=5, right=10, bottom=5), 
                bgcolor="#222", 
                border_radius=10
            ),
            ft.Divider(color="#444", height=2),
            Row([
                Text("Current SG Value:", size=14), 
                self.egrip_sg_result_text
            ], alignment=MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(color="#444", height=2),
            Row([Text("Grip Force (Sensitivity):", size=13, color=colors.ORANGE_400), force_label], alignment=MainAxisAlignment.SPACE_BETWEEN), 
            force_slider,
            Row([Text("SGT_THRS (Threshold):", size=13, color=colors.RED_400), thrs_label], alignment=MainAxisAlignment.SPACE_BETWEEN), 
            thrs_slider, 
            ft.Divider(color="#444", height=2), 
            Text("Manual Control:", size=13, color="#888"), 
            ctrl_buttons
        ], spacing=5, scroll=ScrollMode.AUTO)

        def close_and_save(e):
            self.gripper_settings_data["SGrip"] = list(self.current_gripper_values)
            self._save_gripper_settings()
            self.egrip_tuning_dialog.open = False
            self.page.update()

        self.egrip_tuning_dialog = AlertDialog(
            title=Text("Electric Gripper Tuning"),
            content=Container(width=550, height=650, content=dialog_content),
            actions=[ft.TextButton("Close & Save", on_click=close_and_save)]
        )
        self.page.dialog = self.egrip_tuning_dialog
        self.egrip_tuning_dialog.open = True
        self.page.update()

    def _send_egrip_cmd(self, command_str):
        if self.comm: self.comm.send_message(f"{command_str}\r\n")

    def upload_configuration(self, page_from_main=None):
        if not self.comm or not self.comm.is_open(): return
        target_page = self.page if self.page else page_from_main
        loading_dialog = None
        if target_page:
            loading_content = Container(width=300, height=150, bgcolor="#252525", border_radius=10, padding=20, content=Column([Text("Sending Data...", size=16, weight="bold"), flet.ProgressBar(width=260, color=colors.BLUE_400), Text("Don't turn off the power", size=12, color="red")], alignment=MainAxisAlignment.CENTER))
            loading_dialog = AlertDialog(content=loading_content, modal=True, bgcolor=colors.TRANSPARENT)
            target_page.dialog = loading_dialog
            loading_dialog.open = True
            target_page.update()

        try:
            time.sleep(0.5)
            for motor_id in range(1, 7):
                settings = self.motor_settings_data.get(motor_id, {})
                vals = settings.get(1, [1000, 5000, 5000, 50000, 5000])
                self.comm.send_message(f"OT,ramp,J{motor_id},{vals[0]},{vals[1]},{vals[2]},{vals[3]},{vals[4]}\r\n"); time.sleep(0.15)
                vals = settings.get(2, [5, 10, 10])
                self.comm.send_message(f"OT,current,J{motor_id},{vals[0]},{vals[1]},{vals[2]}\r\n"); time.sleep(0.15)
                vals = settings.get(3, [50000, 2000, 0])
                self.comm.send_message(f"OT,homing,J{motor_id},{vals[0]},{vals[1]},{vals[2]}\r\n"); time.sleep(0.15)
                vals = settings.get(4, [0, 5])
                self.comm.send_message(f"OT,stall,J{motor_id},{vals[0]},{vals[1]}\r\n"); time.sleep(0.15)
            
            v_vals = self.gripper_settings_data.get("VGrip", [-40, -20, 1])
            self.comm.send_message(f"OT,VGrip,{','.join(map(str, v_vals))}\r\n"); time.sleep(0.15)
            s_vals = self.gripper_settings_data.get("SGrip", [10, 20, 5000, 0])
            self.comm.send_message(f"OT,SGrip,{','.join(map(str, s_vals))}\r\n"); time.sleep(0.15)
            
            self._send_global_settings()
            
            time.sleep(1.5) 
            for _ in range(3):
                if self.comm: self.comm.send_message("CONFIG_DONE\r\n")
                time.sleep(0.5)
        except Exception: pass
        finally:
            if target_page and loading_dialog:
                loading_dialog.open = False
                target_page.snack_bar = flet.SnackBar(content=Text("Configuration Complete"), bgcolor=colors.GREEN_700)
                target_page.snack_bar.open = True
                target_page.update()

    def _build_slider_ui(self, structure_configs: list, value_configs: list, is_global: bool = False):
        self.sliders_column_container.controls.clear()
        self.sliders_labels = []
        self.slider_controls = []
        self.slider_value_displays = []

        value_display_box_style = {
            "width": 60, "height": 30, "bgcolor": colors.BLUE_GREY_800, 
            "border_radius": 5, "border": flet.border.all(1, colors.BLUE_GREY_600), 
            "alignment": alignment.center 
        }

        global_keys = ["ot_temp", "ct_temp", "safety_delay"]

        def on_live_change(e, txt_ctrl, idx, is_float):
            val = float(e.control.value)
            if is_float:
                txt_ctrl.value = f"{val:.1f}"
                save_val = round(val, 1)
            else:
                txt_ctrl.value = str(int(val))
                save_val = int(val)

            txt_ctrl.update()
            
            if is_global:
                try:
                    self.global_settings_data[global_keys[idx]] = save_val
                except Exception:
                    pass
            else:
                try:
                    self.motor_settings_data[self.selected_motor_index][self.active_slider_set_id][idx] = save_val
                except Exception:
                    pass

        def on_release(e):
            if is_global:
                self._save_global_settings()
            else:
                self._save_settings()

        for i, (s_label, s_min, s_max) in enumerate(structure_configs):
            s_val = value_configs[i] if i < len(value_configs) else 0
            s_val = max(s_min, min(s_max, s_val))
            is_offset = "OFFSET" in s_label
            num_divisions = int((s_max - s_min) * 10) if is_offset else int(s_max - s_min)
            display_str = f"{s_val:.1f}" if is_offset else str(int(s_val))

            lbl = Text(s_label, color="white", size=14, weight="bold")
            val_txt = Text(display_str, color="white", size=14, weight="bold")
            val_box = Container(content=val_txt, **value_display_box_style)
            
            sld = Slider(min=s_min, max=s_max, value=s_val, label="{value}", divisions=num_divisions, active_color=colors.BLUE_ACCENT_400, expand=True)
            sld.on_change = lambda e, t=val_txt, idx=i, fl=is_offset: on_live_change(e, t, idx, fl)
            sld.on_change_end = lambda e: on_release(e)
            
            self.sliders_labels.append(lbl)
            self.slider_controls.append(sld)
            self.slider_value_displays.append(val_txt) 
            
            self.sliders_column_container.controls.append(Container(
                content=Row(controls=[lbl, sld, val_box], spacing=10),
                padding=flet.padding.only(top=5,bottom=5)
            ))

        if self.active_slider_set_id == 4:
            tuning_btn = ElevatedButton("StallGuard Tuning", icon=flet.icons.TUNE, style=flet.ButtonStyle(bgcolor=colors.ORANGE_700, color="white", shape=flet.RoundedRectangleBorder(radius=8)), on_click=self._start_tuning_procedure)
            self.sliders_column_container.controls.append(Container(content=tuning_btn, alignment=alignment.center, padding=flet.padding.only(top=15)))
        
        if self.active_slider_set_id == 5:
            info_text = Text("⚙️ Global settings apply to the entire robot system", size=12, color=colors.BLUE_GREY_400, italic=True)
            self.sliders_column_container.controls.insert(0, Container(content=info_text, padding=flet.padding.only(bottom=10)))
    
    def _on_slider_set_select(self, idx):
        self.active_slider_set_id = idx
        if idx == 5:
            global_vals = [
                self.global_settings_data.get("ot_temp", 80),
                self.global_settings_data.get("ct_temp", 40),
                self.global_settings_data.get("safety_delay", 500)
            ]
            self._build_slider_ui(self.slider_set_definitions.get(idx, []), global_vals, is_global=True)
        else:
            self._build_slider_ui(self.slider_set_definitions.get(idx, []), self.motor_settings_data.get(self.selected_motor_index, {}).get(idx, []))
        if self.page: self.sliders_column_container.update() 
            
    def _on_motor_select(self, idx):
        self.selected_motor_index = idx
        self.motor_display.value = f"Motor: J{idx}"
        struct = self.slider_set_definitions.get(self.active_slider_set_id, [])
        vals = self.motor_settings_data.get(idx, {}).get(self.active_slider_set_id, [])

        for i in range(min(len(self.slider_controls), len(struct))):
            s_label, s_min, s_max = struct[i]
            v = vals[i] if i < len(vals) else 0
            v = max(s_min, min(s_max, v))
            self.slider_controls[i].min = s_min
            self.slider_controls[i].max = s_max
            self.slider_controls[i].value = v
            if "OFFSET" in s_label: self.slider_value_displays[i].value = f"{v:.1f}"
            else: self.slider_value_displays[i].value = str(int(v))
            self.slider_controls[i].update()
            self.slider_value_displays[i].update()
        if self.page: self.motor_display.update()

    def _restore_default_settings(self, e):
        if self.active_view_name == "render1.png":
            if self.active_slider_set_id == 5:
                self.global_settings_data = self._get_default_global_settings()
                self._save_global_settings()
                self._on_slider_set_select(5)
            else:
                self.motor_settings_data = self._get_default_settings()
                self._save_settings()
                self._on_motor_select(self.selected_motor_index)
        elif self.active_view_name in ["render2.png", "render3.png"]:
            self.content = self._create_detail_view(self.active_view_name)
            if self.page: self.update()

    def _on_send_and_save_click(self, e):
        final_command = ""
        if self.active_view_name == "render1.png":
            if self.active_slider_set_id == 5: 
                self._save_global_settings()
                ot = self.global_settings_data.get("ot_temp", 80)
                ct = self.global_settings_data.get("ct_temp", 40)
                max_spd = self.global_settings_data.get("max_speed", 100)
                safety = self.global_settings_data.get("safety_delay", 500)
                idle = self.global_settings_data.get("idle_timeout", 300)
                final_command = f"OT,global,{ot},{ct},{max_spd},{safety},{idle}"
            else:
                self._save_settings()
                option_map = { 1: "ramp", 2: "current", 3: "homing", 4: "stall" }
                opt = option_map.get(self.active_slider_set_id, "unknown")
                mot = f"J{self.selected_motor_index}"
                try:
                    vals = self.motor_settings_data[self.selected_motor_index][self.active_slider_set_id]
                    v_str = ",".join(map(str, vals))
                    final_command = f"OT,{opt},{mot},{v_str}"
                except: pass
        elif self.active_view_name == "render2.png":
            v_str = ",".join(map(str, self.current_gripper_values))
            self.gripper_settings_data["VGrip"] = list(self.current_gripper_values)
            self._save_gripper_settings()
            final_command = f"OT,VGrip,{v_str}"
        elif self.active_view_name == "render3.png":
            v_str = ",".join(map(str, self.current_gripper_values))
            self.gripper_settings_data["SGrip"] = list(self.current_gripper_values)
            self._save_gripper_settings()
            final_command = f"OT,SGrip,{v_str}"

        if final_command:
            final_command += "\n\r"
            if self.comm and self.comm.is_open():
                self.comm.send_message(final_command)
            else:
                pass

    def _get_default_settings(self):
        return {
            1: { 1: [2000, 5000, 10000, 250000, 2000], 2: [13, 24, 6], 3: [269115, 4455, 0.1], 4: [16, 0] },
            2: { 1: [2000, 5000, 8000, 200000, 2000], 2: [16, 24, 6], 3: [200000, 10000, -9.1], 4: [48, 0] },
            3: { 1: [2000, 5000, 8000, 200000, 2000], 2: [12, 22, 6], 3: [200000, 10000, 3.5], 4: [22, 9] },
            4: { 1: [3000, 10000, 15000, 400000, 3000], 2: [12, 19, 6], 3: [300000, 5000, -4.0], 4: [20, 11] },
            5: { 1: [3000, 10000, 15000, 400000, 3000], 2: [15, 20, 6], 3: [200000, 10000, -3.0], 4: [31, 9] },
            6: { 1: [3000, 8000, 12000, 250000, 3000], 2: [4, 11, 6], 3: [200000, 10000, 3.0], 4: [32, 0] }
        }

    def _load_settings(self):
        try:
            with open(self.config_file_path, "r") as f:
                loaded_data = json.load(f)
                self.motor_settings_data = {int(m): {int(s): v for s, v in sett.items()} for m, sett in loaded_data.items()}
        except:
            self.motor_settings_data = self._get_default_settings()
            self._save_settings()

    def _save_settings(self):
        try:
            with open(self.config_file_path, "w") as f:
                json.dump(self.motor_settings_data, f, indent=4)
        except Exception:
            pass

    def _load_global_settings(self):
        try:
            with open("global_settings.json", "r") as f:
                self.global_settings_data = json.load(f)
        except:
            self.global_settings_data = self._get_default_global_settings()
            self._save_global_settings()

    def _save_global_settings(self):
        try:
            with open("global_settings.json", "w") as f:
                json.dump(self.global_settings_data, f, indent=4)
        except Exception:
            pass

    def _get_default_global_settings(self):
        return {
            "sensor_1_ot": 50, "sensor_1_ct": 70,
            "sensor_2_ot": 50, "sensor_2_ct": 70,
            "sensor_3_ot": 50, "sensor_3_ct": 70,
            "sensor_4_ot": 50, "sensor_4_ct": 70,
            "mag_time": 2528
        }

    def _load_gripper_settings(self):
        try:
            with open("gripper_settings.json", "r") as f:
                self.gripper_settings_data = json.load(f)
        except:
            self.gripper_settings_data = self._get_default_gripper_settings()
            self._save_gripper_settings()

    def _save_gripper_settings(self):
        try:
            with open("gripper_settings.json", "w") as f:
                json.dump(self.gripper_settings_data, f, indent=4)
        except Exception:
            pass

    def _get_default_gripper_settings(self):
        return {
            "VGrip": [-40, -20],
            "SGrip": [4, 11, 91931]
        }

    def _restore_global_defaults(self, e):
        self.global_settings_data = self._get_default_global_settings()
        self._save_global_settings()
        self.content = self._create_detail_view("global_settings")
        if self.page: self.update()

    def _send_global_settings(self, e=None):
        self._save_global_settings()
        
        mag_time = self.global_settings_data.get("mag_time", 2)
        
        final_command = f"OT,global,{mag_time}\r\n"
        if self.comm and self.comm.is_open():
            self.comm.send_message(final_command)
        else:
            pass

    def reset_view(self):
        self.content = self._create_main_view()
        if self.page: self.page.update()

    def on_image_click(self, e, image_path: str):
        self.content = self._create_detail_view(image_path)
        if self.page: self.update()

    def _create_clickable_panel(self, image_name: str, map_key: str):
        panel_style = { "bgcolor": "#2D2D2D", "border_radius": 10, "border": flet.border.all(2, "#555555"), "clip_behavior": flet.ClipBehavior.ANTI_ALIAS, "expand": True }
        return flet.GestureDetector(
            on_tap=lambda e: self.on_image_click(e, image_name),
            content=Container(content=Image(src=image_name, fit=flet.ImageFit.COVER, expand=True), **panel_style),
            expand=True
        )

    def _create_main_view(self):
        self.active_view_name = "MAIN"
        panel1 = self._create_clickable_panel("render1.png", "render1.png")
        panel2 = self._create_clickable_panel("render2.png", "render2.png")
        panel3 = self._create_clickable_panel("render3.png", "render3.png")
        panel4 = self._create_global_settings_panel()
        return Row(controls=[
            Container(content=panel1, expand=2),
            Container(content=Column([panel2, panel3], spacing=10, expand=True), expand=1),
            Container(content=Column([panel4], spacing=10, expand=True), expand=1)
        ], spacing=10, expand=True)

    def _create_global_settings_panel(self):
        panel_style = { 
            "bgcolor": "#2D2D2D", 
            "border_radius": 10, 
            "border": flet.border.all(2, "#555555"), 
            "expand": True 
        }
        
        panel_content = ft.Stack(
            controls=[
                Container(
                    content=flet.Icon(flet.icons.SETTINGS, size=140, color=colors.CYAN_400),
                    alignment=alignment.center,
                    expand=True,
                ),
                Container(
                    content=Text("GLOBAL SETTINGS", size=20, weight="bold", color="white", text_align=flet.TextAlign.CENTER),
                    alignment=alignment.bottom_center,
                    padding=flet.padding.only(bottom=15),
                )
            ],
            expand=True
        )
        
        return flet.GestureDetector(
            on_tap=lambda e: self.on_image_click(e, "global_settings"),
            content=Container(content=panel_content, **panel_style),
            expand=True
        )

    def _get_gripper_config(self, image_name):
        if image_name == "render2.png": 
            vals = self.gripper_settings_data.get("VGrip", [-40, -20])
            return { "title": "VACUUM GRIPPER", "image": "Gripper1.png", "sliders": [("Pump On Pressure [kPa]", -50, -10, vals[0]), ("Pump Off Pressure [kPa]", -40, 0, vals[1])] }
        elif image_name == "render3.png": 
            vals = self.gripper_settings_data.get("SGrip", [10, 20, 5000, 0, 10])
            return { "title": "ELECTRIC GRIPPER", "image": "Gripper2.png", "sliders": [("IHOLD", 0, 31, vals[0]), ("IRUN", 0, 31, vals[1]), ("Grip Speed", 200, 100000, vals[2])] }
        return None

    def _create_detail_view(self, image_name: str):
        self.active_view_name = image_name 
        # Base styles
        podramka_style = { "bgcolor": "#2D2D2D", "border_radius": 10, "border": flet.border.all(1, "#555555"), "padding": 10 }
        podramka_obrazkowa_style = podramka_style.copy()
        podramka_obrazkowa_style.pop("padding", None)
        podramka_obrazkowa_style["clip_behavior"] = flet.ClipBehavior.ANTI_ALIAS
        
        # --- CASE 1: MAIN ROBOT SETTINGS ---
        if image_name == "render1.png":
            # Left Panel: Motor Select
            btn_ctrls = [ElevatedButton(text=name, height=45, width=120, expand=False, style=flet.ButtonStyle(bgcolor=colors.BLUE_GREY_700, color=colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)), on_click=lambda e, i=idx: self._on_motor_select(i)) for idx, name in enumerate(self.motor_names, start=1)]
            
            # Middle Panel: Top Menu & Sliders
            top_btns = [ElevatedButton(text=name, height=45, expand=True, style=flet.ButtonStyle(bgcolor=colors.BLUE_GREY_600, color=colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)), on_click=lambda e, i=i: self._on_slider_set_select(i)) for i, name in enumerate(["Ramp", "Current", "Home"], start=1)]
            default_btn = ElevatedButton(text="DEFAULT", height=45, width=140, style=flet.ButtonStyle(bgcolor=colors.RED_700, color=colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)), on_click=self._restore_default_settings)
            
            top_toolbar = Row(controls=[*top_btns, default_btn], spacing=5, expand=True)

            self.sliders_column_container = Column(controls=[], spacing=10, expand=True, scroll=ScrollMode.ADAPTIVE)
            self._build_slider_ui(self.slider_set_definitions.get(1, []), self.motor_settings_data.get(1, {}).get(1, []))
            
            # Right Panel: Image & Save
            self.motor_display = Text("Motor: J1", color="white", size=18, weight="bold")
            send_save_button = ElevatedButton(text="Send & Save", height=40, expand=True, style=flet.ButtonStyle(bgcolor=colors.GREEN_700, color=colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)), on_click=self._on_send_and_save_click)
            
            # LAYOUT STRUCTURE
            return Row(controls=[
                Container(content=Column(controls=btn_ctrls, spacing=10, expand=True), **podramka_style, width=140, expand=False),
                
                # MIDDLE
                Container(content=Column(controls=[
                    Container(content=top_toolbar, height=60, bgcolor="#2D2D2D", border_radius=10),
                    self.sliders_column_container
                ], spacing=10, expand=True), **{**podramka_style}, expand=True),
                
                # RIGHT
                Container(content=Column(controls=[
                    Container(content=self.motor_display, height=50, alignment=alignment.center),
                    Container(content=Image(src="stepper60.png", fit=flet.ImageFit.CONTAIN, expand=True), **podramka_obrazkowa_style, expand=True),
                    Row(controls=[send_save_button])
                ], spacing=10, expand=True), **podramka_style, width=150, expand=False)
                
            ], spacing=10, expand=True)

        # --- CASE 2: GLOBAL SETTINGS ---
        elif image_name == "global_settings":
            def create_temp_slider(label, min_val, max_val, key, color):
                start_val = self.global_settings_data.get(key, 50)
                val_txt = Text(f"{int(start_val)}°", color="white", size=16, weight="bold")
                
                def on_change(e, v_txt=val_txt, setting_key=key):
                    val = int(e.control.value)
                    v_txt.value = f"{val}°"
                    v_txt.update()
                    self.global_settings_data[setting_key] = val
                
                def on_release(e):
                    self._save_global_settings()
                
                slider = Slider(min=min_val, max=max_val, value=start_val, label="{value}°C",
                               active_color=color, expand=True,
                               on_change=on_change, on_change_end=on_release)
                
                return Row(controls=[
                    Text(label, color=color, size=14, weight="bold", width=30),
                    slider,
                    Container(content=val_txt, width=50, height=32, bgcolor=colors.BLUE_GREY_800,
                             border_radius=5, border=flet.border.all(1, color), alignment=alignment.center)
                ], spacing=2, height=40)
            
            def create_sensor_group(sensor_num):
                ot_slider = create_temp_slider("OT", 30, 80, f"sensor_{sensor_num}_ot", colors.ORANGE_400)
                ct_slider = create_temp_slider("CT", 50, 100, f"sensor_{sensor_num}_ct", colors.RED_400)
                
                return Container(
                    content=Column([
                        Text(f"SENSOR {sensor_num}", size=15, weight="bold", color=colors.CYAN_400, text_align=flet.TextAlign.CENTER),
                        ot_slider,
                        ct_slider,
                    ], spacing=2, horizontal_alignment=flet.CrossAxisAlignment.CENTER),
                    bgcolor="#252525",
                    border_radius=10,
                    border=flet.border.all(1, colors.BLUE_GREY_700),
                    padding=15,
                    expand=True
                )
            
            sensors_row = Row([
                create_sensor_group(1), 
                create_sensor_group(2), 
                create_sensor_group(3), 
                create_sensor_group(4)
            ], spacing=15)
            
            other_sliders = []
            for label, min_val, max_val, key, def_val in [
                ("SOLENOID ON TIME [s]", 0, 10000, "mag_time", 2)
            ]:
                start_val = self.global_settings_data.get(key, def_val)
                val_txt = Text(str(int(start_val)), color="white", size=14, weight="bold")
                
                def on_change_other(e, v_txt=val_txt, setting_key=key):
                    val = int(e.control.value)
                    v_txt.value = str(val)
                    v_txt.update()
                    self.global_settings_data[setting_key] = val
                
                def on_release_other(e):
                    self._save_global_settings()
                
                slider = Slider(min=min_val, max=max_val, value=start_val, label="{value}",
                               active_color=colors.CYAN_400, expand=True,
                               on_change=on_change_other, on_change_end=on_release_other)
                other_sliders.append(Row(controls=[
                    Text(label, color="white", size=13, weight="bold", width=150),
                    slider,
                    Container(content=val_txt, width=60, height=32, bgcolor=colors.BLUE_GREY_800,
                             border_radius=5, border=flet.border.all(1, colors.BLUE_GREY_600), alignment=alignment.center)
                ], spacing=10, height=40))
            
            other_settings_container = Container(
                content=Column([
                    Row([
                        flet.Icon(flet.icons.TUNE, size=20, color=colors.CYAN_400),
                        Text("Other Settings", size=14, weight="bold", color=colors.CYAN_400)
                    ], spacing=8),
                    Column(controls=other_sliders, spacing=10),
                ], spacing=10),
                bgcolor="#252525",
                border_radius=8,
                border=flet.border.all(1, colors.BLUE_GREY_700),
                padding=15,
            )

            action_buttons = Row([
                ElevatedButton("DEFAULT", height=32, width=140,
                              style=flet.ButtonStyle(bgcolor=colors.RED_700, color=colors.WHITE, shape=flet.RoundedRectangleBorder(radius=6)), 
                              on_click=self._restore_global_defaults),
                ElevatedButton("Send & Save", height=32, width=130,
                              style=flet.ButtonStyle(bgcolor=colors.GREEN_700, color=colors.WHITE, shape=flet.RoundedRectangleBorder(radius=6)), 
                              on_click=self._send_global_settings)
            ], spacing=10)
            
            return Column(controls=[
                Row([
                    Row([
                        flet.Icon(flet.icons.SETTINGS, size=28, color=colors.CYAN_400),
                        Text("GLOBAL SETTINGS", size=20, weight="bold", color="white"),
                    ], spacing=10),
                    Container(expand=True), 
                    action_buttons
                ], alignment=MainAxisAlignment.SPACE_BETWEEN),
                flet.Divider(color=colors.BLUE_GREY_700, height=5),
                sensors_row,
                other_settings_container,
            ], spacing=15, expand=True)

        # --- CASE 3: GRIPPERS ---
        else:
            config = self._get_gripper_config(image_name)
            if not config: return Text("Config Error")
            self.current_gripper_values = [item[3] for item in config["sliders"]]
            sliders_list = []
            for index, (label, min_val, max_val, start_val) in enumerate(config["sliders"]):
                val_txt = Text(str(int(start_val)), color="white", size=14, weight="bold")
                def on_change_local(e, v_txt=val_txt, idx=index):
                    v_txt.value = str(int(e.control.value)); v_txt.update(); self.current_gripper_values[idx] = int(e.control.value)
                sliders_list.append(Container(content=Row(controls=[Text(label, color="white", size=14, weight="bold", width=120), Slider(min=min_val, max=max_val, value=start_val, label="{value}", active_color=colors.BLUE_ACCENT_400, expand=True, on_change=on_change_local), Container(content=val_txt, **{"width": 60, "height": 30, "bgcolor": colors.BLUE_GREY_800, "border_radius": 5, "border": flet.border.all(1, colors.BLUE_GREY_600), "alignment": alignment.center})], alignment=MainAxisAlignment.SPACE_BETWEEN, spacing=10), padding=flet.padding.only(bottom=5)))
            
            action_buttons_row = [
                ElevatedButton("DEFAULT", height=40, width=140, style=flet.ButtonStyle(bgcolor=colors.RED_700, color=colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)), on_click=self._restore_default_settings),
                ElevatedButton("Send & Save", height=40, width=150, style=flet.ButtonStyle(bgcolor=colors.GREEN_700, color=colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)), on_click=self._on_send_and_save_click)
            ]

            if image_name == "render3.png":
                tuning_btn = ElevatedButton(
                    "TUNING", height=40, width=140, icon=icons.TUNE,
                    style=flet.ButtonStyle(bgcolor=colors.ORANGE_700, color=colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)),
                    on_click=self._open_egrip_tuning
                )
                action_buttons_row.insert(1, tuning_btn) 

            return Row(controls=[
                Container(
                    content=Image(src=config["image"], fit=flet.ImageFit.CONTAIN), 
                    width=450, 
                    expand=False, 
                    **podramka_obrazkowa_style  
                ),
                Container(content=Column(controls=[
                    Text(config["title"], size=20, weight="bold", color="white"), 
                    Column(controls=sliders_list, scroll=ScrollMode.ADAPTIVE, expand=True), 
                    Row(controls=action_buttons_row, alignment=MainAxisAlignment.END, spacing=10)
                ], spacing=15, expand=True), **podramka_style, expand=True)
            ], spacing=10, expand=True)