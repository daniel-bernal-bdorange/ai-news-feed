# Playbook reutilizable de Git y Azure DevOps

Guia corta para arrancar y operar proyectos con el mismo nivel de trazabilidad usado en este repositorio. Para AI-News-Feed, este playbook se complementa con `docs/devops-rebaseline-v2.md`, que aterriza el brief vigente en backlog, validaciones y orden de ejecucion.

## Principios base

- Mantener comentarios tecnicos y cierres de Azure DevOps en espanol.
- Trabajar por slices pequenas y cerrables, cada una con validacion explicita.
- Evitar commits con artefactos locales o cambios no relacionados.
- Dejar siempre trazabilidad bidireccional entre codigo y backlog.
- Mantener backlog, workflows y criterios de cierre alineados con el brief funcional vigente.
- Actualizar la memoria del proyecto al cerrar historias, features y cierres relevantes.

## Flujo recomendado por historia

1. Mover la historia a estado activo y dejar comentario de arranque en ADO.
2. Si la slice no es trivial, crear una rama `feature/<slug-corto>`.
3. Implementar el cambio y validar con la prueba mas barata y especifica posible.
4. Si la slice toca workflows, secretos, auto-commit o entrega externa, registrar tambien una evidencia operacional corta.
5. Hacer commit solo de los archivos relacionados con la historia.
6. Hacer push y registrar el SHA o la URL del commit.
7. Cerrar la historia en ADO con resumen tecnico, validaciones ejecutadas y resultado.
8. Anadir un comentario final con la URL del commit de GitHub si no quedo en el cierre inicial.
9. Actualizar README, playbook o memoria si la slice cambia el contrato operativo del repo.

## Validacion minima antes de cerrar

- Linter o analisis estatico focalizado sobre los archivos tocados.
- Prueba automatizada minima y especifica para el slice afectado.
- Smoke test funcional si hay integracion visible, persistencia o comportamiento critico.
- Validacion operacional corta cuando la slice afecta CI/CD, secretos, planificacion o entrega externa.

Para este repositorio, la base minima recomendada es:

- `ruff check main.py src tests`
- `python -m pytest tests/<slice>` o `python -m pytest` cuando el cambio cruce varios modulos
- `python main.py` solo para slices locales del flujo actual; cuando entren `fetch_and_store.py` o `digest_and_send.py`, usar el entry point afectado
- `workflow_dispatch` manual cuando el cambio toque GitHub Actions, auto-commit, `data/articles_week.json`, Groq o Teams

## Convenciones de Git

- Preferir nombres de rama legibles y ligados a la historia: `feature/ls-04-timeline-d3-vertical`.
- Usar commits pequenos y descriptivos, normalmente con `feat:`, `fix:` o `docs:`.
- No mezclar cambios de varias historias en un mismo commit si se pueden separar.
- Si una historia ya estaba implementada de antes, cerrar retroactivamente con el commit historico correcto.
- Al terminar una feature, consolidar y borrar ramas fusionadas para dejar `main` limpio.

## Convenciones de Azure DevOps

- Preferir `az boards` frente a otros comandos menos fiables del CLI.
- Para jerarquias padre-hijo, usar `az boards work-item relation add`.
- Despues de tocar jerarquias, verificar con WIQL por `System.Parent` y con `work-item show`.
- Si un item no se puede borrar por permisos, cerrarlo como obsoleto y corregir su jerarquia.
- Si quedan archivos fuera del commit por ser artefactos locales o trabajo no relacionado, dejarlo indicado en ADO.

## Adaptacion actual para AI-News-Feed

- El brief vigente ya no describe un digest diario simple: ahora hay ingesta diaria, acumulacion semanal en repo y digest semanal los viernes.
- La trazabilidad operativa debe distinguir tres workflows: `ci.yml`, `daily_fetch.yml` y `weekly_digest.yml`.
- Las slices que toquen almacenamiento persistente deben vigilar que el unico artefacto mutable esperado sea `data/articles_week.json`.
- La Definition of Done operativa sube el liston: `ruff`, `pytest`, cobertura objetivo >= 80 %, prueba manual por `workflow_dispatch` cuando aplique, secretos revisados y README actualizado si cambia configuracion.
- Los secretos operativos a vigilar son `GROQ_API_KEY`, `TEAMS_WEBHOOK_URL`, `NEWSAPI_KEY` y `GH_PAT`.
- El mapa de backlog y el orden recomendado de ejecucion para este repo viven en `docs/devops-rebaseline-v2.md`.

## Comandos utiles

```powershell
az login --allow-no-subscriptions
az devops configure --defaults organization=https://dev.azure.com/<org>

az boards query --wiql "Select [System.Id], [System.Title], [System.State], [System.WorkItemType] From WorkItems Where [System.TeamProject] = '<project>' Order By [System.ChangedDate] Desc" --output table

az boards work-item show --id <id> --output json

az boards work-item update --id <id> --fields "System.State=Active" --discussion "Inicio de implementacion..." --output table

az boards work-item relation add --id <parentId> --relation-type child --target-id <childId>
```

## Plantilla de comentario de arranque

```text
Inicio de implementacion de la historia.
Alcance de esta slice: <resumen corto>.
Validacion prevista: <eslint/build/smoke/manual>.
```

## Plantilla de comentario de cierre

```text
Historia completada.
Resumen tecnico: <que se implemento>.
Validaciones: <lista corta de checks ejecutados>.
Trazabilidad Git: <url del commit o se anadira en comentario final>.
Notas: <artefactos excluidos, cierres retroactivos, permisos, etc.>
```

## Semilla para un proyecto nuevo

Al crear el siguiente repo, conviene dejar desde el dia 1:

- un documento operativo como este en `docs/`;
- un documento de rebaseline cuando el brief cambie de forma estructural;
- una memoria de setup con org, proyecto, repo y comandos validados;
- una memoria de estado para cierres y checkpoints;
- un script de bootstrap del backlog si el proyecto va a nacer con ADO.
