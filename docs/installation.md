# Barcode Reader — Installation & Deployment Guide (v1.0.0)

This guide provides step-by-step instructions for setting up, configuring, and running the **Barcode Reader** desktop application on Windows.

---

## 1. System Requirements

* **Operating System**: Windows 10 or Windows 11 (64-bit)
* **Python Version**: Python 3.11+ (Tested on Python 3.14)
* **Database**: Local MySQL Server 8.0+ (running on `localhost:3306`)
* **Hardware**:
  * RAM: 4 GB minimum (8 GB recommended)
  * Disk Space: 500 MB free space
  * Webcam: Built-in or external USB camera (for Live Camera Scanner mode)
* **Network**: Internet connection required for initial product API lookups (not required for offline cache or local barcode decoding)

---

## 2. Step-by-Step Installation from Source

### Step 1: Clone or Copy Repository
```powershell
cd "C:\path\to\your\workspace"
git clone https://github.com/yourusername/barcode-reader.git
cd "barcode-reader"
```

### Step 2: Create and Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install Required Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
copy .env.example .env
```

Open `.env` and configure your local MySQL credentials:
```ini
# Local MySQL Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_NAME=barcode_reader
DB_USER=root
DB_PASSWORD=your_actual_mysql_password

# Authentication & Session Security
SESSION_TIMEOUT_MINUTES=30
MAX_LOGIN_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=5

# External Product API Settings
PRODUCT_API_BASE_URL=https://world.openfoodfacts.org/api/v2/product/
PRODUCT_API_TIMEOUT=5
```

### Step 5: Initialize MySQL Database
Run the automated database setup utility:
```powershell
python setup_database.py
```

Expected output:
```text
============================================================
  Barcode Reader — MySQL Database Setup Wizard (v1.0.0)
============================================================

Target Database Configuration:
  • Host:     localhost
  • Port:     3306
  • Database: barcode_reader
  • User:     root

Connecting to MySQL Server...
✓ MySQL connection established successfully.

Initializing database and applying safe table migrations...
✓ Database verified/created.
✓ Table `users` ready.
✓ Table `barcode_scans` ready (with user_id scoping).
✓ Table `products` ready.
✓ Table `audit_logs` ready.

============================================================
🎉 Database setup completed successfully! You can now launch app.py.
============================================================
```

### Step 6: Launch Application
```powershell
python app.py
```

---

## 3. First-Run Setup Workflow

1. On first launch when no administrator exists, the application presents the **Initial Administrator Setup** dialog.
2. Enter your desired Admin Username, Email, and Password (min. 6 characters).
3. Click **Create Administrator**.
4. Log in with your new administrator credentials.
5. Create normal user accounts or access the **🛡️ Admin Panel** to manage the system.

---

## 4. Running the Standalone Executable Package

The application can also be distributed as a standalone Windows executable:

```powershell
cd dist\BarcodeReader
.\BarcodeReader.exe
```

*Note: The executable requires a `.env` file in the same directory (or parent directory) configured with local MySQL credentials.*

---

## 5. Troubleshooting Common Issues

### 1. MySQL Connection Refused (`1045 Access Denied` or `2003 Can't connect`)
* Ensure the MySQL Server service is running in Windows Services (`services.msc` -> `MySQL80` -> Start).
* Verify `DB_USER` and `DB_PASSWORD` in your `.env` file match your MySQL credentials.
* Test manual login: `mysql -u root -p`.

### 2. Camera Access Error / Black Video Feed
* Ensure Windows Camera privacy settings allow desktop apps to access the camera (*Settings* -> *Privacy & Security* -> *Camera*).
* Ensure other applications (Zoom, Teams, Skype) are not actively using the webcam.
* If using an external USB webcam, select `Camera 1` from the camera selector dropdown in the Camera Scanner toolbar.

### 3. Product Not Found Notice
* If a valid barcode was decoded but product information was not found, the barcode may not be cataloged in the public Open Food Facts database. The decoded barcode payload remains intact and can still be copied, saved, and analyzed.
