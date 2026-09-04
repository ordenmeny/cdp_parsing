import { useCallback, useEffect, useMemo, useState } from "react";
import { getSellers, setSellers } from "../api";
import type { Seller, SellerStatus } from "../types";
import {
  ChevronIcon,
  EditIcon,
  ExternalIcon,
  RefreshIcon,
  SearchIcon,
  StoreIcon,
} from "./Icons";
import { SellerEditor } from "./SellerEditor";
import { StatusBadge, statusLabels } from "./StatusBadge";

type Filter = SellerStatus | "all";
type Notify = (message: string, kind?: "success" | "error") => void;
const PAGE_SIZE = 10;

const filters: { value: Filter; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "correct", label: "Корректные" },
  { value: "unconfirmed", label: "На проверке" },
  { value: "incorrect", label: "Некорректные" },
];

export function SellersView({ notify }: { notify: Notify }) {
  const [sellers, setSellerRows] = useState<Seller[]>([]);
  const [allSellers, setAllSellers] = useState<Seller[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkStatus, setBulkStatus] = useState<SellerStatus>("correct");
  const [editing, setEditing] = useState<Seller | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);

  const load = useCallback(
    async (currentFilter: Filter, quiet = false) => {
      if (!quiet) setLoading(true);
      try {
        const [rows, totals] = await Promise.all([
          getSellers(currentFilter === "all" ? undefined : currentFilter),
          currentFilter === "all" ? Promise.resolve(null) : getSellers(),
        ]);
        setSellerRows(rows);
        setAllSellers(totals ?? rows);
        setSelected(new Set());
      } catch (error) {
        notify(error instanceof Error ? error.message : "Не удалось загрузить продавцов", "error");
      } finally {
        setLoading(false);
      }
    },
    [notify],
  );

  useEffect(() => {
    void load(filter);
  }, [filter, load]);

  const counts = useMemo(() => {
    const result = { all: allSellers.length, correct: 0, unconfirmed: 0, incorrect: 0 };
    allSellers.forEach((seller) => result[seller.status]++);
    return result;
  }, [allSellers]);

  const filteredSellers = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("ru");
    if (!needle) return sellers;
    return sellers.filter((seller) =>
      [seller.name, seller.seller_id, seller.official_name, seller.inn]
        .join(" ")
        .toLocaleLowerCase("ru")
        .includes(needle),
    );
  }, [search, sellers]);

  const pageCount = Math.max(1, Math.ceil(filteredSellers.length / PAGE_SIZE));
  const pageStart = (currentPage - 1) * PAGE_SIZE;
  const visible = filteredSellers.slice(pageStart, pageStart + PAGE_SIZE);

  useEffect(() => {
    setCurrentPage(1);
  }, [filter, search]);

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, pageCount));
  }, [pageCount]);

  const pageItems = useMemo(() => {
    if (pageCount <= 7) {
      return Array.from({ length: pageCount }, (_, index) => index + 1);
    }

    const items: (number | string)[] = [1];
    const start = Math.max(2, currentPage - 1);
    const end = Math.min(pageCount - 1, currentPage + 1);
    if (start > 2) items.push("left-gap");
    for (let page = start; page <= end; page += 1) items.push(page);
    if (end < pageCount - 1) items.push("right-gap");
    items.push(pageCount);
    return items;
  }, [currentPage, pageCount]);

  const allVisibleSelected = visible.length > 0 && visible.every((seller) => selected.has(seller.seller_id));

  const toggleAll = () => {
    setSelected((current) => {
      const next = new Set(current);
      visible.forEach((seller) => {
        if (allVisibleSelected) next.delete(seller.seller_id);
        else next.add(seller.seller_id);
      });
      return next;
    });
  };

  const toggleOne = (sellerId: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(sellerId)) next.delete(sellerId);
      else next.add(sellerId);
      return next;
    });
  };

  const applyBulkStatus = async () => {
    setUpdating(true);
    try {
      await setSellers(
        [...selected].map((sellerId) => ({ seller_id: sellerId, status: bulkStatus })),
      );
      notify(`Статус «${statusLabels[bulkStatus]}» установлен: ${selected.size}`);
      await load(filter, true);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Не удалось обновить продавцов", "error");
    } finally {
      setUpdating(false);
    }
  };

  const replaceSeller = (updated: Seller) => {
    setEditing(null);
    notify(`Продавец «${updated.name}» обновлён`);
    void load(filter, true);
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">База продавцов</span>
          <h1>Продавцы</h1>
          <p>Проверяйте ссылки, реквизиты и управляйте статусами.</p>
        </div>
        <button className="button button--ghost" type="button" onClick={() => void load(filter)}>
          <RefreshIcon />
          Обновить
        </button>
      </div>

      <section className="stats-grid" aria-label="Статистика продавцов">
        <article className="stat-card stat-card--dark">
          <div className="stat-card__icon"><StoreIcon /></div>
          <span>Всего продавцов</span>
          <strong>{counts.all}</strong>
          <small>в базе данных</small>
        </article>
        <article className="stat-card">
          <span className="stat-card__marker stat-card__marker--correct" />
          <span>Корректные</span>
          <strong>{counts.correct}</strong>
          <small>{counts.all ? Math.round((counts.correct / counts.all) * 100) : 0}% от общего числа</small>
        </article>
        <article className="stat-card">
          <span className="stat-card__marker stat-card__marker--pending" />
          <span>На проверке</span>
          <strong>{counts.unconfirmed}</strong>
          <small>ожидают обработки</small>
        </article>
        <article className="stat-card">
          <span className="stat-card__marker stat-card__marker--incorrect" />
          <span>Некорректные</span>
          <strong>{counts.incorrect}</strong>
          <small>требуют внимания</small>
        </article>
      </section>

      <section className="panel sellers-panel">
        <div className="panel__toolbar">
          <div className="filter-tabs" role="tablist" aria-label="Фильтр статуса">
            {filters.map((item) => (
              <button
                key={item.value}
                type="button"
                role="tab"
                aria-selected={filter === item.value}
                className={filter === item.value ? "active" : ""}
                onClick={() => setFilter(item.value)}
              >
                {item.label}
                <span>{counts[item.value]}</span>
              </button>
            ))}
          </div>
          <label className="search-box">
            <SearchIcon />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Имя, ID или ИНН"
              aria-label="Поиск продавца"
            />
          </label>
        </div>

        {selected.size > 0 ? (
          <div className="bulk-bar">
            <strong>Выбрано: {selected.size}</strong>
            <span className="bulk-bar__separator" />
            <span>Изменить статус на</span>
            <select value={bulkStatus} onChange={(event) => setBulkStatus(event.target.value as SellerStatus)}>
              <option value="correct">Корректный</option>
              <option value="unconfirmed">На проверке</option>
              <option value="incorrect">Некорректный</option>
            </select>
            <button
              className="button button--small button--primary"
              type="button"
              disabled={updating}
              onClick={() => void applyBulkStatus()}
            >
              {updating ? <span className="spinner" /> : null}
              Применить
            </button>
            <button className="text-button" type="button" onClick={() => setSelected(new Set())}>
              Отменить выбор
            </button>
          </div>
        ) : null}

        <div className="table-scroll">
          <table className="seller-table">
            <thead>
              <tr>
                <th className="check-cell">
                  <input type="checkbox" checked={allVisibleSelected} onChange={toggleAll} aria-label="Выбрать всех" />
                </th>
                <th>Продавец</th>
                <th>Статус</th>
                <th>Реквизиты</th>
                <th>Контакты</th>
                <th aria-label="Действия" />
              </tr>
            </thead>
            <tbody>
              {!loading && visible.map((seller) => (
                <tr key={seller.seller_id} className={selected.has(seller.seller_id) ? "selected" : ""}>
                  <td className="check-cell">
                    <input
                      type="checkbox"
                      checked={selected.has(seller.seller_id)}
                      onChange={() => toggleOne(seller.seller_id)}
                      aria-label={`Выбрать ${seller.name}`}
                    />
                  </td>
                  <td>
                    <div className="seller-cell">
                      <span className="seller-avatar">{seller.name.slice(0, 1).toUpperCase()}</span>
                      <div>
                        <strong>{seller.name}</strong>
                        <span>ID {seller.seller_id}</span>
                        <a href={seller.link_to_seller} target="_blank" rel="noreferrer">
                          Открыть магазин <ExternalIcon />
                        </a>
                      </div>
                    </div>
                  </td>
                  <td><StatusBadge status={seller.status} /></td>
                  <td>
                    <div className="two-lines">
                      <span>{seller.inn ? `ИНН ${seller.inn}` : "ИНН не указан"}</span>
                      <small>{seller.ogrn ? `ОГРН ${seller.ogrn}` : "ОГРН не указан"}</small>
                    </div>
                  </td>
                  <td>
                    <div className="two-lines">
                      <span>{seller.email || "—"}</span>
                      <small>{seller.phone || "Телефон не указан"}</small>
                    </div>
                  </td>
                  <td>
                    <button className="icon-button" type="button" onClick={() => setEditing(seller)} aria-label={`Редактировать ${seller.name}`}>
                      <EditIcon />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {loading ? (
          <div className="loading-state"><span className="spinner spinner--dark" />Загружаем продавцов…</div>
        ) : filteredSellers.length === 0 ? (
          <div className="empty-state"><StoreIcon /><strong>Продавцы не найдены</strong><span>Измените фильтр или поисковый запрос.</span></div>
        ) : (
          <footer className="table-footer">
            <span>
              Показано {pageStart + 1}–{Math.min(pageStart + PAGE_SIZE, filteredSellers.length)} из {filteredSellers.length}
            </span>
            <nav className="pagination" aria-label="Страницы продавцов">
              <button
                type="button"
                disabled={currentPage === 1}
                onClick={() => setCurrentPage((page) => page - 1)}
                aria-label="Предыдущая страница"
              >
                <ChevronIcon className="pagination__previous" />
              </button>
              {pageItems.map((item) =>
                typeof item === "number" ? (
                  <button
                    key={item}
                    type="button"
                    className={currentPage === item ? "active" : ""}
                    onClick={() => setCurrentPage(item)}
                    aria-current={currentPage === item ? "page" : undefined}
                  >
                    {item}
                  </button>
                ) : (
                  <span key={item}>…</span>
                ),
              )}
              <button
                type="button"
                disabled={currentPage === pageCount}
                onClick={() => setCurrentPage((page) => page + 1)}
                aria-label="Следующая страница"
              >
                <ChevronIcon />
              </button>
            </nav>
          </footer>
        )}
      </section>

      {editing ? (
        <SellerEditor
          seller={editing}
          onClose={() => setEditing(null)}
          onSaved={replaceSeller}
          onError={(message) => notify(message, "error")}
        />
      ) : null}
    </>
  );
}
