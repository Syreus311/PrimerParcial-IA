# CONTRATO DEL PLAN Y REGLAS DEL MUNDO

## Emergency Control — Anexo técnico del enunciado

Este documento define dos cosas:

1. el **formato exacto** del plan que su backend debe retornar en `POST /api/solve`;
2. las **reglas del mundo** que el banco de pruebas (el frontend) hace cumplir al ejecutar ese plan.

Este documento **no** define el diseño de su agente. Cómo representar el estado, qué acciones internas modelar, cómo formular la transición, la meta, el costo y la estrategia de búsqueda son decisiones suyas y constituyen la parte principal de la evaluación (ver `design.md` en el enunciado).

---

## 1. Qué es libre y qué es fijo

| Capa | Estatus |
|---|---|
| Modelo interno del agente (estados, acciones internas, transición, búsqueda) | **Libre.** Es su trabajo de diseño. |
| Plan retornado por `/api/solve` | **Fijo.** Debe cumplir este contrato al pie de la letra. |

Su agente puede modelar internamente las acciones que quiera y con los nombres que quiera. Pero el plan que emite hacia el frontend debe estar **traducido** al conjunto cerrado de operaciones de este contrato. El frontend re-ejecuta el plan paso a paso contra su propio simulador: **no confía en el plan**. Cualquier paso que no cumpla el formato o viole una regla del mundo detiene la simulación con un error visible en el log.

---

## 2. Formato de la respuesta de `/api/solve`

```json
{
  "solution_found": true,
  "total_cost": 63,
  "steps": [ ... ],
  "message": "texto opcional"
}
```

Si no existe solución, el agente debe terminar correctamente y retornar `solution_found: false` con `steps: []` (el caso `FAILURE` del enunciado).

---

## 3. Operaciones válidas (conjunto cerrado)

El plan solo puede contener estas cuatro operaciones. Cualquier otro valor de `op` es rechazado.

```text
MOVE | PICKUP | DROP | INTERACT
```

### 3.1. `MOVE` — desplazarse entre zonas adyacentes

```json
{ "op": "MOVE", "from": "Z1", "to": "Z2", "cost": 4 }
```

- `to`: zona destino (obligatorio). `from`: zona origen (opcional; si se incluye, debe coincidir con la zona actual del robot).
- Solo se puede mover entre zonas conectadas por un corredor del escenario. No hay teletransporte ni movimientos multi-zona en un solo paso.

### 3.2. `PICKUP` — recoger un objeto de la zona actual

```json
{ "op": "PICKUP", "item": "KEY1", "cost": 1 }
```

- Llaves y herramientas se referencian por su `id` (`KEY1`, `MULTITOOL`, ...).
- Los materiales se referencian por su **tipo** (`FUSE`, `CHIP`, `CABLE`), no por identificadores individuales.

### 3.3. `DROP` — dejar un objeto en la zona actual

```json
{ "op": "DROP", "item": "KEY1", "cost": 1 }
```

- El objeto queda en el suelo de la zona actual y puede recogerse después.
- El simulador **no** le prohíbe soltar en una zona donde no hace falta el hueco. Esa holgura es física, no una instrucción de diseño: si su búsqueda trata cada `DROP` legal como un sucesor, combinará las posiciones de todos los objetos y no terminará en tiempo de examen. El agente puede generar menos `DROP` que los que el contrato aceptaría, siempre que el plan óptimo siga siendo alcanzable. Detalle en el enunciado §2.2 y en `design.md`.

### 3.4. `INTERACT` — operar sobre un elemento del entorno

`INTERACT` admite **exactamente cuatro** valores en el campo `action`. Cualquier otro valor es rechazado con `Unknown INTERACT action`.

| `action` | `target` | Campos adicionales | Ejemplo |
|---|---|---|---|
| `OPEN_DOOR` | id de puerta | — | `{ "op": "INTERACT", "target": "DOOR1", "action": "OPEN_DOOR", "cost": 2 }` |
| `REPAIR` | id de panel | `consumes`: tipo de material | `{ "op": "INTERACT", "target": "PANEL_A", "action": "REPAIR", "consumes": "FUSE", "cost": 2 }` |
| `ACTIVATE` | id de estación | — | `{ "op": "INTERACT", "target": "GENERATOR", "action": "ACTIVATE", "cost": 2 }` |
| `RECHARGE` | id de cargador | — | `{ "op": "INTERACT", "target": "CHARGER_1", "action": "RECHARGE", "cost": 3 }` |

Nombres como `INSTALL_FUSE` o `REPAIR_COOLING` (ejemplos del enunciado) son **acciones internas** válidas dentro de su agente, pero **no** son valores válidos de `action`: deben traducirse a las operaciones de esta tabla antes de emitir el plan.

---

## 4. Reglas del mundo

El simulador rechaza cualquier paso que viole estas reglas. Son las leyes físicas del entorno; conocerlas es necesario para planear, pero no sustituye el diseño del agente.

### Movimiento

- Un `MOVE` falla si no existe corredor entre las dos zonas.
- Un `MOVE` falla si el corredor tiene una puerta y esa puerta no está `OPEN`.

### Batería

- Toda operación consume batería según su costo. Un paso falla si la batería disponible es menor que su costo.
- `RECHARGE` restaura la batería a su capacidad máxima, pero su propio costo se paga **antes** de recargar: se necesita batería suficiente para ejecutarlo.
- `RECHARGE` falla si la batería ya está llena, o si en la zona actual no hay cargador ni estación de recarga.

### Carga

- `PICKUP` falla si el objeto no está en la zona actual, o si el peso total del payload excedería la capacidad del robot.
- `DROP` falla si el objeto no está en el payload.

### Puertas

- `OPEN_DOOR` falla si el robot no está en una de las dos zonas que conecta la puerta, si la puerta ya está abierta, o si la llave correspondiente no está **en el payload** en ese momento.
- Una vez abierta, la puerta permanece abierta.

### Reparaciones

- `REPAIR` falla si el robot no está en la zona del panel, si el panel ya está reparado, si la herramienta requerida no está en el payload, o si el material indicado en `consumes` no es el requerido o no está en el payload.
- Al reparar, el **material se consume** (desaparece del payload); la **herramienta no se consume** y puede reutilizarse.

### Activaciones

- `ACTIVATE` falla si el robot no está en la zona de la estación, si la estación ya está `ONLINE`, o si no se cumplen sus dependencias: los paneles requeridos deben estar reparados y las estaciones requeridas deben estar `ONLINE`.

### Meta

- La misión se verifica sobre el **estado final del mundo** (las estaciones indicadas en `goal` deben quedar `ONLINE`), no sobre haber ejecutado una lista de pasos.

---

## 5. Costos oficiales

Los costos no se inventan: provienen del escenario (`scenario.json`).

| Operación | Costo oficial |
|---|---|
| `MOVE` | El `cost` del corredor utilizado |
| `PICKUP` | `action_costs.pickup` |
| `DROP` | `action_costs.drop` |
| `INTERACT` (`OPEN_DOOR`, `REPAIR`, `ACTIVATE`) | `action_costs.interact` |
| `INTERACT` (`RECHARGE`) | `action_costs.recharge` |

El campo `cost` de cada paso y el `total_cost` del plan deben corresponder a estos valores oficiales. En la revisión se auditará esta correspondencia: un plan cuyos costos no coincidan con los del escenario se considera inválido.

---

## 6. Advertencias finales

- **El escenario es la fuente de verdad.** No codifique en su agente los ids, costos ni cantidades del ejemplo: el profesor probará con instancias distintas (posiciones, costos, recursos, puertas y existencia de solución pueden cambiar). Las reglas de este contrato se mantienen; los valores no.
- **No «facilite» la demo para que UCS acabe.** Subir `cargo_capacity`, ignorar la batería o recortar estaciones resuelve *esta* instancia y falla la siguiente. El arreglo está en el modelo (estado canónico, `Applicable` más estricto que el simulador cuando se puede justificar).
- **`DROP` es el cuello de botella habitual.** Cinco zonas no son un espacio pequeño si cada objeto puede quedar en cualquiera de ellas. Formule cuándo soltar es una *decisión*, no un paseo.
- **El log del frontend es su herramienta de depuración.** Cada paso rechazado indica la razón exacta (puerta cerrada, batería insuficiente, material faltante, etc.).
- Un plan que el frontend ejecuta completo no implica nota completa: la evaluación principal es el diseño del agente documentado en `design.md` y su correspondencia con la implementación.
