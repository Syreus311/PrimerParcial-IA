# Diseño del agente

Este documento debe completarse **antes** de la implementación principal del agente.

Use sus propias palabras y notación. No reemplace este archivo por una transcripción
del enunciado. Las subsecciones existen para que no se le olvide una decisión;
usted decide el contenido.

El entorno, según las propiedades vistas en clase, es totalmente observable,
determinista, secuencial, estático, discreto y de agente único. Bajo esas
condiciones la solución es un **plan completo** y el marco correcto es la
búsqueda clásica. Justifique cada componente con ese marco (AIMA, cap. 3).

---

## Estado

### Definición formal

Escriba la tupla de estado. Cada componente debe ser una variable que el robot
necesita para saber qué podrá hacer después.

```text
s = ⟨posición, batería, inventario, objetos_suelo,entorno⟩
```
entorno = ⟨puertas_abiertas,paneles_reparados,estaciones_online⟩

- posición indica la zona actual del robot.
- batería representa la energía residual disponible.
- inventario contiene los objetos y materiales que el robot transporta actualmente.
- objetos_suelo representa los objetos y materiales disponibles en cada zona y que pueden ser recogidos.
- entorno representa los cambios persistentes realizados sobre el mundo:
    -puertas_abiertas: conjunto de puertas que ya fueron desbloqueadas.
    -paneles_reparados: conjunto de paneles que ya fueron reparados.
    -estaciones_online: conjunto de estaciones que ya fueron activadas.


### Por qué cada variable es necesaria

Criterio de clase (`Applicable`): una variable pertenece al estado **si y solo si**
dos configuraciones que difieran en ella pueden diferir en las acciones legales
futuras o en su resultado.

Pase ese filtro con cada variable. En particular:

- la **batería** forma parte de la situación física (§2.1 del enunciado);
- la **posición de los objetos** no se deduce del escenario inicial si el robot
  puede soltarlos (`DROP`);
- los cambios permanentes (puertas, paneles, estaciones) condicionan el futuro.

- posición: Indica la zona actual del robot. Es necesaria porque determina los corredores por loq ue puede desplazarse, los objetos que puede recoger y las puertas, paneles, estaciones o los puntos de recarga con los que puede interactuar
- inventario: contiene los objetos y materiales transportados actualmente. Es necesario porque abrir puertas requiere llevar la llave correspondiente, reparar paneles requiere llevar una herramienta y un material específicos, y DROP requiere que el objeto se encuentre en la carga. Además, el inventario permite comprobar si un nuevo PICKUP respetaría la capacidad máxima del robot.
-objetos:suelo: representa qué objetos y materiales permanecen disponibles en cada zona. Es necesario porque los objetos pueden cambiar de ubicación mediante PICKUP y DROP, por lo que su posición actual ya no puede deducirse únicamente de la configuración inicial del escenario. Esta información determina qué objetos pueden recogerse desde la posición actual. Los materiales equivalentes se representan mediante cantidades por tipo y no mediante identificadores individuales artificiales.
-entorno: representa los cambios persistentes producidos en el mundo y está compuesto por:
  -puertas_abiertas: es necesario conocerlas porque un corredor protegido por una puerta solamente puede utilizarse después de abrirla. Una puerta abierta permanece abierta, por lo que basta almacenar el conjunto de puertas que ya cambiaron a este estado.
  -paneles:reparados: determina qué reparaciones siguen pendientes y qué estaciones pueden cumplir sus dependencias. Un panel reparado no vuelve a dañarse durante el problema.
  -estaciones_online: determina qué estaciones todavía pueden activarse, permite comprobar dependencias entre estaciones y también es necesaria para evaluar la condición de meta, ya que la misión se expresa mediante las estaciones que deben quedar ONLINE.

### Qué información se deriva y NO se almacena

Peso de la carga, grafo de corredores, costos, capacidad, batería máxima, etc.
Si se puede calcular a partir del estado y de las constantes del escenario, no
es una variable de estado.

Por ejemplo, el peso de la carga se obtiene sumando los pesos de los objetos que lleva el robot. A partir de este valor también se puede saber cuánto espacio queda disponible para recoger otro objeto:

peso_carga(s) = suma de los pesos de los elementos del inventario

capacidad_disponible = cargo_capacity - peso_carga(s)

Por la misma razón, no es necesario guardar por separado las puertas cerradas, los paneles pendientes de reparación o las estaciones que están fuera de servicio. El estado guarda los cambios relevantes, como puertas_abiertas, paneles_reparados y estaciones_online, y la información restante se puede deducir a partir de las condiciones iniciales del escenario.

Tampoco se almacenan como parte del estado las características que permanecen constantes durante toda la misión, como el mapa de zonas y corredores, los costos de movimiento y de las demás acciones, las llaves necesarias para abrir cada puerta, las ubicaciones fijas de paneles y estaciones, los requisitos de cada reparación, el peso de cada tipo de objeto, la capacidad máxima de carga, la batería máxima y las condiciones que definen la misión.

### Qué pertenece al historial de búsqueda y no al estado físico

`g(n)`, el padre y la acción que trajo aquí describen *cómo llegó*, no *dónde
está*. Viven en el **Nodo**. Si se meten en el estado, CLOSED no puede reconocer
la misma situación física alcanzada por dos rutas.

Por eso, el estado solo debe representar la situación actual del robot y del entorno. En cambio, el nodo guarda la información necesaria para reconstruir el camino seguido hasta ese estado.

Por ejemplo, dos rutas distintas pueden llevar al robot a la misma posición, con la misma batería, inventario y condiciones del entorno. Aunque hayan llegado por caminos diferentes, siguen representando la misma situación física.

En el nodo se guarda:

Nodo = ⟨estado, padre, acción, g(n)⟩

donde g(n) representa el costo acumulado de todas las acciones realizadas desde el estado inicial hasta llegar al estado actual.

De esta manera, CLOSED puede comparar únicamente los estados físicos y evitar volver a explorar una situación que ya fue visitada.

### Cuándo dos configuraciones son el mismo estado

Materiales equivalentes por tipo (§2.2): no les ponga ids artificiales.
Estructuras canónicas (conjuntos, contadores) para que `==` y el hash coincidan
con la equivalencia física. Sin eso Graph Search explota.

Dos configuraciones se consideran el mismo estado cuando tienen la misma posición, batería, inventario, objetos en el suelo y las mismas condiciones del entorno.

En el caso de los materiales, dos unidades del mismo tipo se consideran equivalentes. Por ejemplo, si existen dos FUSE, no se representan como FUSE1 y FUSE2, sino mediante una cantidad:

FUSE: 2

De esta forma, intercambiar dos materiales iguales no crea un estado nuevo, porque físicamente la situación sigue siendo la misma.

Para evitar diferencias causadas únicamente por el orden en que se guardan los datos, se utilizarán estructuras canónicas. Por ejemplo, puertas_abiertas, paneles_reparados y estaciones_online se pueden representar como conjuntos, mientras que los materiales se representan mediante contadores por tipo.

Así, dos estados que representan exactamente la misma situación física producen la misma comparación y el mismo hash, permitiendo que CLOSED reconozca que esa configuración ya fue explorada y evitando generar nuevamente estados equivalentes.

### Relevancia: objetos que ya no cambian el futuro

Los cambios del entorno son **monótonos** (una puerta abierta no se cierra).
Pregúntese: una llave cuya puerta ya está abierta, o una herramienta cuyo panel
ya está reparado, ¿sigue distinguiendo estados si solo cambia *dónde* está en
el suelo? Si no habilita ninguna acción futura, incluirla multiplica el espacio
con permutaciones de objetos muertos. Justifique si las ignora y por qué eso
no pierde el óptimo.

Cuando un objeto ya cumplió su función y no puede habilitar ninguna acción futura necesaria, deja de ser relevante para distinguir estados.

Por ejemplo, si una llave ya abrió la única puerta para la que era necesaria, su ubicación en el suelo deja de afectar el resto del problema. Lo mismo ocurre con una herramienta cuando ya no queda ningún panel pendiente que la necesite.

En estos casos, si el objeto ya está en el suelo, su ubicación exacta puede dejar de tenerse en cuenta al comparar estados. Esto evita crear configuraciones diferentes únicamente porque un objeto que ya no sirve quedó en una zona distinta.

Sin embargo, si ese objeto todavía está en el inventario, no puede ignorarse inmediatamente, porque sigue ocupando capacidad de carga y puede ser necesario hacer DROP para liberar espacio.

Esta simplificación no pierde una solución óptima porque volver a recoger un objeto que ya no habilita ninguna acción útil solo añadiría costo y ocuparía capacidad, sin acercar al robot a la meta.

---

## Acciones

Defina las acciones **internas** del agente (nombres libres). Para cada una:
precondiciones, efectos, costo. Toda acción del mundo exige además
`batería ≥ costo`.

Puede usar una tabla:

```text
```markdown
| Acción | Precondiciones | Efectos | Costo |
|---|---|---|---|
| `MOVER(destino)` | Existe un corredor desde la posición actual hasta `destino`. Si el corredor tiene una puerta, esta debe estar abierta. | La `posición` cambia a la zona destino y se descuenta el costo de la batería. | Costo del corredor utilizado. |
| `RECOGER(objeto)` | El objeto está en `objetos_suelo` de la zona actual y recogerlo no supera la capacidad máxima del inventario. | El objeto pasa de `objetos_suelo` al `inventario` y se descuenta el costo de la batería. | `action_costs.pickup`. |
| `SOLTAR(objeto)` | El objeto se encuentra actualmente en el `inventario`. | El objeto sale del `inventario`, queda en `objetos_suelo` de la zona actual y se descuenta el costo de la batería. | `action_costs.drop`. |
| `ABRIR_PUERTA(puerta)` | El robot está en una de las zonas conectadas por la puerta, la puerta todavía está cerrada y la llave correspondiente está en el `inventario`. | La puerta se agrega a `puertas_abiertas` y se descuenta el costo de la batería. La llave no se consume. | `action_costs.interact`. |
| `REPARAR_PANEL(panel)` | El robot está en la zona del panel, el panel todavía no está reparado y el `inventario` contiene la herramienta y el material requeridos. | El panel se agrega a `paneles_reparados`, el material utilizado se elimina del inventario y se descuenta el costo de la batería. La herramienta permanece en el inventario. | `action_costs.interact`. |
| `ACTIVAR_ESTACION(estacion)` | El robot está en la zona de la estación, esta todavía no está `ONLINE` y se cumplen sus dependencias. | La estación se agrega a `estaciones_online` y se descuenta el costo de la batería. | `action_costs.interact`. |
| `RECARGAR` | El robot está en una zona con punto de recarga, la batería no está llena y tiene batería suficiente para pagar el costo. | Primero se paga el costo y después la batería se restaura hasta `battery_max`. | `action_costs.recharge`. |
```


### `Applicable` interno vs legalidad del contrato

El simulador dice cuándo un paso es **legal**. Su generador de sucesores dice
qué acciones son **relevantes para buscar**. No tienen que ser el mismo conjunto.

El contrato **permite** `DROP` en cualquier zona si el objeto está en la carga.
Si su agente genera ese `DROP` en cada estado con carga, el espacio deja de ser
«5 zonas y unas tareas» y pasa a ser «en cuál de las 5 zonas quedó cada objeto».
Eso no se arregla cambiando `cargo_capacity` ni apagando la batería: el escenario
es la fuente de verdad y el profesor probará otras instancias.

Usted puede (y se espera que) restrinja `DROP` —y cualquier otra acción— a los
casos que un plan **óptimo** podría necesitar. Justifique que ningún plan de
costo mínimo usa una acción que usted dejó de generar.

Aunque el contrato permita realizar un DROP siempre que el objeto esté en el inventario, el agente no lo generará en todos los estados. Solo se considerará cuando exista una necesidad real de liberar capacidad para recoger un objeto o material relevante que se encuentre en la zona actual y que no pueda recogerse con el espacio disponible.

Por ejemplo, si el inventario está lleno y en la zona actual existe un objeto que todavía es necesario para abrir una puerta, reparar un panel o completar alguna dependencia de la misión, Applicable(s) podrá generar acciones DROP sobre los objetos que lleva el robot para crear espacio.

Si liberar el espacio requiere soltar más de un objeto, se pueden generar varios DROP consecutivos hasta alcanzar la capacidad necesaria.

En cambio, si todavía existe espacio suficiente o no hay ningún objeto relevante pendiente de recoger en la zona actual, no se genera DROP, aunque el contrato lo permita.

Esta restricción no pierde el plan óptimo porque transportar un objeto no aumenta el costo de los movimientos. Por lo tanto, no existe beneficio en soltarlo antes de que realmente sea necesario liberar capacidad. Si un plan realiza un DROP sin necesidad de espacio, esa acción puede posponerse hasta el momento en que la capacidad sea necesaria, manteniendo el mismo costo o evitando una acción innecesaria.

El mismo criterio se aplica a las demás acciones: Applicable(s) genera únicamente acciones que sean legales según el contrato y que todavía puedan contribuir al progreso de la misión. Así se reduce el número de sucesores sin modificar las reglas físicas del escenario ni eliminar una solución de costo mínimo.

---

## Modelo de transición

```text
s  --a-->  s'     solo si a ∈ Applicable(s)
```

`Result` es determinista y parcial. Qué puede cambiar: zona, carga/suelo,
batería, entorno persistente. Qué se preserva. Si canonicaliza el estado tras
una acción, dígalo aquí.

Result(s, a) toma el estado actual y una acción aplicable, y devuelve el nuevo estado después de ejecutarla. Es determinista porque, para un mismo estado y una misma acción, el resultado siempre será el mismo. Es parcial porque solo se puede aplicar cuando la acción pertenece a Applicable(s).

Según la acción realizada, cambia únicamente la parte del estado que corresponda:

MOVER: cambia la posición y disminuye la batería según el costo del corredor.
RECOGER: el objeto pasa de objetos_suelo al inventario y disminuye la batería.
SOLTAR: el objeto pasa del inventario a objetos_suelo en la zona actual y disminuye la batería.
ABRIR_PUERTA: la puerta se agrega a puertas_abiertas y disminuye la batería.
REPARAR_PANEL: el panel se agrega a paneles_reparados, se consume el material requerido del inventario y disminuye la batería. La herramienta no se consume.
ACTIVAR_ESTACION: la estación se agrega a estaciones_online y disminuye la batería.
RECARGAR: se paga primero el costo de la acción y luego la batería queda en su capacidad máxima.

Las variables que no sean afectadas por una acción se mantienen iguales en el nuevo estado. Por ejemplo, moverse entre zonas no modifica el inventario ni cambia las puertas, paneles o estaciones.

Después de cada transición, el estado se mantiene en una forma canónica: los conjuntos no dependen del orden de sus elementos y los materiales equivalentes continúan representándose mediante cantidades. También se mantiene el criterio definido anteriormente para los objetos que ya dejaron de ser relevantes. De esta manera, dos resultados que representan la misma situación física son reconocidos como el mismo estado.

---

## Prueba de meta

```text
Goal(s) ⟺ …
```

La misión se verifica sobre el **estado final del mundo**, no sobre haber
ejecutado una lista de tareas. ¿Las puertas y los paneles son parte de la meta
o solo medios?

La meta se cumple cuando todas las estaciones indicadas en scenario.goal.stations_online se encuentran dentro de estaciones_online en el estado actual.

Goal(s) ⟺ todas las estaciones requeridas en goal están ONLINE

De forma más formal:

Goal(s) ⟺ para toda estación e ∈ scenario.goal.stations_online,
           e ∈ estaciones_online

Las puertas abiertas y los paneles reparados no son la meta por sí mismos. Son medios que pueden ser necesarios para poder llegar a ciertas zonas o cumplir las condiciones necesarias para activar las estaciones.

Por esta razón, el agente no necesita abrir todas las puertas ni reparar todos los paneles del escenario. Solo debe realizar aquellos cambios que sean necesarios para alcanzar un estado donde todas las estaciones exigidas por la misión estén ONLINE.

Esto también evita realizar acciones innecesarias que aumentarían el costo del plan sin ayudar a cumplir la meta.

---

## Función de costo

```text
g(n) = …
```

Debe ser la suma de los **costos oficiales** del escenario (no el número de
pasos). Explique por qué minimizar pasos no es lo mismo que minimizar costo
en este mundo (hay corredores baratos y caros).

El costo acumulado g(n) representa cuánto ha costado llegar desde el estado inicial hasta el estado asociado al nodo actual.

g(n) = suma de los costos de todas las acciones realizadas

Para un nodo sucesor:

g(n') = g(n) + costo(a)

Cada acción utiliza el costo definido oficialmente en el escenario. En el caso de MOVER, el costo depende del corredor utilizado, por lo que desplazarse entre dos zonas puede ser más caro que hacerlo entre otras. Las demás acciones utilizan igualmente el costo que les corresponde según el escenario.

Por esta razón, minimizar la cantidad de pasos no garantiza encontrar el plan de menor costo. Un camino con menos acciones puede utilizar corredores más costosos, mientras que otro con más acciones puede tener un costo total menor.

Por ejemplo:

Ruta A: 2 acciones → costo total 12
Ruta B: 3 acciones → costo total 9

Aunque la Ruta A tiene menos pasos, la Ruta B es mejor porque el objetivo del agente es minimizar el costo acumulado y no la cantidad de acciones realizadas.

El costo acumulado g(n) pertenece al Nodo y no al estado físico. La batería, en cambio, sí pertenece al estado porque representa la energía que le queda actualmente al robot.

---

## Estrategia de búsqueda

Elija una estrategia **vista en clase** y justifíquela con las propiedades
reales del problema (costos heterogéneos, plan de menor costo, espacio finito).

Discuta:

- completitud
- optimalidad (¿la prueba de meta se hace al extraer o al generar?)
- costo de camino
- tiempo y espacio (el `b` peligroso no es el grado del mapa: es cuántos
  `DROP`/`PICKUP` genera por estado)
- cuándo se rompen las garantías (costos 0 o negativos, estados mal
  canonicalizados, OPEN que no se vacía)

Graph Search exige una lista CLOSED sobre estados **canónicos**. Explique cómo
evita reexplorar la misma situación física.

La estrategia elegida es Búsqueda de Costo Uniforme (UCS). Se elige porque las acciones del problema tienen costos diferentes y la misión exige encontrar el plan con menor costo acumulado. A diferencia de BFS o IDS, que garantizan optimalidad cuando los costos son iguales, UCS selecciona siempre de OPEN el nodo que tenga el menor g(n).

La búsqueda es completa mientras el espacio de estados sea finito y los costos permitan que la frontera avance. En este problema se utiliza Graph Search para evitar recorrer repetidamente la misma situación física.

También es óptima porque los nodos se expanden según su costo acumulado. La prueba de meta se realiza al extraer el nodo de OPEN y no cuando se genera, ya que una meta puede generarse inicialmente mediante un camino costoso mientras todavía existe en OPEN otro camino que permita alcanzarla con menor costo.

El costo utilizado para ordenar OPEN es:

g(n) = suma de los costos de las acciones desde el estado inicial

Por lo tanto, UCS compara el costo real de los planes y no solamente su número de pasos.

Su principal desventaja es el consumo de tiempo y memoria. El factor de ramificación b no depende únicamente del número de corredores del mapa, sino también de cuántos PICKUP, DROP e interacciones genera Applicable(s). Por esta razón se restringen las acciones que no pueden aportar a un plan óptimo, especialmente los DROP innecesarios y las acciones relacionadas con objetos que ya dejaron de ser relevantes.

OPEN se implementa como una cola de prioridad ordenada por g(n) y CLOSED registra los estados ya explorados utilizando su representación canónica. Así, si dos caminos diferentes llegan a la misma situación física, el agente puede reconocerla y evitar explorar nuevamente estados equivalentes.

Las garantías de UCS dependen de las condiciones del problema. Los costos negativos romperían la lógica de expandir primero el camino más barato y no están permitidos por el contrato. Los costos de cero requieren especial cuidado porque pueden permitir secuencias sin aumento de g(n); la canonicalización y CLOSED evitan repetir indefinidamente la misma situación física. También pueden aparecer problemas si dos estados físicamente iguales tienen representaciones diferentes, ya que CLOSED dejaría de reconocerlos, o si OPEN continúa recibiendo sucesores redundantes y nunca logra vaciarse.

En el escenario proporcionado los costos de las acciones y corredores son positivos y el espacio físico es finito, por lo que UCS, junto con Graph Search, estados canónicos y un Applicable controlado, es adecuado para encontrar el plan de menor costo.

### Batería como recurso

La batería **sí** va en el estado (§2.1). Eso no implica explorar todos los
paseos que solo gastan energía. Si dos caminos llegan a la **misma**
configuración del mundo (zona, carga, suelo, entorno) y uno trae **más batería
residual** a un **costo menor o igual**, el otro no puede mejorar ningún plan
futuro: está dominado. Tratar cada nivel de batería como un mundo distinto,
sin esa observación, hace que UCS recorra detours inútiles hasta agotar
memoria. Justifique cómo CLOSED aprovecha (o no) esta dominancia.

La batería se mantiene dentro del estado porque determina qué acciones puede realizar el robot. Sin embargo, antes de conservar un nuevo estado se compara con otros que hayan llegado a la misma configuración del mundo, es decir, misma posición, inventario, objetos en el suelo y condiciones del entorno.

Por ejemplo, si se llega a la misma configuración mediante dos caminos:

Camino A: batería = 30, costo acumulado = 20
Camino B: batería = 20, costo acumulado = 25

el Camino B está dominado por el Camino A. Desde la misma situación, tener más batería permite realizar como mínimo las mismas acciones futuras, y además el Camino A ya ha costado menos. Por lo tanto, continuar explorando el Camino B no puede producir una solución de menor costo.

Para aprovechar esto, además de reconocer estados exactamente iguales, CLOSED tendrá en cuenta la configuración del mundo sin la batería y conservará las llegadas que no estén dominadas. Un nuevo estado se descarta cuando ya existe para esa misma configuración otro camino con batería mayor o igual y costo acumulado menor o igual.

En cambio, si un estado tiene más batería pero también un costo mayor, no se elimina automáticamente, porque puede existir una diferencia real entre ambos caminos y ninguno domina necesariamente al otro.

Esta comparación permite mantener la batería como parte del estado, como exige el problema, pero evita explorar recorridos que únicamente gastaron energía y aumentaron el costo sin producir ningún cambio útil en el mundo.

---

## Formulación y tamaño del espacio (obligatorio)

El mapa visible es pequeño. El espacio de estados **no** lo es, si se formula
mal. Responda con sus palabras:

1. ¿Por qué «5 zonas, ~10 objetos, capacidad 3» puede generar millones de nodos
   en un UCS ingenuo?
2. ¿Qué papel tiene `DROP` en esa explosión?
3. ¿Qué podas o abstracciones aplicó y por qué **no pierden el óptimo**
   (*sound*)?
4. ¿Por qué **no** es solución subir la capacidad, bajar las estaciones o
   ignorar la batería?

Aunque el mapa tenga pocas zonas, el estado no depende solamente de la posición del robot. También depende de la batería, qué objetos lleva en el inventario, dónde quedaron los objetos en el suelo, qué puertas están abiertas, qué paneles fueron reparados y qué estaciones están ONLINE.

Por esta razón, una misma zona puede aparecer en una gran cantidad de estados diferentes. Por ejemplo, estar en Z3 con una llave y batería 30 no es lo mismo que estar en Z3 sin esa llave o con batería 10. Al combinar todas estas posibilidades, el número de configuraciones crece rápidamente y UCS puede terminar generando una gran cantidad de nodos.

DROP tiene un papel importante en esta explosión porque permite cambiar la ubicación de los objetos. Si el agente pudiera soltar cualquier objeto en cualquier zona sin ninguna restricción, cada objeto podría terminar distribuido en diferentes lugares del mapa y cada distribución sería una configuración distinta. Además, después podría volver a recoger esos objetos y soltarlos nuevamente, generando todavía más combinaciones.

Para reducir este espacio se aplican varias restricciones y abstracciones. DROP solo se genera cuando es necesario liberar capacidad para recoger un objeto relevante. También se dejan de distinguir las ubicaciones de objetos que ya cumplieron su función y no pueden afectar ninguna acción futura. Los materiales equivalentes se representan mediante cantidades y no mediante identificadores individuales, y los estados utilizan una representación canónica para que configuraciones físicamente iguales sean reconocidas como el mismo estado.

Estas decisiones no pierden el plan óptimo porque eliminan únicamente diferencias o acciones que no pueden producir una ventaja. Soltar un objeto cuando todavía existe capacidad suficiente no reduce el costo de los movimientos, y volver a recoger un objeto que ya no es necesario solo añade costo y ocupa capacidad. De la misma manera, intercambiar dos materiales iguales no cambia físicamente el problema.

También se utiliza la dominancia de batería para evitar explorar caminos que llegan a la misma configuración con menos batería y un costo acumulado mayor o igual.

No sería correcto solucionar el problema modificando valores del escenario. Aumentar la capacidad de carga, reducir la cantidad de estaciones o ignorar la batería cambiaría las condiciones originales de la misión en lugar de mejorar la formulación del agente.

Además, el profesor puede probar el agente con otros escenarios, por lo que estos valores no pueden asumirse como fijos. El agente debe respetar siempre cargo_capacity, battery_max, las estaciones requeridas y los demás datos definidos en scenario.json.

La solución, por tanto, no consiste en hacer el problema artificialmente más fácil, sino en representar correctamente los estados y evitar explorar acciones o configuraciones que no pueden contribuir a un plan de menor costo. 
