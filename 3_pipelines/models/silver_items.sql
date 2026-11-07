select item_id, sku, description, unit_price
from {{ src('items') }}
