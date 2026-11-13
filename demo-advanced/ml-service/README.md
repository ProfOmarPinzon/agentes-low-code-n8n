# Servicio de retención con MCP (Churn Retention MCP)

Servicio FastAPI que expone un modelo de **churn (Random Forest)** mediante endpoints **REST** y herramientas **MCP**. Lo consume la Práctica 2 del curso.

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Información del servicio y lista de herramientas MCP |
| GET | `/docs` | Swagger UI |
| GET | `/health` | Verificación de estado |
| GET | `/customer/by-email` | Búsqueda de cliente por correo |
| GET | `/payment_history` | Historial de pagos sintético (`?email=`) |
| POST | `/predict_churn` | Probabilidad de churn y factores principales |
| GET | `/support_history` | Quejas, llamadas y canal preferido (`?email=`) |
| ALL | `/mcp/` | Servidor MCP (*streamable HTTP*); destino del MCP Client de n8n |

## Clientes de demostración

| Correo | Id | Probabilidad | Acción esperada |
|--------|----|--------------|-----------------|
| `laura.gomez@demo.com` | 5001 | 0,66 (alta) | `retain_aggressive` |
| `carlos.toxico@demo.com` | 2017 | 0,93 (alta) | `let_go` (moroso, riesgo muy alto) |
| `maria.inactiva@demo.com` | 3088 | 0,47 (media) | `retain_soft` (pausa de 3 meses) |
| `ana.premium@demo.com` | 1042 | 0,17 (baja) | `retain_soft` (sin descuento) |
| `pedro.moroso@demo.com` | 7001 | 0,71 (alta) | `offer_payment_plan` |

Las acciones dependen de las políticas definidas en `demo-advanced/prompts/05-strategist.txt`. La documentación completa se encuentra en `docs/alumno/03-practica-2-agentes-avanzado.md`.
