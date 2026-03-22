from flask import *
import speech_recognition as sr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from gtts import gTTS 
import os
import platform
import uuid
from flask import copy_current_request_context
import threading
from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify,flash
import os
from datetime import datetime
import re
import time
import random



engine = create_engine("mysql+pymysql://root@localhost:3306/voiceback")
db = scoped_session(sessionmaker(bind=engine))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, "users.db")


app = Flask(__name__)
app.config["SECRET_KEY"] = "voicebackproject123"
app.debug = True
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

recognizer = sr.Recognizer()
def generate_account_number():
    while True:
        account_no = "ABC" + str(random.randint(10000000, 99999999))
        existing = db.execute(
            text("SELECT account_no FROM users WHERE account_no=:acc"),
            {"acc": account_no}
        ).fetchone()
        if not existing:
            return account_no

# ---------------- BALANCE ----------------
@app.route('/balance')
def balance():
    if session.get('user') is not None:
        username = session['user']
        account_balance = db.execute(text("SELECT account_balance FROM users WHERE username = :username"), {"username": username}).fetchone()
        db.commit()
        if account_balance:
            return jsonify({'account_balance': int(account_balance[0])}) 
        else:
            return jsonify({'error': 'User not found'}), 404
    return jsonify({'error': 'User not logged in'}), 403

def get_account_balance():
    mobile = session.get('mobile')

    if not mobile:
        return 0

    result = db.execute(
        text("SELECT account_balance FROM users WHERE mobile=:mobile"),
        {"mobile": mobile}
    ).fetchone()

    db.commit()

    if result:
        return int(result[0])
    else:
        return 0
@app.route("/balance_receipt")
def balance_receipt():

    mobile = session.get("mobile")
    if not mobile:
        return redirect(url_for("login"))

    balance = get_account_balance()
    now = datetime.now()

    session["last_transaction_id"] = "BAL-" + str(uuid.uuid4())[:6]

    fake_data = {
        "username": mobile,
        "account_no": "N/A",
        "mobile": mobile,
        "receiver_mobile": "-",
        "amount": 0,
        "transaction_id": session["last_transaction_id"],
        "transaction_date": now,
        "account_balance": balance
    }

    return render_template("downloadform.html", user=fake_data)

@app.route('/speak_mobile', methods=['POST'])
def speak_mobile():

    data = request.get_json()
    selected_lang = data.get("language", "en")

    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source)

    if selected_lang == "ta":
        text = recognizer.recognize_google(audio, language="ta-IN")
    else:
        text = recognizer.recognize_google(audio, language="en-US")

    # convert digit words to numbers
    text = words_to_digits(text)
    text = re.sub(r'(\d)\s+(?=\d)', r'\1', text)

    mobile_match = re.search(r'\b\d{10}\b', text)

    if mobile_match:
        return jsonify({"mobile": mobile_match.group()})
    else:
        return jsonify({"mobile": ""})



# ---------------- TEXT TO SPEECH ----------------
def format_number_for_speech(text):

    def split_digits(match):
        return " ".join(match.group())

    # Split any 10 digit number into spaced digits
    return re.sub(r'\b\d{10}\b', split_digits, text)

def speak_text(text, lang):
    text = format_number_for_speech(text)

    if lang == "ta":
        tts = gTTS(text=text, lang='ta', slow=False)
    else:
        tts = gTTS(text=text, lang='en', slow=False)

    tts.save("voice.mp3")

    if platform.system() == "Windows":
        os.startfile("voice.mp3")
    else:
        os.system("mpg123 voice.mp3")


# ---------------- PROCESS COMMAND ----------------
import re
from flask import session
from sqlalchemy import text


# ---------------- WORDS TO DIGITS ----------------
def tamil_text_to_number(text):

    tamil_numbers = {
        "பத்து":10, "இருபது":20, "முப்பது":30, "நாற்பது":40,
        "ஐம்பது":50, "அறுபது":60, "எழுபது":70, "எண்பது":80, "தொண்ணூறு":90,
        "நூறு":100
    }

    base_numbers = {
        "ஒன்று":1, "இரண்டு":2, "மூன்று":3, "நான்கு":4,
        "ஐந்து":5, "ஆறு":6, "ஏழு":7, "எட்டு":8, "ஒன்பது":9
    }

    total = 0
    words = text.split()

    for word in words:
        if word in tamil_numbers:
            total += tamil_numbers[word]
        elif word in base_numbers:
            total += base_numbers[word]

    return str(total) if total > 0 else text


def words_to_digits(text):

    number_map = {
        # English
        "zero": "0", "one": "1", "two": "2", "three": "3",
        "four": "4", "five": "5", "six": "6",
        "seven": "7", "eight": "8", "nine": "9",

        # Tamil basic
        "பூஜ்யம்": "0",
        "ஒன்று": "1",
        "இரண்டு": "2",
        "மூன்று": "3",
        "நான்கு": "4",
        "ஐந்து": "5",
        "ஆறு": "6",
        "ஏழு": "7",
        "எட்டு": "8",
        "ஒன்பது": "9"
    }

    words = text.split()
    converted = []

    for word in words:
        if word in number_map:
            converted.append(number_map[word])
        else:
            converted.append(word)

    return " ".join(converted)


# ---------------- MAIN PROCESS FUNCTION ----------------
def process_command(command, account_balance, lang, typed_mobile=None):

    cmd = str(command).lower().strip()
    cmd = tamil_text_to_number(cmd)
    cmd = words_to_digits(cmd)
    cmd = re.sub(r'(\d)\s+(?=\d)', r'\1', cmd)

    print("Processed command:", cmd)

    # ---------------- BALANCE CHECK ----------------
    if any(word in cmd for word in ["account balance", "balance", "பேலன்ஸ்", "இருப்பு"]):

        if lang == "ta":
            return f"உங்கள் கணக்கு இருப்பு {account_balance} ரூபாய்."
        else:
            return f"Your account balance is {account_balance} rupees."

    # ---------------- SEND MONEY (OTP FLOW) ----------------
    elif (
        any(word in cmd for word in ["send", "transfer", "pay"]) or
        any(word in cmd for word in ["அனுப்பு", "அனுப்ப", "அனுப்பவும்", "அனுப்பணும்", "பணம்"])
    ):

        mobile_match = re.search(r'\b\d{10}\b', cmd)
        receiver_mobile = mobile_match.group() if mobile_match else typed_mobile

        if not receiver_mobile:
            return "Receiver mobile not found." if lang == "en" else "பெறுநர் எண் கிடைக்கவில்லை."

        cmd_without_mobile = cmd.replace(receiver_mobile, "")
        amount_match = re.search(r'\b\d{1,6}\b', cmd_without_mobile)
        amount = int(amount_match.group()) if amount_match else None

        if not amount:
            return "Amount not found." if lang == "en" else "தொகை கிடைக்கவில்லை."

        if amount > account_balance:
            return "Insufficient balance." if lang == "en" else "போதுமான இருப்பு இல்லை."

        # Save pending transfer
        session["pending_transfer"] = {
            "receiver_mobile": receiver_mobile,
            "amount": amount
        }

        # Generate OTP
        otp = str(random.randint(100000, 999999))
        session["voice_otp"] = otp
        session["otp_verified"] = False

        db.execute(
            text("INSERT INTO otp_logs (mobile, otp_code, status) VALUES (:m,:o,'sent')"),
            {"m": session.get("mobile"), "o": otp}
        )
        db.commit()

        print("Generated OTP:", otp)

        return "redirect_otp_page"

    # ---------------- DEFAULT ----------------
    else:
        return "Sorry, I didn't understand." if lang == "en" else "மன்னிக்கவும் புரியவில்லை."
    
# ---------------- VOICE COMMAND ----------------

@app.route('/voice_command', methods=['POST'])
def voice_command():

    if not session.get('mobile'):
        return jsonify({'error': 'User not logged in'}), 403

    try:
        data = request.get_json()
        selected_lang = data.get("language", "en")

        # Save selected language
        session['last_lang'] = selected_lang

        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            recognizer.pause_threshold = 1.2
            print("Listening...")
            audio_data = recognizer.listen(source, timeout=7, phrase_time_limit=10)

        # Recognition
        if selected_lang == "ta":
            command = recognizer.recognize_google(audio_data, language="ta-IN")
            detected_lang = "ta"
        else:
            command = recognizer.recognize_google(audio_data, language="en-US")
            detected_lang = "en"

        print("User said:", command)

        account_balance = int(get_account_balance())
        typed_mobile = data.get("typed_mobile", "")
        response_text = str(process_command(
            command,
            account_balance,
            detected_lang,
            typed_mobile
))

        if response_text == "redirect_otp_page":
            return jsonify({"redirect": "/voice_otp_page"})



        # ✅ SAFE THREAD FUNCTION
        @copy_current_request_context
        def run_speech():
            speak_text(response_text, detected_lang)
            
        threading.Thread(target=run_speech).start()

        return jsonify({
            'request_text': command,
            'response_text': response_text,
            'language': detected_lang
        })

    except sr.WaitTimeoutError:
        return jsonify({'error': "Listening timed out. Try again."})

    except sr.UnknownValueError:
        return jsonify({'error': "Could not understand the audio."})

    except sr.RequestError:
        return jsonify({'error': "Internet connection problem. Check your network."})

    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/acknow')
def acknow():

    if not session.get('mobile'):
        return redirect(url_for('login'))

    tid = session.get("last_transaction_id")

    if not tid:
        return "No transaction found"

    with engine.connect() as db:
        result = db.execute(text("""
            SELECT 
                t.sender_mobile,
                t.receiver_mobile,
                t.amount,
                t.transaction_id,
                t.transaction_date,
                u.username,
                u.account_no,
                u.account_balance
            FROM transactions t
            JOIN users u ON t.sender_mobile = u.mobile
            WHERE t.transaction_id = :tid
        """), {"tid": tid}).mappings().fetchone()

    if not result:
        return "Transaction not found"

    user_data = {
        "username": result["username"],
        "account_no": result["account_no"],
        "mobile": result["sender_mobile"],
        "receiver_mobile": result["receiver_mobile"],
        "amount": result["amount"],
        "transaction_id": result["transaction_id"],
        "date_time": result["transaction_date"].strftime("%d-%m-%Y %I:%M:%S %p"),
        "balance": result["account_balance"]
    }

    return render_template("downloadform.html", user=user_data)


@app.route('/download_receipt')
def download_receipt():
    return "Download working"


# ---------------- ROUTES ----------------
@app.before_request
def set_default_language():
    if 'lang' not in session:
        session['lang'] = 'en'

@app.route('/')
def index():
    return render_template("index.html", lang=session.get('lang'))


# -------------------------------
# LOGIN
# -------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form["mobile"]

        with engine.connect() as db:
            user = db.execute(
                text("SELECT * FROM users WHERE mobile=:m"),
                {"m": mobile}
            ).fetchone()

        if user:
            session["mobile"] = mobile
            return redirect(url_for("dashboard"))
        else:
            flash("User not found")

    return render_template("login.html")


# -------------------------------
# DASHBOARD
# -------------------------------
@app.route("/dashboard")
def dashboard():

    mobile = session.get("mobile")

    if not mobile:
        return redirect(url_for("login"))

    with engine.begin() as db:
        result = db.execute(text("""
            SELECT account_balance 
            FROM users 
            WHERE mobile = :m
        """), {"m": mobile})

        row = result.fetchone()

    balance = row[0] if row else 0

    success_data = session.pop("voice_success", None)

    return render_template(
        "home.html",
        balance=balance,
        success_data=success_data
    )
# -------------------------------
# SEND MONEY - STEP 1 (Generate OTP)
# -------------------------------
@app.route("/send_money", methods=["POST"])
def send_money():

    if not session.get("mobile"):
        return redirect(url_for("login"))

    sender = session["mobile"]
    receiver = request.form["receiver"]
    amount = float(request.form["amount"])

    with engine.connect() as db:
        # Check sender blocked
        sender_data = db.execute(
            text("SELECT is_blocked FROM users WHERE mobile=:m"),
            {"m": sender}
        ).fetchone()

        if sender_data[0]:
            return "Account Blocked!"

        # Check receiver exists
        receiver_data = db.execute(
            text("SELECT * FROM users WHERE mobile=:m"),
            {"m": receiver}
        ).fetchone()

        if not receiver_data:
            return "Receiver mobile not found"

    # Generate OTP
    otp = str(random.randint(100000, 999999))
    session["otp"] = otp
    session["receiver"] = receiver
    session["amount"] = amount

    # Save OTP log
    with engine.begin() as db:
        db.execute(
            text("INSERT INTO otp_logs (mobile, otp_code, status) VALUES (:m, :o, 'sent')"),
            {"m": sender, "o": otp}
        )

    print("OTP:", otp)  # For testing

    return render_template("verify_otp.html")


# -------------------------------
# VERIFY OTP
# -------------------------------
@app.route("/verify_otp", methods=["POST"])
def verify_otp():

    if not session.get("mobile"):
        return redirect(url_for("login"))

    entered_otp = request.form["otp"]
    sender = session["mobile"]

    with engine.connect() as db:
        user = db.execute(
            text("SELECT failed_otp_attempts, is_blocked, account_balance FROM users WHERE mobile=:m"),
            {"m": sender}
        ).fetchone()

    failed_attempts = user[0]
    is_blocked = user[1]
    balance = float(user[2])

    if is_blocked:
        return "Account Blocked!"

    # Correct OTP
    if entered_otp == session.get("otp"):

        receiver = session["receiver"]
        amount = float(session["amount"])

        if balance < amount:
            return "Insufficient Balance"

        transaction_id = "TXN" + datetime.now().strftime("%y%m%d") + str(random.randint(100,999))
        now = datetime.now()

        with engine.begin() as db:
            # Deduct sender
            db.execute(
                text("UPDATE users SET account_balance = account_balance - :amt, failed_otp_attempts=0 WHERE mobile=:m"),
                {"amt": amount, "m": sender}
            )

            # Add receiver
            db.execute(
                text("UPDATE users SET account_balance = account_balance + :amt WHERE mobile=:m"),
                {"amt": amount, "m": receiver}
            )

            # Save transaction
            db.execute(
                text("""INSERT INTO transactions 
                        (sender_mobile, receiver_mobile, amount, transaction_id, transaction_date)
                        VALUES (:s, :r, :a, :tid, :dt)"""),
                {
                    "s": sender,
                    "r": receiver,
                    "a": amount,
                    "tid": transaction_id,
                    "dt": now
                }
            )

            # OTP success log
            db.execute(
                text("INSERT INTO otp_logs (mobile, otp_code, status) VALUES (:m, :o, 'success')"),
                {"m": sender, "o": entered_otp}
            )

        session["last_transaction_id"] = transaction_id

        return redirect(url_for("receipt"))

    # Wrong OTP
    else:

        failed_attempts += 1

        with engine.begin() as db:
            db.execute(
                text("UPDATE users SET failed_otp_attempts=:f WHERE mobile=:m"),
                {"f": failed_attempts, "m": sender}
            )

            db.execute(
                text("INSERT INTO otp_logs (mobile, otp_code, status) VALUES (:m, :o, 'failed')"),
                {"m": sender, "o": entered_otp}
            )

            if failed_attempts >= 3:
                db.execute(
                    text("UPDATE users SET is_blocked=TRUE WHERE mobile=:m"),
                    {"m": sender}
                )
                return "Account Blocked due to 3 wrong OTP attempts!"

        return "Wrong OTP"
# Generate OTP Page
@app.route("/voice_otp_page")
def voice_otp_page():

    if not session.get("voice_otp"):
        return redirect(url_for("dashboard"))

    return render_template("voice_otp.html")

# Verify OTP (AJAX)
@app.route("/verify_voice_otp", methods=["POST"])
def verify_voice_otp():

    data = request.get_json()
    user_otp = data.get("otp")

    session_otp = session.get("voice_otp")
    lang = session.get("last_lang", "en")

    if not session_otp:
        return jsonify({"status": "expired"})

    if str(user_otp).strip() == str(session_otp).strip():

        pending = session.get("pending_transfer")

        if not pending:
            return jsonify({"status": "error"})

        sender = session.get("mobile")
        receiver = pending["receiver_mobile"]
        amount = float(pending["amount"])

        current_balance = get_account_balance()

        if amount > current_balance:
            return jsonify({"status": "insufficient"})

        transaction_id = "TXN" + datetime.now().strftime("%y%m%d") + str(random.randint(100,999))
        now = datetime.now()

        with engine.begin() as db:

            # ✅ Get receiver name INSIDE DB block
            receiver_data = db.execute(
                text("SELECT username FROM users WHERE mobile=:m"),
                {"m": receiver}
            ).fetchone()

            receiver_name = receiver_data[0] if receiver_data else "User"

            # Deduct sender
            db.execute(text("""
                UPDATE users 
                SET account_balance = account_balance - :amt 
                WHERE mobile=:m
            """), {"amt": amount, "m": sender})

            # Add receiver
            db.execute(text("""
                UPDATE users 
                SET account_balance = account_balance + :amt 
                WHERE mobile=:m
            """), {"amt": amount, "m": receiver})

            # Save transaction
            db.execute(text("""
                INSERT INTO transactions
                (sender_mobile, receiver_mobile, amount, transaction_id, transaction_date)
                VALUES (:s, :r, :a, :tid, :dt)
            """), {
                "s": sender,
                "r": receiver,
                "a": amount,
                "tid": transaction_id,
                "dt": now
            })

        updated_balance = get_account_balance()

        session.pop("voice_otp", None)
        session.pop("pending_transfer", None)

        session["voice_success"] = {
            "amount": amount,
            "receiver_name": receiver_name,
            "balance": updated_balance,
            "lang": lang
        }
        
        # ✅ SAVE LAST TRANSACTION ID
        session["last_transaction_id"] = transaction_id

# ✅ SAVE RECEIPT DATA (for dashboard voice message also)
        session["voice_success"] = {
    "amount": amount,
    "receiver_name": receiver_name,
    "balance": updated_balance,
    "lang": lang
}

        return jsonify({
            "status": "success",
            "redirect": "/dashboard"
        })

    else:
        return jsonify({"status": "fail"})
    

# Resend OTP
@app.route("/resend_voice_otp")
def resend_voice_otp():

    otp = str(random.randint(100000, 999999))
    session["voice_otp"] = otp

    print("Resent OTP:", otp)

    return jsonify({"status": "resent"})

# -------------------------------
# RECEIPT DOWNLOAD PAGE
# -------------------------------
@app.route("/receipt")
def receipt():

    tid = session.get("last_transaction_id")

    if not tid:
        return "No transaction found in session"

    with engine.connect() as db:
        result = db.execute(text("""
            SELECT 
                t.sender_mobile,
                t.receiver_mobile,
                t.amount,
                t.transaction_id,
                t.transaction_date,
                u.username,
                u.account_no,
                u.account_balance
            FROM transactions t
            JOIN users u ON t.sender_mobile = u.mobile
            WHERE t.transaction_id = :tid
        """), {"tid": tid}).mappings().fetchone()

    if result is None:
        return f"No transaction found for ID: {tid}"

    user_data = {
        "username": result.get("username"),
        "account_no": result.get("account_no"),
        "mobile": result.get("sender_mobile"),
        "receiver_mobile": result.get("receiver_mobile"),
        "amount": result.get("amount"),
        "transaction_id": result.get("transaction_id"),
        "date_time": result.get("transaction_date").strftime("%d-%m-%Y %H:%M:%S")
                        if result.get("transaction_date") else "",
        "balance": result.get("account_balance")
    }

    return render_template("downloadform.html", user=user_data)


@app.route('/setlang/<lang>')
def set_language(lang):
    session['lang'] = lang
    return redirect(request.referrer or url_for('index'))


@app.route('/home')
def home():
    if session.get("mobile"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route('/logincheck', methods=['POST'])
def logincheck():
    mobile = request.form.get('mobile').strip()
    password = request.form.get('password').strip()

    user = db.execute(
        text("SELECT username, mobile, role FROM users WHERE mobile=:mobile AND password=:password"),
        {"mobile": mobile, "password": password}
    ).fetchone()

    if user:
        session['user'] = user[0]
        session['mobile'] = user[1]
        session['role'] = user[2]

        if user[2] == "admin":
            return redirect(url_for('admindashboard'))
        else:
            return redirect(url_for('home'))
    else:
        return render_template('login.html', error="Invalid mobile/password")

    
# ---------------- ADMIN LOGIN ---------------- #

@app.route('/admin', methods=['GET', 'POST'])
def adminlogin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == "admin" and password == "1234":
            session['admin'] = True
            return render_template('admindashboard.html')
        else:
            return "Invalid Admin Credentials"

    return render_template('adminlogin.html')


# ---------------- ADMIN DASHBOARD ---------------- #

@app.route('/admindashboard')
def admindashboard():
    if session.get('role') == 'admin':
        return render_template('admindashboard.html')
    return redirect(url_for('adminlogin'))


# ---------------- ADMIN USER PAGE ---------------- #
@app.route('/adminuser')
def adminuser():

    users = db.execute(text("""
        SELECT username, mobile, password, account_balance, account_no
        FROM users
    """)).fetchall()

    return render_template('adminuser.html', users=users)



@app.route('/deleteuser/<mobile>')
def deleteuser(mobile):
    if not session.get('admin'):
        return redirect(url_for('adminlogin'))

    db.execute(text("DELETE FROM users WHERE mobile=:mobile"),
               {"mobile": mobile})
    db.commit()

    return redirect(url_for('adminuser'))

@app.route('/edituser/<mobile>', methods=['GET', 'POST'])
def edituser(mobile):
    if not session.get('admin'):
        return redirect(url_for('adminlogin'))

    if request.method == 'POST':
        new_username = request.form['username'].strip()
        new_mobile = request.form['mobile'].strip()
        new_balance = request.form['balance'].strip()
        new_password = request.form['password'].strip()

        db.execute(text("""
            UPDATE users
            SET username=:username,
                mobile=:new_mobile,
                password=:password,
                account_balance=:balance
            WHERE mobile=:old_mobile
        """), {
            "username": new_username,
            "new_mobile": new_mobile,
            "password": new_password,
            "balance": new_balance,
            "old_mobile": mobile
        })

        db.commit()
        return redirect(url_for('adminuser'))

    user = db.execute(
        text("SELECT username, mobile, password, account_balance FROM users WHERE mobile=:mobile"),
        {"mobile": mobile}
    ).fetchone()

    return render_template('edituser.html', user=user)



# ---------------- ADD NEW USER ---------------- #
@app.route('/adduser', methods=['GET', 'POST'])
def adduser():
    if not session.get('admin'):
        return redirect(url_for('adminlogin'))

    if request.method == 'POST':
        username = request.form['username']
        mobile = request.form['mobile']
        password = request.form['password']
        balance = request.form['balance']
        role = request.form['role']

        account_no = generate_account_number()

        db.execute(text("""
            INSERT INTO users (username, mobile, password, account_balance, account_no, role)
            VALUES (:username, :mobile, :password, :balance, :account_no, :role)
        """), {
            "username": username,
            "mobile": mobile,
            "password": password,
            "balance": balance,
            "account_no": account_no,
            "role": role
        })

        db.commit()
        return redirect(url_for('adminuser'))

    return render_template('adduser.html')



@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))



if __name__ == '__main__':
    app.run(debug=True)
