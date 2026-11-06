"""MongoDB persistence; no queries or collection handles in view/controller code."""
from __future__ import annotations

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import MongoClient, ASCENDING, DESCENDING
from .engine import soldier_value


class StaleGameError(RuntimeError):
    pass


class GameRepository:
    def __init__(self, uri: str, *, client=None):
        self.client = client or MongoClient(uri, serverSelectionTimeoutMS=4000)
        self.db = self.client.get_default_database()
        if self.db is None:
            raise ValueError('MONGO_URI must include a database name such as /geopolitics_game')
        self.users = self.db.users
        self.games = self.db.games
        self._indexes_ready = False

    def ensure_indexes(self):
        if self._indexes_ready:
            return
        self.migrate_legacy_records()
        self.users.create_index([('username_key', ASCENDING)], unique=True, name='unique_username_key')
        self.games.create_index([('owner_id', ASCENDING), ('created_at', DESCENDING)], name='owner_games')
        self.games.create_index([('status', ASCENDING), ('created_at', DESCENDING)], name='public_games')
        self._indexes_ready = True

    def migrate_legacy_records(self):
        """Best-effort backward compatibility with the original starter collections.

        Legacy turn progress is approximate because the starter did not record phases.
        Users should begin a fresh game to get strict turn-state semantics.
        """
        for person in self.users.find({'username_key': {'$exists': False}}, {'username': 1}):
            name = person.get('username', '')
            if name:
                self.users.update_one({'_id': person['_id'], 'username_key': {'$exists': False}},
                                      {'$set': {'username_key': name.casefold()}})
        for doc in self.games.find({'version': {'$exists': False}}):
            for country in doc.get('countries', {}).values():
                country['starting_soldiers'] = soldier_value(country.get('population', 0))
                country['soldiers'] = max(1, country.get('soldiers', 1))
            messages = doc.pop('log', [])
            doc['events'] = [
                {'id': i, 'kind': 'legacy', 'text': text, 'round': doc.get('round', 1),
                 'time': doc.get('created_at', '')} for i, text in enumerate(messages, start=1)
            ]
            doc['event_no'] = len(messages)
            doc['version'] = 1
            doc['phase'] = 'action'
            doc['turns_taken'] = []
            doc['pending_reinforcements'] = 0
            doc['attack'] = None
            doc['npc_transfer_used'] = False
            doc['stats'] = {p['id']: {'attacks': 0, 'dice_phases': 0, 'conquests': 0,
                                    'lost': 0, 'defeated': 0} for p in doc.get('players', [])}
            owners = {c.get('owner') for c in doc.get('countries', {}).values()}
            complete = len(owners) == 1 and None not in owners
            doc['winner'] = next(iter(owners)) if complete else None
            if doc.get('status') == 'finished' and not complete:
                doc['status'] = 'active'  # legacy early-victory condition was incorrect
            doc.pop('last_round_completed', None)
            doc['event_no'] += 1
            doc['events'].append({
                'id': doc['event_no'], 'kind': 'game', 'round': doc.get('round', 1),
                'time': doc.get('created_at', ''),
                'text': 'Existing starter session imported. Turn sequence was reset; a new game is recommended.'
            })
            self.games.replace_one({'_id': doc['_id'], 'version': {'$exists': False}}, doc)

    @staticmethod
    def _oid(value):
        try:
            return ObjectId(value)
        except (InvalidId, TypeError):
            return None

    def find_user(self, username: str):
        return self.users.find_one({'username_key': username.strip().casefold()})

    def get_user(self, user_id: str):
        oid = self._oid(user_id)
        return self.users.find_one({'_id': oid}) if oid else None

    def add_user(self, username: str, password_hash: str):
        self.ensure_indexes()
        return self.users.insert_one({'username': username, 'username_key': username.casefold(),
                                      'password_hash': password_hash}).inserted_id

    def new_game(self, doc: dict):
        self.ensure_indexes()
        return self.games.insert_one(doc).inserted_id

    def get_game(self, game_id: str, owner_id=None):
        oid = self._oid(game_id)
        if not oid:
            return None
        query = {'_id': oid}
        if owner_id is not None:
            query['owner_id'] = owner_id
        return self.games.find_one(query)

    def save_game(self, doc: dict):
        expected_version = doc['version']
        saved = dict(doc)
        saved['version'] = expected_version + 1
        result = self.games.replace_one({
            '_id': doc['_id'], 'owner_id': doc['owner_id'], 'version': expected_version
        }, saved)
        if result.matched_count != 1:
            raise StaleGameError('The game changed in another tab; reload to see the latest board.')
        doc['version'] = saved['version']

    def list_games(self, *, owner_id=None, limit=24):
        query = {'owner_id': owner_id} if owner_id is not None else {'status': 'active'}
        return list(self.games.find(query).sort('created_at', DESCENDING).limit(limit))

    def health(self):
        self.client.admin.command('ping')
        return True
