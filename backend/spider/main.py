import os
import random
import time
from asyncio import sleep

from spider.application.favorites import FavoriteDeps
from spider.application.keyword_favorites import KeywordFavoriteDeps
from spider.application.preview import CheckoutParsers
from spider.application.retry import PreviewRuntime
from spider.config import (
    LOGIN_CHECK_DEADLINE_SECONDS,
    load_category_cache_ttl,
    load_preview_config,
)
from spider.infrastructure.category_provider import SiteCategoryProvider
from spider.infrastructure.history_parser import extract_orders
from spider.infrastructure.http_client import HttpSiteClient
from spider.infrastructure.product_parser import extract_latest_product_name
from spider.infrastructure.product_parsers import (
    extract_categories,
    extract_confirm,
    extract_order_form,
    extract_payment_options,
    extract_product_ids,
    extract_product_page,
    extract_search_results,
    is_in_cart,
    is_recaptcha_rejected,
)
from spider.presentation.api import Dependencies, create_app
from spider.wiring import SystemClock, build_store, new_id

_store, _setup = build_store(os.environ)
_runtime = PreviewRuntime(sleep=sleep, rng=random.random, now=time.monotonic)
_categories = SiteCategoryProvider(
    client_factory=HttpSiteClient,
    parse=extract_categories,
    now=time.monotonic,
    ttl_seconds=load_category_cache_ttl(os.environ),
)

app = create_app(
    Dependencies(
        client_factory=HttpSiteClient,
        extract_latest_name=extract_latest_product_name,
        extract_orders=extract_orders,
        extract_product_page=extract_product_page,
        extract_search_results=extract_search_results,
        extract_product_ids=extract_product_ids,
        checkout_parsers=CheckoutParsers(
            is_in_cart=is_in_cart,
            payment_options=extract_payment_options,
            confirm=extract_confirm,
            order_form=extract_order_form,
            recaptcha_rejected=is_recaptcha_rejected,
            order_ids=lambda html: {o.order_id for o in extract_orders(html)},
        ),
        preview_config=load_preview_config(os.environ),
        runtime=_runtime,
        login_deadline_seconds=LOGIN_CHECK_DEADLINE_SECONDS,
        favorite_deps=FavoriteDeps(
            accounts=_store.accounts,
            favorites=_store.favorites,
            keyword_favorites=_store.keyword_favorites,
            notifications=_store.notifications,
            settings=_store.settings,
            secret_box=_store.secret_box,
            clock=SystemClock(),
            new_id=new_id,
            client_factory=HttpSiteClient,
            extract_product_page=extract_product_page,
            runtime=_runtime,
            login_deadline_seconds=LOGIN_CHECK_DEADLINE_SECONDS,
        ),
        keyword_deps=KeywordFavoriteDeps(
            keyword_favorites=_store.keyword_favorites,
            accounts=_store.accounts,
            categories=_categories,
            clock=SystemClock(),
            new_id=new_id,
        ),
        on_startup=_setup,
    )
)
