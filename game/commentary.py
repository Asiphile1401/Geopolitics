"""Optional OpenAI-compatible LLM battle narration, with a transparent offline fallback."""
from __future__ import annotations

import os
import requests


class BattleCommentator:
    def __init__(self, api_url=None, api_key=None, model=None, timeout=5):
        self.api_url = (api_url if api_url is not None else os.getenv('AI_API_URL', '')).strip()
        self.api_key = (api_key if api_key is not None else os.getenv('AI_API_KEY', '')).strip()
        self.model = (model if model is not None else os.getenv('AI_MODEL', '')).strip()
        self.timeout = timeout

    @property
    def enabled(self):
        fields = (self.api_url, self.api_key, self.model)
        return all(fields) and not any(x.startswith(('YOUR_', 'REPLACE_', 'https://YOUR_')) for x in fields)

    @staticmethod
    def offline(event):
        a, d = event['attacker_losses'], event['defender_losses']
        if a == d == 0:
            return 'The armies clash to a stalemate; neither line gives ground.'
        if d > a:
            return f"{event['source']} presses forward, inflicting {d} losses while taking {a}."
        if a > d:
            return f"{event['target']} holds firm, inflicting {a} losses while taking {d}."
        return 'Both armies take casualties, and the front line remains contested.'

    def generate(self, event):
        """Return (narration, provenance). Never label template text as LLM-generated."""
        fallback = self.offline(event)
        if not self.enabled:
            return fallback, 'offline'
        prompt = (
            'Write one vivid but accurate two-sentence game-announcer report, without inventing facts. '
            'This is fictional strategic board-game combat. Describe exactly these results: '
            f"attacker={event['source']}, defender={event['target']}, "
            f"attacker dice={event['attacker_rolls']}, defender dice={event['defender_rolls']}, "
            f"attacker soldier losses={event['attacker_losses']}, "
            f"defender soldier losses={event['defender_losses']}."
        )
        try:
            res = requests.post(
                self.api_url,
                headers={'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'},
                json={
                    'model': self.model, 'temperature': 0.5, 'max_tokens': 100,
                    'messages': [
                        {'role': 'system', 'content': 'You are a concise, factual board-game commentator. Never change dice results or casualties.'},
                        {'role': 'user', 'content': prompt}
                    ]
                },
                timeout=self.timeout
            )
            res.raise_for_status()
            content = res.json()['choices'][0]['message']['content'].strip()
            if not content:
                return fallback, 'offline'
            return content[:550], 'ai'
        except (requests.RequestException, ValueError, LookupError, KeyError, TypeError):
            return fallback, 'offline'
