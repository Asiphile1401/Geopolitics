"""Flask routes for the INF4001N single-player geopolitical strategy game.

All game rules live in game.engine and persistence in game.repository.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for, session
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFError, CSRFProtect
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.exceptions import BadRequest
from werkzeug.security import check_password_hash, generate_password_hash

from game.catalog import COUNTRY_DATA
from game.commentary import BattleCommentator
from game.engine import GameEngine, GameRuleError, create_game
from game.repository import GameRepository, StaleGameError

load_dotenv(Path(__file__).with_name('.env'))


class User(UserMixin):
    def __init__(self, document):
        self.id = str(document['_id'])
        self.username = document['username']


def positive_int(value, label='number', *, allow_zero=False):
    try:
        if not isinstance(value, str) or len(value) > 10 or not re.fullmatch(r'\d+', value):
            raise ValueError()
        parsed = int(value)
    except (ValueError, TypeError):
        raise GameRuleError(f'Enter a valid whole {label}.') from None
    if parsed < (0 if allow_zero else 1) or parsed > 1_000_000:
        raise GameRuleError(f'Enter a valid whole {label}.')
    return parsed


def create_app(test_config=None, *, repository=None, commentator=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'DEV_ONLY_CHANGE_THIS_SECRET_KEY'),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', 'false').lower() == 'true',
        WTF_CSRF_TIME_LIMIT=3600,
        MAX_CONTENT_LENGTH=128 * 1024,
        TEMPLATES_AUTO_RELOAD=True,
    )
    if test_config:
        app.config.update(test_config)
    if (os.environ.get('FLASK_ENV') == 'production' and
            app.config['SECRET_KEY'] in ('DEV_ONLY_CHANGE_THIS_SECRET_KEY', 'YOUR_LONG_RANDOM_SECRET_KEY_HERE')):
        raise RuntimeError('Set a real SECRET_KEY in production.')

    mongo_uri = os.environ.get('MONGO_URI')

    mongo_uri = os.environ.get('MONGO_URI')

    if not mongo_uri:
        raise RuntimeError("MONGO_URI is not configured")

    repo = repository or GameRepository(mongo_uri)

    narrator = commentator if commentator is not None else BattleCommentator()
    app.extensions['game_repo'] = repo
    app.extensions['battle_commentator'] = narrator
    csrf = CSRFProtect(app)
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Log in to play a game.'

    @login_manager.user_loader
    def load_user(user_id):
        document = repo.get_user(user_id)
        return User(document) if document else None

    @app.before_request
    def ensure_indexes():
        if request.endpoint not in ('static', 'health'):
            repo.ensure_indexes()

    @app.after_request
    def avoid_private_cache(response):
        if request.path.startswith(('/game/', '/login', '/register')):
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    @app.errorhandler(PyMongoError)
    def db_error(exc):
        app.logger.exception('MongoDB operation failed')
        return render_template('error.html', message='Database temporarily unavailable. Check MONGO_URI and network access.'), 503

    @app.errorhandler(CSRFError)
    def csrf_error(exc):
        return render_template('error.html', message='Security token missing or expired. Reload the page and retry.'), 400

    @app.errorhandler(413)
    def oversized(exc):
        return render_template('error.html', message='Your request is too large.'), 413

    @app.route('/')
    def index():
        recent = repo.list_games(limit=12)
        mine = repo.list_games(owner_id=current_user.id, limit=30) if current_user.is_authenticated else []
        return render_template('index.html', games=[GameEngine(g).summary() for g in recent],
                               my_games=[GameEngine(g).summary() for g in mine])

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            if not re.fullmatch(r'[A-Za-z0-9_]{3,24}', username):
                flash('Username must contain 3–24 letters, numbers or underscores.')
            elif len(password) < 10 or len(password) > 128:
                flash('Use a password of 10–128 characters.')
            elif repo.find_user(username) is not None:
                flash('Username unavailable. Choose another.')
            else:
                try:
                    repo.add_user(username, generate_password_hash(password))
                except DuplicateKeyError:
                    flash('Username unavailable. Choose another.')
                else:
                    flash('Account created. Log in to start playing.')
                    return redirect(url_for('login'))
        return render_template('auth.html', mode='Register')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            # Per-address, shared ten-minute login window. MongoDB TTL index cleans the logs.
            key = request.remote_addr or 'unknown'
            now = datetime.now(timezone.utc)
            repo.db.login_attempts.create_index('at', expireAfterSeconds=900)
            recent = repo.db.login_attempts.count_documents(
                {'key': key, 'at': {'$gte': now - timedelta(minutes=10)}})
            if recent >= 12:
                flash('Too many login attempts. Try again in ten minutes.')
                return render_template('auth.html', mode='Login'), 429
            record = repo.find_user(username)
            if record and check_password_hash(record['password_hash'], password):
                repo.db.login_attempts.delete_many({'key': key})
                session.clear()  # rotate client session state on authentication
                login_user(User(record))
                return redirect(url_for('index'))
            repo.db.login_attempts.insert_one({'key': key, 'at': now})
            flash('Invalid username or password.')
        return render_template('auth.html', mode='Login')

    @app.route('/logout', methods=['POST'])
    @login_required
    def logout():
        logout_user()
        session.clear()
        flash('You have logged out.')
        return redirect(url_for('index'))

    @app.route('/new-game', methods=['GET', 'POST'])
    @login_required
    def create_new_game():
        if request.method == 'POST':
            country = request.form.get('country', '')
            try:
                game = create_game(current_user.username, current_user.id, country, COUNTRY_DATA)
            except GameRuleError as exc:
                flash(str(exc))
            else:
                game_id = str(repo.new_game(game))
                return redirect(url_for('game_page', game_id=game_id))
        return render_template('new_game.html', countries=sorted(COUNTRY_DATA.values(), key=lambda x: x['name']))

    @app.route('/game/<game_id>')
    def game_page(game_id):
        game = repo.get_game(game_id)
        if not game:
            abort(404)
        engine = GameEngine(game)
        owned = current_user.is_authenticated and current_user.id == game['owner_id']
        return render_template('game.html', game=engine.summary(), is_owner=owned,
                               human_alive=bool(engine.owned('human')),
                               narrator_enabled=narrator.enabled)

    @app.route('/game/<game_id>/state')
    def game_state(game_id):
        game = repo.get_game(game_id)
        if game is None:
            return jsonify(error='Game not found'), 404
        eng = GameEngine(game)
        public = eng.summary()
        public['human_alive'] = bool(eng.owned('human'))
        return jsonify(public)

    @app.route('/game/<game_id>/action', methods=['POST'])
    @login_required
    def game_action(game_id):
        game = repo.get_game(game_id, owner_id=current_user.id)
        if game is None:
            abort(403)
        engine = GameEngine(game, commentator=narrator)
        if engine.player_id != 'human' or game['status'] != 'active':
            flash('It is not your turn, or the game has finished.')
            return redirect(url_for('game_page', game_id=game_id))
        action = request.form.get('action', '')
        try:
            if action == 'reinforce':
                allocations = {name: positive_int(request.form.get(f'alloc_{i}', '0'), allow_zero=True)
                               for i, name in enumerate(engine.owned('human'))}
                engine.reinforce(allocations)
            elif action == 'transfer':
                engine.transfer(request.form.get('from_country', ''),
                                request.form.get('to_country', ''),
                                positive_int(request.form.get('amount', '')))
            elif action == 'attack':
                engine.begin_attack(request.form.get('attack_source', ''),
                                    request.form.get('attack_target', ''))
            elif action == 'roll':
                engine.roll_phase()
            elif action == 'stop':
                engine.stop_attack()
            elif action == 'occupy':
                engine.finish_conquest(positive_int(request.form.get('additional', '0'),
                                                    allow_zero=True))
            elif action == 'skip':
                engine.skip()
            else:
                raise GameRuleError('Unrecognised action.')
            repo.save_game(game)
        except (GameRuleError, StaleGameError) as exc:
            flash(str(exc))
        return redirect(url_for('game_page', game_id=game_id))

    @app.route('/game/<game_id>/npc-step', methods=['POST'])
    @login_required
    def npc_step(game_id):
        game = repo.get_game(game_id, owner_id=current_user.id)
        if game is None:
            return jsonify(error='Only the game owner can control the simulation.'), 403
        engine = GameEngine(game, commentator=narrator)
        try:
            engine.npc_step()
            repo.save_game(game)
            state = engine.summary()
            state['human_alive'] = bool(engine.owned('human'))
            return jsonify(state)
        except (GameRuleError, StaleGameError) as exc:
            return jsonify(error=str(exc)), 409

    @app.route('/health')
    def health():
        try:
            repo.health()
            return jsonify(status='ok', database='connected')
        except PyMongoError:
            return jsonify(status='error', database='not connected'), 503

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')
