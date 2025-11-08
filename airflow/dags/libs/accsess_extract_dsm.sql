/* mart_dsm_sale */

/* 1. Аксессор получения актуального среза на конкретную дату обработки*/
CREATE VIEW stg.v_sn_mart_dsm_sale
AS 
select t1.* except (processed_dttm_max), processed_dttm_max as processed_dttm
from (
SELECT 
    cd_reg,
    cd_u,
    stat_year,
    stat_month,
    sales_type_id,
    effective_dttm,
    -- Все числовые метрики
    argMax(volsht_out, processed_dttm) as volsht_out,
    argMax(volrub_out, processed_dttm) as volrub_out,
    argMax(volsht_in, processed_dttm) as volsht_in,
    argMax(volrub_in, processed_dttm) as volrub_in,
    argMax(prcavg_w_in, processed_dttm) as prcavg_w_in,
    argMax(prcavg_w_out, processed_dttm) as prcavg_w_out,
    argMax(pred_pn, processed_dttm) as pred_pn,
    argMax(pred_pn_firm, processed_dttm) as pred_pn_firm,
    argMax(pred_tn, processed_dttm) as pred_tn,
    argMax(pred_tn_firm, processed_dttm) as pred_tn_firm,
    argMax(pred_br, processed_dttm) as pred_br,
    argMax(pred_br_firm, processed_dttm) as pred_br_firm,
    argMax(wpred_pn, processed_dttm) as wpred_pn,
    argMax(wpred_pn_firm, processed_dttm) as wpred_pn_firm,
    argMax(wpred_tn, processed_dttm) as wpred_tn,
    argMax(wpred_tn_firm, processed_dttm) as wpred_tn_firm,
    argMax(wpred_br, processed_dttm) as wpred_br,
    argMax(wpred_br_firm, processed_dttm) as wpred_br_firm,
    -- Технические поля
    argMax(deleted_flag, processed_dttm) as deleted_flag,
    argMax(hash_diff, processed_dttm) as hash_diff,
    max(processed_dttm) as processed_dttm_max
FROM stg.mart_dsm_sale
GROUP BY 
    cd_reg, cd_u, stat_year, stat_month, sales_type_id, effective_dttm
HAVING deleted_flag = false
) t1;

select * from stg.v_sn_mart_dsm_sale;

/* 2. Аксессор получения актуального среза на конкретную версию-дату */
CREATE VIEW IF NOT EXISTS stg.v_sv_mart_dsm_sale ON CLUSTER cluster_2S_2R
AS 
    select t1.* except (processed_dttm_max), processed_dttm_max as processed_dttm
    from (
    SELECT 
        cd_reg,
        cd_u,
        stat_year,
        stat_month,
        sales_type_id,
        effective_dttm,
        -- Все метрики через argMax
        argMax(volsht_out, processed_dttm) as volsht_out,
        argMax(volrub_out, processed_dttm) as volrub_out,
        argMax(volsht_in, processed_dttm) as volsht_in,
        argMax(volrub_in, processed_dttm) as volrub_in,
        argMax(prcavg_w_in, processed_dttm) as prcavg_w_in,
        argMax(prcavg_w_out, processed_dttm) as prcavg_w_out,
        argMax(pred_pn, processed_dttm) as pred_pn,
        argMax(pred_pn_firm, processed_dttm) as pred_pn_firm,
        argMax(pred_tn, processed_dttm) as pred_tn,
        argMax(pred_tn_firm, processed_dttm) as pred_tn_firm,
        argMax(pred_br, processed_dttm) as pred_br,
        argMax(pred_br_firm, processed_dttm) as pred_br_firm,
        argMax(wpred_pn, processed_dttm) as wpred_pn,
        argMax(wpred_pn_firm, processed_dttm) as wpred_pn_firm,
        argMax(wpred_tn, processed_dttm) as wpred_tn,
        argMax(wpred_tn_firm, processed_dttm) as wpred_tn_firm,
        argMax(wpred_br, processed_dttm) as wpred_br,
        argMax(wpred_br_firm, processed_dttm) as wpred_br_firm,
        -- Технические поля
        argMax(deleted_flag, processed_dttm) as deleted_flag,
        argMax(hash_diff, processed_dttm) as hash_diff,
        max(processed_dttm) as processed_dttm_max
    FROM stg.mart_dsm_sale
    WHERE processed_dttm <= {p_processed_dttm_user:DateTime}
    GROUP BY cd_reg, cd_u, stat_year, stat_month, sales_type_id, effective_dttm
    HAVING deleted_flag = false
    ) t1;

SELECT * FROM stg.v_sv_mart_dsm_sale (p_processed_dttm_user = '2025-10-27');

/* 3. Аксессор получения инкремента для */
CREATE VIEW IF NOT EXISTS stg.v_iv_mart_dsm_sale ON CLUSTER cluster_2S_2R
AS 
	select t1.* except (processed_dttm_max), processed_dttm_max as processed_dttm
    from (
    SELECT 
        cd_reg,
        cd_u,
        stat_year,
        stat_month,
        sales_type_id,
        effective_dttm,
        -- Все метрики через argMax
        argMax(volsht_out, processed_dttm) as volsht_out,
        argMax(volrub_out, processed_dttm) as volrub_out,
        argMax(volsht_in, processed_dttm) as volsht_in,
        argMax(volrub_in, processed_dttm) as volrub_in,
        argMax(prcavg_w_in, processed_dttm) as prcavg_w_in,
        argMax(prcavg_w_out, processed_dttm) as prcavg_w_out,
        argMax(pred_pn, processed_dttm) as pred_pn,
        argMax(pred_pn_firm, processed_dttm) as pred_pn_firm,
        argMax(pred_tn, processed_dttm) as pred_tn,
        argMax(pred_tn_firm, processed_dttm) as pred_tn_firm,
        argMax(pred_br, processed_dttm) as pred_br,
        argMax(pred_br_firm, processed_dttm) as pred_br_firm,
        argMax(wpred_pn, processed_dttm) as wpred_pn,
        argMax(wpred_pn_firm, processed_dttm) as wpred_pn_firm,
        argMax(wpred_tn, processed_dttm) as wpred_tn,
        argMax(wpred_tn_firm, processed_dttm) as wpred_tn_firm,
        argMax(wpred_br, processed_dttm) as wpred_br,
        argMax(wpred_br_firm, processed_dttm) as wpred_br_firm,
        -- Технические поля
        argMax(deleted_flag, processed_dttm) as deleted_flag,
        argMax(hash_diff, processed_dttm) as hash_diff,
        max(processed_dttm) as processed_dttm_max
    FROM stg.mart_dsm_sale
    WHERE processed_dttm between {p_from_dttm: DateTime} and {p_to_dttm:DateTime}
    GROUP BY cd_reg, cd_u, stat_year, stat_month, sales_type_id, effective_dttm
    HAVING deleted_flag = false
    ) t1;

SELECT * FROM stg.v_iv_mart_dsm_sale (p_from_dttm = '2025-10-26', p_to_dttm = '2025-10-27');

    /* mart_dsm_stat_product */

    /* 1. Аксессор получения актуального среза на конкретную дату обработки*/
CREATE VIEW IF NOT EXISTS stg.v_sn_mart_dsm_stat_product ON CLUSTER cluster_2S_2R
AS 
	select t1.* except (processed_dttm_max), processed_dttm_max as processed_dttm
    from (
    select
	    cd_u,
	    argMax(nm_atc5, processed_dttm) as nm_atc5,
	    argMax(original, processed_dttm) as original,
	    argMax(brended, processed_dttm) as brended,
	    argMax(recipereq, processed_dttm) as recipereq,
	    argMax(jnvlp, processed_dttm) as jnvlp,
	    argMax(ephmra1, processed_dttm) as ephmra1,
	    argMax(nm_ephmra1, processed_dttm) as nm_ephmra1,
	    argMax(ephmra2, processed_dttm) as ephmra2,
	    argMax(nm_ephmra2, processed_dttm) as nm_ephmra2,
	    argMax(ephmra3, processed_dttm) as ephmra3,
	    argMax(nm_ephmra3, processed_dttm) as nm_ephmra3,
	    argMax(ephmra4, processed_dttm) as ephmra4,
	    argMax(nm_ephmra4, processed_dttm) as nm_ephmra4,
	    argMax(nm_ti, processed_dttm) as nm_ti,
	    argMax(farm_group, processed_dttm) as farm_group,
	    argMax(localized_status, processed_dttm) as localized_status,
	    argMax(nm_f, processed_dttm) as nm_f,
	    argMax(bad1, processed_dttm) as bad1,
	    argMax(nm_bad1, processed_dttm) as nm_bad1,
	    argMax(bad2, processed_dttm) as bad2,
	    argMax(nm_bad2, processed_dttm) as nm_bad2,
	    argMax(kk1_1, processed_dttm) as kk1_1,
	    argMax(kk1_name_am, processed_dttm) as kk1_name_am,
	    argMax(kk2, processed_dttm) as kk2,
	    argMax(kk2_name_vozr, processed_dttm) as kk2_name_vozr,
	    argMax(kk3_1, processed_dttm) as kk3_1,
	    argMax(kk3_name_deistv, processed_dttm) as kk3_name_deistv,
	    argMax(kk4_1, processed_dttm) as kk4_1,
	    argMax(kk4_name_pokaz, processed_dttm) as kk4_name_pokaz,
	    argMax(nm_dt, processed_dttm) as nm_dt,
	    argMax(cd_ias, processed_dttm) as cd_ias,
	    argMax(nm_full, processed_dttm) as nm_full,
	    argMax(nm_t, processed_dttm) as nm_t,
	    argMax(nm_br, processed_dttm) as nm_br,
	    argMax(nm_pack, processed_dttm) as nm_pack,
	    argMax(group_nm_rus, processed_dttm) as group_nm_rus,
	    argMax(corp, processed_dttm) as corp,
	    argMax(nm_d, processed_dttm) as nm_d,
	    argMax(mv, processed_dttm) as mv,
	    argMax(mv_nm_mu, processed_dttm) as mv_nm_mu,
	    argMax(count_in_bl, processed_dttm) as count_in_bl,
	    argMax(count_bl, processed_dttm) as count_bl,
	    argMax(nm_c, processed_dttm) as nm_c,
	    argMax(atc1, processed_dttm) as atc1,
	    argMax(nm_atc1, processed_dttm) as nm_atc1,
	    argMax(atc2, processed_dttm) as atc2,
	    argMax(nm_atc2, processed_dttm) as nm_atc2,
	    argMax(atc3, processed_dttm) as atc3,
	    argMax(nm_atc3, processed_dttm) as nm_atc3,
	    argMax(atc4, processed_dttm) as atc4,
	    argMax(nm_atc4, processed_dttm) as nm_atc4,
	    argMax(atc5, processed_dttm) as atc5,
	    -- Технические поля
	    argMax(deleted_flag, processed_dttm) as deleted_flag,
	    argMax(hash_diff, processed_dttm) as hash_diff,
	    max(processed_dttm) as processed_dttm_max
FROM stg.mart_dsm_stat_product
GROUP BY 
    cd_u
HAVING deleted_flag = false
) t1;

SELECT * FROM stg.v_sn_mart_dsm_stat_product;


/* 2. Аксессор получения актуального среза на конкретную версию-дату */
CREATE VIEW IF NOT EXISTS stg.v_sv_mart_dsm_stat_product ON CLUSTER cluster_2S_2R
AS 
	select t1.* except (processed_dttm_max), processed_dttm_max as processed_dttm
    from (
    	select 
	        cd_u,
	        argMax(nm_atc5, processed_dttm) as nm_atc5,
	        argMax(original, processed_dttm) as original,
	        argMax(brended, processed_dttm) as brended,
	        argMax(recipereq, processed_dttm) as recipereq,
	        argMax(jnvlp, processed_dttm) as jnvlp,
	        argMax(ephmra1, processed_dttm) as ephmra1,
	        argMax(nm_ephmra1, processed_dttm) as nm_ephmra1,
	        argMax(ephmra2, processed_dttm) as ephmra2,
	        argMax(nm_ephmra2, processed_dttm) as nm_ephmra2,
	        argMax(ephmra3, processed_dttm) as ephmra3,
	        argMax(nm_ephmra3, processed_dttm) as nm_ephmra3,
	        argMax(ephmra4, processed_dttm) as ephmra4,
	        argMax(nm_ephmra4, processed_dttm) as nm_ephmra4,
	        argMax(nm_ti, processed_dttm) as nm_ti,
	        argMax(farm_group, processed_dttm) as farm_group,
	        argMax(localized_status, processed_dttm) as localized_status,
	        argMax(nm_f, processed_dttm) as nm_f,
	        argMax(bad1, processed_dttm) as bad1,
	        argMax(nm_bad1, processed_dttm) as nm_bad1,
	        argMax(bad2, processed_dttm) as bad2,
	        argMax(nm_bad2, processed_dttm) as nm_bad2,
	        argMax(kk1_1, processed_dttm) as kk1_1,
	        argMax(kk1_name_am, processed_dttm) as kk1_name_am,
	        argMax(kk2, processed_dttm) as kk2,
	        argMax(kk2_name_vozr, processed_dttm) as kk2_name_vozr,
	        argMax(kk3_1, processed_dttm) as kk3_1,
	        argMax(kk3_name_deistv, processed_dttm) as kk3_name_deistv,
	        argMax(kk4_1, processed_dttm) as kk4_1,
	        argMax(kk4_name_pokaz, processed_dttm) as kk4_name_pokaz,
	        argMax(nm_dt, processed_dttm) as nm_dt,
	        argMax(cd_ias, processed_dttm) as cd_ias,
	        argMax(nm_full, processed_dttm) as nm_full,
	        argMax(nm_t, processed_dttm) as nm_t,
	        argMax(nm_br, processed_dttm) as nm_br,
	        argMax(nm_pack, processed_dttm) as nm_pack,
	        argMax(group_nm_rus, processed_dttm) as group_nm_rus,
	        argMax(corp, processed_dttm) as corp,
	        argMax(nm_d, processed_dttm) as nm_d,
	        argMax(mv, processed_dttm) as mv,
	        argMax(mv_nm_mu, processed_dttm) as mv_nm_mu,
	        argMax(count_in_bl, processed_dttm) as count_in_bl,
	        argMax(count_bl, processed_dttm) as count_bl,
	        argMax(nm_c, processed_dttm) as nm_c,
	        argMax(atc1, processed_dttm) as atc1,
	        argMax(nm_atc1, processed_dttm) as nm_atc1,
	        argMax(atc2, processed_dttm) as atc2,
	        argMax(nm_atc2, processed_dttm) as nm_atc2,
	        argMax(atc3, processed_dttm) as atc3,
	        argMax(nm_atc3, processed_dttm) as nm_atc3,
	        argMax(atc4, processed_dttm) as atc4,
	        argMax(nm_atc4, processed_dttm) as nm_atc4,
	        argMax(atc5, processed_dttm) as atc5,
	        -- Технические поля
	        argMax(deleted_flag, processed_dttm) as deleted_flag,
	        argMax(hash_diff, processed_dttm) as hash_diff,
	        max(processed_dttm) as processed_dttm_max
    FROM stg.mart_dsm_stat_product
    WHERE processed_dttm  <= {p_processed_dttm_user:DateTime}
    GROUP BY cd_u
    HAVING deleted_flag = false
    ) t1;


SELECT * FROM stg.v_sv_mart_dsm_stat_product (p_processed_dttm_user = '2025-10-27'); 

/* 3. Аксессор получения инкремента для */
CREATE VIEW IF NOT EXISTS stg.v_iv_mart_dsm_stat_product ON CLUSTER cluster_2S_2R
AS 
	select t1.* except (processed_dttm_max), processed_dttm_max as processed_dttm
    from (
    select 
        cd_u,
        argMax(nm_atc5, processed_dttm) as nm_atc5,
        argMax(original, processed_dttm) as original,
        argMax(brended, processed_dttm) as brended,
        argMax(recipereq, processed_dttm) as recipereq,
        argMax(jnvlp, processed_dttm) as jnvlp,
        argMax(ephmra1, processed_dttm) as ephmra1,
        argMax(nm_ephmra1, processed_dttm) as nm_ephmra1,
        argMax(ephmra2, processed_dttm) as ephmra2,
        argMax(nm_ephmra2, processed_dttm) as nm_ephmra2,
        argMax(ephmra3, processed_dttm) as ephmra3,
        argMax(nm_ephmra3, processed_dttm) as nm_ephmra3,
        argMax(ephmra4, processed_dttm) as ephmra4,
        argMax(nm_ephmra4, processed_dttm) as nm_ephmra4,
        argMax(nm_ti, processed_dttm) as nm_ti,
        argMax(farm_group, processed_dttm) as farm_group,
        argMax(localized_status, processed_dttm) as localized_status,
        argMax(nm_f, processed_dttm) as nm_f,
        argMax(bad1, processed_dttm) as bad1,
        argMax(nm_bad1, processed_dttm) as nm_bad1,
        argMax(bad2, processed_dttm) as bad2,
        argMax(nm_bad2, processed_dttm) as nm_bad2,
        argMax(kk1_1, processed_dttm) as kk1_1,
        argMax(kk1_name_am, processed_dttm) as kk1_name_am,
        argMax(kk2, processed_dttm) as kk2,
        argMax(kk2_name_vozr, processed_dttm) as kk2_name_vozr,
        argMax(kk3_1, processed_dttm) as kk3_1,
        argMax(kk3_name_deistv, processed_dttm) as kk3_name_deistv,
        argMax(kk4_1, processed_dttm) as kk4_1,
        argMax(kk4_name_pokaz, processed_dttm) as kk4_name_pokaz,
        argMax(nm_dt, processed_dttm) as nm_dt,
        argMax(cd_ias, processed_dttm) as cd_ias,
        argMax(nm_full, processed_dttm) as nm_full,
        argMax(nm_t, processed_dttm) as nm_t,
        argMax(nm_br, processed_dttm) as nm_br,
        argMax(nm_pack, processed_dttm) as nm_pack,
        argMax(group_nm_rus, processed_dttm) as group_nm_rus,
        argMax(corp, processed_dttm) as corp,
        argMax(nm_d, processed_dttm) as nm_d,
        argMax(mv, processed_dttm) as mv,
        argMax(mv_nm_mu, processed_dttm) as mv_nm_mu,
        argMax(count_in_bl, processed_dttm) as count_in_bl,
        argMax(count_bl, processed_dttm) as count_bl,
        argMax(nm_c, processed_dttm) as nm_c,
        argMax(atc1, processed_dttm) as atc1,
        argMax(nm_atc1, processed_dttm) as nm_atc1,
        argMax(atc2, processed_dttm) as atc2,
        argMax(nm_atc2, processed_dttm) as nm_atc2,
        argMax(atc3, processed_dttm) as atc3,
        argMax(nm_atc3, processed_dttm) as nm_atc3,
        argMax(atc4, processed_dttm) as atc4,
        argMax(nm_atc4, processed_dttm) as nm_atc4,
        argMax(atc5, processed_dttm) as atc5,
        -- Технические поля
        argMax(deleted_flag, processed_dttm) as deleted_flag,
        argMax(hash_diff, processed_dttm) as hash_diff,
        max(processed_dttm) as processed_dttm_max
    FROM stg.mart_dsm_stat_product
    WHERE processed_dttm between {p_from_dttm: DateTime} and {p_to_dttm:DateTime}
    GROUP BY cd_u
    HAVING deleted_flag = false
    ) t1;

SELECT * FROM stg.v_iv_mart_dsm_stat_product (p_from_dttm = '2025-10-26', p_to_dttm = '2025-10-27');

/* mart_dsm_region */

/* 1. Аксессор получения актуального среза на конкретную дату обработки*/
CREATE VIEW if not exists stg.v_sn_mart_dsm_region
AS 
select t1.* except (processed_dttm_max), processed_dttm_max as processed_dttm
    from (
    	select 
        cd_reg,
        sales_type_id,
        -- Все метрики через argMax
        argMax(parent_cd_reg, processed_dttm) as parent_cd_reg,
        argMax(nm_reg, processed_dttm) as nm_reg,
        argMax(nm_reg_lat, processed_dttm) as nm_reg_lat,
        argMax(lev, processed_dttm) as lev,
        argMax(nm_segment_rus, processed_dttm) as nm_segment_rus,
        -- Технические поля
        argMax(deleted_flag, processed_dttm) as deleted_flag,
        argMax(hash_diff, processed_dttm) as hash_diff,
        max(processed_dttm) as processed_dttm_max
FROM stg.mart_dsm_region
    GROUP BY cd_reg, sales_type_id
HAVING deleted_flag = false
) t1;

select * from stg.v_sn_mart_dsm_region;

/* 2. Аксессор получения актуального среза на конкретную версию-дату */
CREATE VIEW IF NOT EXISTS stg.v_sv_mart_dsm_region  ON CLUSTER cluster_2S_2R
AS 
	select t1.* except (processed_dttm_max), processed_dttm_max as processed_dttm
    from (
    	select
        cd_reg,
        sales_type_id,
        -- Все метрики через argMax
        argMax(parent_cd_reg, processed_dttm) as parent_cd_reg,
        argMax(nm_reg, processed_dttm) as nm_reg,
        argMax(nm_reg_lat, processed_dttm) as nm_reg_lat,
        argMax(lev, processed_dttm) as lev,
        argMax(nm_segment_rus, processed_dttm) as nm_segment_rus,
        -- Технические поля
        argMax(deleted_flag, processed_dttm) as deleted_flag,
        argMax(hash_diff, processed_dttm) as hash_diff,
        max(processed_dttm) as processed_dttm_max
    FROM stg.mart_dsm_region
    WHERE processed_dttm <= {p_processed_dttm_user:DateTime}
    GROUP BY cd_reg, sales_type_id
    HAVING deleted_flag = false
    ) t1;

SELECT * FROM stg.v_sv_mart_dsm_region (p_processed_dttm_user = '2025-10-27'); 

/* 3. Аксессор получения инкремента для */
CREATE VIEW IF NOT EXISTS stg.v_iv_mart_dsm_region ON CLUSTER cluster_2S_2R
AS 
	select t1.* except (processed_dttm_max), processed_dttm_max as processed_dttm
    from (
    select 
        cd_reg,
        sales_type_id,
        -- Все метрики через argMax
        argMax(parent_cd_reg, processed_dttm) as parent_cd_reg,
        argMax(nm_reg, processed_dttm) as nm_reg,
        argMax(nm_reg_lat, processed_dttm) as nm_reg_lat,
        argMax(lev, processed_dttm) as lev,
        argMax(nm_segment_rus, processed_dttm) as nm_segment_rus,
        -- Технические поля
        argMax(deleted_flag, processed_dttm) as deleted_flag,
        argMax(hash_diff, processed_dttm) as hash_diff,
        max(processed_dttm) as processed_dttm_max
    FROM stg.mart_dsm_region
    WHERE processed_dttm between {p_from_dttm: DateTime} and {p_to_dttm:DateTime}
    GROUP BY cd_reg, sales_type_id
    HAVING deleted_flag = false
    ) t1;

SELECT * FROM stg.v_iv_mart_dsm_region (p_from_dttm = '2025-10-26', p_to_dttm = '2025-10-27');