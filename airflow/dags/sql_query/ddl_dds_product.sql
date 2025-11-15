-- CREATE database dds ON CLUSTER cluster_2S_2R

-- drop table if exists dds.hub_product

CREATE table if not exists dds.hub_product
(product_uuid String,
product_id String,
src String,
effective_from_dttm DateTime,
effective_to_dttm DateTime,
processed_dttm DateTime,
deleted_flg bool
)
ENGINE = MergeTree
order by (product_uuid)

CREATE table if not exists dds.product
(
product_uuid String,
--бизнесс данные
mnn_code String,
full_trade_name String,
trade_name String,
brand_name String,
package_name String,
product_owner_name String,
corporation_name String,
dosage_name String,
weight_num Float32,
weight_unit_name String,
blister_cnt Int32,
blister_package_cnt Int32,
country_name String,
atc1_code String,
atc1_name String,
atc2_code String,
atc2_name String,
atc3_code String,
atc3_name String,
atc4_code String,
atc4_name String,
atc5_code String,
atc5_name String,
original_type String,
branded_type String,
recipereq_type String,
jnvlp_type String,
ephmra1_code String,
ephmra1_name String,
ephmra2_code String,
ephmra2_name String,
ephmra3_code String,
ephmra3_name String,
ephmra4_code String,
ephmra4_name String,
farm_group_name String,
localized_type String,
dosage_form_name String,
classification_bad1_name String,
compound_bad1_name String,
classification_bad2_name String,
compound_bad2_name String,
product_type String,
-- обязательные поля
effective_from_dttm DateTime,
effective_to_dttm DateTime,
processed_dttm DateTime,
deleted_flg bool,
src String,
hash_diff String
)
ENGINE = ReplacingMergeTree
order by (product_uuid, hash_diff)

