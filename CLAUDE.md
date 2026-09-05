# CLAUDE.md

Contexto del proyecto para agentes. Leer entero antes de escribir código.

## Qué es esto

Herramienta personal para convertir apuntes manuscritos tomados en iPad con
GoodNotes en texto y LaTeX utilizables. Uso propio, no es un producto.

El objetivo de largo plazo es dejar de tipear a mano los ejercicios y apuntes.

**No es un proyecto de OCR clásico.** Ver "Decisiones ya tomadas".

## Estado

Funciona un pipeline end-to-end: PDF exportado → Gemini → LaTeX → compilación
con `tectonic` como verificación. Ver `README.md` para la arquitectura, el uso
y el detalle de los resultados medidos.

El baseline obligatorio ya se ejecutó y **cambió el rumbo del proyecto**. Ver
"Resultados del baseline" más abajo antes de proponer nada.

## Insumos disponibles

Cada cuaderno se sincroniza a Nextcloud en dos formatos:

- `*.goodnotes` — formato nativo, conserva los trazos
- `*.pdf` — export rasterizado del mismo cuaderno

El corpus de trabajo real está en
`/home/leo/Desktop/Files/ING/goodnotes/Backup 07-26/PDFS/`: decenas de pares
`.goodnotes`/`.pdf` de Física 3, Mecánica Newtoniana y Programación 1. El PDF
exportado tiene una página por página del cuaderno, en el mismo orden.

**Ojo con la muestra**: no todas las páginas son tinta nativa. Hay páginas cuyo
contenido matemático es una imagen pegada (PNG adjunto) y solo el título son
trazos. Antes de usar una página para probar parseo de trazos, verificar
`len(page.strokes)` y `len(page.image_elements)`.

## Lo que ya se investigó sobre el formato `.goodnotes`

No hace falta volver a averiguar esto:

- Es un **ZIP estándar**. Se descomprime con herramientas normales.
- Adentro: `schema.pb`, `index.notes.pb` (páginas → `notes/<UUID>`),
  `index.attachments.pb`, `index.events.pb`, y `notes/` con un stream de
  records Protobuf por página.
- Los datos de trazo vienen en **Framed LZ4 propietario de Apple** (`bv41` /
  `bv4$`), y adentro hay una imagen de memoria **TPL** con los puntos.
- Por trazo se recupera: UUID, color, alpha, ancho, y puntos con presión.

**No implementar este parseo desde cero.** Existe
`Kaih1825/parser-for-goodnotes` (Python puro, MIT, CLI `gn-inspect`,
`gn-dump`, `gn-export-json`, `gn-export-svg`, y API `GoodNotesDocument`).
Se validó sobre archivos propios: levanta bien los cuadernos reales.

`hudsonmp/goodnotes-mcp` corre Apple Vision sobre el thumbnail o el PDF, **no**
sobre los trazos. Solo sirve como referencia de qué NO alcanza; no es
dependencia de este proyecto.

### Dos bugs reales encontrados al renderizar trazos

Si algún día se vuelve a renderizar desde trazos, esto ya está diagnosticado
(el código está en la rama `experiment/stroke-figures`):

1. **Presión corrupta.** Algunos trazos decodifican con presión absurda (se vio
   287 donde el rango es 0-1). Como el ancho del listón sale de
   `width * pressure`, el trazo se infla y tapa media página. El parser trae
   una ruta vectorial precalculada en `stroke.native_cgpaths` para esos casos:
   usarla cuando exista, y sanear la presión con `is_valid_pressure` en el
   resto. Reproducible en `Fis3 Pr3.goodnotes`, página 2, trazo 135.
2. **Doble escalado.** Las coordenadas de los puntos están en 132 DPI y hay que
   multiplicarlas por `72/132`. `page.dimensions` **ya está** en 72 DPI: si se
   la escala también, el lienzo queda chico y recorta contenido.

## Resultados del baseline (ya ejecutado, no repetir)

Sobre 5 páginas reales de cuadernos distintos, con matemática densa:

1. **Conversión nativa de GoodNotes** (lazo → "Convertir a texto"): falla por
   completo sobre matemática. Devuelve la imagen sin convertir nada.
2. **PDF crudo → VLM**: transcripción completa y correcta.
3. **SVG limpio renderizado desde trazos → mismo VLM**: equivalente a (2).
   A veces empata, a veces queda peor (notación menos fiel, truncamientos).

**Conclusión, ya aplicada: el parseo de trazos no se justifica.** El PDF
exportado rinde igual con una fracción del trabajo. El pipeline actual no abre
el `.goodnotes`.

## Decisiones ya tomadas

No reabrir sin discutirlo:

1. **Tesseract está descartado.** Texto impreso, línea por línea, sin
   estructura 2D. Inútil para fracciones, integrales, subíndices y manuscrita.
2. **No hay reconocedor online open source viable.** Tener los trazos NO da un
   reconocedor. El reconocimiento serio de matemática manuscrita hoy es
   MyScript, y es propietario.
3. **El pipeline arranca del PDF exportado, no de los trazos.** Revertido
   respecto de la idea original, por el baseline de arriba.
4. **Verificación mecánica.** Una salida LaTeX que no compila es una salida
   fallida. Se usa `tectonic`.
5. **Granularidad: página completa, una llamada por página.** Se probó
   segmentar en unidades tipo ejercicio y mandar una llamada por unidad: baja
   el costo un orden de magnitud pero **empeora la calidad**, porque el recorte
   pierde contexto y aparece mucho LaTeX mal formado. Está en la rama
   `experiment/stroke-figures`; no volver a esto sin una razón nueva.
6. **Nada de figuras extraídas de trazos.** Se probó (misma rama): Gemini
   localiza el diagrama, los trazos de esa caja se embeben como PDF vectorial.
   Anda, pero las cajas se comen prosa vecina y el resultado global es peor que
   describir el diagrama en una línea de texto.

## Decisiones abiertas — preguntar, no resolver solo

- **Texto indexable** como segunda salida (buscar en los cuadernos). Hoy solo
  se genera LaTeX. Se puede derivar aplanando el LaTeX, no está hecho.
- **Métrica de calidad.** Hoy: gate de compilación más comparación visual a
  ojo sobre un set fijo chico. No hay métrica automática de fidelidad; hacer
  una necesita transcripciones de referencia hechas a mano.
- **Costo.** Una página densa consume ~30K tokens de salida con
  `gemini-3.6-flash`, en buena parte tokens de razonamiento. Bajar esto sin
  perder calidad sigue sin resolverse (bajar la granularidad ya se probó y
  empeoró la calidad).
- **Procesar cuadernos enteros.** Hoy se corre página por página a mano.

## Cómo trabajar

- Entorno: WSL, Python 3.13 con `uv`. El autor ya usa pandas/matplotlib/scipy
  y `tectonic`.
- Preguntar antes de fijar arquitectura o agregar dependencias pesadas.
  El autor prefiere discutir alternativas y restricciones antes que recibir una
  implementación cerrada.
- Empezar por lo más chico que produzca evidencia. Una página real vale más que
  un pipeline completo sobre datos inventados.
- No generar datos de prueba sintéticos: el corpus son los cuadernos reales.
- Nada de "hecho" sin verificación: si la salida es LaTeX, tiene que compilar.
- La key de Gemini vive en `.env` (ignorado por git). El free tier limita a 15
  llamadas por minuto y por modelo, y devuelve 503 seguido: reintentar.
