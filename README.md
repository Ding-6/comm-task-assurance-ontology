# 閫氫俊淇濋殰鏈綋鍦烘櫙 路 comm-task-assurance-ontology

鏈粨搴撴寜鍒嗘敮绠＄悊閫氫俊浠诲姟淇濋殰鍦烘櫙鐨勫畬鏁磋祫浜э紝閬垮厤鍗曞垎鏀法鍨嬩粨搴撱€?

## 鍒嗘敮

| 鍒嗘敮 | 鍐呭 | 璺緞 |
|------|------|------|
| \ackend\  | FastAPI 鍚庣鏈嶅姟锛圴4.1 閲嶆瀯锛屽惈 evidence / forecast / precheck 涓変釜鏂版湇鍔★級 | \ackend/\ |
| \rontend\ | Vue 3 + Vite + Element Plus + ECharts 鍓嶇宸ョ▼ | \rontend/\ |
| \depoly\   | 閮ㄧ讲浜х墿锛歄WL 鏈綋 / OpenAPI yaml / MySQL 寤鸿〃鑴氭湰 | \depoly/\ |
| \docs\     | 涓変唤璇存槑涔?V4.1 / V1.1 / V2.1 鐨?md 鍓湰 + docx | \docs/\ |
| \main\     | 鏈?README | \README.md\ |

## 鑱旇皟

- 鍚庣鍏ュ彛锛歕POST /api/scene/start\ 鈫?鏃堕挓鍚姩锛沑GET /api/scene/state\ 鈫?鍏ㄩ噺蹇収
- 鍏抽敭鎺ュ彛锛圴4.1锛夛細\/api/comm/alarm\銆乗/api/comm/switch\銆乗/api/comm/occupancy\銆乗/api/comm/plan\銆乗/api/comm/approve\銆乗/api/comm/repair\銆乗/api/comm/restore\銆乗/api/comm/task\銆乗/api/comm/link\銆乗/api/comm/demand\
- 鎵╁睍锛歕/api/comm/forecast\銆乗/api/comm/precheck/task\銆乗/api/comm/evidence/report\
- WebSocket锛歕/api/scene/ws\

## 鏁版嵁婧?

MySQL \zb_db2 @ 172.17.6.242:5904\ 路 9 寮犺〃锛坈omm_task / comm_link / comm_demand / comm_alarm / comm_task_link / comm_approval / comm_plan / comm_repair_order / comm_event锛?

## 鏈湴寮€鍙?

\\\ash
# 鎷夊彇瀵瑰簲鍒嗘敮
git clone -b backend  https://github.com/Ding-6/comm-task-assurance-ontology.git
git clone -b frontend https://github.com/Ding-6/comm-task-assurance-ontology.git
git clone -b depoly   https://github.com/Ding-6/comm-task-assurance-ontology.git
git clone -b docs     https://github.com/Ding-6/comm-task-assurance-ontology.git
\\\