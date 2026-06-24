USE `nagisaki_soyo_digital_waifu`;

-- 1) Inspect the source database structure before importing.
SELECT
    t.table_name,
    t.table_type
FROM information_schema.tables AS t
WHERE t.table_schema = 'xhs_crawler'
ORDER BY t.table_name;

SELECT
    c.table_name,
    c.ordinal_position,
    c.column_name,
    c.column_type,
    c.is_nullable,
    c.column_key
FROM information_schema.columns AS c
WHERE c.table_schema = 'xhs_crawler'
ORDER BY c.table_name, c.ordinal_position;

DROP PROCEDURE IF EXISTS `sp_import_xhs_user_corpus`;

DELIMITER $$

CREATE PROCEDURE `sp_import_xhs_user_corpus`(
    IN p_source_db VARCHAR(64),
    IN p_user_name VARCHAR(64)
)
BEGIN
    DECLARE v_target_db VARCHAR(64) DEFAULT 'nagisaki_soyo_digital_waifu';
    DECLARE v_has_users INT DEFAULT 0;
    DECLARE v_has_notes INT DEFAULT 0;

    DECLARE v_user_id_col VARCHAR(64) DEFAULT NULL;
    DECLARE v_user_name_col VARCHAR(64) DEFAULT NULL;
    DECLARE v_user_bio_col VARCHAR(64) DEFAULT NULL;

    DECLARE v_note_id_col VARCHAR(64) DEFAULT NULL;
    DECLARE v_note_user_fk_col VARCHAR(64) DEFAULT NULL;
    DECLARE v_note_title_col VARCHAR(64) DEFAULT NULL;
    DECLARE v_note_content_col VARCHAR(64) DEFAULT NULL;
    DECLARE v_note_url_col VARCHAR(64) DEFAULT NULL;

    DECLARE v_user_bio_expr TEXT;
    DECLARE v_note_text_expr TEXT;
    DECLARE v_note_url_expr TEXT;
    DECLARE v_sql LONGTEXT;

    SELECT COUNT(*)
    INTO v_has_users
    FROM information_schema.tables
    WHERE table_schema = p_source_db AND table_name = 'users';

    SELECT COUNT(*)
    INTO v_has_notes
    FROM information_schema.tables
    WHERE table_schema = p_source_db AND table_name = 'notes';

    IF v_has_users = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Source database does not contain a users table.';
    END IF;

    SELECT c.column_name
    INTO v_user_id_col
    FROM information_schema.columns AS c
    WHERE c.table_schema = p_source_db
      AND c.table_name = 'users'
      AND c.column_name IN ('user_id', 'id', 'uid')
    ORDER BY FIELD(c.column_name, 'user_id', 'id', 'uid')
    LIMIT 1;

    SELECT c.column_name
    INTO v_user_name_col
    FROM information_schema.columns AS c
    WHERE c.table_schema = p_source_db
      AND c.table_name = 'users'
      AND c.column_name IN ('nickname', 'name', 'display_name', 'username', 'user_name')
    ORDER BY FIELD(c.column_name, 'nickname', 'name', 'display_name', 'username', 'user_name')
    LIMIT 1;

    SELECT c.column_name
    INTO v_user_bio_col
    FROM information_schema.columns AS c
    WHERE c.table_schema = p_source_db
      AND c.table_name = 'users'
      AND c.column_name IN ('description', 'desc', 'bio', 'intro', 'signature')
    ORDER BY FIELD(c.column_name, 'description', 'desc', 'bio', 'intro', 'signature')
    LIMIT 1;

    IF v_user_id_col IS NULL OR v_user_name_col IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'users table is missing a supported user id or user name column.';
    END IF;

    IF v_user_bio_col IS NULL THEN
        SET v_user_bio_expr = 'NULL';
    ELSE
        SET v_user_bio_expr = CONCAT('NULLIF(u.`', v_user_bio_col, '`, '''')');
    END IF;

    SET v_sql = CONCAT(
        'INSERT INTO `', v_target_db, '`.`raw_corpus_entries` (',
        '`corpus_uid`, `source_type`, `source_ref`, `scene`, `speaker_role`, `speaker_name`, ',
        '`content`, `emotion`, `style_label`, `language_code`, `quality_score`, ',
        '`safety_level`, `review_status`, `metadata`',
        ') ',
        'SELECT ',
        'UUID(), ',
        '''imported'', ',
        'CONCAT(', QUOTE(p_source_db), ', ''.users:'', CAST(u.`', v_user_id_col, '` AS CHAR)), ',
        '''profile'', ',
        '''assistant'', ',
        QUOTE(p_user_name), ', ',
        'TRIM(CONCAT_WS(''\n'', ',
        'CONCAT(''昵称: '', u.`', v_user_name_col, '`), ',
        'IFNULL(CONCAT(''简介: '', ', v_user_bio_expr, '), NULL)',
        ')), ',
        'NULL, ',
        '''xhs-user-profile'', ',
        '''zh-CN'', ',
        '6.00, ',
        '0, ',
        '''approved'', ',
        'JSON_OBJECT(',
        '''source_db'', ', QUOTE(p_source_db), ', ',
        '''source_table'', ''users'', ',
        '''matched_user_name'', ', QUOTE(p_user_name), ', ',
        '''source_user_id'', CAST(u.`', v_user_id_col, '` AS CHAR)',
        ') ',
        'FROM `', p_source_db, '`.`users` AS u ',
        'WHERE u.`', v_user_name_col, '` = ', QUOTE(p_user_name), ' ',
        'AND NOT EXISTS (',
        'SELECT 1 FROM `', v_target_db, '`.`raw_corpus_entries` AS t ',
        'WHERE t.`source_ref` = CONCAT(', QUOTE(p_source_db), ', ''.users:'', CAST(u.`', v_user_id_col, '` AS CHAR))',
        ');'
    );

    PREPARE stmt FROM v_sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;

    IF v_has_notes = 1 THEN
        SELECT c.column_name
        INTO v_note_id_col
        FROM information_schema.columns AS c
        WHERE c.table_schema = p_source_db
          AND c.table_name = 'notes'
          AND c.column_name IN ('note_id', 'id')
        ORDER BY FIELD(c.column_name, 'note_id', 'id')
        LIMIT 1;

        SELECT c.column_name
        INTO v_note_user_fk_col
        FROM information_schema.columns AS c
        WHERE c.table_schema = p_source_db
          AND c.table_name = 'notes'
          AND c.column_name IN ('user_id', 'author_id', 'uid')
        ORDER BY FIELD(c.column_name, 'user_id', 'author_id', 'uid')
        LIMIT 1;

        SELECT c.column_name
        INTO v_note_title_col
        FROM information_schema.columns AS c
        WHERE c.table_schema = p_source_db
          AND c.table_name = 'notes'
          AND c.column_name IN ('title', 'note_title')
        ORDER BY FIELD(c.column_name, 'title', 'note_title')
        LIMIT 1;

        SELECT c.column_name
        INTO v_note_content_col
        FROM information_schema.columns AS c
        WHERE c.table_schema = p_source_db
          AND c.table_name = 'notes'
          AND c.column_name IN ('content', 'desc', 'note_content')
        ORDER BY FIELD(c.column_name, 'content', 'desc', 'note_content')
        LIMIT 1;

        SELECT c.column_name
        INTO v_note_url_col
        FROM information_schema.columns AS c
        WHERE c.table_schema = p_source_db
          AND c.table_name = 'notes'
          AND c.column_name IN ('access_url', 'url')
        ORDER BY FIELD(c.column_name, 'access_url', 'url')
        LIMIT 1;

        IF v_note_id_col IS NOT NULL
           AND v_note_user_fk_col IS NOT NULL
           AND (v_note_title_col IS NOT NULL OR v_note_content_col IS NOT NULL) THEN

            IF v_note_title_col IS NOT NULL AND v_note_content_col IS NOT NULL THEN
                SET v_note_text_expr = CONCAT(
                    'TRIM(CONCAT_WS(''\n'', NULLIF(n.`', v_note_title_col, '`, ''''), NULLIF(n.`', v_note_content_col, '`, '''')))'
                );
            ELSEIF v_note_title_col IS NOT NULL THEN
                SET v_note_text_expr = CONCAT('NULLIF(n.`', v_note_title_col, '`, '''')');
            ELSE
                SET v_note_text_expr = CONCAT('NULLIF(n.`', v_note_content_col, '`, '''')');
            END IF;

            IF v_note_url_col IS NULL THEN
                SET v_note_url_expr = 'NULL';
            ELSE
                SET v_note_url_expr = CONCAT('n.`', v_note_url_col, '`');
            END IF;

            SET v_sql = CONCAT(
                'INSERT INTO `', v_target_db, '`.`raw_corpus_entries` (',
                '`corpus_uid`, `source_type`, `source_ref`, `scene`, `speaker_role`, `speaker_name`, ',
                '`content`, `emotion`, `style_label`, `language_code`, `quality_score`, ',
                '`safety_level`, `review_status`, `metadata`',
                ') ',
                'SELECT ',
                'UUID(), ',
                '''imported'', ',
                'CONCAT(', QUOTE(p_source_db), ', ''.notes:'', CAST(n.`', v_note_id_col, '` AS CHAR)), ',
                '''imported'', ',
                '''assistant'', ',
                QUOTE(p_user_name), ', ',
                v_note_text_expr, ', ',
                'NULL, ',
                '''xhs-note'', ',
                '''zh-CN'', ',
                '8.00, ',
                '0, ',
                '''approved'', ',
                'JSON_OBJECT(',
                '''source_db'', ', QUOTE(p_source_db), ', ',
                '''source_table'', ''notes'', ',
                '''matched_user_name'', ', QUOTE(p_user_name), ', ',
                '''source_note_id'', CAST(n.`', v_note_id_col, '` AS CHAR), ',
                '''source_url'', ', v_note_url_expr,
                ') ',
                'FROM `', p_source_db, '`.`notes` AS n ',
                'INNER JOIN `', p_source_db, '`.`users` AS u ',
                'ON n.`', v_note_user_fk_col, '` = u.`', v_user_id_col, '` ',
                'WHERE u.`', v_user_name_col, '` = ', QUOTE(p_user_name), ' ',
                'AND ', v_note_text_expr, ' IS NOT NULL ',
                'AND NOT EXISTS (',
                'SELECT 1 FROM `', v_target_db, '`.`raw_corpus_entries` AS t ',
                'WHERE t.`source_ref` = CONCAT(', QUOTE(p_source_db), ', ''.notes:'', CAST(n.`', v_note_id_col, '` AS CHAR))',
                ');'
            );

            PREPARE stmt FROM v_sql;
            EXECUTE stmt;
            DEALLOCATE PREPARE stmt;
        END IF;
    END IF;
END $$

DELIMITER ;

-- 2) Import profile and note corpus for the specified user.
CALL `sp_import_xhs_user_corpus`('xhs_crawler', '长崎素世');

-- 3) Check what was imported.
SELECT
    source_type,
    style_label,
    COUNT(*) AS row_count
FROM `raw_corpus_entries`
WHERE speaker_name = '长崎素世'
GROUP BY source_type, style_label
ORDER BY source_type, style_label;

SELECT
    id,
    source_ref,
    style_label,
    LEFT(content, 120) AS content_preview,
    created_at
FROM `raw_corpus_entries`
WHERE speaker_name = '长崎素世'
ORDER BY id DESC
LIMIT 20;
