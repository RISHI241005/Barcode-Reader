# Barcode Reader — System Architecture Document (v1.0.0)

This document provides a comprehensive technical overview of the **Barcode Reader** system architecture, design patterns, computer vision pipelines, database models, and security boundaries.

---

## 1. High-Level Architecture Overview

The system is designed following **Clean Layered Architecture** with distinct separation of concerns between the Presentation, Service, Repository, Computer Vision Engine, and Persistence layers.

```mermaid
graph TD
    subgraph UI ["Presentation Layer (CustomTkinter GUI)"]
        MainApp["BarcodeReaderApp (Dual Mode Scanner)"]
        LoginDlg["LoginWindow (Auth & First-Admin Setup)"]
        HistoryDlg["ScanHistoryWindow (Personal / System Scans)"]
        CatalogDlg["ProductCatalogWindow (Search & Manage Cache)"]
        DashDlg["AnalyticsDashboardWindow (KPIs & Daily Charts)"]
        AdminDlg["AdminPanelWindow (User Mgmt, Scans, Audit)"]
        ProfileDlg["ProfileModal (Profile & Password Change)"]
    end

    subgraph Service ["Business Logic & Services"]
        AuthSvc["AuthService (Bcrypt / Lockout / Session)"]
        AuthzSvc["AuthorizationService (RBAC Permissions)"]
        SessionMgr["SessionManager (Inactivity Timeout)"]
        ProdSvc["ProductService (Cache-First Orchestrator)"]
    end

    subgraph CV ["Computer Vision & Scanning Engine"]
        Detector["BarcodeDetector (ZXing-C++ / PyZBar / CV)"]
        ImgProc["ImageProcessor (11-Stage Pipeline)"]
        CamScanner["CameraScanner (Threaded DirectShow VideoCapture)"]
    end

    subgraph Repo ["Repository Layer"]
        UserRepo["UserRepository (User CRUD & Last-Admin Guard)"]
        ScanRepo["ScanRepository (User-Scoped Scans)"]
        ProdRepo["ProductRepository (MySQL Product Cache)"]
        AuditRepo["AuditRepository (Security & Admin Trail)"]
        AnalyticsRepo["AnalyticsRepository (SQL Aggregations)"]
    end

    subgraph Persistence ["Data & External Providers"]
        MySQL["Local MySQL Server (localhost:3306)"]
        OpenFoodFacts["Open Food Facts REST API"]
    end

    MainApp --> Detector
    MainApp --> CamScanner
    MainApp --> ProdSvc
    MainApp --> ScanRepo
    MainApp --> SessionMgr
    MainApp --> AuthzSvc

    CamScanner --> Detector
    Detector --> ImgProc

    ProdSvc --> ProdRepo
    ProdSvc --> OpenFoodFacts

    AuthSvc --> UserRepo
    AuthSvc --> SessionMgr
    AuthSvc --> AuditRepo

    UserRepo --> MySQL
    ScanRepo --> MySQL
    ProdRepo --> MySQL
    AuditRepo --> MySQL
    AnalyticsRepo --> MySQL
```

---

## 2. Computer Vision & Barcode Decoding Pipeline

The image scanning engine incorporates an **11-stage fallback pipeline** with automatic quality metrics evaluation and rotation compensation:

```mermaid
flowchart TD
    Start["Input Image (File Upload or Camera Frame)"] --> CheckDim["Check Dimensions (>2500px -> Scale to 1920px)"]
    CheckDim --> CalcMetrics["Calculate Image Metrics (Contrast, Sharpness, Brightness)"]
    CalcMetrics --> Stage0["Pass 1: Original Raw Image"]
    
    Stage0 --> Decided{"Barcode Found?"}
    Decided -- Yes --> Deduplicate["Deduplicate (IoU & Distance) -> Checksum Validation -> Return"]
    Decided -- No --> Stage1["Pass 2: Grayscale Conversion"]
    
    Stage1 --> Decided1{"Barcode Found?"}
    Decided1 -- Yes --> Deduplicate
    Decided1 -- No --> Stage2["Pass 3: Otsu Thresholding"]
    
    Stage2 --> Decided2{"Barcode Found?"}
    Decided2 -- Yes --> Deduplicate
    Decided2 -- No --> Stage3["Pass 4: Adaptive Gaussian Thresholding"]
    
    Stage3 --> Decided3{"Barcode Found?"}
    Decided3 -- Yes --> Deduplicate
    Decided3 -- No --> Stage4["Pass 5: CLAHE (Contrast Limited Adaptive Histogram Equalization)"]
    
    Stage4 --> Decided4{"Barcode Found?"}
    Decided4 -- Yes --> Deduplicate
    Decided4 -- No --> Stage5["Pass 6: Sharpening Filter Kernel"]
    
    Stage5 --> Decided5{"Barcode Found?"}
    Decided5 -- Yes --> Deduplicate
    Decided5 -- No --> Stage6["Pass 7: Morphological Gradient"]
    
    Stage6 --> Decided6{"Barcode Found?"}
    Decided6 -- Yes --> Deduplicate
    Decided6 -- No --> Stage7["Pass 8: Bilateral Filtering (Denoise)"]
    
    Stage7 --> Decided7{"Barcode Found?"}
    Decided7 -- Yes --> Deduplicate
    Decided7 -- No --> Stage8["Pass 9: Super-Resolution Upscaling (Small Barcodes)"]
    
    Stage8 --> Decided8{"Barcode Found?"}
    Decided8 -- Yes --> Deduplicate
    Decided8 -- No --> StageRot["Pass 10-12: 90°, 180°, 270° Rotations (with Inverse Coordinate Transform)"]
    
    StageRot --> DecidedRot{"Barcode Found?"}
    DecidedRot -- Yes --> Deduplicate
    DecidedRot -- No --> NoBarcode["Return No Barcode Detected Report with Quality Guidance"]
```

---

## 3. Real-Time Camera Scanning & Stability Model

The live webcam scanning component operates on a dedicated capture thread using OpenCV's DirectShow backend:

* **Threaded Frame Acquisition**: `cv2.VideoCapture` runs asynchronously at 30 FPS.
* **Reticle Guide Overlay**: Visual HUD guide marking the optimal scanning area.
* **Fast-Mode Decoding**: Lightweight single-pass decoding on live frames minimizing latency.
* **Consecutive-Frame Stability ($N=3$)**: Requires 3 continuous detections of identical payload before emitting a confirmed scan event.
* **Duplicate Cooldown ($2.0\text{s}$)**: Prevents duplicate save events when holding a barcode in front of the camera.
* **Auto-Release Safety**: Automatically releases the webcam on mode switch, user logout, inactivity timeout, or window close (`WM_DELETE_WINDOW`).

---

## 4. Product Intelligence & Cache-First Architecture

```mermaid
sequenceDiagram
    actor User
    participant App as BarcodeReaderApp
    participant Svc as ProductService
    participant Repo as ProductRepository
    participant MySQL as MySQL Cache (products)
    participant API as Open Food Facts REST API

    User->>App: Click [ 🔎 Product ] on Barcode Card
    App->>Svc: lookup_product(barcode)
    Svc->>Repo: get_product_by_barcode(barcode)
    Repo->>MySQL: SELECT * FROM products WHERE barcode = ?
    
    alt Cache Hit (Product Exists Locally)
        MySQL-->>Repo: Return product record
        Repo-->>Svc: Product object
        Svc-->>App: Product object (is_from_cache=True)
        App->>User: Open ProductDetailsModal (Instant)
    else Cache Miss (Product Not in Cache)
        MySQL-->>Repo: None
        Repo-->>Svc: None
        Svc->>API: GET https://world.openfoodfacts.org/api/v2/product/{barcode}.json
        alt API Success (200 OK)
            API-->>Svc: Product JSON payload
            Svc->>Repo: save_or_update_product(product)
            Repo->>MySQL: INSERT INTO products ... ON DUPLICATE KEY UPDATE ...
            Svc-->>App: Product object (is_from_cache=False)
            App->>User: Open ProductDetailsModal & Update Cache
        else API Offline / Not Found
            API-->>Svc: 404 Not Found / Timeout
            Svc-->>App: None, "Product not found / offline"
            App->>User: Display Friendly Notice (Barcode is preserved)
        end
    end
```

---

## 5. Security & Authentication Architecture

1. **Password Security**:
   * Stored exclusively as bcrypt one-way hashes (`bcrypt.hashpw(password, bcrypt.gensalt(12))`).
   * Passwords are never stored in plaintext, sessions, or logs.
2. **Brute-Force Protection**:
   * Per-identifier failed attempt tracking with temporary lockout after 5 consecutive failed attempts (`MAX_LOGIN_ATTEMPTS=5`, `LOGIN_LOCKOUT_MINUTES=5`).
3. **Session Inactivity Management**:
   * In-memory session tracking `login_time` and `last_activity_time`.
   * Automatic session expiration after 30 minutes of inactivity (`SESSION_TIMEOUT_MINUTES=30`).
4. **Data Isolation & Parameterized SQL**:
   * Every SQL query is parameterized against SQL injection attacks.
   * Normal user scan queries strictly enforce `WHERE user_id = current_user.id`.
   * Normal user deletion queries strictly enforce `DELETE FROM barcode_scans WHERE id = %s AND user_id = %s`.
5. **Last-Admin Protection**:
   * System prohibits deactivating or demoting the final active administrator account.
