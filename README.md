# goodnotesOCR

Convierte apuntes manuscritos de GoodNotes (iPad) en LaTeX compilable.

Toma una página del PDF que GoodNotes exporta, se la manda a Gemini, y
verifica el resultado compilándolo con `tectonic`. Si el LaTeX no compila, la
salida se considera fallida.

Herramienta personal, para apuntes de física y matemática.

## Instalación

Requiere Python 3.13, [uv](https://docs.astral.sh/uv/) y
[tectonic](https://tectonic-typesetting.github.io/) en el `PATH`.

```bash
uv sync
```

La API key de Gemini va en un archivo `.env` en la raíz del repo (está en
`.gitignore`):

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
fijo y devuelve el LaTeX. El prompt pide únicamente el cuerpo del documento,
sin preámbulo, y prohíbe explícitamente Markdown, frases introductorias y
cercas de código; sin esas reglas el modelo devuelve Markdown con fórmulas
embebidas, que no compila. Los diagramas se piden como una descripción de una
línea entre corchetes.

**`verify.py`** — Envuelve el cuerpo en un preámbulo mínimo y compila con
`tectonic`. Devuelve éxito, el log y los bytes del PDF.

**`pipeline.py`** — Encadena los tres pasos, limpia una eventual cerca de
código, y guarda `.tex`, `.pdf` y log bajo `out/pipeline/`.

### Detalles del preámbulo

`tectonic` corre XeTeX, y dos cosas del preámbulo obvio fallan de formas poco
obvias:

- Con `inputenc`/`fontenc` el signo `¿` sale como `£`. Se usa `fontspec`, que
  da Unicode completo.
- `babel` con español convierte la comilla recta en carácter activo, y
  `"Conductor"` termina como `Çonductor"`. Se carga con `es-noshorthands`.

## Limitaciones

- Se procesa una página por llamada; no hay procesamiento de cuadernos enteros.
- Una página densa consume alrededor de 30K tokens de salida.
- Los diagramas no se reproducen: quedan como una frase descriptiva.
- El free tier de Gemini limita a 15 llamadas por minuto y por modelo, y
  devuelve 503 con frecuencia. Conviene reintentar con espera.

## Licencia

MIT.
