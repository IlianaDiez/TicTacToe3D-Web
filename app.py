"""
Tic Tac Toe 3D - Flask + SocketIO + Three.js
Sistema de salas privadas con código de acceso
Desplegable en WAN (Render, VPS, etc.)
"""

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import time
import random
import string
import os

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
salas = {}        # codigo_sala -> {jugadas, turno, terminado, jugadores: {sid: num}}
sid_a_sala = {}   # sid -> codigo_sala
last_ping = {}    # sid -> timestamp del último ping


def generar_codigo_sala():
    """Genera un código de sala de 6 caracteres alfanuméricos"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


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
    """Elimina salas donde todos los jugadores se desconectaron"""
    ahora = time.time()
    salas_muertas = []
    for sala_id, sala in salas.items():
        jugadores_vivos = 0
        for sid_jugador in sala['jugadores']:
            if ahora - last_ping.get(sid_jugador, 0) < 60:
                jugadores_vivos += 1
        if jugadores_vivos == 0:
            salas_muertas.append(sala_id)
    for sala_id in salas_muertas:
        if sala_id in salas:
            for sid in list(sid_a_sala.keys()):
                if sid_a_sala[sid] == sala_id:
                    del sid_a_sala[sid]
            del salas[sala_id]


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('connect')
def on_connect():
    sid = request.sid
    last_ping[sid] = time.time()


# ===================== SISTEMA DE SALAS =====================

@socketio.on('crear_sala')
def crear_sala():
    """Crea una nueva sala privada y devuelve el código"""
    sid = request.sid
    last_ping[sid] = time.time()

    limpiar_salas_muertas()

    # Si ya estaba en una sala, salir primero
    sala_vieja = sid_a_sala.pop(sid, None)
    if sala_vieja and sala_vieja in salas:
        leave_room(sala_vieja, sid=sid)
        if sid in salas[sala_vieja]['jugadores']:
            del salas[sala_vieja]['jugadores'][sid]
        if len(salas[sala_vieja]['jugadores']) == 1:
            emit('rival_desconectado', room=sala_vieja)
        if len(salas[sala_vieja]['jugadores']) == 0:
            del salas[sala_vieja]

    # Generar código único
    codigo = generar_codigo_sala()
    while codigo in salas:
        codigo = generar_codigo_sala()

    # Crear sala
    salas[codigo] = {
        'jugadas': tablero_vacio(),
        'turno': 0,
        'terminado': False,
        'jugadores': {sid: 0},
    }
    sid_a_sala[sid] = codigo

    join_room(codigo, sid=sid)
    emit('sala_creada', {'sala': codigo})


@socketio.on('unirse_sala')
def unirse_sala(datos):
    """Unirse a una sala existente con código"""
    sid = request.sid
    last_ping[sid] = time.time()
    codigo = datos.get('sala', '').upper().strip()

    if not codigo:
        emit('error_sala', {'motivo': 'Código de sala requerido'})
        return

    limpiar_salas_muertas()

    if codigo not in salas:
        emit('error_sala', {'motivo': 'Sala no encontrada'})
        return

    sala = salas[codigo]

    if len(sala['jugadores']) >= 2:
        emit('error_sala', {'motivo': 'La sala ya está llena'})
        return

    if sala['terminado']:
        emit('error_sala', {'motivo': 'La partida ya terminó'})
        return

    # Si ya estaba en otra sala, salir primero
    sala_vieja = sid_a_sala.pop(sid, None)
    if sala_vieja and sala_vieja in salas and sala_vieja != codigo:
        leave_room(sala_vieja, sid=sid)
        if sid in salas[sala_vieja]['jugadores']:
            del salas[sala_vieja]['jugadores'][sid]
        if len(salas[sala_vieja]['jugadores']) == 1:
            emit('rival_desconectado', room=sala_vieja)
        if len(salas[sala_vieja]['jugadores']) == 0:
            del salas[sala_vieja]

    # Unir al jugador
    sala['jugadores'][sid] = 1
    sid_a_sala[sid] = codigo
    join_room(codigo, sid=sid)

    emit('unido_a_sala', {'sala': codigo, 'listo': True})

    # Notificar a ambos jugadores que inicia
    creador_sid = None
    for s, num in sala['jugadores'].items():
        if num == 0:
            creador_sid = s
            break

    if creador_sid:
        emit('inicio', {'jugador': 0, 'sala': codigo}, room=creador_sid)

    emit('inicio', {'jugador': 1, 'sala': codigo}, room=sid)


@socketio.on('salir_sala')
def salir_sala(datos):
    """Salir de una sala (voluntariamente)"""
    sid = request.sid
    codigo = datos.get('sala', '')

    if sid in sid_a_sala:
        del sid_a_sala[sid]

    if codigo and codigo in salas:
        leave_room(codigo, sid=sid)
        if sid in salas[codigo]['jugadores']:
            del salas[codigo]['jugadores'][sid]
        if len(salas[codigo]['jugadores']) >= 1:
            emit('rival_desconectado', room=codigo)
        if len(salas[codigo]['jugadores']) == 0:
            del salas[codigo]


# ===================== JUEGO =====================

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
    sid = request.sid

    sala_id = sid_a_sala.pop(sid, None)
    if sala_id and sala_id in salas:
        if sid in salas[sala_id]['jugadores']:
            del salas[sala_id]['jugadores'][sid]
        emit('rival_desconectado', room=sala_id)
        if len(salas[sala_id]['jugadores']) == 0:
            def borrar_sala():
                if sala_id in salas and len(salas[sala_id]['jugadores']) == 0:
                    del salas[sala_id]
            import threading
            threading.Timer(30.0, borrar_sala).start()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
