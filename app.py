from flask import Flask, session, jsonify, request
from flask_cors import CORS
import random, time, uuid, sqlite3, json

app = Flask(__name__)
app.secret_key = 'troque-esta-chave-por-uma-sua'
CORS(app, supports_credentials=True)
DB = 'db_idle_pragas.sqlite'

# Dados de pragas e configurações
PRAGAS = {
    'rato': 1, 'barata': 2, 'mosquito': 3, 'pombo': 5,
    'formiga': 1.5, 'cupim': 2.2, 'aranha': 1.8,
    'pulga': 1.2, 'carrapato': 1.3, 'morcego': 2.5
}
RAR_CHANCES = [
    ('mitologica', 0.1), ('divina', 0.4), ('exotica', 1),
    ('lendaria', 3), ('epica', 10), ('superior', 20),
    ('media', 30), ('comum', 35.5)
]
RAR_MULT = {
    'comum': 1, 'media': 1.3, 'superior': 1.7, 'epica': 2.5,
    'lendaria': 4, 'exotica': 6, 'divina': 10, 'mitologica': 20
}

# --- IMPORTAR AQUI O SEU DITCIONÁRIO COMPLETO DE PRAGAS_INFO ---
PRAGAS_INFO = {
    # 'rato': { ... }, 'barata': { ... }, etc.
}

def init_db():
    with sqlite3.connect(DB) as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS jogadores(
                id TEXT PRIMARY KEY,
                nome TEXT UNIQUE,
                moedas INTEGER,
                ultimo REAL,
                local TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS colecao(
                pid TEXT,
                tipo TEXT,
                rar TEXT,
                qtd INTEGER,
                PRIMARY KEY(pid,tipo,rar)
            )
        ''')

init_db()

def choose_rar():
    r = random.uniform(0, 100)
    s = 0
    for rar, ch in RAR_CHANCES:
        s += ch
        if r <= s:
            return rar
    return 'comum'

def calc_income(pid):
    tot = 0
    with sqlite3.connect(DB) as c:
        for tipo, rar, qtd in c.execute(
            "SELECT tipo, rar, qtd FROM colecao WHERE pid=?", (pid,)
        ):
            tot += PRAGAS[tipo] * RAR_MULT[rar] * qtd
    return tot

def mock_loc(ip):
    # Em produção, use uma API de geolocalização real
    return json.dumps({'ip': ip, 'cidade': 'São Paulo', 'pais': 'Brasil'})

# ------------------ ROTAS ------------------

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'service': 'Idle Pragas API',
        'status': 'running',
        'endpoints': [
            '/login', '/status', '/coletar',
            '/comprar', '/evoluir', '/ranking', '/pragas_info'
        ]
    })

@app.route('/login', methods=['POST'])
def login():
    nome = request.json.get('nome', '').strip().lower()
    if len(nome) < 3:
        return jsonify({'erro': 'Nome inválido'}), 400

    ip = request.remote_addr
    loc = mock_loc(ip)

    with sqlite3.connect(DB) as c:
        row = c.execute(
            "SELECT id FROM jogadores WHERE nome=?", (nome,)
        ).fetchone()
        if row:
            pid = row[0]
            c.execute(
                "UPDATE jogadores SET local=? WHERE id=?", (loc, pid)
            )
        else:
            pid = str(uuid.uuid4())
            c.execute(
                "INSERT INTO jogadores VALUES(?,?,?,?,?)",
                (pid, nome, 0, time.time(), loc)
            )

    session['pid'] = pid
    return jsonify({'player_id': pid})

@app.route('/status')
def status():
    pid = session.get('pid')
    if not pid:
        return jsonify({'erro': 'nologin'}), 403

    with sqlite3.connect(DB) as c:
        row = c.execute(
            "SELECT moedas, ultimo FROM jogadores WHERE id=?", (pid,)
        ).fetchone()
        if not row:
            return jsonify({'erro': 'no'}), 404

        moedas, ultimo = row
        now = time.time()
        ganho = int(calc_income(pid) * (now - ultimo))
        moedas += ganho
        c.execute(
            "UPDATE jogadores SET moedas=?, ultimo=? WHERE id=?",
            (moedas, now, pid)
        )

        colecao = [
            {'tipo': t, 'raridade': r, 'qtd': q}
            for t, r, q in c.execute(
                "SELECT tipo, rar, qtd FROM colecao WHERE pid=?", (pid,)
            )
        ]

    # Atenção ao campo: aqui o frontend espera "income_por_segundo"
    return jsonify({
        'moedas': moedas,
        'ganho': ganho,
        'income_por_segundo': calc_income(pid),
        'colecao': colecao
    })

@app.route('/coletar', methods=['POST'])
def coletar():
    pid = session.get('pid')
    if not pid:
        return jsonify({'erro': 'nologin'}), 403
    # Reaproveita a lógica de status para coletar
    return status()

@app.route('/comprar', methods=['POST'])
def comprar():
    pid = session.get('pid')
    if not pid:
        return jsonify({'erro': 'nologin'}), 403

    custo = 100
    with sqlite3.connect(DB) as c:
        moedas = c.execute(
            "SELECT moedas FROM jogadores WHERE id=?", (pid,)
        ).fetchone()[0]
        if moedas < custo:
            return jsonify({'erro': 'sem moedas'}), 400

        moedas -= custo
        rar = choose_rar()
        tipo = random.choice(list(PRAGAS))

        if c.execute(
            "SELECT qtd FROM colecao WHERE pid=? AND tipo=? AND rar=?",
            (pid, tipo, rar)
        ).fetchone():
            c.execute(
                "UPDATE colecao SET qtd=qtd+1 WHERE pid=? AND tipo=? AND rar=?",
                (pid, tipo, rar)
            )
        else:
            c.execute(
                "INSERT INTO colecao VALUES(?,?,?,1)",
                (pid, tipo, rar)
            )

        c.execute(
            "UPDATE jogadores SET moedas=? WHERE id=?",
            (moedas, pid)
        )

    return jsonify({'moedas': moedas, 'novo': {'tipo': tipo, 'raridade': rar}})

@app.route('/evoluir', methods=['POST'])
def evoluir():
    pid = session.get('pid')
    if not pid:
        return jsonify({'erro': 'nologin'}), 403

    data = request.json
    tipo = data.get('tipo')
    rar = data.get('raridade')

    with sqlite3.connect(DB) as c:
        q = c.execute(
            "SELECT qtd FROM colecao WHERE pid=? AND tipo=? AND rar=?",
            (pid, tipo, rar)
        ).fetchone()
        if not q or q[0] < 5:
            return jsonify({'erro': 'insuf'}), 400

        c.execute(
            "UPDATE colecao SET qtd=qtd-5 WHERE pid=? AND tipo=? AND rar=?",
            (pid, tipo, rar)
        )
        c.execute(
            "DELETE FROM colecao WHERE pid=? AND tipo=? AND rar=? AND qtd<=0",
            (pid, tipo, rar)
        )

        nrar = choose_rar()
        if c.execute(
            "SELECT qtd FROM colecao WHERE pid=? AND tipo=? AND rar=?",
            (pid, tipo, nrar)
        ).fetchone():
            c.execute(
                "UPDATE colecao SET qtd=qtd+1 WHERE pid=? AND tipo=? AND rar=?",
                (pid, tipo, nrar)
            )
        else:
            c.execute(
                "INSERT INTO colecao VALUES(?,?,?,1)",
                (pid, tipo, nrar)
            )

    return jsonify({'novo': {'tipo': tipo, 'raridade': nrar}})

@app.route('/ranking')
def ranking():
    with sqlite3.connect(DB) as c:
        lista = [
            {'nome': n, 'moedas': m, 'loc': json.loads(l)}
            for n, m, l in c.execute(
                "SELECT nome, moedas, local FROM jogadores ORDER BY moedas DESC LIMIT 10"
            )
        ]
    return jsonify({'lista': lista})

@app.route('/pragas_info')
def pragas_info():
    return jsonify(PRAGAS_INFO)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)