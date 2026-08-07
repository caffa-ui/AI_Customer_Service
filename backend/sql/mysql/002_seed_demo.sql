START TRANSACTION;

INSERT INTO users (user_id, user_name, gender, status) VALUES
    ('cli-user', 'CLI 测试用户', NULL, 'active'),
    ('demo-user', '演示用户', NULL, 'active'),
    ('test-user-003', '隔离测试用户', NULL, 'active')
ON DUPLICATE KEY UPDATE user_id = users.user_id;

INSERT INTO user_tags (user_id, tag) VALUES
    ('cli-user', '办公'),
    ('cli-user', '轻薄'),
    ('demo-user', '高性能'),
    ('test-user-003', '耳机')
ON DUPLICATE KEY UPDATE user_id = user_tags.user_id;

INSERT INTO products (
    product_id,
    name,
    category,
    price,
    summary,
    specifications,
    keywords,
    is_active
) VALUES
    (
        'P-1001',
        '轻薄商务本 Air 14',
        '笔记本电脑',
        4999.00,
        '适合日常办公和差旅，重量较轻，续航表现均衡。',
        JSON_OBJECT(
            '处理器', '8 核移动处理器',
            '内存', '16GB',
            '存储', '512GB SSD',
            '屏幕', '14 英寸 2.2K'
        ),
        JSON_ARRAY('办公', '轻薄', '差旅', '性价比'),
        1
    ),
    (
        'P-1002',
        '性能游戏本 Pro 16',
        '笔记本电脑',
        7999.00,
        '面向游戏和内容创作，提供独立显卡和高刷新率屏幕。',
        JSON_OBJECT(
            '处理器', '14 核高性能处理器',
            '内存', '32GB',
            '存储', '1TB SSD',
            '显卡', '独立显卡 8GB',
            '屏幕', '16 英寸 165Hz'
        ),
        JSON_ARRAY('游戏', '设计', '高性能', '发烧友'),
        1
    ),
    (
        'P-2001',
        '降噪真无线耳机 Lite',
        '耳机',
        399.00,
        '支持主动降噪和多设备切换，适合通勤与日常通话。',
        JSON_OBJECT(
            '续航', '单次 8 小时，含充电盒 30 小时',
            '连接', '蓝牙 5.3',
            '防护', 'IP54'
        ),
        JSON_ARRAY('通勤', '降噪', '蓝牙', '耳机'),
        1
    ),
    (
        'P-3001',
        '人体工学办公椅 E1',
        '办公家具',
        1299.00,
        '提供腰托、头枕和扶手多向调节，适合长时间办公。',
        JSON_OBJECT(
            '承重', '120kg',
            '材质', '高弹网布',
            '调节', '腰托、头枕、扶手、坐深'
        ),
        JSON_ARRAY('办公', '久坐', '人体工学', '椅子'),
        1
    )
ON DUPLICATE KEY UPDATE product_id = products.product_id;

INSERT INTO product_inventory (product_id, stock) VALUES
    ('P-1001', 18),
    ('P-1002', 7),
    ('P-2001', 0),
    ('P-3001', 12)
ON DUPLICATE KEY UPDATE product_id = product_inventory.product_id;

INSERT INTO product_promotions (
    promotion_id,
    product_id,
    description,
    start_at,
    end_at,
    is_active
) VALUES
    (
        'PROMO-P1001-01',
        'P-1001',
        '满 4999 元赠无线鼠标',
        '2026-01-01 00:00:00',
        '2027-12-31 23:59:59',
        1
    ),
    (
        'PROMO-P1001-02',
        'P-1001',
        '支持 6 期免息',
        '2026-01-01 00:00:00',
        '2027-12-31 23:59:59',
        1
    ),
    (
        'PROMO-P1002-01',
        'P-1002',
        '限时直降 300 元',
        '2026-01-01 00:00:00',
        '2027-12-31 23:59:59',
        1
    ),
    (
        'PROMO-P1002-02',
        'P-1002',
        '支持 12 期免息',
        '2026-01-01 00:00:00',
        '2027-12-31 23:59:59',
        1
    ),
    (
        'PROMO-P3001-01',
        'P-3001',
        '到手价 1199 元',
        '2026-01-01 00:00:00',
        '2027-12-31 23:59:59',
        1
    )
ON DUPLICATE KEY UPDATE promotion_id = product_promotions.promotion_id;

INSERT INTO orders (
    order_id,
    user_id,
    status,
    created_at,
    total_amount,
    carrier,
    tracking_number,
    logistics_status,
    latest_logistics,
    estimated_delivery
) VALUES
    (
        'ORD-20260801',
        'cli-user',
        'shipped',
        '2026-08-01 09:30:00',
        4999.00,
        '顺丰速运',
        'SF1234567890',
        '运输中',
        '包裹已到达上海转运中心',
        '2026-08-08 23:59:59'
    ),
    (
        'ORD-20260720',
        'cli-user',
        'completed',
        '2026-07-20 14:10:00',
        399.00,
        '京东物流',
        'JD9876543210',
        '已签收',
        '本人已签收',
        '2026-07-22 23:59:59'
    ),
    (
        'ORD-PRIVATE-01',
        'demo-user',
        'processing',
        '2026-08-02 11:00:00',
        7999.00,
        NULL,
        NULL,
        '待发货',
        '仓库正在配货',
        NULL
    )
ON DUPLICATE KEY UPDATE order_id = orders.order_id;

INSERT INTO order_items (
    order_item_id,
    order_id,
    product_id,
    product_name,
    quantity,
    unit_price
) VALUES
    ('OI-20260801-01', 'ORD-20260801', 'P-1001', '轻薄商务本 Air 14', 1, 4999.00),
    ('OI-20260720-01', 'ORD-20260720', 'P-2001', '降噪真无线耳机 Lite', 1, 399.00),
    ('OI-PRIVATE-01-01', 'ORD-PRIVATE-01', 'P-1002', '性能游戏本 Pro 16', 1, 7999.00)
ON DUPLICATE KEY UPDATE order_item_id = order_items.order_item_id;

INSERT INTO support_tickets (
    ticket_id,
    user_id,
    order_id,
    ticket_type,
    status,
    subject,
    description,
    latest_note,
    created_at
) VALUES
    (
        'TK-20001',
        'cli-user',
        'ORD-20260801',
        'logistics',
        'processing',
        '订单物流长时间未更新',
        '用户反馈物流三天没有变化。',
        '已经联系物流服务商核查',
        '2026-08-07 10:00:00'
    ),
    (
        'TK-20002',
        'cli-user',
        'ORD-20260720',
        'repair',
        'pending',
        '耳机单侧没有声音',
        '用户已经重新配对设备，问题仍然存在。',
        '等待售后人员确认处理方式',
        '2026-08-07 11:00:00'
    ),
    (
        'TK-20003',
        'demo-user',
        'ORD-PRIVATE-01',
        'repair',
        'resolved',
        '游戏本无法正常启动',
        '设备按下电源键后没有显示。',
        '已经完成返厂维修',
        '2026-08-05 09:20:00'
    ),
    (
        'TK-20004',
        'test-user-003',
        NULL,
        'general',
        'processing',
        '商品使用咨询',
        '用户需要人工客服协助确认使用方法。',
        '人工客服正在处理中',
        '2026-08-06 15:30:00'
    )
ON DUPLICATE KEY UPDATE ticket_id = support_tickets.ticket_id;

COMMIT;
