export type Product = { product_id: number; name: string; price_yen: number; in_stock: boolean };

export type PaymentMethod = {
  id: string;
  label: string;
  preview_supported: boolean;
  submit_supported: boolean;
};

export type CheckoutPreview = {
  product_id: number;
  item_name: string;
  payment_method: string;
  shipping_fee_yen: number;
  total_yen: number;
};

export type OrderResult = {
  status: "submitted" | "rejected" | "unknown";
  order_id: string | null;
  reason: string | null;
};

export type Handoff = {
  cookie_name: string;
  cookie_value: string;
  confirm_url: string;
};

export type StorePickupResult = {
  preview: CheckoutPreview;
  attempts: number;
  order: OrderResult | null;
  handoff: Handoff | null;
};

export type Account = { id: string; label: string; email: string };

export type FavoriteState =
  | "watching"
  | "purchasing"
  | "purchased"
  | "rejected"
  | "unknown"
  | "stopped";

export type Favorite = {
  id: string;
  account_id: string;
  product_id: number;
  product_name: string;
  payment_method: string;
  price_cap_yen: number | null;
  state: FavoriteState;
  state_version: number;
  state_changed_at: string;
};

export type NotificationKind =
  | "purchased"
  | "rejected"
  | "unknown"
  | "skipped_price_cap"
  | "account_stopped"
  | "submit_disabled";

export type AppNotification = {
  id: string;
  favorite_id: string | null;
  kind: NotificationKind;
  message: string;
  created_at: string;
  read: boolean;
};

export type NotificationList = { unread: number; items: AppNotification[] };

export type AutoStatus = {
  enabled: boolean;
  order_submit_allowed: boolean;
  last_tick_at: string | null;
  next_nightly_at: string;
};
