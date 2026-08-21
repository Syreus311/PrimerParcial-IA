# Backend — Emergency Control

Python API that exposes `POST /api/solve`.

`POST /api/solve` is served by `src/agent.py` — a Uniform-Cost Search agent
(Graph Search, no heuristics; see `project/design.md` for the full
justification and `agent.py`'s module docstring for the implementation
notes). It can take on the order of 30–60 seconds to answer against the
demo `scenario.json`: that is expected, not a hang (see `project/README.md`,
section 4–5). Do not «fix» `scenario.json` (capacity, battery, rooms) to make
it faster — formulate `Applicable` instead. `src/demo_plan.py` is kept only
as the original hand-written plan used by `tests/test_demo_plan.py`; it is
no longer what `/api/solve` returns.

## Run

```bash
cd project/backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --app-dir src --port 8000
```

Or from `backend/src`:

```bash
cd project/backend/src
uvicorn main:app --reload --port 8000
```

## Tests

```bash
cd project/backend

# original hand-written plan (kept as-is, still legal)
python tests/test_demo_plan.py

# the agent's 5 required validation cases (synthetic scenarios, <1s)
python tests/test_agent.py

# optional: also run the agent against the real scenario.json end-to-end (~1 min)
python tests/test_agent.py --slow
```