# Rebaseline DevOps para el brief v2

## Objetivo

Realinear backlog, validaciones y trazabilidad con el nuevo modelo operativo del proyecto: ingesta diaria, acumulacion semanal en repositorio, ranking editorial los viernes y entrega del digest por Microsoft Teams.

## Cambios que invalidan el baseline anterior

- El alcance deja de ser un digest diario unico y pasa a una operacion de lunes a domingo con digest semanal.
- Aparece persistencia funcional en `data/articles_week.json`, con auto-commit tras la ingesta diaria y tras el reset semanal.
- La ejecucion se separa en tres workflows con objetivos distintos: `ci.yml`, `daily_fetch.yml` y `weekly_digest.yml`.
- El ranking final ya no depende solo de filtrado basico: ahora combina `relevance_score`, `geo_boost`, recencia y diversidad de fuentes.
- La Definition of Done exige mas evidencia operacional: `ruff`, `pytest`, cobertura >= 80 %, prueba manual por `workflow_dispatch`, revision de secretos y README actualizado.

## Recomendacion de backlog en Azure DevOps

Se recomienda conservar la estructura base creada en ADO y reencuadrar su alcance en lugar de abrir un backlog paralelo.

### Epic 287 — Motor de curacion semanal y almacenamiento

- Feature 288 `Ingesta y normalizacion`: RSS, NewsAPI opcional, ventana de 24h, normalizacion comun y deduplicacion de entrada.
- Extender la feature 288 para incluir escritura y lectura de `data/articles_week.json`, deduplicacion persistente por URL y metadatos semanales.
- Feature 292 `Seleccion editorial y priorizacion geografica`: filtros include/exclude, score numerico, `geo_boost`, ranking por recencia, bonus de diversidad y equilibrio por categoria.
- La historia 289 sigue siendo valida como bootstrap de configuracion e ingesta, pero no cierra por si sola la feature 288 bajo el brief v2.

### Epic 299 — Operacion, entrega y calidad

- Feature 296 `Resumenes IA resilientes`: Groq solo los viernes, retries con backoff, prompt con contexto Espana/Europa y fallback al excerpt.
- Feature 300 `Publicacion en Microsoft Teams`: Adaptive Card semanal, badge 🇪🇸 para `geo_boost`, tarjeta minima cuando no haya noticias y reintentos del webhook.
- Feature 303 `Configuracion segura y mantenibilidad`: `config/settings.yaml` como contrato unico, secretos en GitHub Actions y ausencia de secretos en logs o codigo.
- Feature 307 `Automatizacion de ejecucion y validacion`: `daily_fetch.yml`, `weekly_digest.yml`, `ci.yml`, permisos de escritura para auto-commit y ejecucion manual por `workflow_dispatch`.
- Feature 310 `Observabilidad y calidad tecnica`: logs estructurados por etapa, test suite por modulo, cobertura objetivo y actualizacion de README cuando cambie la operativa.

## Orden recomendado de ejecucion

1. Cerrar bien la base de almacenamiento semanal antes de ampliar integraciones externas.
2. Completar scoring, `geo_boost` y ranking semanal antes de cerrar el trabajo de Groq o Teams.
3. Implementar Groq y Teams con mocks estables antes de activar los workflows programados.
4. Dejar `ci.yml` como gate minima antes de habilitar auto-commit en `main`.
5. Ejecutar `workflow_dispatch` controlado de `daily_fetch.yml` y `weekly_digest.yml` antes de considerar cerrada la automatizacion.

## Gate minimo por tipo de slice

| Slice | Validacion minima |
|---|---|
| Configuracion, modelos o utilidades locales | `ruff check main.py src tests` + `pytest` focalizado |
| Ingesta, filtros o ranking | `ruff check main.py src tests` + tests del modulo afectado |
| Persistencia en `data/articles_week.json` | tests de storage/deduplicacion + verificacion del artefacto generado |
| Groq o Teams | tests con mocks + smoke controlado sin exponer secretos |
| GitHub Actions, secretos o auto-commit | validacion local mas `workflow_dispatch` manual con evidencia del run |
| Cierre de feature o epic | `ruff`, `pytest`, cobertura >= 80 %, README actualizado y trazabilidad en ADO |

## Checklist de actualizacion en ADO

- Revisar historias abiertas creadas desde el brief anterior y marcar cuales quedan absorbidas, cuales cambian de alcance y cuales deben cerrarse como obsoletas.
- Actualizar descripciones de features para reflejar el flujo semanal y los tres workflows.
- Asegurar que toda historia que toque entrega o automatizacion incluya un criterio explicito de `workflow_dispatch`.
- Mantener la trazabilidad de commits y validaciones en espanol, indicando si hubo artefactos locales excluidos del commit.