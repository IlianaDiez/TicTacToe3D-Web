"""
Tic Tac Toe 3D - Flask + SocketIO + Three.js
Servidor WebSocket para multiplayer en tiempo real
"""

from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tictactoe3d-secreto-v2'

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="gevent",
    ping_timeout=60,
    ping_interval=25
)

LADO = 4

DIRECCIONES = [
    (1, 0, 0), (0, 1, 0), (0, 0, 1),
    (1, 1, 0), (1, -1, 0),
    (0, 1, 1), (0, 1, -1),
    (1, 0, 1), (1, 0, -1),
    (1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1),
]

# ---------------- Estado del servidor ----------------
esperando = None
salas = {}
sid_a_sala = {}


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
            return celdas
    return None


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('buscar_partida')
def buscar_partida():
    global esperando
    from flask import request
    sid = request.sid

    if esperando is None:
        esperando = sid
        emit('esperando')
        return

    if esperando == sid:
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


@socketio.on('jugar')
def jugar(datos):
    from flask import request
    sid = request.sid
    i = datos.get('i')

    sala_id = sid_a_sala.get(sid)
    if sala_id is None or sala_id not in salas:
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

    ganadora = hay_ganador(sala['jugadas'], x, y, z)
    resultado = {
        'i': i,
        'jugador': quien,
        'ganadora': [list(c) for c in ganadora] if ganadora else None,
    }

    if ganadora:
        sala['terminado'] = True
    else:
        sala['turno'] = 1 - quien

    emit('jugada', resultado, room=sala_id)


@socketio.on('reiniciar')
def reiniciar():
    from flask import request
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
    from flask import request
    sid = request.sid

    if esperando == sid:
        esperando = None

    sala_id = sid_a_sala.pop(sid, None)
    if sala_id and sala_id in salas:
        emit('rival_desconectado', room=sala_id)
        del salas[sala_id]


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
