from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import pymysql, os, time

app = Flask(__name__)
app.json.ensure_ascii = False

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "http_status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Http request latency", ["method", "endpoint"])

def get_db():
    return pymysql.connect(
        host="db",
        port=3306,
        user="root",
        password=os.environ["MYSQL_ROOT_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )

@app.before_request
def start_timer():
    request.start_time = time.time()

@app.after_request
def record_metrics(response):
    request_latency = time.time() - request.start_time
    REQUEST_LATENCY.labels(request.method, request.path).observe(request_latency)
    REQUEST_COUNT.labels(request.method, request.path, response.status_code).inc()
    return response

@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type":CONTENT_TYPE_LATEST}

@app.route("/health")
def health():
    return {"status": "ok", "version": "v2"}

@app.route("/api/notes", methods=["GET"])
def list_notes():
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, title, content, category_id FROM notes")
        result = cursor.fetchall()
    conn.close()
    return jsonify(result)

@app.route("/api/notes", methods=["POST"])
def create_note():
    data = request.get_json()

    conn = get_db()
    with conn.cursor() as cursor:
        sql = "INSERT INTO notes (title, content, category_id) VALUES (%s, %s, %s)"
        cursor.execute(sql, (
            data["title"],
            data["content"],
            data.get("category_id")
        ))
        new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    note = {
        "id": new_id,
        "title": data["title"],
        "content": data["content"],
        "category_id": data.get("category_id")
    }
    return jsonify(note), 201

@app.route("/api/notes/<int:note_id>", methods=["GET"])
def get_note(note_id):
    conn = get_db()
    with conn.cursor() as cursor:
        sql = "SELECT id, title, content, category_id FROM notes WHERE id = %s"
        cursor.execute(sql, (note_id,))
        note = cursor.fetchone()
    conn.close()

    if note is None:
        return {"error": "笔记不存在"}, 404
    return jsonify(note)

@app.route("/api/notes/<int:note_id>", methods=["PUT"])
def update_note(note_id):
    conn = get_db()
    with conn.cursor() as cursor:
        sql = "SELECT id, title, content, category_id FROM notes WHERE id = %s"
        cursor.execute(sql, (note_id,))
        note = cursor.fetchone()
    
    if note is None:
        conn.close()
        return {"error": "笔记不存在"}, 404
    
    data = request.get_json()
    with conn.cursor() as cursor:
        sql = "UPDATE notes SET title = %s, content = %s, category_id = %s WHERE id = %s"
        cursor.execute(sql, (
            data["title"],
            data["content"],
            data.get("category_id"),
            note_id
        ))
    conn.commit()
    conn.close()

    note["title"] = data["title"]
    note["content"] = data["content"]
    note["category_id"] = data.get("category_id")

    return jsonify(note)

@app.route("/api/notes/<int:note_id>", methods=["DELETE"])
def delete_note(note_id):
    conn = get_db()
    with conn.cursor() as cursor:
        sql = "SELECT id FROM notes WHERE id = %s"
        cursor.execute(sql, (note_id,))
        note = cursor.fetchone()
    if note is None:
        conn.close()
        return {"error": "笔记不存在"}, 404
    
    with conn.cursor() as cursor:
        sql = "DELETE FROM notes WHERE id = %s"
        cursor.execute(sql, (note_id,))
    conn.commit()
    conn.close()
    return {"message": "已删除"}, 200

@app.route("/api/categories", methods=["POST"])
def create_category():
    data = request.get_json()

    conn = get_db()
    with conn.cursor() as cursor:
        sql = "INSERT INTO categories (name) VALUES (%s)"
        cursor.execute(sql, (data["name"],))
        new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    category = {
        "id": new_id,
        "name": data["name"]
    }

    return jsonify(category), 201

@app.route("/api/categories", methods=["GET"])
def list_categories():
    conn = get_db()
    with conn.cursor() as cursor:
        sql = "SELECT id, name FROM categories"
        cursor.execute(sql)
        categories = cursor.fetchall()
    conn.close()

    return jsonify(categories)

@app.route("/api/categories/<int:category_id>", methods=["DELETE"])
def delete_category(category_id):
    conn = get_db()
    with conn.cursor() as cursor:
        sql = "SELECT id FROM categories WHERE id = %s"
        cursor.execute(sql, (category_id,))
        category = cursor.fetchone()

    if category is None:
        conn.close()
        return {"error": "分类不存在"}, 404
    
    with conn.cursor() as cursor:
        sql = "SELECT id FROM notes WHERE category_id = %s"
        cursor.execute(sql, (category_id,))
        has_notes = cursor.fetchone() is not None

    if has_notes:
        conn.close()
        return {"error": "该分类下还有笔记，无法删除"}, 409

    with conn.cursor() as cursor:
        sql = "DELETE FROM categories WHERE id = %s"
        cursor.execute(sql, (category_id,))
    conn.commit()
    conn.close()

    return {"message": "已删除"}, 200

@app.route("/ready")
def ready():
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
        conn.close()
        return {"status": "ready"}
    except Exception:
        return {"status": "not ready"}, 503

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True)

