# UNIVERSIDAD DE LA SABANA — FACULTAD DE INGENIERÍA

## Fundamentos de Inteligencia Artificial — Semestre 2026-2

# PRIMER PARCIAL

## Planificador Autónomo de Operaciones Críticas

**Modalidad:** Individual
**Tiempo disponible:** 3 horas
**Tiempo esperado de resolución:** aproximadamente 90 minutos
**Uso de herramientas de IA:** Permitido

---

# 1. PROPÓSITO DEL PARCIAL

En este parcial no se evaluará únicamente la capacidad de escribir código.

Se evaluará la capacidad de **diseñar un agente racional y convertir una descripción de un entorno en un problema de búsqueda correctamente formalizado**.

Las herramientas de IA pueden utilizarse para acelerar la implementación, construir componentes de software, generar interfaces, crear pruebas y resolver problemas de infraestructura.

Sin embargo, las decisiones fundamentales de Ingeniería de IA deberán ser diseñadas, justificadas y defendidas por el estudiante.

El agente debe ser coherente con los conceptos trabajados en clase: agentes racionales, PEAS, propiedades de los entornos, formulación de problemas, estados, acciones, modelo de transición, prueba de meta, costo de camino, búsqueda en grafos y estrategias de búsqueda estudiadas durante el curso.

---

# 2. EL ESCENARIO: EMERGENCY CONTROL

Una instalación experimental ha sufrido una falla en cadena.

Se ha desplegado un robot autónomo de mantenimiento para restaurar los sistemas críticos antes de que la instalación quede fuera de operación.

La instalación está compuesta por varias zonas conectadas mediante corredores.

El robot puede desplazarse por la instalación y ejecutar distintas operaciones sobre los elementos del entorno.

La misión debe resolverse automáticamente mediante un plan de acciones.

## 2.1. Batería

El robot posee una cantidad limitada de batería.

Cada desplazamiento consume una cantidad de energía determinada por el corredor utilizado.

Algunas zonas poseen estaciones de recarga.

Recargar devuelve la batería a su capacidad máxima.

La batería forma parte de la situación física del robot: dos configuraciones idénticas salvo por su nivel de batería representan situaciones diferentes cuando las acciones futuras pueden cambiar.

Eso no obliga a explorar todos los paseos que solo gastan energía. Si dos caminos llegan al mismo mundo (misma zona, misma carga, mismo entorno) y uno trae más batería a un costo menor o igual, el otro está dominado: no puede mejorar el resto del plan. Graph Search puede usar esa observación en CLOSED.

## 2.2. Capacidad de transporte

El robot tiene una capacidad física máxima de transporte.

Los materiales poseen propiedades conocidas de peso o capacidad.

Los objetos del mismo tipo que sean declarados equivalentes en el escenario no deben distinguirse artificialmente mediante identificadores individuales.

El robot puede recoger elementos y, cuando sea necesario para continuar la misión, puede dejarlos temporalmente en una zona.

**Advertencia de formulación (léala antes de implementar):** el contrato permite `DROP` en cualquier zona. Eso no significa que su agente deba *generar* `DROP` como sucesor en cada estado en el que el robot lleva algo. Si lo hace, el espacio de estados deja de ser «un mapa de cinco zonas» y pasa a ser la combinatoria de **dónde quedó cada objeto**. UCS no es lento porque el puzzle sea enorme: es lento cuando `Applicable` es demasiado generoso. Restringir qué `DROP` (y qué `PICKUP`) se generan, **sin perder el plan de menor costo**, es parte del diseño del agente — no se «arregla» subiendo `cargo_capacity` en `scenario.json` ni apagando la batería. El profesor probará instancias distintas con las mismas reglas.

## 2.3. Materiales y herramientas

Existen materiales consumibles y herramientas reutilizables.

Los materiales se consumen al realizar determinadas operaciones.

Las herramientas no se consumen al utilizarlas.

Algunas operaciones requieren simultáneamente herramientas, materiales y condiciones específicas del entorno.

## 2.4. Estado del entorno

Algunas acciones modifican permanentemente el entorno.

Por ejemplo, una operación puede:

* activar un sistema;
* desbloquear una puerta;
* cambiar el estado de un equipo;
* habilitar una estación;
* hacer disponible una nueva operación.

Estos cambios pueden afectar las acciones legales disponibles posteriormente.

## 2.5. Dependencias

Las operaciones pueden depender de otras operaciones previamente realizadas.

Por ejemplo, una operación de reemplazo puede requerir que un sistema haya sido desconectado previamente.

Las dependencias forman parte de las reglas del entorno.

## 2.6. Objetivo

El agente debe producir un plan que conduzca desde el estado inicial hasta un estado que satisfaga **todas las condiciones de la misión**.

El objetivo no debe interpretarse automáticamente como "ejecutar una lista de tareas"; debe verificarse sobre el estado final del mundo.

Cuando existan varios planes válidos, el agente debe preferir el plan con **menor costo acumulado**.

El costo de un plan es la suma de los costos de las acciones que lo componen, con costos no negativos.

Si no existe ningún plan válido, el agente debe retornar `FAILURE`.

## 2.7. Reglas del mundo

Las reglas precisas del entorno (precondiciones que el simulador hace cumplir, formato exacto del plan y costos oficiales) están especificadas en el documento **`CONTRATO.md`**, que forma parte de este enunciado.

El contrato define lo que es **fijo**: el conjunto cerrado de operaciones que acepta el banco de pruebas y las condiciones bajo las cuales un paso es legal.

Lo que sigue siendo **libre** —y es el objeto principal de la evaluación— es el diseño del agente: la representación del estado, el conjunto de acciones internas, el modelo de transición, la prueba de meta, la función de costo y la estrategia de búsqueda.

Hay una distinción que el curso enfatiza y que aquí es crítica:

```text
legal según el simulador  ≠  relevante para buscar
```

El banco de pruebas rechaza un paso ilegal. Su agente, al generar sucesores, puede omitir acciones que el contrato *permitiría* si puede justificar que **ningún plan óptimo** las usa. Esa es una decisión de formulación, no un atajo sobre una instancia.

---

# 3. REPOSITORIO BASE

El profesor entregará un repositorio inicial que ya contiene la estructura general del proyecto, una interfaz web funcional y la carpeta `backend/`.

La estructura esperada es:

```text
project/
├── frontend/
│   ├── src/
│   ├── public/
│   └── ...
│
├── backend/
│   ├── src/
│   ├── tests/
│   └── ...
│
├── scenarios/
│   └── scenario.json
│
├── design.md
└── README.md
```

El estudiante **no necesita construir desde cero el frontend ni crear la carpeta `backend/`**.

La tarea principal consiste en diseñar e implementar el agente dentro del backend y conectarlo con la aplicación existente.

La organización interna de `backend/` puede modificarse cuando sea necesario.

---

# 4. ENTREGABLE 1 — DISEÑO DE IA

## `design.md`

Este archivo debe existir antes de comenzar la implementación principal del agente.

Debe explicar, con sus propias palabras y notación, las siguientes decisiones.

`project/design.md` ya trae las **subsecciones** que se espera cubrir (definición formal, variables necesarias, qué se deriva, nodo vs estado, equivalencia, relevancia, `Applicable` vs contrato, dominancia de la batería, tamaño del espacio). Complételas; no las borre para pegar el enunciado.

## 4.1. Estado

Defina formalmente qué información representa un estado.

Explique:

* qué variables forman parte del estado;
* por qué cada una es necesaria;
* qué información puede derivarse de otras variables;
* qué información pertenece al historial de búsqueda pero no al estado físico;
* cuándo dos configuraciones deben considerarse el mismo estado.

Su representación debe ser suficientemente completa para determinar correctamente qué acciones pueden realizarse en el futuro.

## 4.2. Acciones

Defina las acciones que puede realizar el agente.

Para cada acción indique:

* precondiciones;
* efectos;
* costo.

El conjunto de acciones internas es libre.

Preste atención a `DROP`. En el mundo es legal casi siempre; en la búsqueda, generar todas las colocaciones posibles de objetos es lo que hace inviable UCS. En `design.md` debe quedar escrito **cuándo** su agente genera un `DROP` y por qué esa restricción no pierde el óptimo.

## 4.3. Modelo de transición

Explique cómo una acción legal transforma:

[
s -> s'
]

y qué información del mundo puede cambiar como consecuencia.

## 4.4. Prueba de meta

Defina formalmente:

[
Goal(s)
]

y explique por qué representa la condición real de éxito de la misión.

## 4.5. Función de costo

Defina:

[
g(n)
]

como el costo acumulado desde el estado inicial hasta el nodo actual.

Explique por qué su función de costo representa correctamente qué significa para este agente encontrar una solución "mejor".

## 4.6. Estrategia de búsqueda

Seleccione una estrategia de búsqueda estudiada en clase y justifique su elección considerando las propiedades del problema.

La justificación debe discutir, cuando corresponda:

* completitud;
* optimalidad;
* costo de camino;
* tiempo;
* espacio;
* condiciones bajo las cuales las garantías de la estrategia dejan de cumplirse.

La elección debe estar sustentada por las características reales del entorno y de la misión, no solamente por una definición del algoritmo.

El tiempo y el espacio de UCS dependen del **factor de ramificación que usted genera**, no del número de habitaciones del mapa. Si la búsqueda no termina, el primer sospechoso es `Applicable` (en particular `DROP` y los objetos que ya no sirven), no el algoritmo ni el JSON de la demo.

---

# 5. ENTREGABLE 2 — AGENTE

El backend deberá exponer:

```text
POST /api/solve
```

El endpoint recibirá el escenario y deberá retornar:

1. si existe solución;
2. el plan de acciones;
3. el costo total del plan;
4. información suficiente para que el frontend pueda visualizar la ejecución.

El diseño interno de las acciones es libre.

La solución debe mantener separadas:

```text
modelo interno de IA
```

y

```text
representación visual utilizada por el frontend
```

El frontend proporcionado reconoce las siguientes operaciones visuales:

```text
MOVE
PICKUP
DROP
INTERACT
```

El significado interno de una acción es responsabilidad del estudiante.

Por ejemplo, una acción interna como:

```text
INSTALL_FUSE
OPEN_DOOR
REPAIR_COOLING
ACTIVATE_GENERATOR
RECHARGE
```

puede representarse visualmente mediante una o varias de las operaciones disponibles.

**Importante:** esos nombres son ejemplos de acciones *internas* del agente, no valores aceptados por el frontend. El plan retornado por `/api/solve` debe estar traducido al contrato cerrado especificado en `CONTRATO.md` (las cuatro operaciones visuales y, dentro de `INTERACT`, únicamente las acciones allí enumeradas). Un plan que no cumpla el contrato será rechazado por el banco de pruebas.

La capa visual no debe determinar la lógica del agente.

---

# 6. ENTREGABLE 3 — VALIDACIÓN

La solución deberá incluir pruebas que demuestren al menos las siguientes propiedades.

## Caso 1 — Estados equivalentes

Dos configuraciones físicamente equivalentes deben producir el mismo estado lógico, aunque hayan sido generadas mediante historias diferentes.

## Caso 2 — Información relevante

Dos configuraciones que difieran en información que puede cambiar las acciones futuras deben mantenerse como estados diferentes.

## Caso 3 — Costos diferentes

Debe existir al menos una instancia donde la solución con menor cantidad de acciones no sea la solución de menor costo.

La estrategia seleccionada debe comportarse de acuerdo con la propiedad que el estudiante afirmó en `design.md`.

## Caso 4 — Sin solución

El agente debe terminar correctamente y devolver:

```text
FAILURE
```

cuando la misión no pueda completarse.

No se aceptará una ejecución que quede atrapada indefinidamente explorando el espacio de estados.

## Caso 5 — Rutas alternativas

Debe existir al menos una situación en la que puedan alcanzarse las mismas condiciones del mundo mediante diferentes rutas.

La solución debe manejar correctamente esas rutas y conservar la alternativa que corresponda a la estrategia de búsqueda seleccionada y a su función de costo.

---

# 7. ENTREGABLE 4 — README

El repositorio debe incluir instrucciones suficientes para:

1. instalar dependencias;
2. iniciar el backend;
3. iniciar el frontend;
4. ejecutar el agente;
5. probar una misión;
6. interpretar el resultado.

El proyecto debe poder ser ejecutado por el profesor siguiendo únicamente estas instrucciones.

---

# 8. INTEGRACIÓN VISUAL

La aplicación debe permitir observar el resultado del agente.

Como mínimo debe mostrar:

* posición del robot;
* batería;
* progreso de la misión;
* acciones ejecutadas;
* resultado final;
* costo acumulado del plan.

El estudiante puede utilizar IA para mejorar la experiencia visual, generar componentes React, animaciones, visualizaciones o elementos gráficos.

También puede incorporar assets adicionales cuando estos sean compatibles con el tiempo y alcance del parcial.

La calidad visual no sustituye la correctitud del agente.

---

# 9. USO DE IA

El uso de herramientas de IA está permitido.

Se pueden utilizar para:

* escribir código;
* depurar;
* generar componentes frontend;
* crear tests;
* producir assets;
* estructurar la API;
* documentar el software;
* resolver problemas de configuración;
* mejorar la experiencia visual.

No se exige que el estudiante programe manualmente cada línea.

La responsabilidad del estudiante está en **decidir qué debe construir el sistema, comprobar que la implementación corresponde al diseño de IA entregado y justificar sus decisiones fundamentales**.

Durante la revisión del parcial, el estudiante deberá poder explicar cualquier decisión importante relacionada con el modelo del agente.

---

# 10. RÚBRICA

## A. Ingeniería de IA — 60%

### Modelado del estado — 20%

Se evalúa:

* suficiencia de la representación;
* ausencia de información innecesariamente redundante;
* correcta identificación de estados equivalentes;
* tratamiento de información persistente del entorno;
* capacidad de utilizar el estado para determinar correctamente las acciones futuras.

### Acciones y transición — 15%

Se evalúa:

* precondiciones;
* efectos;
* legalidad de acciones;
* coherencia del modelo de transición;
* consistencia entre el modelo matemático y la implementación;
* tratamiento de `DROP` y de acciones legales pero irrelevantes para el óptimo (factor de ramificación).

### Meta y costo — 10%

Se evalúa:

* definición correcta de `Goal(s)`;
* definición correcta del costo acumulado;
* consistencia entre el objetivo de la misión y la función de costo.

### Elección de búsqueda — 10%

Se evalúa:

* selección del algoritmo;
* justificación;
* completitud;
* optimalidad;
* tiempo;
* espacio.

### Justificación técnica — 5%

Se evalúa la capacidad de explicar por qué la representación elegida es suficiente para determinar el futuro relevante del agente y por qué diferentes representaciones producen o no producen estados equivalentes.

---

## B. Implementación del agente — 25%

Se evalúa:

* funcionamiento correcto;
* generación de sucesores;
* manejo correcto de estados;
* manejo de ciclos y estados repetidos;
* reconstrucción del plan;
* detección de fallo;
* consistencia entre el comportamiento observado y el diseño documentado.

No se exige una estructura de datos específica.

Lo que se evalúa es el comportamiento correcto del agente y la coherencia de su implementación con el diseño presentado.

---

## C. Integración y mini-simulación — 15%

Se evalúa:

* comunicación backend/frontend;
* visualización del plan;
* ejecución de la simulación;
* claridad de la interfaz;
* correcta traducción entre las acciones internas del agente y las operaciones visuales.

La interfaz no necesita ser sofisticada.

Un proyecto funcional y claro obtiene todo el crédito de esta sección.

---

# 11. CRITERIO FUNDAMENTAL DE EVALUACIÓN

Un agente no obtiene crédito completo simplemente por encontrar una solución para la instancia visible.

La solución debe demostrar que el estudiante diseñó correctamente el **modelo general del problema**.

El profesor podrá probar el agente con instancias adicionales que cambien:

* posiciones iniciales;
* costos;
* recursos;
* configuración del entorno;
* disponibilidad de acciones;
* existencia de soluciones.

Estas instancias podrán contener situaciones que no aparezcan explícitamente en el ejemplo principal.

El objetivo es comprobar que el agente está resolviendo el problema de IA y no simplemente reproduciendo una secuencia de acciones para una instancia particular.

---

# 12. RESULTADO ESPERADO

Un buen proyecto no necesita ser grande.

Se espera un sistema pequeño pero completo:

```text
Descripción del mundo
        ↓
Modelo de estado
        ↓
Acciones legales
        ↓
Transición
        ↓
Estrategia de búsqueda
        ↓
Plan
        ↓
Backend
        ↓
Simulación web
```

La IA puede acelerar cada etapa de implementación.

La parte que se evalúa principalmente es la capacidad del estudiante para **diseñar correctamente el agente, justificar sus decisiones y comprobar que la implementación realmente corresponde al modelo propuesto**.
