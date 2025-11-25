CREATE TABLE auction_batches (
  date STRING(6) NOT NULL,
  source_filename STRING(1024),
  row_count INT64,
  updated_at TIMESTAMP OPTIONS (allow_commit_timestamp = TRUE)
) PRIMARY KEY (date);

CREATE TABLE auction_items (
  date STRING(6) NOT NULL,
  row_order INT64 NOT NULL,
  sell_number INT64,
  car_number STRING(32),
  post_title STRING(MAX),
  title STRING(MAX),
  color STRING(64),
  fuel STRING(32),
  image STRING(MAX),
  km INT64,
  price INT64,
  trans STRING(32),
  year INT64,
  auction_name STRING(128),
  vin STRING(64),
  score STRING(32),
  created_at TIMESTAMP OPTIONS (allow_commit_timestamp = TRUE)
) PRIMARY KEY (date, row_order);

CREATE INDEX idx_auction_items_sell_number
ON auction_items(sell_number)
WHERE sell_number IS NOT NULL;

---