# Communication Task Assurance Ontology

Multi-branch layout for the 閫氫俊浠诲姟淇濋殰 scenario.

## Branches

| branch   | content                                                              | path        |
| -------- | -------------------------------------------------------------------- | ----------- |
| backend  | FastAPI service (V4.1, includes evidence / forecast / precheck)       | `backend/`  |
| frontend | Vue 3 + Vite + Element Plus + ECharts app                          | `frontend/` |
| depoly   | OWL ontology / OpenAPI yaml (x2) / MySQL DDL                        | `depoly/`   |
| docs     | V4.1 / V1.1 / V2.1 documents (md + docx)                            | `docs/`     |
| main     | this README                                                         | `README.md` |

## Backend endpoints

`POST /api/scene/start` to start the clock; `GET /api/scene/state` for a full snapshot.

Core (V4.1):

- `POST /api/comm/alarm`      鈥?inject alarm (SK-01)
- `POST /api/comm/switch`     鈥?link fault switch (SK-02)
- `POST /api/comm/occupancy`  鈥?compute current/future/predicted load (SK-03)
- `POST /api/comm/plan`       鈥?generate remediation plan
- `POST /api/comm/approve`    鈥?human decision
- `POST /api/comm/repair`     鈥?repair receipt / done
- `POST /api/comm/restore`    鈥?link restored, task migrated back
- `POST /api/comm/task`       鈥?add task (SK-08)
- `POST /api/comm/link`       鈥?add link (SK-09)
- `POST /api/comm/demand`     鈥?add demand (SK-10)
- `GET  /api/comm/forecast`   鈥?predicted_load staircase points
- `POST /api/comm/precheck/task` 鈥?capacity pre-check (no write)
- `GET  /api/comm/evidence/report` 鈥?T+120 evidence report
- `WS   /api/scene/ws`        鈥?state stream

## Data source

MySQL `zb_db2 @ 172.17.6.242:5904` 路 9 tables:
`comm_task` / `comm_link` / `comm_demand` / `comm_alarm` /
`comm_task_link` / `comm_approval` / `comm_plan` /
`comm_repair_order` / `comm_event`.

## Local dev

```bash
git clone -b backend  https://github.com/Ding-6/comm-task-assurance-ontology.git
git clone -b frontend https://github.com/Ding-6/comm-task-assurance-ontology.git
git clone -b depoly   https://github.com/Ding-6/comm-task-assurance-ontology.git
git clone -b docs     https://github.com/Ding-6/comm-task-assurance-ontology.git
```