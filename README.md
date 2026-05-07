# AI-News-Feed

Repositorio base para el proyecto AI-News-Feed.

## Documentacion operativa

- `docs/git-devops-playbook.md`: playbook reutilizable de Git y Azure DevOps para arrancar el proyecto con trazabilidad desde el primer dia.
- `docs/project-brief-news-digest.md`: brief funcional y tecnico del bot de digest diario.

## Estado del bootstrap

El repositorio ya incluye la base Python para la feature 288:

- carga de configuracion YAML;
- ingesta RSS multi-fuente con ventana temporal configurable;
- NewsAPI como fuente opcional controlada por configuracion;
- normalizacion comun de articulos y deduplicacion por URL o similitud de titulo;
- pruebas unitarias focalizadas para el slice de ingesta.

## Puesta en marcha local

```powershell
pip install -r requirements.txt
python -m pytest
python main.py
```

Variables de entorno relevantes:

- `NEWSAPI_KEY`: habilita la parte opcional de NewsAPI cuando `sources.newsapi.enabled` es `true`.

