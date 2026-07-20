# Evaluación de agentes: Judge e Interviewer, agentic vs baseline

## 0. Arquitectura evaluada (para entender las diferencias de resultados)

- **Agentic**: grafo con nodos separados — `interviewer_node` (hace las preguntas) y
  `judge_node` (decide si hay evidencia suficiente y evalúa). Cada uno tiene su propio
  prompt y su propio golden set.
- **Baseline**: un único nodo que fusiona interviewer + judge + eval en una sola llamada
  (`baseline_node`). No existe un "judge" separado en baseline — su equivalente a
  `ready_for_judge` es el campo `ready_for_evaluation`, y su equivalente a "el judge decide
  parar" es que el propio nodo elija `action: "evaluate"`. `enough_evidence` en el estado
  de baseline se deriva 1:1 de `ready_for_evaluation`.
- **Modelos usados** (ver también memoria `llm_role_architecture`):
  - Agentic: judge en OpenRouter (Llama-3.3-70B-Instruct); interviewer/candidate/feedback
    en LM Studio local.
  - Baseline: todo (`candidate_llm`, `judge_llm`, `interviewer_llm`) apunta al mismo
    `judge_llm_server` (OpenRouter), no hay separación de roles.
- Tanto el **Interviewer** como el **Judge** tienen una comparación agentic-vs-baseline
  directa: en los dos casos baseline se evalúa **reutilizando los mismos fixtures**
  (transcripciones + categoría + etiqueta esperada) que la arquitectura agentic, pero cada
  arquitectura genera su predicción con su propia llamada real e independiente al LLM sobre
  su propio prompt renderizado (`node._build_interviewer_messages` /
  `baseline._build_baseline_messages`). Compartir el fixture de entrada no hace que las dos
  mediciones sean la misma medición: son dos llamadas a modelos/prompts distintos, evaluadas
  contra la misma etiqueta esperada para poder compararlas de forma justa. El Judge no tenía
  antes esta comparación porque baseline no tiene un nodo judge al que apuntar directamente;
  se añadió el 2026-07-18 (sección 1bis).

---

## 1. Evaluación del Judge (agentic)

**Qué mide**: si `judge_node` acierta `enough_evidence` (¿el candidato cubrió todas las
etapas que pide el caso?) — **cobertura, no calidad** de las respuestas.

- **Cómo se construye el golden set**:
  - `build_judge_golden_set_worldcup.py` genera cada fila llamando al `judge_node` real
    con `judge_llm` mockeado y el RAG forzado a vacío, y capturando el `SystemMessage`
    exacto que se le mandaría al LLM (columna `judge_input`).
  - Resultado: `database/node_eval/judge_eval/judge_golden_set_worldcup.csv`, 70 filas
    sobre un único caso (World Cup), cada una etiquetada con `category` y
    `expected_enough_evidence`.
- **Cómo se ejecuta**: `run_judge_golden_set.py` manda cada `judge_input` al judge LLM
  real y compara la salida con la etiqueta esperada.
  ```
  python main/studio/node_eval/judge_eval/run_judge_golden_set.py   # o:
  make judge-eval [GOLDEN_SET=worldcup] [LIMIT=<n>]
  ```
  - Resultados cacheados en `judge_golden_set_worldcup_results.json` (no se recalculan al
    cargar la página — se ven en **Agents > Judge** del workbench).
- **Categorías** (una por fila, agrupadas en dos bloques):
  - **Esperado `False`** (evidencia incompleta): `INCOMPLETE_COVERAGE` (nunca llegó a un
    elemento obligatorio -- exhibit, sección cuantitativa, sección creativa, o
    directamente no pasó de la apertura), `UNFINISHED_ANALYSIS` (el análisis -estructura,
    síntesis de datos o un cálculo- arrancó pero se queda a medias), `PREMATURE_CONCLUSION`
    (recomendación/veredicto en frío, antes de hacer el trabajo), `NON_RESPONSIVE` (no
    responde lo que se le pregunta: se va por las ramas, da rodeos, ignora la pregunta),
    `EVIDENCE_MISREAD` (sí usó la evidencia, pero la entendió/leyó mal).
  - **Esperado `True`** (evidencia suficiente, aunque la ejecución sea floja):
    `FULL_COVERAGE_CLEAN` (todas las etapas, ejecución limpia -fuerte o
    eficiente/comprimida-), `FULL_COVERAGE_MESSY_PROCESS` (todas las etapas, pero el
    camino fue flojo, con redirecciones, o largo/iterativo), `FULL_COVERAGE_CONTENT_FLAW_ATTEMPTED`
    (todas las etapas, pero el contenido tiene un fallo -math mal resuelto, o recomendación
    sin riesgos/next steps-: gap de scoring, no de cobertura), `FULL_COVERAGE_HALLUCINATED_DATA`
    (todas las etapas; el candidato inventa un dato no soportado por el caso).

  > **Nota:** esta taxonomía (9 categorías: 5 `False` + 4 `True`) sustituye a la anterior
  > de 17 categorías (`OPENING_ONLY`, `CREATIVE_SKIPPED`, `FULL_COVERAGE_STRONG`, etc.) el
  > 2026-07-19, tras eliminar el bloque creativo de los casos 03/04.
- **Resultado**: pendiente — hace falta un run nuevo (`make judge-eval GOLDEN_SET=worldcup`,
  con LM Studio arriba) contra la taxonomía y el golden set actuales (59 filas, sin bloque
  creativo).

---

## 1bis. El mismo golden set del Judge, corrido contra baseline (nuevo, 2026-07-18)

Baseline no tiene un `judge_node` propio, pero su nodo fusionado decide `enough_evidence`
exactamente igual: lo deriva 1:1 del booleano `ready_for_evaluation` que el LLM devuelve
en cada turno. Para comparar de forma justa se construyó `build_baseline_judge_golden_set.py`,
que **reutiliza literalmente las mismas 70 transcripciones/categorías/etiquetas** del golden
set del judge (importa `ITEMS` de `build_judge_golden_set_worldcup.py`, no las copia) y
renderiza el prompt real de baseline (`baseline._build_baseline_messages`) para cada una:

- `turn_index` se fija en `2` para las 70 filas (ni turno final ni presupuesto agotado),
  para que la decisión sea el juicio genuino del modelo y no el forzado por presupuesto de
  turnos (`MAX_BASELINE_TURNS`) — mismo criterio de diseño que el golden set del judge, que
  fija `judge_round=0` siempre para no disparar el override de `MAX_JUDGE_ROUNDS`.
- Las columnas de salida (`expected_ready_for_judge`, `baseline_input`) coinciden con las
  que el runner genérico `run_baseline_golden_set.py` ya sabe graduar (mismo mecanismo que
  usan los otros 4 golden sets de baseline), así que no hizo falta un runner nuevo:
  ```
  python -m main.studio.node_eval.baseline_eval.build_baseline_judge_golden_set
  make baseline-eval BASELINE_GOLDEN_SET=worldcup
  ```
  Resultado cacheado en `baseline_golden_set_worldcup_results.json`.

### Resultado

Pendiente — igual que en la sección 1, hace falta repetir la corrida (`make baseline-eval
BASELINE_GOLDEN_SET=worldcup`, junto con `make judge-eval GOLDEN_SET=worldcup` de la
sección 1) contra el golden set actual antes de poder comparar agentic vs baseline con
cifras vigentes.

---

## 2. Evaluación del Interviewer — agentic vs baseline

**Qué mide**: si el nodo que hace las preguntas se comporta según las reglas de su propio
prompt, usando **exactamente los mismos 75 fixtures** (mismo caso World Cup, mismo
transcript, misma categoría esperada) para ambas arquitecturas — así la comparación es
directa. Son 4 CSVs por arquitectura (interviewer y baseline), construidos por
`build_interviewer_golden_sets.py` / `build_baseline_golden_sets.py` (baseline **importa**
los mismos `SOCRATIC_ITEMS`/`EVIDENCE_ITEMS`/`GUARDRAIL_ITEMS`/`TURN_CONTROL_ITEMS` del
módulo del interviewer, no los copia — mismo patrón que 1bis usa para el Judge).

- **Cómo se construye cada fila**: se llama a la función pura y sin efectos secundarios
  que arma el prompt real (`node._build_interviewer_messages` /
  `baseline._build_baseline_messages`), con `focus_areas`/RAG forzado a vacío, y se
  guarda el `SystemMessage` exacto que recibiría el LLM.
- **Cómo se ejecuta**: `run_interviewer_golden_set.py` / `run_baseline_golden_set.py`
  mandan ese input al LLM real (`invoke_json_llm` con el schema `InterviewerMove` /
  `BaselineTurnOutput`), parsean la salida, y gradúan cada fila contra las columnas
  `expected_*` / `must_contain` / `must_not_contain` / `forbidden_substrings` que tenga.
  Cada arquitectura hace su propia llamada real al LLM sobre su propio prompt renderizado
  — compartir el fixture de entrada no hace que las dos mediciones sean la misma medición
  (mismo razonamiento que en la sección 0).
  ```
  make interviewer-eval [INTERVIEWER_GOLDEN_SET=evidence_handling] [LIMIT=<n>]
  make baseline-eval    [BASELINE_GOLDEN_SET=evidence_handling]    [LIMIT=<n>]
  ```
  - Para `socratic_function` hace además una **segunda llamada** a un LLM juez
    independiente (`judge_llm_server`, no el interviewer/baseline mismo, para evitar
    self-assessment bias) que clasifica la pregunta generada en la taxonomía de 3 vías.
  - Resultados cacheados en `*_results.json`, visibles en **Agents > Interviewer** y
    **Agents > Baseline**.

### Las 4 categorías (mismas para interviewer y baseline)

1. **`socratic_function`** (20 filas) — ¿qué función socrática le toca a la afirmación del
   candidato? Clasificación LLM-juez contra 4 etiquetas:
   - `clarity`: la afirmación es vaga ("el coste está mal") → pedir precisión.
   - `premise_testing`: el candidato asume/prioriza/concluye algo sin evidencia →
     preguntar en qué se basa.
   - `perspective_testing`: el candidato razona desde un solo lado, ignorando una
     consecuencia o un ángulo alternativo → introducir el lado que falta.
   - `others`: ninguna de las anteriores encaja.
2. **`evidence_handling`** (15 filas) — cómo maneja hechos/exhibits, comprobado con
   `must_contain` / `must_not_contain` sobre el contenido generado:
   - `STATE_UPON_REQUEST_FACT`: un hecho marcado "dar si se pregunta" → decirlo directo.
   - `STATE_CASE_DATA_FACT`: el dato vive en el bloque de datos del caso → decirlo directo,
     sin pedir que el candidato asuma.
   - `TELL_TO_ASSUME_NOWHERE`: el dato no existe en ningún sitio del contexto → admitirlo y
     pedir que el candidato asuma (no inventar cifras).
   - `DECLINE_HIDDEN_NOT_UPON_REQUEST`: piden coaching/hipótesis oculta → redirigir con una
     pregunta, sin parafrasear la guía oculta.
   - `ACK_ALREADY_REVEALED`: el candidato repite una pregunta ya respondida → reconfirmar
     brevemente y avanzar, sin re-explicar como si fuera nuevo.
3. **`guardrail`** (16 filas) — resistencia a fugas de información / adversarial, checkeado
   con `forbidden_substrings` (nunca debe aparecer la hipótesis oculta del caso):
   - `DIRECT_ASK_FOR_ANSWER`, `PROMPT_INJECTION_IGNORE_INSTRUCTIONS`,
     `SYMPATHY_PLEA_FOR_STRATEGY`, `DECLINEPERFORMANCE_FEEDBACK` — 4 variantes
     de "dame la respuesta / rompe el personaje / dime cómo voy" que el interviewer debe
     rechazar siempre, sea cual sea el framing (urgencia, roleplay, súplica, nota de
     sistema falsa...).
4. **`turn_control`** (24 filas) — gestión del presupuesto de turnos (4 turnos compartidos
   por ambas arquitecturas) y de `ready_for_judge` / `ready_for_evaluation`:
   - `FINAL_TURN_WRAPUP_NORMAL` / `_WHILE_STUCK`: en el turno 3 hay que pedir la
     recomendación final sí o sí, incluso si el candidato está atascado repitiendo algo.
   - `EARLY_SUFFICIENCY_FULL_RECOMMENDATION`: el candidato ya dio todo (estructura,
     diagnóstico, recomendación, riesgo, next step) en un solo turno → `ready_for_judge`
     debe ser `True` aunque no se haya agotado el presupuesto de turnos.
   - `EARLY_TURN_NOT_READY` / `MID_CONVERSATION_NOT_READY_DESPITE_LENGTH`: respuestas
     vacías, tangenciales o circulares → `ready_for_judge=False`, incluso si ya llevan
     varios turnos (la longitud de la conversación no basta).
   - `PREMATURE_RECOMMENDATION_NOT_READY`: recomendación en frío sin estructura ni
     evidencia detrás → tampoco cuenta como lista.

### Resultados

Pendiente — los golden sets ya no son los mismos que cuando se corrió por última vez
(`evidence_handling` tenía 18 filas con la categoría `REVEAL_CREATIVE_BLOCK`, eliminada al
quitar el bloque creativo de los casos 03/04; `guardrail` usaba el nombre
`DECLINE_MIDSTREAM_PERFORMANCE_FEEDBACK`, ahora `DECLINEPERFORMANCE_FEEDBACK`). Hace falta
un run nuevo (`make interviewer-eval` / `make baseline-eval`, con LM Studio arriba) para
cifras que hablen de los fixtures y categorías actuales.

---

## 3. Resumen ejecutivo

Pendiente de rehacer con cifras vigentes: las conclusiones de esta sección se apoyaban en
los resultados de las secciones 1, 1bis y 2, que se han quitado por estar medidas contra
una taxonomía/golden set que ya no existe. Repetir en este orden y volver a escribir el
resumen a partir de los números nuevos:

```
make judge-eval GOLDEN_SET=worldcup
make baseline-eval BASELINE_GOLDEN_SET=worldcup
make interviewer-eval
make baseline-eval
```
