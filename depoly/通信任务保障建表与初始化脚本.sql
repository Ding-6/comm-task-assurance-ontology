-- ============================================================
-- 通信任务保障场景 - MySQL 建表与初始化脚本
-- 引擎: InnoDB | 字符集: utf8mb4 | 排序: utf8mb4_unicode_ci
-- 外键不强制创建（应用层保证一致性），但加 INDEX
-- ============================================================

-- 建议先建库（若已存在可注释）
-- CREATE DATABASE IF NOT EXISTS comm_task_guard
--   DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- USE comm_task_guard;

-- 全部先 DROP（演示场景可重复执行）
DROP TABLE IF EXISTS comm_event;
DROP TABLE IF EXISTS comm_repair_order;
DROP TABLE IF EXISTS comm_approval;
DROP TABLE IF EXISTS comm_plan;
DROP TABLE IF EXISTS comm_alarm;
DROP TABLE IF EXISTS comm_task_link;
DROP TABLE IF EXISTS comm_demand;
DROP TABLE IF EXISTS comm_task;
DROP TABLE IF EXISTS comm_link;

-- ============================================================
-- 1. comm_task 通信任务
-- ============================================================
CREATE TABLE comm_task (
  task_code          varchar(32)  NOT NULL,
  task_name          varchar(64)  NOT NULL,
  duration_min       int          NOT NULL,
  critical_min       int          NULL,
  owner_role         varchar(32)  NULL,
  current_link_code  varchar(32)  NULL,
  initial_demand_gbps decimal(6,2) NOT NULL,
  lookahead_min      int          NULL,
  PRIMARY KEY (task_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='通信任务';

-- ============================================================
-- 2. comm_link 通信链路
-- ============================================================
CREATE TABLE comm_link (
  link_code          varchar(32)  NOT NULL,
  link_name          varchar(64)  NOT NULL,
  capacity_gbps      decimal(6,2) NOT NULL,
  warning_gbps       decimal(6,2) NOT NULL,
  oper_state         varchar(16)  NOT NULL,
  avg_repair_min     int          NULL,
  lookahead_min      int          NULL,
  backup_link_code   varchar(32)  NULL,
  current_load_gbps  decimal(6,2) NULL,
  future_load_gbps   decimal(6,2) NULL,
  warn_status        varchar(16)  NULL,
  PRIMARY KEY (link_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='通信链路';

-- ============================================================
-- 3. comm_demand 流量需求
-- ============================================================
CREATE TABLE comm_demand (
  demand_code     varchar(32)  NOT NULL,
  task_code       varchar(32)  NOT NULL,
  valid_from_min  int          NOT NULL,
  demand_gbps     decimal(6,2) NOT NULL,
  valid_to_min    int          NULL,
  PRIMARY KEY (demand_code),
  KEY idx_demand_task (task_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='流量需求';

-- ============================================================
-- 4. comm_alarm 资源告警
-- ============================================================
CREATE TABLE comm_alarm (
  alarm_code       varchar(32) NOT NULL,
  link_code        varchar(32) NOT NULL,
  alarm_type       varchar(32) NOT NULL,
  native_severity  varchar(16) NOT NULL,
  event_min        int         NOT NULL,
  predicted_min    int         NULL,
  PRIMARY KEY (alarm_code),
  KEY idx_alarm_link (link_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='资源告警';

-- ============================================================
-- 5. comm_task_link 任务链路归属历史
-- ============================================================
CREATE TABLE comm_task_link (
  id            INT         NOT NULL AUTO_INCREMENT,
  task_code     varchar(32) NOT NULL,
  link_code     varchar(32) NOT NULL,
  assigned_min  int         NOT NULL,
  note          varchar(128) NULL,
  PRIMARY KEY (id),
  -- 唯一约束：同一任务在同一 assigned_min 只能有一条归属行。
  -- 对齐说明书 §5.1「(task_code, assigned_min) 联合主键」语义；
  -- 由于 surrogate id 仍是真主键，靠 id 排序支持同分钟多次切换的留痕。
  UNIQUE KEY uk_task_min (task_code, assigned_min),
  INDEX idx_task_link_task (task_code),
  INDEX idx_task_link_link (link_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='任务链路归属历史（surrogate id 主键 + (task_code, assigned_min) 唯一约束）';

-- ============================================================
-- 6. comm_approval 审批记录
-- ============================================================
CREATE TABLE comm_approval (
  approval_code    varchar(64)  NOT NULL,
  plan_code        varchar(128) NULL,
  decision         varchar(16)  NULL,
  reason           varchar(512) NULL,
  approver         varchar(64)  NULL,
  decision_source  varchar(16)  NULL,
  decided_min      int          NULL,
  PRIMARY KEY (approval_code),
  KEY idx_approval_plan (plan_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='审批记录';

-- ============================================================
-- 7. comm_plan 处置方案
-- ============================================================
CREATE TABLE comm_plan (
  plan_code               varchar(128)  NOT NULL,
  alarm_code              varchar(32)   NOT NULL,
  plan_type               varchar(16)   NOT NULL,
  link_code               varchar(32)   NOT NULL,
  target_link_code        varchar(32)   NULL,
  est_repair_min          int           NULL,
  predicted_load_after_gbps decimal(6,2) NULL,
  can_meet_critical       varchar(8)    NULL,
  status                  varchar(16)   NULL,
  is_default              varchar(8)    NULL,
  recommendation          varchar(512)  NULL,
  generated_min           int           NULL,
  PRIMARY KEY (plan_code),
  KEY idx_plan_alarm (alarm_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='处置方案';

-- ============================================================
-- 8. comm_repair_order 修理单
-- ============================================================
CREATE TABLE comm_repair_order (
  order_code        varchar(64) NOT NULL,
  link_code         varchar(32) NOT NULL,
  alarm_code        varchar(32) NULL,
  request_min       int         NOT NULL,
  est_finish_min    int         NULL,
  actual_finish_min int         NULL,
  status            varchar(16) NULL,
  PRIMARY KEY (order_code),
  KEY idx_repair_link (link_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='修理单';

-- ============================================================
-- 9. comm_event 场景事件流水
-- ============================================================
CREATE TABLE comm_event (
  event_code  varchar(64)  NOT NULL,
  event_type  varchar(32)  NOT NULL,
  ref_type    varchar(32)  NULL,
  ref_code    varchar(64)  NULL,
  occur_min   int          NOT NULL,
  summary     varchar(256) NULL,
  PRIMARY KEY (event_code),
  KEY idx_event_type (event_type),
  KEY idx_event_occur (occur_min)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='场景事件流水';

-- ============================================================
-- 初始化数据
-- ============================================================

-- 3 条链路
INSERT INTO comm_link VALUES
('L-1H','指挥通信主用电路',10.00,8.00,'up',30,30,'L-3H',0.00,0.00,'正常'),
('L-2H','直播与既有共享电路',10.00,8.00,'up',30,30,NULL,0.00,0.00,'正常'),
('L-3H','指挥通信备用电路',10.00,8.00,'up',30,30,NULL,0.00,0.00,'正常');

-- 3 项任务
INSERT INTO comm_task VALUES
('T-A','指挥通信保障',120,NULL,'ROLE-DUTY','L-1H',3.00,30),
('T-B','直播传输保障',120,50,'ROLE-B','L-2H',4.00,30),
('T-C','既有传输保障',120,NULL,'ROLE-DUTY','L-2H',2.00,30);

-- 3 条初始需求（D-B2 在 T+50 由预订事件兑现时再插入）
INSERT INTO comm_demand VALUES
('D-A','T-A',0,3.00,NULL),
('D-B1','T-B',0,4.00,50),
('D-C','T-C',0,2.00,NULL);

-- 3 条初始归属
INSERT INTO comm_task_link (task_code, link_code, assigned_min, note) VALUES
('T-A','L-1H',0,'场景初始归属'),
('T-B','L-2H',0,'场景初始归属'),
('T-C','L-2H',0,'场景初始归属');

-- 2条预置预订事件（到点兑现）
-- EVT-0001：T+15 注入 L-1H link_down 告警（ref_code 即 link_code）
-- EVT-0002：T+50 注入 D-B2 需求（ref_code 需求码；summary 编码 task= 与 gbps=）
INSERT INTO comm_event VALUES
('EVT-0001','task_booked','alarm','L-1H',15,'15分钟后线路1故障，预订为T+15兑现'),
('EVT-0002','task_booked','demand','D-B2',50,'task=T-B;gbps=6.00;50分钟后直播需求到6.00G');
