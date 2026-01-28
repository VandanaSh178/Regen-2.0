import time
from vehicle_db import VEHICLE_DB
from datetime import datetime

class GateController:
    def __init__(self):
        self.current_state = "CLOSED"
        self.open_time = 0
        self.gate_duration = 10  # Seconds to stay open
        self.student_start = 6   # 6 AM
        self.student_end = 22    # 10 PM

    def evaluate_access(self, plate, confidence):
        """
        Logic for Flask /gate_status
        Returns: (status, vehicle_type, reason)
        """
        now = time.time()
        
        # 1. Database Lookup
        info = VEHICLE_DB.get(plate, {"type": "Visitor", "owner": "Unknown"})
        v_type = info["type"]
        current_hour = datetime.now().hour

        # 2. Blacklist Check (Priority 1)
        if v_type == "Blacklist":
            self.current_state = "CLOSED"
            return "BLOCK", v_type, "SECURITY ALERT: Vehicle Blacklisted"

        # 3. Student Time Restriction (Priority 2)
        if v_type == "Student":
            if not (self.student_start <= current_hour < self.student_end):
                self.current_state = "CLOSED"
                return "BLOCK", v_type, "Access Denied: Outside Student Hours"

        # 4. Gate State Management
        if plate != "----" and confidence > 40:
            self.current_state = "OPEN"
            self.open_time = now
            return "OPEN", v_type, "Access Granted"

        # Auto-close logic
        if self.current_state == "OPEN" and (now - self.open_time) > self.gate_duration:
            self.current_state = "CLOSED"

        return self.current_state, "IDLE", "Waiting..."

gate_manager = GateController()