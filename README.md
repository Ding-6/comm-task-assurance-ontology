# Communication Task Assurance Ontology

Multi-branch layout for the comm-task-assurance scenario.

## Branches

| branch   | content                                                              | path        |
| -------- | -------------------------------------------------------------------- | ----------- |
| backend  | FastAPI service (V4.1, includes evidence / forecast / precheck)       | backend/    |
| frontend | Vue 3 + Vite + Element Plus + ECharts app                          | frontend/   |
| depoly   | OWL ontology / OpenAPI yaml (x2) / MySQL DDL                        | depoly/     |
| docs     | V4.1 / V1.1 / V2.1 documents (md + docx)                            | docs/       |
| main     | this README                                                         | README.md   |

## Backend endpoints

`POST /api/scene/start` -- start the clock.
`GET /api/scene/state` -- full snapshot.

Core (V4.1):
- `POST /api/comm/alarm`     -- inject alarm (SK-01)
- `POST /api/comm/switch`    -- link fault switch
- `POST /api/comm/occupancy` -- compute current / future / predicted load
- `POST /api/comm/plan`      -- generate remediation plan
- `POST /api/comm/approve`   -- human decision
- `POST /api/comm/repair`    -- repair receipt / done
- `POST /api/comm/restore`   -- link restored, task migrated back
- `POST /api/comm/task`      -- add task
- `POST /api/comm/link`      -- add link
- `POST /api/comm/demand`    -- add demand
- `GET  /api/comm/forecast`  -- predicted_load staircase points
- `POST /api/comm/precheck/task` -- capacity pre-check (no write)
- `GET  /api/comm/evidence/report` -- T+120 evidence report
- `WS   /api/scene/ws`       -- state stream

## Data source

MySQL `zb_db2` on `172.17.6.242:5904`. 9 tables:
comm_task / comm_link / comm_demand / comm_alarm / comm_task_link /
comm_approval / comm_plan / comm_repair_order / comm_event.

## Local dev

```
git clone -b backend  https://github.com/Ding-6/comm-task-assurance-ontology.git
git clone -b frontend https://github.com/Ding-6/comm-task-assurance-ontology.git
git clone -b depoly   https://github.com/Ding-6/comm-task-assurance-ontology.git
git clone -b docs     https://github.com/Ding-6/comm-task-assurance-ontology.git
```