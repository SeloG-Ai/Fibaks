-- PostgreSQL Database Initialization Script for Fibaks ERP
-- Creates tables and loads seed data representing products, listings, and orders.

CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY,
    barcode VARCHAR(255),
    name VARCHAR(255),
    category VARCHAR(100),
    model_code VARCHAR(255),
    color VARCHAR(100),
    warehouse_id UUID,
    shelf_column VARCHAR(50),
    shelf_row VARCHAR(50),
    stock_quantity INT,
    box_no VARCHAR(50),
    min_box_quantity INT,
    max_box_quantity INT,
    box_stock_quantity INT,
    product_model VARCHAR(255),
    label_name VARCHAR(255),
    supplier_name VARCHAR(255),
    product_continues BOOLEAN,
    purchase_price_rmb NUMERIC,
    additional_cost NUMERIC,
    cost NUMERIC,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    kutu_bilgisi BOOLEAN,
    islenecek_adet INT,
    label_compatible_model VARCHAR(255),
    supplier_color VARCHAR(100),
    package_quantity INT,
    transfer_quantity INT,
    min_supply_days INT,
    pending_order_count INT,
    total_suply_count INT,
    additional_barcodes JSONB,
    is_package BOOLEAN,
    avg_sales_before_critical_stock NUMERIC,
    last_below_threshold_date DATE,
    supplier_note TEXT,
    image_id UUID,
    total_supply_count INT,
    earliest_supply_quantity INT,
    earliest_supply_delivery_date DATE,
    earliest_supply_days_remaining INT,
    cost_usd NUMERIC,
    skip_critical_marketplace_stock BOOLEAN,
    is_active BOOLEAN,
    shelf_column_num INT,
    shelf_row_num NUMERIC
);

CREATE TABLE IF NOT EXISTS device_generations (
    device_model VARCHAR(255) PRIMARY KEY,
    generation_group VARCHAR(255) NOT NULL,
    brand VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'VERIFIED'
);

CREATE TABLE IF NOT EXISTS product_trendyol (
    id UUID PRIMARY KEY,
    product_id UUID REFERENCES products(id),
    trendyol_id VARCHAR(255),
    barcode VARCHAR(255),
    title VARCHAR(555),
    product_main_id VARCHAR(255),
    stock_code VARCHAR(255),
    brand VARCHAR(100),
    category_name VARCHAR(255),
    quantity INT,
    list_price NUMERIC,
    sale_price NUMERIC,
    product_url TEXT,
    gender VARCHAR(50),
    color VARCHAR(100),
    size VARCHAR(50),
    images JSONB,
    attributes JSONB,
    is_approved BOOLEAN,
    is_on_sale BOOLEAN,
    is_archived BOOLEAN,
    is_converted_to_main BOOLEAN,
    is_matched BOOLEAN,
    last_synced_at TIMESTAMPTZ,
    trendyol_created_at TIMESTAMPTZ,
    trendyol_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    is_locked BOOLEAN,
    lock_reason TEXT,
    lock_date TIMESTAMPTZ,
    doc_needed BOOLEAN,
    has_violation BOOLEAN,
    is_blacklisted BOOLEAN,
    blacklist_reason TEXT
);

CREATE TABLE IF NOT EXISTS product_hepsiburada (
    id UUID PRIMARY KEY,
    product_id UUID REFERENCES products(id),
    hb_sku VARCHAR(255),
    merchant_sku VARCHAR(255),
    barcode VARCHAR(255),
    product_name VARCHAR(555),
    brand VARCHAR(100),
    category_name VARCHAR(255),
    category_id VARCHAR(255),
    price NUMERIC,
    tax NUMERIC,
    status VARCHAR(100),
    description TEXT,
    images JSONB,
    base_attributes JSONB,
    variant_type_attributes JSONB,
    product_attributes JSONB,
    validation_results JSONB,
    reject_reasons JSONB,
    quality_score NUMERIC,
    quality_status VARCHAR(100),
    is_converted_to_main BOOLEAN,
    is_matched BOOLEAN,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS "order" (
    id INT PRIMARY KEY,
    shipment_package_id BIGINT,
    order_number VARCHAR(100),
    order_date TIMESTAMPTZ,
    status VARCHAR(100),
    gross_amount NUMERIC,
    total_discount NUMERIC,
    total_price NUMERIC,
    currency_code VARCHAR(10),
    customer_id BIGINT,
    customer_first_name VARCHAR(255),
    customer_last_name VARCHAR(255),
    customer_email VARCHAR(255),
    supplier_id INT,
    cargo_tracking_number VARCHAR(100),
    cargo_provider_name VARCHAR(100),
    delivery_type VARCHAR(50),
    estimated_delivery_start TIMESTAMPTZ,
    estimated_delivery_end TIMESTAMPTZ,
    agreed_delivery_date TIMESTAMPTZ,
    shipment_address JSONB,
    invoice_address JSONB,
    created_by VARCHAR(100),
    last_modified_date TIMESTAMPTZ,
    raw_data JSONB,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    marketplace VARCHAR(100),
    marketplace_order_id VARCHAR(100),
    cargo_provider VARCHAR(100),
    barcode_created_at TIMESTAMPTZ,
    cargo_provider_changed BOOLEAN,
    is_sorted INT,
    is_cargo_sent INT,
    is_invoice_created INT,
    kargo_tasarimi INT,
    micro BOOLEAN,
    sorting_code VARCHAR(100),
    group_code VARCHAR(100),
    assigned_machine VARCHAR(100),
    sorted_date TIMESTAMPTZ,
    grup_siralandi INT,
    kargo_siparisno VARCHAR(100),
    is_print INT,
    priority_number INT,
    cargo_change_requested_at TIMESTAMPTZ,
    is_invoice_sent BOOLEAN
);

-- Seed Data Insertion
BEGIN;

-- products (10 satır)
INSERT INTO products (id, barcode, name, category, model_code, color, warehouse_id, shelf_column, shelf_row, stock_quantity, box_no, min_box_quantity, max_box_quantity, box_stock_quantity, product_model, label_name, supplier_name, product_continues, purchase_price_rmb, additional_cost, cost, created_at, updated_at, kutu_bilgisi, islenecek_adet, label_compatible_model, supplier_color, package_quantity, transfer_quantity, min_supply_days, pending_order_count, total_suply_count, additional_barcodes, is_package, avg_sales_before_critical_stock, last_below_threshold_date, supplier_note, image_id, total_supply_count, earliest_supply_quantity, earliest_supply_delivery_date, earliest_supply_days_remaining, cost_usd, skip_critical_marketplace_stock, is_active, shelf_column_num, shelf_row_num) VALUES 
('b429e551-fb18-4212-80b9-dde6d22dbd7d', '8685032022460', 'Blur iPhone 16 Pro / Siyah', 'KILIF', 'Blur', 'Siyah', '26e15466-7ef8-487c-bdcb-3d6f90483ed9', '753', '3.4', 170, 'B720', 10, 40, 21, 'iPhone 16 Pro', 'Fibaks Matte Glacier', 'KAYLA', TRUE, 4.9, 0.15, 38.75, '2026-03-10T23:52:02.433004+00:00', '2026-05-22T14:24:46.413977+00:00', FALSE, 0, 'İP 16 Pro', 'Black', 10, 0, 15, 0, 0, '[]'::jsonb, FALSE, NULL, NULL, NULL, '67edc136-132e-4d28-b544-61408e21ea8f', 200, NULL, NULL, NULL, 0.8611756168359943, FALSE, TRUE, 753, 3.4) ON CONFLICT (id) DO NOTHING;

INSERT INTO products (id, barcode, name, category, model_code, color, warehouse_id, shelf_column, shelf_row, stock_quantity, box_no, min_box_quantity, max_box_quantity, box_stock_quantity, product_model, label_name, supplier_name, product_continues, purchase_price_rmb, additional_cost, cost, created_at, updated_at, kutu_bilgisi, islenecek_adet, label_compatible_model, supplier_color, package_quantity, transfer_quantity, min_supply_days, pending_order_count, total_suply_count, additional_barcodes, is_package, avg_sales_before_critical_stock, last_below_threshold_date, supplier_note, image_id, total_supply_count, earliest_supply_quantity, earliest_supply_delivery_date, earliest_supply_days_remaining, cost_usd, skip_critical_marketplace_stock, is_active, shelf_column_num, shelf_row_num) VALUES 
('fb79e076-335c-4b8a-9e5a-e0f0d84ef806', '8685032006378', 'Magic Privacy iPhone 16 Pro', 'CAM', 'Magic Privacy', NULL, '26e15466-7ef8-487c-bdcb-3d6f90483ed9', '2014', '3', 1180, 'N074', 10, 40, 21, 'iPhone 16 Pro', 'Fibaks Magic Privacy', 'JACKEN', TRUE, 5.75, 0.16, 44.75, '2026-03-10T23:52:05.715807+00:00', '2026-05-22T14:24:46.413977+00:00', FALSE, 0, 'İP 16 Pro', 'xxx', 10, 0, 15, 0, 0, '[]'::jsonb, FALSE, NULL, NULL, NULL, '96b87a3b-1733-4824-8e8a-1486b56aab13', 2000, NULL, NULL, NULL, 0.9945428156748912, FALSE, TRUE, 2014, 3) ON CONFLICT (id) DO NOTHING;

INSERT INTO products (id, barcode, name, category, model_code, color, warehouse_id, shelf_column, shelf_row, stock_quantity, box_no, min_box_quantity, max_box_quantity, box_stock_quantity, product_model, label_name, supplier_name, product_continues, purchase_price_rmb, additional_cost, cost, created_at, updated_at, kutu_bilgisi, islenecek_adet, label_compatible_model, supplier_color, package_quantity, transfer_quantity, min_supply_days, pending_order_count, total_suply_count, additional_barcodes, is_package, avg_sales_before_critical_stock, last_below_threshold_date, supplier_note, image_id, total_supply_count, earliest_supply_quantity, earliest_supply_delivery_date, earliest_supply_days_remaining, cost_usd, skip_critical_marketplace_stock, is_active, shelf_column_num, shelf_row_num) VALUES 
('b0824f7b-aab1-4ce9-bb55-57aebeca6431', '8685032027069', 'Glacier iPhone 7-8 Plus', 'KILIF', 'Glacier', NULL, 'fb0e72ad-bdb4-4375-ba6c-15beef751978', '10000', '10000', 2001, 'C114', 10, 33, 28, 'iPhone 7 Plus', 'Fibaks Glacier', 'KAYLA', TRUE, 1.75, 0.15, 18.18, '2026-03-10T23:52:02.624073+00:00', '2026-05-22T15:04:44.867118+00:00', FALSE, 0, 'İP 7 PLS-8 PLS', 'xxx', 10, 0, 15, 0, 0, '[]'::jsonb, FALSE, NULL, NULL, NULL, '20f254cc-8617-49b9-8dfc-fa7c963136cf', 0, NULL, NULL, NULL, 0.40399129172714077, FALSE, TRUE, 10000, 10000) ON CONFLICT (id) DO NOTHING;

INSERT INTO products (id, barcode, name, category, model_code, color, warehouse_id, shelf_column, shelf_row, stock_quantity, box_no, min_box_quantity, max_box_quantity, box_stock_quantity, product_model, label_name, supplier_name, product_continues, purchase_price_rmb, additional_cost, cost, created_at, updated_at, kutu_bilgisi, islenecek_adet, label_compatible_model, supplier_color, package_quantity, transfer_quantity, min_supply_days, pending_order_count, total_suply_count, additional_barcodes, is_package, avg_sales_before_critical_stock, last_below_threshold_date, supplier_note, image_id, total_supply_count, earliest_supply_quantity, earliest_supply_delivery_date, earliest_supply_days_remaining, cost_usd, skip_critical_marketplace_stock, is_active, shelf_column_num, shelf_row_num) VALUES 
('d035115e-c798-4833-9246-6cf26d093440', '8685032009256', 'Maxi iPhone 6 Plus', 'CAM', 'Maxi ESD', NULL, '26e15466-7ef8-487c-bdcb-3d6f90483ed9', '2042', '2', 20, 'N502', 30, 150, 85, 'iPhone 7 Plus', 'Fibaks Maxi ESD', 'JACKEN', TRUE, 1.04, 0.08, 10.39, '2026-03-10T23:52:06.07373+00:00', '2026-05-22T14:18:08.402073+00:00', TRUE, 0, 'İP 6PLS-7PLS-8PLS', 'xxx', 10, 0, 15, 0, 0, '[]'::jsonb, FALSE, NULL, NULL, NULL, '34600dd8-b0b3-4e7b-a6e7-d5944574493d', 4000, NULL, NULL, NULL, 0.23094339622641513, FALSE, TRUE, 2042, 2) ON CONFLICT (id) DO NOTHING;

INSERT INTO products (id, barcode, name, category, model_code, color, warehouse_id, shelf_column, shelf_row, stock_quantity, box_no, min_box_quantity, max_box_quantity, box_stock_quantity, product_model, label_name, supplier_name, product_continues, purchase_price_rmb, additional_cost, cost, created_at, updated_at, kutu_bilgisi, islenecek_adet, label_compatible_model, supplier_color, package_quantity, transfer_quantity, min_supply_days, pending_order_count, total_suply_count, additional_barcodes, is_package, avg_sales_before_critical_stock, last_below_threshold_date, supplier_note, image_id, total_supply_count, earliest_supply_quantity, earliest_supply_delivery_date, earliest_supply_days_remaining, cost_usd, skip_critical_marketplace_stock, is_active, shelf_column_num, shelf_row_num) VALUES 
('27830415-eef2-4199-a413-b1bac0a19aeb', '8685032025034', 'Cure iPhone 11 / Siyah', 'KILIF', 'Cure', 'Siyah', '26e15466-7ef8-487c-bdcb-3d6f90483ed9', '908', '3.4', 1040, 'A336', 15, 35, 17, 'iPhone 11', 'Fibaks Cure', 'KAYLA', TRUE, 1.85, 0.15, 18.83, '2026-03-10T23:52:01.857034+00:00', '2026-05-22T14:33:07.142502+00:00', FALSE, 0, 'İP 11', 'Black', 10, 0, 15, 1, 0, '[]'::jsonb, FALSE, NULL, NULL, NULL, 'd77d23f4-7b11-4140-8823-be13b728c274', 0, NULL, NULL, NULL, 0.4185050798258345, FALSE, TRUE, 908, 3.4) ON CONFLICT (id) DO NOTHING;

INSERT INTO products (id, barcode, name, category, model_code, color, warehouse_id, shelf_column, shelf_row, stock_quantity, box_no, min_box_quantity, max_box_quantity, box_stock_quantity, product_model, label_name, supplier_name, product_continues, purchase_price_rmb, additional_cost, cost, created_at, updated_at, kutu_bilgisi, islenecek_adet, label_compatible_model, supplier_color, package_quantity, transfer_quantity, min_supply_days, pending_order_count, total_suply_count, additional_barcodes, is_package, avg_sales_before_critical_stock, last_below_threshold_date, supplier_note, image_id, total_supply_count, earliest_supply_quantity, earliest_supply_delivery_date, earliest_supply_days_remaining, cost_usd, skip_critical_marketplace_stock, is_active, shelf_column_num, shelf_row_num) VALUES 
('a0478208-9abb-4f8f-bf76-bb875b241d37', '8685032010009', 'Charm Ayna iPhone 11 / Gümüş', 'KILIF', 'Charm Ayna', 'Gümüş', '26e15466-7ef8-487c-bdcb-3d6f90483ed9', '920', '3.4', 2626, 'A392', 15, 35, 8, 'iPhone 11', 'Fibaks Desi', 'KAYLA', TRUE, 5.0, 0.12, 38.06, '2026-03-10T23:52:01.857034+00:00', '2026-05-22T14:16:59.992124+00:00', TRUE, 0, 'İP 11', 'Silver', 10, 0, 15, 0, 0, '[]'::jsonb, FALSE, NULL, NULL, NULL, '89a897de-7072-4729-af85-8bf709374a77', 0, NULL, NULL, NULL, 0.845689404934688, FALSE, TRUE, 920, 3.4) ON CONFLICT (id) DO NOTHING;

INSERT INTO products (id, barcode, name, category, model_code, color, warehouse_id, shelf_column, shelf_row, stock_quantity, box_no, min_box_quantity, max_box_quantity, box_stock_quantity, product_model, label_name, supplier_name, product_continues, purchase_price_rmb, additional_cost, cost, created_at, updated_at, kutu_bilgisi, islenecek_adet, label_compatible_model, supplier_color, package_quantity, transfer_quantity, min_supply_days, pending_order_count, total_suply_count, additional_barcodes, is_package, avg_sales_before_critical_stock, last_below_threshold_date, supplier_note, image_id, total_supply_count, earliest_supply_quantity, earliest_supply_delivery_date, earliest_supply_days_remaining, cost_usd, skip_critical_marketplace_stock, is_active, shelf_column_num, shelf_row_num) VALUES 
('8a75d1e2-77f4-4f9d-8633-6f8913015062', '8685032038089', 'Gard-02 HW Fit 3 / Şeffaf', 'GARD', 'Gard-02', 'Şeffaf', '26e15466-7ef8-487c-bdcb-3d6f90483ed9', '2087', '2', 2150, 'S172', 10, 60, 29, 'Huawei Watch Fit 3', 'Fibaks Gard', 'JUYOMI', TRUE, 1.3, 0.08, 12.09, '2026-03-10T23:52:07.011589+00:00', '2026-05-22T14:10:37.638308+00:00', FALSE, 0, 'HW Watch Fit 3', 'Clear', 50, 0, 15, 0, 0, '[]'::jsonb, FALSE, NULL, NULL, NULL, 'fdbf4b28-1989-4e64-9d21-4db038112299', 0, NULL, NULL, NULL, 0.2686792452830189, FALSE, TRUE, 2087, 2) ON CONFLICT (id) DO NOTHING;

INSERT INTO products (id, barcode, name, category, model_code, color, warehouse_id, shelf_column, shelf_row, stock_quantity, box_no, min_box_quantity, max_box_quantity, box_stock_quantity, product_model, label_name, supplier_name, product_continues, purchase_price_rmb, additional_cost, cost, created_at, updated_at, kutu_bilgisi, islenecek_adet, label_compatible_model, supplier_color, package_quantity, transfer_quantity, min_supply_days, pending_order_count, total_suply_count, additional_barcodes, is_package, avg_sales_before_critical_stock, last_below_threshold_date, supplier_note, image_id, total_supply_count, earliest_supply_quantity, earliest_supply_delivery_date, earliest_supply_days_remaining, cost_usd, skip_critical_marketplace_stock, is_active, shelf_column_num, shelf_row_num) VALUES 
('a82d3a00-4ee6-4669-a019-47064b015777', '8685032008976', 'Hayalet iPhone 11', 'CAM', 'Hayalet ESD', NULL, '26e15466-7ef8-487c-bdcb-3d6f90483ed9', '2032', '3', 980, 'N316', 30, 80, 52, 'iPhone 11', 'Fibaks Hayalet ESD', 'JACKEN', TRUE, 1.96, 0.08, 16.4, '2026-03-10T23:52:05.895189+00:00', '2026-05-22T14:18:59.481762+00:00', TRUE, 0, 'İP 11-XR', 'xxx', 10, 0, 15, 0, 0, '[]'::jsonb, FALSE, 35.87, '2026-05-07', NULL, 'fd34f6f6-582a-4e39-a609-fca2100bdb6c', 15000, NULL, NULL, NULL, 0.3644702467343977, FALSE, TRUE, 2032, 3) ON CONFLICT (id) DO NOTHING;

INSERT INTO products (id, barcode, name, category, model_code, color, warehouse_id, shelf_column, shelf_row, stock_quantity, box_no, min_box_quantity, max_box_quantity, box_stock_quantity, product_model, label_name, supplier_name, product_continues, purchase_price_rmb, additional_cost, cost, created_at, updated_at, kutu_bilgisi, islenecek_adet, label_compatible_model, supplier_color, package_quantity, transfer_quantity, min_supply_days, pending_order_count, total_suply_count, additional_barcodes, is_package, avg_sales_before_critical_stock, last_below_threshold_date, supplier_note, image_id, total_supply_count, earliest_supply_quantity, earliest_supply_delivery_date, earliest_supply_days_remaining, cost_usd, skip_critical_marketplace_stock, is_active, shelf_column_num, shelf_row_num) VALUES 
('387a7080-0b4a-45d0-9b94-1551da1e835a', '8685032010382', 'Blur iPhone 13-14-15 / Siyah', 'KILIF', 'Blur', 'Siyah', '26e15466-7ef8-487c-bdcb-3d6f90483ed9', '6000', '4', 35934, 'A054', 100, 300, 229, 'iPhone 15', 'Fibaks Matte Glacier', 'KAYLA', TRUE, 4.9, 0.15, 38.75, '2026-03-10T23:52:01.601458+00:00', '2026-05-22T14:59:49.384232+00:00', FALSE, 0, 'İP 13-14-15', 'Black', 200, 0, NULL, 7, 0, '[]'::jsonb, FALSE, NULL, NULL, NULL, '67edc136-132e-4d28-b544-61408e21ea8f', 20000, NULL, NULL, NULL, 0.8611756168359943, FALSE, TRUE, 6000, 4) ON CONFLICT (id) DO NOTHING;

INSERT INTO products (id, barcode, name, category, model_code, color, warehouse_id, shelf_column, shelf_row, stock_quantity, box_no, min_box_quantity, max_box_quantity, box_stock_quantity, product_model, label_name, supplier_name, product_continues, purchase_price_rmb, additional_cost, cost, created_at, updated_at, kutu_bilgisi, islenecek_adet, label_compatible_model, supplier_color, package_quantity, transfer_quantity, min_supply_days, pending_order_count, total_suply_count, additional_barcodes, is_package, avg_sales_before_critical_stock, last_below_threshold_date, supplier_note, image_id, total_supply_count, earliest_supply_quantity, earliest_supply_delivery_date, earliest_supply_days_remaining, cost_usd, skip_critical_marketplace_stock, is_active, shelf_column_num, shelf_row_num) VALUES 
('c17c463b-d2cb-4eb2-bbc0-f12fb984fffb', '8685032009713', 'CL-07 iPhone 13 / Siyah', 'KAMERA LENS', 'CL-07', 'Siyah', '26e15466-7ef8-487c-bdcb-3d6f90483ed9', '2048', '4', 50, 'P012', 30, 130, 44, 'iPhone 13', 'Fibaks CL-07', 'JUDY', TRUE, 0.42, 0.06, 5.44, '2026-03-10T23:52:06.438981+00:00', '2026-05-22T14:12:49.007007+00:00', FALSE, 0, 'İP 13-13 Mini', 'Black', 50, 0, NULL, 0, 0, '[]'::jsonb, FALSE, NULL, NULL, NULL, 'b16c6565-f230-41f4-977f-c4e2003d21f7', 400, NULL, NULL, NULL, 0.12095791001451378, FALSE, TRUE, 2048, 4) ON CONFLICT (id) DO NOTHING;

-- product_trendyol (6 satır)
INSERT INTO product_trendyol (id, product_id, trendyol_id, barcode, title, product_main_id, stock_code, brand, category_name, quantity, list_price, sale_price, product_url, gender, color, size, images, attributes, is_approved, is_on_sale, is_archived, is_converted_to_main, is_matched, last_synced_at, trendyol_created_at, trendyol_updated_at, created_at, updated_at, is_locked, lock_reason, lock_date, doc_needed, has_violation, is_blacklisted, blacklist_reason) VALUES 
('aa018b5e-9afd-4cd1-a193-bd283e55fe15', 'fb79e076-335c-4b8a-9e5a-e0f0d84ef806', '53c3aa82c7df302b337833b6ba0935a2', 'Fibaks-13-Eylül-2024-168', 'Apple iPhone 16 Pro Uyumlu Kolay Uygulama Aparatlı Hayalet Tam Kapatan Cam Ekran Koruyucu', '16pro-ip-kılıf-ekran-magic-hayalet', NULL, 'Fibaks', 'Ekran Koruyucu Film', 1219, 199.0, 199.0, 'https://www.trendyol.com/fibaks/apple-iphone-16-pro-uyumlu-kolay-uygulama-aparatli-hayalet-tam-kapatan-cam-ekran-koruyucu-p-858127685', NULL, NULL, NULL, '[]'::jsonb, '[]'::jsonb, TRUE, TRUE, FALSE, FALSE, TRUE, '2026-05-20T23:23:53.178683+00:00', '2024-09-13T09:08:32+00:00', '2026-05-17T19:45:47+00:00', '2026-03-11T00:02:26.032818+00:00', '2026-05-20T23:23:53.067055+00:00', FALSE, NULL, NULL, FALSE, FALSE, FALSE, NULL) ON CONFLICT (id) DO NOTHING;

INSERT INTO product_trendyol (id, product_id, trendyol_id, barcode, title, product_main_id, stock_code, brand, category_name, quantity, list_price, sale_price, product_url, gender, color, size, images, attributes, is_approved, is_on_sale, is_archived, is_converted_to_main, is_matched, last_synced_at, trendyol_created_at, trendyol_updated_at, created_at, updated_at, is_locked, lock_reason, lock_date, doc_needed, has_violation, is_blacklisted, blacklist_reason) VALUES 
('ac2e522e-0090-49fc-b6c5-55a1fa5a1516', 'b429e551-fb18-4212-80b9-dde6d22dbd7d', 'd0a88e8d46a0b85b2527cf5018ab6d4a', 'Fibaks-24-Eylül-2024-042', 'iPhone 16 Pro Kılıf Kamera Çıkıntılı Magsafe Şarj Destekli Hassas Tuşlu Yumuşak Mat Kapak Siyah', '16pro-ip-telefonkılıfı-simli-aynalı', '', 'Fibaks', 'Kapak & Kılıf', 196, 180.0, 180.0, 'https://www.trendyol.com/abc/xyz-p-860874915', NULL, 'Blur Siyah', NULL, '[]'::jsonb, '[]'::jsonb, TRUE, TRUE, FALSE, FALSE, TRUE, '2026-05-21T01:16:20.065823+00:00', '2024-09-24T08:01:34+00:00', '2026-05-17T19:45:50+00:00', '2026-03-11T00:02:25.806222+00:00', '2026-05-20T22:16:26.190861+00:00', FALSE, NULL, NULL, FALSE, FALSE, FALSE, NULL) ON CONFLICT (id) DO NOTHING;

INSERT INTO product_trendyol (id, product_id, trendyol_id, barcode, title, product_main_id, stock_code, brand, category_name, quantity, list_price, sale_price, product_url, gender, color, size, images, attributes, is_approved, is_on_sale, is_archived, is_converted_to_main, is_matched, last_synced_at, trendyol_created_at, trendyol_updated_at, created_at, updated_at, is_locked, lock_reason, lock_date, doc_needed, has_violation, is_blacklisted, blacklist_reason) VALUES 
('a9d1924a-b92c-45e2-ab74-b2c1b131ef60', 'b0824f7b-aab1-4ce9-bb55-57aebeca6431', '0038ea88df4ef4b48c643d6ed616f79a', 'Fibaks-17-Ocak-002', 'iPhone 7 Plus/8 Plus Kılıf Magsafe Wireless Kablosuz Şarj Destekli Sert Şeffaf Darbe Emici', '7plus-8plus-ip-telefonkılıfı-aynalı', NULL, 'Fibaks', 'Kapak & Kılıf', 2037, 133.0, 133.0, 'https://www.trendyol.com/abc/xyz-p-475120502', NULL, 'Glacier', NULL, '[]'::jsonb, '[]'::jsonb, TRUE, TRUE, FALSE, FALSE, TRUE, '2026-05-21T01:21:58.326448+00:00', '2023-01-17T05:22:22+00:00', '2026-05-17T19:45:48+00:00', '2026-03-11T00:02:30.101526+00:00', '2026-05-20T22:22:23.391151+00:00', FALSE, NULL, NULL, FALSE, FALSE, FALSE, NULL) ON CONFLICT (id) DO NOTHING;

INSERT INTO product_trendyol (id, product_id, trendyol_id, barcode, title, product_main_id, stock_code, brand, category_name, quantity, list_price, sale_price, product_url, gender, color, size, images, attributes, is_approved, is_on_sale, is_archived, is_converted_to_main, is_matched, last_synced_at, trendyol_created_at, trendyol_updated_at, created_at, updated_at, is_locked, lock_reason, lock_date, doc_needed, has_violation, is_blacklisted, blacklist_reason) VALUES 
('7b71a95e-320c-43db-b782-db6794b36537', 'd035115e-c798-4833-9246-6cf26d093440', 'cdc15b192dc5f0d7b630999c2ca3df14', 'Maxi730', 'Apple Iphone 7 Plus 8 Plus Uyumlu 9h Sert Temperli Kırılmaz Cam Koruma Şeffaf Koruyucu', 'iPhone 8 Plus Ekran Koruma', 'Maxi', 'Fibaks', 'Ekran Koruyucu Film', 80, 120.0, 120.0, 'https://www.trendyol.com/abc/xyz-p-80878001', NULL, NULL, NULL, '[]'::jsonb, '[]'::jsonb, TRUE, TRUE, FALSE, FALSE, TRUE, '2026-05-21T01:46:40.236243+00:00', '2021-02-02T12:34:26+00:00', '2026-05-17T19:45:45+00:00', '2026-03-11T00:02:33.729671+00:00', '2026-05-20T22:52:39.924777+00:00', FALSE, NULL, NULL, FALSE, FALSE, FALSE, NULL) ON CONFLICT (id) DO NOTHING;

INSERT INTO product_trendyol (id, product_id, trendyol_id, barcode, title, product_main_id, stock_code, brand, category_name, quantity, list_price, sale_price, product_url, gender, color, size, images, attributes, is_approved, is_on_sale, is_archived, is_converted_to_main, is_matched, last_synced_at, trendyol_created_at, trendyol_updated_at, created_at, updated_at, is_locked, lock_reason, lock_date, doc_needed, has_violation, is_blacklisted, blacklist_reason) VALUES 
('84a01521-8dae-4424-9cc1-262e89f7f6f5', 'a0478208-9abb-4f8f-bf76-bb875b241d37', '7a4d0b8753cc58a8d25b9f96dc340168', 'FBR10108120420', 'iPhone 11 Kılıf Aynalı İnci Charm Askılı Kalp Tasarımlı Desenli Silikon Kapak', '11-ip-ayna-aynalı-desenli-telefonkılıf', NULL, 'Fibaks', 'Kapak & Kılıf', 2654, 160.0, 160.0, 'https://www.trendyol.com/abc/xyz-p-944516576', NULL, 'Askılı', NULL, '[]'::jsonb, '[]'::jsonb, TRUE, TRUE, FALSE, FALSE, TRUE, '2026-05-21T01:14:44.039913+00:00', '2025-06-13T06:16:29+00:00', '2026-05-17T19:45:49+00:00', '2026-03-11T00:02:17.877829+00:00', '2026-05-20T22:14:47.01242+00:00', FALSE, NULL, NULL, FALSE, FALSE, FALSE, NULL) ON CONFLICT (id) DO NOTHING;

INSERT INTO product_trendyol (id, product_id, trendyol_id, barcode, title, product_main_id, stock_code, brand, category_name, quantity, list_price, sale_price, product_url, gender, color, size, images, attributes, is_approved, is_on_sale, is_archived, is_converted_to_main, is_matched, last_synced_at, trendyol_created_at, trendyol_updated_at, created_at, updated_at, is_locked, lock_reason, lock_date, doc_needed, has_violation, is_blacklisted, blacklist_reason) VALUES 
('df9a9cf0-8988-4478-b173-5d4b244ed0e8', '27830415-eef2-4199-a413-b1bac0a19aeb', 'd67b469809b853f52668fc360e7e8ae0', 'Fibaks-15-Mart-2023-009', 'iPhone 11 Kılıf Magsafe Wireless Şarj Özellikli Tam Koruma Renkli Sert Silikon Ege Kapak', '11-ip-kılıf-aynalı-desenli-telefonkılıfı', NULL, 'Fibaks', 'Kapak & Kılıf', 1080, 135.0, 135.0, 'https://www.trendyol.com/abc/xyz-p-670070770', NULL, 'Cure Siyah', NULL, '[]'::jsonb, '[]'::jsonb, TRUE, TRUE, FALSE, FALSE, TRUE, '2026-05-21T01:21:31.878277+00:00', '2023-03-15T06:12:33+00:00', '2026-05-17T19:45:46+00:00', '2026-03-11T00:02:29.879397+00:00', '2026-05-20T22:21:39.399426+00:00', FALSE, NULL, NULL, FALSE, FALSE, FALSE, NULL) ON CONFLICT (id) DO NOTHING;

-- product_hepsiburada (4 satır)
INSERT INTO product_hepsiburada (id, product_id, hb_sku, merchant_sku, barcode, product_name, brand, category_name, category_id, price, tax, status, description, images, base_attributes, variant_type_attributes, product_attributes, validation_results, reject_reasons, quality_score, quality_status, is_converted_to_main, is_matched, last_synced_at, created_at, updated_at) VALUES 
('84dda712-2de2-44c7-ae81-99dc1ecf72a4', '8a75d1e2-77f4-4f9d-8633-6f8913015062', 'HBCV000072FZRZ', 'FBR40409430011', '0F40409430011', 'Fibaks Huawei Watch Fit 3 Yumuşak Silikom Kasa ve Ekran Koruyucu 360 Tam Koruma Kapak', NULL, NULL, NULL, 158.82, NULL, NULL, NULL, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, NULL, NULL, FALSE, TRUE, NULL, '2026-03-11T00:12:41.990866+00:00', '2026-03-11T00:38:21.695262+00:00') ON CONFLICT (id) DO NOTHING;

INSERT INTO product_hepsiburada (id, product_id, hb_sku, merchant_sku, barcode, product_name, brand, category_name, category_id, price, tax, status, description, images, base_attributes, variant_type_attributes, product_attributes, validation_results, reject_reasons, quality_score, quality_status, is_converted_to_main, is_matched, last_synced_at, created_at, updated_at) VALUES 
('9e1ede91-4b8e-4369-974a-31eaa2b911a0', 'a82d3a00-4ee6-4669-a019-47064b015777', 'HBCV00002DC4CQ', 'FİBAKS-DAVİN-HAYALET-001', 'Fiber-Davin-Hayalet-001', 'Fibaks Apple iPhone 11 Uyumlu Tam Kaplayan Hayalet Ekran Koruyucu Gizli Cam', NULL, NULL, NULL, 197.33, NULL, NULL, NULL, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, NULL, NULL, FALSE, TRUE, NULL, '2026-03-11T00:12:40.895804+00:00', '2026-03-11T00:39:13.951935+00:00') ON CONFLICT (id) DO NOTHING;

INSERT INTO product_hepsiburada (id, product_id, hb_sku, merchant_sku, barcode, product_name, brand, category_name, category_id, price, tax, status, description, images, base_attributes, variant_type_attributes, product_attributes, validation_results, reject_reasons, quality_score, quality_status, is_converted_to_main, is_matched, last_synced_at, created_at, updated_at) VALUES 
('afd9eea1-4f8f-43dd-8e97-27caa7b26a40', '387a7080-0b4a-45d0-9b94-1551da1e835a', 'HBCV00006N93BG', 'FİBAKS-09-TEMMUZ-2024-HB-064', 'Fiber-09-Temmuz-2024-HB-064', 'Fibaks Apple iPhone 13 Kılıf Kamera Çıkıntılı Magsafe Şarj Destekli Metal Tuşlu Yumuşak Kenarlı Mat Kapak', NULL, NULL, NULL, 370.67, NULL, NULL, NULL, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, NULL, NULL, FALSE, TRUE, NULL, '2026-03-11T00:09:57.050661+00:00', '2026-03-11T00:39:50.003171+00:00') ON CONFLICT (id) DO NOTHING;

INSERT INTO product_hepsiburada (id, product_id, hb_sku, merchant_sku, barcode, product_name, brand, category_name, category_id, price, tax, status, description, images, base_attributes, variant_type_attributes, product_attributes, validation_results, reject_reasons, quality_score, quality_status, is_converted_to_main, is_matched, last_synced_at, created_at, updated_at) VALUES 
('adbc6c44-0094-4b38-894d-7470ecddb43a', 'c17c463b-d2cb-4eb2-bbc0-f12fb984fffb', 'HBCV00003CG38W', 'FİBAKS-3-ARALIK-HB-069', 'Fiber-3-Aralık-HB-069', 'Apple iPhone 13 Kamera Lens Koruyucu Kırılmaz Cam Kaliteyi Bozmaz Temperli Berrak Koruma Cl-07', NULL, NULL, NULL, 162.67, NULL, NULL, NULL, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, NULL, NULL, FALSE, TRUE, NULL, '2026-03-11T00:12:41.125768+00:00', '2026-03-11T00:39:45.721708+00:00') ON CONFLICT (id) DO NOTHING;

-- order (5 satır)
-- Sipariş 1: Uyumlu (Volkan Zorlu) - iPhone 16 Pro Kılıf + Cam
INSERT INTO "order" (id, shipment_package_id, order_number, order_date, status, gross_amount, total_discount, total_price, currency_code, customer_id, customer_first_name, customer_last_name, customer_email, shipment_address, invoice_address, created_by, last_modified_date, raw_data, created_at, updated_at, marketplace) VALUES 
(5049785, 3870663749, '11259832912', '2026-05-22T16:00:10.788+00:00', 'Picking', 379.0, 0.0, 379.0, 'TRY', 83723819, 'Volkan', 'Zorlu', 'volkan@trendyol.com', 
'{"city": "Ankara", "fullName": "Volkan Zorlu", "fullAddress": "Akyurt/Ankara"}'::jsonb,
'{"city": "Ankara", "fullName": "Volkan Zorlu", "fullAddress": "Akyurt/Ankara"}'::jsonb,
'order-creation', '2026-05-22T13:00:29.01104+00:00',
'{"lines": [{"sku": "Fibaks-24-Eylül-2024-042", "price": 180.0, "barcode": "Fibaks-24-Eylül-2024-042", "quantity": 1, "productName": "iPhone 16 Pro Kılıf Kamera Çıkıntılı Magsafe Şarj Destekli Siyah"}, {"sku": "Fibaks-13-Eylül-2024-168", "price": 199.0, "barcode": "Fibaks-13-Eylül-2024-168", "quantity": 1, "productName": "Apple iPhone 16 Pro Uyumlu Hayalet Cam Ekran Koruyucu"}]}'::jsonb,
'2026-05-22T13:00:21.219466+00:00', '2026-05-22T14:07:40.116307+00:00', 'Trendyol') ON CONFLICT (id) DO NOTHING;

-- Sipariş 2: Uyumlu (Hande Küçük) - iPhone 7/8 Plus Kılıf + Cam
INSERT INTO "order" (id, shipment_package_id, order_number, order_date, status, gross_amount, total_discount, total_price, currency_code, customer_id, customer_first_name, customer_last_name, customer_email, shipment_address, invoice_address, created_by, last_modified_date, raw_data, created_at, updated_at, marketplace) VALUES 
(5049773, 3870661492, '11259829197', '2026-05-22T15:58:43.804+00:00', 'Shipped', 225.4, 0.0, 225.4, 'TRY', 17024244, 'Hande', 'Küçük', 'hande@trendyol.com', 
'{"city": "İstanbul", "fullName": "Hande Küçük", "fullAddress": "Üsküdar/İstanbul"}'::jsonb,
'{"city": "İstanbul", "fullName": "Hande Küçük", "fullAddress": "Üsküdar/İstanbul"}'::jsonb,
'order-creation', '2026-05-22T14:20:06.397+00:00',
'{"lines": [{"sku": "Fibaks-17-Ocak-002", "price": 105.4, "barcode": "Fibaks-17-Ocak-002", "quantity": 1, "productName": "iPhone 7 Plus/8 Plus Kılıf Magsafe Şeffaf Glacier"}, {"sku": "Maxi730", "price": 120.0, "barcode": "Maxi730", "quantity": 1, "productName": "Apple Iphone 7 Plus 8 Plus Uyumlu 9h Kırılmaz Cam"}]}'::jsonb,
'2026-05-22T14:20:00.00+00:00', '2026-05-22T14:20:00.00+00:00', 'Trendyol') ON CONFLICT (id) DO NOTHING;

-- Sipariş 3: UYUMSUZ MODEL (Ahmet Yılmaz) - iPhone 11 Kılıf + iPhone 13-14-15 Kılıf
INSERT INTO "order" (id, shipment_package_id, order_number, order_date, status, gross_amount, total_discount, total_price, currency_code, customer_id, customer_first_name, customer_last_name, customer_email, shipment_address, invoice_address, created_by, last_modified_date, raw_data, created_at, updated_at, marketplace) VALUES 
(5049760, 3870661200, '11259824138', '2026-05-22T15:30:00.000+00:00', 'Picking', 505.67, 0.0, 505.67, 'TRY', 22839401, 'Ahmet', 'Yılmaz', 'ahmet@hepsiburada.com', 
'{"city": "İzmir", "fullName": "Ahmet Yılmaz", "fullAddress": "Bornova/İzmir"}'::jsonb,
'{"city": "İzmir", "fullName": "Ahmet Yılmaz", "fullAddress": "Bornova/İzmir"}'::jsonb,
'order-creation', '2026-05-22T15:30:00.000+00:00',
'{"lines": [{"sku": "Fibaks-15-Mart-2023-009", "price": 135.0, "barcode": "Fibaks-15-Mart-2023-009", "quantity": 1, "productName": "iPhone 11 Kılıf Magsafe Renkli Sert Silikon Ege Kapak"}, {"sku": "Fiber-09-Temmuz-2024-HB-064", "price": 370.67, "barcode": "Fiber-09-Temmuz-2024-HB-064", "quantity": 1, "productName": "Fibaks Apple iPhone 13 Kılıf Kamera Çıkıntılı Mat Kapak"}]}'::jsonb,
'2026-05-22T15:30:00.000+00:00', '2026-05-22T15:30:00.000+00:00', 'Hepsiburada') ON CONFLICT (id) DO NOTHING;

-- Sipariş 4: RİSKLİ MODEL (Can Öz) - Huawei Watch Fit 3 Kasa & Ekran
INSERT INTO "order" (id, shipment_package_id, order_number, order_date, status, gross_amount, total_discount, total_price, currency_code, customer_id, customer_first_name, customer_last_name, customer_email, shipment_address, invoice_address, created_by, last_modified_date, raw_data, created_at, updated_at, marketplace) VALUES 
(5049750, 3870661100, '4824542387', '2026-05-22T14:15:00.000+00:00', 'Picking', 158.82, 0.0, 158.82, 'TRY', 38402941, 'Can', 'Öz', 'can@hepsiburada.com', 
'{"city": "Bursa", "fullName": "Can Öz", "fullAddress": "Nilüfer/Bursa"}'::jsonb,
'{"city": "Bursa", "fullName": "Can Öz", "fullAddress": "Nilüfer/Bursa"}'::jsonb,
'order-creation', '2026-05-22T14:15:00.000+00:00',
'{"lines": [{"sku": "0F40409430011", "price": 158.82, "barcode": "0F40409430011", "quantity": 1, "productName": "Fibaks Huawei Watch Fit 3 Yumuşak Silikon Kasa ve Ekran Koruyucu"}]}'::jsonb,
'2026-05-22T14:15:00.000+00:00', '2026-05-22T14:15:00.000+00:00', 'Hepsiburada') ON CONFLICT (id) DO NOTHING;

-- Sipariş 5: Uyumlu Çoklu (Fatma Demir) - iPhone 11 Kılıf + Cam
INSERT INTO "order" (id, shipment_package_id, order_number, order_date, status, gross_amount, total_discount, total_price, currency_code, customer_id, customer_first_name, customer_last_name, customer_email, shipment_address, invoice_address, created_by, last_modified_date, raw_data, created_at, updated_at, marketplace) VALUES 
(5049740, 3870661000, '4078552515', '2026-05-22T13:00:00.000+00:00', 'Picking', 357.33, 0.0, 357.33, 'TRY', 90213840, 'Fatma', 'Demir', 'fatma@hepsiburada.com', 
'{"city": "Antalya", "fullName": "Fatma Demir", "fullAddress": "Muratpaşa/Antalya"}'::jsonb,
'{"city": "Antalya", "fullName": "Fatma Demir", "fullAddress": "Muratpaşa/Antalya"}'::jsonb,
'order-creation', '2026-05-22T13:00:00.000+00:00',
'{"lines": [{"sku": "FBR10108120420", "price": 160.0, "barcode": "FBR10108120420", "quantity": 1, "productName": "iPhone 11 Kılıf Aynalı İnci Askılı Kapak"}, {"sku": "Fiber-Davin-Hayalet-001", "price": 197.33, "barcode": "Fiber-Davin-Hayalet-001", "quantity": 1, "productName": "Fibaks Apple iPhone 11 Uyumlu Hayalet Ekran Koruyucu Gizli Cam"}]}'::jsonb,
'2026-05-22T13:00:00.000+00:00', '2026-05-22T13:00:00.000+00:00', 'Hepsiburada') ON CONFLICT (id) DO NOTHING;

COMMIT;
