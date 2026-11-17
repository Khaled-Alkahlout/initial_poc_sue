-- Minimal synthetic schema and rows for the four existing proof-of-concept cases.
-- Load into a new, disposable PostgreSQL 16 test database.
BEGIN;

CREATE TABLE customers (
    id integer PRIMARY KEY,
    tenant_id integer NOT NULL,
    email text,
    company text,
    country_code text
);
CREATE TABLE orders (
    id integer PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_id integer NOT NULL REFERENCES customers (id),
    total_cents integer NOT NULL,
    created_at timestamp NOT NULL,
    status text NOT NULL,
    currency text NOT NULL
);
CREATE TABLE products (
    id integer PRIMARY KEY,
    sku text,
    name text,
    brand text,
    currency text
);
CREATE TABLE product_variants (
    id uuid PRIMARY KEY,
    product_id integer NOT NULL REFERENCES products (id)
);
CREATE TABLE order_lines (
    order_id integer NOT NULL REFERENCES orders (id),
    variant_id text NOT NULL,
    quantity integer NOT NULL,
    line_total_cents integer NOT NULL
);
CREATE TABLE audit_log (
    id integer PRIMARY KEY,
    tenant_id integer NOT NULL,
    table_name text NOT NULL,
    row_id uuid,
    action text NOT NULL,
    old_data jsonb,
    new_data jsonb,
    actor_id integer,
    is_system boolean NOT NULL,
    created_at timestamp NOT NULL
);
CREATE INDEX orders_tenant_created ON orders (tenant_id, created_at);
CREATE INDEX audit_tenant_created ON audit_log (tenant_id, created_at);

INSERT INTO customers VALUES
    (1, 1, NULL, 'fixture-a', 'ZZ'),
    (2, 1, NULL, 'fixture-b', NULL),
    (3, 2, NULL, 'fixture-c', 'ZZ');
INSERT INTO orders VALUES
    (1, 1, 1, 100, '2024-01-01', 'paid', 'EUR'),
    (2, 1, 1, 150, '2024-08-01', 'paid', 'EUR'),
    (3, 1, 1, 250, '2024-08-15', 'delivered', 'EUR'),
    (4, 1, 2, 200, '2024-07-01', 'shipped', 'EUR'),
    (5, 1, 2, 120, '2024-08-01', 'processing', 'EUR'),
    (6, 1, 2,  20, '2024-08-16', 'cancelled', 'EUR'),
    (7, 2, 3,  75, '2024-06-01', 'paid', 'EUR'),
    (8, 2, 3, 125, '2024-07-01', 'delivered', 'EUR');
INSERT INTO products VALUES
    (1, 'fixture-sku-1', 'fixture-product-1', NULL, 'EUR'),
    (2, 'fixture-sku-2', 'fixture-product-2', NULL, 'EUR');
INSERT INTO product_variants VALUES
    ('00000000-0000-0000-0000-000000000001', 1),
    ('00000000-0000-0000-0000-000000000002', 1),
    ('00000000-0000-0000-0000-000000000003', 2);
INSERT INTO order_lines VALUES
    (1, '00000000-0000-0000-0000-000000000001', 1, 25),
    (1, '00000000-0000-0000-0000-000000000001', 1, 25),
    (1, '00000000-0000-0000-0000-000000000002', 2, 50),
    (2, '00000000-0000-0000-0000-000000000003', 2, 150),
    (3, '00000000-0000-0000-0000-000000000002', 1, 250),
    (4, '00000000-0000-0000-0000-000000000002', 1, 200),
    (5, '00000000-0000-0000-0000-000000000003', 1, 120),
    (6, '00000000-0000-0000-0000-000000000001', 1, 20),
    (7, '00000000-0000-0000-0000-000000000001', 1, 75),
    (8, '00000000-0000-0000-0000-000000000003', 1, 125);
INSERT INTO audit_log VALUES
    (1, 1, 'orders', NULL, 'insert', NULL, '{"fixture":true}', NULL, true, '2024-08-01'),
    (2, 1, 'customers', NULL, 'update', '{}', '{"fixture":true}', NULL, false, '2024-08-01'),
    (3, 1, 'orders', NULL, 'update', '{}', '{}', NULL, true, '2024-08-02'),
    (4, 2, 'orders', NULL, 'insert', NULL, '{}', NULL, true, '2024-07-01');

ANALYZE customers, orders, products, product_variants, order_lines, audit_log;
COMMIT;
