import functools

from flask import jsonify, session


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized', 'code': 'unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized', 'code': 'unauthorized'}), 401
        if session.get('role') != 'admin':
            return jsonify({'error': 'Forbidden', 'code': 'forbidden'}), 403
        return f(*args, **kwargs)
    return decorated
