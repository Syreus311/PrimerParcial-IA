# Katherin Juliana Moreno Carvajal 
# Proyecto — Emergency Control

El diseño interno de la IA está en [`design.md`](design.md) (estado, acciones,
`DROP`, batería, tamaño del espacio, estrategia de búsqueda). El enunciado
está en el `README.MD` de la raíz; las reglas del mundo, en
[`../CONTRATO.md`](../CONTRATO.md).

## Estructura

```text
project/
├── frontend/          # React + R3F — simulación 3D voxel
├── backend/           # FastAPI — POST /api/solve (agente UCS, backend/src/agent.py)
├── scenarios/         # scenario.json — fuente de verdad
├── design.md
└── README.md
```

## 1–3. Instalar dependencias, iniciar backend, iniciar frontend

Abre **dos terminales**.

### Terminal 1 — Backend

```bash
cd project/backend
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --app-dir src --port 8000
```

Comprobar: http://127.0.0.1:8000/api/health debe responder `{"status":"ok"}`.

### Terminal 2 — Frontend

```bash
cd project/frontend
npm install
npm run dev
```

Abrir: http://localhost:5173 (el proxy de Vite reenvía `/api/*` al backend en el puerto 8000).

## 4–5. Ejecutar el agente y probar una misión

Pulsa **EXECUTE PLAN**. Eso dispara `fetchPlan()` → `POST /api/solve` con el
`scenario.json` cargado, que ahora resuelve `backend/src/agent.py` (Búsqueda
de Costo Uniforme — ver `design.md`), y el frontend reproduce el plan
devuelto casilla a casilla, en el mismo orden en que el agente lo generó.

**El endpoint puede tardar del orden de 30–60 segundos en responder** con el
`scenario.json` de la demo — no es que se haya colgado. `design.md` (sección
"Formulación y tamaño del espacio") explica por qué: es una búsqueda
exhaustiva, sin ninguna heurística, sobre un problema de recolección con
capacidad de carga limitada. Mientras el backend resuelve, el navegador
queda esperando la respuesta HTTP antes de empezar a animar nada; eso es
normal, no un error.

Para probar el endpoint directamente sin el frontend:

```bash
curl -s -X POST http://127.0.0.1:8000/api/solve \
  -H "Content-Type: application/json" \
  -d @scenarios/scenario.json | python3 -m json.tool
```

Para probar con otra instancia, reemplace el JSON del `-d @...` por otro
escenario que respete el mismo esquema (ver `../CONTRATO.md`).

## 6. Interpretar el resultado

La respuesta de `/api/solve` sigue siempre este formato:

```json
{
  "solution_found": true,
  "total_cost": 80,
  "steps": [ { "op": "MOVE", "from": "Z1", "to": "Z2", "cost": 4 }, "..." ],
  "message": "UCS (uninformed, graph search) found the optimal plan in 748712 node expansions."
}
```

- `solution_found: false` + `steps: []` significa que el agente determinó
  que la misión **no tiene solución** con ese escenario (no es un timeout ni
  un error: es el caso `FAILURE` del enunciado, §2.6). El `message` indica
  cuántos nodos exploró antes de agotar el espacio de búsqueda.
- `total_cost` es la suma de los costos oficiales del escenario (no el
  número de pasos) — es el valor que el agente garantiza mínimo, según la
  estrategia UCS justificada en `design.md`.
- `steps` es el plan ya traducido al contrato cerrado (`MOVE` / `PICKUP` /
  `DROP` / `INTERACT`), listo para que el simulador del frontend lo
  reproduzca paso a paso.

En la interfaz, una vez ejecutado el plan, esto es lo que muestra cada panel
(sección "Integración visual" del enunciado):

| Dónde | Qué muestra |
|---|---|
| Escena 3D + badge `ZONE` (abajo) | Posición actual del robot |
| Panel izquierdo, `POWER CORE` | Batería actual / máxima |
| Panel izquierdo, `PAYLOAD` | Objetos que el robot lleva encima ahora mismo |
| Panel derecho, `EXECUTION LOG` + `STEP n/N` | Cada acción ejecutada y el progreso de la misión |
| Panel derecho, `ENERGY COST` | Costo acumulado (`energySpent`) y costo total del plan (`total_cost`) |
| Última línea del log | Resultado final: `MISSION COMPLETE — all stations ONLINE (spent N)` o `Plan finished but goal NOT satisfied` |

Si un paso del plan fuera ilegal según el simulador del frontend (no debería
pasar: el agente ya respeta el contrato), el log lo marca en rojo con la
razón exacta (puerta cerrada, batería insuficiente, material faltante, etc.)
y la ejecución se detiene ahí — ver `../CONTRATO.md` §6.

## Tests

Hay dos suites independientes en `backend/tests/`:

```bash
cd project/backend
# (con el venv activado)

# 1) El plan artesanal original (sin IA) sigue siendo legal — se conserva sin tocar:
python tests/test_demo_plan.py

# 2) Los 5 casos de validación del agente (Entregable 3), con escenarios
#    sintéticos pequeños — corre en menos de un segundo:
python tests/test_agent.py

# Opcional: además de los 5 casos rápidos, correr el agente contra el
# scenario.json real de punta a punta (tarda ~1 minuto):
python tests/test_agent.py --slow
```

## Contrato visual vs agente (importante)

La versión oficial y completa de este contrato (esquema JSON, acciones de `INTERACT`, reglas del mundo y costos) está en `../CONTRATO.md`, que forma parte del enunciado.

El enunciado fija **4 operaciones visuales** que el frontend entiende:

```text
MOVE | PICKUP | DROP | INTERACT
```

`REPAIR`, `ACTIVATE`, `OPEN_DOOR`, `RECHARGE` **no son ops del plan de alto nivel**: son el campo `action` dentro de un paso `INTERACT`.

Ejemplo de lo que debe devolver `/api/solve`:

```json
{ "op": "INTERACT", "target": "PANEL_A", "action": "REPAIR", "consumes": "FUSE", "cost": 2 }
```

- **Agente (`backend/src/agent.py`):** modela acciones internas propias
  (`MOVER`, `RECOGER`, `SOLTAR`, `ABRIR_PUERTA`, `REPARAR_PANEL`,
  `ACTIVAR_ESTACION`, `RECARGAR` — ver `design.md`) y las traduce a
  `MOVE`/`PICKUP`/`DROP`/`INTERACT` en el mismo momento en que genera cada
  sucesor, para que el plan que sale de `/api/solve` ya esté en formato de
  contrato.
- **Frontend / banco de pruebas:** solo ejecuta esas 4 ops. El log muestra `INTERACT REPAIR ...` para dejar claro el `op` + el `action`.

Así no hay contradicción: la capa visual no define la IA; solo anima el plan ya traducido.