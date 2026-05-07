# Playbook reutilizable de Git y Azure DevOps

Guia corta para arrancar un proyecto nuevo con el mismo nivel de trazabilidad operativa usado en Olympic Data Story.

## Principios base

- Mantener comentarios tecnicos y cierres de Azure DevOps en espanol.
- Trabajar por slices pequenas y cerrables, cada una con validacion explicita.
- Evitar commits con artefactos locales o cambios no relacionados.
- Dejar siempre trazabilidad bidireccional entre codigo y backlog.
- Actualizar la memoria del proyecto al cerrar historias, features y cierres relevantes.

## Flujo recomendado por historia

1. Mover la historia a estado activo y dejar comentario de arranque en ADO.
2. Si la slice no es trivial, crear una rama `feature/<slug-corto>`.
3. Implementar el cambio y validar con la prueba mas barata y especifica posible.
4. Hacer commit solo de los archivos relacionados con la historia.
5. Hacer push y registrar el SHA o la URL del commit.
6. Cerrar la historia en ADO con resumen tecnico, validaciones ejecutadas y resultado.
7. Anadir un comentario final con la URL del commit de GitHub si no quedo en el cierre inicial.
8. Actualizar la memoria del repo con el estado final y los aprendizajes operativos.

## Validacion minima antes de cerrar

- `eslint` focalizado en los archivos tocados cuando la slice es local.
- Smoke test funcional si hay interaccion visible o comportamiento critico.
- `npm run build` o validacion equivalente cuando la slice afecta integracion o entrega.
- Verificacion manual breve en la ruta o pantalla afectada cuando aplique.

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
- una memoria de setup con org, proyecto, repo y comandos validados;
- una memoria de estado para cierres y checkpoints;
- un script de bootstrap del backlog si el proyecto va a nacer con ADO.
