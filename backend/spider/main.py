from spider.infrastructure.history_parser import extract_orders
from spider.infrastructure.http_client import HttpSiteClient
from spider.infrastructure.product_parser import extract_latest_product_name
from spider.presentation.api import create_app

app = create_app(HttpSiteClient, extract_latest_product_name, extract_orders)
