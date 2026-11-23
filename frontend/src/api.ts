import type {
  Account,
  AutoStatus,
  Favorite,
  Genre,
  KeywordFavorite,
  NotificationList,
  PaymentMethod,
  Product,
  StorePickupResult,
} from "./types";

export type ApiErrorKind =
  | "login_failed"
  | "not_found"
  | "not_purchasable"
  | "payment_unavailable"
  | "duplicate"
  | "limit"
  | "invalid_transition"
  | "unsupported"
  | "timeout"
  | "disabled"
  | "upstream"
  | "invalid"
  | "network";

export class ApiError extends Error {
  constructor(readonly kind: ApiErrorKind) {
    super(kind);
  }
}

function conflictKind(detail: string): ApiErrorKind {
  switch (detail) {
    case "not_purchasable":
      return "not_purchasable";
    case "duplicate_account":
    case "duplicate_favorite":
      return "duplicate";
    case "favorite_limit":
      return "limit";
    case "invalid_transition":
      return "invalid_transition";
    default:
      return "payment_unavailable";
  }
}

async function classify(response: Response): Promise<ApiErrorKind> {
  const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
  const detail = typeof body.detail === "string" ? body.detail : "";
  switch (response.status) {
    case 401:
      return "login_failed";
    case 403:
      return "disabled";
    case 404:
      return "not_found";
    case 409:
      return conflictKind(detail);
    case 422:
      return detail.startsWith("unsupported_payment_method") ? "unsupported" : "invalid";
    case 504:
      return "timeout";
    default:
      return "upstream";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError("network");
  }
  if (!response.ok) throw new ApiError(await classify(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export type PreviewRequest = {
  account_id: string;
  product_id: number;
  payment_method: string;
  submit_order: boolean;
  handoff: boolean;
};

export type FavoritePatch = {
  payment_method?: string;
  price_cap_yen?: number | null;
  resume?: boolean;
};

const patch = (body: unknown): RequestInit => ({ ...post(body), method: "PATCH" });
const put = (body: unknown): RequestInit => ({ ...post(body), method: "PUT" });
const remove: RequestInit = { method: "DELETE" };

export const api = {
  listPaymentMethods: () => request<PaymentMethod[]>("/api/payment-methods"),
  searchByCode: async (productId: number) => [await request<Product>(`/api/products/${productId}`)],
  searchByKeyword: (keyword: string) =>
    request<Product[]>(`/api/products?keyword=${encodeURIComponent(keyword)}`),
  runPreview: (body: PreviewRequest) =>
    request<StorePickupResult>("/api/store-pickup-preview", post(body)),
  listAccounts: () => request<Account[]>("/api/accounts"),
  addAccount: (body: { label: string; email: string; password: string }) =>
    request<Account>("/api/accounts", post(body)),
  deleteAccount: (id: string) => request<void>(`/api/accounts/${id}`, remove),
  listFavorites: (accountId: string) =>
    request<Favorite[]>(`/api/favorites?account_id=${encodeURIComponent(accountId)}`),
  addFavorite: (body: { account_id: string; product_id: number; payment_method: string }) =>
    request<Favorite>("/api/favorites", post(body)),
  updateFavorite: (id: string, body: FavoritePatch) =>
    request<Favorite>(`/api/favorites/${id}`, patch(body)),
  deleteFavorite: (id: string) => request<void>(`/api/favorites/${id}`, remove),
  notifications: () => request<NotificationList>("/api/notifications"),
  markNotificationsRead: () => request<{ unread: number }>("/api/notifications/read", post({})),
  autoStatus: () => request<AutoStatus>("/api/auto-purchase/status"),
  setAutoEnabled: (enabled: boolean) =>
    request<AutoStatus>("/api/auto-purchase/enabled", put({ enabled })),
  listGenres: () => request<Genre[]>("/api/genres"),
  listKeywordFavorites: (accountId: string) =>
    request<KeywordFavorite[]>(
      `/api/keyword-favorites?account_id=${encodeURIComponent(accountId)}`,
    ),
  addKeywordFavorite: (body: {
    account_id: string;
    keyword: string;
    category_id: number;
    payment_method: string;
    price_cap_yen: number | null;
  }) => request<KeywordFavorite>("/api/keyword-favorites", post(body)),
  updateKeywordFavorite: (
    id: string,
    body: { payment_method: string; price_cap_yen: number | null },
  ) => request<KeywordFavorite>(`/api/keyword-favorites/${id}`, patch(body)),
  setKeywordFavoriteEnabled: (id: string, enabled: boolean) =>
    request<KeywordFavorite>(`/api/keyword-favorites/${id}/enabled`, put({ enabled })),
  deleteKeywordFavorite: (id: string) => request<void>(`/api/keyword-favorites/${id}`, remove),
};
