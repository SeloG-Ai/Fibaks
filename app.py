import os
import json
import sqlite3
import psycopg2
import uuid
import re
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional

class PostgreSQLCursorWrapper:
    def __init__(self, real_cursor, conn):
        self.real_cursor = real_cursor
        self.conn = conn

    def execute(self, query, params=None):
        if not query:
            return self.real_cursor.execute(query, params)
            
        import re
        q_upper = query.upper()
        
        # 1. Translate INSERT OR IGNORE INTO -> INSERT INTO ... ON CONFLICT DO NOTHING
        if "INSERT OR IGNORE INTO" in q_upper:
            query = re.sub(r'(?i)INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', query)
            query = query.strip()
            if query.endswith(';'):
                query = query[:-1].strip() + " ON CONFLICT DO NOTHING;"
            else:
                query = query + " ON CONFLICT DO NOTHING"
                
        # 2. Translate SQLite datetime('now') or datetime('now', 'localtime') to PostgreSQL CURRENT_TIMESTAMP
        query = re.sub(r"(?i)datetime\(\s*'now'\s*(,\s*'localtime'\s*)?\)", 'CURRENT_TIMESTAMP', query)
        
        # 3. Translate 'is_active = 1' to 'is_active = TRUE' or similar boolean queries
        query = re.sub(r"(?i)is_active\s*=\s*1", 'is_active = TRUE', query)
        query = re.sub(r"(?i)is_active\s*=\s*0", 'is_active = FALSE', query)
        
        # 4. Translate SQLite ? placeholders to %s
        query = query.replace('?', '%s')
        
        return self.real_cursor.execute(query, params)

    def fetchone(self):
        return self.real_cursor.fetchone()

    def fetchall(self):
        return self.real_cursor.fetchall()

    def close(self):
        return self.real_cursor.close()

    def __getattr__(self, name):
        return getattr(self.real_cursor, name)

class PostgreSQLConnectionWrapper:
    def __init__(self, real_conn):
        self.real_conn = real_conn

    def cursor(self, *args, **kwargs):
        real_cur = self.real_conn.cursor(*args, **kwargs)
        return PostgreSQLCursorWrapper(real_cur, self)

    def commit(self):
        return self.real_conn.commit()

    def rollback(self):
        return self.real_conn.rollback()

    def close(self):
        return self.real_conn.close()

    def __getattr__(self, name):
        return getattr(self.real_conn, name)

app = FastAPI(title="Fibaks ERP Relationship Dashboard")

# Get PostgreSQL Connection Parameters from Environment or use default
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_NAME = os.getenv("DB_NAME", "fibaks_erp")

# Database Mode Flag: 'postgres' or 'sqlite'
DB_MODE = 'postgres'
DB_CONN_ERROR = None
DB_INITIALIZED = False

# Setup templates directory
templates = Jinja2Templates(directory="templates")

# Pydantic Models for Input Validation
class RuleCreate(BaseModel):
    brand: Optional[str] = ""
    model_pattern: Optional[str] = ""
    warning_message: str
    barcodes: Optional[str] = ""

class MappingCreate(BaseModel):
    product_id: str
    device_model: str

def initialize_postgres_db(conn):
    """
    Checks if products table exists. If not, reads init.sql and initializes the PostgreSQL database.
    """
    cur = conn.cursor()
    try:
        cur.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'products');")
        row = cur.fetchone()
        exists = False
        if row:
            if isinstance(row, dict):
                exists = list(row.values())[0]
            else:
                exists = row[0]
        if not exists:
            print("PostgreSQL tablosu bulunamadı. Şema ve tohum verileri init.sql dosyasından yükleniyor...")
            if os.path.exists("init.sql"):
                with open("init.sql", "r", encoding="utf-8") as f:
                    sql_content = f.read()
                cur.execute(sql_content)
                conn.commit()
                print("PostgreSQL şeması başarıyla oluşturuldu ve tohumlandı.")
            else:
                print("Hata: init.sql dosyası bulunamadı, şema oluşturulamadı.")
    except Exception as e:
        print(f"PostgreSQL veritabanı otomatik kurulum hatası: {e}")
        conn.rollback()
    finally:
        cur.close()

def get_db_connection():
    global DB_MODE, DB_CONN_ERROR, DB_INITIALIZED
    
    # 1. DATABASE_URL (Render / Supabase / Neon gibi bulut sağlayıcılar için)
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        try:
            conn = psycopg2.connect(
                database_url,
                cursor_factory=RealDictCursor,
                connect_timeout=3
            )
            wrapped_conn = PostgreSQLConnectionWrapper(conn)
            if not DB_INITIALIZED:
                initialize_postgres_db(wrapped_conn)
                ensure_required_tables(wrapped_conn)
                DB_INITIALIZED = True
            DB_CONN_ERROR = None  # Reset error on success
            return wrapped_conn, 'postgres'
        except Exception as e:
            DB_CONN_ERROR = f"DATABASE_URL Connection Error: {str(e)}"
            print(f"Ortam değişkenindeki DATABASE_URL ile PostgreSQL bağlantı hatası: {e}. SQLite'a geçiliyor...")
            
    # 2. Yerel PostgreSQL (DB_MODE = 'postgres')
    if DB_MODE == 'postgres':
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                dbname=DB_NAME,
                cursor_factory=RealDictCursor,
                connect_timeout=2
            )
            wrapped_conn = PostgreSQLConnectionWrapper(conn)
            if not DB_INITIALIZED:
                initialize_postgres_db(wrapped_conn)
                ensure_required_tables(wrapped_conn)
                DB_INITIALIZED = True
            DB_CONN_ERROR = None  # Reset error on success
            return wrapped_conn, 'postgres'
        except Exception as e:
            if not DB_CONN_ERROR:
                DB_CONN_ERROR = f"Local PostgreSQL Connection Error: {str(e)}"
            print(f"Yerel PostgreSQL bağlantı hatası: {e}. Yerel SQLite veritabanına geçiş yapılıyor...")
            DB_MODE = 'sqlite'
            
    # 3. SQLite (Geliştirme / Fallback)
    sqlite_db_path = "fibaks_erp.db"
    db_exists = os.path.exists(sqlite_db_path)
    conn = sqlite3.connect(sqlite_db_path)
    conn.row_factory = sqlite_dict_factory
    
    if not DB_INITIALIZED:
        if not db_exists:
            print("SQLite veritabanı dosyası oluşturuldu. Tohumlama başlatılıyor...")
            initialize_sqlite_db(conn)
        else:
            ensure_required_tables(conn)
        DB_INITIALIZED = True
        
    return conn, 'sqlite'

def sqlite_dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def infer_generation_group(model_name, brand):
    import re
    name = model_name.strip()
    name_upper = name.upper()
    brand_lower = (brand or "").lower()
    
    if brand_lower == 'apple':
        if 'IPHONE' in name_upper:
            match = re.search(r'iphone\s*(1\d|\d|xs\s*max|xs|xr|x|se)', name, re.IGNORECASE)
            if match:
                val = match.group(0).strip()
                if 'xs' in val.lower():
                    return 'iPhone X'
                if 'xr' in val.lower():
                    return 'iPhone X'
                if 'x' in val.lower() and not '1' in val:
                    return 'iPhone X'
                return val
            return 'iPhone'
        elif 'IPAD' in name_upper or 'AIR' in name_upper:
            match = re.search(r'ipad\s*(air\s*\d+|pro|mini|\d+)?', name, re.IGNORECASE)
            if match:
                return match.group(0).strip()
            return 'iPad'
            
    elif brand_lower == 'samsung':
        if 'GALAXY' in name_upper or name_upper.startswith('S') or 'TAB' in name_upper:
            match = re.search(r'(galaxy\s*tab\s*s\d+|galaxy\s*tab\s*a\d+|galaxy\s*s\d+|galaxy\s*a\d+|galaxy\s*fit\s*\d+)', name, re.IGNORECASE)
            if match:
                return match.group(0).strip()
            return 'Galaxy'
            
    elif brand_lower == 'huawei':
        if 'WATCH FIT' in name_upper or 'FIT' in name_upper:
            return 'Huawei Watch Fit'
        elif 'BAND' in name_upper:
            return 'Huawei Band'
        elif 'GT' in name_upper:
            return 'Huawei Watch GT'
            
    elif brand_lower == 'xiaomi':
        if 'WATCH' in name_upper:
            return 'Redmi Watch'
        elif 'BAND' in name_upper:
            return 'Redmi Band'
        elif 'NOTE' in name_upper:
            match = re.search(r'redmi\s*note\s*\d+', name, re.IGNORECASE)
            if match:
                return match.group(0).strip()
            return 'Redmi Note'
        else:
            match = re.search(r'redmi\s*\d+', name, re.IGNORECASE)
            if match:
                return match.group(0).strip()
            return 'Redmi'
            
    parts = name.split()
    if len(parts) >= 2:
        return " ".join(parts[:2])
    return name

def seed_device_generations(conn):
    cur = conn.cursor()
    try:
        # Get all distinct models from shadow_product_compatibilities
        cur.execute("SELECT DISTINCT normalized_model, brand FROM shadow_product_compatibilities;")
        rows = cur.fetchall()
        for r in rows:
            if isinstance(r, dict):
                model = r["normalized_model"]
                brand = r["brand"]
            else:
                model = r[0]
                brand = r[1]
            
            if not model:
                continue
                
            group = infer_generation_group(model, brand)
            cur.execute("""
                INSERT OR IGNORE INTO device_generations (device_model, generation_group, brand, status)
                VALUES (?, ?, ?, 'VERIFIED');
            """, (model, group, brand))
        conn.commit()
        print("device_generations table successfully seeded from shadow_product_compatibilities.")
    except Exception as e:
        print("Error seeding device_generations:", e)
        conn.rollback()
    finally:
        cur.close()

def ensure_required_tables(conn):
    cur = conn.cursor()
    
    # Monitored rules table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS monitored_rules (
        id TEXT PRIMARY KEY,
        brand TEXT,
        model_pattern TEXT,
        warning_message TEXT NOT NULL,
        barcodes TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TEXT
    );
    """)
    # Check if we are running in SQLite or PostgreSQL
    is_sqlite = hasattr(conn, 'row_factory')  # sqlite3 connection has row_factory
    
    if is_sqlite:
        try:
            cur.execute("ALTER TABLE monitored_rules ADD COLUMN barcodes TEXT;")
        except Exception:
            pass
    else:
        try:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name='monitored_rules' AND column_name='barcodes'
                );
            """)
            row = cur.fetchone()
            col_exists = False
            if row:
                if isinstance(row, dict):
                    col_exists = list(row.values())[0]
                else:
                    col_exists = row[0]
            if not col_exists:
                cur.execute("ALTER TABLE monitored_rules ADD COLUMN barcodes TEXT;")
        except Exception as e:
            print(f"PostgreSQL column check error: {e}")
    
    # Product device mappings table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS product_device_mappings (
        product_id TEXT NOT NULL,
        device_model TEXT NOT NULL,
        created_at TEXT,
        PRIMARY KEY (product_id, device_model)
    );
    """)
    
    # WhatsApp chats/status table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS order_whatsapp_status (
        order_id TEXT PRIMARY KEY,
        phone_status TEXT NOT NULL,   -- 'null', 'hata', 'işleniyor', or mobile number like '+905...'
        message_status TEXT NOT NULL, -- 'cevap bekleniyor', 'başarıyla tamamlandı', 'itiraz - şikayet'
        chat_history TEXT NOT NULL,   -- JSON array of messages
        updated_at TEXT
    );
    """)

    # Shadow compatibility tables
    cur.execute("""
    CREATE TABLE IF NOT EXISTS shadow_compatibility_metadata (
        product_id TEXT PRIMARY KEY,
        original_string TEXT,
        updated_at TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS shadow_product_compatibilities (
        product_id TEXT NOT NULL,
        normalized_model TEXT NOT NULL,
        brand TEXT NOT NULL,
        PRIMARY KEY (product_id, normalized_model)
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_shadow_compat_prod_id ON shadow_product_compatibilities(product_id);")

    # Device generations table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS device_generations (
        device_model TEXT PRIMARY KEY,
        generation_group TEXT NOT NULL,
        brand TEXT NOT NULL,
        status TEXT DEFAULT 'VERIFIED'
    );
    """)

    # CRM Orders Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS crm_orders (
        id INTEGER PRIMARY KEY,
        order_number TEXT,
        marketplace TEXT,
        customer_first_name TEXT,
        customer_last_name TEXT,
        customer_email TEXT,
        order_date TEXT,
        status TEXT,
        total_price NUMERIC,
        shipment_address TEXT,
        raw_data TEXT,
        created_at TEXT,
        updated_at TEXT
    );
    """)
    conn.commit()

    # Seed device generations table if empty
    cur.execute("SELECT COUNT(*) as count FROM device_generations;")
    row = cur.fetchone()
    dg_count = row["count"] if isinstance(row, dict) else (row[0] if row else 0)
    if dg_count == 0:
        seed_device_generations(conn)


    # If crm_orders is empty, copy rows from the legacy "order" table if it exists
    cur.execute("SELECT COUNT(*) as count FROM crm_orders;")
    row = cur.fetchone()
    crm_count = row["count"] if isinstance(row, dict) else (row[0] if row else 0)
    if crm_count == 0:
        try:
            cur.execute('SELECT * FROM "order";')
            legacy_orders = cur.fetchall()
            for o in legacy_orders:
                if hasattr(o, "keys") or isinstance(o, dict):
                    oid = o["id"]
                    order_number = o["order_number"]
                    marketplace = o["marketplace"]
                    first_name = o["customer_first_name"]
                    last_name = o["customer_last_name"]
                    email = o["customer_email"]
                    order_date = o["order_date"]
                    status = o["status"]
                    total_price = o["total_price"]
                    shipment_address = o["shipment_address"]
                    raw_data = o["raw_data"]
                    created_at = o.get("created_at") or order_date
                    updated_at = o.get("updated_at") or order_date
                else:
                    oid = o[0]
                    order_number = o[2]
                    order_date = o[3]
                    status = o[4]
                    total_price = o[7]
                    first_name = o[10]
                    last_name = o[11]
                    email = o[12]
                    shipment_address = o[20]
                    raw_data = o[24]
                    created_at = o[25] or order_date
                    updated_at = o[26] or order_date
                    marketplace = o[27] if len(o) > 27 else "Trendyol"
                
                if isinstance(shipment_address, (dict, list)):
                    shipment_address = json.dumps(shipment_address)
                if isinstance(raw_data, (dict, list)):
                    raw_data = json.dumps(raw_data)
                
                cur.execute("""
                    INSERT OR IGNORE INTO crm_orders (id, order_number, marketplace, customer_first_name, customer_last_name, customer_email, order_date, status, total_price, shipment_address, raw_data, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (oid, order_number, marketplace, first_name, last_name, email, order_date, status, total_price, shipment_address, raw_data, created_at, updated_at))
            conn.commit()
            print(f"Migrated {len(legacy_orders)} orders from legacy table to crm_orders.")
        except Exception as e:
            print("Error migrating legacy orders:", e)
    
    # Kural tablosu boş ise varsayılan kurallarla doldur
    cur.execute("SELECT COUNT(*) as count FROM monitored_rules;")
    row = cur.fetchone()
    if row and row['count'] == 0:
        print("Monitored rules tablosu boş. Varsayılan kurallar tohumlanıyor...")
        import uuid
        rules_seed = [
            (str(uuid.uuid4()), 'Honor', 'Lite', 'Alt model (Lite vs Pro) karıştırılma riski yüksek.'),
            (str(uuid.uuid4()), 'Huawei', 'Watch Fit', 'Kasa boyutu (Watch Fit 2 vs 3) ve kordon uyumsuzluk riski yüksek.')
        ]
        for r in rules_seed:
            cur.execute("""
                INSERT INTO monitored_rules (id, brand, model_pattern, warning_message, is_active, created_at)
                VALUES (?, ?, ?, ?, TRUE, CURRENT_TIMESTAMP);
            """, r)
        conn.commit()

    # WhatsApp CRM tablosu boş ise tohumla
    cur.execute("SELECT COUNT(*) as count FROM order_whatsapp_status;")
    chat_row = cur.fetchone()
    if chat_row and chat_row['count'] == 0:
        print("order_whatsapp_status tablosu boş. Varsayılan CRM sohbetleri tohumlanıyor...")
        chat_seeds = [
            (
                "5049785", 
                "+905321112233", 
                "başarıyla tamamlandı",
                json.dumps([
                    {"sender": "system", "time": "12:30", "text": "Merhaba Volkan Bey, Fibaks'tan sipariş verdiğiniz kılıf ve cam ürünlerinin her ikisi de iPhone 16 Pro modelidir. Siparişinizin doğruluğunu onaylıyor musunuz?"},
                    {"sender": "customer", "time": "12:35", "text": "Evet, ikisi de iPhone 16 Pro cihazım için. Doğrudur, kargoya verebilirsiniz. Teşekkürler."},
                    {"sender": "system", "time": "12:36", "text": "Teyidiniz için teşekkür ederiz. Siparişiniz onaylandı, paketleme aşamasına geçilmiştir. İyi günler dileriz!"}
                ])
            ),
            (
                "5049773", 
                "+905442223344", 
                "itiraz - şikayet",
                json.dumps([
                    {"sender": "system", "time": "14:15", "text": "Merhaba Hande Hanım, Fibaks'tan sipariş ettiğiniz Glacier Kılıf ve 9H Kırılmaz Cam ürünleri iPhone 7 Plus/8 Plus ile uyumludur. Doğruluğunu onaylıyor musunuz?"},
                    {"sender": "customer", "time": "14:22", "text": "Merhaba, ben yanlışlık yapmışım sanırım. Benim telefonum normal iPhone 8. Plus olmayan model. İptal etmemiz veya değiştirmemiz mümkün mü acaba?"},
                    {"sender": "system", "time": "14:25", "text": "Talebiniz alınmıştır. Dilerseniz siparişinizi Plus olmayan standart iPhone 8 boyutlarıyla güncelleyip gönderebiliriz. İster misiniz?"},
                    {"sender": "customer", "time": "14:30", "text": "Aaa çok iyi olur! iPhone 8 kılıfı ve camı gönderirseniz çok sevinirim, iptal etmeyelim o zaman."}
                ])
            ),
            (
                "5049760", 
                "işleniyor", 
                "cevap bekleniyor",
                json.dumps([
                    {"sender": "system", "time": "15:30", "text": "Merhaba Ahmet Bey, siparişinizdeki iPhone 11 Kılıfı ile iPhone 13 Kılıfı farklı cihaz modellerine aittir. İki farklı cihaz için mi satın aldınız?"}
                ])
            ),
            (
                "5049750", 
                "hata", 
                "cevap bekleniyor",
                json.dumps([
                    {"sender": "system", "time": "16:00", "text": "[Sistem Hatası: +90 (000) 000-0000 numarasına mesaj gönderilemedi. Geçersiz veya eksik telefon numarası formatı.]"}
                ])
            ),
            (
                "5049740", 
                "null", 
                "cevap bekleniyor",
                json.dumps([])
            )
        ]
        for c in chat_seeds:
            cur.execute("""
                INSERT OR IGNORE INTO order_whatsapp_status (order_id, phone_status, message_status, chat_history, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'));
            """, c)
        conn.commit()

def initialize_sqlite_db(conn):
    """
    PostgreSQL SQL'imizi SQLite uyumlu hale getirip tohum verileri yükler.
    """
    cur = conn.cursor()
    
    # 1. Tabloları oluştur
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        barcode TEXT,
        name TEXT,
        category TEXT,
        model_code TEXT,
        color TEXT,
        warehouse_id TEXT,
        shelf_column TEXT,
        shelf_row TEXT,
        stock_quantity INT,
        box_no TEXT,
        min_box_quantity INT,
        max_box_quantity INT,
        box_stock_quantity INT,
        product_model TEXT,
        label_name TEXT,
        supplier_name TEXT,
        product_continues BOOLEAN,
        purchase_price_rmb NUMERIC,
        additional_cost NUMERIC,
        cost NUMERIC,
        created_at TEXT,
        updated_at TEXT,
        kutu_bilgisi BOOLEAN,
        islenecek_adet INT,
        label_compatible_model TEXT,
        supplier_color TEXT,
        package_quantity INT,
        transfer_quantity INT,
        min_supply_days INT,
        pending_order_count INT,
        total_suply_count INT,
        additional_barcodes TEXT,
        is_package BOOLEAN,
        avg_sales_before_critical_stock NUMERIC,
        last_below_threshold_date TEXT,
        supplier_note TEXT,
        image_id TEXT,
        total_supply_count INT,
        earliest_supply_quantity INT,
        earliest_supply_delivery_date TEXT,
        earliest_supply_days_remaining INT,
        cost_usd NUMERIC,
        skip_critical_marketplace_stock BOOLEAN,
        is_active BOOLEAN,
        shelf_column_num INT,
        shelf_row_num NUMERIC
    );
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS product_trendyol (
        id TEXT PRIMARY KEY,
        product_id TEXT REFERENCES products(id),
        trendyol_id TEXT,
        barcode TEXT,
        title TEXT,
        product_main_id TEXT,
        stock_code TEXT,
        brand TEXT,
        category_name TEXT,
        quantity INT,
        list_price NUMERIC,
        sale_price NUMERIC,
        product_url TEXT,
        gender TEXT,
        color TEXT,
        size TEXT,
        images TEXT,
        attributes TEXT,
        is_approved BOOLEAN,
        is_on_sale BOOLEAN,
        is_archived BOOLEAN,
        is_converted_to_main BOOLEAN,
        is_matched BOOLEAN,
        last_synced_at TEXT,
        trendyol_created_at TEXT,
        trendyol_updated_at TEXT,
        created_at TEXT,
        updated_at TEXT,
        is_locked BOOLEAN,
        lock_reason TEXT,
        lock_date TEXT,
        doc_needed BOOLEAN,
        has_violation BOOLEAN,
        is_blacklisted BOOLEAN,
        blacklist_reason TEXT
    );
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS product_hepsiburada (
        id TEXT PRIMARY KEY,
        product_id TEXT REFERENCES products(id),
        hb_sku TEXT,
        merchant_sku TEXT,
        barcode TEXT,
        product_name TEXT,
        brand TEXT,
        category_name TEXT,
        category_id TEXT,
        price NUMERIC,
        tax TEXT,
        status TEXT,
        description TEXT,
        images TEXT,
        base_attributes TEXT,
        variant_type_attributes TEXT,
        product_attributes TEXT,
        validation_results TEXT,
        reject_reasons TEXT,
        quality_score NUMERIC,
        quality_status TEXT,
        is_converted_to_main BOOLEAN,
        is_matched BOOLEAN,
        last_synced_at TEXT,
        created_at TEXT,
        updated_at TEXT
    );
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS "order" (
        id INT PRIMARY KEY,
        shipment_package_id BIGINT,
        order_number TEXT,
        order_date TEXT,
        status TEXT,
        gross_amount NUMERIC,
        total_discount NUMERIC,
        total_price NUMERIC,
        currency_code TEXT,
        customer_id BIGINT,
        customer_first_name TEXT,
        customer_last_name TEXT,
        customer_email TEXT,
        supplier_id INT,
        cargo_tracking_number TEXT,
        cargo_provider_name TEXT,
        delivery_type TEXT,
        estimated_delivery_start TEXT,
        estimated_delivery_end TEXT,
        agreed_delivery_date TEXT,
        shipment_address TEXT,
        invoice_address TEXT,
        created_by TEXT,
        last_modified_date TEXT,
        raw_data TEXT,
        created_at TEXT,
        updated_at TEXT,
        marketplace TEXT,
        marketplace_order_id TEXT,
        cargo_provider TEXT,
        barcode_created_at TEXT,
        cargo_provider_changed BOOLEAN,
        is_sorted INT,
        is_cargo_sent INT,
        is_invoice_created INT,
        kargo_tasarimi TEXT,
        micro BOOLEAN,
        sorting_code TEXT,
        group_code TEXT,
        assigned_machine TEXT,
        sorted_date TEXT,
        grup_siralandi INT,
        kargo_siparisno TEXT,
        is_print INT,
        priority_number INT,
        cargo_change_requested_at TEXT,
        is_invoice_sent BOOLEAN
    );
    """)
    
    ensure_required_tables(conn)

    # 2. Tohum Verileri Yükle
    # products (10 satır)
    products_seed = [
        ('b429e551-fb18-4212-80b9-dde6d22dbd7d', '8685032022460', 'Blur iPhone 16 Pro / Siyah', 'KILIF', 'Blur', 'Siyah', 'iPhone 16 Pro', 'İP 16 Pro', 'Black'),
        ('fb79e076-335c-4b8a-9e5a-e0f0d84ef806', '8685032006378', 'Magic Privacy iPhone 16 Pro', 'CAM', 'Magic Privacy', None, 'iPhone 16 Pro', 'İP 16 Pro', 'xxx'),
        ('b0824f7b-aab1-4ce9-bb55-57aebeca6431', '8685032027069', 'Glacier iPhone 7-8 Plus', 'KILIF', 'Glacier', None, 'iPhone 7 Plus', 'İP 7 PLS-8 PLS', 'xxx'),
        ('d035115e-c798-4833-9246-6cf26d093440', '8685032009256', 'Maxi iPhone 6 Plus', 'CAM', 'Maxi ESD', None, 'iPhone 7 Plus', 'İP 6PLS-7PLS-8PLS', 'xxx'),
        ('27830415-eef2-4199-a413-b1bac0a19aeb', '8685032025034', 'Cure iPhone 11 / Siyah', 'KILIF', 'Cure', 'Siyah', 'iPhone 11', 'İP 11', 'Black'),
        ('a0478208-9abb-4f8f-bf76-bb875b241d37', '8685032010009', 'Charm Ayna iPhone 11 / Gümüş', 'KILIF', 'Charm Ayna', 'Gümüş', 'iPhone 11', 'İP 11', 'Silver'),
        ('8a75d1e2-77f4-4f9d-8633-6f8913015062', '8685032038089', 'Gard-02 HW Fit 3 / Şeffaf', 'GARD', 'Gard-02', 'Şeffaf', 'Huawei Watch Fit 3', 'HW Watch Fit 3', 'Clear'),
        ('a82d3a00-4ee6-4669-a019-47064b015777', '8685032008976', 'Hayalet iPhone 11', 'CAM', 'Hayalet ESD', None, 'iPhone 11', 'İP 11-XR', 'xxx'),
        ('387a7080-0b4a-45d0-9b94-1551da1e835a', '8685032010382', 'Blur iPhone 13-14-15 / Siyah', 'KILIF', 'Blur', 'Siyah', 'iPhone 15', 'İP 13-14-15', 'Black'),
        ('c17c463b-d2cb-4eb2-bbc0-f12fb984fffb', '8685032009713', 'CL-07 iPhone 13 / Siyah', 'KAMERA LENS', 'CL-07', 'Siyah', 'iPhone 13', 'İP 13-13 Mini', 'Black')
    ]
    for p in products_seed:
        cur.execute("""
            INSERT OR IGNORE INTO products (id, barcode, name, category, model_code, color, product_model, label_compatible_model, supplier_color, is_active, stock_quantity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 150);
        """, p)

    # product_trendyol
    trendyol_seed = [
        ('aa018b5e-9afd-4cd1-a193-bd283e55fe15', 'fb79e076-335c-4b8a-9e5a-e0f0d84ef806', 'Fibaks-13-Eylül-2024-168', 'Apple iPhone 16 Pro Uyumlu Kolay Uygulama Aparatlı Hayalet Ekran Koruyucu'),
        ('ac2e522e-0090-49fc-b6c5-55a1fa5a1516', 'b429e551-fb18-4212-80b9-dde6d22dbd7d', 'Fibaks-24-Eylül-2024-042', 'iPhone 16 Pro Kılıf Kamera Çıkıntılı Magsafe Şarj Siyah'),
        ('a9d1924a-b92c-45e2-ab74-b2c1b131ef60', 'b0824f7b-aab1-4ce9-bb55-57aebeca6431', 'Fibaks-17-Ocak-002', 'iPhone 7 Plus/8 Plus Kılıf Magsafe Wireless Şeffaf Glacier'),
        ('7b71a95e-320c-43db-b782-db6794b36537', 'd035115e-c798-4833-9246-6cf26d093440', 'Maxi730', 'Apple Iphone 7 Plus 8 Plus Uyumlu 9h Kırılmaz Cam Koruyucu'),
        ('84a01521-8dae-4424-9cc1-262e89f7f6f5', 'a0478208-9abb-4f8f-bf76-bb875b241d37', 'FBR10108120420', 'iPhone 11 Kılıf Aynalı İnci Charm Askılı Kalp Desenli Kapak'),
        ('df9a9cf0-8988-4478-b173-5d4b244ed0e8', '27830415-eef2-4199-a413-b1bac0a19aeb', 'Fibaks-15-Mart-2023-009', 'iPhone 11 Kılıf Magsafe Wireless Şarj Renkli Sert Silikon Ege Kapak')
    ]
    for pt in trendyol_seed:
        cur.execute("""
            INSERT OR IGNORE INTO product_trendyol (id, product_id, barcode, title, brand)
            VALUES (?, ?, ?, ?, 'Fibaks');
        """, pt)

    # product_hepsiburada
    hepsiburada_seed = [
        ('84dda712-2de2-44c7-ae81-99dc1ecf72a4', '8a75d1e2-77f4-4f9d-8633-6f8913015062', '0F40409430011', 'Fibaks Huawei Watch Fit 3 Yumuşak Silikom Kasa ve Ekran Koruyucu 360 Tam Koruma Kapak'),
        ('9e1ede91-4b8e-4369-974a-31eaa2b911a0', 'a82d3a00-4ee6-4669-a019-47064b015777', 'Fiber-Davin-Hayalet-001', 'Fibaks Apple iPhone 11 Uyumlu Tam Kaplayan Hayalet Ekran Koruyucu Gizli Cam'),
        ('afd9eea1-4f8f-43dd-8e97-27caa7b26a40', '387a7080-0b4a-45d0-9b94-1551da1e835a', 'Fiber-09-Temmuz-2024-HB-064', 'Fibaks Apple iPhone 13 Kılıf Kamera Çıkıntılı Magsafe Şarj Destekli Metal Tuşlu Yumuşak Kenarlı Mat Kapak'),
        ('adbc6c44-0094-4b38-894d-7470ecddb43a', 'c17c463b-d2cb-4eb2-bbc0-f12fb984fffb', 'Fiber-3-Aralık-HB-069', 'Apple iPhone 13 Kamera Lens Koruyucu Kırılmaz Cam Kaliteyi Bozmaz Temperli Berrak Koruma Cl-07')
    ]
    for ph in hepsiburada_seed:
        cur.execute("""
            INSERT OR IGNORE INTO product_hepsiburada (id, product_id, barcode, product_name)
            VALUES (?, ?, ?, ?);
        """, ph)

    # product_device_mappings seed (İlk N-to-N Harita Verileri)
    mappings_seed = [
        ('27830415-eef2-4199-a413-b1bac0a19aeb', 'iPhone 11'),
        ('a0478208-9abb-4f8f-bf76-bb875b241d37', 'iPhone 11'),
        ('a82d3a00-4ee6-4669-a019-47064b015777', 'iPhone 11'),
        ('fb79e076-335c-4b8a-9e5a-e0f0d84ef806', 'iPhone 16 Pro'),
        ('b429e551-fb18-4212-80b9-dde6d22dbd7d', 'iPhone 16 Pro'),
        ('b0824f7b-aab1-4ce9-bb55-57aebeca6431', 'iPhone 7 Plus'),
        ('b0824f7b-aab1-4ce9-bb55-57aebeca6431', 'iPhone 8 Plus'),
        ('d035115e-c798-4833-9246-6cf26d093440', 'iPhone 7 Plus'),
        ('d035115e-c798-4833-9246-6cf26d093440', 'iPhone 8 Plus'),
        ('8a75d1e2-77f4-4f9d-8633-6f8913015062', 'Huawei Watch Fit 3'),
        ('387a7080-0b4a-45d0-9b94-1551da1e835a', 'iPhone 13'),
        ('387a7080-0b4a-45d0-9b94-1551da1e835a', 'iPhone 14'),
        ('387a7080-0b4a-45d0-9b94-1551da1e835a', 'iPhone 15'),
        ('c17c463b-d2cb-4eb2-bbc0-f12fb984fffb', 'iPhone 13')
    ]
    for m in mappings_seed:
        cur.execute("""
            INSERT OR IGNORE INTO product_device_mappings (product_id, device_model, created_at)
            VALUES (?, ?, datetime('now'));
        """, m)

    # order
    order1_raw = {
        "lines": [
            {"sku": "Fibaks-24-Eylül-2024-042", "price": 180.0, "barcode": "Fibaks-24-Eylül-2024-042", "quantity": 1, "productName": "iPhone 16 Pro Kılıf Kamera Çıkıntılı Magsafe Şarj Destekli Siyah"},
            {"sku": "Fibaks-13-Eylül-2024-168", "price": 199.0, "barcode": "Fibaks-13-Eylül-2024-168", "quantity": 1, "productName": "Apple iPhone 16 Pro Uyumlu Hayalet Cam Ekran Koruyucu"}
        ]
    }
    order2_raw = {
        "lines": [
            {"sku": "Fibaks-17-Ocak-002", "price": 105.4, "barcode": "Fibaks-17-Ocak-002", "quantity": 1, "productName": "iPhone 7 Plus/8 Plus Kılıf Magsafe Şeffaf Glacier"},
            {"sku": "Maxi730", "price": 120.0, "barcode": "Maxi730", "quantity": 1, "productName": "Apple Iphone 7 Plus 8 Plus Uyumlu 9h Kırılmaz Cam"}
        ]
    }
    order3_raw = {
        "lines": [
            {"sku": "Fibaks-15-Mart-2023-009", "price": 135.0, "barcode": "Fibaks-15-Mart-2023-009", "quantity": 1, "productName": "iPhone 11 Kılıf Magsafe Renkli Sert Silikon Ege Kapak"},
            {"sku": "Fiber-09-Temmuz-2024-HB-064", "price": 370.67, "barcode": "Fiber-09-Temmuz-2024-HB-064", "quantity": 1, "productName": "Fibaks Apple iPhone 13 Kılıf Kamera Çıkıntılı Mat Kapak"}
        ]
    }
    order4_raw = {
        "lines": [
            {"sku": "0F40409430011", "price": 158.82, "barcode": "0F40409430011", "quantity": 1, "productName": "Fibaks Huawei Watch Fit 3 Yumuşak Silikon Kasa ve Ekran Koruyucu"}
        ]
    }
    order5_raw = {
        "lines": [
            {"sku": "FBR10108120420", "price": 160.0, "barcode": "FBR10108120420", "quantity": 1, "productName": "iPhone 11 Kılıf Aynalı İnci Askılı Kapak"},
            {"sku": "Fiber-Davin-Hayalet-001", "price": 197.33, "barcode": "Fiber-Davin-Hayalet-001", "quantity": 1, "productName": "Fibaks Apple iPhone 11 Uyumlu Hayalet Ekran Koruyucu Gizli Cam"}
        ]
    }

    orders = [
        (5049785, 3870663749, '11259832912', '2026-05-22T16:00:10.788Z', 'Picking', 379.0, 379.0, 'Volkan', 'Zorlu', 'volkan@trendyol.com', '{"city": "Ankara"}', '{"city": "Ankara"}', json.dumps(order1_raw), 'Trendyol'),
        (5049773, 3870661492, '11259829197', '2026-05-22T15:58:43.804Z', 'Shipped', 225.4, 225.4, 'Hande', 'Küçük', 'hande@trendyol.com', '{"city": "İstanbul"}', '{"city": "İstanbul"}', json.dumps(order2_raw), 'Trendyol'),
        (5049760, 3870661200, '11259824138', '2026-05-22T15:30:00.000Z', 'Picking', 505.67, 505.67, 'Ahmet', 'Yılmaz', 'ahmet@hepsiburada.com', '{"city": "İzmir"}', '{"city": "İzmir"}', json.dumps(order3_raw), 'Hepsiburada'),
        (5049750, 3870661100, '4824542387', '2026-05-22T14:15:00.000Z', 'Picking', 158.82, 158.82, 'Can', 'Öz', 'can@hepsiburada.com', '{"city": "Bursa"}', '{"city": "Bursa"}', json.dumps(order4_raw), 'Hepsiburada'),
        (5049740, 3870661000, '4078552515', '2026-05-22T13:00:00.000Z', 'Picking', 357.33, 357.33, 'Fatma', 'Demir', 'fatma@hepsiburada.com', '{"city": "Antalya"}', '{"city": "Antalya"}', json.dumps(order5_raw), 'Hepsiburada')
    ]

    for o in orders:
        cur.execute("""
            INSERT OR IGNORE INTO "order" (id, shipment_package_id, order_number, order_date, status, gross_amount, total_price, customer_first_name, customer_last_name, customer_email, shipment_address, invoice_address, raw_data, marketplace)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, o)
        
        # Seed crm_orders
        cur.execute("""
            INSERT OR IGNORE INTO crm_orders (id, order_number, marketplace, customer_first_name, customer_last_name, customer_email, order_date, status, total_price, shipment_address, raw_data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (o[0], o[2], o[13], o[7], o[8], o[9], o[3], o[4], o[6], o[10], o[12], o[3], o[3]))

    # Monitored rules seed
    rules_seed = [
        (str(uuid.uuid4()), 'Honor', 'Lite', 'Alt model (Lite vs Pro) karıştırılma riski yüksek.'),
        (str(uuid.uuid4()), 'Huawei', 'Watch Fit', 'Kasa boyutu (Watch Fit 2 vs 3) ve kordon uyumsuzluk riski yüksek.')
    ]
    for r in rules_seed:
        cur.execute("""
            INSERT OR IGNORE INTO monitored_rules (id, brand, model_pattern, warning_message, is_active, created_at)
            VALUES (?, ?, ?, ?, 1, datetime('now'));
        """, r)

    conn.commit()
    print("SQLite tohumlama tamamlandı!")

def get_active_monitored_rules():
    conn, mode = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM monitored_rules WHERE is_active = 1;")
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

# =====================================================================
# HİYERARŞİK REGEX VE UYUMLULUK YÖNLENDİRME MOTORU (HIERARCHICAL ROUTING)
# =====================================================================

def parse_brand(name):
    """
    Ürün adından veya modelinden cihaz markasını yakalar.
    """
    if not name:
        return "other"
    name = name.lower()
    if any(k in name for k in ["apple", "iphone", "ipad", "i̇phone"]):
        return "apple"
    if "samsung" in name:
        return "samsung"
    if any(k in name for k in ["xiaomi", "redmi", "mi "]):
        return "xiaomi"
    if "huawei" in name:
        return "huawei"
    if "honor" in name:
        return "honor"
    return "other"

def parse_smartwatch_mm(name):
    """
    Model veya ürün adı içinde geçen smartwatch milimetre (mm) boyutlarını yakalar.
    """
    if not name:
        return None
    match = re.search(r'(\d{2})\s*mm', name.lower())
    if match:
        return match.group(1)
    return None



def normalize_model_name(model_name):
    """
    Model ismini harf büyüklüğü ve boşluk duyarsız hale getirerek normalize eder.
    """
    if not model_name:
        return ""
    normalized = model_name.lower().strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized

# =====================================================================
# JIT SHADOW COMPATIBILITY LAYER
# =====================================================================

def parse_brand_from_string(name):
    if not name:
        return "other"
    name = name.lower().replace('ı', 'i').replace('i̇', 'i').replace('ö', 'o').replace('ü', 'u').replace('ş', 's').replace('ç', 'c').replace('ğ', 'g')
    
    if any(k in name for k in ["apple", "iphone", "ipad", "ip "]):
        return "apple"
    if any(k in name for k in ["samsung", "galaxy", "glx"]):
        return "samsung"
    if any(k in name for k in ["xiaomi", "redmi", "rm ", "mi "]):
        return "xiaomi"
    if any(k in name for k in ["huawei", "hw "]):
        return "huawei"
    if any(k in name for k in ["honor", "hnr "]):
        return "honor"
    return "other"

def parse_and_expand_compatibility(product_model, label_compat_str):
    current_original_string = (label_compat_str or "").strip()
    if not current_original_string or current_original_string.lower() == 'null':
        return []
        
    brand = parse_brand_from_string(current_original_string)
    if brand == "other" and product_model:
        brand = parse_brand_from_string(product_model)
        
    is_ipad = False
    if product_model:
        prod_model_upper = product_model.upper()
        if "IPAD" in prod_model_upper:
            is_ipad = True
            
    # Clean prefixes from compatibility string
    model_part = current_original_string
    prefix_matched = None
    for prefix in ["RM NT", "İP", "IP", "GLX", "GALAXY", "RM", "REDMI", "MI", "HW", "HUAWEI", "OP", "OPPO"]:
        if model_part.upper().startswith(prefix + " "):
            prefix_matched = prefix.upper()
            model_part = model_part[len(prefix)+1:].strip()
            break
            
    # Split by '/' or ','
    subparts = []
    for part1 in re.split(r'[/,]', model_part):
        part1 = part1.strip()
        if part1:
            subparts.append(part1)
            
    # Now check each part for hyphen ranges:
    final_models = []
    for part in subparts:
        if "-" in part:
            is_watch = part.lower().endswith("mm")
            clean_part = part
            if is_watch:
                clean_part = part.lower().replace("mm", "").strip()
            
            parts_hyphen = [p.strip() for p in clean_part.split("-")]
            
            expanded = []
            first_part = parts_hyphen[0]
            expanded.append(first_part + ("mm" if is_watch else ""))
            
            for ph in parts_hyphen[1:]:
                if len(ph) <= 3 and ("G" in ph.upper() or "PRO" in ph.upper() or ph.isdigit()):
                    base_match = re.match(r"^(.*?\b)(4G|5G|PRO|ULTRA|\d+)$", first_part, re.IGNORECASE)
                    if base_match:
                        ph_expanded = base_match.group(1) + ph
                    else:
                        ph_expanded = first_part + " " + ph
                else:
                    ph_expanded = ph
                
                expanded.append(ph_expanded + ("mm" if is_watch else ""))
                
            final_models.extend(expanded)
        else:
            final_models.append(part)
            
    results = []
    for m in final_models:
        m_upper = m.upper()
        
        prefix_to_use = ""
        if brand == "apple" and not m.lower().endswith("mm"):
            if not m_upper.startswith("IPHONE") and not m_upper.startswith("IPAD"):
                if is_ipad or "IPAD" in m_upper or "AIR" in m_upper:
                    prefix_to_use = "iPad "
                else:
                    prefix_to_use = "iPhone "
        elif brand == "samsung" and not m.lower().endswith("mm"):
            if not m_upper.startswith("GALAXY") and not m_upper.startswith("S") and not m_upper.startswith("TAB"):
                prefix_to_use = "Galaxy "
            elif m_upper.startswith("S") and not m_upper.startswith("SAMSUNG"):
                if re.match(r"^S\d+", m_upper):
                    prefix_to_use = "Galaxy "
            elif m_upper.startswith("TAB"):
                prefix_to_use = "Galaxy "
        elif brand == "xiaomi" and not m.lower().endswith("mm"):
            if not m_upper.startswith("REDMI") and not m_upper.startswith("XIAOMI") and not m_upper.startswith("MI"):
                if prefix_matched == "RM NT" or (product_model and "NOTE" in product_model.upper()):
                    if m_upper.startswith("NOTE"):
                        prefix_to_use = "Redmi "
                    else:
                        prefix_to_use = "Redmi Note "
                else:
                    prefix_to_use = "Redmi "
                
        # Suffix translation
        norm_m = m
        norm_m = re.sub(r'\bPLS\b', 'Plus', norm_m, flags=re.IGNORECASE)
        norm_m = re.sub(r'([S\d]+)PLS', r'\1 Plus', norm_m, flags=re.IGNORECASE)
        norm_m = re.sub(r'\bNT\b', 'Note', norm_m, flags=re.IGNORECASE)
        
        full_name = f"{prefix_to_use}{norm_m}"
        full_name = re.sub(r'\s+', ' ', full_name).strip()
        
        if "GALAXY" in full_name.upper() and "TAB" not in full_name.upper():
            if product_model and "TAB" in product_model.upper():
                full_name = re.sub(r'\bGalaxy\b', 'Galaxy Tab', full_name, flags=re.IGNORECASE)
                
        results.append((full_name, brand))
        
    return results

def get_or_create_shadow_compatibilities(product_id, product_model, label_compat_str, conn):
    if not product_id:
        return
        
    mode = 'sqlite' if hasattr(conn, 'row_factory') else 'postgres'
    placeholder = '?' if mode == 'sqlite' else '%s'
    cur = conn.cursor()
    
    original_string = (label_compat_str or "").strip()
    
    try:
        # Check current cache
        cur.execute(f"SELECT original_string FROM shadow_compatibility_metadata WHERE product_id = {placeholder}", (product_id,))
        row = cur.fetchone()
        
        # Check dictionary vs tuple row structure
        orig_val = row["original_string"] if isinstance(row, dict) else (row[0] if row else None)
        
        if row and orig_val == original_string:
            return
            
        # If changed, delete and rewrite
        cur.execute(f"DELETE FROM shadow_compatibility_metadata WHERE product_id = {placeholder}", (product_id,))
        cur.execute(f"DELETE FROM shadow_product_compatibilities WHERE product_id = {placeholder}", (product_id,))
        
        now_fn = "datetime('now')" if mode == 'sqlite' else "NOW()"
        cur.execute(f"""
            INSERT INTO shadow_compatibility_metadata (product_id, original_string, updated_at)
            VALUES ({placeholder}, {placeholder}, {now_fn});
        """, (product_id, original_string))
        
        if not original_string or original_string.lower() == 'null':
            conn.commit()
            return
            
        parsed_list = parse_and_expand_compatibility(product_model, original_string)
        for full_name, brand in parsed_list:
            cur.execute(f"""
                INSERT OR IGNORE INTO shadow_product_compatibilities (product_id, normalized_model, brand)
                VALUES ({placeholder}, {placeholder}, {placeholder});
            """, (product_id, full_name, brand))
            
        conn.commit()
    except Exception as e:
        print(f"JIT Compatibility Error for {product_id}: {e}")
        conn.rollback()
    finally:
        cur.close()

def get_product_compatible_set(product_id, erp_product_model, conn):
    if not product_id:
        return {normalize_model_name(erp_product_model)} if erp_product_model else set()
        
    mode = 'sqlite' if hasattr(conn, 'row_factory') else 'postgres'
    placeholder = '?' if mode == 'sqlite' else '%s'
    cur = conn.cursor()
    
    try:
        cur.execute(f"SELECT normalized_model FROM shadow_product_compatibilities WHERE product_id = {placeholder}", (product_id,))
        rows = cur.fetchall()
        if rows:
            res = set()
            for r in rows:
                val = r["normalized_model"] if isinstance(r, dict) else r[0]
                res.add(normalize_model_name(val))
            return res
        return {normalize_model_name(erp_product_model)} if erp_product_model else set()
    except Exception:
        return {normalize_model_name(erp_product_model)} if erp_product_model else set()
    finally:
        cur.close()

def has_common_compatible_model(lines):
    if not lines:
        return True
    common = set(lines[0].get("_compat_set", set()))
    for line in lines[1:]:
        common = common.intersection(line.get("_compat_set", set()))
    return len(common) > 0

def check_generation_mismatch(items, conn):
    """
    Checks if there is a generation mismatch among the items.
    Returns True if there is any pair of incompatible items that share a generation group.
    """
    if len(items) < 2:
        return False
        
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            item_a = items[i]
            item_b = items[j]
            
            # If they are compatible, there is no mismatch between them
            if has_common_compatible_model([item_a, item_b]):
                continue
                
            # If they are incompatible, check if they share a generation family
            compat_a = item_a.get("_compat_set", set())
            compat_b = item_b.get("_compat_set", set())
            
            gen_set_a = set()
            for m in compat_a:
                g = get_or_create_device_generation(m, conn)
                if g:
                    gen_set_a.add(normalize_model_name(g))
                    
            gen_set_b = set()
            for m in compat_b:
                g = get_or_create_device_generation(m, conn)
                if g:
                    gen_set_b.add(normalize_model_name(g))
                    
            if gen_set_a.intersection(gen_set_b):
                return True
                
    return False

def get_mismatched_items(items, conn):
    """
    Returns a list of barcodes/product_ids that participate in a same-generation mismatch.
    Applies majority voting to isolate outliers if a clear majority model exists,
    otherwise falls back to pairwise mismatch flags.
    """
    res = get_mismatch_analysis(items, conn)
    return res["mismatched_barcodes"]

def get_mismatch_analysis(items, conn):
    """
    Analyzes items and returns a dict with:
      - majority_barcodes: list of barcodes in the majority group
      - minority_barcodes: list of barcodes in the minority group (outliers)
      - mismatched_barcodes: flat list of all mismatched barcodes (fallback in case of tie)
    """
    if len(items) < 2:
        return {"majority_barcodes": [], "minority_barcodes": [], "mismatched_barcodes": []}
        
    # 1. Count how many items in this set are compatible with each model
    model_counts = {}
    for item in items:
        compat_set = item.get("_compat_set", set())
        for model in compat_set:
            model_counts[model] = model_counts.get(model, 0) + 1
            
    # Find the maximum agreement count
    max_count = max(model_counts.values()) if model_counts else 0
    
    # 2. Check if we have a clear majority
    majority_models = [m for m, count in model_counts.items() if count == max_count]
    
    if max_count > 1 and len(majority_models) == 1:
        majority_model = majority_models[0]
        majority_gen = get_or_create_device_generation(majority_model, conn)
        majority_gen_norm = normalize_model_name(majority_gen) if majority_gen else ""
        
        majority_barcodes = set()
        minority_barcodes = set()
        
        # Find if there are actually any same-gen mismatch items
        has_outlier_mismatch = False
        for item in items:
            compat_set = item.get("_compat_set", set())
            if majority_model not in compat_set:
                shares_family = False
                for m in compat_set:
                    g = get_or_create_device_generation(m, conn)
                    if g and normalize_model_name(g) == majority_gen_norm:
                        shares_family = True
                        break
                if shares_family:
                    has_outlier_mismatch = True
                    break
                    
        if has_outlier_mismatch:
            for item in items:
                compat_set = item.get("_compat_set", set())
                shares_family = False
                for m in compat_set:
                    g = get_or_create_device_generation(m, conn)
                    if g and normalize_model_name(g) == majority_gen_norm:
                        shares_family = True
                        break
                
                if shares_family:
                    val = item.get("line_barcode") or item.get("erp_product_id")
                    if val:
                        if majority_model in compat_set:
                            majority_barcodes.add(val)
                        else:
                            minority_barcodes.add(val)
                            
            return {
                "majority_barcodes": list(majority_barcodes),
                "minority_barcodes": list(minority_barcodes),
                "mismatched_barcodes": list(majority_barcodes.union(minority_barcodes))
            }
            
    # Fallback: pairwise comparison
    mismatched = set()
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            item_a = items[i]
            item_b = items[j]
            
            # If they are compatible, no mismatch between them
            if has_common_compatible_model([item_a, item_b]):
                continue
                
            # If they are incompatible, check if they share a generation family
            compat_a = item_a.get("_compat_set", set())
            compat_b = item_b.get("_compat_set", set())
            
            gen_set_a = set()
            for m in compat_a:
                g = get_or_create_device_generation(m, conn)
                if g:
                    gen_set_a.add(normalize_model_name(g))
                    
            gen_set_b = set()
            for m in compat_b:
                g = get_or_create_device_generation(m, conn)
                if g:
                    gen_set_b.add(normalize_model_name(g))
                    
            if gen_set_a.intersection(gen_set_b):
                val_a = item_a.get("line_barcode") or item_a.get("erp_product_id")
                val_b = item_b.get("line_barcode") or item_b.get("erp_product_id")
                if val_a: mismatched.add(val_a)
                if val_b: mismatched.add(val_b)
                
    return {
        "majority_barcodes": [],
        "minority_barcodes": [],
        "mismatched_barcodes": list(mismatched)
    }

def get_or_create_device_generation(model_name, conn):
    if not model_name:
        return None
        
    mode = 'sqlite' if hasattr(conn, 'row_factory') else 'postgres'
    placeholder = '?' if mode == 'sqlite' else '%s'
    cur = conn.cursor()
    
    try:
        cur.execute(f"SELECT generation_group FROM device_generations WHERE LOWER(device_model) = LOWER({placeholder})", (model_name,))
        row = cur.fetchone()
        if row:
            val = row["generation_group"] if isinstance(row, dict) else row[0]
            return val
            
        # Guess/infer and insert as PENDING_REVIEW if not found
        brand = parse_brand_from_string(model_name)
        guessed_group = infer_generation_group(model_name, brand)
        
        cur.execute(f"""
            INSERT OR IGNORE INTO device_generations (device_model, generation_group, brand, status)
            VALUES ({placeholder}, {placeholder}, {placeholder}, 'PENDING_REVIEW');
        """, (model_name, guessed_group, brand))
        conn.commit()
        print(f"JIT Auto-Guess: Mapped '{model_name}' to group '{guessed_group}' (brand: {brand})")
        return guessed_group
    except Exception as e:
        print(f"Error in get_or_create_device_generation for '{model_name}': {e}")
        brand = parse_brand_from_string(model_name)
        return infer_generation_group(model_name, brand)
    finally:
        cur.close()

def generate_mismatch_desc(items, display_name, conn):
    line_models = []
    line_gens = []
    for line in items:
        compat_set = line.get("_compat_set", set())
        # Sort model names and format beautifully
        cleaned_models = []
        for m in sorted(list(compat_set)):
            # Capitalize brand names nicely
            if m.lower().startswith('iphone'):
                cleaned_models.append('iPhone' + m[6:])
            elif m.lower().startswith('ipad'):
                cleaned_models.append('iPad' + m[4:])
            elif m.lower().startswith('galaxy'):
                cleaned_models.append('Galaxy' + m[6:])
            elif m.lower().startswith('huawei'):
                cleaned_models.append('Huawei' + m[6:])
            elif m.lower().startswith('redmi'):
                cleaned_models.append('Redmi' + m[5:])
            else:
                cleaned_models.append(m.title())
        models_str = "/".join(cleaned_models)
        line_models.append(models_str)
        
        # Get generation families
        for model in compat_set:
            gen_group = get_or_create_device_generation(model, conn)
            if gen_group:
                normalized_group = gen_group.strip()
                if normalized_group.lower().startswith('iphone'):
                    normalized_group = 'iPhone' + normalized_group[6:]
                elif normalized_group.lower().startswith('ipad'):
                    normalized_group = 'iPad' + normalized_group[4:]
                elif normalized_group.lower().startswith('galaxy'):
                    normalized_group = 'Galaxy' + normalized_group[6:]
                elif normalized_group.lower().startswith('huawei'):
                    normalized_group = 'Huawei' + normalized_group[6:]
                elif normalized_group.lower().startswith('redmi'):
                    normalized_group = 'Redmi' + normalized_group[5:]
                else:
                    normalized_group = normalized_group.title()
                
                # Case-insensitive deduplication
                if not any(g.lower() == normalized_group.lower() for g in line_gens):
                    line_gens.append(normalized_group)
                
    family_str = " & ".join(line_gens)
    
    # Standardize names for sample message
    model_a = line_models[0] if len(line_models) > 0 else "Model A"
    model_b = line_models[1] if len(line_models) > 1 else "Model B"
    
    desc = "Aynı cihaz ailesine ait fakat ölçüleri farklı cihazlar için uyumsuz aksesuarlar tespit edildi:|Müşterinin yanlışlıkla uyumsuz model sipariş etmiş olma ihtimali çok yüksek."
    return desc

def evaluate_red_flags(order_lines, conn=None):
    flags = []
    score = 0
    
    close_conn = False
    if not conn:
        conn, mode = get_db_connection()
        close_conn = True
        
    cur = conn.cursor()
    
    try:
        # Step 0. Pre-fetch and JIT process each line's compatible set
        for line in order_lines:
            pid = line.get("erp_product_id")
            if pid:
                cur.execute("SELECT product_model, label_compatible_model FROM products WHERE id = ?", (pid,))
                prod_row = cur.fetchone()
                if prod_row:
                    if hasattr(prod_row, "keys"):
                        current_label_compat = prod_row["label_compatible_model"]
                        prod_model = prod_row["product_model"]
                    elif isinstance(prod_row, dict):
                        current_label_compat = prod_row.get("label_compatible_model")
                        prod_model = prod_row.get("product_model")
                    else:
                        prod_model = prod_row[0]
                        current_label_compat = prod_row[1]
                    get_or_create_shadow_compatibilities(pid, prod_model, current_label_compat, conn)
                    
        # Add compatible sets to lines
        for line in order_lines:
            pid = line.get("erp_product_id")
            pmodel = line.get("erp_product_model")
            line["_compat_set"] = get_product_compatible_set(pid, pmodel, conn)
            
        # Evaluate custom monitored rules dynamically (runs for any size of order)
        cur.execute("SELECT brand, model_pattern, warning_message, barcodes FROM monitored_rules WHERE is_active = 1;")
        active_rules = cur.fetchall()
        for rule in active_rules:
            try:
                r_brand = rule["brand"]
                r_pattern = rule["model_pattern"]
                r_msg = rule["warning_message"]
                r_barcodes = rule["barcodes"]
            except Exception:
                try:
                    r_brand = rule[0]
                    r_pattern = rule[1]
                    r_msg = rule[2]
                    r_barcodes = rule[3]
                except Exception:
                    continue
                    
            r_brand_clean = (r_brand or "").strip().lower()
            r_pattern_clean = (r_pattern or "").strip().lower()
            
            # Parse commas/spaces separated barcodes
            r_barcodes_clean = []
            if r_barcodes:
                r_barcodes_clean = [b.strip() for b in r_barcodes.replace(',', ' ').split() if b.strip()]
                
            matching_barcodes = []
            matching_categories = set()
            
            if r_barcodes_clean:
                # Match specifically by barcode lists
                for line in order_lines:
                    barcode = line.get("line_barcode")
                    pid = line.get("erp_product_id")
                    barcode_match = (barcode and barcode in r_barcodes_clean) or (pid and pid in r_barcodes_clean)
                    if barcode_match:
                        val = barcode or pid
                        matching_barcodes.append(val)
                        cat = line.get("erp_category")
                        if cat:
                            matching_categories.add(cat)
            else:
                # Match by brand and pattern
                if not r_brand_clean:
                    continue
                    
                for line in order_lines:
                    p_name = (line.get("erp_product_name") or line.get("marketplace_title") or "").strip().lower()
                    p_model = (line.get("erp_product_model") or "").strip().lower()
                    p_compat = (line.get("erp_compatible_model") or "").strip().lower()
                    
                    # Check brand
                    brand_match = (r_brand_clean in p_name) or (r_brand_clean in p_model) or (r_brand_clean in p_compat)
                    
                    # Check pattern
                    if not r_pattern_clean:
                        pattern_match = True
                    else:
                        pattern_match = (r_pattern_clean in p_name) or (r_pattern_clean in p_model) or (r_pattern_clean in p_compat)
                        
                    if brand_match and pattern_match:
                        val = line.get("line_barcode") or line.get("erp_product_id")
                        if val:
                            matching_barcodes.append(val)
                        cat = line.get("erp_category")
                        if cat:
                            matching_categories.add(cat)
                            
            if matching_barcodes:
                score += 50
                cat_display = "_AND_".join(sorted(list(matching_categories))) if matching_categories else "KILIF"
                title_suffix = f"{r_brand} {r_pattern or ''}" if r_brand_clean else "Belirli Barkodlar"
                flags.append({
                    "type": "WARNING",
                    "title": f"Özel Risk Kuralı: {title_suffix} ⚠️",
                    "desc": f"{r_msg}|Belirtilen özel risk filtresiyle eşleşen ürün(ler) tespit edildi.",
                    "score": 50,
                    "category": cat_display,
                    "mismatched_barcodes": matching_barcodes,
                    "majority_barcodes": [],
                    "minority_barcodes": []
                })
            
        # 1. Tetiklenme Koşulu: Eğer siparişte 2 veya daha fazla ürün varsa incelemeye başla
        if len(order_lines) >= 2:
            flags.append({
                "type": "INFO",
                "title": "Çoklu Ürün Siparişi",
                "desc": f"Siparişte {len(order_lines)} farklı ürün kalemi bulunmaktadır.",
                "score": 0
            })
            
            # Kategorilere göre grupla (case-insensitive & locale-independent)
            categories = {}
            for line in order_lines:
                cat = line.get("erp_category")
                if cat:
                    cat_key = cat.strip().replace('ı', 'i').replace('I', 'i').upper()
                    if cat_key not in categories:
                        categories[cat_key] = []
                    categories[cat_key].append(line)
            
            # Her kategoriyi kendi içinde değerlendir
            for cat, items in categories.items():
                if len(items) > 1:
                    # Find mismatch groups in this category
                    mismatch_by_gen = {}
                    for i in range(len(items)):
                        for j in range(i + 1, len(items)):
                            item_a = items[i]
                            item_b = items[j]
                            
                            if has_common_compatible_model([item_a, item_b]):
                                continue
                                
                            compat_a = item_a.get("_compat_set", set())
                            compat_b = item_b.get("_compat_set", set())
                            
                            gen_set_a = set()
                            for m in compat_a:
                                g = get_or_create_device_generation(m, conn)
                                if g: gen_set_a.add(g)
                                
                            gen_set_b = set()
                            for m in compat_b:
                                g = get_or_create_device_generation(m, conn)
                                if g: gen_set_b.add(g)
                                
                            shared_gens = gen_set_a.intersection(gen_set_b)
                            for gen in shared_gens:
                                if gen not in mismatch_by_gen:
                                    mismatch_by_gen[gen] = set()
                                mismatch_by_gen[gen].add(i)
                                mismatch_by_gen[gen].add(j)
                                
                    # Generate warning flags for each mismatch group
                    for gen_group, item_indices in mismatch_by_gen.items():
                        group_items = [items[idx] for idx in item_indices]
                        analysis_res = get_mismatch_analysis(group_items, conn)
                        score += 80
                        
                        cat_clean = cat.replace('_', ' ').lower()
                        if 'kilif' in cat_clean:
                            cat_clean = cat_clean.replace('kilif', 'kılıf')
                        cat_display = cat_clean.title()
                        
                        gen_display = gen_group.strip()
                        if gen_display.lower().startswith('iphone'):
                            gen_display = 'iPhone ' + gen_display[6:].strip()
                        elif gen_display.lower().startswith('ipad'):
                            gen_display = 'iPad ' + gen_display[4:].strip()
                        elif gen_display.lower().startswith('galaxy'):
                            gen_display = 'Galaxy ' + gen_display[6:].strip()
                        elif gen_display.lower().startswith('huawei'):
                            gen_display = 'Huawei ' + gen_display[6:].strip()
                        elif gen_display.lower().startswith('redmi'):
                            gen_display = 'Redmi ' + gen_display[5:].strip()
                        else:
                            gen_display = gen_display.title()
                            
                        mismatch_desc = generate_mismatch_desc(group_items, f"{cat_display} ({gen_display})", conn)
                        flags.append({
                            "type": "CRITICAL",
                            "title": f"{cat_display} ({gen_display} Serisi) - Modeli Uyuşmazlığı 🔴",
                            "desc": mismatch_desc,
                            "score": 80,
                            "category": cat,
                            "mismatched_barcodes": analysis_res.get("mismatched_barcodes", []),
                            "majority_barcodes": analysis_res.get("majority_barcodes", []),
                            "minority_barcodes": analysis_res.get("minority_barcodes", [])
                        })
            
            # Cross-kategori uyum kontrolleri (Kılıf & Cam / Tablet Kılıf & Tablet Cam / Gard & Kordon)
            cross_pairs = [
                ("KILIF", "CAM", "Telefon Kılıfı & Cam Filmi"),
                ("KILIF", "KAMERA LENS", "Telefon Kılıfı & Kamera Lens"),
                ("CAM", "KAMERA LENS", "Cam Filmi & Kamera Lens"),
                ("TABLET KILIF", "TABLET CAM", "Tablet Kılıfı & Cam Filmi"),
                ("GARD", "KORDON", "Akıllı Saat Gard & Kordon")
            ]
            
            for cat1, cat2, display_name in cross_pairs:
                items1 = categories.get(cat1, [])
                items2 = categories.get(cat2, [])
                if len(items1) > 0 and len(items2) > 0:
                    combined = items1 + items2
                    
                    # Find mismatch groups in this cross category
                    mismatch_by_gen = {}
                    for i in range(len(combined)):
                        for j in range(i + 1, len(combined)):
                            item_a = combined[i]
                            item_b = combined[j]
                            
                            if has_common_compatible_model([item_a, item_b]):
                                continue
                                
                            compat_a = item_a.get("_compat_set", set())
                            compat_b = item_b.get("_compat_set", set())
                            
                            gen_set_a = set()
                            for m in compat_a:
                                g = get_or_create_device_generation(m, conn)
                                if g: gen_set_a.add(g)
                                
                            gen_set_b = set()
                            for m in compat_b:
                                g = get_or_create_device_generation(m, conn)
                                if g: gen_set_b.add(g)
                                
                            shared_gens = gen_set_a.intersection(gen_set_b)
                            for gen in shared_gens:
                                if gen not in mismatch_by_gen:
                                    mismatch_by_gen[gen] = set()
                                mismatch_by_gen[gen].add(i)
                                mismatch_by_gen[gen].add(j)
                                
                    # Generate warning flags for each mismatch group
                    for gen_group, item_indices in mismatch_by_gen.items():
                        group_items = [combined[idx] for idx in item_indices]
                        analysis_res = get_mismatch_analysis(group_items, conn)
                        score += 80
                        
                        gen_display = gen_group.strip()
                        if gen_display.lower().startswith('iphone'):
                            gen_display = 'iPhone ' + gen_display[6:].strip()
                        elif gen_display.lower().startswith('ipad'):
                            gen_display = 'iPad ' + gen_display[4:].strip()
                        elif gen_display.lower().startswith('galaxy'):
                            gen_display = 'Galaxy ' + gen_display[6:].strip()
                        elif gen_display.lower().startswith('huawei'):
                            gen_display = 'Huawei ' + gen_display[6:].strip()
                        elif gen_display.lower().startswith('redmi'):
                            gen_display = 'Redmi ' + gen_display[5:].strip()
                        else:
                            gen_display = gen_display.title()
                            
                        mismatch_desc = generate_mismatch_desc(group_items, f"{display_name} ({gen_display})", conn)
                        flags.append({
                            "type": "CRITICAL",
                            "title": f"{display_name} ({gen_display} Serisi) - Uyuşmazlığı 🔴",
                            "desc": mismatch_desc,
                            "score": 80,
                            "category": f"{cat1}_AND_{cat2}",
                            "mismatched_barcodes": analysis_res.get("mismatched_barcodes", []),
                            "majority_barcodes": analysis_res.get("majority_barcodes", []),
                            "minority_barcodes": analysis_res.get("minority_barcodes", [])
                        })
    finally:
        if close_conn:
            cur.close()
            conn.close()
            
    # Risk puanını 0 ile 100 arasında sınırla (Extensible cap)
    score = min(score, 100)
    
    # Genel risk durum rengi tayini: 60 ve üzeri Kırmızı, 0-59 Turuncu, 0 Yeşil
    status_color = "green"
    if score >= 60:
        status_color = "red"
    elif score > 0:
        status_color = "orange"
        
    critical_count = len([f for f in flags if f["type"] == "CRITICAL"])
    warning_count = len([f for f in flags if f["type"] == "WARNING"])
        
    return {
        "flags": flags,
        "status_color": status_color,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "risk_score": score
    }

def fetch_resolved_orders():
    conn, mode = get_db_connection()
    cur = conn.cursor()
    placeholder = '?' if mode == 'sqlite' else '%s'
    
    try:
        cur.execute('SELECT * FROM crm_orders ORDER BY order_date DESC;')
        orders = cur.fetchall()
        
        resolved_orders = []
        for o in orders:
            raw_data = o["raw_data"]
            if isinstance(raw_data, str):
                raw_data = json.loads(raw_data)
                
            lines = raw_data.get("lines", [])
            marketplace = o["marketplace"]
            
            resolved_lines = []
            for line in lines:
                barcode = line.get("barcode")
                quantity = line.get("quantity", 1)
                price = line.get("price", 0)
                product_name = line.get("productName", "")
                
                erp_product = None
                # Siparişin geldiği pazaryerine göre öncelikli arama yap, bulamazsa diğer pazaryerinden sorgula
                if marketplace == "Trendyol":
                    cur.execute(f"""
                        SELECT p.* 
                        FROM product_trendyol pt
                        JOIN products p ON p.id = pt.product_id
                        WHERE pt.barcode = {placeholder};
                    """, (barcode,))
                    erp_product = cur.fetchone()
                    
                    if not erp_product:
                        cur.execute(f"""
                            SELECT p.* 
                            FROM product_hepsiburada ph
                            JOIN products p ON p.id = ph.product_id
                            WHERE ph.barcode = {placeholder};
                        """, (barcode,))
                        erp_product = cur.fetchone()
                else:
                    cur.execute(f"""
                        SELECT p.* 
                        FROM product_hepsiburada ph
                        JOIN products p ON p.id = ph.product_id
                        WHERE ph.barcode = {placeholder};
                    """, (barcode,))
                    erp_product = cur.fetchone()
                    
                    if not erp_product:
                        cur.execute(f"""
                            SELECT p.* 
                            FROM product_trendyol pt
                            JOIN products p ON p.id = pt.product_id
                            WHERE pt.barcode = {placeholder};
                        """, (barcode,))
                        erp_product = cur.fetchone()
                
                resolved_lines.append({
                    "line_barcode": barcode,
                    "quantity": quantity,
                    "price": price,
                    "marketplace_title": product_name,
                    "erp_product_id": erp_product["id"] if erp_product else None,
                    "erp_product_name": erp_product["name"] if erp_product else "Eşleşme Bulunamadı",
                    "erp_category": erp_product["category"] if erp_product else None,
                    "erp_product_model": erp_product["product_model"] if erp_product else None,
                    "erp_compatible_model": erp_product["label_compatible_model"] if erp_product else None,
                    "erp_color": erp_product["color"] if erp_product else None
                })
            
            analysis = evaluate_red_flags(resolved_lines)
            
            order_date_val = o["order_date"]
            if not isinstance(order_date_val, str) and order_date_val:
                order_date_val = order_date_val.isoformat()
            
            resolved_orders.append({
                "id": o["id"],
                "order_number": o["order_number"],
                "order_date": order_date_val,
                "status": o["status"],
                "total_price": float(o["total_price"]),
                "marketplace": marketplace,
                "customer_name": f"{o['customer_first_name']} {o['customer_last_name']}",
                "customer_email": o["customer_email"],
                "lines": resolved_lines,
                "flags": analysis["flags"],
                "status_color": analysis["status_color"],
                "critical_count": analysis["critical_count"],
                "warning_count": analysis["warning_count"],
                "risk_score": analysis["risk_score"]
            })
            
        return resolved_orders
    finally:
        cur.close()
        conn.close()

# --- WEB ENDPOINTS ---

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/database", response_class=HTMLResponse)
async def database_explorer_page(request: Request):
    return templates.TemplateResponse("database.html", {"request": request})

@app.get("/api/db-raw")
async def get_raw_table_data(table: str):
    if table not in ["products", "order", "crm_orders", "product_trendyol", "product_hepsiburada", "erp_proposal", "product_device_mappings", "shadow_compatibility_metadata", "shadow_product_compatibilities", "device_generations"]:
        return {"error": "Geçersiz tablo adı"}
    
    if table == "erp_proposal":
        return [
            {
                "hedef_kolon": "id",
                "veri_tipi": "UUID (Primary Key)",
                "kaynak_tablo": "order / product_trendyol",
                "kaynak_kolon": "id",
                "aciklama": "Entegrasyon ve risk kaydı benzersiz anahtarı.",
                "ornek_veri": "res-8f12a3-9b4c"
            },
            {
                "hedef_kolon": "erp_order_id",
                "veri_tipi": "UUID (Foreign Key -> erp.orders.id)",
                "kaynak_tablo": "order (ERP Sipariş Tablosu)",
                "kaynak_kolon": "id",
                "aciklama": "ERP sistemindeki sipariş kaydının ID'si. İki yönlü sipariş durumu eşitlemesi için zorunludur.",
                "ornek_veri": "a0478208-9abb-4f8f-bf76-bb875b241d37"
            },
            {
                "hedef_kolon": "marketplace_order_number",
                "veri_tipi": "VARCHAR(255) (Index)",
                "kaynak_tablo": "order (Sipariş Detayı)",
                "kaynak_kolon": "order_number",
                "aciklama": "Pazaryeri (Trendyol / Hepsiburada) sipariş numarası. Müşteriye WhatsApp'tan yazarken siparişi bulmasını sağlar.",
                "ornek_veri": "304918231"
            },
            {
                "hedef_kolon": "marketplace",
                "veri_tipi": "VARCHAR(100)",
                "kaynak_tablo": "order (Sipariş Detayı)",
                "kaynak_kolon": "marketplace",
                "aciklama": "Siparişin geldiği entegrasyon kanalı ('Trendyol', 'Hepsiburada', 'Amazon' vb.).",
                "ornek_veri": "Trendyol"
            },
            {
                "hedef_kolon": "customer_phone",
                "veri_tipi": "VARCHAR(50)",
                "kaynak_tablo": "Harici CRM / Müşteri Rehberi (Harici Kaynak)",
                "kaynak_kolon": "phone / mobile (Mevcut Değil - Harici Eşleşme)",
                "aciklama": "Müşterinin WhatsApp üzerinden iletişime geçilecek telefon numarası. Sipariş tablosunda bulunmaz, harici CRM veya API üzerinden eşleştirilerek çekilir.",
                "ornek_veri": "+905551234567"
            },
            {
                "hedef_kolon": "customer_name",
                "veri_tipi": "VARCHAR(255)",
                "kaynak_tablo": "order (Sipariş Detayı)",
                "kaynak_kolon": "shipment_address.fullName",
                "aciklama": "WhatsApp mesajını kişiselleştirmek için müşterinin adı soyadı. Siparişteki teslimat adresindeki (shipment_address) 'fullName' alanından ayıklanır.",
                "ornek_veri": "Murat Dex"
            },
            {
                "hedef_kolon": "marketplace_product_title",
                "veri_tipi": "VARCHAR(555)",
                "kaynak_tablo": "order (Sipariş Detayı)",
                "kaynak_kolon": "raw_data.items[].title",
                "aciklama": "Müşterinin pazaryerinde (Trendyol/Hepsiburada) görerek tıkladığı ve satın aldığı ürün başlığı.",
                "ornek_veri": "Blur iPhone 16 Pro Max / Siyah"
            },
            {
                "hedef_kolon": "erp_product_id",
                "veri_tipi": "UUID (Foreign Key -> products.id)",
                "kaynak_tablo": "product_trendyol / product_hepsiburada",
                "kaynak_kolon": "product_id",
                "aciklama": "Eşleşen ERP depo ürün kartının benzersiz ID'si.",
                "ornek_veri": "mock-ip16promax-kilif"
            },
            {
                "hedef_kolon": "erp_product_name",
                "veri_tipi": "VARCHAR(555)",
                "kaynak_tablo": "products (Depo Ürün Kartı)",
                "kaynak_kolon": "name",
                "aciklama": "ERP depo ürün kartındaki gerçek başlık. **Regex kuralları çalıştırılırken (örn. model/renk uyuşmazlığı tespiti) kullanılacak ham veridir.**",
                "ornek_veri": "Blur iPhone 16 Pro Max / Siyah"
            },
            {
                "hedef_kolon": "category",
                "veri_tipi": "VARCHAR(100)",
                "kaynak_tablo": "products (Depo Ürün Kartı)",
                "kaynak_kolon": "category",
                "aciklama": "Ürünün kategorisi (örn. 'KILIF', 'CAM', 'KORDON'). Kural motorunda kategorisel süzme ve öncelik kuralı işletmek için kullanılır.",
                "ornek_veri": "KILIF"
            },
            {
                "hedef_kolon": "product_model",
                "veri_tipi": "VARCHAR(100)",
                "kaynak_tablo": "products (Depo Ürün Kartı)",
                "kaynak_kolon": "product_model",
                "aciklama": "ERP kartındaki ürün modeli (örn. 'iPhone 16 Pro Max'). Regex motoruyla cihaz modeli uyuşmazlığını denetlemek için kritiktir.",
                "ornek_veri": "iPhone 16 Pro Max"
            },
            {
                "hedef_kolon": "color",
                "veri_tipi": "VARCHAR(50)",
                "kaynak_tablo": "products (Depo Ürün Kartı)",
                "kaynak_kolon": "color",
                "aciklama": "ERP kartındaki ürün rengi (örn. 'Siyah'). Renk uyuşmazlığı denetimleri için kullanılır.",
                "ornek_veri": "Siyah"
            },
            {
                "hedef_kolon": "risk_status",
                "veri_tipi": "VARCHAR(100)",
                "kaynak_tablo": "Konsolide (Yeni Alan - WhatsApp Risk)",
                "kaynak_kolon": "Mevcut Değil",
                "aciklama": "Siparişin WhatsApp risk/iletişim durumu (örn. 'SAFE', 'SUSPECTED', 'CONTACTED', 'RESOLVED_APPROVED', 'RESOLVED_CANCELLED'). Panelimiz bu alanı yazar.",
                "ornek_veri": "SUSPECTED"
            },
            {
                "hedef_kolon": "risk_reason",
                "veri_tipi": "TEXT",
                "kaynak_tablo": "Konsolide (Yeni Alan - WhatsApp Risk)",
                "kaynak_kolon": "Mevcut Değil",
                "aciklama": "Siparişin neden şüpheli işaretlendiğinin gerekçesi (örn. 'Model Uyuşmazlığı: Sipariş iPhone 16 Pro Max iken, açıklama iPhone 16 Pro').",
                "ornek_veri": "Model uyuşmazlığı algılandı."
            },
            {
                "hedef_kolon": "erp_sync_status",
                "veri_tipi": "VARCHAR(100)",
                "kaynak_tablo": "Konsolide (Yeni Alan - ERP Geri Bildirim)",
                "kaynak_kolon": "Mevcut Değil",
                "aciklama": "**ERP sisteminin okuyacağı sipariş onay durumu** (örn. 'HOLD', 'RELEASED_TO_CARRIER', 'CANCELLED_BY_CUSTOMER'). Hem ERP hem de risk panelimiz burayı günceller ve okur.",
                "ornek_veri": "HOLD"
            },
            {
                "hedef_kolon": "updated_at",
                "veri_tipi": "TIMESTAMPTZ",
                "kaynak_tablo": "Konsolide (Ortak Sütun)",
                "kaynak_kolon": "Mevcut Değil",
                "aciklama": "Kaydın hem ERP hem de risk sistemi tarafından en son güncellenme zaman damgası.",
                "ornek_veri": "2026-05-31 10:20:00"
            }
        ]
    
    conn, mode = get_db_connection()
    cur = conn.cursor()
    try:
        # Secure table whitelist query
        if table == "order":
            query = 'SELECT * FROM "order" ORDER BY id DESC;'
        elif table == "crm_orders":
            query = 'SELECT * FROM crm_orders ORDER BY id DESC;'
        else:
            query = f'SELECT * FROM {table};'
            
        cur.execute(query)
        rows = cur.fetchall()
        
        # Convert rows to serializable dicts
        resolved = []
        for r in rows:
            d = dict(r)
            # Handle bytes/special structures
            for k, v in d.items():
                if isinstance(v, bytes):
                    d[k] = v.decode('utf-8', errors='ignore')
            resolved.append(d)
            
        return resolved
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.get("/api/product-mappings")
async def get_product_mappings(product_id: str):
    conn, mode = get_db_connection()
    cur = conn.cursor()
    try:
        if mode == 'sqlite':
            cur.execute("""
                SELECT id, product_id, barcode, title, brand 
                FROM product_trendyol 
                WHERE product_id = ?;
            """, (product_id,))
        else:
            cur.execute("""
                SELECT id, product_id, barcode, title, brand 
                FROM product_trendyol 
                WHERE product_id = %s;
            """, (product_id,))
        trendyol_rows = cur.fetchall()
        
        if mode == 'sqlite':
            cur.execute("""
                SELECT id, product_id, barcode, product_name AS title, brand 
                FROM product_hepsiburada 
                WHERE product_id = ?;
            """, (product_id,))
        else:
            cur.execute("""
                SELECT id, product_id, barcode, product_name AS title, brand 
                FROM product_hepsiburada 
                WHERE product_id = %s;
            """, (product_id,))
        hepsiburada_rows = cur.fetchall()
        
        ty_resolved = []
        for r in trendyol_rows:
            d = dict(r)
            for k, v in d.items():
                if isinstance(v, bytes):
                    d[k] = v.decode('utf-8', errors='ignore')
            ty_resolved.append(d)
            
        hb_resolved = []
        for r in hepsiburada_rows:
            d = dict(r)
            for k, v in d.items():
                if isinstance(v, bytes):
                    d[k] = v.decode('utf-8', errors='ignore')
            hb_resolved.append(d)
            
        return {
            "trendyol": ty_resolved,
            "hepsiburada": hb_resolved
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.get("/api/orders")
async def get_orders():
    try:
        orders = fetch_resolved_orders()
        return orders
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/orders/simulate")
async def simulate_new_orders():
    import random
    from datetime import datetime
    import json
    
    conn, mode = get_db_connection()
    cur = conn.cursor()
    placeholder = '?' if mode == 'sqlite' else '%s'
    
    try:
        # Seed on-demand simulation products to ensure perfect barcode mapping resolution
        mock_products = [
            # iPhone 15 Pro vs Pro Max (Variant Mismatch)
            ("mock-ip15pro", "8685032039017", "Blur iPhone 15 Pro / Lacivert", "KILIF", "iPhone 15 Pro", "Lacivert", "İP 15 Pro"),
            ("mock-ip15promax", "8685032039018", "Blur iPhone 15 Pro Max / Lacivert", "KILIF", "iPhone 15 Pro Max", "Lacivert", "İP 15 Pro Max"),
            # Redmi 13 Pro 4G vs 5G (Network Gen Mismatch)
            ("mock-redmi13pro4g", "8685032039021", "Glacier Redmi Note 13 Pro 4G / Şeffaf", "KILIF", "Redmi Note 13 Pro 4G", "Şeffaf", "Redmi Note 13 Pro 4G"),
            ("mock-redmi13pro5g", "8685032039022", "Glacier Redmi Note 13 Pro 5G / Şeffaf", "KILIF", "Redmi Note 13 Pro 5G", "Şeffaf", "Redmi Note 13 Pro 5G"),
            # Apple Watch 41mm vs 45mm (Watch mm Mismatch)
            ("mock-watch41", "8685032039031", "Kordon Apple Watch 41mm / Kırmızı", "KORDON", "Apple Watch 41mm", "Kırmızı", "AW 41mm"),
            ("mock-watch45", "8685032039032", "Kordon Apple Watch 45mm / Kırmızı", "KORDON", "Apple Watch 45mm", "Kırmızı", "AW 45mm"),
            # Samsung Galaxy S24 Ultra (Cross-Brand Mismatch)
            ("mock-s24ultra", "8685032039041", "Glacier Samsung Galaxy S24 Ultra / Şeffaf", "KILIF", "Samsung Galaxy S24 Ultra", "Şeffaf", "S24 Ultra"),
            # Dynamic Categories expansion
            # iPhone 16 Pro Max
            ("mock-ip16promax-kilif", "8685032039051", "Blur iPhone 16 Pro Max / Siyah", "KILIF", "iPhone 16 Pro Max", "Siyah", "İP 16 Pro Max"),
            ("mock-ip16promax-cam", "8685032039052", "Magic Privacy iPhone 16 Pro Max / Şeffaf", "CAM", "iPhone 16 Pro Max", "Şeffaf", "İP 16 Pro Max"),
            ("mock-ip16promax-lens", "8685032039053", "CL-07 Kamera Lens iPhone 16 Pro Max / Gümüş", "KAMERA LENS", "iPhone 16 Pro Max", "Gümüş", "İP 16 Pro Max"),
            # Apple Watch Ultra 49mm
            ("mock-watchultra-kordon", "8685032039061", "Kordon Apple Watch Ultra 49mm / Turuncu", "KORDON", "Apple Watch Ultra 49mm", "Turuncu", "AW 49mm"),
            ("mock-watchultra-gard", "8685032039062", "Gard-02 Apple Watch Ultra 49mm / Şeffaf", "GARD", "Apple Watch Ultra 49mm", "Şeffaf", "AW 49mm"),
            # Samsung Galaxy S24 Ultra (CAM)
            ("mock-s24ultra-cam", "8685032039042", "Magic Privacy Samsung Galaxy S24 Ultra / Şeffaf", "CAM", "Samsung Galaxy S24 Ultra", "Şeffaf", "S24 Ultra"),
            # Redmi Note 13 Pro 5G (CAM)
            ("mock-redmi13pro5g-cam", "8685032039023", "Maxi Ekran Koruyucu Redmi Note 13 Pro 5G", "CAM", "Redmi Note 13 Pro 5G", "Siyah", "Redmi Note 13 Pro 5G"),
            # Samsung Galaxy S23 Ultra
            ("mock-s23ultra-kilif", "8685032039071", "Cure Samsung Galaxy S23 Ultra / Lacivert", "KILIF", "Samsung Galaxy S23 Ultra", "Lacivert", "S23 Ultra"),
            ("mock-s23ultra-cam", "8685032039072", "Maxi Ekran Koruyucu Samsung Galaxy S23 Ultra", "CAM", "Samsung Galaxy S23 Ultra", "Şeffaf", "S23 Ultra"),
            # Huawei Watch Fit 3 (KORDON, GARD)
            ("mock-fit3-kordon", "8685032039081", "Kordon Huawei Watch Fit 3 / Lacivert", "KORDON", "Huawei Watch Fit 3", "Lacivert", "HW Fit 3"),
            ("mock-fit3-gard", "8685032039082", "Gard-02 Huawei Watch Fit 3 / Şeffaf", "GARD", "Huawei Watch Fit 3", "Şeffaf", "HW Fit 3"),
            # Honor 90 Lite
            ("mock-honor90lite", "8685032039091", "Glacier Honor 90 Lite / Siyah", "KILIF", "Honor 90 Lite", "Siyah", "Honor 90 Lite"),
        ]
        
        for p_id, bc, name, cat, model, color, comp in mock_products:
            # Insert into products
            if mode == 'sqlite':
                cur.execute("""
                    INSERT OR IGNORE INTO products (id, barcode, name, category, color, product_model, label_compatible_model, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1);
                """, (p_id, bc, name, cat, color, model, comp))
                
                cur.execute("""
                    INSERT OR IGNORE INTO product_trendyol (id, product_id, barcode, title, brand)
                    VALUES (?, ?, ?, ?, 'Fibaks');
                """, (f"ty-{p_id}", p_id, bc, name))
                
                cur.execute("""
                    INSERT OR IGNORE INTO product_hepsiburada (id, product_id, barcode, product_name, brand)
                    VALUES (?, ?, ?, ?, 'Fibaks');
                """, (f"hb-{p_id}", p_id, bc, name))
            else:
                cur.execute("""
                    INSERT INTO products (id, barcode, name, category, color, product_model, label_compatible_model, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 1) ON CONFLICT (id) DO NOTHING;
                """, (p_id, bc, name, cat, color, model, comp))
                
                cur.execute("""
                    INSERT INTO product_trendyol (id, product_id, barcode, title, brand)
                    VALUES (%s, %s, %s, %s, 'Fibaks') ON CONFLICT (id) DO NOTHING;
                """, (f"ty-{p_id}", p_id, bc, name))
                
                cur.execute("""
                    INSERT INTO product_hepsiburada (id, product_id, barcode, product_name, brand)
                    VALUES (%s, %s, %s, %s, 'Fibaks') ON CONFLICT (id) DO NOTHING;
                """, (f"hb-{p_id}", p_id, bc, name))
                
        # 5 ile 10 arasında random sipariş adedi
        generated_count = random.randint(5, 10)
        
        first_names = ["Hakan", "Murat", "Serkan", "Volkan", "Burak", "Cem", "Deniz", "Selim", "Seda", "Gözde", "Merve", "Aslı", "Kadir", "Tufan", "Okan", "Gizem"]
        last_names = ["Yılmaz", "Kaya", "Korkmaz", "Şen", "Demir", "Çetin", "Öztürk", "Bulut", "Aksoy", "Toprak", "Yıldız", "Arslan", "Polat"]
        cities = ["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Adana", "Muğla", "Trabzon", "Samsun", "Eskişehir", "Gaziantep"]
        marketplaces = ["Trendyol", "Hepsiburada"]
        
        # Risk Senaryoları Dağılım Oranları:
        # 0: Aynı Kategori - Aynı Model (Yüksek Risk) -> %15
        # 1: Aynı Kategori - Farklı Model (Orta Risk) -> %15
        # 2: Riskli Kural Eşleşmesi (Huawei/Honor) -> %15
        # 3: Uyumlu/Temiz Sipariş (Uyumlu) -> %15
        # 4: Pro vs Pro Max Boyut Uyuşmazlığı (Kritik Risk - 90 Puan) -> %10
        # 5: 4G vs 5G Ağ Uyuşmazlığı (Kritik Risk - 85 Puan) -> %10
        # 6: Akıllı Saat mm Boyut Uyuşmazlığı (Kritik Risk - 75 Puan) -> %10
        # 7: Yüksek Adetli B2C Sipariş Kontrolü (Orta Risk - 45 Puan) -> %5
        # 8: Çapraz Marka Siparişi (Düşük Risk - 35 Puan) -> %5
        
        for _ in range(generated_count):
            order_id = random.randint(10000000, 99999999)
            shipment_pkg_id = random.randint(1000000000, 9999999999)
            order_num = str(random.randint(1000000000, 9999999999))
            
            order_date = datetime.now().isoformat()
            
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            city = random.choice(cities)
            marketplace = random.choice(marketplaces)
            
            # Senaryo Seçimi
            scenario = random.choices(
                [0, 1, 2, 3, 4, 5, 6, 7, 8], 
                weights=[15, 15, 15, 15, 10, 10, 10, 5, 5]
            )[0]
            
            lines = []
            if scenario == 0:
                # 2 Items of SAME category and SAME model (Fully randomized category/model)
                sub_scenarios = [
                    # Category KILIF
                    [
                        {"sku": "mock-ip16promax-kilif", "price": 180.0, "barcode": "8685032039051", "quantity": 1, "productName": "Blur iPhone 16 Pro Max / Siyah"},
                        {"sku": "mock-ip16promax-kilif", "price": 180.0, "barcode": "8685032039051", "quantity": 1, "productName": "Blur iPhone 16 Pro Max / Siyah"}
                    ],
                    # Category CAM
                    [
                        {"sku": "mock-s24ultra-cam", "price": 150.0, "barcode": "8685032039042", "quantity": 1, "productName": "Magic Privacy Samsung Galaxy S24 Ultra / Şeffaf"},
                        {"sku": "mock-s24ultra-cam", "price": 150.0, "barcode": "8685032039042", "quantity": 1, "productName": "Magic Privacy Samsung Galaxy S24 Ultra / Şeffaf"}
                    ],
                    # Category KORDON
                    [
                        {"sku": "mock-fit3-kordon", "price": 130.0, "barcode": "8685032039081", "quantity": 1, "productName": "Kordon Huawei Watch Fit 3 / Lacivert"},
                        {"sku": "mock-fit3-kordon", "price": 130.0, "barcode": "8685032039081", "quantity": 1, "productName": "Kordon Huawei Watch Fit 3 / Lacivert"}
                    ],
                    # Category KILIF for Samsung Galaxy S23 Ultra
                    [
                        {"sku": "mock-s23ultra-kilif", "price": 140.0, "barcode": "8685032039071", "quantity": 1, "productName": "Cure Samsung Galaxy S23 Ultra / Lacivert"},
                        {"sku": "mock-s23ultra-kilif", "price": 140.0, "barcode": "8685032039071", "quantity": 1, "productName": "Cure Samsung Galaxy S23 Ultra / Lacivert"}
                    ]
                ]
                lines = random.choice(sub_scenarios)
            elif scenario == 1:
                # 2 Items of SAME category but DIFFERENT models
                sub_scenarios = [
                    [
                        {"sku": "mock-ip16promax-kilif", "price": 180.0, "barcode": "8685032039051", "quantity": 1, "productName": "Blur iPhone 16 Pro Max / Siyah"},
                        {"sku": "mock-ip15promax", "price": 170.0, "barcode": "8685032039018", "quantity": 1, "productName": "Blur iPhone 15 Pro Max / Lacivert"}
                    ],
                    [
                        {"sku": "mock-watch41", "price": 120.0, "barcode": "8685032039031", "quantity": 1, "productName": "Kordon Apple Watch 41mm / Kırmızı"},
                        {"sku": "mock-watch45", "price": 120.0, "barcode": "8685032039032", "quantity": 1, "productName": "Kordon Apple Watch 45mm / Kırmızı"}
                    ],
                    [
                        {"sku": "mock-s24ultra-cam", "price": 150.0, "barcode": "8685032039042", "quantity": 1, "productName": "Magic Privacy Samsung Galaxy S24 Ultra / Şeffaf"},
                        {"sku": "mock-s23ultra-cam", "price": 130.0, "barcode": "8685032039072", "quantity": 1, "productName": "Maxi Ekran Koruyucu Samsung Galaxy S23 Ultra"}
                    ]
                ]
                lines = random.choice(sub_scenarios)
            elif scenario == 2:
                # Triggers Huawei Watch Fit or Honor rule -> Orta Risk
                sub_scenarios = [
                    [
                        {"sku": "0F40409430011", "price": 158.82, "barcode": "8685032038089", "quantity": 1, "productName": "Gard-02 HW Fit 3 / Şeffaf"}
                    ],
                    [
                        {"sku": "mock-honor90lite", "price": 120.0, "barcode": "8685032039091", "quantity": 1, "productName": "Glacier Honor 90 Lite / Siyah"}
                    ]
                ]
                lines = random.choice(sub_scenarios)
            elif scenario == 3:
                # Clean order (Compatible products for the same device) -> Güvenli
                sub_scenarios = [
                    [
                        {"sku": "mock-ip16promax-kilif", "price": 180.0, "barcode": "8685032039051", "quantity": 1, "productName": "Blur iPhone 16 Pro Max / Siyah"},
                        {"sku": "mock-ip16promax-cam", "price": 160.0, "barcode": "8685032039052", "quantity": 1, "productName": "Magic Privacy iPhone 16 Pro Max / Şeffaf"},
                        {"sku": "mock-ip16promax-lens", "price": 110.0, "barcode": "8685032039053", "quantity": 1, "productName": "CL-07 Kamera Lens iPhone 16 Pro Max / Gümüş"}
                    ],
                    [
                        {"sku": "mock-watchultra-kordon", "price": 150.0, "barcode": "8685032039061", "quantity": 1, "productName": "Kordon Apple Watch Ultra 49mm / Turuncu"},
                        {"sku": "mock-watchultra-gard", "price": 95.0, "barcode": "8685032039062", "quantity": 1, "productName": "Gard-02 Apple Watch Ultra 49mm / Şeffaf"}
                    ],
                    [
                        {"sku": "mock-s23ultra-kilif", "price": 140.0, "barcode": "8685032039071", "quantity": 1, "productName": "Cure Samsung Galaxy S23 Ultra / Lacivert"},
                        {"sku": "mock-s23ultra-cam", "price": 130.0, "barcode": "8685032039072", "quantity": 1, "productName": "Maxi Ekran Koruyucu Samsung Galaxy S23 Ultra"}
                    ]
                ]
                lines = random.choice(sub_scenarios)
            elif scenario == 4:
                # Pro vs Pro Max variant mismatch -> Kritik (%90)
                sub_scenarios = [
                    [
                        {"sku": "Fibaks-IP15PRO-Blue", "price": 220.0, "barcode": "8685032039017", "quantity": 1, "productName": "Blur iPhone 15 Pro / Lacivert"},
                        {"sku": "Fibaks-IP15PROMAX-Blue", "price": 240.0, "barcode": "8685032039018", "quantity": 1, "productName": "Blur iPhone 15 Pro Max / Lacivert"}
                    ],
                    [
                        {"sku": "mock-ip16promax-cam", "price": 160.0, "barcode": "8685032039052", "quantity": 1, "productName": "Magic Privacy iPhone 16 Pro Max / Şeffaf"},
                        {"sku": "fb79e076-335c-4b8a-9e5a-e0f0d84ef806", "price": 199.0, "barcode": "8685032006378", "quantity": 1, "productName": "Magic Privacy iPhone 16 Pro"}
                    ]
                ]
                lines = random.choice(sub_scenarios)
            elif scenario == 5:
                # 4G vs 5G mismatch -> Kritik (%85)
                sub_scenarios = [
                    [
                        {"sku": "Fibaks-REDMI13PRO4G-Clear", "price": 150.0, "barcode": "8685032039021", "quantity": 1, "productName": "Glacier Redmi Note 13 Pro 4G / Şeffaf"},
                        {"sku": "Fibaks-REDMI13PRO5G-Clear", "price": 150.0, "barcode": "8685032039022", "quantity": 1, "productName": "Glacier Redmi Note 13 Pro 5G / Şeffaf"}
                    ],
                    [
                        {"sku": "Fibaks-REDMI13PRO4G-Clear", "price": 150.0, "barcode": "8685032039021", "quantity": 1, "productName": "Glacier Redmi Note 13 Pro 4G / Şeffaf"},
                        {"sku": "mock-redmi13pro5g-cam", "price": 140.0, "barcode": "8685032039023", "quantity": 1, "productName": "Maxi Ekran Koruyucu Redmi Note 13 Pro 5G"}
                    ]
                ]
                lines = random.choice(sub_scenarios)
            elif scenario == 6:
                # Watch mm mismatch -> Kritik (%75)
                sub_scenarios = [
                    [
                        {"sku": "Fiber-Watch-41-Red", "price": 120.0, "barcode": "8685032039031", "quantity": 1, "productName": "Kordon Apple Watch 41mm / Kırmızı"},
                        {"sku": "Fiber-Watch-45-Red", "price": 120.0, "barcode": "8685032039032", "quantity": 1, "productName": "Kordon Apple Watch 45mm / Kırmızı"}
                    ],
                    [
                        {"sku": "mock-watchultra-kordon", "price": 150.0, "barcode": "8685032039061", "quantity": 1, "productName": "Kordon Apple Watch Ultra 49mm / Turuncu"},
                        {"sku": "Fiber-Watch-41-Red", "price": 120.0, "barcode": "8685032039031", "quantity": 1, "productName": "Kordon Apple Watch 41mm / Kırmızı"}
                    ]
                ]
                lines = random.choice(sub_scenarios)
            elif scenario == 7:
                # High quantity B2C -> Orta (%45)
                sub_scenarios = [
                    [{"sku": "mock-ip16promax-kilif", "price": 180.0, "barcode": "8685032039051", "quantity": 3, "productName": "Blur iPhone 16 Pro Max / Siyah"}],
                    [{"sku": "mock-s24ultra-cam", "price": 150.0, "barcode": "8685032039042", "quantity": 4, "productName": "Magic Privacy Samsung Galaxy S24 Ultra / Şeffaf"}]
                ]
                lines = random.choice(sub_scenarios)
            else:
                # Cross-Brand Mismatch (Apple and Samsung / Xiaomi) -> Düşük (%35)
                sub_scenarios = [
                    [
                        {"sku": "mock-ip16promax-kilif", "price": 180.0, "barcode": "8685032039051", "quantity": 1, "productName": "Blur iPhone 16 Pro Max / Siyah"},
                        {"sku": "mock-s24ultra-cam", "price": 150.0, "barcode": "8685032039042", "quantity": 1, "productName": "Magic Privacy Samsung Galaxy S24 Ultra / Şeffaf"}
                    ],
                    [
                        {"sku": "mock-s23ultra-kilif", "price": 140.0, "barcode": "8685032039071", "quantity": 1, "productName": "Cure Samsung Galaxy S23 Ultra / Lacivert"},
                        {"sku": "Fibaks-REDMI13PRO5G-Clear", "price": 150.0, "barcode": "8685032039022", "quantity": 1, "productName": "Glacier Redmi Note 13 Pro 5G / Şeffaf"}
                    ]
                ]
                lines = random.choice(sub_scenarios)
                
            total_price = sum(item["price"] * item.get("quantity", 1) for item in lines)
            raw_data = {"lines": lines}
            
            cur.execute(f"""
                INSERT INTO crm_orders (id, order_number, order_date, status, total_price, customer_first_name, customer_last_name, customer_email, shipment_address, raw_data, marketplace, created_at, updated_at)
                VALUES ({placeholder}, {placeholder}, {placeholder}, 'Picking', {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, datetime('now'), datetime('now'));
            """, (
                order_id, 
                order_num, 
                order_date, 
                total_price, 
                first_name, 
                last_name, 
                f"{first_name.lower()}@fibaksverify.com", 
                json.dumps({"city": city, "fullName": f"{first_name} {last_name}", "fullAddress": f"{city}/Türkiye"}), 
                json.dumps(raw_data), 
                marketplace
            ))
            
        conn.commit()
        return {"success": True, "generated_count": generated_count}
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

# --- PRODUCT RELATIONSHIPS CRUD API (NEW & SEARCH/FILTER/SORT ENABLED) ---

@app.get("/api/products")
async def get_products(brand: Optional[str] = None, model: Optional[str] = None, search: Optional[str] = None, sort_by: Optional[str] = None):
    """
    Tüm ürünleri ve onların uyumluluk haritasını çeker. Arama, Marka/Model filtreleme ve Sıralamayı (Sort) destekler.
    """
    conn, mode = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Fetch mappings and listings in bulk to prevent N+1 network queries latency
        cur.execute("SELECT product_id, device_model FROM product_device_mappings;")
        mappings_raw = cur.fetchall()
        mappings_dict = {}
        for r in mappings_raw:
            pid = r["product_id"]
            if pid not in mappings_dict:
                mappings_dict[pid] = []
            mappings_dict[pid].append(r["device_model"])
            
        cur.execute("SELECT product_id, barcode, title FROM product_trendyol;")
        trendyol_raw = cur.fetchall()
        trendyol_dict = {}
        for r in trendyol_raw:
            pid = r["product_id"]
            if pid not in trendyol_dict:
                trendyol_dict[pid] = []
            trendyol_dict[pid].append({"marketplace": "Trendyol", "barcode": r["barcode"], "title": r["title"]})
            
        cur.execute("SELECT product_id, barcode, product_name AS title FROM product_hepsiburada;")
        hepsiburada_raw = cur.fetchall()
        hepsiburada_dict = {}
        for r in hepsiburada_raw:
            pid = r["product_id"]
            if pid not in hepsiburada_dict:
                hepsiburada_dict[pid] = []
            hepsiburada_dict[pid].append({"marketplace": "Hepsiburada", "barcode": r["barcode"], "title": r["title"]})

        # Ürünleri ve onlara bağlı barkodları alalım
        query = """
            SELECT p.id, p.barcode, p.name, p.category, p.product_model, p.stock_quantity, p.color
            FROM products p
            WHERE 1=1
        """
        params = []
        
        # Filtre 1: Arama kelimesi
        if search:
            if mode == 'sqlite':
                query += " AND (p.name LIKE ? OR p.barcode LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])
            else:
                query += " AND (p.name ILIKE %s OR p.barcode ILIKE %s)"
                params.extend([f"%{search}%", f"%{search}%"])
                
        # Filtre 2: Marka Filtresi (İsme göre)
        if brand and brand != 'ALL':
            if mode == 'sqlite':
                query += " AND p.name LIKE ?"
                params.append(f"%{brand}%")
            else:
                query += " AND p.name ILIKE %s"
                params.append(f"%{brand}%")
                
        # Filtre 3: Model Filtresi
        if model and model != 'ALL':
            if mode == 'sqlite':
                query += " AND p.product_model LIKE ?"
                params.append(f"%{model}%")
            else:
                query += " AND p.product_model ILIKE %s"
                params.append(f"%{model}%")
                
        # Sıralama (Sort)
        if sort_by == 'name':
            query += " ORDER BY p.name ASC"
        elif sort_by == 'category':
            query += " ORDER BY p.category ASC"
        elif sort_by == 'stock':
            query += " ORDER BY p.stock_quantity DESC"
        else:
            query += " ORDER BY p.name ASC"
            
        cur.execute(query, params)
        db_products = cur.fetchall()
        
        products_list = []
        for p in db_products:
            pid = p["id"]
            mapped_devices = mappings_dict.get(pid, [])
            listings = trendyol_dict.get(pid, []) + hepsiburada_dict.get(pid, [])
            
            products_list.append({
                "id": pid,
                "barcode": p["barcode"],
                "name": p["name"],
                "category": p["category"],
                "product_model": p["product_model"],
                "stock_quantity": p["stock_quantity"],
                "color": p["color"],
                "compatible_devices": mapped_devices,
                "listings": listings
            })
            
        return products_list
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.get("/api/products/resolve-single")
async def resolve_single_product(query: str):
    conn, mode = get_db_connection()
    if mode == 'sqlite':
        conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    placeholder = '?' if mode == 'sqlite' else '%s'
    
    try:
        cur.execute(f"""
            SELECT id, barcode, name, category, product_model, label_compatible_model 
            FROM products 
            WHERE id = {placeholder} OR barcode = {placeholder}
            LIMIT 1;
        """, (query.strip(), query.strip()))
        row = cur.fetchone()
        if row:
            if hasattr(row, "keys"):
                return {
                    "success": True,
                    "id": row["id"],
                    "barcode": row["barcode"],
                    "name": row["name"],
                    "category": row["category"],
                    "product_model": row["product_model"],
                    "label_compatible_model": row["label_compatible_model"]
                }
            else:
                return {
                    "success": True,
                    "id": row[0],
                    "barcode": row[1],
                    "name": row[2],
                    "category": row[3],
                    "product_model": row[4],
                    "label_compatible_model": row[5]
                }
        return {"success": False, "error": "Ürün bulunamadı"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.post("/api/products/mappings")
async def add_device_mapping(mapping: MappingCreate):
    """
    Bir ürüne yeni bir uyumlu cihaz modeli ekler (Harita Düzenleme).
    """
    conn, mode = get_db_connection()
    cur = conn.cursor()
    placeholder = '?' if mode == 'sqlite' else '%s'
    
    try:
        cur.execute(f"""
            INSERT OR IGNORE INTO product_device_mappings (product_id, device_model, created_at)
            VALUES ({placeholder}, {placeholder}, datetime('now'));
        """, (mapping.product_id, mapping.device_model))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.delete("/api/products/mappings")
async def delete_device_mapping(product_id: str, device_model: str):
    """
    Bir ürünün cihaz uyumluluğunu siler (Harita Düzenleme).
    """
    conn, mode = get_db_connection()
    cur = conn.cursor()
    placeholder = '?' if mode == 'sqlite' else '%s'
    
    try:
        cur.execute(f"""
            DELETE FROM product_device_mappings 
            WHERE product_id = {placeholder} AND device_model = {placeholder};
        """, (product_id, device_model))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

# --- PRE-MATCH BATCH PROCESSING JOB (ÖNDEN HAZIRLIK / PROACTIVE) ---

@app.post("/api/products/pre-match")
async def batch_pre_match_products():
    """
    ÖNDEN HAZIRLIK: ERP'deki tüm ürünleri tarar, isimlerinden marka/model analizini 
    akıllı Regular Expression'lar ile yapar ve product_device_mappings tablosuna önden yazar!
    """
    conn, mode = get_db_connection()
    cur = conn.cursor()
    
    # Tanımlı Regex Arama Kalıpları
    brands = {
        "Apple": [
            r"iPhone\s\d+\sPro\sMax", 
            r"iPhone\s\d+\sPro", 
            r"iPhone\s\d+\sPlus", 
            r"iPhone\s\d+",
            r"iPhone\s[XSxsM]+",
            r"iPhone\s7-8\sPlus",
            r"iPhone\s7-8"
        ],
        "Huawei": [
            r"Huawei\sWatch\sFit\s\d+",
            r"HW\sWatch\sFit\s\d+",
            r"Huawei\sWatch\sFit",
            r"HW\sWatch\sFit"
        ],
        "Honor": [
            r"Honor\s\d+\sLite",
            r"Honor\s\d+[Xxi]?",
            r"Honor\s\d+"
        ]
    }
    
    matched_count = 0
    
    try:
        # Cihaz uyumluluğu olmayan tüm ürünleri bulalım
        cur.execute("""
            SELECT id, name, product_model 
            FROM products 
            WHERE id NOT IN (SELECT DISTINCT product_id FROM product_device_mappings);
        """)
        unmatched_products = cur.fetchall()
        
        for p in unmatched_products:
            pname = p["name"]
            p_id = p["id"]
            
            # Metni regex'ler ile analiz et
            matched_model = None
            for brand, patterns in brands.items():
                for pattern in patterns:
                    match = re.search(pattern, pname, re.IGNORECASE)
                    if match:
                        matched_model = match.group(0)
                        # Standartlaştırma
                        if "7-8 Plus" in matched_model:
                            matched_model = "iPhone 7 Plus"
                        break
                if matched_model:
                    break
                    
            # Eşleşme bulunduysa veri tabanına önden yaz!
            if matched_model:
                placeholder = '?' if mode == 'sqlite' else '%s'
                # Birincil modeli yaz
                cur.execute(f"""
                    INSERT OR IGNORE INTO product_device_mappings (product_id, device_model, created_at)
                    VALUES ({placeholder}, {placeholder}, datetime('now'));
                """, (p_id, matched_model))
                
                # Eğer "iPhone 7 Plus" ise yanına "iPhone 8 Plus" da ekle (Çoklu uyumluluk)
                if matched_model == "iPhone 7 Plus":
                    cur.execute(f"""
                        INSERT OR IGNORE INTO product_device_mappings (product_id, device_model, created_at)
                        VALUES ({placeholder}, 'iPhone 8 Plus', datetime('now'));
                    """, (p_id,))
                
                matched_count += 1
                
        conn.commit()
        return {"success": True, "matched_count": matched_count}
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

# --- RULES CRUD ENDPOINTS ---

@app.get("/api/rules")
async def get_rules():
    conn, mode = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM monitored_rules ORDER BY created_at DESC;")
        return cur.fetchall()
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.post("/api/products/bulk-import")
async def bulk_import_products(request: Request):
    """
    Excel'den eşleştirilmiş ürün JSON listesini alır,
    SQLite / PostgreSQL veritabanında barkoda göre UPSERT yapar.
    """
    import uuid
    from datetime import datetime
    products_list = await request.json()
    conn, mode = get_db_connection()
    cur = conn.cursor()
    
    inserted = 0
    updated = 0
    
    placeholder = '?' if mode == 'sqlite' else '%s'
    
    try:
        for p in products_list:
            barcode = p.get("barcode")
            if barcode is not None:
                barcode = str(barcode).strip()
            name = p.get("name")
            if name is not None:
                name = str(name).strip()
            
            if not barcode or not name:
                continue # Skip invalid rows
            
            # Check if product exists by barcode
            cur.execute(f"SELECT id FROM products WHERE barcode = {placeholder};", (barcode,))
            existing = cur.fetchone()
            
            # Extract common properties
            category = p.get("category")
            model_code = p.get("model_code")
            color = p.get("color")
            warehouse_id = p.get("warehouse_id")
            shelf_column = p.get("shelf_column")
            shelf_row = p.get("shelf_row")
            
            # stock quantity default to 0
            stock_q = p.get("stock_quantity")
            if stock_q is not None:
                try: stock_q = int(stock_q)
                except: stock_q = 0
            else:
                stock_q = 0
                
            box_no = p.get("box_no")
            product_model = p.get("product_model")
            label_name = p.get("label_name")
            label_compatible_model = p.get("label_compatible_model")
            supplier_name = p.get("supplier_name")
            supplier_color = p.get("supplier_color")
            
            purchase_price = p.get("purchase_price_rmb")
            cost = p.get("cost")
            cost_usd = p.get("cost_usd")
            
            supplier_note = p.get("supplier_note")
            
            is_active = p.get("is_active", True)
            is_active_val = 1 if is_active else 0
            
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if existing:
                # Update existing product
                update_fields = [
                    "name = ?", "category = ?", "model_code = ?", "color = ?",
                    "warehouse_id = ?", "shelf_column = ?", "shelf_row = ?", "stock_quantity = ?",
                    "box_no = ?", "product_model = ?", "label_name = ?", "label_compatible_model = ?",
                    "supplier_name = ?", "supplier_color = ?", "purchase_price_rmb = ?", "cost = ?",
                    "cost_usd = ?", "supplier_note = ?", "is_active = ?", "updated_at = ?"
                ]
                
                # Replace placeholders for pg compatibility if needed
                if mode != 'sqlite':
                    update_fields = [f.replace('?', '%s') for f in update_fields]
                    
                query = f"UPDATE products SET {', '.join(update_fields)} WHERE barcode = {placeholder};"
                
                params = (
                    name, category, model_code, color,
                    warehouse_id, shelf_column, shelf_row, stock_q,
                    box_no, product_model, label_name, label_compatible_model,
                    supplier_name, supplier_color, purchase_price, cost,
                    cost_usd, supplier_note, is_active_val, now_str, barcode
                )
                
                cur.execute(query, params)
                updated += 1
            else:
                # Create new product
                p_id = p.get("id") or f"prod-{str(uuid.uuid4())[:8]}"
                
                insert_cols = [
                    "id", "barcode", "name", "category", "model_code", "color",
                    "warehouse_id", "shelf_column", "shelf_row", "stock_quantity",
                    "box_no", "product_model", "label_name", "label_compatible_model",
                    "supplier_name", "supplier_color", "purchase_price_rmb", "cost",
                    "cost_usd", "supplier_note", "is_active", "created_at", "updated_at"
                ]
                
                placeholders = [placeholder] * len(insert_cols)
                query = f"INSERT INTO products ({', '.join(insert_cols)}) VALUES ({', '.join(placeholders)});"
                
                params = (
                    p_id, barcode, name, category, model_code, color,
                    warehouse_id, shelf_column, shelf_row, stock_q,
                    box_no, product_model, label_name, label_compatible_model,
                    supplier_name, supplier_color, purchase_price, cost,
                    cost_usd, supplier_note, is_active_val, now_str, now_str
                )
                
                cur.execute(query, params)
                inserted += 1
                
        conn.commit()
        return {
            "success": True, 
            "inserted_count": inserted, 
            "updated_count": updated
        }
    except Exception as e:
        if conn: conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.post("/api/rules")
async def create_rule(rule: RuleCreate):
    conn, mode = get_db_connection()
    cur = conn.cursor()
    placeholder = '?' if mode == 'sqlite' else '%s'
    new_id = str(uuid.uuid4())
    
    try:
        cur.execute(f"""
            INSERT INTO monitored_rules (id, brand, model_pattern, warning_message, barcodes, is_active, created_at)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, 1, datetime('now'));
        """, (new_id, rule.brand, rule.model_pattern, rule.warning_message, rule.barcodes))
        conn.commit()
        return {"success": True, "id": new_id}
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: str):
    conn, mode = get_db_connection()
    cur = conn.cursor()
    placeholder = '?' if mode == 'sqlite' else '%s'
    
    try:
        cur.execute(f"DELETE FROM monitored_rules WHERE id = {placeholder};", (rule_id,))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

# --- DEVICE GENERATIONS CRUD ENDPOINTS ---

class DeviceGenerationCreate(BaseModel):
    device_model: str
    generation_group: str
    brand: str
    status: Optional[str] = "VERIFIED"

class DeviceGenerationUpdate(BaseModel):
    generation_group: str
    status: Optional[str] = "VERIFIED"

@app.get("/api/device-generations")
async def get_device_generations():
    conn, mode = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM device_generations ORDER BY brand, device_model;")
        return cur.fetchall()
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.post("/api/device-generations")
async def create_device_generation_api(dg: DeviceGenerationCreate):
    conn, mode = get_db_connection()
    cur = conn.cursor()
    placeholder = '?' if mode == 'sqlite' else '%s'
    try:
        cur.execute(f"""
            INSERT OR REPLACE INTO device_generations (device_model, generation_group, brand, status)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder});
        """, (dg.device_model.strip(), dg.generation_group.strip(), dg.brand.strip().lower(), dg.status or 'VERIFIED'))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.put("/api/device-generations/{device_model:path}")
async def update_device_generation_api(device_model: str, dg: DeviceGenerationUpdate):
    conn, mode = get_db_connection()
    cur = conn.cursor()
    placeholder = '?' if mode == 'sqlite' else '%s'
    try:
        cur.execute(f"""
            UPDATE device_generations
            SET generation_group = {placeholder}, status = {placeholder}
            WHERE LOWER(device_model) = LOWER({placeholder});
        """, (dg.generation_group.strip(), dg.status or 'VERIFIED', device_model.strip()))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.delete("/api/device-generations/{device_model:path}")
async def delete_device_generation_api(device_model: str):
    conn, mode = get_db_connection()
    cur = conn.cursor()
    placeholder = '?' if mode == 'sqlite' else '%s'
    try:
        cur.execute(f"DELETE FROM device_generations WHERE LOWER(device_model) = LOWER({placeholder});", (device_model.strip(),))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()

# --- HIERARCHICAL GRAPH ENDPOINT ---

@app.get("/api/graph")
async def get_graph():
    try:
        orders = fetch_resolved_orders()
        
        nodes = []
        edges = []
        added_nodes = set()
        
        nodes.append({
            "id": "fibaks_erp",
            "label": "Fibaks ERP",
            "group": "erp",
            "shape": "dot",
            "size": 35,
            "title": "Merkezi Fibaks Veritabanı"
        })
        
        for o in orders:
            order_id = f"order_{o['id']}"
            customer_name = o["customer_name"]
            order_num = o["order_number"]
            marketplace = o["marketplace"]
            
            color_map = {
                "red": "#f87171",
                "orange": "#fb923c",
                "green": "#4ade80"
            }
            order_color = color_map.get(o["status_color"], "#4ade80")
            
            nodes.append({
                "id": order_id,
                "label": f"Sipariş: {order_num}\n({customer_name})",
                "group": "order",
                "shape": "dot",
                "size": 25,
                "color": {
                    "background": order_color,
                    "border": "#1e293b",
                    "highlight": { "background": order_color, "border": "#ffffff" }
                },
                "title": f"Müşteri: {customer_name}"
            })
            
            edges.append({
                "from": order_id,
                "to": "fibaks_erp",
                "color": {"color": "#64748b", "opacity": 0.4},
                "arrows": "to"
            })
            
            for line in o["lines"]:
                barcode = line["line_barcode"]
                barcode_id = f"barcode_{barcode}"
                erp_product_id = line["erp_product_id"]
                
                if barcode_id not in added_nodes:
                    added_nodes.add(barcode_id)
                    nodes.append({
                        "id": barcode_id,
                        "label": f"Barkod: {barcode}",
                        "group": "listing",
                        "shape": "box",
                        "color": "#38bdf8",
                        "title": f"Başlık: {line['marketplace_title']}"
                    })
                    
                edges.append({
                    "from": order_id,
                    "to": barcode_id,
                    "color": {"color": "#38bdf8", "opacity": 0.7}
                })
                
                if erp_product_id:
                    product_node_id = f"product_{erp_product_id}"
                    
                    if product_node_id not in added_nodes:
                        added_nodes.add(product_node_id)
                        nodes.append({
                            "id": product_node_id,
                            "label": f"Ürün:\n{line['erp_product_name']}",
                            "group": "product",
                            "shape": "dot",
                            "size": 18,
                            "color": "#a855f7",
                            "title": f"ERP ID: {line['erp_product_id']}"
                        })
                        
                    edges.append({
                        "from": barcode_id,
                        "to": product_node_id,
                        "color": {"color": "#a855f7", "opacity": 0.8},
                        "style": "dash"
                    })
                    
                    device_model = line["erp_product_model"]
                    if device_model:
                        device_node_id = f"device_{device_model}"
                        if device_node_id not in added_nodes:
                            added_nodes.add(device_node_id)
                            nodes.append({
                                "id": device_node_id,
                                "label": f"Model:\n{device_model}",
                                "group": "device",
                                "shape": "triangle",
                                "color": "#10b981",
                                "title": f"Cihaz: {device_model}"
                            })
                            
                        edges.append({
                            "from": product_node_id,
                            "to": device_node_id,
                            "color": {"color": "#10b981", "opacity": 0.8}
                        })
                        
                        # Marka Hiyerarşisi
                        brand_name = "Diğer"
                        if "iPhone" in device_model or "Apple" in device_model:
                            brand_name = "Apple"
                        elif "Huawei" in device_model or "HW" in device_model:
                            brand_name = "Huawei"
                        elif "Honor" in device_model:
                            brand_name = "Honor"
                            
                        brand_node_id = f"brand_{brand_name}"
                        if brand_node_id not in added_nodes:
                            added_nodes.add(brand_node_id)
                            brand_color = "#f43f5e" if brand_name == "Honor" else "#3b82f6"
                            if brand_name == "Apple": brand_color = "#ffffff"
                            
                            nodes.append({
                                "id": brand_node_id,
                                "label": f"Marka:\n{brand_name}",
                                "group": "brand",
                                "shape": "diamond",
                                "color": brand_color,
                                "size": 22,
                                "title": f"Ana Marka: {brand_name}"
                            })
                            
                            edges.append({
                                "from": brand_node_id,
                                "to": "fibaks_erp",
                                "color": {"color": "#64748b", "opacity": 0.6}
                            })
                            
                        edges.append({
                            "from": device_node_id,
                            "to": brand_node_id,
                            "color": {"color": "#3b82f6", "opacity": 0.7}
                        })
                        
        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        return {"error": str(e)}

# --- SIPARIS SIMULASYON ENDPOINTS ---

@app.get("/simulate", response_class=HTMLResponse)
async def simulate_page(request: Request):
    return templates.TemplateResponse("simulate.html", {"request": request})

@app.post("/api/simulate-order")
async def simulate_order_api(data: dict):
    import random
    import uuid
    import urllib.request
    from datetime import datetime
    
    conn, mode = get_db_connection()
    if mode == 'sqlite':
        conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    thinking_log = []
    
    try:
        difficulty = int(data.get("difficulty", 5))
        marketplace = data.get("marketplace", "Trendyol")
        cust_name = data.get("customer_name", "").strip()
        gemini_api_key = data.get("gemini_api_key", "").strip()
        
        # 1. Start thinking log
        thinking_log.append("> [SYSTEM]: Sipariş Simülasyon Motoru başlatıldı.")
        thinking_log.append(f"> [PARAM]: Zorluk Seviyesi: {difficulty}/10, Satış Pazaryeri: {marketplace}")
        
        # Generative list of random Turkish names
        turkish_names = [
            ("Hakan", "Yılmaz"), ("Selin", "Kaya"), ("Emre", "Demir"), 
            ("Gamze", "Çelik"), ("Yiğit", "Şahin"), ("Melis", "Öztürk"),
            ("Can", "Aydın"), ("Büşra", "Arslan"), ("Deniz", "Koç"),
            ("Oğuzhan", "Korkmaz"), ("Merve", "Bulut"), ("Alperen", "Yıldız"),
            ("Zeynep", "Aslan"), ("Burak", "Özdemir"), ("Bahar", "Turan")
        ]
        if not cust_name:
            chosen = random.choice(turkish_names)
            fname, lname = chosen[0], chosen[1]
            thinking_log.append(f"> [AI]: Müşteri ismi boş bırakıldı. Rastgele seçildi: {fname} {lname}")
        else:
            parts = cust_name.split(maxsplit=1)
            fname = parts[0]
            lname = parts[1] if len(parts) > 1 else "Teyitli"
            thinking_log.append(f"> [AI]: Müşteri ismi işlendi: {fname} {lname}")

        products_input = data.get("products", [])
        if not products_input:
            p1 = data.get("product_1", {})
            p2 = data.get("product_2", {})
            products_input = []
            if p1: products_input.append(p1)
            if p2: products_input.append(p2)
            
        if not products_input:
            products_input = [{}, {}] # Default fallback to 2 empty products
            
        product_count = len(products_input)
        for p in products_input:
            if "product_id" not in p: p["product_id"] = ""
            if "category" not in p: p["category"] = ""
            if "model" not in p: p["model"] = ""
            if "title" not in p: p["title"] = ""
            if "compat" not in p: p["compat"] = ""
        thinking_log.append(f"> [PARAM]: Simüle Edilecek Ürün Kalemi Adedi: {product_count}")
        
        use_gemini = False
        gemini_failed = False
        
        if gemini_api_key:
            thinking_log.append("> [MODEL]: Gemini API anahtarı sağlandı. Bulut YZ motoru çağrılıyor...")
            use_gemini = True
            
            # Format inputs dynamically for LLM
            inputs_str = ""
            for idx, p in enumerate(products_input):
                cat = p.get("category", "").strip() or "RANDOM"
                model = p.get("model", "").strip() or "RANDOM"
                title = p.get("title", "").strip() or "RANDOM"
                inputs_str += f"- Product {idx+1} (Category: {cat}, Model: {model}, Title: {title})\n"
            
            prompt = f"""
            You are a QA automation expert specializing in testing e-commerce regex parsing engines.
            Your task is to generate exactly {product_count} products that test the limits of our regex parsing system.
            
            Input Parameters:
            - Marketplace: {marketplace}
            - Difficulty Level (1-10): {difficulty}
            {inputs_str}
            
            Based on the Difficulty Level, mutate titles and models to simulate chaotic marketplace listings:
            - Levels 1-2: Standard Turkish e-commerce names, perfectly clean titles, standard model codes. No mutation.
            - Levels 3-4 (Case variation): Randomly swap uppercase/lowercase characters (e.g., 'iPHoNe 15 prO mAx', 'ApPLe WAtCh').
            - Levels 5-6 (Spacing traps): Add multiple consecutive internal spaces between words (e.g., 'iPhone     15    Pro').
            - Levels 7-8 (Smartwatch MM Trap): If smartwatch accessories (KORDON or GARD) are generated, append misleading telephone model suffixes or mix sizes (e.g., 'Apple Watch Kordon Uyumlu 45mm Pro Max' or 'Huawei Watch Fit 3 Uyumlu Kordon Plus').
            - Levels 9-10 (Extreme Chaos): Combine case swapping, multiple spacing, brand mismatches (e.g. apple watch kordon for samsung watch), network generations (4G vs 5G) on same-generation devices (e.g. Redmi Note 13 Pro 4G vs 5G), Xiaomi/Redmi sub-brands, and Watch mm collisions.
            
            The output MUST be a valid JSON matching exactly this schema (it must return exactly an array called "products" containing {product_count} objects):
            {{
              "products": [
                 {{
                    "category": "KILIF" or "CAM" or "KORDON" or "GARD" or "KAMERA LENS",
                    "model": "resolved database clean model name (e.g. 'iPhone 15 Pro Max')",
                    "title": "chaotic mutated marketplace title matching the difficulty rules"
                 }},
                 ...
              ]
            }}
            
            Return ONLY the raw JSON. Do not include markdown code block syntax (like ```json), HTML tags, or any conversational text.
            """
            
            try:
                # Call Gemini 2.5 Flash
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_api_key}"
                headers = {"Content-Type": "application/json"}
                body = {
                    "contents": [
                        {"parts": [{"text": prompt}]}
                    ],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    }
                }
                
                req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=12) as response:
                    resp_json = json.loads(response.read().decode('utf-8'))
                    text_resp = resp_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    gemini_result = json.loads(text_resp)
                    
                    gemini_prods = gemini_result.get("products", [])
                    # Fallback to dictionary values if they returned a dictionary of p1, p2
                    if not gemini_prods and "p1" in gemini_result:
                        gemini_prods = [gemini_result["p1"]]
                        if "p2" in gemini_result:
                            gemini_prods.append(gemini_result["p2"])
                            
                    # Map back to our products_input array
                    for idx in range(min(product_count, len(gemini_prods))):
                        products_input[idx]["category"] = gemini_prods[idx].get("category", "KILIF")
                        products_input[idx]["model"] = gemini_prods[idx].get("model", "iPhone 15 Pro")
                        products_input[idx]["title"] = gemini_prods[idx].get("title", "Premium Kılıf")
                    
                    thinking_log.append("> [MODEL]: Gemini API çağrısı başarılı.")
                    for idx, p in enumerate(products_input):
                        thinking_log.append(f"> [AI P{idx+1}]: Kategori: {p['category']}, Model: {p['model']}")
                        thinking_log.append(f"> [AI P{idx+1}]: Üretilen Başlık: '{p['title']}'")
            except Exception as gemini_err:
                thinking_log.append(f"> [WARNING]: Gemini API çağrısı başarısız oldu: {str(gemini_err)}")
                thinking_log.append("> [FALLBACK]: Gelişmiş Yerel YZ Algoritmasına geçiş yapılıyor (Fallback active).")
                gemini_failed = True
                use_gemini = False
        
        # 2. Local AI Heuristics fallback or default
        if not use_gemini:
            thinking_log.append("> [MODEL]: Gelişmiş Yerel YZ Algoritması (Helezonik Model) aktif.")
            
            def fetch_random_db_product():
                try:
                    cur.execute("""
                        SELECT category, product_model, name 
                        FROM products 
                        WHERE category IS NOT NULL AND product_model IS NOT NULL AND name IS NOT NULL
                        ORDER BY RANDOM() LIMIT 1;
                    """)
                    row = cur.fetchone()
                    if row:
                        if hasattr(row, 'keys'):
                            return row['category'], row['product_model'], row['name']
                        elif isinstance(row, dict):
                            return row.get('category'), row.get('product_model'), row.get('name')
                        else:
                            return row[0], row[1], row[2]
                except Exception as db_e:
                    thinking_log.append(f"> [DB WARNING]: Referans ürün çekilirken hata oluştu: {str(db_e)}")
                
                fallback_pool = [
                    ("KILIF", "iPhone 15 Pro Max", "Blur iPhone 15 Pro Max / Lacivert"),
                    ("KILIF", "iPhone 16 Pro", "Cure iPhone 16 Pro / Gümüş"),
                    ("CAM", "iPhone 11", "Hayalet Ekran Koruyucu iPhone 11"),
                    ("KORDON", "Apple Watch 45mm", "Kordon Apple Watch 45mm Uyumlu / Kırmızı"),
                    ("GARD", "Apple Watch Ultra 49mm", "Gard-02 Koruyucu Kasa Apple Watch Ultra 49mm"),
                    ("KILIF", "Redmi Note 13 Pro 4G", "Glacier Redmi Note 13 Pro 4G / Şeffaf")
                ]
                return random.choice(fallback_pool)
            
            # Resolve all products in the list
            for idx in range(product_count):
                p = products_input[idx]
                cat = p.get("category", "").strip()
                model = p.get("model", "").strip()
                title = p.get("title", "").strip()
                
                if not cat and not model and not title:
                    cat, model, title = fetch_random_db_product()
                    thinking_log.append(f"> [AI]: Ürün {idx+1} boş bırakıldı. Veritabanından '{title}' ({cat}) ürünü referans seçildi.")
                else:
                    if not cat:
                        cat = "KILIF"
                    if not model:
                        model = "iPhone 15 Pro"
                    if not title:
                        title = f"Premium {model} Uyumlu {cat.capitalize()} Aksesuarı"
                    thinking_log.append(f"> [AI]: Ürün {idx+1} işlendi. Kategori={cat}, Model={model}")
                
                p["category"] = cat
                p["model"] = model
                p["title"] = title
            
            # Apply procedural difficulty-based mutations
            def mutate_text(text, diff, category, is_title=True):
                if not text:
                    return ""
                
                if diff >= 5:
                    words = text.split()
                    mutated_words = []
                    for w in words:
                        space_count = random.randint(2, 4) if random.random() < (diff - 4) * 0.2 else 1
                        mutated_words.append(w + (" " * space_count))
                    text = "".join(mutated_words).strip()
                
                if diff >= 3:
                    casing_prob = (diff - 2) * 0.12
                    chars = []
                    for c in text:
                        if c.isalpha() and random.random() < casing_prob:
                            chars.append(c.swapcase())
                        else:
                            chars.append(c)
                    text = "".join(chars)
                
                if diff >= 7 and is_title and category in ["KORDON", "GARD"]:
                    traps = ["Pro Max", "Ultra Series 10", "Pro Plus Uyumlu", "5G Uyumlu Kordon"]
                    trap_word = random.choice(traps)
                    text = f"{text} {trap_word}"
                    
                if diff >= 9 and is_title:
                    brand_traps = ["Xiaomi Redmi POCO Uyumlu", "Samsung S24 Ultra ve iPhone Uyumlu", "Apple Watch mm Kordon Xiaomi"]
                    trap_brand = random.choice(brand_traps)
                    text = f"{text} ({trap_brand})"
                    
                return text

            thinking_log.append(f"> [MUTATION]: Zorluk derecesi {difficulty} için manipülasyon kuralları yükleniyor...")
            
            # Mutate all products
            for idx in range(product_count):
                p = products_input[idx]
                cat = p["category"]
                model = p["model"]
                title = p["title"]
                
                p["title"] = mutate_text(title, difficulty, cat, is_title=True)
                p["model"] = mutate_text(model, difficulty, cat, is_title=False)
            
            if difficulty >= 3:
                thinking_log.append("> [MUTATION]: Harf karıştırma (Case variation) başarıyla enjekte edildi.")
            if difficulty >= 5:
                thinking_log.append("> [MUTATION]: Aşırı boşluk tuzakları (Spacing traps) kelimelere uygulandı.")
            if difficulty >= 7:
                thinking_log.append("> [MUTATION]: Smartwatch MM kordon telefon/plus trap sonekleri eklendi.")
            if difficulty >= 9:
                thinking_log.append("> [MUTATION]: Marka çelişkileri, Xiaomi-Redmi alt marka anomalileri enjekte edildi.")
            
        # 3. DB Insertion & Bridge mapping loops
        lines = []
        resolved_lines = []
        generated_lines_resp = []
        
        bridge_table = "product_trendyol" if marketplace == "Trendyol" else "product_hepsiburada"
        title_col = "title" if marketplace == "Trendyol" else "product_name"
        
        for idx in range(product_count):
            p = products_input[idx]
            p_id = p.get("product_id", "").strip()
            
            db_product_found = False
            if p_id:
                try:
                    cur.execute("""
                        SELECT id, barcode, name, category, product_model, label_compatible_model 
                        FROM products 
                        WHERE id = ? OR barcode = ? 
                        LIMIT 1;
                    """, (p_id, p_id))
                    ref_row = cur.fetchone()
                    if ref_row:
                        if hasattr(ref_row, "keys"):
                            p_id = ref_row["id"]
                            barcode = ref_row["barcode"]
                            title = ref_row["name"]
                            cat = ref_row["category"]
                            model = ref_row["product_model"]
                            compat = ref_row["label_compatible_model"]
                        else:
                            p_id = ref_row[0]
                            barcode = ref_row[1]
                            title = ref_row[2]
                            cat = ref_row[3]
                            model = ref_row[4]
                            compat = ref_row[5]
                        db_product_found = True
                        thinking_log.append(f"> [DATABASE]: Ürün {idx+1} veritabanındaki mevcut ürün kartından yüklendi. ID: {p_id}")
                except Exception as db_err:
                    print(f"Error fetching existing product: {db_err}")
            
            if not db_product_found:
                cat = p["category"]
                model = p["model"]
                title = p["title"]
                compat = p.get("compat", "").strip()
                
                if not compat:
                    # Eşleşen gerçek bir ürün bulmaya çalış ve label_compatible_model'ini kopyala
                    try:
                        cur.execute("""
                            SELECT label_compatible_model FROM products 
                            WHERE category = ? AND product_model = ? AND label_compatible_model IS NOT NULL AND label_compatible_model != '' AND label_compatible_model != 'null'
                            LIMIT 1;
                        """, (cat, model))
                        ref_row = cur.fetchone()
                        if ref_row:
                            compat = ref_row["label_compatible_model"] if isinstance(ref_row, dict) else ref_row[0]
                            thinking_log.append(f"> [DATABASE]: Ürün {idx+1} için veritabanından uyumluluk şablonu kopyalandı: '{compat}'")
                    except Exception as ref_err:
                        print(f"Error fetching reference compat: {ref_err}")
                else:
                    thinking_log.append(f"> [DATABASE]: Ürün {idx+1} için kullanıcı tarafından girilen uyumluluk şablonu kullanılacak: '{compat}'")
                
                barcode = f"8685{random.randint(10000000, 99999999)}"
                p_id = f"sim-{random.randint(1000, 9999)}"
                
                thinking_log.append(f"> [DATABASE]: Ürün {idx+1} için geçici stok kartı oluşturuluyor. ID: {p_id}, Barkod: {barcode}")
                
                cur.execute("""
                    INSERT INTO products (id, barcode, name, category, product_model, stock_quantity, label_compatible_model)
                    VALUES (?, ?, ?, ?, ?, 150, ?);
                """, (p_id, barcode, title, cat, model, compat))
            
            # Ensure bridge mapping exists so resolving barcode works
            cur.execute(f"SELECT 1 FROM {bridge_table} WHERE product_id = ? AND barcode = ? LIMIT 1;", (p_id, barcode))
            if not cur.fetchone():
                cur.execute(f"""
                    INSERT OR IGNORE INTO {bridge_table} (id, product_id, barcode, {title_col}, brand)
                    VALUES (?, ?, ?, ?, ?);
                """, (str(uuid.uuid4()), p_id, barcode, title, parse_brand(title)))
            
            lines.append({
                "sku": p_id,
                "price": 110.0,
                "barcode": barcode,
                "quantity": 1,
                "productName": title
            })
            
            resolved_lines.append({
                "line_barcode": barcode,
                "quantity": 1,
                "price": 110.0,
                "marketplace_title": title,
                "erp_product_id": p_id,
                "erp_product_name": title,
                "erp_category": cat,
                "erp_product_model": model,
                "erp_compatible_model": compat
            })
            
            generated_lines_resp.append({
                "barcode": barcode,
                "title": title,
                "model": model,
                "category": cat
            })
        
        # 4. Create simulated Order
        order_id = random.randint(10000000, 99999999)
        order_number = f"206{random.randint(100000, 999999)}"
        
        thinking_log.append(f"> [DATABASE]: Sipariş kaydediliyor. Sipariş No: #{order_number}")
        
        raw_data = {"lines": lines}
        shipment_address = {"city": "Istanbul", "fullName": f"{fname} {lname}", "fullAddress": "Istanbul/Turkiye"}
        total_price = 110.0 * product_count
        
        cur.execute("""
            INSERT INTO crm_orders (id, order_number, order_date, status, total_price, marketplace, customer_first_name, customer_last_name, shipment_address, raw_data, created_at)
            VALUES (?, ?, ?, 'Picking', ?, ?, ?, ?, ?, ?, datetime('now'));
        """, (order_id, order_number, datetime.now().isoformat(), total_price, marketplace, fname, lname, json.dumps(shipment_address), json.dumps(raw_data)))
        
        # 5. Evaluate red flags
        thinking_log.append("> [ENGINE]: Sipariş kalemi analizleri için hiyerarşik regex ve kural motoru tetiklendi...")
        analysis = evaluate_red_flags(resolved_lines, conn)
        
        # 6. Auto-create WhatsApp CRM entry for simulated order
        phone_status = f"+905{random.randint(30, 55)}{random.randint(1000000, 9999999)}"
        if difficulty in [5, 6]:
            phone_status = "işleniyor"
        elif difficulty in [7, 8]:
            phone_status = "hata"
        elif difficulty >= 9:
            phone_status = "null"
            
        has_conflicts = len([f for f in analysis["flags"] if f["type"] in ["CRITICAL", "WARNING"]]) > 0
        
        message_status = "cevap bekleniyor"
        chat_history_list = []
        
        if phone_status != "null":
            if phone_status == "hata":
                chat_history_list.append({
                    "sender": "system",
                    "time": datetime.now().strftime("%H:%M"),
                    "text": "[Sistem Hatası: Mesaj gönderilemedi. Geçersiz veya eksik telefon numarası formatı.]"
                })
            else:
                # Welcome template
                product_names_str = " ve ".join([normalize_model_name(l["erp_product_model"]) for l in resolved_lines if l.get("erp_product_model")])
                welcome_text = f"Merhaba {fname} Bey, Fibaks'tan sipariş ettiğiniz {product_names_str} ürünleri için model/uyumluluk teyidi rica ediyoruz. Siparişinizin doğruluğunu onaylıyor musunuz?"
                if fname.endswith(("a", "e", "ı", "i", "o", "ö", "u", "ü")):
                    welcome_text = f"Merhaba {fname} Hanım, Fibaks'tan sipariş ettiğiniz {product_names_str} ürünleri için model/uyumluluk teyidi rica ediyoruz. Siparişinizin doğruluğunu onaylıyor musunuz?"
                
                chat_history_list.append({
                    "sender": "system",
                    "time": datetime.now().strftime("%H:%M"),
                    "text": welcome_text
                })
                
                if not has_conflicts:
                    message_status = "başarıyla tamamlandı"
                    chat_history_list.append({
                        "sender": "customer",
                        "time": datetime.now().strftime("%H:%M"),
                        "text": "Evet doğrudur, gönderebilirsiniz. Teşekkürler!"
                    })
                    chat_history_list.append({
                        "sender": "system",
                        "time": datetime.now().strftime("%H:%M"),
                        "text": "Teyidiniz için teşekkür ederiz. Siparişiniz onaylanmış ve paketleme sürecine alınmıştır. İyi günler dileriz."
                    })
                else:
                    if random.random() < 0.5:
                        message_status = "itiraz - şikayet"
                        chat_history_list.append({
                            "sender": "customer",
                            "time": datetime.now().strftime("%H:%M"),
                            "text": "Merhaba, ben sanırım yanlışlık yapmışım. Modelleri değiştirebilir miyiz?"
                        })
                        
        cur.execute("""
            INSERT OR IGNORE INTO order_whatsapp_status (order_id, phone_status, message_status, chat_history, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'));
        """, (str(order_id), phone_status, message_status, json.dumps(chat_history_list)))
        
        conn.commit()
        thinking_log.append("> [DATABASE]: Tüm simülasyon ve CRM kayıtları başarıyla diske yazıldı (commit).")
        
        score = analysis["risk_score"]
        status_color = analysis["status_color"]
        flags_count = len(analysis["flags"])
        
        thinking_log.append(f"> [ENGINE]: Kural motoru tamamlandı. Risk Puanı: %{score}, Bayrak Sayısı: {flags_count}")
        thinking_log.append("> [SYSTEM]: Simülasyon işlemi başarıyla sonuçlandırıldı.")
        
        return {
            "success": True,
            "order_id": order_id,
            "order_number": order_number,
            "customer_name": f"{fname} {lname}",
            "marketplace": marketplace,
            "difficulty": difficulty,
            "thinking_log": thinking_log,
            "generated_lines": generated_lines_resp,
            "analysis_result": {
                "risk_score": score,
                "status_color": status_color,
                "flags": analysis["flags"]
            }
        }
        
    except Exception as e:
        if conn: conn.rollback()
        thinking_log.append(f"> [CRITICAL]: Simülasyon sırasında kritik bir hata oluştu: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "thinking_log": thinking_log
        }
    finally:
        cur.close()
        conn.close()

# --- WHATSAPP CRM ENDPOINTS ---

@app.get("/whatsapp", response_class=HTMLResponse)
async def whatsapp_page(request: Request):
    return templates.TemplateResponse("whatsapp.html", {"request": request})

@app.get("/api/whatsapp/chats")
async def get_whatsapp_chats():
    import json
    import random
    from datetime import datetime
    conn, mode = get_db_connection()
    if mode == 'sqlite':
        conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        resolved_orders = fetch_resolved_orders()
        cur.execute("SELECT * FROM order_whatsapp_status;")
        chats = cur.fetchall()
        chat_map = {}
        for c in chats:
            chat_map[str(c["order_id"])] = {
                "phone_status": c["phone_status"],
                "message_status": c["message_status"],
                "chat_history": json.loads(c["chat_history"]),
                "updated_at": c["updated_at"]
            }
            
        chats_list = []
        for o in resolved_orders:
            o_id_str = str(o["id"])
            if o_id_str in chat_map:
                chat_data = chat_map[o_id_str]
            else:
                phone_status = f"+905{random.randint(30, 55)}{random.randint(1000000, 9999999)}"
                message_status = "cevap bekleniyor"
                chat_history_list = []
                
                has_conflicts = len(o["flags"]) > 0
                if has_conflicts:
                    product_names_str = " ve ".join([normalize_model_name(l["erp_product_model"]) for l in o["lines"] if l.get("erp_product_model")])
                    fname = o["customer_name"].split(" ")[0]
                    welcome_text = f"Merhaba {fname} Bey, Fibaks'tan sipariş ettiğiniz {product_names_str} ürünleri için model/uyumluluk teyidi rica ediyoruz. Siparişinizin doğruluğunu onaylıyor musunuz?"
                    if fname.endswith(("a", "e", "ı", "i", "o", "ö", "u", "ü")):
                        welcome_text = f"Merhaba {fname} Hanım, Fibaks'tan sipariş ettiğiniz {product_names_str} ürünleri için model/uyumluluk teyidi rica ediyoruz. Siparişinizin doğruluğunu onaylıyor musunuz?"
                    
                    chat_history_list.append({
                        "sender": "system",
                        "time": datetime.now().strftime("%H:%M"),
                        "text": welcome_text
                    })
                
                cur.execute("""
                    INSERT OR IGNORE INTO order_whatsapp_status (order_id, phone_status, message_status, chat_history, updated_at)
                    VALUES (?, ?, ?, ?, datetime('now'));
                """, (o_id_str, phone_status, message_status, json.dumps(chat_history_list)))
                conn.commit()
                
                chat_data = {
                    "phone_status": phone_status,
                    "message_status": message_status,
                    "chat_history": chat_history_list,
                    "updated_at": datetime.now().isoformat()
                }
            
            last_message = ""
            if chat_data["chat_history"]:
                last_msg_obj = chat_data["chat_history"][-1]
                last_message = last_msg_obj.get("text", "")
            
            chats_list.append({
                "order_id": o_id_str,
                "order_number": o["order_number"],
                "order_date": o["order_date"],
                "customer_name": o["customer_name"],
                "marketplace": o["marketplace"],
                "phone_status": chat_data["phone_status"],
                "message_status": chat_data["message_status"],
                "last_message": last_message,
                "chat_history": chat_data["chat_history"],
                "updated_at": chat_data["updated_at"],
                "flags": o["flags"],
                "status_color": o["status_color"],
                "risk_score": o["risk_score"],
                "lines": o["lines"]
            })
            
        return {"success": True, "chats": chats_list}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.get("/api/whatsapp/chats/{order_id}")
async def get_whatsapp_chat_detail(order_id: str):
    import json
    conn, mode = get_db_connection()
    if mode == 'sqlite':
        conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM order_whatsapp_status WHERE order_id = ?;", (order_id,))
        chat = cur.fetchone()
        if not chat:
            return {"success": False, "error": "Sohbet bulunamadı"}
            
        resolved_orders = fetch_resolved_orders()
        matched_order = None
        for o in resolved_orders:
            if str(o["id"]) == order_id:
                matched_order = o
                break
                
        if not matched_order:
            return {"success": False, "error": "Sipariş bulunamadı"}
            
        return {
            "success": True,
            "order_id": order_id,
            "order_number": matched_order["order_number"],
            "order_date": matched_order["order_date"],
            "customer_name": matched_order["customer_name"],
            "marketplace": matched_order["marketplace"],
            "phone_status": chat["phone_status"],
            "message_status": chat["message_status"],
            "chat_history": json.loads(chat["chat_history"]),
            "updated_at": chat["updated_at"],
            "flags": matched_order["flags"],
            "status_color": matched_order["status_color"],
            "risk_score": matched_order["risk_score"],
            "lines": matched_order["lines"]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.post("/api/whatsapp/chats/{order_id}/message")
async def send_whatsapp_message(order_id: str, data: dict):
    import json
    from datetime import datetime
    conn, mode = get_db_connection()
    if mode == 'sqlite':
        conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        text = data.get("text", "").strip()
        sender = data.get("sender", "admin").strip()
        
        if not text:
            return {"success": False, "error": "Mesaj içeriği boş olamaz"}
            
        cur.execute("SELECT * FROM order_whatsapp_status WHERE order_id = ?;", (order_id,))
        chat = cur.fetchone()
        if not chat:
            return {"success": False, "error": "Sohbet bulunamadı"}
            
        chat_history = json.loads(chat["chat_history"])
        
        new_msg = {
            "sender": sender,
            "time": datetime.now().strftime("%H:%M"),
            "text": text
        }
        chat_history.append(new_msg)
        
        customer_reply = None
        current_status = chat["message_status"]
        
        text_lower = text.lower()
        
        if sender == "admin":
            if "iptal" in text_lower:
                customer_reply = "Anlıyorum, iptal edebilirsiniz. Teşekkürler."
                current_status = "başarıyla tamamlandı"
            elif "güncelledik" in text_lower or "değiştirdik" in text_lower or "revize" in text_lower:
                customer_reply = "Süper, çok teşekkürler! Kolay gelsin."
                current_status = "başarıyla tamamlandı"
            elif "onaylıyor musunuz" in text_lower or "doğru mudur" in text_lower or "emin misiniz" in text_lower or text_lower.endswith("?"):
                if chat["message_status"] == "itiraz - şikayet":
                    customer_reply = "Evet, kılıfı iPhone 8 (standart) yapalım, camı da standart iPhone 8 yapalım lütfen. Çok teşekkürler."
                else:
                    customer_reply = "Evet, hepsi doğrudur. Gönderebilirsiniz."
                    current_status = "başarıyla tamamlandı"
            elif "merhaba" in text_lower or "selam" in text_lower:
                customer_reply = "Merhaba, siparişimle ilgili yardımcı olabilir misiniz?"
            elif "yardımcı" in text_lower or "nasıl yardımcı" in text_lower:
                customer_reply = "Siparişimde kılıfı yanlış model seçmişim, Plus yerine düz modelle değiştirmek istiyordum."
        
        if customer_reply:
            reply_msg = {
                "sender": "customer",
                "time": datetime.now().strftime("%H:%M"),
                "text": customer_reply
            }
            chat_history.append(reply_msg)
            
        cur.execute("""
            UPDATE order_whatsapp_status 
            SET chat_history = ?, message_status = ?, updated_at = datetime('now')
            WHERE order_id = ?;
        """, (json.dumps(chat_history), current_status, order_id))
        conn.commit()
        
        return {
            "success": True, 
            "chat_history": chat_history,
            "message_status": current_status
        }
    except Exception as e:
        if conn: conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.post("/api/whatsapp/chats/{order_id}/status")
async def update_whatsapp_status(order_id: str, data: dict):
    conn, mode = get_db_connection()
    if mode == 'sqlite':
        conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        phone_status = data.get("phone_status")
        message_status = data.get("message_status")
        
        cur.execute("SELECT * FROM order_whatsapp_status WHERE order_id = ?;", (order_id,))
        chat = cur.fetchone()
        if not chat:
            return {"success": False, "error": "Sohbet bulunamadı"}
            
        updates = []
        params = []
        if phone_status is not None:
            updates.append("phone_status = ?")
            params.append(phone_status)
        if message_status is not None:
            updates.append("message_status = ?")
            params.append(message_status)
            
        if not updates:
            return {"success": False, "error": "Güncellenecek alan gönderilmedi"}
            
        params.append(order_id)
        query = f"UPDATE order_whatsapp_status SET {', '.join(updates)}, updated_at = datetime('now') WHERE order_id = ?;"
        
        cur.execute(query, tuple(params))
        conn.commit()
        
        return {"success": True, "message": "Statü başarıyla güncellendi"}
    except Exception as e:
        if conn: conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.post("/api/whatsapp/chats/{order_id}/update-models")
async def update_order_product_models(order_id: str, data: dict):
    conn, mode = get_db_connection()
    if mode == 'sqlite':
        conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        updates = data.get("updates", [])
        if not updates:
            return {"success": False, "error": "Güncellenecek model bulunamadı"}
            
        for u in updates:
            barcode = u.get("barcode")
            new_model = u.get("model", "").strip()
            if barcode and new_model:
                product_id = None
                
                # 1. Search in product_trendyol
                cur.execute("SELECT product_id FROM product_trendyol WHERE barcode = ?;", (barcode,))
                row = cur.fetchone()
                if row:
                    product_id = row["product_id"]
                    
                # 2. Search in product_hepsiburada
                if not product_id:
                    cur.execute("SELECT product_id FROM product_hepsiburada WHERE barcode = ?;", (barcode,))
                    row = cur.fetchone()
                    if row:
                        product_id = row["product_id"]
                        
                # 3. Search in products directly
                if not product_id:
                    cur.execute("SELECT id FROM products WHERE barcode = ?;", (barcode,))
                    row = cur.fetchone()
                    if row:
                        product_id = row["id"]
                        
                # If found, update products model
                if product_id:
                    cur.execute("""
                        UPDATE products 
                        SET product_model = ? 
                        WHERE id = ?;
                    """, (new_model, product_id))
                
        conn.commit()
        return {"success": True, "message": "Modeller başarıyla güncellendi"}
    except Exception as e:
        if conn: conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()

@app.get("/api/db-status")
async def get_db_status():
    global DB_MODE, DB_CONN_ERROR
    db_url = os.getenv("DATABASE_URL")
    masked_url = None
    if db_url:
        import urllib.parse
        try:
            parsed = urllib.parse.urlsplit(db_url)
            if parsed.password:
                masked_url = db_url.replace(parsed.password, "********")
            else:
                masked_url = db_url
        except Exception:
            masked_url = "[Unparseable URL]"
            
    products_count = 0
    try:
        conn, mode = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM products;")
        row = cur.fetchone()
        if isinstance(row, dict):
            products_count = list(row.values())[0]
        else:
            products_count = row[0]
        cur.close()
        conn.close()
    except Exception as e:
        products_count = f"Error: {str(e)}"
        
    return {
        "db_mode": DB_MODE,
        "database_url_exists": db_url is not None,
        "database_url_masked": masked_url,
        "postgres_error": DB_CONN_ERROR,
        "products_count": products_count
    }

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    is_prod = os.getenv("DATABASE_URL") is not None
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=not is_prod)
