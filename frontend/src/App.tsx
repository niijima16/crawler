import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api";
import { type Arrival, collectArrivals, enqueue, loadAutoOpen, saveAutoOpen } from "./autoOpen";
import { AccountCard } from "./components/AccountCard";
import { type AutoLine, AutoPurchaseTab } from "./components/AutoPurchaseTab";
import { FavoritesTab } from "./components/FavoritesTab";
import { HandoffProgress } from "./components/HandoffProgress";
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
// 新着通知はすぐ開けるよう、通知だけ短い間隔で取得する（自分の backend への問い合わせのみ）
const NOTE_POLL_MS = 1_000;
// 自動の引き継ぎが混雑で終わったら、0〜0.5秒待ってやり直す（売り切れなどで止まるまで）
const RESTART_MAX_DELAY_MS = 500;
const RESTART_REASONS = new Set(["timeout", "upstream_error"]);

type HandoffRun = {
  id: number;
  productId: number;
  paymentMethod: string;
  auto: boolean;
  attempt: number;
  /** 1行の表示に使う、元の新着通知の文言（手動は空） */
  label: string;
};

const EXTENSION_MISSING = "extension_missing";

// 自動の引き継ぎの1行（実行中はここから作り、終わったら結果を残す）
function runningLine(run: HandoffRun, queued: number): AutoLine {
  const retry = run.attempt > 1 ? `（混雑のためやり直し ${run.attempt}回目）` : "";
  const wait = queued > 0 ? `・順番待ち ${queued}件` : "";
  return { text: `自動: ${run.label} を引き継ぎ中${retry}${wait}`, tone: "warn" };
}

function resultLine(run: HandoffRun, reason: string | null): AutoLine {
  if (reason === null) return { text: `自動: ${run.label} の確認画面を開きました`, tone: "ok" };
  if (reason === EXTENSION_MISSING)
    return {
      text: `自動: ${run.label} の確認画面を開けませんでした（拡張機能が入っていません）`,
      tone: "err",
    };
  if (reason === "not_purchasable")
    return { text: `自動: ${run.label} は売り切れでした`, tone: "err" };
  return { text: `自動: ${run.label} の引き継ぎに失敗しました（${reason}）`, tone: "err" };
}

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
  const [handoff, setHandoff] = useState<HandoffRun | null>(null);
  const handoffIds = useRef(0);
  const [autoOpen, setAutoOpen] = useState(loadAutoOpen);
  const autoOpenRef = useRef(autoOpen);
  const seenRef = useRef<Set<string> | null>(null);
  const [queue, setQueue] = useState<Arrival[]>([]);
  const [autoResult, setAutoResult] = useState<AutoLine | null>(null);
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

  const loadingNotes = useRef(false);
  const loadNotes = useCallback(() => {
    if (loadingNotes.current) return; // 前の取得が終わっていなければ重ねない
    loadingNotes.current = true;
    api
      .notifications()
      .then(
        (list) => {
          setNotes(list);
          const { arrivals, seen } = collectArrivals(list.items, seenRef.current);
          seenRef.current = seen;
          if (autoOpenRef.current && arrivals.length > 0) setQueue((q) => enqueue(q, arrivals));
        },
        () => undefined,
      )
      .finally(() => {
        loadingNotes.current = false;
      });
  }, []);

  const loadStatus = useCallback(() => {
    setNow(new Date());
    api.autoStatus().then(setStatus, () => undefined);
  }, []);

  useEffect(() => {
    loadStatus();
    const timer = setInterval(loadStatus, POLL_MS);
    return () => clearInterval(timer);
  }, [loadStatus]);

  useEffect(() => {
    loadNotes();
    const timer = setInterval(loadNotes, NOTE_POLL_MS);
    return () => clearInterval(timer);
  }, [loadNotes]);

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
        handoff: false,
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

  // 引き継ぎ（確認画面まで）を開始する。進捗は HandoffProgress が SSE で表示する。
  const startHandoff = useCallback(
    (productId: number, paymentMethod: string, auto = false, label = "") => {
      handoffIds.current += 1;
      setHandoff({ id: handoffIds.current, productId, paymentMethod, auto, attempt: 1, label });
    },
    [],
  );

  // 引き継ぎが動いていなければ、順番待ちの一番新しい新着通知を開く（同時に1件だけ）
  useEffect(() => {
    if (handoff !== null || accountId === null || queue.length === 0) return;
    const [next, ...rest] = queue;
    setQueue(rest);
    startHandoff(next.product_id, next.payment_method ?? DEFAULT_PAYMENT_ID, true, next.message);
  }, [handoff, accountId, queue, startHandoff]);

  function changeAutoOpen(on: boolean) {
    setAutoOpen(on);
    autoOpenRef.current = on;
    saveAutoOpen(on);
    if (on) return;
    // OFF: 順番待ちを空にし、実行中の自動の引き継ぎも止める（ダイアログが無く、ほかに止める手段がないため）
    setQueue([]);
    setHandoff((h) => (h?.auto ? null : h));
    setAutoResult(null);
  }

  // 自動の引き継ぎを終えて結果を1行に残す（すぐ次へ進む）
  function finishAuto(run: HandoffRun, reason: string | null) {
    setAutoResult(resultLine(run, reason));
    setHandoff((h) => (h?.id === run.id ? null : h));
  }

  // 自動の引き継ぎだけ: 混雑ならやり直し、それ以外（売り切れなど）で止まったらすぐ次へ
  function handoffFailed(run: HandoffRun, reason: string) {
    if (!run.auto) return;
    if (RESTART_REASONS.has(reason)) {
      setTimeout(() => {
        setHandoff((h) =>
          h?.id === run.id && autoOpenRef.current ? { ...h, attempt: h.attempt + 1 } : h,
        );
      }, Math.random() * RESTART_MAX_DELAY_MS);
    } else {
      finishAuto(run, reason);
    }
  }

  const openArrival = useCallback(
    (note: AppNotification) => {
      if (note.product_id === null) return;
      startHandoff(note.product_id, note.payment_method ?? DEFAULT_PAYMENT_ID);
    },
    [startHandoff],
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
                blocked={handoff?.auto ?? false}
                onRun={() =>
                  mode === "order"
                    ? setConfirming(true)
                    : mode === "handoff" && selected
                      ? startHandoff(selected.product_id, paymentId)
                      : execute(false)
                }
              />
              {outcome && <ResultCard outcome={outcome} />}
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
              status={status}
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
            onChanged={() => {
              loadStatus();
              loadNotes(); // 既読にした結果をすぐ反映する
            }}
            onOpenConfirmation={openArrival}
            autoOpen={autoOpen}
            onAutoOpenChange={changeAutoOpen}
            autoLine={handoff?.auto ? runningLine(handoff, queue.length) : autoResult}
            manualBlocked={handoff?.auto ?? false}
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
      {handoff && accountId !== null && (
        // 自動の引き継ぎは進捗ダイアログを出さない（SSE と拡張への引き継ぎは同じく動く）
        <div className={handoff.auto ? undefined : "backdrop"} hidden={handoff.auto}>
          <HandoffProgress
            key={`${handoff.id}-${handoff.attempt}`}
            accountId={accountId}
            productId={handoff.productId}
            paymentMethod={handoff.paymentMethod}
            extensionInstalled={isExtensionInstalled()}
            onReady={(h) => {
              if (isExtensionInstalled()) openConfirmation(h.cookie_value);
              if (handoff.auto)
                finishAuto(handoff, isExtensionInstalled() ? null : EXTENSION_MISSING);
            }}
            onClose={() => setHandoff(null)}
            auto={handoff.auto}
            onError={(reason) => handoffFailed(handoff, reason)}
          />
        </div>
      )}
      <footer className="foot">Pickup Assistant — の確定はサイトの画面で行います</footer>
    </div>
  );
}
