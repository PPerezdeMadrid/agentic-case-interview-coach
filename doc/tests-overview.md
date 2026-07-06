# Test Overview

Este documento resume como estan organizados los tests del proyecto y que se evalua en cada archivo y seccion. La idea no es describir cada test individual, sino dejar clara la estructura general para que el suite siga siendo facil de mantener aunque se añadan o eliminen casos.

## Estructura general

Actualmente los tests principales estan separados por area funcional:

- `src/main/studio/tests/test_agentic_graph.py`
- `src/main/web/tests/test_workbench.py`

La separacion sigue la arquitectura del proyecto:

- `studio` cubre la logica del grafo conversacional y sus variantes.
- `web` cubre la capa de dashboard, metricas, almacenamiento y endpoints HTTP.

## `src/main/studio/tests/test_agentic_graph.py`

Este archivo valida el comportamiento del sistema de entrevista en modo `agentic` y en modo `baseline`.

### Helpers y fixtures del archivo

La parte inicial del archivo construye un caso sintetico minimo para probar el flujo sin depender de datos externos reales:

- `make_runtime_case()`: crea los bloques del caso de prueba.
- `make_runtime_bundle()`: monta escenario, caso y rubrica.
- `make_state()`: genera un estado inicial util para invocar nodos concretos del grafo.

Estos helpers permiten probar nodos y recorridos completos con datos controlados y faciles de razonar.

### Seccion `AgenticGraphTests`

Esta seccion cubre el comportamiento del grafo principal `agentic`.

Los bloques de cobertura aqui se centran en:

- Construccion del estado inicial del grafo.
- Comportamiento del nodo entrevistador en el primer turno.
- Visibilidad correcta del transcript para el candidato.
- Uso de `focus_areas` del juez para guiar el siguiente turno.
- Limite de rondas del juez y forzado de evaluacion.
- Reconstruccion de contexto cuando falta `case_prompt`.
- Ejecucion end-to-end del grafo completo, incluyendo transcript, evaluacion final y persistencia en SQLite.

En esta seccion se usan `Mock` y `patch` para aislar el LLM, la recuperacion de contexto y la persistencia, de forma que la logica del grafo se pueda verificar sin depender de servicios externos.

### Seccion `BaselineGraphTests`

Esta seccion cubre la variante `baseline`, que comparte parte de la logica del sistema pero con un flujo mas simple.

Aqui se valida principalmente:

- Inyeccion de contexto recuperado en el prompt del entrevistador baseline.
- Almacenamiento del contexto recuperado dentro del estado.
- Reconstruccion de la query cuando no existe `case_prompt`.

En resumen, esta parte asegura que el baseline siga teniendo cobertura propia y no dependa implicitamente de la cobertura del grafo agentic.

## `src/main/web/tests/test_workbench.py`

Este archivo cubre la capa web y el almacenamiento asociado al dashboard de evaluacion.

### Helpers y fixtures del archivo

La parte inicial define utilidades para crear una base SQLite temporal y poblarla con un run de ejemplo:

- `create_runs_table(db_path)`: crea las tablas necesarias del dashboard.
- `insert_sample_run(db_path)`: inserta un run sintetico con transcript, scores y trazas.

El objetivo de estos helpers es permitir tests deterministas sobre carga de runs, metricas, trazas y APIs HTTP.

### Seccion `DashboardStoreTests`

Esta seccion prueba la capa de acceso a datos y calculo de metricas en `dashboard_store.py`.

Los temas que cubre son:

- Calculo de metricas de error entre expected, model y human scores.
- Comportamiento de `exact_match_rate` en distintos escenarios.
- Tratamiento de pares no comparables o scores no numericos.
- Construccion del payload agregado de un run con expected scores, model scores, human scores y metricas.
- Construccion del payload de trazas para la vista temporal del run.

Esta seccion es la referencia principal para validar la logica numerica y de agregacion del dashboard.

### Seccion `WorkbenchAppTests`

Esta seccion prueba la capa HTTP de Flask usando `test_client()`.

Los bloques de cobertura aqui incluyen:

- Respuesta JSON de detalle de run.
- Flujo de guardado y lectura de evaluacion humana por API.
- Contrato del endpoint de evaluacion humana cuando no existe evaluacion previa.
- Respuesta de la vista o endpoint de trazas.
- Validaciones de payload invalido para la API.

Estas pruebas no se centran en HTML detallado, sino en verificar que los endpoints principales responden con la estructura esperada y que estan conectados correctamente con `dashboard_store`.

## Criterio de organizacion

La organizacion actual sigue tres ideas:

- Un archivo por subsistema grande.
- Fixtures locales y pequeñas dentro de cada archivo, para que el contexto del test sea visible cerca de donde se usa.
- Separacion interna por clases de `unittest` para distinguir entre logica de dominio, almacenamiento y capa HTTP.

## Alcance del documento

Este documento describe que se cubre en cada archivo y en cada bloque principal. No pretende ser un inventario fijo de tests, porque esa lista cambiara con la evolucion del proyecto.
