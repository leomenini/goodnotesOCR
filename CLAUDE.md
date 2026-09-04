# CLAUDE.md

Contexto del proyecto para agentes. Leer entero antes de escribir código.

## Qué es esto

Herramienta personal para convertir apuntes manuscritos tomados en iPad con
GoodNotes en texto y LaTeX utilizables. Uso propio, no es un producto.

El objetivo de largo plazo es dejar de tipear a mano los ejercicios y apuntes.
El objetivo de la primera etapa es mucho más chico: ver cuánta calidad de
reconocimiento se puede sacar de una página real, y con qué preprocesado.

**No es un proyecto de OCR clásico.** Ver "Decisiones ya tomadas".

## Estado

Greenfield. No hay código todavía. Este documento es el punto de partida.

## Insumos disponibles

Cada cuaderno se sincroniza a Nextcloud en dos formatos:

- `*.goodnotes` — formato nativo, conserva los trazos
- `*.pdf` — export rasterizado del mismo cuaderno

## Lo que ya se investigó sobre el formato `.goodnotes`

No hace falta volver a averiguar esto:

- Es un **ZIP estándar**. Se descomprime con herramientas normales.
- Adentro: `schema.pb` (versión de schema), `index.notes.pb` (lista de páginas
  y mapeo a `notes/<UUID>`), `index.attachments.pb`, `index.events.pb`, y una
  carpeta `notes/` con un stream de records Protobuf por página.
- Los records de página contienen trazos, formas y cajas de texto.
- Los datos de trazo vienen envueltos en el **Framed LZ4 propietario de Apple**
  (marcadores `bv41` / `bv4$`), y adentro hay una imagen de memoria **TPL**
  (librería en C de Troy Hanson) con los puntos de coordenadas.
- Por trazo se puede recuperar: UUID, color, alpha, y la lista de puntos.
  Los puntos son vectores, no píxeles.

**No implementar este parseo desde cero.** Ya existe:

- `Kaih1825/parser-for-goodnotes` — Python puro, sin `.proto`. Expone
  `gn-inspect`, `gn-dump`, `gn-diff`, `gn-export-json`, `gn-export-svg`.
  Tiene wiki con el análisis del formato.
- `hudsonmp/goodnotes-mcp` — servidor MCP que hace OCR de cuadernos vía Apple
  Vision. Corre Vision sobre el thumbnail o el PDF exportado, **no** sobre los
  trazos. Útil como referencia de qué NO alcanza.

Primer paso real del proyecto: evaluar si el parser levanta bien los archivos
propios antes de construir nada encima.

## Decisiones ya tomadas

No reabrir sin discutirlo:

1. **Tesseract está descartado.** Entrenado para texto impreso, trabaja línea
   por línea, no representa estructura 2D. Inútil para fracciones, integrales,
   subíndices y manuscrita.
2. **No hay reconocedor online open source viable.** El reconocimiento de
   matemática manuscrita a partir de trazos en serio hoy es MyScript, y es
   propietario. Tener los trazos NO da un reconocedor.
3. **Los trazos se usan para preparar la entrada, no para reconocer.**
   Arquitectura: trazos → limpieza y segmentación → VLM → LaTeX → compilación
   como verificación.
   - Renderizar SVG limpio a alta resolución: sin rayado de papel, sin fondo,
     tinta en negro puro. Un VLM lee bastante mejor eso que el PDF exportado.
   - Segmentar por agrupamiento espacial y temporal de trazos, y mandar un
     ejercicio por llamada en lugar de la página entera. Buena parte de los
     errores de OCR matemático son de layout, no de símbolo.
   - El orden de escritura de los trazos es metadato aprovechable para
     desambiguar estructura 2D.
4. **El PDF es camino de respaldo desde el día uno.** El parser es ingeniería
   inversa de un formato no documentado; un update de GoodNotes lo puede
   romper. El pipeline no puede depender exclusivamente de él.
5. **Verificación mecánica.** Una salida LaTeX que no compila es una salida
   fallida. Usar `tectonic`, que ya está en uso en otro proyecto del autor.

## Decisiones abiertas — preguntar, no resolver solo

- **Salida objetivo.** LaTeX compilable para entregar trabajos, o texto
  indexable para buscar en los cuadernos. Son dos herramientas distintas y la
  segunda tolera errores que la primera no. Todavía no está decidido cuál se
  construye primero.
- **Criterio de segmentación** de trazos en unidades (ejercicio, ecuación,
  párrafo). Hay opciones espaciales y temporales y no está claro cuál gana.
- **Granularidad de la llamada al modelo**: página, región, ecuación suelta.
- **Cómo se mide la calidad.** Sin métrica no se sabe si un cambio mejoró algo.
  Hay que definirla antes de empezar a iterar sobre prompts.

## Baseline obligatorio antes de construir

Ejecutar y anotar el resultado, en este orden:

1. **Conversión nativa de GoodNotes** (lazo → convertir a texto) sobre una
   página manuscrita real. Si la app nativa no levanta bien esa letra, el techo
   del proyecto está más abajo de lo que se cree.
2. **PDF exportado directo al VLM**, sin ningún preprocesado.
3. **SVG limpio renderizado desde trazos, al mismo VLM.**

Si (3) no le gana claramente a (2), el trabajo de parseo de trazos no se
justifica y hay que replantear el proyecto. Ese es el resultado más valioso
que puede dar la primera semana, incluso si es negativo.

## Cómo trabajar

- Entorno: WSL, Python. El autor ya usa pandas/matplotlib/scipy y `tectonic`.
- Preguntar antes de fijar arquitectura o agregar dependencias pesadas.
  El autor prefiere discutir alternativas y restricciones antes que recibir una
  implementación cerrada.
- Empezar por lo más chico que produzca evidencia. Una página real vale más que
  un pipeline completo sobre datos inventados.
- No generar datos de prueba sintéticos: el corpus son los cuadernos reales.
- Nada de "hecho" sin verificación: si la salida es LaTeX, tiene que compilar.
