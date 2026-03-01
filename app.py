from flask import Flask, render_template, jsonify, request, redirect, session, url_for
from flask_mysqldb import MySQL
import razorpay
import random
import hmac
import hashlib
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json
import smtplib
from email.message import EmailMessage
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

mysql = MySQL(app)

# Razorpay Client (TEST MODE)
razorpay_client = razorpay.Client(
    auth=(Config.RAZORPAY_KEY_ID, Config.RAZORPAY_SECRET)
)

otp_storage = {}
order_context_store = {}
whatsapp_sent_orders = set()
partner_alert_sent_orders = set()

fallback_providers = [
    {
        "id": 1,
        "company": "SkyAgri Drones",
        "distributor": "AeroViaX Partner",
        "service": "Agriculture",
        "location": "Hyderabad",
        "price": 2500,
        "rating": "4.8"
    },
    {
        "id": 2,
        "company": "LensLift Aerial",
        "distributor": "AeroViaX Partner",
        "service": "Aerial Photography",
        "location": "Bengaluru",
        "price": 3000,
        "rating": "4.7"
    },
    {
        "id": 3,
        "company": "MapGrid Surveys",
        "distributor": "AeroViaX Partner",
        "service": "Mapping",
        "location": "Chennai",
        "price": 2800,
        "rating": "4.6"
    },
    {
        "id": 4,
        "company": "CropShield UAV",
        "distributor": "AeroViaX Partner",
        "service": "Spraying",
        "location": "Vijayawada",
        "price": 3200,
        "rating": "4.7"
    },
    {
        "id": 5,
        "company": "SeedDrop Aero",
        "distributor": "AeroViaX Partner",
        "service": "Seeding",
        "location": "Warangal",
        "price": 3100,
        "rating": "4.5"
    },
    {
        "id": 6,
        "company": "EstateLens Pro",
        "distributor": "AeroViaX Partner",
        "service": "Real Estate Survey",
        "location": "Pune",
        "price": 3500,
        "rating": "4.8"
    },
    {
        "id": 7,
        "company": "InfraScan UAV",
        "distributor": "AeroViaX Partner",
        "service": "Infrastructure Inspection",
        "location": "Mumbai",
        "price": 4200,
        "rating": "4.7"
    },
    {
        "id": 8,
        "company": "MineMap Robotics",
        "distributor": "AeroViaX Partner",
        "service": "Mining Survey",
        "location": "Nagpur",
        "price": 4600,
        "rating": "4.6"
    },
    {
        "id": 9,
        "company": "SecureEye Drones",
        "distributor": "AeroViaX Partner",
        "service": "Surveillance",
        "location": "Delhi",
        "price": 3900,
        "rating": "4.7"
    },
    {
        "id": 10,
        "company": "UtilityFly Inspect",
        "distributor": "AeroViaX Partner",
        "service": "Utility Inspection",
        "location": "Ahmedabad",
        "price": 4100,
        "rating": "4.5"
    },
    {
        "id": 11,
        "company": "TourVista Aerial",
        "distributor": "AeroViaX Partner",
        "service": "Tourism Media",
        "location": "Jaipur",
        "price": 3400,
        "rating": "4.6"
    },
    {
        "id": 12,
        "company": "UrbanGrid Analytics",
        "distributor": "AeroViaX Partner",
        "service": "Urban Planning",
        "location": "Hyderabad",
        "price": 4300,
        "rating": "4.7"
    }
]

def reset_auto_increment(table_name):
    try:
        cur = mysql.connection.cursor()
        cur.execute(f"ALTER TABLE {table_name} AUTO_INCREMENT = 1")
        mysql.connection.commit()
        cur.close()
    except Exception:
        # Ignore if table type/engine does not support or value is unchanged.
        pass


def ensure_reviews_table():
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INT AUTO_INCREMENT PRIMARY KEY,
                booking_order_id VARCHAR(120) UNIQUE,
                distributor_id INT NOT NULL,
                customer_name VARCHAR(255),
                rating INT NOT NULL,
                review_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        mysql.connection.commit()
        cur.close()
    except Exception as e:
        print("REVIEWS TABLE CHECK ERROR:", str(e))


def ensure_partner_tables():
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS service_holders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                holder_name VARCHAR(255) NOT NULL,
                company_name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                phone VARCHAR(20),
                password VARCHAR(255) NOT NULL,
                location VARCHAR(255),
                service VARCHAR(255),
                rating DECIMAL(3,1) DEFAULT 4.5,
                status VARCHAR(20) DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS amount_change_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                partner_id INT NOT NULL,
                distributor_id INT NOT NULL,
                current_price DECIMAL(10,2) NOT NULL,
                requested_price DECIMAL(10,2) NOT NULL,
                status VARCHAR(20) DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                event_key VARCHAR(180) UNIQUE,
                booking_order_id VARCHAR(120),
                event_type VARCHAR(80) NOT NULL,
                channel VARCHAR(30) NOT NULL,
                recipient VARCHAR(255),
                status VARCHAR(20) NOT NULL,
                message TEXT,
                error_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP NULL
            )
        """)

        # Optional columns for booking operations in partner dashboard.
        for alter in [
            "ALTER TABLE bookings ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE bookings ADD COLUMN service_date DATE NULL",
            "ALTER TABLE bookings ADD COLUMN service_time VARCHAR(20) NULL",
            "ALTER TABLE bookings ADD COLUMN review_requested_at TIMESTAMP NULL",
            "ALTER TABLE bookings ADD COLUMN notified_partner_at TIMESTAMP NULL",
            "ALTER TABLE bookings ADD COLUMN review_submitted_at TIMESTAMP NULL"
        ]:
            try:
                cur.execute(alter)
            except Exception:
                pass

        mysql.connection.commit()
        cur.close()
    except Exception as e:
        print("PARTNER TABLE CHECK ERROR:", str(e))


def fetch_partner_bookings(cur, company_name):
    try:
        cur.execute("""
            SELECT b.id, b.customer_name, b.email, b.phone, d.service, d.location,
                   b.amount, b.razorpay_order_id, b.status, b.created_at, b.service_date, b.service_time
            FROM bookings b
            JOIN distributors d ON b.distributor_id = d.id
            WHERE d.company=%s
            ORDER BY b.id DESC
        """, (company_name,))
        return cur.fetchall()
    except Exception as e:
        print("PARTNER BOOKINGS OPTIONAL COLUMN FALLBACK:", str(e))
        cur.execute("""
            SELECT b.id, b.customer_name, b.email, b.phone, d.service, d.location,
                   b.amount, b.razorpay_order_id, b.status, b.created_at
            FROM bookings b
            JOIN distributors d ON b.distributor_id = d.id
            WHERE d.company=%s
            ORDER BY b.id DESC
        """, (company_name,))
        rows = cur.fetchall()
        return [tuple(list(r) + [None, None]) for r in rows]


def fetch_admin_bookings(cur):
    try:
        cur.execute("""
            SELECT b.id, d.company, d.service, b.customer_name, b.email, b.phone,
                   b.amount, b.razorpay_order_id, b.status, b.service_date, b.service_time, b.review_requested_at
            FROM bookings b
            JOIN distributors d ON b.distributor_id = d.id
            ORDER BY b.id DESC
        """)
        return cur.fetchall()
    except Exception as e:
        print("ADMIN BOOKINGS OPTIONAL COLUMN FALLBACK:", str(e))
        cur.execute("""
            SELECT b.id, d.company, d.service, b.customer_name, b.email, b.phone,
                   b.amount, b.razorpay_order_id, b.status
            FROM bookings b
            JOIN distributors d ON b.distributor_id = d.id
            ORDER BY b.id DESC
        """)
        rows = cur.fetchall()
        return [tuple(list(r) + [None, None, None]) for r in rows]


def log_notification(event_key, booking_order_id, event_type, channel, recipient, status, message, error_text=None):
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO notifications
            (event_key, booking_order_id, event_type, channel, recipient, status, message, error_text, sent_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                status=VALUES(status),
                recipient=VALUES(recipient),
                message=VALUES(message),
                error_text=VALUES(error_text),
                sent_at=VALUES(sent_at)
        """, (
            event_key,
            booking_order_id,
            event_type,
            channel,
            recipient,
            status,
            message,
            error_text,
            datetime.now() if status == "SENT" else None
        ))
        mysql.connection.commit()
        cur.close()
    except Exception as e:
        print("NOTIFICATION LOG ERROR:", str(e))


def send_partner_booking_email(to_email, holder_name, company_name, order_id, customer_name, customer_phone, customer_email, service, amount, host_url):
    if not to_email:
        return False, "Missing recipient email"
    if not (Config.MAIL_HOST and Config.MAIL_USERNAME and Config.MAIL_PASSWORD):
        return False, "SMTP credentials not configured"

    msg = EmailMessage()
    msg["Subject"] = f"New Booking Alert | {company_name} | AeroViaX"
    msg["From"] = Config.MAIL_FROM
    msg["To"] = to_email
    msg.set_content(
        f"""Hi {holder_name or 'Partner'},

You have a new booking on AeroViaX.

Order ID: {order_id}
Service: {service}
Amount: Rs {amount}

Customer Name: {customer_name}
Customer Phone: {customer_phone}
Customer Email: {customer_email}

Please login to your distributor dashboard and accept/schedule this order:
{host_url.rstrip('/')}/partner/dashboard
"""
    )

    starttls_ports = [int(Config.MAIL_PORT), 2525]
    tried = set()
    for port in starttls_ports:
        if port in tried:
            continue
        tried.add(port)
        try:
            with smtplib.SMTP(Config.MAIL_HOST, port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if "auth" not in server.esmtp_features:
                    raise smtplib.SMTPException("SMTP AUTH extension not supported after STARTTLS")
                server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
                server.send_message(msg)
            return True, f"Sent via STARTTLS:{port}"
        except Exception as e:
            last_error = str(e)

    try:
        with smtplib.SMTP_SSL(Config.MAIL_HOST, 465, timeout=20) as server:
            server.ehlo()
            if "auth" not in server.esmtp_features:
                raise smtplib.SMTPException("SMTP AUTH extension not supported on SSL")
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.send_message(msg)
        return True, "Sent via SSL:465"
    except Exception as e:
        return False, str(e)


def send_partner_booking_whatsapp(to_phone, holder_name, order_id, service, amount):
    if not (Config.TWILIO_ACCOUNT_SID and Config.TWILIO_AUTH_TOKEN):
        return False, "Twilio credentials not configured"
    normalized_to = normalize_phone_for_whatsapp(to_phone)
    if not normalized_to:
        return False, "Invalid partner phone"

    body = (
        f"Hi {holder_name or 'Partner'}, new booking received on AeroViaX. "
        f"Order: {order_id}, Service: {service}, Amount: Rs {amount}. "
        "Please check your partner dashboard."
    )

    endpoint = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{Config.TWILIO_ACCOUNT_SID}/Messages.json"
    )
    payload_data = {
        "From": Config.TWILIO_WHATSAPP_FROM,
        "To": f"whatsapp:{normalized_to}",
        "Body": body
    }
    payload = urlencode(payload_data).encode("utf-8")
    req = Request(endpoint, data=payload, method="POST")
    credentials = f"{Config.TWILIO_ACCOUNT_SID}:{Config.TWILIO_AUTH_TOKEN}".encode("utf-8")
    import base64
    req.add_header("Authorization", f"Basic {base64.b64encode(credentials).decode('utf-8')}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urlopen(req, timeout=15) as response:
            if 200 <= response.status < 300:
                return True, "WhatsApp sent"
            return False, f"HTTP {response.status}"
    except HTTPError as e:
        return False, f"HTTPError {e.code}"
    except URLError as e:
        return False, f"URLError {e}"


def notify_partner_new_booking(order_id, distributor_id, company_name, customer_name, customer_phone, customer_email, service, amount, host_url):
    lookup_company = company_name
    if not lookup_company and distributor_id:
        try:
            c0 = mysql.connection.cursor()
            c0.execute("SELECT company FROM distributors WHERE id=%s LIMIT 1", (distributor_id,))
            row = c0.fetchone()
            c0.close()
            lookup_company = row[0] if row else ""
        except Exception as e:
            print("DISTRIBUTOR COMPANY LOOKUP ERROR:", str(e))

    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT id, holder_name, email, phone
            FROM service_holders
            WHERE company_name=%s AND status='APPROVED'
            ORDER BY id DESC
            LIMIT 1
        """, (lookup_company,))
        partner = cur.fetchone()
        cur.close()
    except Exception as e:
        print("PARTNER LOOKUP ERROR:", str(e))
        return False

    if not partner:
        log_notification(
            event_key=f"{order_id}-partner-email",
            booking_order_id=order_id,
            event_type="NEW_BOOKING_PARTNER",
            channel="EMAIL",
            recipient="N/A",
            status="SKIPPED",
            message="No approved partner found for company",
            error_text="Partner profile missing"
        )
        return False

    _, holder_name, partner_email, partner_phone = partner
    email_ok, email_msg = send_partner_booking_email(
        partner_email, holder_name, company_name, order_id,
        customer_name, customer_phone, customer_email, service, amount, host_url
    )
    log_notification(
        event_key=f"{order_id}-partner-email",
        booking_order_id=order_id,
        event_type="NEW_BOOKING_PARTNER",
        channel="EMAIL",
        recipient=partner_email,
        status="SENT" if email_ok else "FAILED",
        message=email_msg if email_ok else "Partner booking email failed",
        error_text=None if email_ok else email_msg
    )

    wa_ok = False
    wa_msg = "Partner phone unavailable"
    if partner_phone:
        wa_ok, wa_msg = send_partner_booking_whatsapp(partner_phone, holder_name, order_id, service, amount)

    log_notification(
        event_key=f"{order_id}-partner-whatsapp",
        booking_order_id=order_id,
        event_type="NEW_BOOKING_PARTNER",
        channel="WHATSAPP",
        recipient=partner_phone or "N/A",
        status="SENT" if wa_ok else ("SKIPPED" if not partner_phone else "FAILED"),
        message=wa_msg if wa_ok else "Partner booking WhatsApp not sent",
        error_text=None if wa_ok else wa_msg
    )

    if email_ok or wa_ok:
        try:
            c2 = mysql.connection.cursor()
            c2.execute("UPDATE bookings SET notified_partner_at=NOW() WHERE razorpay_order_id=%s", (order_id,))
            mysql.connection.commit()
            c2.close()
        except Exception as e:
            print("BOOKING NOTIFIED_PARTNER_AT UPDATE ERROR:", str(e))
        return True
    return False


def normalize_phone_for_whatsapp(phone):
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not digits:
        return ""
    if len(digits) == 10:
        return f"+91{digits}"
    if digits.startswith("91") and len(digits) == 12:
        return f"+{digits}"
    if str(phone).startswith("+"):
        return str(phone)
    return f"+{digits}"


def send_whatsapp_success_message(to_phone, customer_name, service, provider):
    if not (Config.TWILIO_ACCOUNT_SID and Config.TWILIO_AUTH_TOKEN):
        print("WHATSAPP SKIPPED: Twilio credentials not configured")
        return False

    normalized_to = normalize_phone_for_whatsapp(to_phone)
    if not normalized_to:
        print("WHATSAPP SKIPPED: Invalid recipient phone")
        return False

    body = (
        f"Hi {customer_name or 'Customer'}, your AeroViaX booking payment is successful. "
        f"Service: {service or 'Drone service'} with {provider or 'our partner'}. "
        "Your service slot will be scheduled shortly. "
        "For any queries, reply to this WhatsApp message."
    )

    endpoint = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{Config.TWILIO_ACCOUNT_SID}/Messages.json"
    )
    payload_data = {
        "From": Config.TWILIO_WHATSAPP_FROM,
        "To": f"whatsapp:{normalized_to}"
    }

    if Config.TWILIO_CONTENT_SID:
        payload_data["ContentSid"] = Config.TWILIO_CONTENT_SID
        payload_data["ContentVariables"] = json.dumps({
            "1": datetime.now().strftime("%d/%m/%Y"),
            "2": "within 24 hours"
        })
    else:
        payload_data["Body"] = body

    payload = urlencode(payload_data).encode("utf-8")

    req = Request(endpoint, data=payload, method="POST")
    credentials = f"{Config.TWILIO_ACCOUNT_SID}:{Config.TWILIO_AUTH_TOKEN}".encode("utf-8")
    import base64
    req.add_header("Authorization", f"Basic {base64.b64encode(credentials).decode('utf-8')}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urlopen(req, timeout=15) as response:
            if 200 <= response.status < 300:
                print(f"WHATSAPP SENT to {normalized_to}")
                return True
            print(f"WHATSAPP FAILED: HTTP {response.status}")
            return False
    except HTTPError as e:
        error_body = ""
        twilio_code = ""
        twilio_message = ""
        try:
            error_body = e.read().decode("utf-8", errors="ignore")
            payload = json.loads(error_body)
            twilio_code = payload.get("code")
            twilio_message = payload.get("message")
        except Exception:
            pass

        print(f"WHATSAPP FAILED: HTTPError {e.code}")
        if twilio_code or twilio_message:
            print(f"WHATSAPP FAILED DETAILS: code={twilio_code}, message={twilio_message}")
        elif error_body:
            print(f"WHATSAPP FAILED DETAILS: {error_body}")

        if e.code == 400:
            print("WHATSAPP HINT: Verify sandbox join, 'From' number, and recipient format (whatsapp:+91XXXXXXXXXX)")
        return False
    except URLError as e:
        print(f"WHATSAPP FAILED: URLError {e}")
        return False


def send_booking_success_email(to_email, customer_name, service, provider, amount, order_id, payment_id):
    if not to_email:
        print("EMAIL SKIPPED: Missing recipient email")
        return False

    if not (Config.MAIL_HOST and Config.MAIL_USERNAME and Config.MAIL_PASSWORD):
        print("EMAIL SKIPPED: SMTP credentials not configured")
        return False

    msg = EmailMessage()
    msg["Subject"] = "Booking Confirmed | AeroViaX"
    msg["From"] = Config.MAIL_FROM
    msg["To"] = to_email
    msg.set_content(
        f"""Hi {customer_name or 'Customer'},

Your AeroViaX booking payment was successful.

Service: {service or '-'}
Provider: {provider or '-'}
Amount: Rs {amount if amount is not None else '-'}
Order ID: {order_id or '-'}
Payment Reference: {payment_id or '-'}

Our team will contact you shortly for scheduling.
For any queries, reply to this email.

Regards,
AeroViaX Team
"""
    )

    starttls_ports = [int(Config.MAIL_PORT), 2525]
    tried = set()

    for port in starttls_ports:
        if port in tried:
            continue
        tried.add(port)
        try:
            with smtplib.SMTP(Config.MAIL_HOST, port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if "auth" not in server.esmtp_features:
                    raise smtplib.SMTPException("SMTP AUTH extension not supported by server after STARTTLS")
                server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
                server.send_message(msg)
            print(f"EMAIL SENT to {to_email} via STARTTLS:{port}")
            return True
        except Exception as e:
            print(f"EMAIL STARTTLS:{port} FAILED: {e}")

    try:
        # Final fallback to implicit SSL (465).
        with smtplib.SMTP_SSL(Config.MAIL_HOST, 465, timeout=20) as server:
            server.ehlo()
            if "auth" not in server.esmtp_features:
                raise smtplib.SMTPException("SMTP AUTH extension not supported by server on SSL")
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.send_message(msg)
        print(f"EMAIL SENT to {to_email} via SSL:465")
        return True
    except Exception as ssl_err:
        print(f"EMAIL FAILED: {ssl_err}")
        return False


def send_review_request_email(to_email, customer_name, order_id, service, provider, host_url):
    if not to_email:
        print("REVIEW EMAIL SKIPPED: Missing recipient email")
        log_notification(
            event_key=f"{order_id}-review-email",
            booking_order_id=order_id,
            event_type="REVIEW_REQUEST_CUSTOMER",
            channel="EMAIL",
            recipient="N/A",
            status="SKIPPED",
            message="Missing customer email",
            error_text="Missing recipient email"
        )
        return False
    if not (Config.MAIL_HOST and Config.MAIL_USERNAME and Config.MAIL_PASSWORD):
        print("REVIEW EMAIL SKIPPED: SMTP credentials not configured")
        log_notification(
            event_key=f"{order_id}-review-email",
            booking_order_id=order_id,
            event_type="REVIEW_REQUEST_CUSTOMER",
            channel="EMAIL",
            recipient=to_email,
            status="FAILED",
            message="SMTP credentials not configured",
            error_text="SMTP credentials missing"
        )
        return False

    review_link = f"{host_url.rstrip('/')}/review/{order_id}"
    msg = EmailMessage()
    msg["Subject"] = "Please Rate Your Service | AeroViaX"
    msg["From"] = Config.MAIL_FROM
    msg["To"] = to_email
    msg.set_content(
        f"""Hi {customer_name or 'Customer'},

Your service has been marked as completed by the distributor.

Service: {service or '-'}
Provider: {provider or '-'}
Order ID: {order_id or '-'}

Please share your feedback and rating here:
{review_link}

Thank you for choosing AeroViaX.
"""
    )

    starttls_ports = [int(Config.MAIL_PORT), 2525]
    tried = set()
    for port in starttls_ports:
        if port in tried:
            continue
        tried.add(port)
        try:
            with smtplib.SMTP(Config.MAIL_HOST, port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if "auth" not in server.esmtp_features:
                    raise smtplib.SMTPException("SMTP AUTH extension not supported by server after STARTTLS")
                server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
                server.send_message(msg)
            print(f"REVIEW EMAIL SENT to {to_email} via STARTTLS:{port}")
            log_notification(
                event_key=f"{order_id}-review-email",
                booking_order_id=order_id,
                event_type="REVIEW_REQUEST_CUSTOMER",
                channel="EMAIL",
                recipient=to_email,
                status="SENT",
                message=f"Sent via STARTTLS:{port}",
                error_text=None
            )
            return True
        except Exception as e:
            print(f"REVIEW EMAIL STARTTLS:{port} FAILED: {e}")

    try:
        with smtplib.SMTP_SSL(Config.MAIL_HOST, 465, timeout=20) as server:
            server.ehlo()
            if "auth" not in server.esmtp_features:
                raise smtplib.SMTPException("SMTP AUTH extension not supported by server on SSL")
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.send_message(msg)
        print(f"REVIEW EMAIL SENT to {to_email} via SSL:465")
        log_notification(
            event_key=f"{order_id}-review-email",
            booking_order_id=order_id,
            event_type="REVIEW_REQUEST_CUSTOMER",
            channel="EMAIL",
            recipient=to_email,
            status="SENT",
            message="Sent via SSL:465",
            error_text=None
        )
        return True
    except Exception as ssl_err:
        print(f"REVIEW EMAIL FAILED: {ssl_err}")
        log_notification(
            event_key=f"{order_id}-review-email",
            booking_order_id=order_id,
            event_type="REVIEW_REQUEST_CUSTOMER",
            channel="EMAIL",
            recipient=to_email,
            status="FAILED",
            message="Review request email failed",
            error_text=str(ssl_err)
        )
        return False


@app.route("/test-email", methods=["POST"])
def test_email():
    data = request.get_json(silent=True) or {}
    to_email = data.get("email") or Config.MAIL_USERNAME

    sent = send_booking_success_email(
        to_email=to_email,
        customer_name="Test User",
        service="Test Service",
        provider="AeroViaX Test Provider",
        amount=999,
        order_id="test_order_123",
        payment_id="test_payment_123"
    )

    if sent:
        return jsonify({"status": "success", "message": f"Test email sent to {to_email}"})

    return jsonify({"status": "failed", "message": "SMTP send failed. Check terminal logs."}), 500

# ================= HOME =================

@app.route("/")
def home():
    ensure_reviews_table()
    ensure_partner_tables()
    return render_template("index.html", razorpay_key_id=Config.RAZORPAY_KEY_ID)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return redirect("mailto:info@aeroviax.com")


@app.route("/partner/become", methods=["GET", "POST"])
def become_partner():
    ensure_partner_tables()
    message = None

    if request.method == "POST":
        holder_name = (request.form.get("holder_name") or "").strip()
        company_name = (request.form.get("company_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip()
        password = (request.form.get("password") or "").strip()
        location = (request.form.get("location") or "").strip()
        service = (request.form.get("service") or "").strip()

        if not all([holder_name, company_name, email, password, location, service]):
            message = "Please fill all required fields."
        else:
            try:
                cur = mysql.connection.cursor()
                cur.execute("""
                    INSERT INTO service_holders
                    (holder_name, company_name, email, phone, password, location, service, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    holder_name, company_name, email, phone, password, location, service, "PENDING"
                ))
                mysql.connection.commit()
                cur.close()
                message = "Partner request submitted. Admin approval pending."
            except Exception as e:
                message = f"Submission failed: {e}"

    return render_template("partner-become.html", message=message)


@app.route("/patner/become", methods=["GET", "POST"])
def become_partner_alias():
    return redirect(url_for("become_partner"))


@app.route("/partner/login", methods=["GET", "POST"])
def partner_login():
    ensure_partner_tables()
    message = None

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()

        try:
            cur = mysql.connection.cursor()
            cur.execute("""
                SELECT id, holder_name, company_name, status
                FROM service_holders
                WHERE LOWER(email)=LOWER(%s)
                  AND (password=%s OR TRIM(password)=%s)
                ORDER BY id DESC
                LIMIT 1
            """, (email, password, password))
            row = cur.fetchone()

            # If email exists but password mismatch, show a clearer message.
            if not row:
                cur.execute("""
                    SELECT id
                    FROM service_holders
                    WHERE LOWER(email)=LOWER(%s)
                    LIMIT 1
                """, (email,))
                email_exists = cur.fetchone()
                if email_exists:
                    message = "Password is incorrect for this partner account."
            cur.close()
        except Exception as e:
            row = None
            message = f"Login failed: {e}"

        if row:
            account_status = str(row[3] or "").strip().upper()
            if account_status != "APPROVED":
                message = "Your account is not approved yet. Please wait for admin approval."
            else:
                session["partner_id"] = row[0]
                session["partner_name"] = row[1]
                session["partner_company"] = row[2]
                return redirect(url_for("partner_dashboard"))
        elif not message:
            message = "Invalid partner credentials."

    return render_template("partner-login.html", message=message)


@app.route("/patner/login", methods=["GET", "POST"])
def partner_login_alias():
    return redirect(url_for("partner_login"))


@app.route("/partner/logout")
def partner_logout():
    session.pop("partner_id", None)
    session.pop("partner_name", None)
    session.pop("partner_company", None)
    return redirect(url_for("partner_login"))


@app.route("/partner/dashboard")
def partner_dashboard():
    ensure_partner_tables()
    if "partner_id" not in session:
        return redirect(url_for("partner_login"))

    partner_id = session["partner_id"]

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, holder_name, company_name, email, phone, location, service, rating, status
        FROM service_holders
        WHERE id=%s
        LIMIT 1
    """, (partner_id,))
    partner = cur.fetchone()

    bookings = []
    amount_requests = []
    distributor = None
    if partner:
        company_name = partner[2]
        holder_name = partner[1]
        service_name = partner[6]

        cur.execute("""
            SELECT id, company, distributor, service, location, price, rating
            FROM distributors
            WHERE company=%s AND distributor=%s AND service=%s
            LIMIT 1
        """, (company_name, holder_name, service_name))
        distributor = cur.fetchone()

        bookings = fetch_partner_bookings(cur, company_name)

        cur.execute("""
            SELECT id, current_price, requested_price, status, created_at, reviewed_at
            FROM amount_change_requests
            WHERE partner_id=%s
            ORDER BY id DESC
        """, (partner_id,))
        amount_requests = cur.fetchall()

    cur.close()
    metrics = {
        "total_orders": len(bookings),
        "pending_orders": len([b for b in bookings if b[8] in ("CREATED", "SUCCESS", "ASSIGNED", "IN_PROGRESS")]),
        "completed_orders": len([b for b in bookings if b[8] in ("COMPLETED", "REVIEWED", "CLOSED")]),
        "today_orders": len([b for b in bookings if str(b[9]).startswith(str(datetime.now().date()))])
    }
    return render_template(
        "partner-dashboard.html",
        partner=partner,
        bookings=bookings,
        distributor=distributor,
        amount_requests=amount_requests,
        metrics=metrics
    )


@app.route("/partner/update-booking/<int:booking_id>", methods=["POST"])
def partner_update_booking(booking_id):
    if "partner_id" not in session:
        return redirect(url_for("partner_login"))

    status = (request.form.get("status") or "").upper()
    if status == "COMPLETED_BY_DISTRIBUTOR":
        status = "COMPLETED"
    service_date = (request.form.get("service_date") or "").strip() or None
    service_time = (request.form.get("service_time") or "").strip() or None

    allowed_statuses = {"CREATED", "SUCCESS", "FAILED", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "REVIEWED", "CLOSED"}
    if status not in allowed_statuses:
        return "Invalid status", 400

    cur = mysql.connection.cursor()
    cur.execute("SELECT company_name FROM service_holders WHERE id=%s LIMIT 1", (session["partner_id"],))
    partner_row = cur.fetchone()
    company_name = partner_row[0] if partner_row else ""

    cur.execute("""
        SELECT b.status, b.razorpay_order_id, b.customer_name, b.email, d.service, d.company
        FROM bookings b
        JOIN distributors d ON b.distributor_id = d.id
        WHERE b.id=%s AND d.company=%s
        LIMIT 1
    """, (booking_id, company_name))
    old_booking = cur.fetchone()

    try:
        cur.execute("""
            UPDATE bookings b
            JOIN distributors d ON b.distributor_id = d.id
            SET b.status=%s, b.service_date=%s, b.service_time=%s
            WHERE b.id=%s AND d.company=%s
        """, (status, service_date, service_time, booking_id, company_name))
    except Exception:
        cur.execute("""
            UPDATE bookings b
            JOIN distributors d ON b.distributor_id = d.id
            SET b.status=%s
            WHERE b.id=%s AND d.company=%s
        """, (status, booking_id, company_name))
    mysql.connection.commit()
    cur.close()

    if old_booking:
        old_status, order_id, customer_name, customer_email, service_name, provider_company = old_booking
        completed_states = {"SUCCESS", "COMPLETED"}
        if status in completed_states and old_status not in completed_states:
            try:
                mark_cur = mysql.connection.cursor()
                mark_cur.execute("UPDATE bookings SET review_requested_at=NOW() WHERE id=%s", (booking_id,))
                mysql.connection.commit()
                mark_cur.close()
            except Exception as mark_err:
                print("REVIEW REQUEST MARK ERROR:", str(mark_err))
            send_review_request_email(
                customer_email,
                customer_name,
                order_id,
                service_name,
                provider_company,
                request.host_url
            )

    return redirect(url_for("partner_dashboard"))


@app.route("/partner/request-amount-change", methods=["POST"])
def partner_request_amount_change():
    if "partner_id" not in session:
        return redirect(url_for("partner_login"))

    try:
        requested_price = float(request.form.get("requested_price") or 0)
    except Exception:
        requested_price = 0

    if requested_price <= 0:
        return "Invalid requested amount", 400

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT sh.id, sh.company_name, sh.holder_name, sh.service, d.id, d.price
        FROM service_holders sh
        JOIN distributors d ON d.company=sh.company_name AND d.distributor=sh.holder_name AND d.service=sh.service
        WHERE sh.id=%s
        LIMIT 1
    """, (session["partner_id"],))
    row = cur.fetchone()

    if not row:
        cur.close()
        return "No linked distributor profile found", 400

    partner_id, _, _, _, distributor_id, current_price = row
    cur.execute("""
        INSERT INTO amount_change_requests
        (partner_id, distributor_id, current_price, requested_price, status)
        VALUES (%s, %s, %s, %s, 'PENDING')
    """, (partner_id, distributor_id, current_price, requested_price))
    mysql.connection.commit()
    cur.close()
    return redirect(url_for("partner_dashboard"))


# ================= REGISTER =================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        return redirect(url_for("admin_login"))
    return render_template("register.html")


@app.route("/login")
def login_redirect():
    return redirect(url_for("admin_login"))


# ================= ADMIN LOGIN =================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":
        username = request.form.get("username") or request.form.get("email")
        password = request.form.get("password")

        if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            return "Invalid Credentials"

    return render_template("login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


# ================= ADMIN DASHBOARD =================

@app.route("/admin/dashboard")
def admin_dashboard():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    ensure_partner_tables()
    ensure_reviews_table()
    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM distributors")
    distributors = cur.fetchall()

    bookings = fetch_admin_bookings(cur)

    cur.execute("SELECT IFNULL(SUM(amount),0) FROM bookings WHERE status <> 'FAILED'")
    revenue = cur.fetchone()[0]

    cur.execute("""
        SELECT id, holder_name, company_name, email, phone, location, service, rating, status
        FROM service_holders
        ORDER BY id DESC
    """)
    partner_requests = cur.fetchall()

    cur.execute("""
        SELECT acr.id, sh.company_name, sh.holder_name, d.service,
               acr.current_price, acr.requested_price, acr.status, acr.created_at
        FROM amount_change_requests acr
        JOIN service_holders sh ON acr.partner_id = sh.id
        JOIN distributors d ON acr.distributor_id = d.id
        ORDER BY acr.id DESC
    """)
    amount_change_requests = cur.fetchall()

    try:
        cur.execute("""
            SELECT id, booking_order_id, event_type, channel, recipient, status, sent_at, created_at, error_text
            FROM notifications
            ORDER BY id DESC
            LIMIT 120
        """)
        notifications = cur.fetchall()
    except Exception as e:
        print("NOTIFICATIONS FETCH ERROR:", str(e))
        notifications = []

    cur.close()

    return render_template(
        "admin.html",
        distributors=distributors,
        bookings=bookings,
        revenue=revenue,
        partner_requests=partner_requests,
        amount_change_requests=amount_change_requests,
        notifications=notifications
    )


# ================= ADD DISTRIBUTOR =================

@app.route("/admin/add-distributor", methods=["POST"])
def add_distributor():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    cur = mysql.connection.cursor()

    cur.execute("""
        INSERT INTO distributors
        (company, distributor, service, location, price, rating)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (
        request.form.get("company"),
        request.form.get("distributor"),
        request.form.get("service"),
        request.form.get("location"),
        request.form.get("price"),
        request.form.get("rating")
    ))

    mysql.connection.commit()
    cur.close()

    return redirect(url_for("admin_dashboard"))


# ================= DELETE DISTRIBUTOR =================

@app.route("/admin/delete-distributor/<int:id>", methods=["POST"])
def delete_distributor(id):

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    cur = mysql.connection.cursor()
    cur.execute("SELECT company, distributor, service FROM distributors WHERE id=%s LIMIT 1", (id,))
    dist = cur.fetchone()

    # Remove ratings tied to this distributor row.
    cur.execute("DELETE FROM reviews WHERE distributor_id=%s", (id,))
    cur.execute("DELETE FROM distributors WHERE id=%s", (id,))

    # Remove partner login/account for same company + holder + service.
    if dist:
        cur.execute("""
            DELETE FROM service_holders
            WHERE company_name=%s AND holder_name=%s AND service=%s
        """, (dist[0], dist[1], dist[2]))

    mysql.connection.commit()
    cur.close()

    reset_auto_increment("distributors")
    reset_auto_increment("service_holders")
    reset_auto_increment("reviews")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/update-booking/<int:id>", methods=["POST"])
def update_booking(id):

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    status = (request.form.get("status") or "").upper()
    if status == "PAID":
        status = "SUCCESS"
    if status == "COMPLETED_BY_DISTRIBUTOR":
        status = "COMPLETED"

    allowed_statuses = {"CREATED", "SUCCESS", "FAILED", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "REVIEWED", "CLOSED"}
    if status not in allowed_statuses:
        return "Invalid status", 400

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT b.status, b.razorpay_order_id, b.customer_name, b.email, d.service, d.company
        FROM bookings b
        LEFT JOIN distributors d ON b.distributor_id = d.id
        WHERE b.id=%s
        LIMIT 1
    """, (id,))
    old_booking = cur.fetchone()

    cur.execute("UPDATE bookings SET status=%s WHERE id=%s", (status, id))

    if old_booking:
        old_status, order_id, customer_name, customer_email, service_name, provider_company = old_booking
        completed_states = {"SUCCESS", "COMPLETED"}
        if status in completed_states and old_status not in completed_states:
            cur.execute("UPDATE bookings SET review_requested_at=NOW() WHERE id=%s", (id,))
            send_review_request_email(
                customer_email,
                customer_name,
                order_id,
                service_name,
                provider_company,
                request.host_url
            )
    mysql.connection.commit()
    cur.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/approve-partner/<int:partner_id>", methods=["POST"])
def approve_partner(partner_id):

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT holder_name, company_name, location, service, rating
        FROM service_holders
        WHERE id=%s
        LIMIT 1
    """, (partner_id,))
    partner = cur.fetchone()

    cur.execute("UPDATE service_holders SET status='APPROVED' WHERE id=%s", (partner_id,))

    # Push approved partner into customer-facing distributors list.
    if partner:
        holder_name, company_name, location, service, rating = partner

        cur.execute("""
            SELECT id FROM distributors
            WHERE company=%s AND distributor=%s AND service=%s
            LIMIT 1
        """, (company_name, holder_name, service))
        existing = cur.fetchone()

        if not existing:
            cur.execute("""
                INSERT INTO distributors
                (company, distributor, service, location, price, rating)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                company_name,
                holder_name,
                service,
                location,
                2500,
                rating if rating is not None else 4.5
            ))

    mysql.connection.commit()
    cur.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete-partner/<int:partner_id>", methods=["POST"])
def delete_partner(partner_id):

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT holder_name, company_name, service
        FROM service_holders
        WHERE id=%s
        LIMIT 1
    """, (partner_id,))
    partner = cur.fetchone()

    if partner:
        holder_name, company_name, service = partner

        # Delete related distributor rows and their reviews.
        cur.execute("""
            SELECT id FROM distributors
            WHERE company=%s AND distributor=%s AND service=%s
        """, (company_name, holder_name, service))
        dist_rows = cur.fetchall()
        for row in dist_rows:
            cur.execute("DELETE FROM reviews WHERE distributor_id=%s", (row[0],))

        cur.execute("""
            DELETE FROM distributors
            WHERE company=%s AND distributor=%s AND service=%s
        """, (company_name, holder_name, service))

    # Delete partner login/account.
    cur.execute("DELETE FROM service_holders WHERE id=%s", (partner_id,))
    mysql.connection.commit()
    cur.close()

    reset_auto_increment("distributors")
    reset_auto_increment("service_holders")
    reset_auto_increment("reviews")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/review-amount-request/<int:request_id>", methods=["POST"])
def review_amount_request(request_id):

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    action = (request.form.get("action") or "").lower()
    if action not in {"approve", "reject"}:
        return "Invalid action", 400

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT distributor_id, requested_price, status
        FROM amount_change_requests
        WHERE id=%s
        LIMIT 1
    """, (request_id,))
    req = cur.fetchone()

    if not req:
        cur.close()
        return redirect(url_for("admin_dashboard"))

    distributor_id, requested_price, current_status = req
    if current_status != "PENDING":
        cur.close()
        return redirect(url_for("admin_dashboard"))

    if action == "approve":
        cur.execute("UPDATE distributors SET price=%s WHERE id=%s", (requested_price, distributor_id))
        cur.execute("""
            UPDATE amount_change_requests
            SET status='APPROVED', reviewed_at=NOW()
            WHERE id=%s
        """, (request_id,))
    else:
        cur.execute("""
            UPDATE amount_change_requests
            SET status='REJECTED', reviewed_at=NOW()
            WHERE id=%s
        """, (request_id,))

    mysql.connection.commit()
    cur.close()
    return redirect(url_for("admin_dashboard"))


# ================= PROVIDERS API (FILTER) =================

@app.route("/api/providers")
def providers():

    service = request.args.get("service")
    ensure_reviews_table()

    try:
        cur = mysql.connection.cursor()

        if service and service != "all":
            cur.execute("""
                SELECT d.id, d.company, d.distributor, d.service, d.location, d.price,
                       COALESCE(ROUND(AVG(r.rating), 1), d.rating) AS avg_rating
                FROM distributors d
                LEFT JOIN reviews r ON r.distributor_id = d.id
                WHERE d.service=%s
                GROUP BY d.id, d.company, d.distributor, d.service, d.location, d.price, d.rating
            """, (service,))
        else:
            cur.execute("""
                SELECT d.id, d.company, d.distributor, d.service, d.location, d.price,
                       COALESCE(ROUND(AVG(r.rating), 1), d.rating) AS avg_rating
                FROM distributors d
                LEFT JOIN reviews r ON r.distributor_id = d.id
                GROUP BY d.id, d.company, d.distributor, d.service, d.location, d.price, d.rating
            """)

        data = cur.fetchall()
        cur.close()

        result = []
        for row in data:
            result.append({
                "id": row[0],
                "company": row[1],
                "distributor": row[2],
                "service": row[3],
                "location": row[4],
                "price": int(row[5]),
                "rating": round(float(row[6]), 1) if row[6] is not None else 0.0
            })

        if result:
            return jsonify(result)

    except Exception as e:
        print("PROVIDERS API ERROR:", str(e))

    if service and service != "all":
        filtered = [p for p in fallback_providers if p["service"] == service]
        return jsonify(filtered)

    return jsonify(fallback_providers)


# ================= SEND OTP =================

@app.route("/send-otp", methods=["POST"])
def send_otp():

    phone = request.json.get("phone")

    if not phone:
        return jsonify({"status": "failed"}), 400

    otp = random.randint(100000, 999999)
    otp_storage[phone] = otp

    print("OTP for", phone, ":", otp, flush=True)

    return jsonify({"status": "success", "otp": str(otp)})


# ================= VERIFY OTP =================

@app.route("/verify-otp", methods=["POST"])
def verify_otp():

    phone = request.json.get("phone")
    otp = request.json.get("otp")

    if phone in otp_storage and str(otp_storage[phone]) == str(otp):
        return jsonify({"status": "verified"})

    return jsonify({"status": "invalid"})


# ================= CREATE ORDER =================

@app.route("/create-order", methods=["POST"])
def create_order():

    try:
        data = request.get_json()

        amount = int(data.get("amount", 0))
        if amount <= 0:
            return jsonify({"error": "Invalid amount"}), 400

        if not Config.RAZORPAY_KEY_ID or not Config.RAZORPAY_SECRET:
            return jsonify({
                "error": "Razorpay credentials are missing. Set RAZORPAY_KEY_ID and RAZORPAY_SECRET."
            }), 500

        order = razorpay_client.order.create({
            "amount": amount * 100,
            "currency": "INR",
            "payment_capture": 1
        })

        order_context_store[order["id"]] = {
            "phone": data.get("phone"),
            "customer_name": data.get("name"),
            "email": data.get("email"),
            "service": data.get("service"),
            "provider": data.get("provider"),
            "amount": amount,
            "distributor_id": int(data.get("distributor_id") or 0)
        }

        try:
            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO bookings
                (distributor_id, customer_name, email, phone, amount, razorpay_order_id, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (
                data.get("distributor_id"),
                data.get("name"),
                data.get("email"),
                data.get("phone"),
                amount,
                order["id"],
                "CREATED"
            ))
            mysql.connection.commit()
            cur.close()
        except Exception as db_err:
            # Keep payment flow alive even when booking persistence is unavailable.
            print("BOOKING INSERT ERROR:", str(db_err))

        return jsonify(order)

    except Exception as e:
        print("CREATE ORDER ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# ================= VERIFY PAYMENT =================

@app.route("/verify-payment", methods=["POST"])
def verify_payment():

    try:
        data = request.get_json()

        generated_signature = hmac.new(
            bytes(Config.RAZORPAY_SECRET, "utf-8"),
            bytes(data["razorpay_order_id"] + "|" + data["razorpay_payment_id"], "utf-8"),
            hashlib.sha256
        ).hexdigest()

        status = "success" if generated_signature == data["razorpay_signature"] else "failed"
        success_details = {
            "order_id": data.get("razorpay_order_id", "-"),
            "payment_id": data.get("razorpay_payment_id", "-"),
            "signature": data.get("razorpay_signature", "-"),
            "amount": "-",
            "service": "-",
            "provider": "-",
            "phone": "-",
            "used_fallback": False,
            "timestamp": datetime.now().strftime("%d %b %Y, %I:%M:%S %p")
        }
        fail_details = {
            "order_id": data.get("razorpay_order_id", "-"),
            "amount": "-",
            "service": "-",
            "provider": "-",
            "reason": "Signature verification failed",
            "timestamp": datetime.now().strftime("%d %b %Y, %I:%M:%S %p")
        }

        try:
            cur = mysql.connection.cursor()
            booking_info = None
            cur.execute("""
                SELECT b.status, b.phone, b.customer_name, b.email, b.amount, b.distributor_id, d.service, d.company
                FROM bookings b
                LEFT JOIN distributors d ON b.distributor_id = d.id
                WHERE b.razorpay_order_id=%s
                LIMIT 1
            """, (data["razorpay_order_id"],))
            booking_info = cur.fetchone()

            if status != "success":
                cur.execute("UPDATE bookings SET status='FAILED' WHERE razorpay_order_id=%s",
                            (data["razorpay_order_id"],))
            mysql.connection.commit()
            cur.close()

            if status == "success" and booking_info:
                previous_status = booking_info[0]
                phone = booking_info[1]
                customer_name = booking_info[2]
                customer_email = booking_info[3]
                amount = booking_info[4]
                distributor_id = booking_info[5]
                service = booking_info[6]
                provider = booking_info[7]

                success_details.update({
                    "amount": amount if amount is not None else "-",
                    "service": service or "-",
                    "provider": provider or "-",
                    "phone": phone or "-",
                    "distributor_id": distributor_id or 0,
                    "customer_name": customer_name or "-"
                })
                fail_details.update({
                    "amount": amount if amount is not None else "-",
                    "service": service or "-",
                    "provider": provider or "-"
                })

                if data["razorpay_order_id"] not in partner_alert_sent_orders:
                    partner_sent = notify_partner_new_booking(
                        order_id=data.get("razorpay_order_id"),
                        distributor_id=distributor_id,
                        company_name=provider or "",
                        customer_name=customer_name or "",
                        customer_phone=phone or "",
                        customer_email=customer_email or "",
                        service=service or "",
                        amount=amount if amount is not None else 0,
                        host_url=request.host_url
                    )
                    if partner_sent:
                        partner_alert_sent_orders.add(data["razorpay_order_id"])

                if data["razorpay_order_id"] not in whatsapp_sent_orders:
                    send_whatsapp_success_message(phone, customer_name, service, provider)
                    send_booking_success_email(
                        customer_email,
                        customer_name,
                        service,
                        provider,
                        amount,
                        data.get("razorpay_order_id"),
                        data.get("razorpay_payment_id")
                    )
                    whatsapp_sent_orders.add(data["razorpay_order_id"])
            elif status == "success" and data["razorpay_order_id"] not in whatsapp_sent_orders:
                fallback = order_context_store.get(data["razorpay_order_id"], {})
                if fallback:
                    success_details.update({
                        "amount": fallback.get("amount", "-"),
                        "service": fallback.get("service", "-"),
                        "provider": fallback.get("provider", "-"),
                        "phone": fallback.get("phone", "-"),
                        "distributor_id": fallback.get("distributor_id", 0),
                        "customer_name": fallback.get("customer_name", "-")
                    })
                    fail_details.update({
                        "amount": fallback.get("amount", "-"),
                        "service": fallback.get("service", "-"),
                        "provider": fallback.get("provider", "-")
                    })
                    if data["razorpay_order_id"] not in partner_alert_sent_orders:
                        partner_sent = notify_partner_new_booking(
                            order_id=data.get("razorpay_order_id"),
                            distributor_id=fallback.get("distributor_id", 0),
                            company_name=fallback.get("provider", ""),
                            customer_name=fallback.get("customer_name", ""),
                            customer_phone=fallback.get("phone", ""),
                            customer_email=fallback.get("email", ""),
                            service=fallback.get("service", ""),
                            amount=fallback.get("amount", 0),
                            host_url=request.host_url
                        )
                        if partner_sent:
                            partner_alert_sent_orders.add(data["razorpay_order_id"])
                    sent = send_whatsapp_success_message(
                        fallback.get("phone"),
                        fallback.get("customer_name"),
                        fallback.get("service"),
                        fallback.get("provider")
                    )
                    send_booking_success_email(
                        fallback.get("email"),
                        fallback.get("customer_name"),
                        fallback.get("service"),
                        fallback.get("provider"),
                        fallback.get("amount"),
                        data.get("razorpay_order_id"),
                        data.get("razorpay_payment_id")
                    )
                    if sent:
                        whatsapp_sent_orders.add(data["razorpay_order_id"])
        except Exception as db_err:
            print("VERIFY PAYMENT DB ERROR:", str(db_err))
            if status == "success" and data["razorpay_order_id"] not in whatsapp_sent_orders:
                fallback = order_context_store.get(data["razorpay_order_id"], {})
                if fallback:
                    success_details.update({
                        "amount": fallback.get("amount", "-"),
                        "service": fallback.get("service", "-"),
                        "provider": fallback.get("provider", "-"),
                        "phone": fallback.get("phone", "-"),
                        "distributor_id": fallback.get("distributor_id", 0),
                        "customer_name": fallback.get("customer_name", "-")
                    })
                    fail_details.update({
                        "amount": fallback.get("amount", "-"),
                        "service": fallback.get("service", "-"),
                        "provider": fallback.get("provider", "-")
                    })
                    if data["razorpay_order_id"] not in partner_alert_sent_orders:
                        partner_sent = notify_partner_new_booking(
                            order_id=data.get("razorpay_order_id"),
                            distributor_id=fallback.get("distributor_id", 0),
                            company_name=fallback.get("provider", ""),
                            customer_name=fallback.get("customer_name", ""),
                            customer_phone=fallback.get("phone", ""),
                            customer_email=fallback.get("email", ""),
                            service=fallback.get("service", ""),
                            amount=fallback.get("amount", 0),
                            host_url=request.host_url
                        )
                        if partner_sent:
                            partner_alert_sent_orders.add(data["razorpay_order_id"])
                    sent = send_whatsapp_success_message(
                        fallback.get("phone"),
                        fallback.get("customer_name"),
                        fallback.get("service"),
                        fallback.get("provider")
                    )
                    send_booking_success_email(
                        fallback.get("email"),
                        fallback.get("customer_name"),
                        fallback.get("service"),
                        fallback.get("provider"),
                        fallback.get("amount"),
                        data.get("razorpay_order_id"),
                        data.get("razorpay_payment_id")
                    )
                    if sent:
                        whatsapp_sent_orders.add(data["razorpay_order_id"])

        if status == "success":
            session["payment_success_details"] = success_details
            return jsonify({"status": status, "redirect_url": url_for("success")})

        session["payment_fail_details"] = fail_details
        return jsonify({"status": status, "redirect_url": url_for("fail")})
    except Exception as e:
        print("VERIFY PAYMENT ERROR:", str(e))
        return jsonify({"status": "failed", "error": str(e)}), 500


# ================= RESULT PAGES =================

@app.route("/p-success")
def success():
    details = session.pop("payment_success_details", None)
    if not details:
        details = {
            "order_id": "-",
            "payment_id": "-",
            "signature": "-",
            "amount": "-",
            "service": "-",
            "provider": "-",
            "phone": "-",
            "distributor_id": 0,
            "customer_name": "-",
            "used_fallback": False,
            "timestamp": datetime.now().strftime("%d %b %Y, %I:%M:%S %p")
        }
    return render_template("p-success.html", details=details)


@app.route("/submit-review", methods=["POST"])
def submit_review():
    data = request.get_json(silent=True) or {}
    order_id = (data.get("order_id") or "").strip()
    distributor_id = int(data.get("distributor_id") or 0)
    rating = int(data.get("rating") or 0)
    review_text = (data.get("review_text") or "").strip()
    customer_name = (data.get("customer_name") or "Customer").strip()

    if not order_id or distributor_id <= 0:
        return jsonify({"status": "failed", "message": "Invalid booking details"}), 400

    if rating < 1 or rating > 5:
        return jsonify({"status": "failed", "message": "Rating must be between 1 and 5"}), 400

    ensure_reviews_table()
    try:
        cur = mysql.connection.cursor()
        try:
            cur.execute("""
                SELECT distributor_id, status, review_requested_at
                FROM bookings
                WHERE razorpay_order_id=%s
                LIMIT 1
            """, (order_id,))
            row = cur.fetchone()
        except Exception:
            cur.execute("""
                SELECT distributor_id, status
                FROM bookings
                WHERE razorpay_order_id=%s
                LIMIT 1
            """, (order_id,))
            temp_row = cur.fetchone()
            row = (temp_row[0], temp_row[1], None) if temp_row else None
        cur.close()
        if not row:
            return jsonify({"status": "failed", "message": "Booking not found"}), 404

        booking_distributor_id, booking_status, review_requested_at = row
        if int(booking_distributor_id or 0) != distributor_id:
            return jsonify({"status": "failed", "message": "Distributor mismatch"}), 400
        if not review_requested_at and booking_status not in {"COMPLETED"}:
            return jsonify({"status": "failed", "message": "Review opens after distributor marks service as done"}), 400
    except Exception as e:
        print("REVIEW BOOKING VALIDATION ERROR:", str(e))

    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO reviews (booking_order_id, distributor_id, customer_name, rating, review_text)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            rating=VALUES(rating),
            review_text=VALUES(review_text),
            customer_name=VALUES(customer_name)
        """, (order_id, distributor_id, customer_name, rating, review_text))
        try:
            cur.execute("""
                UPDATE bookings
                SET status='REVIEWED', review_submitted_at=NOW()
                WHERE razorpay_order_id=%s
            """, (order_id,))
        except Exception:
            cur.execute("""
                UPDATE bookings
                SET status='REVIEWED'
                WHERE razorpay_order_id=%s
            """, (order_id,))
        mysql.connection.commit()
        cur.close()
        log_notification(
            event_key=f"{order_id}-review-submitted",
            booking_order_id=order_id,
            event_type="REVIEW_SUBMITTED",
            channel="WEB",
            recipient=customer_name,
            status="SENT",
            message=f"Customer submitted rating {rating}",
            error_text=None
        )
        return jsonify({"status": "success"})
    except Exception as e:
        print("SUBMIT REVIEW ERROR:", str(e))
        return jsonify({"status": "failed", "message": "Could not submit review"}), 500


@app.route("/review/<order_id>")
def review_page(order_id):
    ensure_reviews_table()
    try:
        cur = mysql.connection.cursor()
        try:
            cur.execute("""
                SELECT b.razorpay_order_id, b.customer_name, b.status, b.review_requested_at, d.id, d.company, d.service
                FROM bookings b
                JOIN distributors d ON b.distributor_id = d.id
                WHERE b.razorpay_order_id=%s
                LIMIT 1
            """, (order_id,))
            booking = cur.fetchone()
        except Exception:
            cur.execute("""
                SELECT b.razorpay_order_id, b.customer_name, b.status, d.id, d.company, d.service
                FROM bookings b
                JOIN distributors d ON b.distributor_id = d.id
                WHERE b.razorpay_order_id=%s
                LIMIT 1
            """, (order_id,))
            tmp = cur.fetchone()
            booking = (tmp[0], tmp[1], tmp[2], None, tmp[3], tmp[4], tmp[5]) if tmp else None
        cur.close()
    except Exception as e:
        print("REVIEW PAGE ERROR:", str(e))
        booking = None

    if not booking:
        return "Invalid review link", 404

    if not booking[3] and booking[2] != "COMPLETED":
        return "Feedback is not opened yet for this order.", 400

    details = {
        "order_id": booking[0],
        "customer_name": booking[1] or "Customer",
        "status": booking[2] or "-",
        "distributor_id": booking[4],
        "provider": booking[5] or "-",
        "service": booking[6] or "-"
    }
    return render_template("customer-review.html", details=details)


@app.route("/p-fail")
def fail():
    details = session.pop("payment_fail_details", None)
    if not details:
        details = {
            "order_id": "-",
            "amount": "-",
            "service": "-",
            "provider": "-",
            "reason": request.args.get("reason", "Payment was not completed."),
            "timestamp": datetime.now().strftime("%d %b %Y, %I:%M:%S %p")
        }
    return render_template("p-fail.html", details=details)


# ================= RUN =================

if __name__ == "__main__":
    app.run(debug=False)
