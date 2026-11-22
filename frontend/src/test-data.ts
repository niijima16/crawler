import type {
  Account,
  AppNotification,
  AutoStatus,
  Favorite,
  PaymentMethod,
  Product,
  StorePickupResult,
} from "./types";

export const METHODS: PaymentMethod[] = [
  { id: "8", label: "店頭支払", preview_supported: true, submit_supported: true },
  { id: "3", label: "代金引換", preview_supported: true, submit_supported: true },
  { id: "1", label: "銀行振込", preview_supported: true, submit_supported: true },
  { id: "2", label: "郵便振替", preview_supported: true, submit_supported: true },
  { id: "10000006", label: "PayPal", preview_supported: true, submit_supported: false },
  { id: "10000050", label: "PayPayオンライン", preview_supported: true, submit_supported: false },
  { id: "10000002_1", label: "後払い", preview_supported: true, submit_supported: false },
  { id: "10000028", label: "クレジットカード", preview_supported: false, submit_supported: false },
];

export const MAME: Product = {
  product_id: 807736,
  name: "SD/豆本 S-26-11-01-584-TO-ZS",
  price_yen: 990,
  in_stock: true,
};

export const SOLD_OUT: Product = {
  product_id: 810296,
  name: "SD/豆本 I-26-11-05-334-KD-ZI",
  price_yen: 550,
  in_stock: false,
};

export const PREVIEW_RESULT: StorePickupResult = {
  preview: {
    product_id: 807736,
    item_name: "SD/豆本 S-26-11-01-584-TO-ZS",
    payment_method: "店頭支払",
    shipping_fee_yen: 660,
    total_yen: 1650,
  },
  attempts: 7,
  order: null,
  handoff: null,
};

export const ACCOUNT: Account = { id: "a1", label: "テスト用 A", email: "tester@example.com" };
export const ACCOUNT_B: Account = { id: "a2", label: "テスト用 B", email: "sato@example.com" };

export function favorite(overrides: Partial<Favorite> = {}): Favorite {
  return {
    id: "f1",
    account_id: "a1",
    product_id: 807736,
    product_name: "SD/豆本 S-26-11-01-584-TO-ZS",
    payment_method: "8",
    price_cap_yen: null,
    state: "watching",
    state_version: 0,
    state_changed_at: "2026-11-22T12:00:00Z",
    ...overrides,
  };
}

export const STATUS: AutoStatus = {
  enabled: true,
  order_submit_allowed: true,
  last_tick_at: "2026-11-22T10:59:30Z",
  next_nightly_at: "2026-11-22T12:23:00Z",
};

export const NOTE_REJECTED: AppNotification = {
  id: "n1",
  favorite_id: "f1",
  kind: "rejected",
  message: "サイトの reCAPTCHA により注文は受理されませんでした（注文は作られていません）: SD/豆本",
  created_at: "2026-11-22T12:00:00Z",
  read: false,
};

export const NOTE_PURCHASED: AppNotification = {
  id: "n2",
  favorite_id: "f2",
  kind: "purchased",
  message: "注文が確定しました（受注番号 96301）: SD16/OF:靴",
  created_at: "2026-11-21T05:12:00Z",
  read: true,
};
