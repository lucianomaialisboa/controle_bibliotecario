"""Controle de empréstimos da biblioteca escolar.

Aplicação mínima: Flask + SQLite, um único arquivo de banco (biblioteca.db).
"""
import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("BIBLIOTECA_DB", os.path.join(BASE_DIR, "biblioteca.db"))
PRAZO_PADRAO_DIAS = int(os.environ.get("BIBLIOTECA_PRAZO_DIAS", "7"))

app = Flask(__name__)
app.secret_key = os.environ.get("BIBLIOTECA_SECRET", "troque-esta-chave")

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nome TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    admin INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_por INTEGER REFERENCES usuarios(id),
    criado_em TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS alunos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    turma TEXT,
    matricula TEXT,
    telefone TEXT,
    criado_por INTEGER REFERENCES usuarios(id),
    criado_em TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS livros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    autor TEXT,
    codigo TEXT,
    exemplares INTEGER NOT NULL DEFAULT 1,
    criado_por INTEGER REFERENCES usuarios(id),
    criado_em TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS emprestimos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aluno_id INTEGER NOT NULL REFERENCES alunos(id),
    livro_id INTEGER NOT NULL REFERENCES livros(id),
    data_emprestimo TEXT NOT NULL,
    data_prevista TEXT NOT NULL,
    data_devolucao TEXT,
    observacao TEXT,
    criado_por INTEGER REFERENCES usuarios(id),
    devolvido_por INTEGER REFERENCES usuarios(id)
);
CREATE INDEX IF NOT EXISTS idx_emp_aberto ON emprestimos(data_devolucao);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    # Migração simples para bancos criados antes do controle de usuários
    for tabela, coluna in [("alunos", "criado_por"), ("livros", "criado_por"),
                           ("emprestimos", "criado_por"), ("emprestimos", "devolvido_por")]:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({tabela})")]
        if coluna not in cols:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} INTEGER REFERENCES usuarios(id)")
    con.commit()
    con.close()


def hoje():
    return date.today().isoformat()


def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@app.template_filter("br")
def data_br(valor):
    """Converte AAAA-MM-DD [HH:MM:SS] para DD/MM/AAAA [HH:MM]."""
    if not valor:
        return ""
    try:
        dia, _, hora = valor.partition(" ")
        a, m, d = dia.split("-")
        return f"{d}/{m}/{a}" + (f" {hora[:5]}" if hora else "")
    except ValueError:
        return valor


# ---------------------------------------------------------------- usuários e login
@app.before_request
def carregar_usuario():
    g.user = None
    uid = session.get("uid")
    if uid:
        g.user = get_db().execute(
            "SELECT * FROM usuarios WHERE id = ? AND ativo = 1", (uid,)
        ).fetchone()
        if g.user is None:
            session.clear()
    if request.endpoint in ("login", "primeiro_acesso", "static"):
        return None
    if g.user is None:
        tem_usuario = get_db().execute("SELECT 1 FROM usuarios LIMIT 1").fetchone()
        return redirect(url_for("login" if tem_usuario else "primeiro_acesso"))
    return None


def somente_admin(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not g.user or not g.user["admin"]:
            abort(403)
        return view(*args, **kwargs)
    return wrapper


@app.route("/primeiro-acesso", methods=["GET", "POST"])
def primeiro_acesso():
    db = get_db()
    if db.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
        return redirect(url_for("login"))
    if request.method == "POST":
        erro = validar_usuario(request.form)
        if erro:
            flash(erro, "erro")
        else:
            cur = db.execute(
                "INSERT INTO usuarios (login, nome, senha_hash, admin) VALUES (?, ?, ?, 1)",
                (request.form["login"].strip(), request.form["nome"].strip(),
                 generate_password_hash(request.form["senha"])),
            )
            db.commit()
            session.clear()
            session["uid"] = cur.lastrowid
            flash("Administrador criado. Bem-vindo!", "ok")
            return redirect(url_for("index"))
    return render_template("primeiro_acesso.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = get_db().execute(
            "SELECT * FROM usuarios WHERE login = ? AND ativo = 1",
            (request.form.get("login", "").strip(),),
        ).fetchone()
        if u and check_password_hash(u["senha_hash"], request.form.get("senha", "")):
            session.clear()
            session["uid"] = u["id"]
            return redirect(url_for("index"))
        flash("Usuário ou senha inválidos.", "erro")
    return render_template("login.html")


@app.route("/sair")
def sair():
    session.clear()
    return redirect(url_for("login"))


def validar_usuario(f, exigir_senha=True):
    if not f.get("login", "").strip() or not f.get("nome", "").strip():
        return "Informe login e nome."
    if exigir_senha and len(f.get("senha", "")) < 4:
        return "A senha precisa ter pelo menos 4 caracteres."
    return None


@app.route("/usuarios", methods=["GET", "POST"])
@somente_admin
def usuarios():
    db = get_db()
    if request.method == "POST":
        erro = validar_usuario(request.form)
        if not erro and db.execute("SELECT 1 FROM usuarios WHERE login = ?",
                                   (request.form["login"].strip(),)).fetchone():
            erro = "Já existe um usuário com esse login."
        if erro:
            flash(erro, "erro")
        else:
            db.execute(
                "INSERT INTO usuarios (login, nome, senha_hash, admin, criado_por) VALUES (?, ?, ?, ?, ?)",
                (request.form["login"].strip(), request.form["nome"].strip(),
                 generate_password_hash(request.form["senha"]),
                 1 if request.form.get("admin") else 0, g.user["id"]),
            )
            db.commit()
            flash("Usuário criado.", "ok")
        return redirect(url_for("usuarios"))
    rows = db.execute(
        """SELECT u.*, c.nome AS criador FROM usuarios u
           LEFT JOIN usuarios c ON c.id = u.criado_por ORDER BY u.nome"""
    ).fetchall()
    return render_template("usuarios.html", usuarios=rows)


@app.post("/usuarios/<int:uid>/ativo")
@somente_admin
def alternar_usuario(uid):
    if uid == g.user["id"]:
        flash("Você não pode desativar o seu próprio usuário.", "erro")
    else:
        db = get_db()
        db.execute("UPDATE usuarios SET ativo = 1 - ativo WHERE id = ?", (uid,))
        db.commit()
        flash("Situação do usuário alterada.", "ok")
    return redirect(url_for("usuarios"))


@app.post("/usuarios/<int:uid>/senha")
@somente_admin
def redefinir_senha(uid):
    senha = request.form.get("senha", "")
    if len(senha) < 4:
        flash("A senha precisa ter pelo menos 4 caracteres.", "erro")
    else:
        db = get_db()
        db.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (generate_password_hash(senha), uid))
        db.commit()
        flash("Senha redefinida.", "ok")
    return redirect(url_for("usuarios"))


@app.route("/minha-senha", methods=["GET", "POST"])
def minha_senha():
    if request.method == "POST":
        if not check_password_hash(g.user["senha_hash"], request.form.get("atual", "")):
            flash("Senha atual incorreta.", "erro")
        elif len(request.form.get("nova", "")) < 4:
            flash("A nova senha precisa ter pelo menos 4 caracteres.", "erro")
        else:
            db = get_db()
            db.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?",
                       (generate_password_hash(request.form["nova"]), g.user["id"]))
            db.commit()
            flash("Senha alterada.", "ok")
            return redirect(url_for("index"))
    return render_template("minha_senha.html")


LIVROS_SQL = """
SELECT l.*, u.nome AS cadastrado_por,
       l.exemplares - (SELECT COUNT(*) FROM emprestimos e
                       WHERE e.livro_id = l.id AND e.data_devolucao IS NULL) AS disponiveis
FROM livros l
LEFT JOIN usuarios u ON u.id = l.criado_por
"""

EMPRESTIMOS_SQL = """
SELECT e.*, a.nome AS aluno_nome, a.turma AS aluno_turma,
       l.titulo AS livro_titulo, l.codigo AS livro_codigo,
       uc.nome AS emprestado_por, ud.nome AS recebido_por
FROM emprestimos e
JOIN alunos a ON a.id = e.aluno_id
JOIN livros l ON l.id = e.livro_id
LEFT JOIN usuarios uc ON uc.id = e.criado_por
LEFT JOIN usuarios ud ON ud.id = e.devolvido_por
"""


# ---------------------------------------------------------------- empréstimo
@app.route("/")
def index():
    db = get_db()
    alunos = db.execute("SELECT * FROM alunos ORDER BY nome").fetchall()
    livros = db.execute(LIVROS_SQL + " ORDER BY titulo").fetchall()
    abertos = db.execute(
        EMPRESTIMOS_SQL + " WHERE e.data_devolucao IS NULL ORDER BY e.data_prevista"
    ).fetchall()
    prevista = (date.today() + timedelta(days=PRAZO_PADRAO_DIAS)).isoformat()
    alunos_json = [
        {
            "id": a["id"],
            "texto": a["nome"] + (f" ({a['turma']})" if a["turma"] else ""),
            "extra": f"matrícula {a['matricula']}" if a["matricula"] else "",
            "busca": " ".join(filter(None, [a["nome"], a["turma"], a["matricula"]])),
        }
        for a in alunos
    ]
    livros_json = [
        {
            "id": l["id"],
            "texto": l["titulo"] + (f" – {l['autor']}" if l["autor"] else ""),
            "extra": (f"[{l['codigo']}] " if l["codigo"] else "")
                     + (f"{l['disponiveis']} de {l['exemplares']} disponíveis" if l["disponiveis"] > 0
                        else "nenhum exemplar disponível"),
            "indisponivel": l["disponiveis"] <= 0,
            "busca": " ".join(filter(None, [l["titulo"], l["autor"], l["codigo"]])),
        }
        for l in livros
    ]
    return render_template(
        "index.html", alunos_json=alunos_json, livros_json=livros_json, abertos=abertos,
        prevista=prevista, hoje=hoje(),
    )


@app.post("/emprestar")
def emprestar():
    db = get_db()
    f = request.form

    # Aluno: existente ou novo
    if f.get("aluno_id") == "novo":
        nome = f.get("aluno_nome", "").strip()
        if not nome:
            flash("Informe o nome do novo aluno.", "erro")
            return redirect(url_for("index"))
        cur = db.execute(
            "INSERT INTO alunos (nome, turma, matricula, criado_por) VALUES (?, ?, ?, ?)",
            (nome, f.get("aluno_turma", "").strip(), f.get("aluno_matricula", "").strip(), g.user["id"]),
        )
        aluno_id = cur.lastrowid
    else:
        aluno_id = f.get("aluno_id", type=int)
        if not aluno_id:
            flash("Escolha um aluno ou cadastre um novo.", "erro")
            return redirect(url_for("index"))

    # Livro: existente ou novo
    if f.get("livro_id") == "novo":
        titulo = f.get("livro_titulo", "").strip()
        if not titulo:
            flash("Informe o título do novo livro.", "erro")
            return redirect(url_for("index"))
        exemplares = max(1, f.get("livro_exemplares", type=int) or 1)
        cur = db.execute(
            "INSERT INTO livros (titulo, autor, codigo, exemplares, criado_por) VALUES (?, ?, ?, ?, ?)",
            (titulo, f.get("livro_autor", "").strip(), f.get("livro_codigo", "").strip(), exemplares,
             g.user["id"]),
        )
        livro_id = cur.lastrowid
    else:
        livro_id = f.get("livro_id", type=int)
        if not livro_id:
            flash("Escolha um livro ou cadastre um novo.", "erro")
            return redirect(url_for("index"))

    livro = db.execute(LIVROS_SQL + " WHERE l.id = ?", (livro_id,)).fetchone()
    if livro is None or livro["disponiveis"] <= 0:
        db.rollback()
        flash("Não há exemplar disponível desse livro.", "erro")
        return redirect(url_for("index"))

    prevista = f.get("data_prevista") or (date.today() + timedelta(days=PRAZO_PADRAO_DIAS)).isoformat()
    db.execute(
        "INSERT INTO emprestimos (aluno_id, livro_id, data_emprestimo, data_prevista, observacao, criado_por)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (aluno_id, livro_id, agora(), prevista, f.get("observacao", "").strip(), g.user["id"]),
    )
    db.commit()
    flash(f"Empréstimo registrado: “{livro['titulo']}”.", "ok")
    return redirect(url_for("index"))


@app.post("/devolver/<int:emp_id>")
def devolver(emp_id):
    db = get_db()
    db.execute(
        "UPDATE emprestimos SET data_devolucao = ?, devolvido_por = ? WHERE id = ? AND data_devolucao IS NULL",
        (agora(), g.user["id"], emp_id),
    )
    db.commit()
    flash("Devolução registrada.", "ok")
    destino = request.referrer or url_for("index")
    if "/historico" not in destino:
        destino = destino.split("#")[0] + "#devolucao"
    return redirect(destino)


# ---------------------------------------------------------------- histórico
@app.route("/historico")
def historico():
    busca = request.args.get("q", "").strip()
    sql = EMPRESTIMOS_SQL
    params = ()
    if busca:
        sql += (" WHERE a.nome LIKE ? OR l.titulo LIKE ? OR a.turma LIKE ?"
                " OR uc.nome LIKE ? OR ud.nome LIKE ?")
        params = (f"%{busca}%",) * 5
    sql += " ORDER BY e.id DESC LIMIT 500"
    rows = get_db().execute(sql, params).fetchall()
    return render_template("historico.html", emprestimos=rows, busca=busca, hoje=hoje())


# ---------------------------------------------------------------- alunos
@app.route("/alunos", methods=["GET", "POST"])
def alunos():
    db = get_db()
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if nome:
            db.execute(
                "INSERT INTO alunos (nome, turma, matricula, telefone, criado_por) VALUES (?, ?, ?, ?, ?)",
                (nome, request.form.get("turma", "").strip(), request.form.get("matricula", "").strip(),
                 request.form.get("telefone", "").strip(), g.user["id"]),
            )
            db.commit()
            flash("Aluno cadastrado.", "ok")
        return redirect(url_for("alunos"))
    rows = db.execute(
        """SELECT a.*, u.nome AS cadastrado_por,
                  (SELECT COUNT(*) FROM emprestimos e
                   WHERE e.aluno_id = a.id AND e.data_devolucao IS NULL) AS em_aberto
           FROM alunos a LEFT JOIN usuarios u ON u.id = a.criado_por ORDER BY a.nome"""
    ).fetchall()
    return render_template("alunos.html", alunos=rows)


@app.route("/alunos/<int:aluno_id>/editar", methods=["GET", "POST"])
def editar_aluno(aluno_id):
    db = get_db()
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if nome:
            db.execute(
                "UPDATE alunos SET nome=?, turma=?, matricula=?, telefone=? WHERE id=?",
                (nome, request.form.get("turma", "").strip(), request.form.get("matricula", "").strip(),
                 request.form.get("telefone", "").strip(), aluno_id),
            )
            db.commit()
            flash("Aluno atualizado.", "ok")
        return redirect(url_for("alunos"))
    aluno = db.execute("SELECT * FROM alunos WHERE id=?", (aluno_id,)).fetchone()
    if aluno is None:
        return redirect(url_for("alunos"))
    return render_template("editar_aluno.html", aluno=aluno)


# ---------------------------------------------------------------- livros
@app.route("/livros", methods=["GET", "POST"])
def livros():
    db = get_db()
    if request.method == "POST":
        titulo = request.form.get("titulo", "").strip()
        if titulo:
            db.execute(
                "INSERT INTO livros (titulo, autor, codigo, exemplares, criado_por) VALUES (?, ?, ?, ?, ?)",
                (titulo, request.form.get("autor", "").strip(), request.form.get("codigo", "").strip(),
                 max(1, request.form.get("exemplares", type=int) or 1), g.user["id"]),
            )
            db.commit()
            flash("Livro cadastrado.", "ok")
        return redirect(url_for("livros"))
    rows = db.execute(LIVROS_SQL + " ORDER BY titulo").fetchall()
    return render_template("livros.html", livros=rows)


@app.route("/livros/<int:livro_id>/editar", methods=["GET", "POST"])
def editar_livro(livro_id):
    db = get_db()
    if request.method == "POST":
        titulo = request.form.get("titulo", "").strip()
        if titulo:
            db.execute(
                "UPDATE livros SET titulo=?, autor=?, codigo=?, exemplares=? WHERE id=?",
                (titulo, request.form.get("autor", "").strip(), request.form.get("codigo", "").strip(),
                 max(1, request.form.get("exemplares", type=int) or 1), livro_id),
            )
            db.commit()
            flash("Livro atualizado.", "ok")
        return redirect(url_for("livros"))
    livro = db.execute("SELECT * FROM livros WHERE id=?", (livro_id,)).fetchone()
    if livro is None:
        return redirect(url_for("livros"))
    return render_template("editar_livro.html", livro=livro)


init_db()

if __name__ == "__main__":
    # Servidor de produção simples (waitress). Uso: python3 app.py
    host = os.environ.get("BIBLIOTECA_HOST", "0.0.0.0")
    port = int(os.environ.get("BIBLIOTECA_PORT", "8080"))
    try:
        from waitress import serve
        print(f"Biblioteca rodando em http://{host}:{port}")
        serve(app, host=host, port=port)
    except ImportError:
        app.run(host=host, port=port)
