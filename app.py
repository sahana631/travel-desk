import os
import sqlite3
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "travel-desk-local-secret")
app.config["DATABASE"] = os.environ.get(
    "DATABASE_PATH", os.path.join(os.path.dirname(__file__), "travel_desk.db")
)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            destination TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS itinerary_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_datetime TEXT NOT NULL,
            description TEXT,
            FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE CASCADE
        );
        """
    )
    db.commit()


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


@app.before_request
def load_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT id, username FROM users WHERE id = ?", (user_id,)
        ).fetchone()


@app.context_processor
def inject_user():
    return {"current_user": g.user}


@app.route("/")
def index():
    if g.user is None:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))


@app.route("/register", methods=("GET", "POST"))
def register():
    if g.user is not None:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        error = None

        if not username:
            error = "Username is required."
        elif not password:
            error = "Password is required."

        if error is None:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                db.commit()
            except sqlite3.IntegrityError:
                error = "That username is already taken."
            else:
                flash("Your account is ready. Please log in.", "success")
                return redirect(url_for("login"))

        flash(error, "error")

    return render_template("auth/register.html")


@app.route("/login", methods=("GET", "POST"))
def login():
    if g.user is not None:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password"], password):
            flash("Incorrect username or password.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

    return render_template("auth/login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    trips = get_db().execute(
        """
        SELECT trips.*,
               (SELECT COUNT(*) FROM itinerary_items
                WHERE itinerary_items.trip_id = trips.id) AS itinerary_count
        FROM trips
        WHERE user_id = ?
        ORDER BY start_date ASC, id DESC
        """,
        (g.user["id"],),
    ).fetchall()
    return render_template("dashboard.html", trips=trips)


def get_trip(trip_id):
    return get_db().execute(
        "SELECT * FROM trips WHERE id = ? AND user_id = ?",
        (trip_id, g.user["id"]),
    ).fetchone()


@app.route("/trips/new", methods=("GET", "POST"))
@login_required
def create_trip():
    if request.method == "POST":
        destination = request.form["destination"]
        start_date = request.form["start_date"]
        end_date = request.form["end_date"]
        notes = request.form["notes"]

        if not destination or not start_date or not end_date:
            flash("Destination, start date, and end date are required.", "error")
        else:
            db = get_db()
            db.execute(
                """
                INSERT INTO trips (user_id, destination, start_date, end_date, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (g.user["id"], destination, start_date, end_date, notes),
            )
            db.commit()
            flash("Trip booked.", "success")
            return redirect(url_for("dashboard"))

    return render_template("trip_form.html", trip=None, form_title="Book a trip")


@app.route("/trips/<int:trip_id>/edit", methods=("GET", "POST"))
@login_required
def edit_trip(trip_id):
    trip = get_trip(trip_id)
    if trip is None:
        flash("Trip not found.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        destination = request.form["destination"]
        start_date = request.form["start_date"]
        end_date = request.form["end_date"]
        notes = request.form["notes"]

        if not destination or not start_date or not end_date:
            flash("Destination, start date, and end date are required.", "error")
        else:
            db = get_db()
            db.execute(
                """
                UPDATE trips
                SET destination = ?, start_date = ?, end_date = ?, notes = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    destination,
                    start_date,
                    end_date,
                    notes,
                    trip_id,
                    g.user["id"],
                ),
            )
            db.commit()
            flash("Trip updated.", "success")
            return redirect(url_for("trip_detail", trip_id=trip_id))

        trip = {
            "id": trip_id,
            "destination": destination,
            "start_date": start_date,
            "end_date": end_date,
            "notes": notes,
        }

    return render_template("trip_form.html", trip=trip, form_title="Edit trip")


@app.post("/trips/<int:trip_id>/delete")
@login_required
def delete_trip(trip_id):
    trip = get_trip(trip_id)
    if trip is None:
        flash("Trip not found.", "error")
    else:
        db = get_db()
        db.execute("DELETE FROM itinerary_items WHERE trip_id = ?", (trip_id,))
        db.execute(
            "DELETE FROM trips WHERE id = ? AND user_id = ?", (trip_id, g.user["id"])
        )
        db.commit()
        flash("Trip deleted.", "success")
    return redirect(url_for("dashboard"))


@app.route("/trips/<int:trip_id>")
@login_required
def trip_detail(trip_id):
    trip = get_trip(trip_id)
    if trip is None:
        flash("Trip not found.", "error")
        return redirect(url_for("dashboard"))

    items = get_db().execute(
        """
        SELECT * FROM itinerary_items
        WHERE trip_id = ?
        ORDER BY item_datetime ASC, id ASC
        """,
        (trip_id,),
    ).fetchall()
    return render_template("trip_detail.html", trip=trip, items=items)


@app.route("/trips/<int:trip_id>/itinerary/new", methods=("GET", "POST"))
@login_required
def add_itinerary_item(trip_id):
    trip = get_trip(trip_id)
    if trip is None:
        flash("Trip not found.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        item_type = request.form["item_type"]
        item_datetime = request.form["item_datetime"]
        description = request.form["description"]

        if not item_type or not item_datetime:
            flash("Type and date/time are required.", "error")
        else:
            db = get_db()
            db.execute(
                """
                INSERT INTO itinerary_items
                    (trip_id, item_type, item_datetime, description)
                VALUES (?, ?, ?, ?)
                """,
                (trip_id, item_type, item_datetime, description),
            )
            db.commit()
            flash("Itinerary item added.", "success")
            return redirect(url_for("trip_detail", trip_id=trip_id))

    return render_template("itinerary_form.html", trip=trip)


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)