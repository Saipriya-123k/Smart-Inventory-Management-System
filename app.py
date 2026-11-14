from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from functools import wraps
from datetime import datetime, date
from pathlib import Path

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DB_PATH = Path(__file__).with_name("inventory.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT '',
            price REAL NOT NULL DEFAULT 0,
            quantity INTEGER NOT NULL DEFAULT 0,
            min_stock INTEGER NOT NULL DEFAULT 5
        );
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total REAL NOT NULL,
            sold_at TEXT NOT NULL
        );
        """)
        if not db.execute("SELECT id FROM users LIMIT 1").fetchone():
            db.executemany("INSERT INTO users(username,password,role) VALUES(?,?,?)", [
                ("admin", "admin123", "admin"),
                ("staff", "staff123", "staff")
            ])
        if not db.execute("SELECT id FROM products LIMIT 1").fetchone():
            db.executemany(
                "INSERT INTO products(name,category,price,quantity,min_stock) VALUES(?,?,?,?,?)",
                [
                    ("Rice (1 kg)", "Groceries", 60, 50, 10),
                    ("Sugar (1 kg)", "Groceries", 48, 8, 15),
                    ("Cooking Oil", "Groceries", 145, 30, 10),
                    ("Biscuits", "Snacks", 10, 5, 20),
                ]
            )

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_user():
    return {"current_user": session.get("username"), "current_role": session.get("role")}

@app.route("/", methods=["GET"])
def home():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
        if user:
            session.update(user_id=user["id"], username=user["username"], role=user["role"])
            return redirect(url_for("dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    with get_db() as db:
        total_products = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        total_units = db.execute("SELECT COALESCE(SUM(quantity),0) FROM products").fetchone()[0]
        low_count = db.execute("SELECT COUNT(*) FROM products WHERE quantity <= min_stock").fetchone()[0]
        today_sales = db.execute("SELECT COALESCE(SUM(total),0) FROM sales WHERE date(sold_at)=date('now','localtime')").fetchone()[0]
        recent = db.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 5").fetchall()
        low_items = db.execute("SELECT * FROM products WHERE quantity <= min_stock ORDER BY quantity ASC LIMIT 5").fetchall()
    return render_template("dashboard.html", total_products=total_products, total_units=total_units,
                           low_count=low_count, today_sales=today_sales, recent=recent, low_items=low_items)

@app.route("/products", methods=["GET", "POST"])
@login_required
def products():
    with get_db() as db:
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            try:
                price = max(0, float(request.form.get("price", 0)))
                quantity = max(0, int(request.form.get("quantity", 0)))
                min_stock = max(0, int(request.form.get("min_stock", 5)))
            except ValueError:
                flash("Please enter valid numbers.", "error")
                return redirect(url_for("products"))
            if not name:
                flash("Product name is required.", "error")
            else:
                db.execute("INSERT INTO products(name,category,price,quantity,min_stock) VALUES(?,?,?,?,?)",
                           (name, category, price, quantity, min_stock))
                flash("Product added successfully.", "success")
            return redirect(url_for("products"))
        q = request.args.get("q", "").strip()
        items = db.execute("SELECT * FROM products WHERE name LIKE ? OR category LIKE ? ORDER BY name",
                           (f"%{q}%", f"%{q}%")).fetchall()
    return render_template("products.html", products=items, query=q)

@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    with get_db() as db:
        item = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not item:
            flash("Product not found.", "error")
            return redirect(url_for("products"))
        if request.method == "POST":
            try:
                db.execute("""UPDATE products SET name=?, category=?, price=?, quantity=?, min_stock=? WHERE id=?""",
                           (request.form["name"].strip(), request.form.get("category","").strip(),
                            max(0,float(request.form["price"])), max(0,int(request.form["quantity"])),
                            max(0,int(request.form["min_stock"])), product_id))
                flash("Product updated.", "success")
            except (ValueError, KeyError):
                flash("Please check the entered values.", "error")
            return redirect(url_for("products"))
    return render_template("edit_product.html", product=item)

@app.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
def delete_product(product_id):
    with get_db() as db:
        db.execute("DELETE FROM products WHERE id=?", (product_id,))
    flash("Product deleted.", "success")
    return redirect(url_for("products"))

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    with get_db() as db:
        if request.method == "POST":
            try:
                product_id = int(request.form["product_id"])
                qty = int(request.form["quantity"])
                product = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
                if not product or qty <= 0:
                    raise ValueError
                if qty > product["quantity"]:
                    flash("Not enough stock available.", "error")
                else:
                    total = qty * product["price"]
                    db.execute("UPDATE products SET quantity=quantity-? WHERE id=?", (qty, product_id))
                    db.execute("INSERT INTO sales(product_id,product_name,quantity,unit_price,total,sold_at) VALUES(?,?,?,?,?,?)",
                               (product_id, product["name"], qty, product["price"], total, datetime.now().isoformat(timespec="seconds")))
                    flash(f"Sale recorded. Total: ₹{total:.2f}", "success")
            except (ValueError, KeyError):
                flash("Please select a product and enter a valid quantity.", "error")
            return redirect(url_for("sell"))
        items = db.execute("SELECT * FROM products WHERE quantity > 0 ORDER BY name").fetchall()
        recent = db.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 10").fetchall()
    return render_template("sales.html", products=items, sales=recent)

@app.route("/alerts")
@login_required
def alerts():
    with get_db() as db:
        items = db.execute("SELECT * FROM products WHERE quantity <= min_stock ORDER BY quantity ASC").fetchall()
    return render_template("alerts.html", products=items)

@app.route("/reports")
@login_required
def reports():
    with get_db() as db:
        total = db.execute("SELECT COALESCE(SUM(total),0) FROM sales").fetchone()[0]
        count = db.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        rows = db.execute("SELECT product_name, SUM(quantity) AS qty, SUM(total) AS revenue FROM sales GROUP BY product_name ORDER BY revenue DESC").fetchall()
        daily = db.execute("""SELECT date(sold_at) AS day, SUM(total) AS revenue FROM sales
                              GROUP BY date(sold_at) ORDER BY day DESC LIMIT 7""").fetchall()
    return render_template("reports.html", total=total, count=count, rows=rows, daily=list(reversed(daily)))

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    with get_db() as db:
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            user = db.execute(
                "SELECT * FROM users WHERE id=?",
                (session["user_id"],)
            ).fetchone()

            if current_password != user["password"]:
                flash("Current password is incorrect.", "error")

            elif not username:
                flash("Username cannot be empty.", "error")

            elif db.execute(
                "SELECT id FROM users WHERE username=? AND id!=?",
                (username, session["user_id"])
            ).fetchone():
                flash("Username already exists.", "error")

            elif new_password and new_password != confirm_password:
                flash("New passwords do not match.", "error")

            elif new_password and len(new_password) < 6:
                flash("Password must contain at least 6 characters.", "error")

            else:
                if new_password:
                    db.execute(
                        "UPDATE users SET username=?, password=? WHERE id=?",
                        (username, new_password, session["user_id"])
                    )
                else:
                    db.execute(
                        "UPDATE users SET username=? WHERE id=?",
                        (username, session["user_id"])
                    )

                session["username"] = username
                flash("Account updated successfully!", "success")

            return redirect(url_for("settings"))

    return render_template("settings.html")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
