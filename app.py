import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
from datetime import datetime, timedelta
import os, json, threading, time

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///messenger.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Ключ шифрования
ENCRYPT_KEY = os.environ.get('ENCRYPT_KEY', Fernet.generate_key().decode())
fernet = Fernet(ENCRYPT_KEY.encode() if isinstance(ENCRYPT_KEY, str) else ENCRYPT_KEY)

# --- Модели базы данных ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    avatar_color = db.Column(db.String(7), default='#6c63ff')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_online = db.Column(db.Boolean, default=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.Text, nullable=False)  # зашифровано
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    delete_at = db.Column(db.DateTime, nullable=True)  # автоудаление
    is_deleted = db.Column(db.Boolean, default=False)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    room_id = db.Column(db.String(100), unique=True, nullable=False)
    is_group = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class RoomMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

# --- Шифрование ---

def encrypt(text):
    return fernet.encrypt(text.encode()).decode()

def decrypt(text):
    try:
        return fernet.decrypt(text.encode()).decode()
    except:
        return "[сообщение недоступно]"

# --- Автоудаление сообщений ---

def auto_delete_messages():
    while True:
        with app.app_context():
            now = datetime.utcnow()
            expired = Message.query.filter(
                Message.delete_at != None,
                Message.delete_at <= now,
                Message.is_deleted == False
            ).all()
            for msg in expired:
                msg.is_deleted = True
                msg.content = encrypt("[сообщение удалено]")
            if expired:
                db.session.commit()
        time.sleep(10)

# --- Маршруты ---

@app.route('/')
def index():
    if 'user_id' not in session:
        return render_template('login.html')
    return render_template('chat.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Заполни все поля'}), 400
    if len(username) < 3:
        return jsonify({'error': 'Имя минимум 3 символа'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Пароль минимум 6 символов'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Имя уже занято'}), 400

    colors = ['#6c63ff', '#ff6584', '#43aa8b', '#f8961e', '#277da1', '#e63946']
    import random
    color = random.choice(colors)

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        avatar_color=color
    )
    db.session.add(user)
    db.session.commit()
    session['user_id'] = user.id
    session['username'] = user.username
    return jsonify({'success': True})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data.get('username')).first()
    if not user or not check_password_hash(user.password_hash, data.get('password', '')):
        return jsonify({'error': 'Неверное имя или пароль'}), 401
    session['user_id'] = user.id
    session['username'] = user.username
    return jsonify({'success': True})

@app.route('/api/logout', methods=['POST'])
def logout():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user.is_online = False
            db.session.commit()
    session.clear()
    return jsonify({'success': True})

@app.route('/api/users')
def get_users():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401
    users = User.query.filter(User.id != session['user_id']).all()
    return jsonify([{
        'id': u.id,
        'username': u.username,
        'color': u.avatar_color,
        'online': u.is_online
    } for u in users])

@app.route('/api/rooms')
def get_rooms():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401
    members = RoomMember.query.filter_by(user_id=session['user_id']).all()
    room_ids = [m.room_id for m in members]
    rooms = Room.query.filter(Room.room_id.in_(room_ids)).all() if room_ids else []
    return jsonify([{
        'room_id': r.room_id,
        'name': r.name,
        'is_group': r.is_group
    } for r in rooms])

@app.route('/api/start_chat', methods=['POST'])
def start_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401
    data = request.json
    target_id = data.get('user_id')
    target = User.query.get(target_id)
    if not target:
        return jsonify({'error': 'Пользователь не найден'}), 404

    ids = sorted([session['user_id'], target_id])
    room_id = f"dm_{ids[0]}_{ids[1]}"

    room = Room.query.filter_by(room_id=room_id).first()
    if not room:
        room = Room(name=target.username, room_id=room_id, is_group=False, created_by=session['user_id'])
        db.session.add(room)
        db.session.add(RoomMember(room_id=room_id, user_id=session['user_id']))
        db.session.add(RoomMember(room_id=room_id, user_id=target_id))
        db.session.commit()

    return jsonify({'room_id': room_id, 'name': target.username})

@app.route('/api/messages/<room_id>')
def get_messages(room_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401
    messages = Message.query.filter_by(room=room_id, is_deleted=False).order_by(Message.created_at).limit(100).all()
    result = []
    for m in messages:
        user = User.query.get(m.sender_id)
        result.append({
            'id': m.id,
            'text': decrypt(m.content),
            'sender': user.username if user else 'Unknown',
            'sender_id': m.sender_id,
            'color': user.avatar_color if user else '#999',
            'time': m.created_at.strftime('%H:%M'),
            'delete_at': m.delete_at.isoformat() if m.delete_at else None
        })
    return jsonify(result)

# --- WebSocket события ---

@socketio.on('connect')
def on_connect():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user.is_online = True
            db.session.commit()

@socketio.on('disconnect')
def on_disconnect():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user.is_online = False
            db.session.commit()

@socketio.on('join')
def on_join(data):
    room = data.get('room')
    join_room(room)

@socketio.on('leave')
def on_leave(data):
    room = data.get('room')
    leave_room(room)

@socketio.on('message')
def on_message(data):
    if 'user_id' not in session:
        return
    room_id = data.get('room')
    text = data.get('text', '').strip()
    delete_after = data.get('delete_after')  # минуты, None = не удалять

    if not text or not room_id:
        return

    delete_at = None
    if delete_after:
        delete_at = datetime.utcnow() + timedelta(minutes=int(delete_after))

    msg = Message(
        room=room_id,
        sender_id=session['user_id'],
        content=encrypt(text),
        delete_at=delete_at
    )
    db.session.add(msg)
    db.session.commit()

    user = User.query.get(session['user_id'])
    emit('message', {
        'id': msg.id,
        'text': text,
        'sender': user.username,
        'sender_id': user.id,
        'color': user.avatar_color,
        'time': msg.created_at.strftime('%H:%M'),
        'delete_at': delete_at.isoformat() if delete_at else None
    }, room=room_id)

@socketio.on('get_my_id')
def on_get_my_id():
    if 'user_id' in session:
        emit('my_id', {'id': session['user_id']})

@socketio.on('delete_message')
def on_delete(data):
    if 'user_id' not in session:
        return
    msg = Message.query.get(data.get('message_id'))
    if msg and msg.sender_id == session['user_id']:
        msg.is_deleted = True
        msg.content = encrypt("[сообщение удалено]")
        db.session.commit()
        emit('message_deleted', {'id': msg.id}, room=msg.room)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    t = threading.Thread(target=auto_delete_messages, daemon=True)
    t.start()
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
