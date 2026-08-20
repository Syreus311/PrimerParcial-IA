# Backend — Emergency Control

Python API that exposes `POST /api/solve`.

The default implementation returns a **demo plan** (no search / no AI) so the
frontend can be tested end-to-end. Students replace the solve handler with
their search agent. Do not «fix» `scenario.json` (capacity, battery, rooms)
to make UCS finish: formulate `Applicable` instead. See `project/design.md`.

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
python tests/test_demo_plan.py
```
