import requests
import json
import base64
import threading
import datetime
import urllib3
import litellm
import random
import re
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


TOP_MOST_PROMPT = """"
You are a helpful assistant that helps Anki users memorize flashcards through active practice.

Below is the user's description of how they want this card practiced:

---- User's task description ----
TASK_DESCRIPTION
---- End of task description ----

Guidelines:
- Stay focused on the specific card content and the user's stated approach above.
- If you are completely sure or the user explicitely tells you that the exercise is over, just reply precisely with only "END_EXERCISE", so that the program can continue.
- Ask questions, prompt the user to produce answers, or engage them actively — don't just lecture or give away the answer immediately.
- If the user makes a mistake, gently correct it and briefly explain why, then continue the exercise.
- Keep your responses concise; this is a quick review exercise, not a lecture.
- This is one card in a long series of independent review sessions the user will do back to back. Do NOT open with greetings, ask how you can help, or add closing remarks like "let me know if you'd like to continue" or "ready when you are".
    Get straight into the exercise for this specific card and stay there.
- Do not refer to future cards, past cards, or the review session as a whole — treat this exchange as self-contained.
- NEVER use syntax for HTML, MD or similar. The editor doesn't render those.

If your task requires generating words or phrases that may need translation or could be unfamiliar to the user, you can draw from the examples below, taken from the user's own past Anki interactions:

---- Reference vocabulary ----
REF_VOCABULARY
---- End of reference vocabulary ----
"""


class Data:
    def __init__(self):
        self.pending_save_config = False
        self.pending_save_config_llm = False
        self.pending_save_history = False
        self.pending_connection_err = False
        self.decks = {}
        self.config = {}
        self.config_llm = {}
        self._last_shown_note_id = {}
        self.history = {}
        self.today_code = datetime.date.today().toordinal()
        self.current_deck = None
        self.current_model = None
        self.current_exercise = None
        self._config_lock = threading.Lock()
        self._autosave_stop_event = threading.Event()
        self._autosave_thread = None
        self.first_load()

    def first_load(self):
        if not test_connection():
            self.config = {}
            self.decks = {}
            self.pending_connection_err = True
            return

        self.config = {int(k): v for k, v in load_anki("_ankillm_config.json").items()}
        self.config_llm = load_anki("_ankillm_config_llm.json")
        if not self.config_llm:
            self.config_llm = {
                "api_endpoint": "",
                "pricing": None,
                "api_token": "",
                "model_name": "",
            }
        self.history = load_history("_ankillm_history.json")
        self.decks = get_decks()
    
    def add_exercise(self, exercise_name: str):
        self.config.setdefault(self.current_deck, {}).setdefault(self.current_model, {})[exercise_name] = {
            "system_prompt": "",
            "vocabulary": []
        }
        self.pending_save_config = True
    
    def remove_cur_exercise(self):
        self.config.get(self.current_deck, {}).get(self.current_model, {}).pop(self.current_exercise, None)
        self.pending_save_config = True
    
    def update_exercise(self, system_prompt: str, vocabulary: list[str]):
        config = self.config
        if config.get(self.current_deck, {}).get(self.current_model, {}).get(self.current_exercise, None):
            config[self.current_deck][self.current_model][self.current_exercise]["system_prompt"] = system_prompt
            config[self.current_deck][self.current_model][self.current_exercise]["vocabulary"] = vocabulary
            self.pending_save_config = True

    def save_config(self):
        with self._config_lock:
            config_copy = json.loads(json.dumps(self.config))
        save_anki(config_copy, "_ankillm_config.json")

    def save_config_llm(self):
        with self._config_lock:
            config_copy = json.loads(json.dumps(self.config_llm))
        save_anki(config_copy, "_ankillm_config_llm.json")

    def save_history(self):
        with self._config_lock:
            config_copy = json.loads(json.dumps(self.history))
        save_anki(config_copy, "_ankillm_history.json")
    
    def start_autosave(self, interval_seconds: float = 5.0):
        print("start autosave")
        if self._autosave_thread is not None:
            return
        self._autosave_stop_event.clear()

        def _loop():
            while not self._autosave_stop_event.is_set():
                if self.pending_save_config:
                    print("saving configuration")
                    self.save_config()
                    self.pending_save_config = False
                if self.pending_save_config_llm:
                    print("saving configuration for LLM")
                    self.save_config_llm()
                    self.pending_save_config_llm = False
                if self.pending_save_history:
                    print("saving history")
                    self.save_history()
                    self.pending_save_history = False
                self._autosave_stop_event.wait(interval_seconds)

        self._autosave_thread = threading.Thread(target=_loop, daemon=True)
        self._autosave_thread.start()

    def stop_autosave(self):
        if self._autosave_thread is None:
            return
        self._autosave_stop_event.set()
        self._autosave_thread.join(timeout=2)
        self._autosave_thread = None

    def set_note_status(self, deck_id, model, exercise, note_id, status, token_consumption):
        self.history.setdefault("notes", {}).setdefault(self.today_code, {}).setdefault(deck_id, {})\
            .setdefault(model, {}).setdefault(exercise, {})[note_id] = { "token_consumption": token_consumption, "card_status": status }
        self.pending_save_history = True
    
    def get_exercise_review_counts(self, deck_id, model, exercise, note_ids):
        """Returns (not_ok_count, unreviewed_count) for today, given the full
        list of note ids that belong to this exercise's reviewed-today set."""
        statuses = self.history.get("notes", {}).get(self.today_code, {}).get(deck_id, {}).get(model, {}).get(exercise, {})
        not_ok_count = 0
        unreviewed_count = 0
        for note_id in note_ids:
            status = statuses.get(note_id, {}).get("card_status", None)
            if status == "not_ok":
                not_ok_count += 1
            elif status is None:
                unreviewed_count += 1
        return not_ok_count, unreviewed_count

    def get_next_note(self, deck_id, model, exercise, reviewed_today_notes):
        """reviewed_today_notes: list of note dicts (from notesInfo).
        Returns the next note dict to review, or None if all are marked 'ok'."""
        statuses = self.history.get("notes", {}).get(self.today_code, {}).get(deck_id, {}).get(model, {}).get(exercise, {})
        key = (deck_id, model, exercise)

        # first pass: notes never attempted today
        for note in reviewed_today_notes:
            if statuses.get(note['noteId'], {}).get("card_status", None) is None:
                self._last_shown_note_id[key] = note['noteId']
                return note

        # second pass: retry notes marked "not_ok", round-robin away from the last one shown
        not_ok_notes = [n for n in reviewed_today_notes if statuses.get(n['noteId'], {}).get("card_status", None) == "not_ok"]
        if not not_ok_notes:
            self._last_shown_note_id.pop(key, None)
            return None

        last_id = self._last_shown_note_id.get(key)
        candidates = [n for n in not_ok_notes if n['noteId'] != last_id]
        chosen = candidates[0] if candidates else not_ok_notes[0]  # fall back if it's the only one left

        self._last_shown_note_id[key] = chosen['noteId']
        return chosen

    def deck_name(self, deck_id):
        return self.decks.get(deck_id, {}).get("name")
    
    def set_llm_config(self, config: dict):
        config["pricing"] = litellm.model_cost.get(config["model_name"])
        self.config_llm = config
        self.pending_save_config_llm = True

    def setDeck(self, deck_id):
        if deck_id is None or deck_id not in self.decks:
            self.current_deck = None
            self.current_model = None
            self.current_exercise = None
            return

        self.current_deck = deck_id
        models = self.decks[deck_id]["models"]
        if len(models) == 1:
            self.setCurrentModel(next(iter(models)))
        else:
            self.setCurrentModel(None)

    def setCurrentModel(self, current_model: str | None):
        if current_model is None or self.current_deck is None:
            self.current_model = None
            self.current_exercise = None
            return

        available_models = self.decks[self.current_deck]["models"]
        self.current_model = current_model if current_model in available_models else None

        possible_exercises = list(
            self.config.get(self.current_deck, {}).get(self.current_model, {}).keys()
        )
        
        if len(possible_exercises) == 1:
            self.setCurrentExercise(possible_exercises[0])
        elif self.current_exercise not in possible_exercises:
            self.setCurrentExercise(None)

    def setCurrentExercise(self, current_exercise: str | None):
        self.current_exercise = current_exercise


from PyQt5.QtCore import QThread, pyqtSignal


class LLMOpeningWorker(QThread):
    finished = pyqtSignal(str, dict)
    error = pyqtSignal(str)

    def __init__(self, history, system_prompt, vocabulary, reference_notes, parent=None):
        super().__init__(parent)
        self.history = history
        self.system_prompt = system_prompt
        self.vocabulary = vocabulary
        self.reference_notes = reference_notes

    def run(self):
        try:
            answer, token_info = self.history.get_llm_opening(self.system_prompt, self.vocabulary, self.reference_notes)
            self.finished.emit(answer, token_info)
        except Exception as e:
            self.error.emit(str(e))


class LLMReplyWorker(QThread):
    finished = pyqtSignal(str, dict)
    error = pyqtSignal(str)

    def __init__(self, history, user_message, parent=None):
        super().__init__(parent)
        self.history = history
        self.user_message = user_message

    def run(self):
        try:
            answer, token_info = self.history.get_llm_reply(self.user_message)
            self.finished.emit(answer, token_info)
        except Exception as e:
            self.error.emit(str(e))



class History:
    def __init__(self, llm_config):
        self.chat_history = []
        self.opened = False
        self.llm_config = llm_config
        self.system_prompt = None  # set once at opening, reused for every later call

    def resolve_system_prompt(self, system_prompt, note):
        fields = note.get('fields', {})

        def replace_placeholder(match):
            field_name = match.group(1).strip()
            field_data = fields.get(field_name)
            if field_data is None:
                return ""
            return field_data.get('value', '')

        return re.sub(r'\{\{(.*?)\}\}', replace_placeholder, system_prompt)

    def resolve_vocabulary(self, vocabulary, reference_notes):
        selected = get_vocabulary_entries(vocabulary, reference_notes, random_pick=True)
        if not selected:
            return ""
        examples_text = "\n".join(f"- {e}" for e in selected)
        return examples_text

    def _build_messages(self):
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        for entry in self.chat_history:
            role = "assistant" if entry["role"] == "llm" else "user"
            messages.append({"role": role, "content": entry["text"]})
        return messages

    def get_llm_opening(self, system_prompt, vocabulary, reference_notes=None):
        self.system_prompt = TOP_MOST_PROMPT.replace("TASK_DESCRIPTION", system_prompt).replace("REF_VOCABULARY", self.resolve_vocabulary(vocabulary, reference_notes or []))
        messages = self._build_messages()
        answer, token_info = call_llm(self.llm_config, messages)
        self.chat_history.append({"role": "llm", "text": answer})
        self.opened = True
        return answer, token_info

    def get_llm_reply(self, user_message):
        self.chat_history.append({"role": "user", "text": user_message})
        messages = self._build_messages()  # now includes self.system_prompt every time
        answer, token_info = call_llm(self.llm_config, messages)
        self.chat_history.append({"role": "llm", "text": answer})
        return answer, token_info

    def llm_message_count(self):
        return sum(1 for m in self.chat_history if m["role"] == "llm")


def get_vocabulary_entries(vocabulary, reference_notes, random_pick: bool = False):
    """Returns the list of individual entry strings (e.g. 'Hund - dog'),
    capped at ~200 words total. Shared by History.resolve_vocabulary and
    the vocabulary-examples dialog, so both stay in sync."""
    if not vocabulary or not reference_notes:
        return []
    entries = []
    ref_notes = reference_notes.copy()
    if random_pick:
        random.shuffle(ref_notes)
    for note in reference_notes:
        fields = note.get('fields', {})
        parts = []
        for field_name in vocabulary:
            field_data = fields.get(field_name)
            if field_data and field_data.get('value'):
                parts.append(field_data['value'].strip())
        if parts:
            entries.append(" - ".join(parts))
    if not entries:
        return []
    selected = []
    word_count = 0
    for entry in entries:
        entry_words = len(entry.split())
        if selected and word_count + entry_words > 200:
            break
        selected.append(entry)
        word_count += entry_words
    return selected


def test_connection():
    try:
        version = anki_connect_invoke('version')
        print(f"Connected! AnkiConnect version: {version}")
        return True
    except requests.exceptions.ConnectionError:
        print("Could not connect - is Anki running with AnkiConnect installed?")
        return False
    except Exception as e:
        print(f"Connected to server, but got an error: {e}")
        return False


def test_llm_connection(config: dict, timeout: float = 2.0) -> tuple[bool, str]:
    litellm.ssl_verify = False
    
    endpoint = config.get("api_endpoint", "").strip()
    token = config.get("api_token", "").strip()
    model = config.get("model_name", "").strip()

    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "api_key": token or None,
        "timeout": timeout,
        "max_tokens": 1,
    }

    if endpoint:
        kwargs["api_base"] = endpoint.rstrip("/")
        kwargs["custom_llm_provider"] = "openai"

    try:
        litellm.completion(**kwargs)
        return True, "Connected"
    except Exception as e:
        return False, str(e)


def call_llm(config: dict, messages: list[dict], timeout: float = 30.0) -> str:
    """messages: [{"role": "user"/"assistant"/"system", "content": str}, ...]
    Returns the assistant's reply text. Raises on failure — caller should catch."""
    litellm.ssl_verify = False

    endpoint = config.get("api_endpoint", "").strip()
    token = config.get("api_token", "").strip()
    model = config.get("model_name", "").strip()

    kwargs = {
        "model": model,
        "messages": messages,
        "api_key": token or None,
        "timeout": timeout,
    }

    if endpoint:
        kwargs["api_base"] = endpoint.rstrip("/")
        kwargs["custom_llm_provider"] = "openai"

    response = litellm.completion(**kwargs)
    return response.choices[0].message.content, compute_usage(response, config["pricing"])


def compute_usage(response, pricing: dict | None) -> dict:
    usage = getattr(response, "usage", None) or {}

    # --- raw token counts ---
    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0
    total_tokens = getattr(usage, "total_tokens", input_tokens + output_tokens) or 0
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    cache_read_tokens = getattr(prompt_details, "cached_tokens", 0) or 0 if prompt_details else 0
    completion_details = getattr(usage, "completion_tokens_details", None)
    reasoning_tokens = getattr(completion_details, "reasoning_tokens", 0) or 0 if completion_details else 0

    # --- per-token prices (default to 0 if missing from pricing dict) ---
    print("asdasfjkgf")
    input_cost_per_token = pricing.get("input_cost_per_token", 0) if pricing else 0
    output_cost_per_token = pricing.get("output_cost_per_token", 0) if pricing else 0
    cache_read_cost_per_token = pricing.get("cache_read_input_token_cost", 0) if pricing else 0
    reasoning_cost_per_token = pricing.get("output_cost_per_reasoning_token", 0) if pricing else 0

    # --- costs ---
    input_cost = input_tokens * input_cost_per_token
    output_cost = output_tokens * output_cost_per_token
    cache_read_cost = cache_read_tokens * cache_read_cost_per_token
    reasoning_cost = reasoning_tokens * reasoning_cost_per_token

    total_cost = input_cost + output_cost + cache_read_cost + reasoning_cost

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "reasoning_tokens": reasoning_tokens,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "cache_read_cost": cache_read_cost,
        "reasoning_cost": reasoning_cost,
        "total_cost": total_cost,
    }


def add_tokens(token_consumption, token_info):
    return {k: (v + token_consumption.get(k, 0)) for k, v in token_info.items()}
    

def anki_connect_invoke(action, params=None):
    if params is None:
        params = {}
    response = requests.post('http://127.0.0.1:8765', json={
        'action': action,
        'version': 5,
        'params': params
    })
    result = response.json()
    if result.get('error'):
        raise Exception(result['error'])
    if 'result' not in result:
        raise Exception('failed to get results from AnkiConnect')
    return result['result']


def save_anki(config, filename):
    try:
        data = json.dumps(config, ensure_ascii=False, indent=2)
        encoded = base64.b64encode(data.encode('utf-8')).decode('utf-8')
        anki_connect_invoke('storeMediaFile', {
            "filename": filename,
            "data": encoded
        })
        return True
    except Exception as e:
        print(f"Failed to save config: {e}")
        return None


def load_anki(filename):
    try:
        result = anki_connect_invoke('retrieveMediaFile', {"filename": filename})
        if not result:
            return {}
        result = json.loads(base64.b64decode(result).decode('utf-8'))
        return result
    except Exception as e:
        print(f"Failed to load {filename}: {e}")
        return {}


def load_history(filename):
    try:
        result = anki_connect_invoke('retrieveMediaFile', {"filename": filename})
        if not result:
            return {}
        result = json.loads(base64.b64decode(result).decode('utf-8'))
        # structure: {"notes": {deck_id: {today_code: {model: {exercise: {note_id: status}}}}}, ...}
        fixed = {"notes": {}, **{k: v for k, v in result.items() if k != "notes"}}
        for deck_id, today_codes in result["notes"].items():
            fixed["notes"][int(deck_id)] = {}
            for today_code, models in today_codes.items():
                fixed["notes"][int(deck_id)][int(today_code)] = {}
                for model, exercises in models.items():
                    fixed["notes"][int(deck_id)][int(today_code)][model] = {}
                    for exercise, notes in exercises.items():
                        fixed["notes"][int(deck_id)][int(today_code)][model][exercise] = {
                            int(note_id): status for note_id, status in notes.items()
                        }
        return fixed
    except Exception as e:
        print(f"Failed to load {filename}: {e}")
        return {}


# --------------------------


def get_deck_names_and_ids() -> dict:
    """Returns {deck_id: deck_name}, excluding Default."""
    result = anki_connect_invoke('deckNamesAndIds')
    return {v: k for k, v in result.items() if k != "Default"}


def get_decks() -> dict:
    """Returns {deck_id: {"name": deck_name, "models": {...}}}."""
    try:
        id_to_name = get_deck_names_and_ids()
        result = {}
        for deck_id, deck_name in id_to_name.items():
            result[deck_id] = {
                "name": deck_name,
                "models": get_models_in_deck(deck_name)
            }
        return result
    except Exception:
        return {}


def find_notes(deck: str):
    return anki_connect_invoke('findNotes', {"query": f'deck:"{deck}" rated:1'})


def get_notes_info(note_ids: list, batch_size=100):
    all_notes = []
    for i in range(0, len(note_ids), batch_size):
        batch = note_ids[i:i + batch_size]
        notes = anki_connect_invoke('notesInfo', {"notes": batch})
        all_notes.extend(notes)
        print(f"Fetched {len(all_notes)}/{len(note_ids)} notes...")
    return all_notes


def get_models_in_deck(deck: str) -> dict:
    all_models = anki_connect_invoke('modelNames')
    result = {}
    for model in all_models:
        note_ids = anki_connect_invoke('findNotes', {
            "query": f'deck:"{deck}" note:"{model}"'
        })
        if note_ids:
            fields = anki_connect_invoke('modelFieldNames', {"modelName": model})
            reviewed_today_ids = anki_connect_invoke('findNotes', {
                "query": f'deck:"{deck}" note:"{model}" rated:1'
            })
            top_known_due_ids = [x for x in get_top_known_due_notes(deck, model, limit=300) if x not in reviewed_today_ids]
            result[model] = {
                "fields": fields,
                "reviewed_today_note_ids": reviewed_today_ids,
                "top_known_due_note_ids": top_known_due_ids
            }
    return result

def get_top_known_due_notes(deck: str, model: str, limit: int) -> list:
    """Returns up to `limit` note ids for the cards with the longest interval
    in this deck/model — i.e. the ones scheduled furthest into the future,
    which indicates the strongest retention / most familiar terms. Due status
    is irrelevant here: a card due today can still have a long interval, and
    a card not due for months is exactly the kind of "solid" vocabulary we want."""
    base_query = f'deck:"{deck}" note:"{model}"'

    total_candidates = anki_connect_invoke('findCards', {"query": base_query})
    if not total_candidates:
        return []

    if len(total_candidates) <= limit:
        card_ids = total_candidates
    else:
        lo, hi = 0, 3650
        card_ids = total_candidates
        while lo < hi:
            mid = (lo + hi) // 2
            query = f'{base_query} prop:ivl>={mid}'
            matched = anki_connect_invoke('findCards', {"query": query})
            if len(matched) > limit:
                lo = mid + 1
            else:
                card_ids = matched
                hi = mid
        if not card_ids:
            card_ids = anki_connect_invoke('findCards', {
                "query": f'{base_query} prop:ivl>={lo}'
            })

    cards_info = anki_connect_invoke('cardsInfo', {"cards": card_ids})
    cards_info.sort(key=lambda c: c.get('ivl', 0), reverse=True)

    seen = set()
    note_ids = []
    for card in cards_info[:limit * 2]:
        nid = card['note']
        if nid not in seen:
            seen.add(nid)
            note_ids.append(nid)
        if len(note_ids) >= limit:
            break
    return note_ids


def get_first_notes_info(deck: str, model: str, limit) -> list:
    note_ids = anki_connect_invoke('findNotes', {
        "query": f'deck:"{deck}" note:"{model}"'
    })
    note_ids = note_ids[:limit]
    if not note_ids:
        return []
    return get_notes_info(note_ids, limit)


def main():
    decks = get_decks()
    print(decks)

    # note_ids = find_notes("Deutsch: 4000 German Words by Frequency")
    # print(f"Found {len(note_ids)} notes")

    # models = get_models_in_deck("Deutsch: 4000 German Words by Frequency")
    # print(models)


if __name__ == "__main__":
    main()