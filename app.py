# 1. الترقيع الجوهري - يجب أن يكون في السطر الأول تماماً
import eventlet
eventlet.monkey_patch()

# 2. الاستدعاءات الخاصة بك
from flask import Flask, render_template, request, jsonify, url_for, send_file
from flask_socketio import SocketIO, join_room, emit, leave_room as flask_leave_room
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text  # مطلوب لتنفيذ أمر الترقيع الآمن
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import os
import json
import subprocess
import io
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'anas_chat_437_ultra'

# إعداد المجلدات المحلية (مؤقتة في بيئة Render سيتم رفعها لـ Neon لاحقاً)
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 3. إعدادات قاعدة البيانات (متوافقة تماماً مع Render و Neon Postgres)
db_url = os.environ.get('DATABASE_URL', 'sqlite:///anas_chat_v14.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,  # يتأكد من سلامة الاتصال قبل الإرسال
    "pool_recycle": 280,    # يعيد تدوير الاتصال قبل أن يقطعه السيرفر
    "pool_timeout": 20
}

db = SQLAlchemy(app)

# 4. إعدادات SocketIO لدعم الاتصال الخارجي والملفات الكبيرة
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='eventlet',
    max_http_buffer_size=50 * 1024 * 1024  # السماح برفع ملفات حتى 50 ميجا
)

# كلمة سر الأدمن الخاصة بك
ADMIN_PASSWORD = "anas_anas_anas_anas_anas"

# --- الجداول وقاعدة البيانات ---
class SiteSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    global_password = db.Column(db.String(100), default="anas2026")

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(50))
    username = db.Column(db.String(50))
    content = db.Column(db.String(2000))
    reply_to = db.Column(db.String(1000))
    file = db.Column(db.String(1000))
    file_type = db.Column(db.String(20))
    time = db.Column(db.String(20))
    reactions = db.Column(db.String(2000), default="{}")
    is_uploaded = db.Column(db.Boolean, default=False)

class FileStorage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), unique=True)
    data = db.Column(db.LargeBinary)

class BannedDevice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(150), unique=True)

class BannedIP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(100), unique=True)

class VisitorLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    ip_address = db.Column(db.String(100))
    device_id = db.Column(db.String(150))
    room_name = db.Column(db.String(50))
    last_visit = db.Column(db.String(50))

# ========================================================
# 5. بناء وتحديث قاعدة البيانات بأمان تام
# ========================================================
with app.app_context():
    db.create_all()
    try:
        db.session.execute(text('ALTER TABLE message ADD COLUMN is_uploaded BOOLEAN DEFAULT FALSE;'))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        
    configs = SiteSetting.query.order_by(SiteSetting.id.asc()).all()
    if not configs:
        db.session.add(SiteSetting(global_password="anas2026"))
        db.session.commit()
    elif len(configs) > 1:
        for c in configs[1:]:
            db.session.delete(c)
        db.session.commit()

# --- دالة رفع الملفات المرفقة إلى Neon ---
def save_files_to_neon():
    pending_messages = Message.query.filter(Message.file != None, Message.is_uploaded == False).all()
    for msg in pending_messages:
        if not msg.file: 
            continue
        filename = msg.file.split('/')[-1]
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        if os.path.exists(local_path):
            try:
                with open(local_path, 'rb') as f:
                    file_data = f.read()
                
                existing_file = FileStorage.query.filter_by(filename=filename).first()
                if not existing_file:
                    new_file = FileStorage(filename=filename, data=file_data)
                    db.session.add(new_file)
                
                msg.is_uploaded = True
                db.session.commit()
                
                # حذف الملف المحلي لتوفير المساحة
                os.remove(local_path)
                print(f"تم رفع الملف بنجاح إلى Neon: {filename}")
            except Exception as e:
                db.session.rollback()
                print(f"فشل في رفع الملف {filename}: {e}")

# -------------------------------------------------------------
# دالة الساعة 23:00 (رفع + حذف ما يزيد عن 500 رسالة)
# -------------------------------------------------------------
def task_at_23_gmt():
    with app.app_context():
        try:
            # أولاً: رفع/حفظ الملفات الجديدة إلى Neon
            save_files_to_neon()
            
            # ثانياً: جلب الرسائل القديمة (ما بعد أحدث 500 رسالة) وحذفها مع ملفاتها
            old_messages = Message.query.order_by(Message.id.desc()).offset(500).all()
            for msg in old_messages:
                if msg.file and msg.is_uploaded:
                    filename = msg.file.split('/')[-1]
                    file_record = FileStorage.query.filter_by(filename=filename).first()
                    if file_record:
                        db.session.delete(file_record)
                db.session.delete(msg)
            
            db.session.commit()
            print("[23:00 GMT] تم حفظ الملفات وتنظيف الرسائل (تم الإبقاء على 500 رسالة).")
            
        except Exception as e:
            db.session.rollback()
            print(f"[23:00 GMT] حدث خطأ: {e}")

# -------------------------------------------------------------
# دالة الساعة 03:00 (رفع/حفظ الرسائل المتراكمة فقط - بدون أي حذف)
# -------------------------------------------------------------
def task_at_03_gmt():
    with app.app_context():
        try:
            save_files_to_neon()
            db.session.commit()
            print("[03:00 GMT] تم حفظ الملفات الجديدة المتراكمة بنجاح (بدون حذف أي رسائل).")
        except Exception as e:
            db.session.rollback()
            print(f"[03:00 GMT] حدث خطأ: {e}")

# -------------------------------------------------------------
# إعداد المجدول بتوقيت غرينتش (UTC)
# -------------------------------------------------------------
scheduler = BackgroundScheduler(daemon=True)

scheduler.add_job(func=task_at_23_gmt, trigger='cron', hour=23, minute=0, timezone=pytz.utc)
scheduler.add_job(func=task_at_03_gmt, trigger='cron', hour=3, minute=0, timezone=pytz.utc)
scheduler.start()

def get_site_setting():
    return SiteSetting.query.order_by(SiteSetting.id.asc()).first()

# الهياكل المؤقتة في الذاكرة الحية
active_sessions = {}
offline_history = {}

def get_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]

def compress_video(input_path):
    output_path = input_path + "_compressed.mp4"
    try:
        cmd = f"ffmpeg -y -i {input_path} -vcodec libx264 -crf 28 -preset fast -acodec aac {output_path}"
        subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(output_path) and os.path.getsize(output_path) < os.path.getsize(input_path):
            os.remove(input_path)
            os.rename(output_path, input_path)
    except Exception as e:
        print("فشل ضغط الفيديو، سيتم إرساله بالحجم الأصلي كبديل آمن:", e)
        if os.path.exists(output_path):
            os.remove(output_path)

@app.before_request
def check_global_ip_ban():
    if request.endpoint and request.endpoint.startswith('static'):
        return
    if BannedIP.query.filter_by(ip_address=get_ip()).first():
        return "<h1>أنت محظور نهائياً من دخول هذا الموقع.</h1>", 403

# --- مسارات الويب الـ HTTP API ---
@app.route('/admin_gate')
def admin_gate():
    p = request.args.get('pass')
    if p == ADMIN_PASSWORD:
        online = [v for v in active_sessions.values()]
        banned_devs = BannedDevice.query.all()
        banned_ips = BannedIP.query.all()
        history = VisitorLog.query.order_by(VisitorLog.id.desc()).all()
        rooms = Room.query.all()
        
        config = get_site_setting()
        global_pass = config.global_password if config else "anas2026"
        
        return render_template('admin.html', online=online, banned_devs=banned_devs, banned_ips=banned_ips, history=history, rooms=rooms, global_pass=global_pass)
    return "خطأ في كلمة السر", 401

@app.route('/api/check_global_pass', methods=['POST'])
def check_global_pass():
    data = request.json
    config = get_site_setting()
    current_pass = config.global_password if config else "anas2026"
    if data.get('password') == current_pass:
        return jsonify({"status": "success"})
    return jsonify({"status": "wrong"}), 401

@app.route('/api/admin/update_global_pass', methods=['POST'])
def admin_update_global_pass():
    data = request.json
    if data.get('pass') == ADMIN_PASSWORD:
        new_pass = data.get('new_global_pass').strip()
        if not new_pass:
             return jsonify({"status": "error", "msg": "كلمة السر فارغة"}), 400
        
        config = get_site_setting()
        config.global_password = new_pass
        db.session.commit()
        return jsonify({"status": "success"})
    return jsonify({"status": "unauthorized"}), 401

@app.route('/api/admin/delete_room', methods=['POST'])
def admin_delete_room():
    data = request.json
    if data.get('pass') == ADMIN_PASSWORD:
        room_id = data.get('room_id')
        room = Room.query.get(room_id)
        if room:
            Message.query.filter_by(room=room.name).delete()
            db.session.delete(room)
            db.session.commit()
            return jsonify({"status": "success"})
    return jsonify({"status": "unauthorized"}), 401

@app.route('/api/admin/delete_log', methods=['POST'])
def admin_delete_log():
    data = request.json
    if data.get('pass') == ADMIN_PASSWORD:
        log_id = data.get('log_id')
        if log_id == "all":
            VisitorLog.query.delete()
            offline_history.clear()
            rooms = Room.query.all()
            for r in rooms:
                socketio.emit('offline_history_update', {}, to=r.name)
        else:
            log = VisitorLog.query.get(log_id)
            if log:
                if log.room_name in offline_history and log.username in offline_history[log.room_name]:
                    del offline_history[log.room_name][log.username]
                    socketio.emit('offline_history_update', offline_history[log.room_name], to=log.room_name)
                db.session.delete(log)
        db.session.commit()
        return jsonify({"status": "success"})
    return jsonify({"status": "unauthorized"}), 401

@app.route('/api/ban', methods=['POST'])
def api_ban():
    data = request.json
    if data.get('pass') == ADMIN_PASSWORD:
        dev_id = data.get('device_id')
        ip = data.get('ip')
        if dev_id and not BannedDevice.query.filter_by(device_id=dev_id).first():
            db.session.add(BannedDevice(device_id=dev_id))
        if ip and not BannedIP.query.filter_by(ip_address=ip).first():
            db.session.add(BannedIP(ip_address=ip))
        db.session.commit()
        for sid, session in list(active_sessions.items()):
            if (dev_id and session['device_id'] == dev_id) or (ip and session['ip'] == ip):
                socketio.emit('kick_banned', {}, to=sid)
        return jsonify({"status": "success"})
    return jsonify({"status": "unauthorized"}), 401

@app.route('/api/unban', methods=['POST'])
def api_unban():
    data = request.json
    if data.get('pass') == ADMIN_PASSWORD:
        dev_id = data.get('device_id')
        ip = data.get('ip')
        if dev_id:
            ban_entry = BannedDevice.query.filter_by(device_id=dev_id).first()
            if ban_entry: db.session.delete(ban_entry)
        if ip:
            ban_entry = BannedIP.query.filter_by(ip_address=ip).first()
            if ban_entry: db.session.delete(ban_entry)
        db.session.commit()
        return jsonify({"status": "success"})
    return jsonify({"status": "unauthorized"}), 401

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.json
    if Room.query.filter_by(name=data['name']).first():
        return jsonify({"msg": "اسم الغرفة موجود مسبقاً!"})
    db.session.add(Room(name=data['name'], password=data['password']))
    db.session.commit()
    return jsonify({"msg": "تم الإنشاء بنجاح ✅"})

@app.route('/upload_chunk', methods=['POST'])
def upload_chunk():
    file = request.files['chunk']
    fname = request.form['filename']
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], fname)
    with open(filepath, "ab") as f:
        f.write(file.read())
    return jsonify({"status": "success"})

@app.route('/file/<filename>')
def serve_file(filename):
    db_file = FileStorage.query.filter_by(filename=filename).first()
    if db_file:
        return send_file(io.BytesIO(db_file.data), download_name=filename)
        
    local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(local_path):
        return send_file(local_path)
        
    return "File not found", 404

@app.route('/api/user-disconnect', methods=['POST'])
def api_user_disconnect():
    try:
        data = json.loads(request.data.decode('utf-8'))
        user = data.get('user')
        room = data.get('room')
        reason = data.get('reason', 'انقطاع النت / خروج مفاجئ')
        ts = data.get('time', datetime.now().strftime("%I:%M %p"))
        
        keys_to_delete = [sid for sid, s in active_sessions.items() if s['user'] == user and s['room'] == room]
        for sid in keys_to_delete:
            active_sessions.pop(sid, None)
            
        if room:
            if room not in offline_history: offline_history[room] = {}
            offline_history[room][user] = {'time': ts, 'reason': reason}
            socketio.emit('offline_history_update', offline_history[room], to=room)
            
        users = [s['user'] for s in active_sessions.values() if s['room'] == room]
        socketio.emit('update_users', {'users': users}, to=room)
    except Exception as e:
        pass
    return jsonify({"status": "ok"})

# --- أحداث الـ SocketIO ---
@socketio.on('join')
def on_join(data):
    dev_id = data.get('device_id')
    ip = get_ip()
    if BannedDevice.query.filter_by(device_id=dev_id).first() or BannedIP.query.filter_by(ip_address=ip).first():
        emit('join_status', 'banned')
        return
    r = Room.query.filter_by(name=data['room'], password=data['password']).first()
    if r:
        join_room(data['room'])
        active_sessions[request.sid] = {'user': data['username'], 'room': data['room'], 'ip': ip, 'device_id': dev_id}
        
        log = VisitorLog.query.filter_by(device_id=dev_id, room_name=data['room']).first()
        if not log:
            db.session.add(VisitorLog(username=data['username'], ip_address=ip, device_id=dev_id, room_name=data['room'], last_visit=datetime.now().strftime("%Y-%m-%d %H:%M")))
        else:
            log.username = data['username']
            log.ip_address = ip
            log.last_visit = datetime.now().strftime("%Y-%m-%d %H:%M")
        db.session.commit()
        
        emit('join_status', 'success')
        
        if data['room'] in offline_history:
            if data['username'] in offline_history[data['room']]:
                del offline_history[data['room']][data['username']]
            emit('offline_history_update', offline_history[data['room']], to=data['room'])
            
        users = [s['user'] for s in active_sessions.values() if s['room'] == data['room']]
        emit('update_users', {'users': users}, to=data['room'])
        
        recent_messages = Message.query.filter_by(room=data['room']).order_by(Message.id.desc()).limit(150).all()
        history_data = []
        for m in reversed(recent_messages):
            history_data.append({
                "id": m.id, "username": m.username, "msg": m.content,
                 "reply_to": m.reply_to, "file": m.file, "file_type": m.file_type,
                 "time": m.time, "reactions": m.reactions
            })
        emit('load_history', history_data)
    else:
        emit('join_status', 'error')

@socketio.on('request_more_messages')
def request_more_messages(data):
    room = data.get('room')
    oldest_id = data.get('oldest_id')
    if not room or not oldest_id: return
    older_messages = Message.query.filter(Message.room == room, Message.id < oldest_id).order_by(Message.id.desc()).limit(150).all()
    history_data = []
    for m in older_messages:
        history_data.append({
            "id": m.id, "username": m.username, "msg": m.content,
             "reply_to": m.reply_to, "file": m.file, "file_type": m.file_type,
             "time": m.time, "reactions": m.reactions
        })
    emit('receive_more_messages', history_data, to=request.sid)

@socketio.on('leave_room')
def on_leave_room_client(data):
    active_sessions.pop(request.sid, None)
    room = data.get('room')
    user = data.get('username')
    reason = data.get('reason', 'خروج عادي')
    ts = datetime.now().strftime("%I:%M %p")
    
    if room:
        flask_leave_room(room)
        if room not in offline_history: offline_history[room] = {}
        offline_history[room][user] = {'time': ts, 'reason': reason}
        socketio.emit('offline_history_update', offline_history[room], to=room)
        
    users = [s['user'] for s in active_sessions.values() if s['room'] == room]
    socketio.emit('update_users', {'users': users}, to=room)

@socketio.on('disconnect')
def on_disconnect():
    s = active_sessions.pop(request.sid, None)
    if s:
        room = s['room']
        user = s['user']
        ts = datetime.now().strftime("%I:%M %p")
        reason = "انقطاع الاتصال"
        
        if room not in offline_history: offline_history[room] = {}
        offline_history[room][user] = {'time': ts, 'reason': reason}
        socketio.emit('offline_history_update', offline_history[room], to=room)
        
        users = [ss['user'] for ss in active_sessions.values() if ss['room'] == room]
        socketio.emit('update_users', {'users': users}, to=room)
        socketio.emit('message', {
            "id": f"sys_leave_{request.sid}",
            "username": "⚙️ النظام",
            "msg": f"لقد غادر/ت {user} الدردشة.",
            "reply_to": None, "file": None, "file_type": None,
            "time": ts, "reactions": "{}"
        }, to=room)

@socketio.on('message')
def handle_msg(data):
    session_data = active_sessions.get(request.sid)
    if not session_data or BannedDevice.query.filter_by(device_id=session_data['device_id']).first() or BannedIP.query.filter_by(ip_address=session_data['ip']).first():
        return
        
    ts = datetime.now().strftime("%I:%M %p")
    ft = None
    final_file_url = None
    
    if data.get('file'):
        ext = data['file'].split('.')[-1].lower()
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']: ft = 'image'
        elif ext in ['mp4', 'webm', 'ogg', 'mov']: ft = 'video'
        elif ext in ['mp3', 'wav', 'weba', 'm4a']: ft = 'audio'
        else: ft = 'file'
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], data['file'])
        if os.path.exists(filepath):
            if ft == 'video':
                compress_video(filepath)
            
            final_file_url = f"/file/{data['file']}"
            
    new_m = Message(
        room=data['room'],
        username=data['username'],
        content=data.get('msg'),
        reply_to=data.get('reply_to'),
        file=final_file_url,
        file_type=ft,
        time=ts,
        reactions="{}",
        is_uploaded=False
    )
    db.session.add(new_m)
    db.session.commit()
    
    emit('message', {"id": new_m.id, "username": data['username'], "msg": data.get('msg'), "reply_to": data.get('reply_to'), "file": final_file_url, "file_type": ft, "time": ts, "reactions": "{}"}, to=data['room'])

@socketio.on('delete_message')
def delete_msg(data):
    m = Message.query.get(data['id'])
    session_data = active_sessions.get(request.sid)
    if m and session_data and m.username == session_data['user']:
        room = m.room
        db.session.delete(m)
        db.session.commit()
        emit('message_deleted', {'id': data['id']}, to=room)

@socketio.on('send_reaction')
def handle_reaction(data):
    session_data = active_sessions.get(request.sid)
    if not session_data: return
    msg_id = data.get('msg_id')
    emoji = data.get('emoji')
    username = session_data['user']
    m = Message.query.get(msg_id)
    if m:
        try: rx = json.loads(m.reactions or "{}")
        except: rx = {}
        
        if emoji not in rx: rx[emoji] = []
        if username in rx[emoji]:
            rx[emoji].remove(username)
            if not rx[emoji]: del rx[emoji]
        else: rx[emoji].append(username)
        
        m.reactions = json.dumps(rx)
        db.session.commit()
        emit('update_reaction', {'msg_id': msg_id, 'reactions': rx}, to=m.room)

# تعديل أمر التشغيل النهائي ليتناسب مع متغيرات خوادم Render
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)