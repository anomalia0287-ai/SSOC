"""
db.py — MySQL 데이터 레이어
─────────────────────────────────────────────
이 코드는 Anthropic Claude Opus의 도움을 받아 작성되었습니다.
─────────────────────────────────────────────
환경 변수:
  DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

테이블:
  channel_configs      — 채널별 봇 설정
  green_buffer         — GREEN 공지 다이제스트 대기열
  classification_stats — 일별·채널별·등급별 분류 통계
  classification_log   — 전체 분류 감사 로그 (선택)
"""

import os, json, logging
from datetime import date, timedelta
from contextlib import contextmanager

import pymysql
from dbutils.pooled_db import PooledDB

logger = logging.getLogger(__name__)

# ── 커넥션 풀 ────────────────────────────────────
_pool: PooledDB | None = None


def init_pool() -> None:
    """앱 시작 시 1회 호출. 커넥션 풀 생성 + 테이블 초기화."""
    global _pool
    _pool = PooledDB(
        creator=pymysql,
        maxconnections=10,
        mincached=2,
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "notice_bot"),
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    _create_tables()
    logger.info("MySQL 커넥션 풀 초기화 완료")


@contextmanager
def _get_conn():
    """커넥션을 풀에서 꺼내고 자동 반환."""
    conn = _pool.connection()
    try:
        yield conn
    finally:
        conn.close()


def _create_tables() -> None:
    """테이블이 없으면 생성."""
    ddl = [
        """
        CREATE TABLE IF NOT EXISTS channel_configs (
            channel_id  VARCHAR(32)  PRIMARY KEY,
            threshold   FLOAT        NOT NULL DEFAULT 0.85,
            digest_hour INT          NOT NULL DEFAULT 18,
            red_mention VARCHAR(16)  NOT NULL DEFAULT 'here',
            admin_users JSON,
            updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS green_buffer (
            id          BIGINT       AUTO_INCREMENT PRIMARY KEY,
            channel_id  VARCHAR(32)  NOT NULL,
            text        TEXT         NOT NULL,
            reason      VARCHAR(500),
            message_ts  VARCHAR(32),
            created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_channel (channel_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS classification_stats (
            id          BIGINT       AUTO_INCREMENT PRIMARY KEY,
            channel_id  VARCHAR(32)  NOT NULL,
            stat_date   DATE         NOT NULL,
            grade       ENUM('RED','YELLOW','GREEN') NOT NULL,
            cnt         INT          NOT NULL DEFAULT 0,
            UNIQUE KEY  uq_ch_date_grade (channel_id, stat_date, grade),
            INDEX       idx_ch_date (channel_id, stat_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS classification_log (
            id               BIGINT       AUTO_INCREMENT PRIMARY KEY,
            channel_id       VARCHAR(32)  NOT NULL,
            message_ts       VARCHAR(32),
            original_text    TEXT,
            grade            ENUM('RED','YELLOW','GREEN') NOT NULL,
            reason           VARCHAR(500),
            emoji            VARCHAR(16),
            stage2_used      BOOLEAN      DEFAULT FALSE,
            overridden       BOOLEAN      DEFAULT FALSE,
            override_reason  VARCHAR(500),
            reclassified_by  VARCHAR(64),
            created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_channel  (channel_id),
            INDEX idx_created  (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    ]
    with _get_conn() as conn:
        with conn.cursor() as cur:
            for stmt in ddl:
                cur.execute(stmt)


# ═══════════════════════════════════════════════
#  channel_configs CRUD
# ═══════════════════════════════════════════════

DEFAULT_CONFIG = {
    "threshold":   0.85,
    "digest_hour": 18,
    "red_mention": "here",
    "admin_users": [],
}


def get_channel_config(channel: str) -> dict:
    """채널 설정 조회. 없으면 기본값 반환."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT threshold, digest_hour, red_mention, admin_users "
                "FROM channel_configs WHERE channel_id = %s",
                (channel,),
            )
            row = cur.fetchone()
    if not row:
        return {**DEFAULT_CONFIG}
    return {
        "threshold":   row["threshold"],
        "digest_hour": row["digest_hour"],
        "red_mention": row["red_mention"],
        "admin_users": json.loads(row["admin_users"]) if row["admin_users"] else [],
    }


def update_channel_config(channel: str, updates: dict) -> None:
    """채널 설정 upsert."""
    cfg = {**DEFAULT_CONFIG, **get_channel_config(channel), **updates}
    admin_json = json.dumps(cfg["admin_users"], ensure_ascii=False)
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO channel_configs
                    (channel_id, threshold, digest_hour, red_mention, admin_users)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    threshold   = VALUES(threshold),
                    digest_hour = VALUES(digest_hour),
                    red_mention = VALUES(red_mention),
                    admin_users = VALUES(admin_users)
                """,
                (channel, cfg["threshold"], cfg["digest_hour"],
                 cfg["red_mention"], admin_json),
            )


def get_all_digest_hours() -> set[int]:
    """등록된 모든 채널의 digest_hour 집합."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT digest_hour FROM channel_configs")
            return {row["digest_hour"] for row in cur.fetchall()}


def get_channels_by_digest_hour(hour: int) -> list[str]:
    """특정 시각에 다이제스트를 받아야 하는 채널 목록."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT channel_id FROM channel_configs WHERE digest_hour = %s",
                (hour,),
            )
            return [row["channel_id"] for row in cur.fetchall()]


def get_configured_channel_count() -> int:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM channel_configs")
            return cur.fetchone()["cnt"]


# ═══════════════════════════════════════════════
#  green_buffer CRUD
# ═══════════════════════════════════════════════

def add_green_item(channel: str, text: str, reason: str, message_ts: str) -> None:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO green_buffer (channel_id, text, reason, message_ts) "
                "VALUES (%s, %s, %s, %s)",
                (channel, text, reason, message_ts),
            )


def pop_green_items(channel: str = None) -> dict[str, list[tuple]]:
    """
    버퍼에서 항목을 꺼내고(삭제) 반환.
    channel 지정 시 해당 채널만, None이면 전체.

    반환: {channel_id: [(text, reason, message_ts), ...]}
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            if channel:
                cur.execute(
                    "SELECT id, channel_id, text, reason, message_ts "
                    "FROM green_buffer WHERE channel_id = %s ORDER BY id",
                    (channel,),
                )
            else:
                cur.execute(
                    "SELECT id, channel_id, text, reason, message_ts "
                    "FROM green_buffer ORDER BY id"
                )
            rows = cur.fetchall()
            if not rows:
                return {}

            ids = [r["id"] for r in rows]
            # 청크 단위 삭제 (IN 절 크기 제한 대비)
            chunk = 500
            for i in range(0, len(ids), chunk):
                batch = ids[i : i + chunk]
                placeholders = ",".join(["%s"] * len(batch))
                cur.execute(
                    f"DELETE FROM green_buffer WHERE id IN ({placeholders})", batch
                )

    result: dict[str, list] = {}
    for r in rows:
        result.setdefault(r["channel_id"], []).append(
            (r["text"], r["reason"], r["message_ts"])
        )
    return result


def restore_green_items(channel: str, items: list[tuple]) -> None:
    """전송 실패 시 버퍼에 복원."""
    if not items:
        return
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO green_buffer (channel_id, text, reason, message_ts) "
                "VALUES (%s, %s, %s, %s)",
                [(channel, t, r, ts) for t, r, ts in items],
            )


# ═══════════════════════════════════════════════
#  classification_stats CRUD
# ═══════════════════════════════════════════════

def increment_stat(channel: str, grade: str) -> None:
    """오늘 날짜 기준 분류 카운트 +1 (UPSERT)."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO classification_stats (channel_id, stat_date, grade, cnt)
                VALUES (%s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE cnt = cnt + 1
                """,
                (channel, date.today(), grade),
            )


def adjust_stat(channel: str, old_grade: str, new_grade: str) -> None:
    """재분류 시 통계 보정: old -1, new +1."""
    today = date.today()
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE classification_stats
                SET cnt = GREATEST(cnt - 1, 0)
                WHERE channel_id = %s AND stat_date = %s AND grade = %s
                """,
                (channel, today, old_grade),
            )
            cur.execute(
                """
                INSERT INTO classification_stats (channel_id, stat_date, grade, cnt)
                VALUES (%s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE cnt = cnt + 1
                """,
                (channel, today, new_grade),
            )


def get_weekly_stats() -> dict[str, dict[str, int]]:
    """
    최근 7일 통계를 채널별로 집계.
    반환: {channel_id: {"RED": n, "YELLOW": n, "GREEN": n}}
    """
    since = date.today() - timedelta(days=7)
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT channel_id, grade, SUM(cnt) AS total
                FROM classification_stats
                WHERE stat_date >= %s
                GROUP BY channel_id, grade
                """,
                (since,),
            )
            rows = cur.fetchall()

    result: dict[str, dict[str, int]] = {}
    for r in rows:
        ch = r["channel_id"]
        result.setdefault(ch, {"RED": 0, "YELLOW": 0, "GREEN": 0})
        result[ch][r["grade"]] = int(r["total"])
    return result


def delete_old_stats(days: int = 30) -> int:
    """오래된 통계 정리. 반환: 삭제 행 수."""
    cutoff = date.today() - timedelta(days=days)
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM classification_stats WHERE stat_date < %s",
                (cutoff,),
            )
            return cur.rowcount


# ═══════════════════════════════════════════════
#  classification_log (감사 로그)
# ═══════════════════════════════════════════════

def insert_log(
    channel: str,
    message_ts: str,
    text: str,
    grade: str,
    reason: str,
    emoji: str = "",
    stage2_used: bool = False,
    overridden: bool = False,
    override_reason: str = None,
    reclassified_by: str = None,
) -> None:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO classification_log
                    (channel_id, message_ts, original_text, grade,
                     reason, emoji, stage2_used, overridden,
                     override_reason, reclassified_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (channel, message_ts, text, grade, reason, emoji,
                 stage2_used, overridden, override_reason, reclassified_by),
            )
