# AI-News-Feed

Repositorio base para el proyecto AI-News-Feed.

## Documentacion operativa

- `docs/git-devops-playbook.md`: playbook reutilizable de Git y Azure DevOps para arrancar el proyecto con trazabilidad desde el primer dia.
- `docs/devops-rebaseline-v2.md`: aterrizaje del brief v2 en backlog, validaciones y orden recomendado de ejecucion.
- `docs/project-brief-news-digest-v2.md`: brief funcional y tecnico vigente del bot con ingesta diaria y digest semanal.
- `docs/project-brief-news-digest.md`: brief anterior, mantenido solo como referencia historica.

## Estado del bootstrap

El repositorio ya incluye la base Python del primer slice de la feature 288:

- carga de configuracion YAML;
- ingesta RSS multi-fuente con ventana temporal configurable;
- NewsAPI como fuente opcional controlada por configuracion;
- normalizacion comun de articulos y deduplicacion por URL o similitud de titulo;
- pruebas unitarias focalizadas para el slice de ingesta.

Con el brief v2, ese bootstrap cubre solo la base de ingesta. El backlog operativo pendiente para almacenamiento semanal, ranking, Groq, Teams y GitHub Actions queda documentado en `docs/devops-rebaseline-v2.md`.

## Puesta en marcha local

```powershell
pip install -r requirements.txt
python -m pytest
python main.py
```

Variables de entorno relevantes:

- `NEWSAPI_KEY`: habilita la parte opcional de NewsAPI cuando `sources.newsapi.enabled` es `true`.

