from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
import secrets
import shutil
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "marrfim_store.db")
UPLOAD_APPS = os.path.join(BASE, "uploads", "apps")
UPLOAD_IMAGES = os.path.join(BASE, "uploads", "images")
BACKUPS = os.path.join(BASE, "backups")

os.makedirs(UPLOAD_APPS, exist_ok=True)
os.makedirs(UPLOAD_IMAGES, exist_ok=True)
os.makedirs(BACKUPS, exist_ok=True)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

ADMIN_USER = "admin"
ADMIN_PASSWORD = "123456"

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()

    con.execute("""
    CREATE TABLE IF NOT EXISTS settings(
        id INTEGER PRIMARY KEY CHECK(id=1),
        store_name TEXT DEFAULT 'MARRFIM STORE',
        subtitle TEXT DEFAULT 'Aplicativos simples, leves e acessíveis.',
        description TEXT DEFAULT 'Loja oficial de aplicativos MARRFIM.',
        pix_key TEXT DEFAULT '',
        pix_instructions TEXT DEFAULT ''
    )
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        version TEXT DEFAULT '1.0',
        price REAL DEFAULT 0,
        description TEXT DEFAULT '',
        features TEXT DEFAULT '',
        requirements TEXT DEFAULT '',
        size TEXT DEFAULT '',
        os TEXT DEFAULT 'Windows 10/11',
        active INTEGER DEFAULT 1,
        exe_name TEXT DEFAULT '',
        created_at TEXT
    )
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        customer_name TEXT,
        customer_email TEXT,
        payment_method TEXT,
        amount REAL,
        status TEXT DEFAULT 'PENDENTE',
        token TEXT UNIQUE,
        created_at TEXT
    )
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS admin_users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT
    )
    """)

    settings = con.execute("SELECT * FROM settings WHERE id=1").fetchone()

    if not settings:
        con.execute("""
        INSERT INTO settings
        (id,store_name,subtitle,description)
        VALUES(1,?,?,?)
        """,(
            "MARRFIM STORE",
            "Aplicativos simples, leves e acessíveis.",
            "Loja oficial de aplicativos MARRFIM."
        ))

    admin = con.execute(
        "SELECT * FROM admin_users WHERE username=?",
        (ADMIN_USER,)
    ).fetchone()

    if not admin:
        con.execute(
            "INSERT INTO admin_users(username,password_hash) VALUES(?,?)",
            (ADMIN_USER, generate_password_hash(ADMIN_PASSWORD))
        )

    product = con.execute(
        "SELECT * FROM products WHERE name=?",
        ("Marrfim ART Estúdio",)
    ).fetchone()

    if not product:
        con.execute("""
        INSERT INTO products
        (name,version,price,description,features,requirements,size,os,active,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,(
            "Marrfim ART Estúdio",
            "V20",
            19.00,
            "Editor de Pixel Art e animação 2D para Windows.",
            "Pixel Art|Animação 2D|Camadas|Timeline|Frames|Pincéis|Paletas|PNG",
            "Windows 10 ou Windows 11|Processador básico|4 GB de RAM recomendado",
            "Leve",
            "Windows 10/11",
            1,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

    con.commit()
    con.close()

@app.context_processor
def globals():
    con=db()
    settings=con.execute("SELECT * FROM settings WHERE id=1").fetchone()
    con.close()
    return {"settings":settings}

@app.route("/")
def home():
    con=db()
    products=con.execute(
        "SELECT * FROM products WHERE active=1 ORDER BY id DESC"
    ).fetchall()
    con.close()
    return render_template("home.html",products=products)

@app.route("/aplicativos")
def apps():
    con=db()
    products=con.execute(
        "SELECT * FROM products WHERE active=1 ORDER BY id DESC"
    ).fetchall()
    con.close()
    return render_template("apps.html",products=products)

@app.route("/produto/<int:product_id>")
def product(product_id):
    con=db()
    p=con.execute(
        "SELECT * FROM products WHERE id=? AND active=1",
        (product_id,)
    ).fetchone()
    con.close()

    if not p:
        abort(404)

    return render_template("product.html",product=p)

@app.route("/comprar/<int:product_id>", methods=["GET","POST"])
def checkout(product_id):
    con=db()
    p=con.execute(
        "SELECT * FROM products WHERE id=? AND active=1",
        (product_id,)
    ).fetchone()
    con.close()

    if not p:
        abort(404)

    if request.method=="POST":
        name=request.form.get("name","").strip()
        email=request.form.get("email","").strip()
        payment=request.form.get("payment","PIX")

        if not name or not email:
            flash("Preencha nome e e-mail.")
            return redirect(url_for("checkout",product_id=product_id))

        token=secrets.token_urlsafe(32)

        con=db()
        cur=con.execute("""
        INSERT INTO orders
        (product_id,customer_name,customer_email,payment_method,amount,status,token,created_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,(
            product_id,
            name,
            email,
            payment,
            p["price"],
            "PENDENTE",
            token,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        order_id=cur.lastrowid
        con.commit()
        con.close()

        return redirect(url_for("order",order_id=order_id))

    return render_template("checkout.html",product=p)

@app.route("/pedido/<int:order_id>")
def order(order_id):
    con=db()
    o=con.execute("""
    SELECT orders.*,products.name AS product_name
    FROM orders
    LEFT JOIN products ON products.id=orders.product_id
    WHERE orders.id=?
    """,(order_id,)).fetchone()
    con.close()

    if not o:
        abort(404)

    return render_template("order.html",order=o)

@app.route("/sobre")
def about():
    return render_template("about.html")

@app.route("/suporte")
def support():
    return render_template("support.html")

# ============================================================
# DOWNLOAD PROTEGIDO
# ============================================================

@app.route("/download/<token>")
def download(token):
    con=db()

    o=con.execute("""
    SELECT orders.*,products.exe_name
    FROM orders
    LEFT JOIN products ON products.id=orders.product_id
    WHERE orders.token=? AND orders.status='PAGO'
    """,(token,)).fetchone()

    con.close()

    if not o or not o["exe_name"]:
        abort(403)

    path=os.path.join(UPLOAD_APPS,o["exe_name"])

    if not os.path.isfile(path):
        abort(404)

    return send_file(path,as_attachment=True)

# ============================================================
# LOGIN ADMIN
# ============================================================

@app.route("/admin/login",methods=["GET","POST"])
def admin_login():

    if request.method=="POST":
        username=request.form.get("username","")
        password=request.form.get("password","")

        con=db()
        user=con.execute(
            "SELECT * FROM admin_users WHERE username=?",
            (username,)
        ).fetchone()
        con.close()

        if user and check_password_hash(user["password_hash"],password):
            session["admin"]=True
            return redirect(url_for("admin"))

        flash("Usuário ou senha incorretos.")

    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))

def admin_required():
    if not session.get("admin"):
        return False
    return True

@app.route("/admin")
def admin():

    if not admin_required():
        return redirect(url_for("admin_login"))

    con=db()

    products=con.execute(
        "SELECT * FROM products ORDER BY id DESC"
    ).fetchall()

    orders=con.execute("""
    SELECT orders.*,products.name AS product_name
    FROM orders
    LEFT JOIN products ON products.id=orders.product_id
    ORDER BY orders.id DESC
    """).fetchall()

    total_products=con.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]

    total_orders=con.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

    pending=con.execute(
        "SELECT COUNT(*) FROM orders WHERE status='PENDENTE'"
    ).fetchone()[0]

    paid=con.execute(
        "SELECT COUNT(*) FROM orders WHERE status='PAGO'"
    ).fetchone()[0]

    sales=con.execute(
        "SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='PAGO'"
    ).fetchone()[0]

    con.close()

    return render_template(
        "admin.html",
        products=products,
        orders=orders,
        total_products=total_products,
        total_orders=total_orders,
        pending=pending,
        paid=paid,
        sales=sales
    )

@app.route("/admin/produto/novo",methods=["GET","POST"])
def new_product():

    if not admin_required():
        return redirect(url_for("admin_login"))

    if request.method=="POST":

        name=request.form.get("name","").strip()

        if not name:
            flash("Nome obrigatório.")
            return redirect(url_for("new_product"))

        con=db()

        cur=con.execute("""
        INSERT INTO products
        (name,version,price,description,features,requirements,size,os,active,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,(
            name,
            request.form.get("version","1.0"),
            float(request.form.get("price","0") or 0),
            request.form.get("description",""),
            request.form.get("features",""),
            request.form.get("requirements",""),
            request.form.get("size",""),
            request.form.get("os","Windows 10/11"),
            1,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        product_id=cur.lastrowid
        con.commit()
        con.close()

        flash("Produto criado.")
        return redirect(url_for("edit_product",product_id=product_id))

    return render_template("admin_product.html",product=None)

@app.route("/admin/produto/<int:product_id>/editar",methods=["GET","POST"])
def edit_product(product_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    con=db()

    product=con.execute(
        "SELECT * FROM products WHERE id=?",
        (product_id,)
    ).fetchone()

    if not product:
        con.close()
        abort(404)

    if request.method=="POST":

        exe=request.files.get("exe")

        exe_name=product["exe_name"]

        if exe and exe.filename:

            if not exe.filename.lower().endswith(".exe"):
                flash("Somente arquivos EXE são permitidos.")
                con.close()
                return redirect(url_for("edit_product",product_id=product_id))

            filename=secure_filename(exe.filename)

            if not filename:
                flash("Nome de arquivo inválido.")
                con.close()
                return redirect(url_for("edit_product",product_id=product_id))

            save_name=f"{product_id}_{secrets.token_hex(6)}_{filename}"
            exe.save(os.path.join(UPLOAD_APPS,save_name))

            if exe_name:
                old=os.path.join(UPLOAD_APPS,exe_name)
                if os.path.isfile(old):
                    try:
                        os.remove(old)
                    except:
                        pass

            exe_name=save_name

        con.execute("""
        UPDATE products SET
        name=?,
        version=?,
        price=?,
        description=?,
        features=?,
        requirements=?,
        size=?,
        os=?,
        active=?,
        exe_name=?
        WHERE id=?
        """,(
            request.form.get("name",""),
            request.form.get("version",""),
            float(request.form.get("price","0") or 0),
            request.form.get("description",""),
            request.form.get("features",""),
            request.form.get("requirements",""),
            request.form.get("size",""),
            request.form.get("os",""),
            1 if request.form.get("active")=="on" else 0,
            exe_name,
            product_id
        ))

        con.commit()

        product=con.execute(
            "SELECT * FROM products WHERE id=?",
            (product_id,)
        ).fetchone()

        con.close()

        flash("Produto atualizado.")
        return redirect(url_for("edit_product",product_id=product_id))

    con.close()

    return render_template("admin_product.html",product=product)

@app.route("/admin/produto/<int:product_id>/excluir",methods=["POST"])
def delete_product(product_id):

    if not admin_required():
        return redirect(url_for("admin_login"))

    con=db()
    product=con.execute(
        "SELECT exe_name FROM products WHERE id=?",
        (product_id,)
    ).fetchone()

    if product and product["exe_name"]:
        path=os.path.join(UPLOAD_APPS,product["exe_name"])
        if os.path.isfile(path):
            os.remove(path)

    con.execute("DELETE FROM products WHERE id=?",(product_id,))
    con.commit()
    con.close()

    flash("Produto excluído.")
    return redirect(url_for("admin"))

# ============================================================
# STATUS DOS PEDIDOS
# ============================================================

@app.route("/admin/pedido/<int:order_id>/<status>",methods=["POST"])
def order_status(order_id,status):

    if not admin_required():
        return redirect(url_for("admin_login"))

    allowed=["PENDENTE","PAGO","CANCELADO"]

    if status not in allowed:
        abort(400)

    con=db()
    con.execute(
        "UPDATE orders SET status=? WHERE id=?",
        (status,order_id)
    )
    con.commit()
    con.close()

    flash("Pedido atualizado.")
    return redirect(url_for("admin"))

# ============================================================
# CONFIGURAÇÕES
# ============================================================

@app.route("/admin/config",methods=["GET","POST"])
def admin_config():

    if not admin_required():
        return redirect(url_for("admin_login"))

    con=db()

    if request.method=="POST":

        con.execute("""
        UPDATE settings SET
        store_name=?,
        subtitle=?,
        description=?,
        pix_key=?,
        pix_instructions=?
        WHERE id=1
        """,(
            request.form.get("store_name","MARRFIM STORE"),
            request.form.get("subtitle",""),
            request.form.get("description",""),
            request.form.get("pix_key",""),
            request.form.get("pix_instructions","")
        ))

        con.commit()
        flash("Configurações salvas.")

    settings=con.execute(
        "SELECT * FROM settings WHERE id=1"
    ).fetchone()

    con.close()

    return render_template("admin_config.html",settings=settings)

# ============================================================
# ALTERAR SENHA
# ============================================================

@app.route("/admin/senha",methods=["POST"])
def change_password():

    if not admin_required():
        return redirect(url_for("admin_login"))

    new_password=request.form.get("password","")

    if len(new_password)<6:
        flash("A senha precisa ter pelo menos 6 caracteres.")
        return redirect(url_for("admin"))

    con=db()

    con.execute("""
    UPDATE admin_users
    SET password_hash=?
    WHERE username=?
    """,(
        generate_password_hash(new_password),
        ADMIN_USER
    ))

    con.commit()
    con.close()

    flash("Senha alterada.")
    return redirect(url_for("admin"))

# ============================================================
# BACKUP
# ============================================================

@app.route("/admin/backup")
def backup():

    if not admin_required():
        return redirect(url_for("admin_login"))

    name="marrfim_store_backup_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".db"

    path=os.path.join(BACKUPS,name)

    shutil.copy2(DB,path)

    return send_file(path,as_attachment=True)

# ============================================================
# ERROS
# ============================================================

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html",code=404,message="Página não encontrada."),404

@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html",code=403,message="Acesso não autorizado."),403

# ============================================================
# START
# ============================================================


# ==========================================================
# PUBLIC_SITE_ROUTES_V2
# ==========================================================

@app.route("/")
def public_home():
    return render_template("index.html")

@app.route("/aplicacoes")
def public_aplicacoes():
    return render_template("aplicacoes.html")

@app.route("/produto/<int:product_id>")
def public_produto(product_id):
    return render_template("produto.html")

@app.route("/sobre")
def public_sobre():
    return render_template("sobre.html")

@app.route("/suporte")
def public_suporte():
    return render_template("suporte.html")

@app.route("/checkout/<int:product_id>")
def public_checkout(product_id):
    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Compra — MARRFIM STORE</title>
    <link rel="stylesheet" href="/static/style.css">
    </head>
    <body>
    <header>
    <div class="logo">MARRFIM<span>STORE</span></div>
    <nav>
    <a href="/">Início</a>
    <a href="/aplicacoes">Aplicativos</a>
    <a href="/suporte">Suporte</a>
    </nav>
    </header>
    <main class="page">
    <div class="page-head">
    <span>FINALIZAR COMPRA</span>
    <h1>Marrfim ART Estúdio</h1>
    <p>Preço: R$ 19,00</p>
    </div>
    <div class="info-box">
    <h2>Compra</h2>
    <p>O sistema de pagamento será conectado ao método configurado no painel administrativo.</p>
    <br>
    <a class="btn primary" href="/admin/login">Continuar</a>
    </div>
    </main>
    <footer><b>MARRFIM STORE</b></footer>
    </body>
    </html>
    """


@app.route("/", methods=["GET"])
def marrfim_store_home():
    return render_template("index.html")
if __name__=="__main__":
    init_db()
    print("")
    print("==============================================")
    print("        MARRFIM STORE V2")
    print("==============================================")
    print("URL: http://localhost:8080")
    print("ADMIN: http://localhost:8080/admin/login")
    print("USUARIO: admin")
    print("SENHA INICIAL: 123456")
    print("==============================================")
    print("")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False) # RENDER_PORT_CONFIG



