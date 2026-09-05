-- 为已有数据库补充模拟退款审核所需字段。
ALTER TABLE support_tickets
    ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
    ADD COLUMN IF NOT EXISTS refund_thread_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
    ADD COLUMN IF NOT EXISTS reviewer_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
    ADD COLUMN IF NOT EXISTS review_note VARCHAR(1000) NULL,
    ADD COLUMN IF NOT EXISTS reviewed_at DATETIME(6) NULL,
    ADD INDEX IF NOT EXISTS idx_support_tickets_refund_status (ticket_type, status, created_at);
