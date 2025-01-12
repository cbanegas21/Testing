from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import threading
import time

app = Flask(__name__)
socketio = SocketIO(app)

# ------------------------------------------------------------------------------------
# Variables globales
# ------------------------------------------------------------------------------------
timer_data = {
    "time_left": 0,
    "segment_duration": 0,
    "current_segment": "",
    "is_running": False,
    "blink_enabled": True,
    "duplicate_window_open": False,
}

blink_thread = None
blink_thread_stop_event = threading.Event()
start_time_reference = 0.0

# ------------------------------------------------------------------------------------
# HILO PRINCIPAL DEL TIMER
# ------------------------------------------------------------------------------------
def timer_thread():
    global start_time_reference

    while True:
        if timer_data["is_running"] and timer_data["time_left"] > 0:
            now = time.perf_counter()
            elapsed = now - start_time_reference

            if elapsed >= 1.0:
                seconds_passed = int(elapsed)
                timer_data["time_left"] = max(timer_data["time_left"] - seconds_passed, 0)
                start_time_reference = now
                emit_update_time()
            time.sleep(0.1)

        elif timer_data["time_left"] == 0 and timer_data["is_running"]:
            # Se acabó el tiempo
            timer_data["is_running"] = False

            # Solo parpadea en Discurso Público / Estudio de La Atalaya
            if timer_data["blink_enabled"] and timer_data["current_segment"] in [
                "Discurso Público",
                "Estudio de La Atalaya"
            ]:
                start_blinking()

        else:
            time.sleep(0.1)

# ------------------------------------------------------------------------------------
# LÓGICA DE PARPADEO (FONDO)
# ------------------------------------------------------------------------------------
def blinking_logic(stop_event):
    """
    Alterna True/False cada 0.5s y lo emite a los clientes vía 'update_blink'.
    """
    blink_on = False
    while not stop_event.is_set():
        blink_on = not blink_on
        socketio.emit('update_blink', {"blink": blink_on})
        time.sleep(0.5)

def start_blinking():
    global blink_thread, blink_thread_stop_event
    stop_blinking()  # detiene cualquier parpadeo anterior
    blink_thread_stop_event = threading.Event()
    blink_thread = threading.Thread(
        target=blinking_logic, args=(blink_thread_stop_event,), daemon=True
    )
    blink_thread.start()

def stop_blinking():
    global blink_thread, blink_thread_stop_event
    if blink_thread and blink_thread.is_alive():
        blink_thread_stop_event.set()
        blink_thread.join()
    blink_thread = None

# ------------------------------------------------------------------------------------
# Funciones de ayuda
# ------------------------------------------------------------------------------------
def emit_update_time():
    socketio.emit('update_time', {
        "time_left": timer_data["time_left"],
        "segment_duration": timer_data["segment_duration"],
        "current_segment": timer_data["current_segment"],
    })

# ------------------------------------------------------------------------------------
# RUTAS FLASK
# ------------------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/duplicate')
def duplicate():
    return render_template('duplicate.html')

@app.route('/start', methods=['POST'])
def start_timer():
    global start_time_reference
    stop_blinking()

    segment_index = int(request.json.get("segment_index", 0))
    segments = [
        ("Canción y Oración Inicial", 300),
        ("Discurso Público", 1800),
        ("Transición", 60),
        ("Estudio de La Atalaya", 3600),
        ("Canción y Oración Final", 300)
    ]

    name, duration = segments[segment_index]
    timer_data["current_segment"] = name
    timer_data["segment_duration"] = duration
    timer_data["time_left"] = duration
    timer_data["is_running"] = True
    start_time_reference = time.perf_counter()

    emit_update_time()
    return jsonify(success=True)

@app.route('/start_now', methods=['POST'])
def start_now():
    global start_time_reference
    stop_blinking()

    if timer_data["time_left"] > 0:
        timer_data["is_running"] = True
        start_time_reference = time.perf_counter()
        emit_update_time()

    return jsonify(success=True)

@app.route('/pause', methods=['POST'])
def pause_timer():
    timer_data["is_running"] = False
    return jsonify(success=True)

@app.route('/reset', methods=['POST'])
def reset_timer():
    stop_blinking()
    timer_data["is_running"] = False
    timer_data["time_left"] = 0
    timer_data["segment_duration"] = 0
    timer_data["current_segment"] = ""

    emit_update_time()
    return jsonify(success=True)

@app.route('/modify', methods=['POST'])
def modify_timer():
    global start_time_reference
    was_running = timer_data["is_running"]

    new_minutes = int(request.json.get("new_minutes", 0))
    new_seconds = int(request.json.get("new_seconds", 0))
    new_time = new_minutes * 60 + new_seconds

    timer_data["time_left"] = new_time

    if was_running:
        timer_data["is_running"] = True
        start_time_reference = time.perf_counter()

    stop_blinking()
    emit_update_time()
    return jsonify(success=True)

@app.route('/toggle_duplicate', methods=['POST'])
def toggle_duplicate():
    timer_data["duplicate_window_open"] = not timer_data["duplicate_window_open"]
    socketio.emit('toggle_duplicate', {"open": timer_data["duplicate_window_open"]})
    emit_update_time()
    return jsonify(success=True)

# ------------------------------------------------------------------------------------
# EVENTOS SOCKETIO
# ------------------------------------------------------------------------------------
@socketio.on('connect')
def on_connect():
    emit_update_time()

# ------------------------------------------------------------------------------------
# Lanzar la aplicación
# ------------------------------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=timer_thread, daemon=True).start()
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
