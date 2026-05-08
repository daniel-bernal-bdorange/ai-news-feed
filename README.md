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
- persistencia semanal en `data/articles_week.json` con actualizacion atomica del acumulado actual;
- ranking final del digest con limites configurables por fuente y categoria;
- pruebas unitarias focalizadas para el slice de ingesta.

Con el brief v2, ese bootstrap cubre solo la base de ingesta. El backlog operativo pendiente para almacenamiento semanal, ranking, Groq, Teams y GitHub Actions queda documentado en `docs/devops-rebaseline-v2.md`.

## Puesta en marcha local

```powershell
pip install -r requirements.txt
python -m pytest --cov=main --cov=src --cov-fail-under=80
python main.py --mode daily
```

Modos de ejecucion del runtime:

- `python main.py --mode daily`: ejecuta ingesta y persistencia semanal sin publicar digest.
- `python main.py --mode weekly`: ejecuta ingesta, re-sumariza el acumulado semanal y publica digest si `POWER_AUTOMATE_URL` esta configurada.

Automatizacion GitHub Actions:

- `daily_fetch.yml`: cron diario + disparo manual por `workflow_dispatch`.
- `weekly_digest.yml`: cron de viernes + disparo manual por `workflow_dispatch`.
- En disparos manuales de ambos workflows, el input `commit_changes` permite decidir si se hace auto-commit de `data/articles_week.json`.

Variables de entorno relevantes:

- `NEWSAPI_KEY`: habilita la parte opcional de NewsAPI cuando `sources.newsapi.enabled` es `true`.
- `GROQ_API_KEY`: habilita la generacion de resumenes IA mediante Groq cuando `ai_summary.enabled` es `true`.
- `POWER_AUTOMATE_URL`: habilita la publicacion del digest semanal (solo en `--mode weekly`).

Configuracion relevante para resumenes IA en `config/settings.yaml`:

```yaml
ai_summary:
	enabled: true
	provider: "groq"
	api_url: "https://api.groq.com/openai/v1/chat/completions"
	model: "llama-3.1-8b-instant"
	max_words: 60
	timeout_seconds: 20.0
	prompt_template: |
		You are a news analyst for a technology and telecom company based in Spain.
		Summarize the following news article in {max_words} words or less.
		{geo_instruction}
		Be factual, neutral, and concise. Output only the summary, no preamble.
		Article: {content}
```

