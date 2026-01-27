# 🛡️ NIT Manipur: Smart Campus Security & ANPR System

An AI-powered Automated Number Plate Recognition (ANPR) system designed for campus security. This system uses computer vision to detect vehicles, verify credentials against a local database, and automate gate control.

## 🚀 Key Features
- **Real-time Detection:** Powered by YOLOv8 for high-speed plate localization.
- **Character Recognition:** EasyOCR engine for precise plate text extraction.
- **Admin SOC Dashboard:** Secure login for security officers to monitor live traffic.
- **Vehicle Management:** CRUD (Create, Read, Update, Delete) functionality for authorized vehicles.
- **Security Auditing:** Automated PDF report generation for official record-keeping.
- **Instant Alerts:** Visual and data alerts for blacklisted or unauthorized vehicles.

## 🛠️ Tech Stack
- **Backend:** Flask (Python)
- **AI/ML:** YOLOv8 (Ultralytics), EasyOCR
- **Frontend:** HTML5, CSS3 (Modern Dark Theme), JavaScript (Vanilla)
- **Database:** Flat-file Python dictionary for high-speed lookups
- **Reporting:** ReportLab PDF Engine

## 📥 Installation

1. **Clone the repository:**
   ```bash
   git clone <your-repo-link>
   cd backend