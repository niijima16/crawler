import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api";
import { AccountCard } from "./components/AccountCard";
import { AutoPurchaseTab } from "./components/AutoPurchaseTab";
import { FavoritesTab } from "./components/FavoritesTab";
import { HandoffCard } from "./components/HandoffCard";
import { Header } from "./components/Header";
import { type Mode, OptionsCard, type SearchMode } from "./components/OptionsCard";
import { OrderConfirmDialog } from "./components/OrderConfirmDialog";
import { OrderSummaryCard } from "./components/OrderSummaryCard";
import { type Outcome, ResultCard } from "./components/ResultCard";
import { SearchCard } from "./components/SearchCard";
import { Stepper } from "./components/Stepper";
import { type Tab, Tabs } from "./components/Tabs";
import { isExtensionInstalled, openConfirmation } from "./extension";
import { maskEmail } from "./format";
import { favoriteError, LOGIN_INVALIDATED } from "./messages";
import type {
  Account,
  AppNotification,
  AutoStatus,
  Favorite,
  Genre,
  KeywordFavorite,
  NotificationList,
  PaymentMethod,
  Product,
} from "./types";

const DEFAULT_PAYMENT_ID = "8";
const POLL_MS = 30_000;

export function App() {
  const [tab, setTab] = useState<Tab>("search");
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [accountId, setAccountId] = useState<string | null>(null);
  const [methods, setMethods] = useState<PaymentMethod[]>([]);
  const [paymentId, setPaymentId] = useState(DEFAULT_PAYMENT_ID);
  const [mode, setMode] = useState<Mode>("check");
  const [searchMode, setSearchMode] = useState<SearchMode>("code");
  const [selected, setSelected] = useState<Product | null>(null);
  const [running, setRunning] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<Favorite[]>([]);
  const [genres, setGenres] = useState<Genre[]>([]);
  const [keywordFavorites, setKeywordFavorites] = useState<KeywordFavorite[]>([]);
  const [favoriteMessage, setFavoriteMessage] = useState<string | null>(null);
  const [notes, setNotes] = useState<NotificationList>({ unread: 0, items: [] });
  const [status, setStatus] = useState<AutoStatus | null>(null);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    api.listPaymentMethods().then(setMethods, () => setMethods([]));
    api.listGenres().then(setGenres, () => setGenres([]));
    api.listAccounts().then(
      (list) => {
        setAccounts(list);
        setAccountId((current) => current ?? list[0]?.id ?? null);
      },
      () => setAccounts([]),
    );
  }, []);

  const loadFavorites = useCallback(() => {
    if (accountId === null) {
      setFavorites([]);
      setKeywordFavorites([]);
      return;
    }
    api.listFavorites(accountId).then(setFavorites, () => setFavorites([]));
    api.listKeywordFavorites(accountId).then(setKeywordFavorites, () => setKeywordFavorites([]));
  }, [accountId]);

  useEffect(loadFavorites, [loadFavorites]);

  const loadStatus = useCallback(() => {
    setNow(new Date());
    api.notifications().then(setNotes, () => undefined);
    api.autoStatus().then(setStatus, () => undefined);
  }, []);

  useEffect(() => {
    loadStatus();
    const timer = setInterval(loadStatus, POLL_MS);
    return () => clearInterval(timer);
  }, [loadStatus]);

  // 引き継ぎが完了したら、拡張があれば確認画面を別タブに自動で開く（1回だけ）。
  const openedHandoffRef = useRef<string | null>(null);
  useEffect(() => {
    const handoff = outcome?.status === "done" ? outcome.result.handoff : null;
    if (handoff && isExtensionInstalled() && openedHandoffRef.current !== handoff.cookie_value) {
      openedHandoffRef.current = handoff.cookie_value;
      openConfirmation(handoff.cookie_value);
    }
  }, [outcome]);

  const locked = accountId === null;
  const account = accounts?.find((a) => a.id === accountId) ?? null;
  const paymentLabel = methods.find((m) => m.id === paymentId)?.label ?? "";
  const canFavorite =
    !locked && methods.find((m) => m.id === paymentId)?.submit_supported !== false;

  function choosePayment(id: string) {
    setPaymentId(id);
    if (mode === "order" && methods.find((m) => m.id === id)?.submit_supported === false) {
      setMode("check");
    }
  }

  function selectAccount(id: string | null) {
    setAccountId(id);
    setSelected(null);
    setOutcome(null);
    setNotice(null);
  }

  function removeAccount(id: string) {
    const rest = (accounts ?? []).filter((a) => a.id !== id);
    setAccounts(rest);
    if (id === accountId) selectAccount(rest[0]?.id ?? null);
  }

  async function addFavorite(product: Product) {
    if (accountId === null) return;
    setFavoriteMessage(null);
    try {
      await api.addFavorite({
        account_id: accountId,
        product_id: product.product_id,
        payment_method: paymentId,
      });
      loadFavorites();
    } catch (error) {
      setFavoriteMessage(favoriteError(error instanceof ApiError ? error.kind : "network"));
    }
  }

  async function execute(submitOrder: boolean) {
    if (accountId === null || !selected) return;
    setConfirming(false);
    setRunning(true);
    setOutcome(null);
    try {
      const result = await api.runPreview({
        account_id: accountId,
        product_id: selected.product_id,
        payment_method: paymentId,
        submit_order: submitOrder,
        handoff: mode === "handoff",
      });
      setOutcome({ status: "done", result });
    } catch (error) {
      const kind = error instanceof ApiError ? error.kind : "network";
      if (kind === "login_failed") setNotice(LOGIN_INVALIDATED);
      else setOutcome({ status: "error", kind });
    } finally {
      setRunning(false);
    }
  }

  const openArrival = useCallback(
    async (note: AppNotification) => {
      if (accountId === null || note.product_id === null) return;
      try {
        const result = await api.runPreview({
          account_id: accountId,
          product_id: note.product_id,
          payment_method: note.payment_method ?? DEFAULT_PAYMENT_ID,
          submit_order: false,
          handoff: true,
        });
        if (result.handoff && isExtensionInstalled()) {
          openConfirmation(result.handoff.cookie_value);
        }
      } catch {
        // 売り切れ等は結果カードではなく通知側で扱う（ここでは握りつぶさず再取得に任せる）
        loadStatus();
      }
    },
    [accountId, loadStatus],
  );

  const step = locked ? 1 : outcome ? 5 : selected ? 4 : 3;
  return (
    <div className="screen">
      <Header email={account?.email ?? null} />
      <Tabs current={tab} unread={notes.unread} onChange={setTab} />
      {tab === "search" && (
        <>
          <Stepper current={step} />
          <div className="body">
            <div className="col">
              <AccountCard
                accounts={accounts}
                selectedId={accountId}
                notice={notice}
                onSelect={selectAccount}
                onAdded={(added) => {
                  setAccounts((list) => [...(list ?? []), added]);
                  selectAccount(added.id);
                }}
                onDeleted={removeAccount}
              />
              {locked && <p className="locknote">🔒 ログインすると使えます</p>}
              <OptionsCard
                methods={methods}
                paymentId={paymentId}
                mode={mode}
                searchMode={searchMode}
                disabled={locked || running}
                onPayment={choosePayment}
                onMode={setMode}
                onSearchMode={setSearchMode}
              />
              <SearchCard
                searchMode={searchMode}
                disabled={locked || running}
                selectedId={selected?.product_id ?? null}
                onSelect={(product) => {
                  setSelected(product);
                  setOutcome(null);
                }}
                favorites={favorites}
                canFavorite={canFavorite}
                favoriteMessage={favoriteMessage}
                onFavorite={addFavorite}
              />
            </div>
            <div className="col">
              <OrderSummaryCard
                product={selected}
                paymentLabel={paymentLabel}
                mode={mode}
                account={account ? maskEmail(account.email) : null}
                running={running}
                locked={locked}
                onRun={() => (mode === "order" ? setConfirming(true) : execute(false))}
                handoffReady={outcome?.status === "done" && outcome.result.handoff !== null}
                canOpenHandoff={isExtensionInstalled()}
                onOpenHandoff={() =>
                  outcome?.status === "done" &&
                  outcome.result.handoff &&
                  openConfirmation(outcome.result.handoff.cookie_value)
                }
              />
              {outcome?.status === "done" && outcome.result.handoff ? (
                <HandoffCard
                  preview={outcome.result.preview}
                  handoff={outcome.result.handoff}
                  extensionInstalled={isExtensionInstalled()}
                />
              ) : (
                outcome && <ResultCard outcome={outcome} />
              )}
            </div>
          </div>
        </>
      )}
      {tab === "favorites" && (
        <div className="body one">
          {locked ? (
            <p className="locknote">「商品を探す」タブでアカウントを追加してください。</p>
          ) : (
            <FavoritesTab
              favorites={favorites}
              methods={methods}
              onChanged={loadFavorites}
              keywordFavorites={keywordFavorites}
              genres={genres}
              accountId={accountId ?? ""}
            />
          )}
        </div>
      )}
      {tab === "auto" && (
        <div className="body one">
          <AutoPurchaseTab
            status={status}
            notifications={notes}
            now={now}
            onChanged={loadStatus}
            onOpenConfirmation={openArrival}
          />
        </div>
      )}
      {confirming && selected && account && (
        <OrderConfirmDialog
          product={selected}
          paymentLabel={paymentLabel}
          account={maskEmail(account.email)}
          onConfirm={() => execute(true)}
          onCancel={() => setConfirming(false)}
        />
      )}
      <footer className="foot">Pickup Assistant — 購入の確定はサイトの画面で行います</footer>
    </div>
  );
}
