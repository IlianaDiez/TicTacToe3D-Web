"""
Tic Tac Toe 3D - Flask + SocketIO + Three.js
Sistema de emparejamiento robusto con re-conexión automática
"""

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tictactoe3d-secreto-v2'

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="gevent",
    ping_timeout=10,
    ping_interval=5
)

LADO = 4

DIRECCIONES = [
    (1, 0, 0), (0, 1, 0), (0, 0, 1),
    (1, 1, 0), (1, -1, 0),
    (0, 1, 1), (0, 1, -1),
    (1, 0, 1), (1, 0, -1),
    (1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1),
]

NOMBRES_DIRECCION = {
    (1, 0, 0): "Horizontal (eje X)",
    (0, 1, 0): "Vertical (eje Y)",
    (0, 0, 1): "Profundidad (eje Z)",
    (1, 1, 0): "Diagonal frontal",
    (1, -1, 0): "Diagonal frontal inversa",
    (0, 1, 1): "Diagonal vertical",
    (0, 1, -1): "Diagonal vertical inversa",
    (1, 0, 1): "Diagonal horizontal",
    (1, 0, -1): "Diagonal horizontal inversa",
    (1, 1, 1): "Diagonal cruzada principal",
    (1, 1, -1): "Diagonal cruzada",
    (1, -1, 1): "Diagonal cruzada",
    (1, -1, -1): "Diagonal cruzada inversa",
}

# ---------------- Estado del servidor ----------------
esperando = None
salas = {}
sid_a_sala = {}
last_ping = {}  # sid -> timestamp del último ping


def tablero_vacio():
    return [[[0]*LADO for _ in range(LADO)] for _ in range(LADO)]


def inicio_de_linea(punto, direccion):
    ini = []
    for p, d in zip(punto, direccion):
        if d == 1:
            ini.append(0)
        elif d == -1:
            ini.append(LADO - 1)
        else:
            ini.append(p)
    return tuple(ini)


def hay_ganador(jugadas, x, y, z):
    for d in DIRECCIONES:
        ix, iy, iz = inicio_de_linea((x, y, z), d)
        celdas, suma = [], 0
        for k in range(LADO):
            cx, cy, cz = ix + k*d[0], iy + k*d[1], iz + k*d[2]
            celdas.append((cx, cy, cz))
            suma += jugadas[cz][cy][cx]
        if abs(suma) == LADO:
            tipo = NOMBRES_DIRECCION.get(d, "Línea desconocida")
            return celdas, tipo
    return None, None


def limpiar_salas_muertas():
    """Elimina salas donde un jugador se desconectó"""
    global esperando
    ahora = time.time()
    # Limpiar jugador esperando si lleva más de 30 segundos
    if esperando and ahora - last_ping.get(esperando, 0) > 30:
        esperando = None
    # Limpiar salas con jugadores desconectados
    salas_muertas = []
    for sala_id, sala in salas.items():
        jugadores_vivos = 0
        for sid_jugador in sala['jugadores']:
            if ahora - last_ping.get(sid_jugador, 0) < 30:
                jugadores_vivos += 1
        if jugadores_vivos < 2 and not sala['terminado']:
            salas_muertas.append(sala_id)
    for sala_id in salas_muertas:
        if sala_id in salas:
            del salas[sala_id]


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('connect')
def on_connect():
    sid = request.sid
    last_ping[sid] = time.time()


@socketio.on('buscar_partida')
def buscar_partida():
    global esperando
    sid = request.sid
    last_ping[sid] = time.time()

    # Limpiar salas viejas antes de emparejar
    limpiar_salas_muertas()

    # Si ya estaba en una sala, salir de ella primero
    sala_vieja = sid_a_sala.pop(sid, None)
    if sala_vieja and sala_vieja in salas:
        leave_room(sala_vieja, sid=sid)
        emit('rival_desconectado', room=sala_vieja)
        del salas[sala_vieja]

    if esperando is None:
        esperando = sid
        emit('esperando')
        return

    if esperando == sid:
        return

    # Verificar que el jugador esperando siga vivo
    if time.time() - last_ping.get(esperando, 0) > 30:
        esperando = sid
        emit('esperando')
        return

    pareja_sid = esperando
    esperando = None

    sala_id = str(uuid.uuid4())[:8].upper()
    salas[sala_id] = {
        'jugadas': tablero_vacio(),
        'turno': 0,
        'terminado': False,
        'jugadores': {pareja_sid: 0, sid: 1},
    }
    sid_a_sala[pareja_sid] = sala_id
    sid_a_sala[sid] = sala_id

    join_room(sala_id, sid=pareja_sid)
    join_room(sala_id, sid=sid)

    emit('inicio', {'jugador': 0, 'sala': sala_id}, room=pareja_sid)
    emit('inicio', {'jugador': 1, 'sala': sala_id}, room=sid)


@socketio.on('ping_vivo')
def ping_vivo():
    sid = request.sid
    last_ping[sid] = time.time()


@socketio.on('jugar')
def jugar(datos):
    sid = request.sid
    last_ping[sid] = time.time()
    i = datos.get('i')

    sala_id = sid_a_sala.get(sid)
    if sala_id is None or sala_id not in salas:
        emit('error', {'motivo': 'No estás en una sala activa'})
        return
    sala = salas[sala_id]

    quien = sala['jugadores'].get(sid)
    if quien is None or sala['terminado']:
        return
    if sala['turno'] != quien:
        emit('jugada_invalida', {'motivo': 'No es tu turno'})
        return

    z, y, x = i // 16, (i % 16) // 4, i % 4
    if sala['jugadas'][z][y][x] != 0:
        emit('jugada_invalida', {'motivo': 'Casilla ocupada'})
        return

    valor = -1 if quien == 0 else 1
    sala['jugadas'][z][y][x] = valor

    ganadora, tipo_ganador = hay_ganador(sala['jugadas'], x, y, z)
    resultado = {
        'i': i,
        'jugador': quien,
        'ganadora': [list(c) for c in ganadora] if ganadora else None,
        'tipo_ganador': tipo_ganador,
    }

    if ganadora:
        sala['terminado'] = True
    else:
        sala['turno'] = 1 - quien

    emit('jugada', resultado, room=sala_id)


@socketio.on('reiniciar')
def reiniciar():
    sid = request.sid
    sala_id = sid_a_sala.get(sid)
    if sala_id is None or sala_id not in salas:
        return
    sala = salas[sala_id]
    sala['jugadas'] = tablero_vacio()
    sala['turno'] = 0
    sala['terminado'] = False
    emit('reiniciada', room=sala_id)


@socketio.on('disconnect')
def al_desconectar():
    global esperando
    sid = request.sid

    if esperando == sid:
        esperando = None

    sala_id = sid_a_sala.pop(sid, None)
    if sala_id and sala_id in salas:
        emit('rival_desconectado', room=sala_id)
        # No borramos la sala inmediatamente, damos 10 segundos por si reconecta
        def borrar_sala():
            if sala_id in salas:
                # Verificar si alguien sigue en la sala
                for s in salas[sala_id]['jugadores']:
                    if s != sid and time.time() - last_ping.get(s, 0) < 30:
                        return
                del salas[sala_id]
        # Usar un timer simple en vez de threading
        import threading
        threading.Timer(10.0, borrar_sala).start()


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
