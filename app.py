import calendar
import os
import secrets
import sqlite3
from datetime import date, datetime

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

from auth import admin_required, login_required
from banks import bank_name
from db import SCHOOL_NAME, close_connection, get_db, init_db
from reports import reports_bp

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
if hasattr(app, 'json'):
    app.json.ensure_ascii = False
app.register_blueprint(reports_bp)


@app.teardown_appcontext
def _close_connection(exception):
    close_connection(exception)


def fail(code, status=400):
    return jsonify({'error': code, 'code': code}), status


def clean(value):
    if value is None:
        return ''
    return str(value).strip()


def digits_only(value):
    return ''.join(ch for ch in clean(value) if ch.isdigit())


def embg_checksum_ok(number):
    weights = (7, 6, 5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    total = sum(int(number[i]) * weights[i] for i in range(12))
    check = 11 - (total % 11)
    if check >= 10:
        check = 0
    return check == int(number[12])


def reject_spaces(value, space_code, digit_code):
    raw = clean(value)
    if any(ch.isspace() for ch in raw):
        return None, space_code
    if any(not ch.isdigit() for ch in raw):
        return None, digit_code
    return raw, None


def parse_embg(value):
    raw = clean(value)
    if not raw:
        return None, False, None
    number, error = reject_spaces(raw, 'embg_spaces', 'embg_digits')
    if error:
        return None, False, error
    if len(number) != 13:
        return None, False, 'embg_length'
    day = int(number[0:2])
    month = int(number[2:4])
    year_part = int(number[4:7])
    year = 2000 + year_part if year_part < 100 else 1000 + year_part
    if month < 1 or month > 12 or day < 1 or day > calendar.monthrange(year, month)[1]:
        return None, False, 'embg_date'
    return number, embg_checksum_ok(number), None


def parse_account(value):
    raw = clean(value)
    if not raw:
        return None, None
    number, error = reject_spaces(raw, 'account_spaces', 'account_digits')
    if error:
        return None, error
    if len(number) != 15:
        return None, 'account_length'
    return number, None


def parse_date(value):
    text = clean(value)
    if not text:
        return None, 'date_required'
    try:
        date.fromisoformat(text)
    except ValueError:
        return None, 'bad_date'
    return text, None


def parse_amount(value):
    if value is None or value == '':
        return None, 'amount_required'
    if isinstance(value, bool):
        return None, 'bad_amount'
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = clean(value).replace(' ', '').replace('\u00a0', '')
        if not text:
            return None, 'amount_required'
        if ',' in text and '.' in text:
            if text.rfind(',') > text.rfind('.'):
                text = text.replace('.', '').replace(',', '.')
            else:
                text = text.replace(',', '')
        elif ',' in text:
            text = text.replace(',', '.')
        elif text.count('.') > 1:
            text = text.replace('.', '')
        elif text.count('.') == 1:
            left, right = text.split('.')
            if len(right) == 3 and left.isdigit() and right.isdigit():
                text = left + right
        try:
            number = float(text)
        except ValueError:
            return None, 'bad_amount'
    number = round(number, 2)
    if number <= 0:
        return None, 'amount_positive'
    return number, None


CLASS_YEARS = ('I', 'II', 'III', 'IV')
CLASS_NUMBERS = tuple(str(number) for number in range(1, 13))


def parse_class(value):
    text = clean(value).upper().replace(' ', '')
    if not text:
        return None, None
    if '-' not in text:
        return None, 'bad_class'
    year, number = text.split('-', 1)
    if year not in CLASS_YEARS or number not in CLASS_NUMBERS:
        return None, 'bad_class'
    return f'{year}-{number}', None


def parse_identity(data):
    last_name = clean(data.get('last_name'))
    first_name = clean(data.get('first_name'))
    parent_name = clean(data.get('parent_name'))
    if not last_name:
        return None, 'last_name_required'
    if not first_name:
        return None, 'first_name_required'
    if not parent_name:
        return None, 'parent_required'
    class_name, error = parse_class(data.get('class_name'))
    if error:
        return None, error
    embg, checksum_ok, error = parse_embg(data.get('parent_embg'))
    if error:
        return None, error
    account, error = parse_account(data.get('bank_account'))
    if error:
        return None, error
    return {
        'last_name': last_name,
        'first_name': first_name,
        'parent_name': parent_name,
        'class_name': class_name,
        'parent_embg': embg,
        'bank_account': account,
        'notes': clean(data.get('notes')) or None,
        'embg_warning': not checksum_ok,
    }, None


def parse_bill(item):
    if not isinstance(item, dict):
        return None, 'bad_bill'
    bill_date, error = parse_date(item.get('bill_date'))
    if error:
        return None, error
    amount, error = parse_amount(item.get('amount'))
    if error:
        return None, error
    bill_id = item.get('id')
    if bill_id in (None, '', 0, '0'):
        bill_id = None
    else:
        try:
            bill_id = int(bill_id)
        except (TypeError, ValueError):
            return None, 'bad_bill'
    return {
        'id': bill_id,
        'bill_date': bill_date,
        'amount': amount,
        'note': clean(item.get('note')) or None,
        'year': int(bill_date[:4]),
        'month': int(bill_date[5:7]),
    }, None


def parse_bills(data):
    raw = data.get('bills') or []
    if not isinstance(raw, list):
        return None, 'bad_bill'
    bills = []
    for item in raw:
        if not isinstance(item, dict):
            return None, 'bad_bill'
        if not clean(item.get('bill_date')) and not clean(item.get('amount')) and not clean(item.get('note')):
            continue
        parsed, error = parse_bill(item)
        if error:
            return None, error
        bills.append(parsed)
    return bills, None


def student_row(student_id):
    db = get_db()
    row = db.execute('SELECT * FROM students WHERE id = ?', (student_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    bills = db.execute(
        'SELECT * FROM bills WHERE student_id = ? ORDER BY bill_date, id',
        (student_id,)
    ).fetchall()
    item['bills'] = [dict(bill) for bill in bills]
    item['bill_count'] = len(item['bills'])
    item['total'] = round(sum(bill['amount'] for bill in item['bills']), 2)
    item['embg_warning'] = bool(item['parent_embg']) and not embg_checksum_ok(item['parent_embg'])
    item['bank_name'] = bank_name(item['bank_account'])
    return item


def find_duplicate(identity, skip_id=None):
    last_name = identity['last_name'].casefold()
    first_name = identity['first_name'].casefold()
    rows = get_db().execute(
        'SELECT id, last_name, first_name, parent_embg FROM students'
    ).fetchall()
    for row in rows:
        if skip_id and row['id'] == skip_id:
            continue
        if not identity['parent_embg'] or not row['parent_embg']:
            continue
        if (row['last_name'].casefold() == last_name
                and row['first_name'].casefold() == first_name
                and row['parent_embg'] == identity['parent_embg']):
            return row
    return None


def insert_bills(db, student_id, bills):
    for bill in bills:
        db.execute(
            '''INSERT INTO bills (student_id, bill_date, amount, note, year, month)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (student_id, bill['bill_date'], bill['amount'], bill['note'], bill['year'], bill['month'])
        )


def replace_month_bills(db, student_id, year, month, bills):
    """Replace bills for one month only. Bills from other months stay."""
    for bill in bills:
        if bill['year'] != year or bill['month'] != month:
            return 'bill_outside_month'
    existing = {
        row['id']: row
        for row in db.execute(
            'SELECT * FROM bills WHERE student_id = ? AND year = ? AND month = ?',
            (student_id, year, month)
        )
    }
    kept = set()
    for bill in bills:
        if bill['id'] is None:
            insert_bills(db, student_id, [bill])
            continue
        if bill['id'] not in existing:
            return 'bad_bill'
        kept.add(bill['id'])
        db.execute(
            '''UPDATE bills SET bill_date=?, amount=?, note=?, year=?, month=?
               WHERE id=? AND student_id=?''',
            (bill['bill_date'], bill['amount'], bill['note'], bill['year'], bill['month'],
             bill['id'], student_id)
        )
    for bill_id in existing:
        if bill_id not in kept:
            db.execute('DELETE FROM bills WHERE id = ? AND year = ? AND month = ?', (bill_id, year, month))
    return None


def bill_period(data):
    year = clean(data.get('bill_year'))
    month = clean(data.get('bill_month'))
    if not year.isdigit() or not (2000 <= int(year) <= 2100):
        return None, None, 'bad_year'
    if not month.isdigit() or not (1 <= int(month) <= 12):
        return None, None, 'bad_month'
    return int(year), int(month), None


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    db = get_db()
    user = db.execute(
        'SELECT * FROM users WHERE username = ?',
        (clean(data.get('username')),)
    ).fetchone()
    if not user or not check_password_hash(user['password_hash'], data.get('password', '')):
        return fail('bad_login', 401)
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    return jsonify({'id': user['id'], 'username': user['username'], 'role': user['role']})


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/me')
def me():
    if 'user_id' not in session:
        return fail('unauthorized', 401)
    return jsonify({
        'id': session['user_id'],
        'username': session['username'],
        'role': session['role'],
        'school': SCHOOL_NAME,
    })


@app.route('/api/me/password', methods=['PUT'])
@login_required
def change_own_password():
    data = request.get_json(silent=True) or {}
    new_pw = clean(data.get('password'))
    if not new_pw:
        return fail('password_required')
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if not user or not check_password_hash(user['password_hash'], data.get('current_password', '')):
        return fail('bad_password')
    db.execute(
        'UPDATE users SET password_hash = ? WHERE id = ?',
        (generate_password_hash(new_pw), session['user_id'])
    )
    db.commit()
    return jsonify({'ok': True})


@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    rows = get_db().execute(
        'SELECT id, username, role, created_at FROM users ORDER BY id'
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json(silent=True) or {}
    username = clean(data.get('username'))
    password = clean(data.get('password'))
    role = clean(data.get('role')) or 'user'
    if not username or not password:
        return fail('user_required')
    if role not in ('admin', 'user'):
        return fail('bad_role')
    db = get_db()
    try:
        cur = db.execute(
            'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
            (username, generate_password_hash(password), role)
        )
        db.commit()
    except sqlite3.IntegrityError:
        return fail('user_exists', 409)
    row = db.execute(
        'SELECT id, username, role, created_at FROM users WHERE id = ?',
        (cur.lastrowid,)
    ).fetchone()
    return jsonify(dict(row)), 201


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        return fail('cannot_delete_self')
    db = get_db()
    target = db.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()
    if not target:
        return fail('not_found', 404)
    if target['role'] == 'admin':
        admins = db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
        if admins <= 1:
            return fail('last_admin')
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    return jsonify({'ok': True})


@app.route('/api/students', methods=['GET'])
@login_required
def get_students():
    search = clean(request.args.get('search')).casefold()
    year = clean(request.args.get('year'))
    year_value = int(year) if year.isdigit() else None
    rows = get_db().execute('''
        SELECT s.*,
               COUNT(b.id) AS bill_count,
               ROUND(COALESCE(SUM(b.amount), 0), 2) AS total
        FROM students s
        LEFT JOIN bills b ON b.student_id = s.id
            AND (? IS NULL OR b.year = ?)
        GROUP BY s.id
        ORDER BY s.last_name COLLATE NOCASE, s.first_name COLLATE NOCASE, s.id
    ''', (year_value, year_value)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item['bank_name'] = bank_name(item['bank_account'])
        if search:
            item['bank_name'] = bank_name(item['bank_account'])
            haystack = ' '.join([
                item['last_name'], item['first_name'], item['parent_name'], item['class_name'] or '',
                item['parent_embg'] or '', item['bank_account'] or '', item['notes'] or '',
            ]).casefold()
            if search not in haystack:
                continue
        result.append(item)
    return jsonify(result)


@app.route('/api/students/<int:student_id>', methods=['GET'])
@login_required
def get_student(student_id):
    item = student_row(student_id)
    if not item:
        return fail('not_found', 404)
    return jsonify(item)


@app.route('/api/students', methods=['POST'])
@login_required
def create_student():
    data = request.get_json(silent=True) or {}
    identity, error = parse_identity(data)
    if error:
        return fail(error)
    bills, error = parse_bills(data)
    if error:
        return fail(error)
    if find_duplicate(identity):
        return fail('duplicate', 409)
    db = get_db()
    cur = db.execute(
        '''INSERT INTO students (last_name, first_name, parent_name, class_name, parent_embg, bank_account, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (identity['last_name'], identity['first_name'], identity['parent_name'], identity['class_name'],
         identity['parent_embg'], identity['bank_account'], identity['notes'])
    )
    insert_bills(db, cur.lastrowid, bills)
    db.commit()
    return jsonify(student_row(cur.lastrowid)), 201


@app.route('/api/students/<int:student_id>', methods=['PUT'])
@admin_required
def update_student(student_id):
    data = request.get_json(silent=True) or {}
    identity, error = parse_identity(data)
    if error:
        return fail(error)
    bills = None
    if 'bills' in data:
        bills, error = parse_bills(data)
        if error:
            return fail(error)
    if not student_row(student_id):
        return fail('not_found', 404)
    if find_duplicate(identity, student_id):
        return fail('duplicate', 409)
    db = get_db()
    db.execute(
        '''UPDATE students SET last_name=?, first_name=?, parent_name=?, class_name=?, parent_embg=?,
           bank_account=?, notes=? WHERE id=?''',
        (identity['last_name'], identity['first_name'], identity['parent_name'], identity['class_name'],
         identity['parent_embg'], identity['bank_account'], identity['notes'], student_id)
    )
    if 'bills' in data:
        year, month, error = bill_period(data)
        if error:
            return fail(error)
        error = replace_month_bills(db, student_id, year, month, bills)
        if error:
            db.rollback()
            return fail(error)
    db.commit()
    return jsonify(student_row(student_id))


@app.route('/api/students/<int:student_id>/bills', methods=['POST'])
@login_required
def add_bills(student_id):
    data = request.get_json(silent=True) or {}
    raw = data.get('bills', data)
    bills, error = parse_bills({'bills': raw if isinstance(raw, list) else [raw]})
    if error:
        return fail(error)
    if not bills:
        return fail('amount_required')
    if not student_row(student_id):
        return fail('not_found', 404)
    db = get_db()
    insert_bills(db, student_id, bills)
    db.commit()
    return jsonify(student_row(student_id)), 201


@app.route('/api/students/<int:student_id>', methods=['DELETE'])
@admin_required
def delete_student(student_id):
    db = get_db()
    if not db.execute('SELECT id FROM students WHERE id = ?', (student_id,)).fetchone():
        return fail('not_found', 404)
    db.execute('DELETE FROM students WHERE id = ?', (student_id,))
    db.commit()
    return jsonify({'ok': True})


@app.route('/api/years')
@login_required
def get_years():
    rows = get_db().execute('SELECT DISTINCT year FROM bills ORDER BY year DESC').fetchall()
    years = [row['year'] for row in rows]
    current = datetime.now().year
    if current not in years:
        years.insert(0, current)
    return jsonify(years)


if __name__ == '__main__':
    init_db()
    print()
    print('  Поврат на патни трошоци — ' + SCHOOL_NAME)
    print('  Отворете: http://127.0.0.1:5050')
    print()
    app.run(host='127.0.0.1', port=5050, debug=False)
