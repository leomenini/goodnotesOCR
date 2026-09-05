# goodnotesOCR

Convierte apuntes manuscritos de GoodNotes (iPad) en LaTeX compilable.

Toma una página del PDF que GoodNotes exporta, se la manda a un modelo de
visión, y verifica el resultado compilándolo con `tectonic`. Si el LaTeX no
compila, la salida se considera fallida.

Es una herramienta personal, para apuntes de física y matemática de la
facultad. No es un producto ni pretende serlo.

## Por qué funciona así

La idea original era distinta: `.goodnotes` es un ZIP con los trazos vectoriales
adentro, así que parecía razonable renderizar tinta limpia desde los trazos
(sin rayado de hoja, sin fondo) y darle eso al modelo, esperando mejor
reconocimiento que sobre el PDF rasterizado.

Se midió antes de construir. Sobre 5 páginas reales de cuadernos distintos, con
matemática densa:

| Enfoque | Resultado |
| --- | --- |
| Conversión nativa de GoodNotes (lazo → texto) | Falla por completo. Devuelve la imagen sin convertir. |
| PDF exportado → modelo de visión | Transcripción completa y correcta. |
| SVG limpio desde trazos → mismo modelo | Equivalente. A veces peor (notación menos fiel, truncamientos). |

Parsear el formato propietario no se pagaba con mejor calidad, así que el
pipeline arranca del PDF. El parseo de trazos quedó documentado en `CLAUDE.md`
y el código en la rama `experiment/stroke-figures`.

## Instalación

Requiere Python 3.13, [uv](https://docs.astral.sh/uv/) y
[tectonic](https://tectonic-typesetting.github.io/) en el `PATH`.

```bash
uv sync
```

La API key de Gemini va en un archivo `.env` en la raíz del repo (está en
`.gitignore`, no se commitea):

```
GEMINI_API_KEY=...
```

## Uso

```python
from goodnotesocr import pipeline

result = pipeline.run_page("ruta/al/cuaderno.pdf", page_index=1)  # 0-indexed
print(result.compiled)      # True si el LaTeX compiló
print(result.tex_path)      # out/pipeline/cuaderno_p2.tex
print(result.pdf_out_path)  # out/pipeline/cuaderno_p2.pdf (solo si compiló)
print(result.log_path)      # log de tectonic, útil cuando falla
```

Todo lo generado va a `out/`, que está en `.gitignore`.

## Arquitectura

Cuatro módulos en `src/goodnotesocr/`, uno por paso:

**`pdf_render.py`** — Rasteriza una página del PDF a PNG con `pymupdf`, a 200
DPI por defecto. También expone `page_count`.

**`vlm.py`** — Cliente sobre la API de Gemini. Manda la imagen más un prompt
fijo y devuelve el LaTeX. El prompt es la parte que más importa: pide
únicamente el cuerpo del documento, sin preámbulo, y prohíbe explícitamente
Markdown, frases introductorias y cercas de código. Sin esas reglas el modelo
devuelve Markdown con fórmulas embebidas, que no compila. Los diagramas se
piden como una descripción de una línea entre corchetes, no como intento de
reproducirlos.

**`verify.py`** — Envuelve el cuerpo en un preámbulo mínimo y compila con
`tectonic`. Devuelve éxito, el log y los bytes del PDF.

**`pipeline.py`** — Encadena los tres pasos, limpia una eventual cerca de
código, y guarda `.tex`, `.pdf` y log bajo `out/pipeline/`.

### Detalles del preámbulo que costaron sangre

`tectonic` corre XeTeX, y dos cosas del preámbulo obvio fallan de formas poco
obvias:

- Con `inputenc`/`fontenc` el signo `¿` sale como `£`. Se usa `fontspec`, que
  da Unicode completo.
- `babel` con español convierte la comilla recta en carácter activo, y
  `"Conductor"` termina como `Çonductor"`. Se carga con `es-noshorthands`.

## Estado y limitaciones

Anda de punta a punta y produce LaTeX que compila sobre páginas reales del
corpus. Lo que no está resuelto:

- **Costo.** Una página densa consume alrededor de 30K tokens de salida, en
  buena parte tokens de razonamiento del modelo. Bajar la granularidad a una
  llamada por ejercicio reduce eso un orden de magnitud pero **empeora la
  calidad**: el recorte pierde contexto y aparece mucho LaTeX mal formado.
  Ese intento está en la rama `experiment/stroke-figures`.
- **Los diagramas se pierden.** Quedan como una frase descriptiva. Extraerlos
  como figuras vectoriales desde los trazos se probó y funciona, pero las cajas
  detectadas se comen prosa vecina y el resultado global empeora.
- **Sin métrica automática.** Hoy la calidad se juzga con el gate de
  compilación más comparación visual contra la página original.
- **Página por página.** No hay procesamiento de cuadernos enteros.
- **Free tier de Gemini.** 15 llamadas por minuto y por modelo, y 503 seguidos
  por saturación. Conviene reintentar con espera.

## Corpus

Los cuadernos reales viven fuera del repo, en el sync de Nextcloud. Una
advertencia si se van a usar para probar: no todas las páginas son tinta
nativa. Algunas tienen el contenido matemático como imagen pegada y solo el
título en trazos.

## Licencia

MIT.
