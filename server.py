#!/usr/bin/env python3
"""
Flask Server for Tuition Management App
Mirrors Flutter Hive data structure with JSON file persistence
Includes student management and admission request system
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import threading
import time

app = Flask(__name__, static_folder='web')
# Enable CORS for all domains (Cloudflare tunnel + mobile apps)
CORS(app, resources={r"/*": {"origins": "*"}})

# Data file paths
STUDENTS_FILE = 'students_data.json'
ADMISSIONS_FILE = 'admission_requests.json'
BACKUP_DIR = 'backups'

# Auto-save lock
save_lock = threading.Lock()

# ==================== Data Persistence ====================

def load_json_file(filepath: str, default_data: dict) -> dict:
    """Load JSON file with error handling"""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading {filepath}: {e}. Using default data.")
            backup_corrupted_file(filepath)
    return default_data


def save_json_file(filepath: str, data: dict):
    """Save JSON file with atomic write"""
    with save_lock:
        temp_file = f"{filepath}.tmp"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, filepath)  # Atomic operation
        except IOError as e:
            print(f"Error saving {filepath}: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)


def backup_corrupted_file(filepath: str):
    """Backup corrupted file before overwriting"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f"{os.path.basename(filepath)}.{timestamp}.bak")
    try:
        os.rename(filepath, backup_path)
        print(f"Corrupted file backed up to: {backup_path}")
    except Exception as e:
        print(f"Could not backup corrupted file: {e}")


def auto_backup():
    """Create periodic backups"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if os.path.exists(STUDENTS_FILE):
        backup_path = os.path.join(BACKUP_DIR, f"students_data_{timestamp}.json")
        with open(STUDENTS_FILE, 'r') as src, open(backup_path, 'w') as dst:
            dst.write(src.read())
    
    if os.path.exists(ADMISSIONS_FILE):
        backup_path = os.path.join(BACKUP_DIR, f"admission_requests_{timestamp}.json")
        with open(ADMISSIONS_FILE, 'r') as src, open(backup_path, 'w') as dst:
            dst.write(src.read())


# ==================== Data Models (matching Hive structure) ====================

"""
Student data structure matching Flutter Hive model:
{
    "id": int,
    "name": str,
    "className": str,
    "school": str (optional),
    "guardianPhone": str,
    "guardianName": str (optional),
    "studentPhone": str (optional),
    "address": str (optional),
    "dob": int (milliseconds since epoch),
    "admissionDate": int (milliseconds since epoch),
    "subjects": List[str],
    "fees": float,
    "profileImagePath": str (optional),
    "createdAt": int (milliseconds since epoch),
    "yearlyMonthStatus": Dict[str, Dict[int, int]],  # "2025" -> {1: 0, 2: 1, ...}
    "yearlyPaymentRecords": Dict[str, Dict[int, PaymentRecord]],
    "pendingFeesReminders": Dict[str, List[int]]
}

PaymentRecord:
{
    "paidDate": int (milliseconds),
    "amount": float,
    "notes": str (optional),
    "paymentMethod": str (cash/online/upi/bank)
}
"""

# Initialize data storage
students_data = load_json_file(STUDENTS_FILE, {"students": [], "next_id": 1})
admissions_data = load_json_file(ADMISSIONS_FILE, {"requests": [], "next_id": 1})


def get_next_student_id() -> int:
    """Get next available student ID"""
    current_id = students_data["next_id"]
    students_data["next_id"] += 1
    save_json_file(STUDENTS_FILE, students_data)
    return current_id


def get_next_admission_id() -> int:
    """Get next available admission request ID"""
    current_id = admissions_data["next_id"]
    admissions_data["next_id"] += 1
    save_json_file(ADMISSIONS_FILE, admissions_data)
    return current_id


# ==================== Student API Endpoints ====================

@app.route('/api/students', methods=['GET'])
def get_all_students():
    """Get all students"""
    return jsonify({
        "success": True,
        "students": students_data["students"],
        "count": len(students_data["students"])
    })


@app.route('/api/students/<int:student_id>', methods=['GET'])
def get_student(student_id: int):
    """Get single student by ID"""
    student = next((s for s in students_data["students"] if s["id"] == student_id), None)
    if student:
        return jsonify({"success": True, "student": student})
    return jsonify({"success": False, "error": "Student not found"}), 404


@app.route('/api/students', methods=['POST'])
def add_student():
    """Add new student"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ["name", "className", "guardianPhone", "dob", "admissionDate", "subjects", "fees"]
        for field in required_fields:
            if field not in data:
                return jsonify({"success": False, "error": f"Missing required field: {field}"}), 400
        
        # Create new student with auto-increment ID
        student = {
            "id": get_next_student_id(),
            "name": data["name"],
            "className": data["className"],
            "school": data.get("school"),
            "guardianPhone": data["guardianPhone"],
            "guardianName": data.get("guardianName"),
            "studentPhone": data.get("studentPhone"),
            "address": data.get("address"),
            "dob": data["dob"],  # milliseconds since epoch
            "admissionDate": data["admissionDate"],
            "subjects": data["subjects"],
            "fees": float(data["fees"]),
            "profileImagePath": data.get("profileImagePath"),
            "createdAt": int(datetime.now().timestamp() * 1000),
            "yearlyMonthStatus": data.get("yearlyMonthStatus", {}),
            "yearlyPaymentRecords": data.get("yearlyPaymentRecords", {}),
            "pendingFeesReminders": data.get("pendingFeesReminders", {})
        }
        
        students_data["students"].append(student)
        save_json_file(STUDENTS_FILE, students_data)
        
        return jsonify({"success": True, "student": student, "id": student["id"]}), 201
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/students/<int:student_id>', methods=['PUT'])
def update_student(student_id: int):
    """Update existing student"""
    try:
        student = next((s for s in students_data["students"] if s["id"] == student_id), None)
        if not student:
            return jsonify({"success": False, "error": "Student not found"}), 404
        
        data = request.json
        
        # Update fields
        updatable_fields = [
            "name", "className", "school", "guardianPhone", "guardianName",
            "studentPhone", "address", "dob", "admissionDate", "subjects",
            "fees", "profileImagePath", "yearlyMonthStatus", "yearlyPaymentRecords",
            "pendingFeesReminders"
        ]
        
        for field in updatable_fields:
            if field in data:
                if field == "fees":
                    student[field] = float(data[field])
                else:
                    student[field] = data[field]
        
        save_json_file(STUDENTS_FILE, students_data)
        
        return jsonify({"success": True, "student": student})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/students/<int:student_id>', methods=['DELETE'])
def delete_student(student_id: int):
    """Delete student"""
    try:
        student = next((s for s in students_data["students"] if s["id"] == student_id), None)
        if not student:
            return jsonify({"success": False, "error": "Student not found"}), 404
        
        students_data["students"].remove(student)
        save_json_file(STUDENTS_FILE, students_data)
        
        return jsonify({"success": True, "message": "Student deleted successfully"})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/students/<int:student_id>/payment', methods=['POST'])
def record_payment(student_id: int):
    """Record payment for a student"""
    try:
        student = next((s for s in students_data["students"] if s["id"] == student_id), None)
        if not student:
            return jsonify({"success": False, "error": "Student not found"}), 404
        
        data = request.json
        year = data.get("year", str(datetime.now().year))
        month = int(data.get("month", datetime.now().month))
        
        payment_record = {
            "paidDate": data.get("paidDate", int(datetime.now().timestamp() * 1000)),
            "amount": float(data["amount"]),
            "notes": data.get("notes"),
            "paymentMethod": data.get("paymentMethod", "cash")
        }
        
        # Initialize yearly structures if needed
        if "yearlyMonthStatus" not in student:
            student["yearlyMonthStatus"] = {}
        if "yearlyPaymentRecords" not in student:
            student["yearlyPaymentRecords"] = {}
        
        if year not in student["yearlyMonthStatus"]:
            student["yearlyMonthStatus"][year] = {}
        if year not in student["yearlyPaymentRecords"]:
            student["yearlyPaymentRecords"][year] = {}
        
        # Mark as paid (status = 1)
        student["yearlyMonthStatus"][year][str(month)] = 1
        student["yearlyPaymentRecords"][year][str(month)] = payment_record
        
        save_json_file(STUDENTS_FILE, students_data)
        
        return jsonify({"success": True, "student": student})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== Admission Request API Endpoints ====================

@app.route('/api/admissions', methods=['POST'])
def submit_admission_request():
    """Submit new admission request from web form"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ["name", "className", "guardianPhone", "subjects"]
        for field in required_fields:
            if field not in data:
                return jsonify({"success": False, "error": f"Missing required field: {field}"}), 400
        
        admission_request = {
            "id": get_next_admission_id(),
            "name": data["name"],
            "className": data["className"],
            "school": data.get("school", ""),
            "guardianPhone": data["guardianPhone"],
            "guardianName": data.get("guardianName", ""),
            "studentPhone": data.get("studentPhone", ""),
            "address": data.get("address", ""),
            "dob": data.get("dob", ""),
            "admissionDate": data.get("admissionDate", int(datetime.now().timestamp() * 1000)),
            "subjects": data["subjects"] if isinstance(data["subjects"], list) else [data["subjects"]],
            "fees": float(data.get("fees", 0)),
            "submittedAt": int(datetime.now().timestamp() * 1000),
            "status": "pending"  # pending, approved, rejected
        }
        
        admissions_data["requests"].append(admission_request)
        save_json_file(ADMISSIONS_FILE, admissions_data)
        
        return jsonify({
            "success": True,
            "message": "Admission request submitted successfully!",
            "request": admission_request
        }), 201
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/admissions', methods=['GET'])
def get_admission_requests():
    """Get all admission requests (optionally filter by status)"""
    status_filter = request.args.get('status', None)
    
    requests = admissions_data["requests"]
    if status_filter:
        requests = [r for r in requests if r["status"] == status_filter]
    
    return jsonify({
        "success": True,
        "requests": requests,
        "count": len(requests)
    })


@app.route('/api/admissions/<int:request_id>', methods=['GET'])
def get_admission_request(request_id: int):
    """Get single admission request"""
    admission = next((r for r in admissions_data["requests"] if r["id"] == request_id), None)
    if admission:
        return jsonify({"success": True, "request": admission})
    return jsonify({"success": False, "error": "Admission request not found"}), 404


@app.route('/api/admissions/<int:request_id>/approve', methods=['POST'])
def approve_admission(request_id: int):
    """Approve admission request and create student"""
    try:
        admission = next((r for r in admissions_data["requests"] if r["id"] == request_id), None)
        if not admission:
            return jsonify({"success": False, "error": "Admission request not found"}), 404
        
        if admission["status"] != "pending":
            return jsonify({"success": False, "error": "Request already processed"}), 400
        
        # Create student from admission request
        admission_date = admission.get("admissionDate", int(datetime.now().timestamp() * 1000))
        
        # Initialize yearly month statuses based on admission date
        from datetime import datetime as dt
        adm_dt = dt.fromtimestamp(admission_date / 1000)
        now = dt.now()
        current_year = str(now.year)
        
        yearly_month_status = {
            current_year: {
                str(i): (
                    2 if i < adm_dt.month else  # Ignored before admission
                    0 if i <= now.month else    # Pending from admission to current
                    3                             # Upcoming after current month
                )
                for i in range(1, 13)
            }
        }
        
        student = {
            "id": get_next_student_id(),
            "name": admission["name"],
            "className": admission["className"],
            "school": admission["school"],
            "guardianPhone": admission["guardianPhone"],
            "guardianName": admission["guardianName"],
            "studentPhone": admission["studentPhone"],
            "address": admission["address"],
            "dob": admission["dob"] if admission["dob"] else int(datetime.now().timestamp() * 1000),
            "admissionDate": admission_date,
            "subjects": admission["subjects"],
            "fees": admission["fees"],
            "profileImagePath": None,
            "createdAt": int(datetime.now().timestamp() * 1000),
            "yearlyMonthStatus": yearly_month_status,
            "yearlyPaymentRecords": {},
            "pendingFeesReminders": {}
        }
        
        students_data["students"].append(student)
        save_json_file(STUDENTS_FILE, students_data)
        
        # Update admission status
        admission["status"] = "approved"
        admission["processedAt"] = int(datetime.now().timestamp() * 1000)
        admission["studentId"] = student["id"]
        save_json_file(ADMISSIONS_FILE, admissions_data)
        
        return jsonify({
            "success": True,
            "message": "Admission approved and student created",
            "student": student
        })
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/admissions/<int:request_id>/reject', methods=['POST'])
def reject_admission(request_id: int):
    """Reject admission request"""
    try:
        admission = next((r for r in admissions_data["requests"] if r["id"] == request_id), None)
        if not admission:
            return jsonify({"success": False, "error": "Admission request not found"}), 404
        
        if admission["status"] != "pending":
            return jsonify({"success": False, "error": "Request already processed"}), 400
        
        data = request.json or {}
        admission["status"] = "rejected"
        admission["processedAt"] = int(datetime.now().timestamp() * 1000)
        admission["rejectionReason"] = data.get("reason", "")
        
        save_json_file(ADMISSIONS_FILE, admissions_data)
        
        return jsonify({"success": True, "message": "Admission request rejected"})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/admissions/pending/count', methods=['GET'])
def get_pending_count():
    """Get count of pending admission requests"""
    pending = [r for r in admissions_data["requests"] if r["status"] == "pending"]
    return jsonify({
        "success": True,
        "count": len(pending),
        "requests": pending
    })


# ==================== Static Web Form ====================

@app.route('/')
def serve_registration_form():
    """Serve student registration form"""
    return send_from_directory('web', 'index.html')


@app.route('/web/<path:filename>')
def serve_static(filename):
    """Serve static files"""
    return send_from_directory('web', filename)

@app.route('/Testing-Host')
def route_testing_host():
    return "<h1>Page : Working</h1><br><br><h1>Response : Success</h1>"


# ==================== Health Check & Info ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": int(datetime.now().timestamp() * 1000),
        "students_count": len(students_data["students"]),
        "pending_admissions": len([r for r in admissions_data["requests"] if r["status"] == "pending"])
    })


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get server statistics"""
    pending = len([r for r in admissions_data["requests"] if r["status"] == "pending"])
    approved = len([r for r in admissions_data["requests"] if r["status"] == "approved"])
    rejected = len([r for r in admissions_data["requests"] if r["status"] == "rejected"])
    
    return jsonify({
        "success": True,
        "stats": {
            "total_students": len(students_data["students"]),
            "pending_admissions": pending,
            "approved_admissions": approved,
            "rejected_admissions": rejected,
            "server_uptime": int(datetime.now().timestamp() * 1000)
        }
    })


# ==================== Backup Endpoint ====================

@app.route('/api/backup', methods=['POST'])
def trigger_backup():
    """Manually trigger backup"""
    try:
        auto_backup()
        return jsonify({"success": True, "message": "Backup created successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== Server Startup ====================

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Tuition Management Server Starting...")
    print("=" * 60)
    print(f"📂 Students Data: {STUDENTS_FILE}")
    print(f"📂 Admissions Data: {ADMISSIONS_FILE}")
    print(f"📂 Backup Directory: {BACKUP_DIR}")
    print(f"👥 Loaded {len(students_data['students'])} students")
    print(f"📝 Loaded {len(admissions_data['requests'])} admission requests")
    print("=" * 60)
    print("📡 Server Endpoints:")
    print("   GET    /api/students           - Get all students")
    print("   GET    /api/students/<id>      - Get student by ID")
    print("   POST   /api/students           - Add new student")
    print("   PUT    /api/students/<id>      - Update student")
    print("   DELETE /api/students/<id>      - Delete student")
    print("   POST   /api/students/<id>/payment - Record payment")
    print("   ")
    print("   POST   /api/admissions         - Submit admission request")
    print("   GET    /api/admissions         - Get admission requests")
    print("   POST   /api/admissions/<id>/approve - Approve admission")
    print("   POST   /api/admissions/<id>/reject  - Reject admission")
    print("   GET    /api/admissions/pending/count - Get pending count")
    print("   ")
    print("   GET    /                       - Student registration form")
    print("   GET    /api/health             - Health check")
    print("   GET    /api/stats              - Server statistics")
    print("=" * 60)
    print("🌐 Server running on: http://0.0.0.0:5000")
    print("🌐 Registration form: http://localhost:5000")
    print("=" * 60)
    
    # Create backups directory if it doesn't exist
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    # Create web directory if it doesn't exist
    if not os.path.exists('web'):
        os.makedirs('web')
        print("⚠️  'web' directory created. Please add index.html for registration form.")
    
    # Run server
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
