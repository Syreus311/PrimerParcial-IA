# Scenarios

Instancia de la misión que recibe el agente y el frontend.

El archivo de trabajo es `scenario.json`. Es la **fuente de verdad** de esta
demo; el profesor puede enviar otro JSON con las mismas reglas.

## Contenido del demo

- 5 zonas: CONTROL, STORAGE, WORKSHOP, GENERATOR_BAY, COMMAND_DECK
- 3 puertas corredizas (cyan / yellow / magenta) + llaves del mismo color
- 3 herramientas (MULTITOOL, SOLDERING, WIRE_CUTTER) + materiales (FUSE, CHIP, CABLE)
- 3 paneles dañados y 3 estaciones (GENERATOR, COMMAND, ARTILLERY)
- 1 cargador en WORKSHOP
- **Capacidad de carga 3** (es intencional: obliga a `DROP` reales)
- Batería inicial 55 (el plan artesanal recarga porque cuesta 99; un plan
  mejor podría o no recargar, según su costo)
- Grafo con costos distintos y rutas alternativas (apto para UCS)

## Cómo leer este mapa

Cinco zonas no quieren decir «cinco estados». Cada objeto que el robot puede
soltar tiene una posición, y `DROP` en cualquier casilla combina esas
posiciones. El plan de `demo_plan.py` usa varios `DROP` precisamente porque la
capacidad es 3: hay que hacer hueco. Si su UCS no termina, no suba la
capacidad ni borre objetos: formule mejor `Applicable` (ver enunciado §2.2 y
`design.md`).

El `meta.description` dice *Resolvable by UCS*. Lo es, con un generador de
sucesores que no trate cada `DROP` legal como una decisión distinta.
